# Attribution

Third-party material bundled with Craft Anything, file by file. Rust crates are pulled from
crates.io under their own licences (see `Cargo.lock`) and are not listed here.

## Fonts (`assets/fonts/`)

All fonts are under the SIL Open Font License 1.1. The fonts are embedded unmodified; the
licence requires that the font software is not sold by itself and that reserved font names are
not used for modified versions.

| File | Font | Copyright | Source | Licence |
|---|---|---|---|---|
| `DMSans-Regular.ttf`, `DMSans-Medium.ttf`, `DMSans-Bold.ttf` | DM Sans 1.200 (body text, labels, headlines) | © 2014-2017 Indian Type Foundry, © 2019 Google LLC | https://github.com/googlefonts/dm-fonts (`Sans/Exports/`, commit 23aafb3) | `OFL-DMSans.txt` |
| `JetBrainsMono-Regular.ttf` | JetBrains Mono (code views) | © 2020 The JetBrains Mono Project Authors | https://github.com/JetBrains/JetBrainsMono | `OFL-JetBrainsMono.txt` |
| `GeistMono-Regular.ttf`, `GeistMono-Medium.ttf` | Geist Mono (labels and buttons) | © 2024 The Geist Project Authors | https://github.com/vercel/geist-font (`fonts/GeistMono/ttf/`) | `OFL-GeistMono.txt` |

## egui default fonts (`epaint_default_fonts` crate)

egui embeds these fonts through the `epaint_default_fonts` crate (crate licence:
`(MIT OR Apache-2.0) AND OFL-1.1 AND Ubuntu-font-1.0`). They are embedded unmodified; the licence
texts are in the crate's `fonts/` folder.

| File | Font | Copyright | Licence |
|---|---|---|---|
| `Ubuntu-Light.ttf` | Ubuntu Light (egui's default proportional font) | © 2011 Canonical Ltd. | Ubuntu Font Licence 1.0, `UFL.txt` |
| `NotoEmoji-Regular.ttf` | Noto Emoji | © 2013 Google Inc. | SIL OFL 1.1, `OFL.txt` |
| `Hack-Regular.ttf` | Hack (egui's default monospace font) | © 2018 Source Foundry Authors; Bitstream Vera © 2003 Bitstream, Inc.; DejaVu changes public domain | MIT and Bitstream Vera License, `Hack-Regular.txt` |
| `emoji-icon-font.ttf` | emoji-icon-font | © 2014 John Slegers | MIT, `emoji-icon-font-mit-license.txt` |

## Icons (`assets/icons/`)

| Files | Set | Copyright | Source | Licence |
|---|---|---|---|---|
| `*.svg` | Lucide | © Lucide Icons and Contributors | https://lucide.dev | ISC, `LICENSE-lucide.txt` |

## App icon (`assets/app-icon/`)

The raven, the Crafting Apps' shared icon, made by the ArtCraft team; not open source, used on the
brand terms below. See `assets/app-icon/LICENSE.txt`.

## Brand (`docs/brand/`)

The ArtCraft name, wordmark and logos are trademarks of the ArtCraft Team and are not covered by
the open-source licence; see `docs/brand/LICENSE-brand.txt`.

## Optional build-time fonts

Builds made with `CRAFT_FONTS_DIR` (craft-fonts), releases among them, also embed the fonts in
that folder (all OFL-1.1). Their packages ship each one's licence as `OFL-<font>.txt`; craft-fonts'
own `ATTRIBUTION.md` names their authors and pinned sources.
