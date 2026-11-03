# Fonts

No font is bundled here. The title act (`GLYPH_TEXT` in `src/config.ts`) needs a CJK-capable
bold face at the path named by `GLYPH_FONT_FILE`, which defaults to:

```
public/fonts/NotoSansSC-Bold.otf
```

Drop that file in, or point `GLYPH_FONT_FILE` at a different font. Noto Sans SC is licensed under
the SIL Open Font License 1.1 and is available from
<https://fonts.google.com/noto/specimen/Noto+Sans+SC>.

Set `GLYPH_TEXT` to whatever you want the swarm to write. Latin and CJK both work; the glyph is
sampled as coverage, so heavy weights hold their strokes better than light ones once the jitter is
applied.
