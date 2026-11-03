# Quality, verification and casting

Measured on 1,372 single-word takes and a 73 s narrated film. Implemented in `scripts/voice_qa.py`.

Contents
1. Static, noise and quality gates
2. Verification without ears
3. Casting
4. Children and sensitive audiences

---

## Static, noise and quality gates

Measured on 1,372 takes; implemented in `scripts/voice_qa.py`.

- **Noise floor** = level of the quietest 10% of frames relative to the loudest frame (Hann frames of 1024 samples, hop 512,
  RMS dB). Voices with audible static measured −50 to −60 dB; clean voices −66 to −76 dB.
- **Gate every take at ≤ −62 dB.** Screen voices at ≤ −65 dB on two probes (a short syllable and a long word, or a short and a
  long script line); about half of 132 library voices passed. Check every take, not just the voice: one clean voice produced a
  single take at −42 dB.
- The method needs silence: on a sentence with less than ~10% silence the floor isn't measurable, and the script says so
  instead of passing it. Narration takes usually have 20 to 50% silence, so it works on them too.
- **Sentences fail without hiss**: soft-tagged narration (`[softly]`) measured −47 to −52 dB because its quiet frames are soft
  speech or breath, not static; `voice_qa.py` adds a hint when the quiet frames' spectral centre sits under 1.5 kHz. Three
  narration takes at −60 to −61.6 dB shipped in a film without audible noise, so −62 is strict for sentences: listen
  before re-recording a near miss.
- Decode takes the way the gate was calibrated (ffmpeg reading the file from stdin keeps the MP3 encoder delay); decoding by
  path reads up to ~3 dB higher on clips under 1 s.
- Raw ElevenLabs takes peak up to −0.3 dBTP; that's fine, `vo_build.py` limits them. The raw-take true-peak gate defaults to
  0 dBTP so `--until-pass` doesn't buy needless retakes.
- **Quiet at source** (−24 to −32 LUFS against a typical −18, or ≥ 4 LU below the voice's median) means a breathy read.
  Re-record; a steeper high-pass changed nothing.
- **Length**: cut-off takes are 0.1 to 0.2 s; good single items are ≥ 0.5 s. For lines in Spanish, Portuguese or English,
  estimate duration from **syllables** (~4.5 per second plus ~0.25 s per internal comma or stop), not words: on real film
  takes syllable rate varied 14% against 22% for words per minute, and a 150 wpm estimate failed 14 good takes. More than
  ~30% off the estimate is suspect.
- Processing for clips: high-pass 80 Hz; trim leading silence at −50 dBFS (keep 40 ms) and trailing at −40 dBFS (keep 80 ms)
  with short fades; loudness to target with gain plus a limiter (v4's sharp consonant peaks need up to 8 dB of reduction and a
  short release); R128 needs ≥ 400 ms, so measure short clips looped. `vo_build.py` does this per line.

## Verification without ears

- **Speech-to-text diff** against the spoken layer with tags stripped, with per-language homophone allowances (Spanish b/v,
  s/z/c, ll/y, silent h, final y/i) and a list of known harmless misses. Scribe (`scribe_v2`) beat local Whisper large-v3
  on accuracy and speed. Don't pass the expected text as keyterms (it biases the check).
- STT is unreliable on single short words and leans English ("Ten", then "Den" for the same take; "Ping" for pin). **Trust
  only a miss that repeats** in 2 of 3 transcriptions; skip the verdict for 1 to 2 syllable texts.
- Look for: missing words, extra words at the start or end (context leaks), tag words heard (a spoken tag), unrequested audio
  events (laughs, sighs, breaths), long internal silences (dropped words), a speech span ending well before the file ends.
- **Audio-model judges hit a ceiling**: all 30 judged film takes scored 8 to 10 and all were called "Colombian". Absolute
  scores and accent fields don't discriminate. Use them for specific defects, then pairwise: "which is warmer / more natural /
  more credibly <accent>", three runs with the order swapped, majority only. Add a wrong-accent decoy to prove the judge can
  hear accents at all. Then the user's ears on the hero lines.
- Retake ladder for isolated items: `texto.` × 2, then `«texto».` × 2, then `«Texto».` × 2; stop at the first take passing every
  check (52 of 1,372 takes needed a quoted form).

## Casting

1. Filter the library by language, accent and use case.
2. Noise-screen two probes per voice (`voice_qa.py --screen-voices`), keep those under −65 dB.
3. Blind test 3 to 4 voices per gender behind letters with a fixed item mix: for narration, 3 to 4 representative script lines
   (the emotional peak, the CTA, a line with a brand name or number, a short line); for item libraries, syllables, short words
   and long words. The listener ranks each row and each voice, and can tick "static". Include a known reference voice to
   calibrate (in one round the listener picked the reference again without knowing it). `voice_qa.py` builds the blind page.
4. The in-product voice (the app's own audio) must differ from the narrator.
5. Lock the choice in a project voice file (`assets/voice.example.json`: voice id, model, settings, language, context template,
   tag vocabulary) and keep 2 to 3 approved reference takes to compare future takes against pairwise.

## Children and sensitive audiences

- Teaching voices: adult, warm, clear, unhurried (110 to 130 wpm); the "teacher reading to a child" frame; stability 0.8; the
  plain `texto.` form.
- Breathy or suggestive reads of short syllables happened without context and with exclamations. Prevent with a framing
  context, high stability, a period instead of `!`, and never `[whispers]`, `[softly]` on bare syllables or "breathy", "airy",
  "intimate" in tags or prompts. Detect as quiet-at-source takes and re-record.
- Keep voice sets gender-balanced; use the same voice for replays within a session.
- Design child characters rather than cloning a real child; check the provider's policy.
- Parent-facing copy: comfort first; the pain line soft, the reframe warm.
