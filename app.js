// ClipPolish plugin website. Plain JavaScript, no build step, no libraries.
// Reads index.json (format: docs/PLUGINS.md "Plugin websites") and shows one card per plugin, with search,
// kind filters (Stickers, Effects, Music… — where its parts show up in the app), a "Contains …" line with a Combo
// badge, an "Install in ClipPolish" deep link (clippolish://install?url=…) and a direct download.
// Another index can be shown with ?index=<link to index.json> (that server must allow cross-origin requests).
"use strict";

(function () {
  // Plugin parts: JSON part name -> [one, many] labels, for the "what it contains" chips of a card.
  const PARTS = {
    effects: ["effect", "effects"],
    particles: ["particle preset", "particle presets"],
    transitions: ["transition", "transitions"],
    templates: ["template", "templates"],
    components: ["component", "components"],
    motions: ["motion", "motions"],
    behaviors: ["behaviour", "behaviours"],
    packs: ["style pack", "style packs"],
    layouts: ["layout", "layouts"],
    luts: ["colour look", "colour looks"],
    fonts: ["font", "fonts"],
    sounds: ["sound", "sounds"],
    stickers: ["sticker pack", "sticker packs"],
    audioFx: ["sound preset", "sound presets"],
    generators: ["generator", "generators"],
    eases: ["easing curve", "easing curves"],
    rules: ["rule", "rules"],
    live: ["live rule", "live rules"],
    animations: ["animation", "animations"],
  };
  // Plugin kinds (docs/PLUGINS.md "Plugin kinds", the app's PluginKind): where a plugin's parts show up in the editor.
  // The order is the order of the filter chips; a plugin is in every kind it has parts of, COMBO when 2 or more.
  const KINDS = {
    STICKER: "Stickers", FX: "Effects", FILTER: "Filters", TRANSITION: "Transitions", SFX: "Sound FX", MUSIC: "Music",
    VOICE_FX: "Voice effects", TEXT: "Text", FONT: "Fonts", ANIMATION: "Animations", TEMPLATE: "Templates",
    STYLE: "Styles", GENERATOR: "Generators", AUTOMATION: "Automations", COMBO: "Combo",
  };
  // JSON part name -> kind, when only the counts are known (the same table as the app's PluginKinds.fromCounts).
  // Sounds are MUSIC when the plugin is tagged "music", else SFX; templates count as TEMPLATE.
  const PART_KIND = {
    stickers: "STICKER", effects: "FX", particles: "FX", luts: "FILTER", transitions: "TRANSITION", sounds: "SFX",
    audioFx: "VOICE_FX", fonts: "FONT", motions: "ANIMATION", behaviors: "ANIMATION", eases: "ANIMATION",
    templates: "TEMPLATE", components: "TEMPLATE", packs: "STYLE", layouts: "STYLE", generators: "GENERATOR",
    rules: "AUTOMATION", live: "AUTOMATION", animations: "AUTOMATION",
  };
  // Words used in the older "contents" text ("12 templates · 3 styles") -> part name.
  const CONTENT_WORDS = {
    rules: "rules", "live rules": "live", styles: "packs", layouts: "layouts", templates: "templates", motions: "motions",
    effects: "effects", transitions: "transitions", behaviours: "behaviors", behaviors: "behaviors", eases: "eases",
    generators: "generators", sounds: "sounds", looks: "luts", fonts: "fonts", components: "components",
    "particle presets": "particles", particles: "particles", animations: "animations",
    "sticker packs": "stickers", stickers: "stickers", "sound presets": "audioFx",
  };

  const $ = (sel) => document.querySelector(sel);
  const params = new URLSearchParams(location.search);
  const indexUrl = new URL(params.get("index") || "index.json", location.href).href;
  const isAndroid = /Android/i.test(navigator.userAgent);

  // ?kind=STICKER filters by kind (the older ?cat=<part name> still works).
  const startKind = (params.get("kind") || "").toUpperCase() || PART_KIND[params.get("cat")] || "all";
  const state = { plugins: [], query: params.get("q") || "", kind: KINDS[startKind] ? startKind : "all" };

  // ---------------------------------------------------------------- helpers

  /** An absolute http(s) link, or null (anything else, e.g. javascript:, is refused). */
  function safeUrl(raw, base) {
    if (typeof raw !== "string" || !raw.trim()) return null;
    try {
      const u = new URL(raw.trim(), base);
      return u.protocol === "https:" || u.protocol === "http:" ? u.href : null;
    } catch (e) {
      return null;
    }
  }

  function str(v, fallback) { return typeof v === "string" ? v : (fallback || ""); }

  /** Part counts: the entry's "counts", else read from its "contents" text. */
  function countsOf(e) {
    const out = {};
    if (e.counts && typeof e.counts === "object") {
      for (const [k, v] of Object.entries(e.counts)) if (PARTS[k] && Number(v) > 0) out[k] = Math.floor(Number(v));
      if (Object.keys(out).length) return out;
    }
    for (const piece of str(e.contents).split("·")) {
      const m = piece.trim().match(/^(\d+)\s+(.+)$/);
      if (!m) continue;
      const key = CONTENT_WORDS[m[2].toLowerCase()];
      if (key) out[key] = (out[key] || 0) + Number(m[1]);
    }
    return out;
  }

  /** Kinds from part counts, the "music" tag and the declared "kind", in KINDS order; COMBO with 2 or more. */
  function kindsOf(counts, tags, declared) {
    const music = tags.some((t) => t.toLowerCase() === "music");
    const found = new Set(Object.keys(counts).map((k) => (k === "sounds" && music ? "MUSIC" : PART_KIND[k])));
    const out = Object.keys(KINDS).filter((k) => k !== "COMBO" && found.has(k));
    if (out.length >= 2) out.push("COMBO");
    if (KINDS[declared] && !out.includes(declared)) out.push(declared);
    return out;
  }

  /** "Contains: Stickers · Sound FX · Effects" (Combo is shown as a badge instead). */
  function containsText(kinds) {
    const list = kinds.filter((k) => k !== "COMBO").map((k) => KINDS[k]);
    return list.length ? "Contains: " + list.join(" · ") : "";
  }

  function normalize(e) {
    const url = safeUrl(e.url, indexUrl);
    if (!url || !e.id || !e.name) return null;
    const tags = Array.isArray(e.tags) ? e.tags.filter((t) => typeof t === "string" && t.trim()).map((t) => t.trim()) : [];
    const req = e.requires && typeof e.requires === "object" ? e.requires : null;
    const counts = countsOf(e);
    return {
      id: str(e.id), name: str(e.name), description: str(e.description), icon: str(e.icon, "✨") || "✨",
      author: str(e.author), version: Number.isFinite(Number(e.version)) ? Number(e.version) : 1,
      tags, url, preview: safeUrl(e.preview, indexUrl), homepage: safeUrl(e.homepage, indexUrl),
      counts, kinds: kindsOf(counts, tags, str(e.kind).toUpperCase()),
      requires: req ? { app: str(req.app).trim(), plugins: Array.isArray(req.plugins) ? req.plugins.filter((p) => typeof p === "string") : [] } : null,
    };
  }

  function installLink(url) { return "clippolish://install?url=" + encodeURIComponent(url); }

  async function copy(text, button) {
    let ok = false;
    try {
      await navigator.clipboard.writeText(text);
      ok = true;
    } catch (e) {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      try { ok = document.execCommand("copy"); } catch (e2) { ok = false; }
      ta.remove();
    }
    if (button) {
      const old = button.textContent;
      button.textContent = ok ? "Copied" : "Copy failed";
      setTimeout(() => { button.textContent = old; }, 1600);
    }
  }

  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  // ---------------------------------------------------------------- filters

  function matches(p) {
    if (state.kind !== "all" && !p.kinds.includes(state.kind)) return false;
    const q = state.query.trim().toLowerCase();
    if (!q) return true;
    const hay = [p.name, p.description, p.author, p.id, p.tags.join(" "),
      Object.keys(p.counts).map((k) => PARTS[k].join(" ")).join(" "), p.kinds.map((k) => KINDS[k]).join(" ")].join(" ").toLowerCase();
    return q.split(/\s+/).every((w) => hay.includes(w));
  }

  function saveState() {
    const next = new URLSearchParams(location.search);
    if (state.query.trim()) next.set("q", state.query.trim()); else next.delete("q");
    if (state.kind !== "all") next.set("kind", state.kind); else next.delete("kind");
    next.delete("cat");
    const qs = next.toString();
    history.replaceState(null, "", location.pathname + (qs ? "?" + qs : "") + location.hash);
  }

  function renderKinds() {
    const nav = $("#categories");
    nav.textContent = "";
    const totals = {};
    for (const p of state.plugins) for (const k of p.kinds) totals[k] = (totals[k] || 0) + 1;
    const kinds = [["all", "All", state.plugins.length]].concat(
      Object.keys(KINDS).filter((k) => totals[k]).map((k) => [k, KINDS[k], totals[k]]));
    if (!kinds.some(([k]) => k === state.kind)) state.kind = "all";
    for (const [key, label, n] of kinds) {
      const b = el("button", "chip", label);
      b.type = "button";
      b.setAttribute("aria-pressed", String(key === state.kind));
      b.appendChild(el("span", "n", String(n)));
      b.addEventListener("click", () => {
        state.kind = key;
        saveState();
        renderKinds();
        renderGrid();
      });
      nav.appendChild(b);
    }
  }

  // ---------------------------------------------------------------- cards

  function requiresText(r, byId) {
    if (!r) return "";
    const parts = [];
    if (r.app) parts.push("ClipPolish " + r.app + " or newer");
    for (const dep of r.plugins) {
      const [id, min] = dep.split("@");
      const known = byId[id.trim()];
      parts.push((known ? known.name : id.trim()) + (min ? " (version " + min.trim() + "+)" : ""));
    }
    return parts.length ? "Needs " + parts.join(" · ") : "";
  }

  function card(p, byId) {
    const node = $("#card-template").content.firstElementChild.cloneNode(true);
    node.id = "plugin-" + p.id.replace(/[^A-Za-z0-9_-]/g, "-");
    if (p.preview) {
      node.querySelector(".card-preview").hidden = false;
      const img = node.querySelector(".card-preview img");
      img.src = p.preview;
      img.alt = p.name + " preview";
    }
    node.querySelector(".icon").textContent = p.icon;
    node.querySelector(".name").textContent = p.name;
    node.querySelector(".meta").textContent = [p.author ? "by " + p.author : "", "version " + p.version].filter(Boolean).join(" · ");
    const desc = node.querySelector(".desc");
    if (p.description) desc.textContent = p.description; else desc.remove();

    const kinds = node.querySelector(".kinds");
    if (p.kinds.includes("COMBO")) kinds.appendChild(el("span", "badge", "Combo"));
    const contains = containsText(p.kinds);
    if (contains) kinds.appendChild(document.createTextNode(contains)); else if (!kinds.children.length) kinds.remove();

    const list = node.querySelector(".contents");
    for (const [k, n] of Object.entries(p.counts)) {
      const li = el("li");
      li.appendChild(el("b", null, String(n)));
      li.appendChild(document.createTextNode(" " + PARTS[k][n === 1 ? 0 : 1]));
      list.appendChild(li);
    }
    if (!list.children.length) list.remove();

    const req = requiresText(p.requires, byId);
    if (req) {
      const r = node.querySelector(".requires");
      r.hidden = false;
      r.textContent = req;
    }

    const tags = node.querySelector(".tags");
    for (const t of p.tags) {
      const b = el("button", "tag", "#" + t);
      b.type = "button";
      b.title = "Show plugins tagged " + t;
      b.addEventListener("click", () => {
        state.query = t;
        $("#q").value = t;
        saveState();
        renderGrid();
      });
      tags.appendChild(b);
    }
    if (!tags.children.length) tags.remove();

    const install = node.querySelector(".install");
    install.href = installLink(p.url);
    install.setAttribute("aria-label", "Install " + p.name + " in ClipPolish");
    const download = node.querySelector(".download");
    download.href = p.url;
    download.setAttribute("download", "");
    download.setAttribute("aria-label", "Download " + p.name);
    const copyBtn = node.querySelector(".copy");
    copyBtn.setAttribute("aria-label", "Copy the link of " + p.name);
    copyBtn.addEventListener("click", () => copy(p.url, copyBtn));
    return node;
  }

  function renderGrid() {
    const grid = $("#grid");
    grid.textContent = "";
    const byId = Object.fromEntries(state.plugins.map((p) => [p.id, p]));
    const shown = state.plugins.filter(matches);
    for (const p of shown) grid.appendChild(card(p, byId));
    if (!shown.length && state.plugins.length) grid.appendChild(el("p", "empty", "No plugins match. Try another word or kind."));
    $("#status").textContent = state.plugins.length
      ? shown.length + " of " + state.plugins.length + " plugins"
      : "This website has no plugins yet.";
  }

  // ---------------------------------------------------------------- start

  async function load() {
    $("#index-url").textContent = indexUrl;
    $("#copy-index").addEventListener("click", (ev) => copy(indexUrl, ev.currentTarget));
    $("#install-hint").hidden = isAndroid;
    const q = $("#q");
    q.value = state.query;
    q.addEventListener("input", () => {
      state.query = q.value;
      saveState();
      renderGrid();
    });
    try {
      const res = await fetch(indexUrl, { cache: "no-cache" });
      if (!res.ok) throw new Error("HTTP " + res.status);
      const idx = await res.json();
      if (typeof idx.name === "string" && idx.name.trim()) {
        $("#site-name").textContent = idx.name;
        document.title = idx.name;
      }
      if (typeof idx.description === "string" && idx.description.trim()) $("#site-description").textContent = idx.description;
      const seen = new Set();
      state.plugins = (Array.isArray(idx.plugins) ? idx.plugins : [])
        .map(normalize)
        .filter((p) => p && !seen.has(p.id) && seen.add(p.id))
        .sort((a, b) => a.name.localeCompare(b.name));
      renderKinds();
      renderGrid();
    } catch (e) {
      const s = $("#status");
      s.classList.add("error");
      s.textContent = "Couldn't load the plugin list (" + indexUrl + "): " + e.message +
        (location.protocol === "file:" ? ". Open the page through a web server, e.g. python3 -m http.server in this folder." : "");
    }
  }

  load();
})();
