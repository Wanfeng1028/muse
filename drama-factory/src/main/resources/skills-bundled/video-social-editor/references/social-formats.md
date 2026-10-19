# Social Media Format Specs

## Supported output formats

| Format | Dimensions | Ratio | Best for |
|--------|-----------|-------|---------|
| `9:16` | 1080×1920 | Vertical | Instagram Stories, TikTok, YouTube Shorts, LinkedIn Stories |
| `1:1`  | 1080×1080 | Square  | Instagram feed, LinkedIn feed, Twitter/X |
| `4:5`  | 1080×1350 | Portrait | Instagram portrait feed (more screen space than square) |
| `16:9` | 1920×1080 | Landscape | YouTube, LinkedIn landscape post, Twitter/X |

## Recommended duration per platform

| Platform | Format | Sweet spot | Hard max |
|---------|--------|-----------|---------|
| Instagram Stories | 9:16 | 15–60s | 60s per story card |
| TikTok | 9:16 | 30–90s | 10 min |
| YouTube Shorts | 9:16 | 30–60s | 60s |
| LinkedIn | 9:16 or 16:9 | 60–90s | 10 min |
| Instagram Reels | 9:16 | 30–90s | 90s |
| Twitter/X | 16:9 or 1:1 | 30–140s | 140s |

## Output settings (all formats)

- Frame rate: 30fps (halved from typical 60fps source)
- Codec: H.264 (libx264), CRF 20, preset medium
- Audio: dropped unless user explicitly provides a VO audio file
- Container: .mp4
