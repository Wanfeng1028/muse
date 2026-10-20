# Shorts (9:16)

`page({ ..., w: 1080, h: 1920, vertical: true, chapters: [] })` switches to Shorts chrome: no
chapter chip or rail, big captions parked at 66cqh. Use `subtitleChunks(beats, { maxWords: 4 })`
for 2 to 4 word caption chunks.

- **Safe zone:** content between 9cqh and 62cqh. Nothing in the bottom 22% (title and buttons sit
  there) or the right 12% (the like and comment rail).
- **Frame 0 is the thumbnail.** Shorts autoplay, so the very first frame must already show the
  text hook and a visual. No fade-in from blank.
- 40 to 60 seconds, one idea, the last line short enough to loop back into the first.
- Example: `examples/chatgpt-dots-short/build.mjs`.
