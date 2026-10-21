# Noto Sans SC

Retrieved 2026-09-19 from the official Google Fonts repository. No Memmy
assets were used. The font binary and OFL.txt are unmodified upstream bytes;
only the local font filename replaces `[wght]` with `-wght`.

## Source And Integrity

- Repository: https://github.com/google/fonts/tree/main/ofl/notosanssc
- Font download: https://raw.githubusercontent.com/google/fonts/main/ofl/notosanssc/NotoSansSC%5Bwght%5D.ttf
- License download: https://raw.githubusercontent.com/google/fonts/main/ofl/notosanssc/OFL.txt
- Metadata: https://raw.githubusercontent.com/google/fonts/main/ofl/notosanssc/METADATA.pb
- Metadata's upstream repository: https://github.com/notofonts/noto-cjk
- Metadata's upstream source commit: `523d033d6cb47f4a80c58a35753646f5c3608a78`

The download URLs track main. The exact acquired bytes are pinned below using
SHA-256 and the independently returned Git blob IDs from the official directory
API. The source commit above is from METADATA.pb, not a Google Fonts checkout
commit. The Google Fonts main-ref API returned HTTP 403; no commit is invented.

| Local file | Bytes | SHA-256 | Verified upstream Git blob SHA-1 |
| --- | ---: | --- | --- |
| NotoSansSC-wght.ttf | 17772300 | a3041811a78c361b1de50f953c805e0244951c21c5bd412f7232ef0d899af0da | fb0637bafbcd804fe32152370a1225990745b4bc |
| OFL.txt | 4388 | 1c05c68c34f9708415aada51f17e1b0092d2cea709bf4a94cd38114f9e73d7d9 | 1c9f43281b8f216c5461fe9ac729afbade7724e4 |

## License

Copyright 2014-2021 Adobe, with Reserved Font Name 'Source'. SIL Open Font
License 1.1 permits bundling, embedding and redistribution with software;
retain the complete adjacent OFL.txt and copyright notice. Do not sell the
font by itself or relicense it under the application's license. No endorsement
by the font authors is implied.

## Contents And Size

- Internal typographic family: Noto Sans SC.
- Version: `2.004-H2;hotconv 1.0.118;makeotfexe 2.5.65603`.
- One variable TrueType file: 17.77 MB decimal / 16.95 MiB.
- `wght` axis: 100 through 900, default 100; real 400/500/600/700 supported.
- Legacy family/PostScript names include Thin because the default is 100;
  this is not a static Thin file. `fvar`, `gvar`, `avar`, HVAR and STAT exist.
- 31,036 glyphs; 30,890 mapped nonzero Unicode code points.
- 20,976 mapped Basic CJK code points and 6,582 Extension A code points.
- All upstream coverage is retained. This is the full Google Fonts SC file,
  not a UI-text subset or a claim to cover all Unicode CJK extensions,
  all languages, or emoji. Unsupported characters still need fallback fonts.
- `OS/2.fsType = 0`; complete table checksums and whole-font checksum pass.

One full variable file avoids four separate full Chinese weight files and
incomplete downloaded subset shards. No conversion, compression or glyph
subsetting was performed; no new tooling was installed. This prioritizes
offline desktop completeness, not minimal web cold-load bytes.

## Integration

Main must import `apps/web/src/r6-fonts.css`. It only declares the existing
`Noto Sans SC` family, normal style, continuous 100-900 weights, with swap.
There is no `local()` source, runtime CDN request, unicode-range restriction,
selector override, font-size or line-height change. Existing family stacks
continue to control usage. Preserve both font and license in distributions.

The public URL is `/fonts/NotoSansSC-wght.ttf`, following Vite's public-asset
convention. Main must verify its final base/path rewriting in the packaged
app, successful font requests, and actual rendered custom-font identity after
loading. Binary/native decoding tests do not establish browser acceptance.
