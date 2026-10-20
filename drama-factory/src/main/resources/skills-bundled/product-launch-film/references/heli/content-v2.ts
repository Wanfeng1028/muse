// Every Heli string below is verbatim output of heli-harness v0.10.4 (repo HEAD 3d0d234), captured by
// running a copy of the repo with HOME=/tmp/hs2/home against a scratch parent workspace
// (heli install /tmp/hs2/shop). Raw captures: docs/captures-v2/. Only the workspace path was localised
// (/private/tmp/hs2/shop -> /Users/kj/code/shop). The api repo, its test names and the patch are a demo.

export const TASK_ID = 'fix-login-timeout';

// heli task create  (lib/cli/task.mjs "create")
export const CREATE_CMD = ["heli task create fix-login-timeout \\", "  --title 'Fix login timeout on slow networks' --repo api"];
export const CREATE_OUT = [
	'Created task fix-login-timeout',
	'  title: Fix login timeout on slow networks',
	'  fingerprint: f2708ab87e7834fecfe3f3224f578911',
	'  workspace mode: concurrent',
];

// .heli-harness/tasks/fix-login-timeout/current-task.md as the Claude Code session left it
// (template: .heli-harness/templates/current-task.md; field names are Heli's, values are the demo's).
export const RECORD_PATH = '.heli-harness/tasks/fix-login-timeout/current-task.md';
export type RecLine = {t: string; key?: 'changed' | 'failed' | 'next' | 'status'};
export const RECORD: RecLine[] = [
	{t: '# Current Task'},
	{t: ''},
	{t: 'Task: Fix login timeout on slow networks'},
	{t: 'Risk tier: S1'},
	{t: 'Files expected to change:', key: 'changed'},
	{t: '- repos/api/src/auth/client.ts', key: 'changed'},
	{t: 'Planned verification:'},
	{t: '- npm test -- auth'},
	{t: 'Current status: blocked', key: 'status'},
	{t: 'Failed attempts count: 2', key: 'failed'},
	{t: 'Next smallest action: stop patching; diagnose why', key: 'next'},
	{t: '  the client aborts at 10s', key: 'next'},
];

// SessionStart additionalContext emitted by .heli-harness/adapters/codex-plugin/hooks/heli-session-start.mjs
// (adapters/shared/concurrency/resolve.mjs buildConcurrentSessionContext). Lines shown in order; '…' marks
// lines skipped for space.
export const CONTEXT = [
	'Heli Concurrent Session',
	'- Task: fix-login-timeout',
	'- Target: api',
	'- Lease: active',
	'…',
	'Bound task state from tasks/fix-login-timeout/current-task.md:',
	'…',
	'Current status: blocked',
	'Failed attempts count: 2',
	'Next smallest action: stop patching; diagnose why the client aborts at 10s',
];
export const SWITCH_HOSTS = ['Claude Code', 'Codex', 'Grok Build', 'OpenCode', 'Kimi Code CLI'];

// Skill rules, verbatim from .heli-harness/skills/<name>/SKILL.md
export const SKILLS = [
	{name: 'verify-premise', rule: 'Do not implement if the premise is false or unclear.'},
	{name: 'fix-loop', rule: 'After two failed implementation attempts on the same issue, stop coding and write diagnosis.'},
];

// Codex PreToolUse (apply_patch) with the record above: adapters/shared/concurrency/resolve.mjs readTaskGateForContext
export const PATCH_FILE = 'repos/api/src/auth/client.ts';
export const PATCH = ['-  timeout: 10_000,', '+  timeout: 30_000,'];
export const STRIKE_REASON =
	'Heli-Harness: task fix-login-timeout current-task.md shows 2 failed attempts and status "blocked" — update tasks/fix-login-timeout/current-task.md before continuing.';

// Evidence-gated completion (lib/cli/task.mjs "complete" + adapters/shared/concurrency/diagnosis.mjs
// evaluateDiagnosisCompletion), with an active diagnosis on the task.
export const COMPLETE_CMD = 'heli task complete fix-login-timeout';
export const COMPLETE_BLOCKED = [
	'Error: task fix-login-timeout completion blocked: current passing verification evidence is required before completion',
	'Code: VERIFICATION_EVIDENCE_REQUIRED',
];
export const RECORD_CMD = ['heli diagnosis record fix-login-timeout --type run \\', `  --json '{"runId":"auth-tests","status":"passed"}'`];
/** The record command prints the whole diagnosis.json (≈60 lines); shown folded to its first keys. */
export const RECORD_OUT_FOLDED = '{ "schemaVersion": 1, "taskId": "fix-login-timeout", … }';
export const COMPLETE_OK = ['Released write lease on fix-login-timeout', 'Task fix-login-timeout marked complete (revision 2)'];

// Governance (v1 captures, claude-plugin PreToolUse, linked project)
export const PUSH_CMD = 'git push origin main';
export const PUSH_REASON =
	'Heli-Harness blocks git push without scoped authority. Ask the user to run `heli grant issue --action git.push --scope once` in their own terminal. Emergency/debug overrides remain HELI_ALLOW_GIT_PUSH or YOLO.';
export const RM_CMD = 'rm -rf build';
export const RM_REASON =
	'Heli-Harness blocks destructive command "rm -rf" (rule destructive-delete, tier T6): Recursive forced delete is destructive. This is a hard deny; scoped grants, YOLO and HELI_ALLOW_COMMAND do not override it.';
export const RULE_HOSTS = ['Claude Code', 'Codex', 'Grok Build', 'OpenCode', 'Kimi Code CLI', 'Pi'];
