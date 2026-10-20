# Review checklists

## A. Storyboard (before building)
- [ ] **Story and claims**
  - [ ] Logline fits in two sentences: tension → reveal → payoff → closing line.
  - [ ] ONE outcome thread runs from goal to result. Hypotheses, approaches, PR/result and payoff all name the same metric.
  - [ ] Every claim is traceable (source URL or user approval) and listed in BRIEF.md.
  - [ ] Demo-tenant numbers appear only inside UI shots, never as headline type or under a proof heading.
  - [ ] Copy is on-message (BRIEF on/off lists) and grammatical with every swapped word in a slot-machine pill.
- [ ] **Timing**
  - [ ] Every caption has a start time and ≥ 0.35 s/word of fully visible time.
  - [ ] Scenes are contiguous from 0 to the end, and section changes land on bar lines.
- [ ] **Assets**
  - [ ] Every referenced capture exists and shows what the scene claims. Readable text in it doesn't contradict the story.
  - [ ] Layout fits: caption band + window + safe margins.
- [ ] **Hand-offs and payoff**
  - [ ] Every boundary has a hand-off (dip default; CUT on the drop; XFADE only when backgrounds match).
  - [ ] The end card holds the full lockup ≥ 2.4 s, and the closing line pays off the opening.
- [ ] **Score plan:** hit list complete; music plan matches the section map.

## B. Scene (art director, per scene)
- [ ] **Copy:** verbatim, with clean line breaks, no widows, and punctuation tight after pills.
- [ ] **Timing:**
  - [ ] Hits land on the exact frames; render each hit frame.
  - [ ] Readability holds.
  - [ ] Content is complete before scene end − 0.25 s (dip hand-off), and nothing important happens in the first 6 frames.
- [ ] **Composition:**
  - [ ] One focal point, nothing inside the 96 px safe margin.
  - [ ] Caption band position and size match the other steps.
- [ ] **UI shots:**
  - [ ] Push-ins are aimed via rects.json; key UI text is ≥ 20 px on screen; zoom ≤ ~2.2×.
  - [ ] No half-cut lines of text at the window edges.
  - [ ] No readable text that contradicts the story; demo numbers stay out of focus.
- [ ] **Motion and colour:**
  - [ ] Eased, with spring pops; no linear moves except drifts; no jitter (render f, f+1, f+2).
  - [ ] Brand palette and status colours used consistently.

## C. Release (rendered MP4)
- [ ] **Story:** the 1 fps contact sheet reads as a story with the sound off.
- [ ] **Hand-offs** (check the boundary sheet):
  - [ ] No double-exposed text.
  - [ ] No blank or flash frames, unless intentional.
  - [ ] No sudden brightness collapse.
- [ ] **Look:**
  - [ ] Full-res frames at every UI moment are legible and crisp.
  - [ ] The grade is continuous; the close feels like release, brighter than the middle.
- [ ] **Audio:**
  - [ ] −14 ±0.5 LUFS integrated, ≤ −1 dBTP.
  - [ ] Duration is exact; the audio stream is present (AAC 48 kHz).
  - [ ] All hits are placed and the viz is checked. **A human listen is still required.**
- [ ] **First and last frames:** the first frame is clean, and the last 15 frames fade to black.
- [ ] **Deliverables:** the 4K master renders and spot-checks crisp (crop a UI region); the poster frame is exported.
- [ ] **Privacy:** no PII, keys, internal URLs, or customer data, and nothing the intake said must never appear.
- [ ] **README:** written (re-render, file map, music swap, licences).
