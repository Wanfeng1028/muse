# Review contract

## One decision at a time

Start with the promise, viewer, credible starting state, lesson, and visible payoff. Then present one scene card at a time, including the exact current narration and action anchors. Ask whether to approve, revise wording, or revise the scene. After every answer, summarize what changed and what remains next.

Finish with a short readback in scene order, including the exact opening and closing lines. Approval is an explicit human choice; a recommendation, a passing checker, or no reply is not approval.

## Hash-bound decisions

Keep the story approval ledger separate from the runtime's semantic-audit `review.json`. In the working ledger, bind each decision to a stable hash of the exact card contents, narration, and upstream inputs that affect it. Record the approved wording verbatim. If wording, screen state, actions, or order changes, mark the affected decision stale and present it again. Reordering scenes requires a new final readback.

Do not preserve an approval merely because a new draft sounds similar. A changed card has a new hash and needs a fresh decision. Keep a small machine-readable decision record with current input hashes, review status, card hashes, exact decision, and timestamp. A plan's `wordingApproval.sha256` binds exact scene text and is not evidence of operator approval. The later CLI `review.json` records a caller-declared independent or operator content/UX verdict; it binds `missionId`, `packetHash`, `planHash`, and `videoHash`, but does not store per-card approvals. `reviewerId` and `reviewerType` are local declarations, not authenticated identity. The resulting receipt sets `identityAssurance` to `caller-attested`; the tool compares the declared ID's fingerprint with the producer fingerprint but cannot prove who performed the review. Ensure actual independence through the surrounding process. See the [CLI contract](../../../docs/cli.md) for its exact submission shape.

## Draft previews

A preview is evidence for a review choice, not approval or publication proof. Use the actual browser path and current proposed narration; do not substitute a mock, a slide, or an unrelated clip. Label the candidate and its working note `DRAFT PREVIEW — NOT APPROVED`, and bind it in the working record to the current card, narration, source capture, and rendered video hashes. The CLI `preview` command prints the plan and review packet; it does not open or render a video preview.

After a preview finding, repair the owning story, action, or capture input and generate a new preview. Recheck every open finding against the replacement. Reuse only footage that still matches the exact current story, action, state, and framing. A changed input invalidates its derived preview.

## Bounded revisions

Track each meaningful revision and the finding it addresses. Stop on the first complete pass. Do not use more than six review rounds; six is a ceiling, not a target. A repeated finding without new evidence is a signal to revisit the owning decision, not to keep polishing around it.
