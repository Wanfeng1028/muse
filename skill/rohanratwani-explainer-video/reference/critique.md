# The critique loop

Mandatory before every render the user will see.

```sh
cd videos/<slug>
T=$(node -e 'const b=require("./beats.json");console.log(b.flatMap(x=>[(x.start+0.35).toFixed(2),(x.end-0.45).toFixed(2)]).join(","))')
cd edit && npx --yes hyperframes snapshot --at "$T" --no-end -o ../snaps --describe false
```
That snapshots every beat 0.35s after it starts (catches entrance bugs and empty frames) and
0.45s before it ends (the fully built state, just before the exit). Read `snaps/contact-sheet-*.jpg`.

Score each frame 1 to 10 on:
1. **Legibility:** every word readable at phone size? Nothing under the minimum sizes?
2. **Composition:** balanced, no dead half of the frame, nothing jammed into a corner?
3. **Hierarchy:** one obvious thing to look at first?
4. **Collisions:** nothing overlapping by accident, nothing clipped, nothing under the chrome?
5. **Concept clarity:** would the picture make sense with the sound off?
6. **Consistency:** same card style, chips and accent use as the rest of the video?
7. **Motion** (judge from a render or several close snapshots): does every beat move?

Fix the worst three, re-snapshot, repeat until every frame is 8+. Typical first-pass failures:
labels too small, empty card space, a stamp sitting on a label, a beat that opens on a blank
frame, a counter showing "0" before it starts.
