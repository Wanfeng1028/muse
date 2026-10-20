# Legal and honesty

Ownership, indemnity, people, platform disclosure, provenance.

Contents
1. Legal and honesty

---

## Legal and honesty

| Provider | Outputs | Watch out |
|---|---|---|
| OpenAI | "you ... own the Output"; may not be unique | IP indemnity for API/Enterprise customers, excluding trademark claims, disabled safety features, modified/combined outputs, and "knew or should have known" infringement; usage policy bans non-consensual likeness that confuses authenticity |
| Google Gemini API | Google claims no ownership | **Terms forbid use in an app "directed towards or likely to be accessed by individuals under the age of 18"**. My reading (unverified): offline asset generation by a developer may be outside it, but for children's brands prefer OpenAI or confirm with counsel. Indemnity only on Vertex. SynthID always on |
| Midjourney | you own Assets; companies over $1M revenue need Pro/Mega; public by default; stealth Pro/Mega only | no API, automation forbidden; studio character lawsuits pending |
| BFL FLUX | no ownership claim; commercial OK; BFL gets a licence to inputs/outputs | [dev] weights non-commercial, though their outputs may be used commercially |
| Ideogram | no ownership claim; commercial OK | API ToS asks apps to label "Powered by Ideogram"; free generations public (unverified) |
| Recraft | paid plans: full ownership, private; free plan: Recraft owns, no commercial use | |
| Seedream (BytePlus) | ownership clause not readable (unverified) | visible "AI-generated" watermark on by default (`watermark:false`), C2PA embedded; terms may forbid stripping AI marks (unverified) |
| Adobe Firefly | "commercially safe" training data | indemnity on qualifying enterprise plans |

- Copyright: the US Copyright Office (Part 2, 2025-01-29) says prompts alone don't make output copyrightable. Human selection, arrangement and modification can be protected. So keep prompt logs and record the human curation and compositing.
- People:
  - Never generate a real, identifiable person, public figure or employee.
  - Cast fictional characters only.
  - Don't present generated people as customers or testimonials.
  - Disclose realistic synthetic people where the platform requires it.
- Platform rules:
  - YouTube requires the "altered or synthetic" disclosure for realistic content; clearly animated or unrealistic content is exempt.
  - TikTok and Meta auto-label uploads that carry C2PA.
  - EU AI Act Art. 50 applies from 2026-08-02. Deepfakes must be disclosed; for evidently artistic or fictional works, disclosure must "not hamper" the work.
- IP: no trademarked characters, logos, brand products or living-artist names in prompts. If a brand appears, composite the client's own asset under their licence.
- Provenance:
  - OpenAI API images carry C2PA + SynthID. BFL signs C2PA plus a soft watermark. Google adds SynthID, plus C2PA on Vertex. ModelArk embeds C2PA.
  - C2PA metadata is lost on screenshot or re-encode, and a Remotion render re-encodes everything. Keep masters with their credentials in the project archive.
  - Don't deliberately strip marks. If a client needs C2PA on the final video, sign the render with a C2PA tool (unverified).
