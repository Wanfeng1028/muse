# Whole-film rules — decided before any device

Source: the author's lab notes on axes and pairing, and its production order (the lab is not
shipped; its rules are written back into this file, which is the operating copy). Tiers: see
`evidence-and-instruments.md` §Tiers. Origin: the author's reviews of lab rounds r10-r13
(2026-09-29/30), stated by the author as the big problems of ALL ad/product/promo films.

## §0 Confirm first (author r14, 2026-09-30)

Before Layer 1, settle these with the user (unattended: `build/questions.md` + the
request's most literal reading, stated in `build/plan.md`):

| # | Item | Why |
|---|---|---|
| 1 | Purpose / film type: intro ad, hype ad, product tour, explainer, profile | picks the skeleton; r14 made two detailed tours when an ad was wanted; r15 made an intro ad when a hype ad was wanted (`film-types.md` §1) |
| 2 | Where it is shown (feed, site hero, talk, YouTube) | length, ratio, sound-off reading, cover |
| 3 | What the viewer does after (download, remember the name, read docs) | the end card and its hold |
| 4 | Audience | §1 |
| 5 | The ONE thing to remember | an ad hits one point; a tour walks each feature |
| 6 | Energy (calm / lively / hype) and ground. ASK it; never infer it from the product alone | §1; r14-r15 inferred "calm" for a privacy tool and the author wanted hype; r16: naming the energy moved tone and pace (moving share 0.41 -> 0.70) |
| 7 | Materials and limits (real screens, logo, forbidden claims) | `build-and-export.md` §4 |
| 8 | Content voice: marketing / social (slogans, a closing hook) or a light technical explainer | the same content reads either way; it is a choice made per film, not a film type (author r18, 2026-10-01) |
| 9 | Presentation form: paged (fixed page title per section, items appear and hold, section change = page change) or continuous-stage (one continuous stage, things enter, move, leave; the eye is led by camera, dimming or a moving character) | author r18: preferred the continuous-stage arm for its presentation, not its content (n=1). A film may also MIX the two; the author's lab has named mixes (stage-led opening then pages on the dimmed same stage, pages placed in one stage world, stage bookends around paged middle, anthology, beat-cut montage) with fail conditions - case readings only, no effect evidence yet (author 2026-10-02) |

"介紹片" alone does not settle ad vs tour, and "廣告" alone does not settle intro vs hype: ask.

## §1 Layer 1 — the whole film (fix these four first)

| Decision | Rule | Tier |
|---|---|---|
| Audience | Name the ONE group the film speaks to. Every section, including the end, speaks to it. Content on the site aimed at someone else (listing fees for shop owners in a film for readers) is a major failure, not extra value. | verified (r12: owner-facing sections 0/3 with the rule vs 3/3 without; r13 same) |
| Only what the viewer needs | How the film or data was made (sort order, data source) is noise in an ad. Every number needs a meaning for the viewer. A highlighted item needs copy saying why it is highlighted. | author (r12) |
| Tone | The energy the user named in §0 item 6 wins. Only when none is named, judge the character from product + audience (a bookshop directory = quiet, relaxed, unhurried). Pace, motion and sound follow it. | author (r10: all 9 arms too lively; r15: a privacy tool read as calm, author wanted hype); r12 arms self-judged tone correctly |
| Ground colour | One background colour for the whole film (a hype ad loosens this, §6). Accent and data colours may vary; the ground may not. A transition (a full-frame colour wipe) never counts as a ground change; only a shot's resident ground does. | verified (r12: 0-2 ground switches with the rule vs 8-11 without); transition clause author 2026-09-30 |

The audience, tone and ground rules were given together in r12, so which rule caused which
difference is not separated; "verified" means the bundle moved the measure, not each rule
alone.

## §2 Devices carry a tone

Every device has the tone it fits. Choose devices against Layer 1's tone. **When a device
clashes with the tone, drop the device, never the tone** (author 2026-09-30). The device→tone
list is proposed by the model during later work; a human is not its first reviewer.

| Device | Fits | Tier |
|---|---|---|
| Heavy-hit punch: one full-strength hit per second, a full-frame statement on each (recipe: `film-types.md` §1b) | energetic, upbeat, hype ad; never in a quiet film | author (r10 A1 promise section, chosen again as a hype reference 2026-09-30) |
| Dark translucent dim overlay to single out a selected item | a tension device; clashes with a light, calm film | author |
| Blurred / dimmed photo as background | "not busy, more alive"; tone fit not yet judged | author |
| Book-spine colour-bar wipe | neutral-to-lively; slow it 1.25-1.5x for a calm film | model proposal (r13) |
| Red blocks stacking bottom-up (transition) | neutral; slow it for a calm film | model proposal (r13) |
| Books falling like dominoes | lively, playful; fit in a calm film unjudged | model proposal (r13) |
| Giant outline "ghost" word drifting behind a statement | none: reads hollow, ugly | author (r17) |
| 3D tilt push-in of a product screen | hype ad; text stays readable when cropped | author (r17: readable) |
| Guide character (small mascot reacting to the narration with ! ? ✓ ♥ …; T11) | a logo / brand watermark, 1/8-1/6 of frame height, never covering text; appears only where it has work (opening, chapter change, a key or turning line), otherwise leaves or shrinks to a corner mark; which moments it leaves is not yet ruled | author (r18, 2026-10-01; n=1) |
| Pointer dot moving to what is being said | none when on-screen motion already cues the point: redundant, noisy | author (r18) |
| Split-flap numbers, tilted card wall, rotating list, whoosh on every transition | not yet judged | — |

## §2a Motion intent — nothing moves for the sake of moving (adopted 2026-10-01)

Tier: claim (a motion designer's public critique of AI-made motion graphics, Threads
2026-09-30, adopted by the author 2026-10-01; not measured or A/B-tested here).

- Every moving element in the storyboard has one line saying what its motion says: it
  points at data, an order, a cause, or the emphasis. No line → the element holds still or
  is cut. Example with intent: T07's particles are one point per data record; the same
  burst as decoration has none.
- Stock devices need that line before they are used: particle burst into a "universe",
  tunnel / vortex transition, floating tilted card pile, glitch / RGB split, big text
  standing in for design, randomly ticking numbers or fake HUD metadata. No line tying it
  to the content → not used. (The §2 tone check still applies on top.)
- Stacked effects: each extra layer on one element (glow, grain, blur, shake, chromatic
  split) carries its own intent line. No numeric cap yet — set one only after measuring.

## §3 Pairing principles (author, after r12/r13)

- Transitions: a fade disturbs least; many-colour transitions disturb and read as ground
  changes; a transition may carry ONE image (gathering the shops into the brand name).
- Items at once: at a fast pace, many items at once is reading load. Either one item at a
  time, or hold longer.
- Section seams: the incoming transition never covers the outgoing section's last beat.
- Ending: replay nothing without a reason; resolve the logo fully; hold it 2.5-3.5 s
  (author r14: 5.8 s and 7.4 s too long; provisional until the ad round is watched). The
  last line pushes the viewer to act (r18 A1's "你來做吧" beat B1's ending, author r18).
- More content is not better: pick devices by film type and tone; using every borrowed
  device made r14 L's big-text verb-card transitions ugly (author r14).
  The same holds for devices the model found itself by web research: r21 D1 executed every
  reference it named, and its full-frame black/white barcode transition was unrelated to
  the song and abrupt (author r21). A researched device gets the same intent line as a
  stock device.
- Landing on the beat is not a reason to use a device (author r21): the beat map is a
  calculation aid. Decide the device from the content first, then whether to lock it. A
  target box scaling + background flash on every beat was on time and wholly unsuitable.
- Local and global agree: a transition that changes only the demo area while the
  headline card around it stays put reads as two layers doing separate things; move both,
  or use a whole-frame transition (author r14).
- Crop product screens so their text reads at film size (r14 S's type and scale preferred
  over L's, author).
- Demos never drag: real waits (probing, downloading) are sped up with the speed map in
  `build-and-export.md` §1 (author r14).
- Readability beats beat-locking: when a lock would pull a line of text off screen too
  early, give up that lock (T01 "做片時" (b), author ruling; no seconds threshold yet).
- Dwell per page / level must let the viewer finish reading: r19 A1 held each level
  ~2.15 s and the author could not finish; at least +1 s per page (~3.2 s and up; author
  r19, n=1, provisional). More text or lower contrast needs more time — fix the text first.
- In a one-take scale dive, a hard camera surge into each level (rotation + rush, r19 A1)
  was preferred over C28's same-angle soft cross-fade (author r19: strong impact; tone fit open).

## §4 Materials and text

| Decision | Rule | Tier |
|---|---|---|
| Site has pictures | Use them: related, colour-unified, blurred or dimmed as background; never pasted raw | verified (r10: with/without images); treatment author |
| Short-section headline | The headline is the biggest text in its section; the shorter the section, the more it must read at first glance. Set it as ONE block: big title + one small caption line, nothing competing beside it (C28 has it; r19 A1's 40 px title crowded by status line, labels and legend read as having none, author r19) | author (r11, r19) |
| Leader-line labels | Large and high-contrast enough to be recognised at first glance; r19 A1's 11-14 px monospace on a dim ground slowed recognition | author (r19) |
| Numbers on screen | Traceable to the product; optional features marked; illustrations marked; scope words as the docs say | measured (T05, `scripts/fidelity.py`) |
| Material consistency | No material type the film has not used before appears mid-film; no text colour the film has not used for text (a data colour is not a text colour) | author (r12, r13) |
| Emphasis contrast | The emphasised item needs enough contrast. How to get it on a locked LIGHT ground is still open | author (r13); open |
| Declaration line | A promise / declaration subtitle is set large: it is a declaration, not an explanation | author (r12) |
| Saturation | Fits the tone; oversaturation glares | author (r12) |

## §5 Multi-arm contests (when several versions compete)

Keep ONE arm that deliberately ignores the tone rule and plays free (author 2026-09-29).
Ask the user for per-section picks, not one overall winner.

## §6 What loosens in a hype ad (author r15/r16 reviews; r17 watched and accepted, 2026-09-30)

The §3 principles came from calm films (a bookshop directory, a privacy tool). In a hype ad
(`film-types.md` §1b) a model that follows them literally rebuilds an intro ad (r16: one
dark ground, a 12 s step-by-step GUI walk, fades, cuts on bar lines only). In a hype ad:

| Calm-film rule | In a hype ad |
|---|---|
| One ground for the whole film | a hit run (<= 4 s) may alternate or invert the ground on each hit, rotating the product's theme colours (r10 A1; C06 invert; author r17: ok); outside hit runs the ground holds |
| A fade disturbs least | hard cut, white flash, invert, slam, wipe; each kind at most once or twice (C06 uses seven kinds, each once) |
| Lock only strong beats | every cut on a beat, section lengths 2 / 4 / 8 beats (C06, +-12 ms) |
| Features as action -> result | the product is MATERIAL: a screen is shown as one striking frame per hit (3D-tilted, pushed in, cropped to one number), never walked step by step; a real wait never appears |
| More content is not better | still holds: ONE word or number per hit |
| Local and global agree | still holds: a hit moves the whole frame |

Audience, only-what-the-viewer-needs, real numbers (T05) and the end-card hold are NOT
loosened.

