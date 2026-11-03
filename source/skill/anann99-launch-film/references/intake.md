# Intake questionnaire: what to ask the user before making the film

Ask everything in **one message**. Use `AskUserQuestion` for the four discrete choices (length, aspect, audio, tone) and plain text for the rest. Tell the user: *"Anything you don't know or don't care about, I'll research from your website or choose a sensible default and tell you what I picked."*

Save the answers verbatim to `INTAKE.md` at the project root. Every brief, storyboard and agent prompt is built from it.

---

## A. Required. Don't start the storyboard without these.

| # | Ask | Why it matters | If they can't answer |
|---|---|---|---|
| 1 | **Company and product name** (and how they write it: "Acme" vs "ACME", product vs company brand) | End card, wordmark, every caption | Take it from the website `<title>` and logo |
| 2 | **Website URL** | Source of copy, palette, fonts, logo, imagery, proof | Required, no default |
| 3 | **What the product does, in one sentence, and who the film is for** (buyer persona, e.g. "Heads of Growth at consumer apps"; or investors, developers, existing users) | Sets vocabulary, depth and what "proof" means to the viewer | Infer from the homepage hero and pricing/enterprise pages, then confirm |
| 4 | **Where product footage can come from:** a public demo URL, a sandbox/demo tenant login, screenshots, screen recordings, or "website only". **And what must never appear on screen** (customer data, internal tools, unreleased features, pricing) | Real UI is what makes a launch film credible. Privacy rules are absolute | Website-only fallback: rebuild UI moments as motion graphics from site visuals, and say so |
| 5 | **The ONE outcome the film follows.** The metric, result or use case the product delivers, ideally one metric on one surface (e.g. "lift impression-to-stream +2pp on the home shelf", "cut onboarding time from days to minutes") | The product section follows this single thread from goal to result. Unrelated examples stitched together read as fake | Propose 2–3 options from the site's hero, pillars and case studies; let them pick |
| 6 | **Approved proof:** customer names/logos and numbers you may publish (with links to case studies), awards, funding or team pedigree. **Also: numbers you must NOT show** | Proof is the payoff. Unapproved logos and invented numbers are the biggest legal and credibility risk | Use only what's publicly published on their site, cite it, and confirm. If there's none, use a capability-proof beat instead (speed, scale, benchmark) |
| 7 | **Call to action:** the URL to show and the action ("Book a demo", "Start free", "Join the waitlist"), plus any end-card line they want | The end card sells. The URL must be exact | Use the site's primary CTA button text and root domain |

## B. Optional. Defaults apply if blank.

| # | Ask | Default |
|---|---|---|
| 8 | **Positioning guardrails:** phrases to use, phrases to avoid, competitors to differentiate from, claims legal has flagged | Derive from the site hero and pillars. Avoid superlatives you can't prove ("best", "only") |
| 9 | **Brand assets:** logo (SVG preferred; mark and wordmark), colour palette, fonts (names or files), brand guidelines PDF, photography/illustration | Extract from the site: CSS custom properties, `@font-face`, inline SVG logo, hero imagery |
| 10 | **Style references and anti-references:** links to 1–3 videos they love (theirs or others', e.g. Linear, Vercel, Stripe, Apple), and anything they hate | Premium dark SaaS launch style in the brand palette: kinetic type with pill highlights, floating product windows, dashed connectors |
| 11 | **Length** | 60 s (alternatives: 30 s cutdown, 90 s) |
| 12 | **Aspect / resolution** | 16:9 at 1920×1080, plus a 4K master. Offer 9:16 / 1:1 cutdowns as a follow-up |
| 13 | **Audio:** music-only or voiceover; original composed score or a licensed track they provide; mood and BPM preferences | Music-only, original synthesized score at 120 BPM, composed to the cut |
| 14 | **Tone** | Premium, confident, technical, warm at the close |
| 15 | **Where it will be shown:** site hero (autoplay, muted?), LinkedIn/X, event stage, sales deck | Site hero and social. Design so it reads muted (all story in on-screen text) |
| 16 | **Deadline, approvers, legal footer** (trademarks, "results may vary", etc.), **languages/subtitles** | No legal footer, English only |
| 17 | **Existing videos** of theirs (to match or improve on) | None |

---

## Copy-paste version for the user

```text
LAUNCH FILM INTAKE: answer what you can; write "you decide" for anything else.

REQUIRED
1. Company / product name (exact spelling + casing):
2. Website URL:
3. One-line description of the product + who this film is for:
4. Product footage source (public demo URL / sandbox login / screenshots / recordings / website only):
   Never show on screen:
5. The ONE outcome the film should follow (metric + where it moves, or the hero use case):
6. Proof we may publish (customer names, numbers, case-study links), and numbers we must NOT show:
7. Call to action (URL + button text, e.g. "acme.com · Book a demo"):

OPTIONAL
8.  Phrases to use / avoid, competitors, legal-flagged claims:
9.  Brand assets (logo SVG, colours, fonts, guidelines link):
10. Style references (videos you love) / anti-references:
11. Length (default 60 s):
12. Aspect & resolution (default 16:9, 1080p + 4K):
13. Audio (default music-only, original score) / licensed track / voiceover:
14. Tone (default premium, confident, technical):
15. Where it will be shown:
16. Deadline / approvers / legal footer / languages:
17. Existing videos of yours to match or beat:
```

## After intake
- Read back a 5-line summary: story thread, proof, footage source, length/aspect/audio, CTA. Then start Phase 1.
- If footage access needs a login, ask the user to log in themselves in the browser, or to provide a sandbox. Never type their passwords.
- Re-confirm any proof number you couldn't trace to a public source before it goes into the storyboard.
