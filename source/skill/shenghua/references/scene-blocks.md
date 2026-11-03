# Scene Blocks

The vocabulary for a voiceover edit. A shot is one `<section class="shot">` plus its timeline
lines. Pick a block for each line of speech, then time it to the word.

---

## Pacing

Short form (a Short, a reel, anything under ~3 minutes). Long form holds diagrams and cuts on ideas
instead: `long-form.md` → *Pacing*.

- **Cut every 1–4 seconds.** A shot held longer than ~5s needs internal motion (a push-in, a
  line drawing, a counter) or the viewer scrolls.
- **Cut on the word, not the sentence.** The shot starts at the first word of its idea.
- **Hits are punctuation.** Use `hit()` / `slam()` on the one word per shot that lands the
  point: a year, a name, a reveal, a punchline. More than ~2 hits per shot reads as noise.
- **Contrast beats intensity.** Slow down for reflective lines (fade entries, no hits, music
  down); speed up for montages (one word per cut).
- **End on a slam, then hold.** The last ~2.5s after the final word is the outro: handle, mascot,
  call to action.

## Transitions (`shot(id, in, out, enter)`)

| enter | Feel | Use for |
|---|---|---|
| *(none)* | hard cut | the default between fast beats |
| `whip` | sideways blur-whip | moving forward in the story |
| `whipUp` | vertical whip | lists, rising energy, "then…" |
| `zoom` | punch in from blur | reveals, new chapter |
| `fade` | soft | reflective lines, setup before a reveal |
| `soft` | scale-settle with blur | polished launches, calm reveals |
| `slide` | push in from the right, no blur | next item, next chapter |
| `wipe` | hard-edged left-to-right reveal | news beats, diagram steps |
| `iris` | circle opening from the centre | focusing on one person or thing |
| `flash` | white flash cut | a sudden turn, "and then…" |
| `glitch` | jitter + colour shift + buzz | failures, hacks, retro beats |
| `cut` | hard cut, even when the theme has a default entry | overriding the theme |

Omitting `enter` uses the theme's default (`templates.json` → `motion.enter`): hard cut for
`kinetic`/`brutalist`, `fade` for `documentary`/`minimal`, `wipe` for `newsroom`/`blueprint`, `soft` for
`aurora`, `glitch` for `retro`. The theme also scales every `hit()` shake and flash, so write the same
powers in every theme and let the theme decide how loud they look.

### Spring easing

`springEase(stiffness, damping)` is an analytic damped spring — a pure function of progress, so it can
stand in for a GSAP ease string anywhere: `stiffness` sets the speed (default 170), `damping` the
overshoot (default 12 ≈ 20% overshoot; ≥ 2·√stiffness never overshoots). `pop()`, `slam()` and `rise()`
take it as an optional last argument, with `"spring"` as the alias for the defaults:

```js
pop("#s05t", 12.4, "spring");                 // spring instead of back.out(2)
pop("#s05t", 12.4, .5, springEase(220, 9));   // slower pop, bigger overshoot
slam("#s01a", .44, 1.2, "spring");            // spring on the slam's entry (the hit is unchanged)
rise("#s01b", 1.46, .35, "spring");
```

Omit the argument for the stock feel. Reach for a spring on soft/organic beats (mascots, hosts,
product cards); keep the stock `expo.out`/`back.out` on hard hits and fast cuts.

---

## Blocks

### Kinetic slam
One huge word crashing in, everything else small around it.
```html
<div class="cx xl" id="s01a" style="top:520px;font-size:340px">JAVA</div>
```
```js
slam("#s01a", 0.44, 1.2);
```

### Strike-through
Kill a wrong assumption ("not built for the web").
```html
<span style="position:relative;display:inline-block">the web?<span class="strike" id="s01s"></span></span>
```
```js
tl.fromTo("#s01s",{scaleX:0},{scaleX:1,duration:.25,ease:EX},2.1); hit(2.12,.7);
```

### Highlight box
Marker-pen accent behind the key word.
```html
<span class="hl"><i id="s02hl"></i>DIFFERENT</span>
```
```js
tl.fromTo("#s02hl",{scaleX:0},{scaleX:1,duration:.3,ease:EX},4.58); hit(4.6,.6);
```

### Stacked slams
Each word of a slogan on its own line, one hit each ("WRITE / ONCE. / RUN / ANYWHERE.").
Add a `#pinkflash` burst on the last word. Hide captions.

### Counter
Years, stats, "30+ years later". Ease-out so it settles on the number.
```js
counter("#s03y", 1984, 1991, 6.5, 7.2); hit(7.2,.8);
counter("#s18n", 0, 200000, 50.6, 51.3, true);   // true adds thousands separators: 200,000
```

### Typewriter / terminal
Code, commands, errors. The template's `.term` gives the window chrome; `typer()` types plain
text and pushes typing SFX. For mixed colours (red error lines), use `terminal()`: each line is
HTML, and it types visible characters only, so tags and entities never break mid-way.
```js
terminal("#s05t", [
  {t: 12.0, e: 13.2, html: `<span class="k">synchronized</span> (lock) {`},
  {t: 13.6, e: 13.6, html: `<span style="color:var(--brand-error)">pinned: carrier blocked</span>`},
]);
```

### Swap
A value or word that changes on a beat: a count going 5 → 6, `RUNNING` → `HUNG`, a status
flipping. Before the first swap the element shows its authored HTML; every swap holds until the
next. Deterministic (any frame renders alone), unlike setting `textContent` from a GSAP callback.
```js
swap("#s07n", 24.8, "6"); hit(24.8, .5);
swap("#s07st", 31.2, `<span style="color:var(--brand-error)">HUNG</span>`);
```

### Photo tape-in
A person or artefact. Tilted polaroid with a tape strip, slow push-in (`drift` on the `<img>`
scale), a typed name tag and a stamp.

### Pan-and-zoom photo *(Ken Burns)*
Any photo held more than ~1.5s. Full-bleed or inside a `.photo` frame; the frame clips the push-in.
```html
<div class="photo" style="inset:0"><img id="s02img" src="assets/torvalds-portrait.jpg" alt="" style="object-position:50% 30%"></div>
<div class="credit" style="right:40px;top:160px">Krd / CC BY-SA 4.0</div>
```
```js
kenBurns("#s02img", 2.8, 6.1, "in");   // "in" · "out" · "left" · "right"
```

### Punch-in *(emphasis zoom)*
Submagic-style emphasis on a held frame: a face shot, a photo, a clip, a card. `punchIn()` is a slow
ease-in-out push between two times (keep `scale` ≤ ~1.12 — more reads as a reframe, not a nudge);
`punchPulse()` is a ~0.3s snap zoom and settle on the one word that lands the point. Both are pure
functions of `t` and silent — pair the pulse with `hit()` when the beat earns a sound.
```js
punchIn("#s07>img", 20.1, 23.4, 1.08);    // holds the face shot alive for its whole window
punchPulse("#s11a", 54.44, .08);          // snap on the reveal word, once
```
Never stack them on one element (one scale tween per element — `punchIn` replaces `kenBurns`, it
doesn't ride on it): to push *and* pulse the same frame, push the outer element and pulse its child —
nested scales compose (`punchIn("#s07", …)` the section, `punchPulse("#s07>img", …)` the image). And
never pulse the point itself more than once: one snap per shot, on the word the viewer must remember.

### Lower third
Name and role the first time a person appears on screen. Keep it above the caption zone
(vertical: top ≤ 1300).
```html
<div class="lower" id="s02lt" style="top:1180px"><div class="lower-name">Linus Torvalds</div><div class="lower-role">Creator of Linux &amp; Git</div></div>
```
```js
lowerThird("#s02lt", 3.2, 6.0);   // wipes in, wipes out 0.35s before the end
```

### Clip in frame *(picture-in-picture)*
The person speaking, the product demo, the launch on stage. The box size must match the size passed to
`extract_clip.sh`; always add a `.credit` line.
```html
<div class="pip" id="s04pip" style="left:90px;top:440px;width:900px;height:620px"><img id="s04img" alt=""><span class="tag">LF · 2017</span></div>
<div class="credit" style="left:90px;top:1080px">The Linux Foundation / CC BY 4.0</div>
```
```js
pop("#s04pip", 9.1);
clip("#s04img", "torvalds", 8.9, 12.6);   // same name, in and out as extract_clip.sh
```

### Reaction gif
A punchline beat: the facepalm, the "this is fine" dog. A `.pip` box, never full-bleed, looping for
1.5–2.5s. Fetch it with `find_media.py … --kind gif` and cut it with `extract_clip.sh … --loop`; the
box size matches the size passed to `extract_clip.sh`.

Only where it earns its place: zero is a fine answer, one is the norm, two only in a long video.
A line qualifies when the viewer would react to it out loud:
- a fail or a reveal of pain: "and then production just hangs", "it worked on my laptop"
- an understatement or a dry aside: "so that went well"
- the payoff after a long setup: "and that one keyword fixes it"

Never on the point itself (the fix, the definition, the number): the gif would steal the line the
viewer needs to remember. Query the reaction, not the topic: "this is fine", "facepalm", "mind blown",
"waiting skeleton", not "deadlock". GIPHY results carry no licence and often come from film or TV,
which YouTube's Content ID can claim; name each one in the report.
```html
<div class="pip" id="s09pip" style="left:140px;top:520px;width:800px;height:560px;transform:rotate(-3deg)"><img id="s09img" alt=""></div>
<div class="credit" style="left:140px;top:1100px">GIPHY / @creator</div>
```
```js
pop("#s09pip", 31.2);
clip("#s09img", "facepalm", 31.2, 33.4);
```

### Full-bleed clip
Same as the face shot, fed from `extract_clip.sh … vertical …` instead of the camera.
```html
<section class="shot face" id="s07"><img alt=""></section>
```
```js
shot("s07", 20.1, 23.4, "zoom"); clip("#s07>img", "launch", 20.1, 23.4);
```

### B-roll under narration
Footage playing full-bleed while the voice continues. Add a lower-third or a caption-safe headline so the shot still works muted. `broll()` is an alias for `clip()`.
```html
<section class="shot face" id="s08"><img alt=""></section>
<div class="lower" id="s08lt" style="top:1180px"><div class="lower-name">Linux Foundation</div><div class="lower-role">Collaboration Summit · 2017</div></div>
```
```js
shot("s08", 24.0, 28.5, "fade");
broll("#s08>img", "summit", 24.0, 28.5);
lowerThird("#s08lt", 24.2, 28.2);
```

### Portrait quote
The person's own words when their clip can't carry sound, or to repeat the line they just said.
```html
<div class="quote" id="s05q" style="top:420px">
  <div class="portrait"><img src="assets/torvalds-portrait.jpg" alt=""></div>
  <q>People can agree on the end result.</q>
  <cite>Linus Torvalds</cite>
</div>
```
```js
rise("#s05q", 12.7, .5);
```

### Document card
Quoting a paper, article or docs page on screen: the captured passage in a framed card, the source
title below, and an accent box that draws over the quoted lines. Capture the excerpt first — it lands
in `excerpts/` and registers itself in `excerpts.js`:
```bash
node scripts/excerpt.js <work> <url> --text "the quoted passage" --name kafka-paper
```
```html
<div id="s06d" style="position:absolute;left:90px;top:320px;width:900px"></div>
```
```js
docCard("#s06d", "kafka-paper", 14.2, 18.6);
```
The card rises in at `t0`, the highlight box draws left-to-right at `t0 + .3` (0.4s), and the card
leaves at `t1`. The container sets position and width; the frame hugs the image's aspect, so the
highlight fractions always land on the quoted lines. An excerpt name missing from `excerpts.js` fails
the render loudly with the capture command. Keep the whole card inside the shot area (vertical:
y = 150…1450) and hold it long enough to read the passage aloud — 3–5s. The excerpt is a quote, not
licensed media: excerpt.js records it in `credits.json` as unlicensed, and the report names it.

### Duo
Two people, two products, before/after: two photos side by side.
```html
<div class="duo" style="left:70px;right:70px;top:380px;height:760px">
  <div class="photo"><img src="assets/a.jpg" alt=""></div><div class="photo"><img src="assets/b.jpg" alt=""></div>
</div>
```

### Ticker
A scrolling news band, mostly for `newsroom`. Place it under the signature (vertical: top 150).
Make the text long enough to fill the shot's scroll: ~160px per second.
```html
<div class="ticker" style="top:150px"><span id="s04tk">BREAKING · … · BREAKING · …</span></div>
```
```js
ticker("#s04tk", 8.9, 12.6);
```

### Stamp
Verdicts: `NOT READY`, `CONFIDENTIAL`, `SUN MICROSYSTEMS`.

```html
<div class="cx stamp" id="s04stamp" style="top:840px;color:var(--accent);font-size:120px">CONFIDENTIAL</div>
```
```js
stamp("#s04stamp", 4.2);
```

### Era look
Period-specific texture for historical beats:
- **VHS**: `.scan` overlay, `.vhs` chromatic text, moving `.track` bars, blinking `● SP`, date stamp
- **CRT monitor**: beige bezel `div` around a period screenshot with `.scan` at 40%
- **Dossier**: dark manila card, mono metadata, stamped title

### Diagram
Hub-and-spoke or tree. Draw paths with `strokeDashoffset`, `pop()` the nodes, send `.pkt`
dots along the routes, then turn nodes green with a `ding` per node. Keep diagrams inside
y = 150…1450 on vertical so captions never collide.

### Chart
One SVG path drawn over 2–4s. A crash is a line that climbs then falls; pair it with a `down`
cue and a stamp.

### Montage
One shot per word, 0.8–2s each, a `whip` and a `hit` on each: an icon or logo plus one word.
The emotional "it's everywhere" beat.

### Logo wall
3x3 grid of `.logo` cards popping with a stagger; nine `pop` cues.
```js
stagger("#s09 .logo", 20.4, .09);   // one pop and one pop cue per card, in DOM order
```

### Logo chip
Naming a company mid-video without a wall: one small rounded chip carrying its logo. Only ever the
kit's own files (`kit/logos/…`) — never draw or approximate a logo the kit doesn't contain. Pick the
variant for the canvas (`BRAND.scheme`), as with the end card.
```html
<div class="logo-chip" id="s07lc" style="left:360px;top:620px"><img id="s07lg" alt=""></div>
```
```js
q("#s07lg").src = BRAND.logos.mark;
pop("#s07lc", 16.8);
```
Keep it in the shot area (vertical: y = 150…1450), one chip on screen at a time, 1.5–3s. For several
companies at once use the logo wall instead; for the closing brand beat use the logo end card.

### Path / journey
An SVG curve drawing slowly through labelled milestones — for "found its purpose along the way".

### Reflective photo
Full-bleed photo, darkened gradient, slow drift, large sentence fading in. No hits, music ducked.

### Host *(script mode)*
A cartoon character that talks when its lines play: mouth or bounce follow `speech.js`, blinks and bobs
run on their own. `kind` is `keeper` (teacher) or `drone` (sidekick); `who` is the speaker's name in
the script. The element is only a box; size it for the shot.
```html
<div class="host" id="s04pip" style="left:340px;top:520px;width:400px;height:420px"></div>
<div class="host" id="s04k" style="left:30px;top:1020px;width:330px;height:480px"></div>
```
```js
host("#s04pip","drone","pip"); host("#s04k","keeper","keeper");   // once per element, before the shots
mood("#s04pip","panic", 3.6, 5.2);    // "panic": shakes and sweats · "happy": eye becomes a smile
look("#s04pip", -1, .4, 0, 3.6);      // pupil direction, -1..1
point("#s04k", 6.6, 9.0);             // keeper raises her arm while explaining
```
A host appears in several shots as several elements; call `host()` on each. Keep a host in the same
spot across a scene so it reads as one character, and give the bubble side room.

### Speech bubble
The line a host is saying, on screen while it's said. Captions step aside while it's up.
```html
<div class="bubble tail-down" id="s04b" style="left:250px;top:330px">Which wire goes where?!</div>
```
```js
say("#s04b","pip",0);                 // times itself to Pip's first line in speech.js
bubble("#s04b", 3.5, 5.2);            // or explicit in/out
```
Tails: `tail-down`, `tail-up`, `tail-left`, `tail-right`; point it at the speaker. Short lines only,
under ~8 words. The teacher's narration stays in captions; bubbles are for the lines a character
says *in* the scene.

### Term pill
The first time a term is said, name it on screen. One pill per term, per video.
```html
<div class="pill" id="s05t" style="left:340px;top:250px">Topic: orders</div>
```
```js
pop("#s05t", line("keeper",4).s + 1.2);
```
Colour a pill by what it names (`style="background:#2dd4bf"`); keep one colour per kind of thing.

### Lane and tokens
An ordered log, a queue, a pipeline stage: a lane with a label, and tokens (letters, messages, jobs)
that fly into it. The token's number badge is its position (an offset, a ticket number).
```html
<div class="lane" id="s05l" style="left:190px;top:560px;width:820px;--lane:#ffb020"><span class="lane-name">P0</span></div>
<div class="token" id="s05a" style="left:540px;top:-80px;--tag:#9b7bff"><b>0</b></div>
```
```js
send("#s05a", 270, 635, 6.7);          // arc to (x, y), whoosh out, pop on landing
tl.set("#s05l",{borderColor:"#3ddc84"}, 17); // outline turns green: "in order"
```
Tokens are positioned by `left`/`top` (the token's centre) so `send()` can read where they start.
Slots in a lane: `left + 80 + i * 120`, centred on `top + 75`. `--tag` colours the strip that marks a
key; `--lane` colours the label. Start a token off-frame (`top:-80px`) to drop it in from above.

### Slots and tiles
Places in a row or grid (cores, carriers, pool slots) and the things that move between them (threads,
tasks, requests). The rack lays the slots out; `centerOf()` reads a slot's centre from that layout, and
`moveTo()` moves a tile there. Each move starts where the last move of that tile ended, so call the moves of
one tile in time order.
```html
<div class="rack" id="s04r" style="left:160px;top:200px">
  <div class="slot" id="c1"><small>core 1</small></div><div class="slot" id="c2"><small>core 2</small></div>
</div>
<div class="tile" id="t1" style="left:300px;top:560px">T1</div>
<div class="tile alt" id="t2" style="left:460px;top:560px">T2</div>
```
```js
const c1 = centerOf("#c1");
moveTo("#t1", c1.x, c1.y, 12.4, .6, "pop");     // optional sound cue on the move
tl.set("#c1", {attr:{class:"slot on"}}, 12.9);   // the core lights while it runs
moveTo("#t1", 300, 560, 16.0);                   // switched out: back to the queue
moveTo("#t2", c1.x, c1.y, 16.2);                 // the next thread takes the core
```
`.tile` is the main kind of thing (the brand colour), `.tile.alt` a second kind, `.tile.wait` a thing that
is parked or waiting. `.slot.on` glows, `.slot.dead` dims. A tile is 120x76 and centred on its
`left`/`top`, so slots fit one tile each.

### Scheduling timeline
Rows of blocks that fill in as the narration plays: which thread ran on which core, when a request waited,
a trace. Block times are video seconds; the axis spans the shot window `s`..`e`, and each block grows from
its `t` to its `e`.
```html
<div id="s05g" style="left:160px;top:420px;width:1600px"></div>
```
```js
gantt("#s05g", [
  {label:"core 1", blocks:[{t:30.2, e:33.0, text:"T1"}, {t:33.0, e:36.4, text:"T25", cls:"alt"}]},
  {label:"core 2", blocks:[{t:30.6, e:34.1, text:"T2"}, {t:34.4, e:38.0, text:"T26"}]},
], 30, 40);
```
`cls`: `alt`, `muted` (idle or switching), `bad` (blocked), `ok` (done). Stagger the switches across rows;
lockstep blocks read as fake.

### Failure and recovery
Break the thing the video is about, then show the concept fixing it: a host crashes (`mood(…,"panic")`,
a red `.pill` "CRASHED", `hit()`), a lane dims (`tl.to("#s07l",{opacity:.3},t)`), then the fix lands
with a green pill and the sidekick goes `happy`. This beat is what makes the concept stick.

### Outro
Stacked slams for the final line, mascot bouncing in, `follow @handle`. Hold ~2.5s. With a video
input, use *Face sign-off* instead.

### Logo end card
The brand's wordmark over its name or call to action, for the last ~2.5s. Pick the wordmark for the
canvas: `BRAND.scheme` is `dark` or `light`. SVG logos often carry only a `viewBox`, so always give the
`<img>` a height; the width follows the aspect ratio.
```html
<section class="shot" id="s30">
  <div class="cx" style="top:760px"><img id="s30logo" alt="" style="height:140px;width:auto"></div>
  <div class="cx kick" style="top:960px">acme.com</div>
</section>
```
```js
q("#s30logo").src = BRAND.logos[BRAND.scheme === "dark" ? "wordmark.onDark" : "wordmark.onLight"] || BRAND.logos.mark;
shot("s30", 27.5, D, "fade"); pop("#s30logo", 27.7); rise("#s30 .kick", 28.1);
```
Without a wordmark in the kit, slam the brand name instead. Never draw or approximate a logo the kit
doesn't contain.

### Corner mark
Automatic: when the kit has `logos.mark`, the corner signature shows it next to the handle instead of
`</>`. Nothing to author.

### Lower third with mark
The kit's mark beside a speaker's name, for a company's own people. Same as *Lower third*, with
`<img src="kit/logos/mark.svg" style="height:56px;width:auto">` before `.lower-name`, reading the path from
`BRAND.logos.mark`.

## Kit backgrounds

The kit's `background.style` lays a layer under every shot: `theme` (the theme's own canvas), `solid`,
`glow` (three soft brand-coloured glows that drift as a pure function of `t`), `gradient`, `grid`, or
`image`. Shots stay transparent over it; a shot with its own background (a full-bleed photo, a terminal
scene) covers it as before.

### Face hook *(video input)*
The speaker on camera saying the opening line. Always shot 01, ending on the hook's last word.
```html
<section class="shot face" id="s01"><img alt=""></section>
```
```js
faceCam("s01", 0, 2.4);
hit(1.62, .5);
```
One punch-in on the word that lands the claim. Keep captions on: most viewers watch muted. Enter the
next shot with `zoom`. The `faceCam()` in/out times must exactly match the `extract_face.sh` range
for this shot.

### Series badge
Series name and episode, shown and never spoken. Pops on the first animated shot and leaves before
its cut. Place it inside that shot's section, not the face shot.
```html
<div class="cx" style="top:170px;z-index:5"><span class="badge" id="s02badge">SERIES NAME #04</span></div>
```
```js
pop("#s02badge", 2.5); tl.to("#s02badge",{opacity:0,duration:.3,ease:E},4.3);
```

### Face sign-off *(video input)*
The speaker on camera for the closing line. Always the last shot, from its first word to the end of
the composition. `fade` entry, no hits, no mascot.
```html
<section class="shot face" id="s24"><img alt=""></section>
```
```js
faceCam("s24", 84.1, D, "fade");
```
Face shots are full-bleed; check stills for a crop that cuts off the head. The `faceCam()` in/out
times must exactly match the `extract_face.sh` range for this shot.

---

## Presenter blocks *(green-screen video, presenter mode)*

The keyed speaker (`key_greenscreen.py`) is a layer under every shot; each shot says where it stands.
Layouts are fractions of the frame, so the same shot list works on every canvas (landscape 1920x1080,
vertical 1080x1920, square 1080x1080, portrait 1080x1350). On wide canvases the splits put the speaker
left or right; on tall and square canvases both splits stack the speaker at the bottom with the panel
on top. Pip layouts float the speaker in a framed corner bubble, in the kit's colours, above the
full-screen shot — keep that corner clear of panels and headlines.

Layouts: `full`, `split-left` (`split` is an alias), `split-right`, `close`, and the corner bubbles
`pip-br`, `pip-bl`, `pip-tr`, `pip-tl`.

### Speaker position

A position from the presenter brief sets the layout `presenter("auto", …)` resolves to for every
shot, so the speaker stays put and close-ups and cutaways read as accents:

```js
presenterPosition("bottom-right");   // auto · bottom-right · bottom-left · left · right · full
presenter("auto", 10.3, 15.4);       // resolves to pip-br on every presenter shot
presenter("close", 21.0, 23.5);      // an explicit layout still wins — the accent
```

With `auto` (the default, no `presenterPosition` call) the engine cycles sides and corners — split-left,
pip-br, split-right, pip-bl, pip-tr, pip-tl — so two presenter shots never share a layout back to back.
Pacing rules for `auto`: never the same layout twice in a row (the cycle guarantees it), vary hold
lengths (1–4s as usual), and prefer a pip bubble over stepping the speaker out during most cutaways so
they stay on screen. Call `presenterPosition()` once, before the first `presenter()` call.

### Presenter full
The speaker centred, one short thing beside their head: a tag, a quote, a two-line headline at x ≥ 1300.
```html
<section class="shot" id="s04"><div class="h2" id="s04q" style="position:absolute;left:1300px;top:380px;width:560px">“Sounds like the answer.”</div></section>
```
```js
presenter("full", 10.3, 15.4); shot("s04", 10.3, 15.4, "cut"); rise("#s04q", 14.2);
```

### Presenter split with panel
Speaker on the left, a panel on the right building the point line by line. The workhorse of a long talk.
```html
<section class="shot" id="s06"><div class="panel" id="s06p" style="left:940px;top:110px;width:900px">
  <div class="kk">Their pitch</div>
  <div class="li" id="s06a"><span class="ic no">✕</span>Stay on Java 8</div>
  <div class="li" id="s06b"><span class="ic ok">✓</span>Upgrade with tooling</div></div></section>
```
```js
presenter("split", 22.3, 29.2); shot("s06", 22.3, 29.2);   // split = split-left
fromRight("#s06p", 22.35); cross("#s06a", 22.64); check("#s06b", 26.4);
```
Keep the panel above the captions (bottom ≤ 840 in landscape). `.ic.ok` / `.ic.no` / `.ic.mu` are tick,
cross and neutral; `check()` and `cross()` pop them with a ding or a buzz. On tall and square canvases
the speaker stacks at the bottom instead: the panel goes on top (top ≥ 150, bottom ≤ 26% of the height).

### Presenter split-right
The mirror of split: speaker on the right, panel on the left (landscape: `left:70px`, width ≤ 950 so its
right edge stays clear of the speaker at x ≥ 1050). Alternate it with split-left so long edits don't
lean to one side. On tall and square canvases it matches split-left (speaker stacked at the bottom).
```js
presenter("split-right", 30.0, 36.4); shot("s07", 30.0, 36.4);
fromRight("#s07p", 30.1);
```

### Presenter pip *(corner bubble)*
The speaker in a framed corner bubble — kit panel fill, `--frame` border, the theme's radius — floating
over a full-screen graphic: a diagram, a chart, a clip, a quote. Use it during cutaways so the speaker
never disappears. The bubble is above every shot but under the captions.
```js
presenter("pip-br", 40.3, 46.9); shot("s09", 40.3, 46.9, "zoom");   // bottom-right bubble over the diagram
presenter("pip-tl", 47.0, 52.0);                                     // top-left over the next beat
```
Keep the bubble's corner clear. The bubble spans roughly the corner's 45% width / 35% height:

| layout | keep clear (any canvas) | put panels and headlines |
|---|---|---|
| `pip-br` | x ≥ 55% of W, y ≥ 30% of H | left half, or the top band above 25% of H |
| `pip-bl` | x ≤ 45% of W, y ≥ 30% of H | right half, or the top band above 25% of H |
| `pip-tr` | x ≥ 55% of W, y ≤ 60% of H | left half, or the bottom band above the captions |
| `pip-tl` | x ≤ 45% of W, y ≤ 60% of H | right half, or the bottom band above the captions |

### Presenter close-up with slam
Punch in on the line that lands the point, with the slam beside the speaker.
```js
presenter("close", 53.6, 58.0); shot("s11", 53.6, 58.0, "cut"); slam("#s11a", 54.44, .8);
```

### Full-screen cutaway
Diagrams, stats and comparisons need the whole frame: step the speaker out, step them back in after —
or keep them on screen in a `pip-*` corner bubble instead (preferred for most cutaways).
```js
presenterOff(40.3); shot("s09", 40.3, 46.9, "zoom");
presenter("split", 46.9, 53.6);   // fades back in
```
Diagram pieces: `.box` nodes (`.on` lit, `.dead` greyed), `.ln` lines in an `svg.full` drawn with
`draw()` when the path has `pathLength="1"`, `.chip` labels, `.stampx` verdicts, `.vbar` bars grown
with `tl.fromTo(sel,{scaleY:0},{scaleY:1,…})`.

### Chapter card
A long talk's section headings, from the article or script. The speaker steps out for the card.
```js
chapter("s12", 58.0, 61.1, "01", "The patch was never<br>the bottleneck");
```
Hide captions under the card with `NOCAP` when the heading is the spoken line.

---

## Animating one element twice

Every helper is a `fromTo`, and GSAP renders a `fromTo`'s start values the moment the timeline is
built. That is what hides an entrance before its time, but a *second* tween on the same element
(in, out, back in) applies its start values at build time too, so the element shows up early as a
ghost. Give every later tween on an element `immediateRender:false`, and set its hidden state at
the shot start with `tl.set`:
```js
rise("#s08tag", 30.1);
tl.to("#s08tag", {opacity:0, duration:.2}, 31.0);
tl.set("#s08tag", {opacity:0}, 32.0);
tl.fromTo("#s08tag", {y:70, opacity:0}, {y:0, opacity:1, duration:.45, ease:EX, immediateRender:false}, 32.4);
```

## Captions

Captions are burned in automatically from `words.js`. Hide them whenever the spoken word *is* the
visual (a huge headline, a counter, a terminal) by adding its time range to `NOCAP` in the template:

```js
const NOCAP = [[1.2, 2.4], [4.1, 5.6]];
```

Never cover the element the viewer is meant to read; hide captions instead.

Caption styles, set with `CAP_STYLE` in the template:

| `CAP_STYLE` | Feel | Use for |
|---|---|---|
| `null` *(stock default)* | the theme's pick (`templates.json` → `motion.captions`) | letting the theme decide |
| `"phrase"` | whole phrase dimmed, one pulse, the spoken word marked | calm explainers, long sentences |
| `"pop"` | each word pops in on its own timestamp | fast Shorts, listicles, hype |
| `"rise"` | each word rises in on its own timestamp, no scale | news beats, precise explainers |
| `"fade"` | the whole phrase fades in once | reflective lines, documentary pacing |
| `"off"` | no burned-in captions; upload `captions.srt` instead | long form (`long-form.md` → *Captions*) |

The theme defaults: `pop` for `kinetic`/`brutalist`/`retro`, `rise` for `newsroom`/`blueprint`, `fade` for
`documentary`/`minimal`/`aurora`; anything without a pick falls back to `"phrase"`. All styles use the
theme's mark for the spoken word. Words flagged in `keywords.json` stay in the accent colour after they
are spoken, and in `pop` each flagged word lands with a single quiet `tick` cue — the only per-word
sound; ordinary words stay silent.

---

## Sound cues

Every helper pushes its own cue into `SFX`; add extras with `SFX.push({t, type, dur?, power?})`.

| type | Sound | Pair with |
|---|---|---|
| `hit` | sub boom + click | `hit()`, `slam()` |
| `whoosh` | filtered noise sweep | transitions (auto from `shot()` enter) |
| `stamp` | dull thud | stamps |
| `pop` | pitched blip | `pop()` |
| `ding` | bell | success ticks |
| `type` (dur) | key clicks | `typer()` |
| `tick` (dur) | fast ticks | `counter()` |
| `riser` (dur) | rising noise + tone | the 1–2s before a big reveal |
| `down` (dur) | falling tone | crashes, failures |
| `error` | square buzz | red error lines |

Each cue's sound, level or mute, and the music itself, can come from the kit's `audio` block
(`brand-kits.md` → *Sound*); the cue you push stays the same. The music bed ducks under the voice
automatically at mix time (`mix-audio.sh`). Use `--drop <t>`
in `synth_audio.py` to cut the music just before the final slam — silence before the punchline is
the strongest hit.

Let the music act out the script, not just sit under it. `synth_audio.py` takes three moments,
each an `A:B` range in seconds and repeatable, on the synth bed or a kit's own track:

| Flag | What the listener hears | Use it on |
|---|---|---|
| `--stop A:B` | the music winds down like a stopped tape at A, silence, back at B | "it hangs", "everything froze", a crash |
| `--muffle A:B` | the music behind a wall, sweeping open into B | something hidden or stale, opening on the reveal word |
| `--stutter A:B` | one beat from A repeats until B, like a stuck record | a loop, a retry storm, something stuck, released on the fix |

One or two per video: a moment lands because the rest of the bed is steady.

---

## Layout safe zones (vertical 1080x1920)

```
y=0      ┌───────────────┐
y=92     │   signature   │
y=150    ├───────────────┤
         │   shot area   │  keep diagrams and cards here
y=1450   ├───────────────┤
y=1500   │   captions    │  70px, up to 3 lines
y=1800   ├───────────────┤
y=1910   └── progress ───┘
```

Full-bleed photos and backgrounds may fill the whole frame; readable elements may not.

Landscape (1920x1080) safe zones are in `long-form.md`.

## Layout safe zones (square 1080x1080, portrait 1080x1350)

Square and portrait follow the same proportions as vertical: signature at the top (y ≈ 92, as on every
canvas), shot area below it, captions at ~78% of the height (square: top 850; portrait: top 1050),
progress bar at the bottom.

```
square 1080x1080          portrait 1080x1350
y=0   ┌───────────┐       y=0    ┌───────────┐
y=92  │ signature │       y=92   │ signature │
y=150 ├───────────┤       y=150  ├───────────┤
      │ shot area │              │ shot area │
y=800 ├───────────┤       y=1000 ├───────────┤
y=850 │ captions  │       y=1050 │ captions  │
y=1070├───────────┤       y=1330 ├───────────┤
      └─ progress ┘              └─ progress ┘
```

Presenter layouts scale themselves to the canvas; panels and headlines follow the same rules as
vertical — stacked above the speaker in splits, clear of the bubble's corner in pips.
