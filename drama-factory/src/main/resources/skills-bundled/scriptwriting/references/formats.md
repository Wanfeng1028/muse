# Script formats

Templates for beat sheets, A/V scripts, shot tables and paper edits.

Contents
1. Script formats

---

## Script formats

| Format | Use when |
|---|---|
| Beat sheet | pitching and structuring, before any line is written |
| A/V two-column | narrated films, ads, explainers, demos: the default for production and review |
| Shot-by-shot table | music-led, no-VO or montage films; social cuts |
| Paper edit | documentary, interview, testimonial: bites with timecodes |
| Screenplay (Fountain) | scripted dialogue scenes with actors |

**A/V two-column with a text track**

```markdown
# Tally · "Day 40" · 30 s · 9:16 + 16:9 · es-CO, tú
Message: Tally chases unpaid invoices so you don't have to.
Viewer: a freelance designer, 40 days into an unpaid invoice, embarrassed to ask again.
Structure: ABT (cold audience); hook formula: stated cost. Feeling: valley (awkward) → relief.

| # | Time | Picture | On-screen text | VO / sound |
|---|------|---------|----------------|------------|
| 1 | 0.0-3.0 | Calendar, day 40 circled; a hand deletes a reminder | DÍA 40 | VO: "Cuarenta días. Y la factura, sin pagar." SFX: delete ×3 |
| 2 | 3.0-8.0 | She types "solo quería saber si…", winces, closes the laptop | (captions) | VO: "Escribes el recordatorio, lo borras, lo vuelves a escribir." |
| 3 | 8.0-12.0 | Phone face down. [beat] | (none) | VO: "Cobrar no debería darte vergüenza." Music drops out |
| 4 | 12.0-22.0 | Reminder schedule fills; polite email preview; status flips to PAGADA | Recordatorios automáticos | VO: "Tally envía los recordatorios por ti, con buen tono, hasta que te paguen." |
| 5 | 22.0-26.0 | The payment notification; a small smile | PAGADA · día 42 | SFX: soft chime |
| 6 | 26.0-30.0 | End card | Prueba Tally gratis | VO: "Tally. Tú diseñas, Tally cobra." |
Words: 46 VO (30 s carries 55 to 75; this leaves room for the held beat).
```

**Beat sheet**

```markdown
| # | Beat | Time | Job (traces to message) | Emotion (+/−) | Persuasion move | Picture idea | Line or card |
|---|------|------|-------------------------|---------------|-----------------|--------------|--------------|
| 1 | Hook | 0-3 | name the cost | − awkward | stated cost | day 40 circled | "Cuarenta días." |
| 3 | Turn | 8-12 | reframe | + permission | reframe | held still | "Cobrar no debería darte vergüenza." |
Planted/paid: the circled day (beat 1) returns as "día 42" (beat 5).
```

**Two-layer lines** for anything a voice might mispronounce: each line has a `display` form (captions, cards) and a
`spoken` form (TTS), e.g. `{"display": "repitis.com", "spoken": "repitis punto com"}`. Captions always show display.

**Shot-by-shot**: `Shot | Bars / time | Frame | Action (one verb) | Text | Sound cue | Why`, one row per cut, times snapped
to the track. **Paper edit**: `Order | Source · TC in–out | Bite (verbatim) | Story role | Cover (b-roll)`.
