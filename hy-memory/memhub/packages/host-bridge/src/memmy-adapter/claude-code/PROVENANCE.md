# MH-C01 Claude Code Candidate

Upstream: MemTensor `memmy-agent`, pinned commit
`25acd5f29fc7df73b943713abe61f1b2f9839887`.
License: MIT, Copyright (c) 2026-present MemTensor. `LICENSE.memmy` preserves the
complete upstream notice verbatim; `license.ts` embeds that same notice in the
candidate installation. No upstream brand assets, icons, fonts or mascots are used.

## Adaptation Boundary

This is a source-level adaptation of the Claude integration module's installation
and event design, not a verbatim import of the upstream runtime. The module is
substantially rewritten to honor One Memory's distinct authorization and storage
contracts. It is not yet selected by any default installer or package entry point.

| Upstream module under `Memory/src/agent-source/integration/` | Candidate implementation and actual changes |
| --- | --- |
| `claude-code/target.ts`, `hook-command.ts`, `skill-directory.ts`, `types.ts` | `target.ts`, `install-plan.ts`, `hook-template.ts`: retain Claude settings, five event bindings, instruction marker, skill and explicit slash-command installation. Replace substring deletion and directory replacement with exact owned entries, preview fingerprints, conflict rejection and a reversible journal. This transaction machinery is new One Memory code. |
| `templates/memmy-resume-hook.ts` | `event-adapter.ts`, `runtime.ts`, `session-state.ts`: adapt JSON hook dispatch, prompt/stop separation, explicit resume parser and turn-local state. Rewrite service calls and state representation; no transcript reads, pending prompt/answer storage, weak state hash or default session identity. |
| `memmy-runtime-config.ts`, `workspace-bridge/runtime.ts`, `runtime-loader.ts`, `build-runtime.mjs` | `runtime-config.ts`, `runtime.ts`, generated `hook.mjs`: retain separately packaged runtime/config boundary. Replace YAML/default endpoint/empty-token/analytics identity resolution with explicit trusted One Memory paths and a required injected notification capability. Reuse existing One Memory `broker-client.ts`, not Memmy's session service. |
| `templates/memmy-plugin.ts`, `memmy-skill-directory.ts`, Claude resume command | `hook-template.ts`: newly worded One Memory instructions, explicit query-only resume and honest unavailable states. No upstream product claims, L3 promises or episode picker. |
| Upstream filesystem writes/state helpers | `private-files.ts`, state locking and SHA256 identities are new One Memory safeguards, not copied upstream guarantees. |

The inspected dependency closure also included agent-path resolution and workspace
identity/canonical JSON/L3 rendering contracts. These are not imported: the pilot
ignores host-supplied cwd/path/source/token and uses only the authorized `all-apps`
recall scope. Memmy `sessions/open`, `turns/start`, `turns/complete`, L3 boundaries,
episode search/detail, analytics and automatic trust mutations are not migrated.

## D37 Complementary Mode

The original 20-test candidate freeze remains historical evidence. D37 adds an
explicit, validated `sync-only` or `recall-and-sync` configuration; missing mode
is rejected instead of silently enabling recall. Initial integration selects
sync-only: prompts record bounded turn metadata and Stop notifies, while existing
MCP recall remains independent. No prompt context or public recall notice is
injected in this mode. An oversized recall query still leaves a pending turn for
Stop; the runtime's existing 64KiB total JSON input bound remains unchanged.

`notification-transport.ts` is new One Memory code, not copied from Memmy. It
uses the existing discovery/credential boundaries and Axios to verify loopback
broker identity before sending the four-field `/source-changed` notification.
The entire call has a 25-second deadline, with no redirects, environment proxy,
automatic retries, alternate endpoint or raw error/credential disclosure. A
late credential lookup cannot dispatch after the deadline. Each call rereads
the installation credential; it does not create grants or read transcripts.

Both modes are tested as temporary self-contained runtime/notification ESM
assets with real Node child processes and a local fake service. Multi-entry
bundles require `splitting:false` as well as the existing `createRequire`
banner; otherwise a shared chunk would be absent from the two-asset install.
These tests do not execute a native Claude session or a real model call.

## Delivered Contract And Remaining Integration

- In recall-and-sync mode, prompt and explicit `/one-memory-resume <query>` use existing authenticated
  recall, at most 2000 characters without truncating an oversized query. Actual
  returned memory/evidence IDs are retained. Empty, denial and unavailable differ.
- Stop emits only version/event ID/session ID/event kind. No text, path, source,
  token, Evidence write, model request or permission mutation is sent.
- SessionStart/PostCompact/SessionEnd maintain local versioned state only.
- The production notification asset is now implemented; the desktop integration owns broker
  installation-to-source mapping, source-read and independent sync gates,
  revocation, coalescing/rate bounds and adapter -> Evidence -> HY acceptance.
  No test endpoint is present in the production transport or bundled assets.
- `verifiedAssets` is an exact-hash packaging-owner attestation, not a sandbox or
  semantic proof for arbitrary JavaScript. Missing assets/proof refuse a plan.
  Passing candidate tests does not attest a future production transport asset.

## Operational Limits

POSIX candidate only; no Windows ACL claim. Explicit existing Node executable,
no new runtime dependency, no default dist build. Bundling the existing Axios
dependency to ESM requires a Node `createRequire` banner; the loopback integration
test executes that exact temporary bundle outside the repository's node_modules.

The installation journal supports rollback after caught failures, not multi-file
crash atomicity. An interrupted applying journal requires explicit recovery and
is never silently overwritten. Uninstall preserves runtime state and credentials;
it removes only owned installation files and leaves unrelated directories alone.
Same-OS-account malicious filesystem races are not a sandbox boundary.

Each state file is size-limited and keeps at most 64 event hashes; total session
file count is not globally bounded. Stop reserves an event before sending to
coalesce concurrent hooks. A caught transport failure permits a same-ID retry;
process death after reservation can lose that notification, so this is not an
exactly-once delivery guarantee. Stale Stop detection is stronger only when the
host supplies a turn ID. Normal source watching remains Core-owned. Full episode
resume and L3 remain explicitly pending, not success-shaped placeholders.
