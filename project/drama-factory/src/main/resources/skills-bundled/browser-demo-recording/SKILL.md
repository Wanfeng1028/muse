---
name: browser-demo-recording
description: Record an approved product walkthrough in a real browser with readable transitions, purposeful cursor movement, and verifiable results.
---

# Browser demo recording

Use this skill to capture an approved plan in a real browser. Record the product's actual behavior; an animated cursor or a spoken claim cannot stand in for a completed interaction.

## Workflow

1. Confirm the plan, target URL, viewport, browser, app readiness, and output workspace. The viewport is the delivered resolution, so choose one whose text stays readable on a phone. Do not access a protected or customer system unless the user authorized that target and action.
2. Use stable, visible browser locators and the app's actual controls. Type at a human-readable pace; do not rely on forced clicks or coordinate fallbacks.
3. Keep a purposeful cursor path and continuous screen composition. Let viewers read a result before transitioning, and orient them before the next active action.
4. Capture evidence for each required state change and assertion. Keep active actions synchronized to their approved spoken anchors.
5. Save outputs only within the declared workspace, then run [demo-audit](../demo-audit/SKILL.md). Read [the capture contract](references/capture-contract.md) for preparation, pacing, and repair. When you record many plans, rehearse each one silently first; see [demo-production-pipeline](../demo-production-pipeline/SKILL.md).

By default, use the bundled synthetic example and captioned output. Paid credentials are not required for the default workflow. Voice providers and their terms are optional choices; never place credentials in a plan, prompt, command line, or generated artifact.
