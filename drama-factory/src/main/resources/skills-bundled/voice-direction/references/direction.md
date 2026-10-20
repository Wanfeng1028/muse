# Directing the voice

ElevenLabs models, settings, tags, context framing, the feeling matrix and accents. Checked against the docs on 2026-10-06; re-check the model page when a model changes.

Contents
1. Models
2. Settings
3. Tags, punctuation, pronunciation
4. Unspoken context and framing
5. Feeling → direction matrix
6. Language, accent and register

---

## Models

| Model | Use for | Delivery control |
|---|---|---|
| `eleven_v4` | Default for published VO: films, ads, characters | Audio tags, punctuation, IPA in `/slashes/`; stability + similarity only; 10,000 chars per request |
| `eleven_v4_turbo` | Drafts, agents, live apps | Same as v4 |
| `eleven_v3` | A voice you liked on v3 | Tags; style supported; no request stitching |
| `eleven_multilingual_v2` | Very long stable reads; Castilian or European Portuguese voices (it lists Spain, Mexico, Brazil, Portugal) | Style, speed 0.7 to 1.2; **tags are spoken aloud**; no `language_code` |
| `eleven_flash_v2_5` | Bulk, cheap, realtime | No tags; weak number normalisation |

- v4 reproduces the source voice faithfully, **flaws included** (plosives, sibilance, volume jumps, room noise). Static
  screening matters more on v4 than before.
- Accent on v4: if the voice's language matches the output language, the voice keeps its accent; if not, v4 aims for generic
  fluent speech. Its list names only "Spanish (LatAm)" and "Portuguese (Brazil)", so a specific regional accent needs a voice
  native to it (and possibly an A/B with multilingual v2 for Castilian or European Portuguese).
- Voice Design voices may be less performative on v4; prefer library voices or clones for finals.

## Settings

| Setting | Effect | Direction |
|---|---|---|
| stability (0 to 1, default 0.5) | variation within and between takes | 0.3 to 0.45 expressive (more drift and hallucinated words); 0.5 tagged narration; 0.75 to 0.85 calm, steady, follows tags less. **0.8 with similarity 0.75 fixed breathy single syllables.** |
| similarity (0 to 1, default 0.75) | closeness to the reference voice | 0.75 default; lower to 0.5 to 0.6 if you hear the voice's recording noise (higher copies the flaws) |
| style (v2/v3 only) | exaggerates the voice's style | 0 to 0.3; ignored on v4 |
| speed (v2/v3/Flash only) | tempo | 0.9 to 1.1; ignored on v4 |
| seed | best-effort determinism | always send and log it; good for re-rolling a near miss soon after, never an archive |

Starting points (stability / similarity): narration 0.7/0.5, conversational 0.4/0.75, news 0.8/0.6, characters 0.3/0.8
(official v4 presets); measured: isolated words and syllables 0.8/0.75, tagged film narration 0.5/0.75.

## Tags, punctuation, pronunciation

**Tags (v4/v3)**
- Free text in square brackets: `[warmly]`, `[softly]`, `[tired, trying to sound cheerful]`, `[starting calm, then losing
  patience]`. Combine in one bracket with commas. English tags work inside Spanish lines and aren't spoken.
- Place them right before the words they affect; emotion carries forward until the next tag, so tag only the shifts (in the
  film, 7 of 14 lines had a tag). One tag per clause; contrasting tags on the same words blur the read; more than ~3 per line
  is too many.
- v4 also knows sound effects, so describe the **voice**, not a sound: `[low, gravelly voice]`, not `[gravelly]`.
- Tags are spoken aloud on v2 and Flash, or with the wrong brackets. Narrative cues ("she said, trembling") are always spoken.
- Long-form style: one short direction per paragraph (`[Warm, intimate narration]`, `[Building tension, measured pace]`).

**Punctuation**
- A period ends a breath group; a comma lifts; an ellipsis adds a pause and weight; a dash makes a short break; CAPITALS add
  emphasis (sparingly, they can shout). Use `¿…?` in Spanish so the rise starts on time.
- No SSML breaks on v4/v3. For an exact pause, split the line and insert silence in the edit.
- To change delivery, change the sentence before changing a setting: short sentences calm and clarify, fragments punch, run-ons
  rush and flatten; put the stressed word at the end of the sentence.
- Isolated words and syllables: the plain form `texto.` beat bare text, `¡texto!`, `Texto.` and `«texto».` in blind tests.

**Pronunciation and normalisation**
- v4: IPA between slashes inside the text (`/ˌbaɪoʊˈkemɪstri/`); results vary by voice, so take more than once.
- Pronunciation dictionaries (max 3 per request): phoneme rules on v4, v3, flash_v2; alias rules elsewhere.
- Respelling in the spoken layer is the portable fix; captions keep the real spelling (`vo_build.py` `spoken_fixes`,
  `caption_joins`).
- Guillemets fix two failures: texts that come back as 0.1 to 0.2 s blips (read as stage directions: «ri»., «voz».,
  «música».) and abbreviation expansion (`col.` read as "columna"). One word only worked capitalised and quoted («Pausa».).
- Never trust the normaliser in a film: write amounts, dates, percentages, URLs, units and acronyms as they are said.

## Unspoken context and framing

- Frame speaker, listener and situation **in the target language** in `previous_text`, and a natural continuation in
  `next_text`. Example used for children's cards: "A preschool teacher, calm and warm, reads a reading card aloud to a child.
  The card says:" before the item, "Very good, now the next card." after. This fixed breathy or suggestive syllables and the
  English accent on short words.
- Risk: syllables leak from the context into the take ("pera" came out as "espera", "coche" as "mi coche"). End the frame with
  a colon or period, and catch leaks with speech-to-text.
- For narration, neighbouring lines are usually enough context; add a frame for short or isolated lines, or when the read must
  be a specific relationship ("a mother telling a friend…").
- Other models: an audio profile (who), a scene (where, what is physically happening), performance notes (style, pace, accent).
  Concrete sensory scenes beat role labels. Don't quote the transcript inside the notes (some engines speak them).
- Don't direct flatness ("quiet", "no rush", "low energy"): models deliver monotone. Say "warm and sincere, measured but present".

## Feeling → direction matrix

wpm ranges are English conventions; budget roughly 10 to 20% fewer words in Spanish for the same time (estimate; measure).
Settings are v4 stability / similarity.

| Feeling | Cast | wpm | Settings | Tags and writing | Avoid |
|---|---|---|---|---|---|
| Warm, comforting | mid-low, rounded, smiling; 30 to 50 | 130 to 150 | 0.55–0.7 / 0.75 | `[warmly]`, `[gently]`; direct address; short sentences that resolve; the pain line `[softly]` | airy or breathy voices, exclamations |
| Trustworthy, authoritative | lower, steady, clear consonants; 35 to 60 | 140 to 155 | 0.75–0.85 / 0.75–0.9 | few tags; declaratives ending in periods; facts in short clauses | upspeak, question tags, CAPS, laughs |
| Excited, hype | bright, forward, wide range; 20s–30s | 165 to 185 | 0.3–0.45 / 0.75 | `[excited]`, `[energetic, speeding up]`; punchy fragments; one exclamation at the peak | every line at max; low stability on long lines |
| Playful | light, agile, smiling | 150 to 170 | 0.4–0.55 / 0.75 | `[playful]`; a `[soft laugh]` at most once; contrast and surprise in the copy | giggles on a serious voice; sarcasm with kids or parents |
| Calm, meditative | low, soft, unhurried; narrow range | 100 to 125 | 0.75–0.9 / 0.75 | `[calm, unhurried]`; ellipses; one idea per sentence; real pauses added in the edit | `[whispers]`; "quiet" in directions |
| Urgent | tight, forward, clear diction | 170 to 190 | 0.45–0.6 / 0.75 | `[restrained urgency]`; imperatives; deadline last | panic or shouting in brand work |
| Nostalgic | warm, slightly husky, older | 120 to 140 | 0.55–0.7 / 0.75 | `[wistful]`, `[softly, remembering]`; past tense; sensory details; ellipsis before the turn | crying or sad tags |
| Premium, luxury | low, smooth, close, restrained | 110 to 135 | 0.75–0.85 / 0.8–0.9 | almost no tags; very short lines; silence between them | hype, laughs, crowded copy |
| Intimate, confessional | soft, close; adult audiences only | 120 to 140 | 0.5–0.65 / 0.75 | `[sincere, a little vulnerable]`; first person; hesitation by ellipsis | whispers for kids or general audiences |
| Documentary, neutral | mid, even, clear | 140 to 155 | 0.7–0.8 / 0.75 (or v2 for long reads) | one `[Quiet, measured narration]` per paragraph; complete sentences | emotional tags, rhetorical questions |
| Friendly, conversational | natural, relaxed | 150 to 165 | 0.45–0.55 / 0.75 | contractions and local colloquialisms; direct address; questions answered at once | read-aloud cadence, list intonation |
| Inspiring | warm, resonant | 135 to 160, building | 0.5–0.6 / 0.75 | `[building energy]`; quiet start, crescendo across lines, payoff line alone | starting at the peak; generic uplift |

## Language, accent and register

- Cast by language **and** accent. ElevenLabs library filter:
  `GET /v1/shared-voices?language=es&accent=colombian&page_size=100&page=0` (pages start at 0; also `gender`, `age`,
  `use_cases`, `descriptives`, `category`, `sort=cloned_by_count`). Prefer descriptions with warm, natural, friendly,
  conversational or educational, the `high_quality` category, or high `cloned_by_count`. Skip ads, sports, commanding, epic.
- **English accent on short words**: bare short texts that are also English words (`sol`, `bus`, `pin`) were read with an
  American accent. Fixes in order: `language_code`; a target-language frame; a period (`sol.`); quoting (`«sol».`).
  Exclamations fixed the accent but produced moans. Keep each request in one language.
- Brand names that switch language: decide how the brand is said in that market and write it so in the spoken layer, with a
  target-language frame; an English brand can tip a short line into an English accent. Check by speech-to-text.
- Regional words belong in the script, not just the voice (Colombian "el colegio", "la profe", "listo"; avoid Spain's
  "móvil" or Mexico's "ahorita"). Rioplatense needs voseo in the script and a native voice. British vs American: accent filter,
  vocabulary and date formats.
- Register (tú, usted, vos) is a script decision tied to the audience; voice age and warmth must match it.
- Voice Design prompt: `Native <language>, <regional variant and what to avoid>. <Gender>, <age range>. <Quality>. Persona:
  <2 to 5 words>. Emotion: <2 to 3 adjectives>. <1 to 2 sentences on timbre, pacing, delivery>.` Say "intonation" when you
  mean it (the word "accent" triggers dialect shifts); avoid effect words (reverb, phone) and vague words (foreign, exotic).
  Preview text 100 to 1,000 characters in the target language and mood; you get 3 previews per call.
- Cloning: Instant clones from ~10 s, 1 to 2 minutes recommended, clean single-style audio (v4 copies flaws). Only voices you
  have rights to.
