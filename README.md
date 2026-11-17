# ClipPolish plugin website

A static website that lists ClipPolish plugins. It needs no build step and loads nothing from other websites: just
`index.html`, `app.js`, `style.css`, the list `index.json` and the plugin files in `plugins/`.

Each plugin card shows the icon, name, description, its kinds ("Contains: Stickers · Sound FX · Effects", with a
**Combo** badge when it has two or more), what it contains, its tags and version, plus three buttons:

- **Install in ClipPolish** opens `clippolish://install?url=<plugin link>`. On a phone with ClipPolish, this opens
  the app's install screen. That screen shows what the plugin contains and where it comes from, and installs
  nothing until the user taps Install. The app only accepts `https://` links here.
- **Download** gets the `.json` / `.zip` file. In the app, install it with **Plugins → File**.
- **Copy link** copies the plugin link. In the app, paste it with **Plugins → Link**.

The footer shows the link of `index.json`. In the app, **Plugins → Get more plugins → + Website** with that link
lists the same plugins, with Install and Update buttons.

## Try it on your computer

`fetch()` doesn't work from `file://`, so serve the folder:

```sh
cd website
python3 -m http.server 8000
# open http://localhost:8000
```

To show another plugin list, add `?index=<link to its index.json>` to the page address. That server must allow
cross-origin requests.

## Host it on GitHub Pages

1. Put the contents of this folder in a GitHub repository, either at the root or in a `docs/` folder.
2. In the repository, open **Settings → Pages**. Under "Build and deployment", choose **Deploy from a branch**,
   pick the branch and the folder (`/` or `/docs`), then **Save**.
3. After a minute the site is at `https://<user>.github.io/<repo>/`. The list is at
   `https://<user>.github.io/<repo>/index.json`.

GitHub Pages serves everything over https, which the app's install links require. Any other static host works the
same way (Netlify, Cloudflare Pages, your own server).

## Add a plugin

1. Make the plugin in the app (**Plugins → Share / Save**), or have your AI write one with the MCP tool
   `create_plugin`. Then run `test_plugin` and fix every problem it reports. You get a `.clippolish.json` file, or a
   `.clippolish.zip` when the plugin has pictures, sounds, fonts or looks.
2. Copy the file into `plugins/`.
3. Add an entry to the `plugins` list in `index.json`:

```json
{
  "id": "acme.neon_titles",
  "name": "Neon titles",
  "description": "Glowing title cards",
  "icon": "💡",
  "author": "Acme",
  "version": 3,
  "tags": ["titles", "neon"],
  "url": "plugins/neon-titles.clippolish.zip",
  "contents": "6 templates · 1 styles",
  "counts": { "templates": 6, "packs": 1 },
  "requires": { "app": "0.1.1", "plugins": ["acme.base@2"] },
  "preview": "previews/neon-titles.jpg",
  "homepage": "https://example.com/neon"
}
```

- `id` and `version` must match the plugin file. Raise `version` in both places for every update; the app then
  shows an **Update** button.
- `url`, `preview` and `homepage` may be relative to `index.json`.
- `counts` drives the kind filters (Stickers, Effects, Filters, Transitions, Sound FX, Music, Voice effects, Text,
  Fonts, Animations, Templates, Styles, Generators, Automations, Combo; see docs/PLUGINS.md "Plugin kinds") and the
  "what it contains" chips. `sounds` count as Music when the plugin is tagged `music`. Use the plugin's part names: `effects`,
  `particles`, `transitions`, `templates`, `components`, `motions`, `behaviors`, `packs`, `layouts`, `luts`, `fonts`,
  `sounds`, `stickers`, `audioFx`, `generators`, `eases`, `rules`, `live`, `animations`. Without `counts`, the site reads the `contents`
  text instead.
- `requires` is a copy of the plugin's own `requires`, so people can see what to install first. The app checks the
  plugin file itself.
- `kind` (optional) is the plugin's declared primary kind (`"COMBO"`, `"STICKER"`…), added to the computed ones.
- `contents`, `counts`, `kind`, `requires`, `preview` and `homepage` are optional. `?kind=STICKER` in the page address
  opens the list filtered by that kind.

The sample plugins in `plugins/` show every kind of part: effects with a behaviour and an easing curve, particle
presets, a component, title templates with a style pack, colour looks (LUTs), recording rules, a plugin that
`requires` two others (Party titles needs Particle pack and Neon titles), and a `.zip` plugin with files (Beat
stickers: a sticker pack with PNG / SVG / Lottie stickers, a sound preset and an audio-reactive effect; its source
folder is `plugins/beat-stickers/`, zip it with `cd plugins/beat-stickers && zip -r ../beat-stickers.clippolish.zip .`).

**Free sound pack** (`plugins/free-sounds.clippolish.zip`, id `clippolish.free_sounds`): ClipPolish's own 30 sound
effects, all synthesised by `tools/make_free_sounds.py` (standard-library Python; no samples, so the sounds are ours to
give away). Run `python3 tools/make_free_sounds.py` from this repo's root to rebuild `plugins/free-sounds/` and the
zip (it uses macOS `afconvert` or `ffmpeg` for AAC, else keeps WAV). The app's Sound FX tray offers it with a Download
card and fetches it from
`https://raw.githubusercontent.com/Santoshkurmi/clippolish_plugins/main/plugins/free-sounds.clippolish.zip`, so it
works once this repo is pushed to `main` (no GitHub Pages needed for that).
