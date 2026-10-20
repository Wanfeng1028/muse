---
name: demo-story-review
description: Review the exact scenes and narration of a demo one decision at a time, with hash-bound approvals and draft previews.
---

# Demo story review

Use this skill when a person needs to approve the story, scene order, or exact narration before capture. This is an approval workflow, not permission to rewrite the product facts.

Show one review card at a time. Include **Before / During / After / Say / Do / Learn / Next**, with the exact current narration. Offer the evidence-supported recommendation, but never treat silence or a preview as approval.

## Workflow

1. Review the whole-story promise and payoff, then each scene, then a concise final readback.
2. Ask one decision at a time. Record the selected choice and exact accepted wording against the current card hash in the working decision ledger. This authoring ledger is distinct from the runtime's semantic-audit `review.json`.
3. When words, order, or visible proof change, invalidate affected decisions and ask again for the changed card.
4. If useful, show a real-screen draft preview marked **DRAFT PREVIEW — NOT APPROVED** and non-publishable. Bind it to the exact draft and source hashes.
5. After capture, an independent reviewer compares the final screen and speech with the accepted story and submits a separate exact-hash `review.json`. When using the built CLI, run `node dist/cli.js review --file review.json --work-dir <work-dir>`. Return only the current reviewed story to [demo-audit](../demo-audit/SKILL.md). Read [the review contract](references/review-contract.md) for decision records, draft previews, and revision limits.

The generated `review-packet.json` is review evidence, not an approval. The hash in `wordingApproval` is an integrity binding, not a human decision. The narration author must not be the sole reviewer; this is a workflow requirement. The resulting receipt marks `identityAssurance` as `caller-attested`; the runtime compares the caller-supplied reviewer ID with its locally stored producer fingerprint, but does not authenticate real-world identity or prove that `reviewerType: independent` is true. A human decision is required for every approval boundary the user requested; a genuinely independent semantic review is still required before publication.
