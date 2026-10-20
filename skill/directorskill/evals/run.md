# Running the Evals

[evals.json](evals.json) is a behaviour contract, not a suite that executes itself. Each case is a prompt plus assertions checkable from the response text alone. Running it means generating responses, then grading them.

## Run one case by hand

1. Open a fresh session with the skill installed and nothing else in context. A carried-over conversation is the largest source of false passes.
2. Paste the case's `prompt` verbatim. Add nothing — no "use the cinematic-director skill", no format hint, no reminder of the mode.
3. Save the whole response, preamble included, then grade the assertions in order against that text.

One case per session. Two cases in one session lets the second inherit the first's shot plan.

## Run the suite with a grading agent

Generate one response per case in `evals.json` first, then grade. Generating and grading in one session leaks the assertions into the answer. Send this once per case, with nothing else in context:

```text
You are grading one response against a fixed list of assertions. You have no other job.

CASE PROMPT:
<the case's prompt field, verbatim>

RESPONSE:
<the full response text>

ASSERTIONS:
1. <assertion 1>  ...  n. <assertion n>

For each assertion output exactly one line:
  <n>. PASS|FAIL — <quoted span from the response, or why nothing satisfies it>

Judge only what is written in RESPONSE. Do not infer intent, do not credit a near
miss, and do not reward good work the assertion did not ask for. An assertion naming
a number, a unit, or a verbatim clause fails unless that number, unit, or clause
appears in the text. Output no summary and no advice.
```

## What counts as a pass

| Assertion shape | Passes when |
|---|---|
| Names a number or range — "in mm", "sums to 20 seconds", "0-18" | The number is present and inside the range. Arithmetic that does not close is a fail. |
| Names a verbatim artifact — "repeated verbatim across all four prompts" | The string appears identically in every place the assertion names. |
| Forbids something — "no segment line contains an emotion word" | Zero instances anywhere in the response. One instance is a fail. |
| Names a structure — "look, what-is-seen, reaction" | Every named part is present and identifiable. Partial structure is a fail. |
| Names proportion — "no director's book appears" | Judge the delivered sections, not the word count. |

A case passes only when every one of its assertions passes. Assertions are the unit of diagnosis; cases are the unit of the score.

## The pass bar

- **Ship bar: 92% of cases** — 52 of the 57 in the suite today. Below that, do not tag a release.
- **Hard-fail set, which must pass whatever the total:** `symptom-only-no-artifact`, `one-line-ask-one-deliverable`, `multi-shot-timestamped-sequence`, and every case carrying a copyright-safety assertion. These guard guardrails, not craft.
- Re-run a failing case twice before editing the skill. Three runs distinguish model variance from a real hole; one failure does not.

## The `loads` field

`loads` is **advisory and is not graded**. Response text does not reliably state which files were opened, and an assertion that demanded it would be an assertion about hidden reasoning — which this suite forbids. Two ways to check it when it matters: read the harness's tool log for the run and diff the opened paths against `loads`; or, with no log, treat `loads` as a claim about the routing table in [../SKILL.md](../SKILL.md) and verify the table instead of the response. CI checks that every `loads` path exists on disk. It cannot check that a response used it.

## Adding a case

1. Give it a unique lowercase hyphenated id naming the behaviour under test, not the scene.
2. Carry exactly the six fields — `id`, `mode`, `loads`, `prompt`, `expected_output`, `assertions`. The validator rejects extras and missing ones.
3. Write 5-6 assertions, each checkable from the response text by a reader who has not opened SKILL.md.
4. Assert nothing SKILL.md does not specify. Where the skill forbids something, assert the forbidden thing is absent — never assert behaviour the skill rules out.
5. A new director overlay needs exactly one case proving the lens changed camera, palette, pacing, or sound, plus the copyright-safety assertion. See [../CONTRIBUTING.md](../CONTRIBUTING.md).
6. Run `python3 -c "import json;json.load(open('evals/evals.json'))"` before pushing; the `evals` workflow runs the full validation.

Worked example — assertion 4 of `multi-shot-timestamped-sequence`, "no segment line contains an emotion word". Scan the three segment lines only, not the global block or the prose around them. `[00:03-00:06] Close on her hand taking the envelope, camera locked.` carries none, and neither do the other two: PASS. Had it read `she takes the envelope nervously`, that one instance fails the assertion outright — no credit for the two clean segments.
