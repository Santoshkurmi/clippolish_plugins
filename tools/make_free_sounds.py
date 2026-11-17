#!/usr/bin/env python3
"""Builds ClipPolish's free sound pack from scratch.

Every sound is synthesised by this script (oscillators, filtered noise, envelopes): no samples and no third-party
audio, so the pack is ours to give away and free to use in any video. Standard library only.

    python3 tools/make_free_sounds.py

writes plugins/free-sounds/ (plugin.json + sounds/*.m4a) and plugins/free-sounds.clippolish.zip.
The WAVs are converted to AAC .m4a with macOS `afconvert` (or `ffmpeg` when it is installed); without either the
pack keeps .wav files (bigger, same sounds). Raise VERSION (and the version in website/index.json) after a change.
"""
import json
import math
import os
import random
import shutil
import struct
import subprocess
import sys
import tempfile
import wave
import zipfile

SR = 44100
TAU = 2 * math.pi
VERSION = 1
PLUGIN_ID = "clippolish.free_sounds"

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGINS = os.path.normpath(os.path.join(HERE, "..", "plugins"))
PACK_DIR = os.path.join(PLUGINS, "free-sounds")
ZIP_PATH = os.path.join(PLUGINS, "free-sounds.clippolish.zip")


# ------------------------------------------------------------------ building blocks

def n_of(sec):
    return int(sec * SR)


def buf(sec):
    return [0.0] * n_of(sec)


class SVF:
    """State-variable filter (Chamberlin), run twice per sample so high cut-offs stay stable."""

    def __init__(self):
        self.lp = 0.0
        self.bp = 0.0

    def run(self, x, fc, damp):
        f = 2 * math.sin(math.pi * min(max(fc, 10.0), SR * 0.24) / (2 * SR))
        hp = 0.0
        for _ in range(2):
            hp = x - self.lp - damp * self.bp
            self.bp += f * hp
            self.lp += f * self.bp
        return self.lp, self.bp, hp


class OnePole:
    def __init__(self, fc):
        self.a = 1 - math.exp(-TAU * fc / SR)
        self.y = 0.0

    def lp(self, x):
        self.y += self.a * (x - self.y)
        return self.y

    def hp(self, x):
        return x - self.lp(x)


def ad(t, attack, decay):
    """Linear attack, exponential decay (time constant [decay] seconds)."""
    if t < 0:
        return 0.0
    if t < attack:
        return t / attack
    return math.exp(-(t - attack) / decay)


def saw(ph, harmonics=8):
    return sum(math.sin(k * ph) / k for k in range(1, harmonics + 1)) * 0.6


def square(ph, freq, top=9000.0):
    s = 0.0
    k = 1
    while k * freq < top and k < 40:
        s += math.sin(k * ph) / k
        k += 2
    return s * 0.8


def mix_into(out, src, at_sec, gain=1.0):
    start = n_of(at_sec)
    for i, v in enumerate(src):
        j = start + i
        if j >= len(out):
            break
        out[j] += v * gain
    return out


def damped(freqs, sec, decays, gains, rnd=None, noise_amt=0.0, noise_decay=0.002):
    """Sum of decaying sines (struck wood / metal), optionally with a short noise burst on top."""
    b = buf(sec)
    for i in range(len(b)):
        t = i / SR
        v = 0.0
        for f, d, g in zip(freqs, decays, gains):
            v += math.sin(TAU * f * t) * math.exp(-t / d) * g
        if rnd is not None and noise_amt:
            v += rnd.uniform(-1, 1) * noise_amt * math.exp(-t / noise_decay)
        b[i] = v
    return b


def band_noise_sweep(rnd, sec, fc_of, damp, amp_of):
    b = buf(sec)
    f = SVF()
    for i in range(len(b)):
        x = i / len(b)
        _, bp, _ = f.run(rnd.uniform(-1, 1), fc_of(x), damp)
        b[i] = bp * amp_of(x)
    return b


# ------------------------------------------------------------------ the sounds

def whoosh_air(r):
    lp = OnePole(500)
    b = band_noise_sweep(r, 0.75, lambda x: 250 + 2600 * math.sin(math.pi * x ** 0.9) ** 1.5, 0.7,
                         lambda x: math.sin(math.pi * x ** 0.9) ** 1.8)
    for i in range(len(b)):
        x = i / len(b)
        b[i] += lp.lp(r.uniform(-1, 1)) * 0.6 * math.sin(math.pi * x) ** 2
    return b


def whoosh_fast(r):
    return band_noise_sweep(r, 0.38, lambda x: 600 + 4500 * x, 0.5,
                            lambda x: (x / 0.7) ** 2 if x < 0.7 else math.exp(-(x - 0.7) * 12))


def swipe(r):
    return band_noise_sweep(r, 0.2, lambda x: 3000 + 4000 * x, 0.9, lambda x: math.sin(math.pi * x))


def swish_double(r):
    b = buf(0.5)
    one = band_noise_sweep(r, 0.22, lambda x: 1800 + 3500 * x, 0.6, lambda x: math.sin(math.pi * x) ** 1.3)
    two = band_noise_sweep(r, 0.22, lambda x: 2400 + 4200 * x, 0.6, lambda x: math.sin(math.pi * x) ** 1.3)
    mix_into(b, one, 0.0)
    return mix_into(b, two, 0.22, 0.9)


def zipper(r):
    b = buf(0.42)
    t = 0.0
    rate = 60.0
    while t < 0.4:
        f = SVF()
        fc = 2600 + 3000 * (t / 0.4)
        start = n_of(t)
        for i in range(n_of(0.006)):
            j = start + i
            if j >= len(b):
                break
            _, bp, _ = f.run(r.uniform(-1, 1) * math.exp(-i / (SR * 0.0015)), fc, 0.15)
            b[j] += bp * (0.6 + 0.4 * math.sin(math.pi * t / 0.4))
        rate = 60 + 140 * (t / 0.4)
        t += 1.0 / rate * r.uniform(0.85, 1.15)
    return b


def riser_short(r):
    sec = 1.1
    b = buf(sec)
    f = SVF()
    ph = 0.0
    for i in range(len(b)):
        x = i / len(b)
        fc = 400 * (6000 / 400) ** x
        _, bp, _ = f.run(r.uniform(-1, 1), fc, 0.6)
        freq = 200 * 6 ** x * (1 + 0.01 * math.sin(TAU * 6 * i / SR))
        ph += TAU * freq / SR
        tail = min(1.0, (1 - x) * sec / 0.03)
        b[i] = (bp * x ** 2 + math.sin(ph) * 0.35 * x ** 1.5) * tail
    return b


def riser_tension(r):
    sec = 2.2
    b = buf(sec)
    f = SVF()
    phs = [0.0, 0.0, 0.0]
    detune = [1.0, 1.006, 0.994]
    for i in range(len(b)):
        x = i / len(b)
        t = i / SR
        base = 110 * 4 ** x
        v = 0.0
        for k in range(3):
            phs[k] += TAU * base * detune[k] / SR
            v += saw(phs[k], 6)
        trem_rate = 4 + 12 * x
        trem = 0.75 + 0.25 * math.sin(TAU * trem_rate * t * (0.5 + 0.5 * x))
        _, bp, _ = f.run(r.uniform(-1, 1), 800 * 8 ** x, 0.7)
        tail = min(1.0, (1 - x) * sec / 0.03)
        b[i] = (v * 0.25 * trem + bp * 0.8 * x ** 2) * x ** 1.6 * tail
    return b


def downlifter(r):
    sec = 1.3
    b = buf(sec)
    f = SVF()
    ph = 0.0
    for i in range(len(b)):
        x = i / len(b)
        t = i / SR
        _, bp, _ = f.run(r.uniform(-1, 1), 6000 * (200 / 6000) ** x, 0.6)
        ph += TAU * 900 * (60 / 900) ** x / SR
        att = min(1.0, t / 0.02)
        b[i] = (bp * (1 - x) ** 1.5 + math.sin(ph) * 0.4 * (1 - x) ** 2) * att
    return b


def boom(r):
    b = buf(1.6)
    ph = 0.0
    lp1 = OnePole(1200)
    lp2 = OnePole(150)
    for i in range(len(b)):
        t = i / SR
        ph += TAU * (38 + 52 * math.exp(-t * 8)) / SR
        v = math.sin(ph) * ad(t, 0.002, 0.45)
        v += lp1.lp(r.uniform(-1, 1)) * 1.6 * math.exp(-t / 0.06)
        v += lp2.lp(r.uniform(-1, 1)) * 3.0 * ad(t, 0.01, 0.6)
        b[i] = math.tanh(1.5 * v)
    return b


def punch(r):
    b = buf(0.4)
    ph = 0.0
    f = SVF()
    lp = OnePole(800)
    for i in range(len(b)):
        t = i / SR
        ph += TAU * (55 + 105 * math.exp(-t * 30)) / SR
        v = math.sin(ph) * ad(t, 0.001, 0.12)
        _, bp, _ = f.run(r.uniform(-1, 1), 2500, 0.8)
        v += bp * math.exp(-t / 0.008) * 0.8
        v += lp.lp(r.uniform(-1, 1)) * math.exp(-t / 0.04) * 1.2
        b[i] = math.tanh(2 * v)
    return b


def click_soft(r):
    b = buf(0.06)
    f = SVF()
    for i in range(len(b)):
        t = i / SR
        _, bp, _ = f.run(r.uniform(-1, 1), 2000, 0.3)
        b[i] = bp * math.exp(-t / 0.004) + math.sin(TAU * 1200 * t) * math.exp(-t / 0.01) * 0.5
    return b


def tap(r):
    return damped([900, 2350], 0.15, [0.03, 0.012], [1.0, 0.5], r, 0.6, 0.002)


def pop_bubble(r):
    b = buf(0.16)
    ph = 0.0
    for i in range(len(b)):
        t = i / SR
        ph += TAU * (400 + 1000 * (1 - math.exp(-t * 40))) / SR
        b[i] = math.sin(ph) * ad(t, 0.002, 0.04)
    return b


def pop_cork(r):
    b = buf(0.3)
    ph = 0.0
    lp = OnePole(3000)
    hp = OnePole(200)
    for i in range(len(b)):
        t = i / SR
        ph += TAU * (300 + 80 * math.exp(-t * 30)) / SR
        v = lp.lp(r.uniform(-1, 1)) * math.exp(-t / 0.005) * 1.5
        v += math.sin(ph) * ad(t, 0.001, 0.05)
        b[i] = hp.hp(v)
    return b


def marimba(freq, sec, decay=0.25):
    return damped([freq, freq * 4, freq * 9.9], sec, [decay, decay * 0.3, decay * 0.1], [1.0, 0.25, 0.08])


def notify(r):
    b = buf(0.8)
    mix_into(b, marimba(880, 0.7), 0.0, 0.8)
    return mix_into(b, marimba(1318.5, 0.68), 0.12)


def bell(r):
    base = 660.0
    ratios = [0.56, 0.92, 1.19, 1.71, 2.0, 2.74, 3.0, 3.76, 4.07]
    gains = [1.0, 0.67, 1.0, 1.8, 2.67, 1.67, 1.46, 1.33, 1.33]
    durs = [1.0, 0.9, 0.65, 0.55, 0.325, 0.35, 0.25, 0.2, 0.15]
    b = damped([base * k for k in ratios], 2.0, [d * 0.7 for d in durs], gains)
    for i in range(min(len(b), n_of(0.002))):
        b[i] *= i / n_of(0.002)
    return b


def soft_tone(freq, sec, decay):
    b = buf(sec)
    for i in range(len(b)):
        t = i / SR
        ph = TAU * freq * t
        b[i] = (math.sin(ph) + 0.2 * math.sin(3 * ph)) * ad(t, 0.004, decay)
    return b


def success(r):
    b = buf(0.95)
    for k, (f, at) in enumerate([(1046.5, 0.0), (1318.5, 0.08), (1568.0, 0.16), (2093.0, 0.26)]):
        mix_into(b, soft_tone(f, 0.65, 0.35 if k == 3 else 0.12), at, 0.7)
    return b


def error(r):
    b = buf(0.55)
    for at, f in [(0.0, 180.0), (0.22, 170.0)]:
        lp = OnePole(2500)
        one = buf(0.16)
        ph = 0.0
        for i in range(len(one)):
            t = i / SR
            ph += TAU * f / SR
            env = min(1.0, t / 0.005, (0.16 - t) / 0.01)
            one[i] = lp.lp(square(ph, f, 6000)) * env
        mix_into(b, one, at)
    return b


def coin(r):
    b = buf(0.5)
    ph = 0.0
    for i in range(len(b)):
        t = i / SR
        f = 988.0 if t < 0.07 else 1318.5
        ph += TAU * f / SR
        env = 1.0 if t < 0.07 else math.exp(-(t - 0.07) / 0.13)
        b[i] = square(ph, f, 8000) * env * min(1.0, t / 0.002)
    return b


def cash(r):
    b = buf(1.3)
    lp = OnePole(600)
    for i in range(n_of(0.25)):
        t = i / SR
        b[i] += lp.lp(r.uniform(-1, 1)) * math.exp(-t / 0.03) * 2.0 + math.sin(TAU * 120 * t) * math.exp(-t / 0.05)
    for k in range(4):
        mix_into(b, damped([3100 + 400 * k], 0.03, [0.006], [0.4], r, 0.3, 0.001), 0.04 + 0.025 * k)
    ching = damped([2637, 3520, 2637 * 2.76, 3520 * 2.4, 5200], 1.1, [0.5, 0.45, 0.2, 0.15, 0.1], [1.0, 0.8, 0.35, 0.25, 0.2], r, 0.2, 0.003)
    mix_into(b, ching, 0.13, 0.9)
    return b


def typing(r):
    b = buf(1.6)
    t = 0.02
    while t < 1.5:
        space = r.random() < 0.12
        if space:
            key = damped([180, 420], 0.06, [0.02, 0.008], [0.8, 0.3], r, 0.5, 0.004)
        else:
            f = SVF()
            fc = r.uniform(2000, 4000)
            body = r.uniform(300, 450)
            key = buf(0.04)
            for i in range(len(key)):
                tt = i / SR
                _, bp, _ = f.run(r.uniform(-1, 1), fc, 0.4)
                key[i] = bp * math.exp(-tt / 0.006) + math.sin(TAU * body * tt) * math.exp(-tt / 0.015) * 0.5
        mix_into(b, key, t, r.uniform(0.6, 1.0))
        t += r.uniform(0.08, 0.17)
    return b


def shutter(r):
    b = buf(0.32)
    first = damped([1600], 0.05, [0.01], [0.6], r, 1.0, 0.004)
    mix_into(b, first, 0.0, 0.8)
    f = SVF()
    for i in range(n_of(0.02), n_of(0.1)):
        _, bp, _ = f.run(r.uniform(-1, 1), 2000, 0.8)
        b[i] += bp * 0.12
    second = damped([1100, 2500], 0.08, [0.015, 0.006], [0.8, 0.5], r, 1.2, 0.005)
    return mix_into(b, second, 0.11)


def tick_tock(r):
    b = buf(2.0)
    for k in range(4):
        hi = k % 2 == 0
        freqs = [3000, 1800] if hi else [2200, 1300]
        mix_into(b, damped(freqs, 0.06, [0.008, 0.012], [0.8, 0.6], r, 0.4, 0.001), k * 0.5)
    return b


def heartbeat(r):
    b = buf(1.5)

    def beat(gain):
        one = buf(0.25)
        ph = 0.0
        lp = OnePole(120)
        for i in range(len(one)):
            t = i / SR
            ph += TAU * (45 + 15 * math.exp(-t * 20)) / SR
            one[i] = (math.sin(ph) * ad(t, 0.004, 0.07) + lp.lp(r.uniform(-1, 1)) * 4 * ad(t, 0.004, 0.05)) * gain
        return one

    for at in (0.0, 0.8):
        mix_into(b, beat(1.0), at)
        mix_into(b, beat(0.7), at + 0.28)
    return [math.tanh(1.3 * v) for v in b]


def boing(r):
    b = buf(0.9)
    ph = 0.0
    for i in range(len(b)):
        t = i / SR
        freq = 180 + 40 * t + 140 * math.exp(-t * 3.5) * math.sin(TAU * 12 * t)
        ph += TAU * freq / SR
        b[i] = (math.sin(ph) + 0.3 * math.sin(2 * ph) + 0.15 * math.sin(3 * ph)) * ad(t, 0.003, 0.35)
    return b


def slide_whistle(r, f0, f1):
    sec = 0.8
    b = buf(sec)
    ph = 0.0
    f = SVF()
    for i in range(len(b)):
        x = i / len(b)
        t = i / SR
        freq = f0 * (f1 / f0) ** (x ** 0.9) * (1 + 0.02 * math.sin(TAU * 6 * t))
        ph += TAU * freq / SR
        _, bp, _ = f.run(r.uniform(-1, 1), freq, 0.2)
        env = min(1.0, t / 0.03, (sec - t) / 0.06)
        b[i] = (math.sin(ph) + 0.05 * math.sin(2 * ph) + bp * 0.08) * env
    return b


def rimshot(r):
    b = buf(1.5)

    def tom(f_hi, f_lo, gain):
        one = buf(0.3)
        ph = 0.0
        lp = OnePole(1500)
        for i in range(len(one)):
            t = i / SR
            ph += TAU * (f_lo + (f_hi - f_lo) * math.exp(-t * 25)) / SR
            one[i] = (math.sin(ph) * ad(t, 0.001, 0.15) + lp.lp(r.uniform(-1, 1)) * ad(t, 0.001, 0.02)) * gain
        return one

    mix_into(b, tom(180, 140, 0.9), 0.0)
    mix_into(b, tom(120, 95, 1.0), 0.18)
    # Cymbal: six detuned square waves (metallic) plus noise, high-passed.
    freqs = [205.3, 304.4, 369.6, 522.7, 540.0, 800.0]
    hp1 = OnePole(6000)
    hp2 = OnePole(6000)
    cym = buf(1.05)
    phs = [0.0] * 6
    for i in range(len(cym)):
        t = i / SR
        v = 0.0
        for k, f in enumerate(freqs):
            phs[k] += f / SR
            v += 1.0 if (phs[k] % 1.0) < 0.5 else -1.0
        v = v / 6 + r.uniform(-1, 1) * 0.8
        cym[i] = hp2.hp(hp1.hp(v)) * ad(t, 0.001, 0.32)
    mix_into(b, cym, 0.42, 1.6)
    mix_into(b, tom(110, 50, 0.8), 0.42)
    return b


def glitch(r):
    b = buf(0.55)
    pos = 0
    while pos < len(b):
        size = n_of(r.uniform(0.03, 0.06))
        kind = r.choice(["tone", "tone", "noise", "crush", "gap"])
        freq = r.uniform(200, 3000)
        hold = r.randint(4, 24)
        last = 0.0
        for i in range(size):
            j = pos + i
            if j >= len(b):
                break
            t = i / SR
            if kind == "tone":
                v = 1.0 if math.sin(TAU * freq * t) > 0 else -1.0
            elif kind == "noise":
                v = r.uniform(-1, 1)
            elif kind == "crush":
                if i % hold == 0:
                    last = round(math.sin(TAU * freq * 0.3 * t) * 3) / 3
                v = last
            else:
                v = 0.0
            edge = min(1.0, i / 44, (size - i) / 44)
            b[j] = v * 0.6 * edge
        pos += size
    return b


def honk(r):
    b = buf(0.6)
    for at, f in [(0.0, 330.0), (0.3, 294.0)]:
        lp = OnePole(2500)
        one = buf(0.24)
        ph = 0.0
        for i in range(len(one)):
            t = i / SR
            ph += TAU * f * (1 - 0.03 * t / 0.24) / SR
            env = min(1.0, t / 0.01, (0.24 - t) / 0.03)
            one[i] = lp.lp(saw(ph, 14) + 0.3 * square(ph, f, 5000)) * env
        mix_into(b, one, at)
    return b


# id, name, category, tags, make
SOUNDS = [
    ("whoosh_air", "Air whoosh", "whoosh", ["transition", "whoosh"], whoosh_air),
    ("whoosh_fast", "Fast whoosh", "whoosh", ["transition", "whoosh"], whoosh_fast),
    ("swipe", "Swipe", "whoosh", ["transition", "ui"], swipe),
    ("swish_double", "Double swish", "whoosh", ["transition"], swish_double),
    ("zip", "Zip", "whoosh", ["transition", "comedy"], zipper),
    ("riser_short", "Short riser", "riser", ["transition", "build-up"], riser_short),
    ("riser_tension", "Tension riser", "riser", ["transition", "build-up"], riser_tension),
    ("downlifter", "Downlifter", "riser", ["transition"], downlifter),
    ("boom", "Boom", "impact", ["impact", "hit"], boom),
    ("punch", "Punch", "impact", ["impact", "hit", "comedy"], punch),
    ("click_soft", "Soft click", "ui", ["ui", "click"], click_soft),
    ("tap", "Tap", "ui", ["ui", "click"], tap),
    ("pop_bubble", "Bubble pop", "ui", ["ui", "pop"], pop_bubble),
    ("pop_cork", "Cork pop", "ui", ["pop", "comedy"], pop_cork),
    ("notify", "Notification", "alert", ["ui", "alert"], notify),
    ("bell", "Bell", "alert", ["ding", "alert"], bell),
    ("success", "Success", "alert", ["ui", "win"], success),
    ("error", "Error", "alert", ["ui", "fail"], error),
    ("coin", "Coin", "alert", ["game", "win"], coin),
    ("cash", "Cash register", "real", ["money", "win"], cash),
    ("typing", "Typing", "real", ["keyboard", "tutorial"], typing),
    ("shutter", "Camera shutter", "real", ["camera", "photo"], shutter),
    ("tick_tock", "Tick tock", "real", ["clock", "time"], tick_tock),
    ("heartbeat", "Heartbeat", "real", ["tension"], heartbeat),
    ("boing", "Boing", "comedy", ["comedy", "cartoon"], boing),
    ("slide_up", "Slide whistle up", "comedy", ["comedy", "cartoon"], lambda r: slide_whistle(r, 500, 1700)),
    ("slide_down", "Slide whistle down", "comedy", ["comedy", "cartoon", "fail"], lambda r: slide_whistle(r, 1700, 450)),
    ("rimshot", "Ba-dum-tss", "comedy", ["comedy", "joke", "drums"], rimshot),
    ("honk", "Clown horn", "comedy", ["comedy", "cartoon"], honk),
    ("glitch", "Glitch", "impact", ["digital", "transition"], glitch),
]


# ------------------------------------------------------------------ output

def finish(samples):
    """Peak to −1 dBFS, but no 100 ms stretch louder than −12 dBFS RMS (steady tones would sound much louder than
    clicks otherwise); 2 ms fade in and 8 ms fade out (no clicks)."""
    peak = max(1e-9, max(abs(v) for v in samples))
    k = 0.89 / peak
    win = n_of(0.1)
    loudest = max(math.sqrt(sum(v * v for v in samples[i:i + win]) / win) for i in range(0, max(1, len(samples) - win + 1), win // 4))
    k = min(k, 10 ** (-12 / 20) / max(loudest, 1e-9))
    out = [v * k for v in samples]
    fi, fo = n_of(0.002), n_of(0.008)
    for i in range(min(fi, len(out))):
        out[i] *= i / fi
    for i in range(min(fo, len(out))):
        out[-1 - i] *= i / fo
    return out


def write_wav(path, samples):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1.0, min(1.0, v)) * 32767)) for v in samples))


def encode(wav, out_base):
    """AAC .m4a when an encoder is around, else the WAV itself. Returns the file written."""
    m4a = out_base + ".m4a"
    if shutil.which("afconvert"):
        subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", "-b", "80000", wav, m4a], check=True)
        return m4a
    if shutil.which("ffmpeg"):
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", wav, "-c:a", "aac", "-b:a", "80k", m4a], check=True)
        return m4a
    shutil.copyfile(wav, out_base + ".wav")
    return out_base + ".wav"


def main():
    sounds_dir = os.path.join(PACK_DIR, "sounds")
    if os.path.isdir(sounds_dir):
        shutil.rmtree(sounds_dir)
    os.makedirs(sounds_dir)
    entries = []
    total = 0.0
    with tempfile.TemporaryDirectory() as tmp:
        for i, (sid, name, cat, tags, make) in enumerate(SOUNDS):
            samples = finish(make(random.Random(1000 + i)))
            total += len(samples) / SR
            wav = os.path.join(tmp, sid + ".wav")
            write_wav(wav, samples)
            out = encode(wav, os.path.join(sounds_dir, sid))
            entries.append({"id": sid, "name": name, "file": "sounds/" + os.path.basename(out), "category": cat, "tags": tags})
            print(f"{sid:14s} {len(samples) / SR:5.2f} s  {os.path.getsize(out) / 1024:6.1f} KB")
    plugin = {
        "id": PLUGIN_ID,
        "name": "Free sound pack",
        "icon": "🔊",
        "author": "ClipPolish",
        "version": VERSION,
        "kind": "SFX",
        "description": f"{len(entries)} short sounds for edits: whooshes, risers, impacts, pops, clicks, dings, typing, a camera "
                       "shutter, a cash register, boing, slide whistles and more. Made from scratch by ClipPolish "
                       "(synthesised, no samples): free to use in any video.",
        "tags": ["sounds", "sfx", "transitions", "comedy", "free"],
        "sounds": entries,
    }
    with open(os.path.join(PACK_DIR, "plugin.json"), "w", encoding="utf-8") as f:
        json.dump(plugin, f, ensure_ascii=False, indent=2)
        f.write("\n")
    # Fixed dates so the same sounds give the same zip.
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as z:
        for root, dirs, files in os.walk(PACK_DIR):
            dirs.sort()
            for fn in sorted(files):
                full = os.path.join(root, fn)
                info = zipfile.ZipInfo(os.path.relpath(full, PACK_DIR), date_time=(2026, 11, 17, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                with open(full, "rb") as src:
                    z.writestr(info, src.read())
    print(f"{len(entries)} sounds, {total:.1f} s of sound, zip {os.path.getsize(ZIP_PATH) / 1024:.0f} KB -> {ZIP_PATH}")


if __name__ == "__main__":
    sys.exit(main())
