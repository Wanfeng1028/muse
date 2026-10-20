# Formats

| Format | Frame | Caption band (`K.CAP_TOP`) | Scenes stop at (`K.BAND`) | Caption size | Where it goes |
|---|---|---|---|---|---|
| `4x5` (default) | 1080×1350 | y 1150 | y 1098 | 50 px | X, LinkedIn, Substack Notes, Instagram feed |
| `9x16` | 1080×1920 | y 1560 | y 1500 | 54 px | Reels, Shorts, TikTok, Stories |
| `16x9` | 1920×1080 | y 930 | y 900 | 48 px | YouTube, X landscape, embeds |

- **9:16 safe area:** platform UI covers the bottom ~20% (caption, buttons) and a right rail (~120 px). Keep essential text inside x 60–960, y 220–1500; the kit's caption band already sits above the Reels caption area.
- **4:5** crops least on every feed and is the default.
- **16:9** has room for split screens (two worlds side by side) and wide camera moves; captions stay short because lines are long.

## Making more than one format

A film is authored for one format. For a second format, `studio.py new <slug>-9x16 --format 9x16 …`, copy `film.html`, `sound.py` and `sources/`, and re-lay-out using `K.W`, `K.H`, `K.BAND` instead of literal coordinates. Write positions as fractions of the frame from the start (`K.W * 0.37`), and the second format is mostly a review pass rather than a rewrite. The sound is the same file: copy `out/mix.wav`, or run the same `sound.py`.

Render and verify each format separately; run the blind read on the primary format only unless the layouts differ in what they show.
