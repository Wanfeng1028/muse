# AGENTS.md: guide for AI agents and contributors

Craft Anything is a native, pure-Rust app that shows anyone how a piece of software works (programs, apps, files,
websites, phones) with evidence-backed answers, then helps them rebuild it. It ships a desktop app (egui), a CLI and
an MCP server, all driven by one engine. Display name **Craft Anything**; machine names `craft-anything-*`; bundle id
`ai.storyteller.craft-anything`. Standards shared across the Crafting Apps live in `../craftrules` (read its
`AGENTS.md`); follow them. Repos never share code.

**Original work only:** never copy code, scripts, schemas, names, assets or wording from another project, and
never name other reverse-engineering products in source, docs, UI or commit messages.

## Workspace map

```text
crates/
  evidence   L0  Evidence records, canonical ids, confidence, unknowns, ToolError (the error contract)
  formats    L0  Standalone parsers (no workspace deps, no I/O): ELF/PE/Mach-O/WASM/DEX/APK/ASAR/plist/.NET/Go/…
  disasm     L1  Our own native engine (Clean room): decode, functions, CFG, xrefs, call graph, pseudo-C
  js         L1  JavaScript/Electron/web bundles: parse, module graph, IPC, source maps, unbundling
  analysis   L2  Analyzers producing evidence (triage, dossiers, trace, compare, app graph, rebuild ledger)
  platform   L2  Native services: owned processes, PTY capture, sandbox, engine store, atomic files
  engines    L3  Optional external engines: Ghidra bridge (Deep mode), adb, CDP, Frida, JADX, Apktool…
  engine     L4  Session, projects (.cany), workspaces (what the person is making), the inbox
                 (questions/approvals), ToolSpec registry, settings, consent, the tool list
  ai         L5  AI backends (Anthropic, OpenAI, OpenRouter, local, agent CLIs, SSH) + agent loop + crews,
                 and the rebuild workflow (study → build → check → refine)
  mcp        L5  MCP server: progressive toolsets, resources, prompts
  setup      L5  Connect to coding-agent apps; doctor; uninstall
  ui-egui    L6  The egui interface (Beginner + Experienced). The only crate that may use egui/eframe/winit/rfd.
  testkit        Test helpers and synthetic sample builders
apps/  craft-anything (desktop) · craft-anything-cli (CLI + `mcp`) · craft-anything-web (browser viewer)
xtask/ cargo xtask layers | tools [--check] | wasm | secrets [--history] | ci | version [set X.Y.Z]
```

Layering is enforced by `cargo xtask layers`. Register new crates in `xtask/src/main.rs`.

## Golden rules

1. **Never crash** (`../craftrules/standards/never-crash.md`). Hostile input is our main input. No
   `unwrap`/`expect`/`panic!`/`todo!`/`unimplemented!`/`unreachable!`/indexing on input-derived values in non-test
   code; every production crate root carries the deny attribute. Checked arithmetic, bounded recursion, capped
   allocations. Every crash fix gets a regression test.
2. **Everything is a tool.** User-visible behaviour = a `ToolSpec` in `crates/engine/src/tools/<area>.rs` with id,
   title, summary, beginner text, toolset, effects, requires, a schemars params struct, and `run`. Register the
   module with one line in `tools/mod.rs`. UI, CLI, MCP and the AI agent all dispatch by id. Programmatic calls
   never open dialogs.
3. **Evidence is the result.** Analysis tools return `ToolOutput::Evidence` built with `EvidenceBuilder` (honest
   confidence, limitations, coverage, locations). Large results: summary first, paged views (`offset`/`limit`).
4. **Clean room vs Deep.** `session.clean_room()` is true unless Deep mode is on (`deep_mode`, or `--deep` for one
   CLI run). Clean room never looks inside the original: only the tools in `engine/src/clean_room.rs` run, so a new
   tool is Deep-only until it's listed there, and it may be listed only if it touches no target or watches from
   outside, as a visitor or user would. Deep mode uses every tool; built-in engines must work fully without Ghidra,
   which only adds. Evidence records the engine and the flag.
5. **Effects are honest.** Declare every side effect. `EXECUTES_FOREIGN_CODE` and `MUTATES_DEVICE` trigger consent.
6. **Never break wasm** for L0–L2 (`cargo xtask wasm`).
7. **Thin UI.** UI state is serde data; colours/radii come from theme tokens.
8. **No secrets, no personal data** in requests, logs, tests or the repo (it is public): no API keys, tokens,
   private keys, `.env` files or local paths, only obvious fakes like `sk-test`. `cargo xtask secrets` checks what
   git would commit (`--history` checks every commit); enable the hook once per clone with
   `git config core.hooksPath .githooks`. Generic `CraftAnything-dev` User-Agent.
9. **Safe Rust only.** `unsafe_code = "forbid"` everywhere, no exceptions. Prefer pure-Rust crates; any dependency
   must be safe to use from safe code.
10. **Never crash, never lock up, around other programs.** Every external program (Ghidra, Java, adb, a browser,
    an agent CLI, ssh, git…) runs through `craft_anything_platform::process` only, never `std::process::Command`
    directly:
    - stdin is closed (or a pipe we write to), never inherited, so nothing can sit waiting at a prompt; ssh gets
      `BatchMode=yes`; tools get their non-interactive flags;
    - every run has a deadline (wall clock and idle), output is capped and drained on threads so pipes never fill,
      and the child (and its process group / Job Object) is killed on timeout, cancel or drop;
    - a missing program, non-zero exit, bad output or timeout is a `ToolError` with a plain-English remediation,
      never a panic or a hang;
    - nothing slow ever runs on the UI thread: the UI sends work to background threads and polls results.
11. **Never lock up on a lock.** Use `craft_anything_platform::sync::Mutex`, never `std::sync::Mutex` (clippy
    refuses it). It stops a real deadlock as soon as it forms, the waiter's work unwinding to its `catch_unwind` as
    an error; the watchdog reports anything held too long. Long jobs are fine: label the guard (`guard.label(id)`,
    as `Engine::call` does for tools) and they're waited for, not treated as stuck. A guard that isn't bound to a
    name lives until the statement ends, so read the session once: `cargo xtask locks` refuses a second
    `.session()` in reach of the first.

## Working rules (mandatory)

These apply to every change by every agent and contributor, whether or not anyone mentions them.

### Roles and ownership
- `docs/ROADMAP.md` is the plan: each item has an id (`R<milestone>.<n>`), an **owner**, a status and pending
  changes (`- [ ]` lines). Owners are roles, never people's names: **maintainers** (the project's maintainers
  steer it; agents may take its unclaimed pending changes, but anything marked **decision** waits for a
  maintainer) or **open** (anyone may take it).
- **Claim before you start:** put `— claimed: <name>, branch <branch>` on the pending change and push your branch
  early (or open a draft PR) so others see it. Never take a change someone else has claimed.
- Work in the order the roadmap's "Order and dependencies" table gives; an item starts only when its
  dependencies are done.
- A person's explicit instruction for a task overrides these rules for that task only; otherwise they apply to
  every change, without being asked.

### Before you write code
- Pick work from `docs/ROADMAP.md` only. Don't start an item that is claimed, `blocked`, or waiting on a
  **decision**, and don't start one whose dependencies aren't done.
- Claim the pending change first (name + branch, in its own small commit), so no two agents do the same work.
- Read the code you'll touch and check STATUS.md and the roadmap for gaps it depends on. If you find new gaps or
  dependencies, add them to the roadmap rather than widening your change.

### Git workflow
- Never commit to `main`. Branch from an up-to-date `main` with a standard prefix, then the roadmap id if
  there is one: `feature/`, `bugfix/`, `hotfix/` (urgent fix to released code), `refactor/`, `docs/`, `test/`
  or `chore/` (tooling, deps, CI). Example: `feature/r1.1-target-kind`.
- One roadmap item (or pending change) per PR. Keep PRs small and reviewable. No unrelated refactors or drive-by
  formatting.
- Open a PR into `main`. It is **squash-merged**, so the PR title is the commit message: plain English, present
  tense, what changed for the person or developer.
- Rebase on `main` before asking for review. Never force-push someone else's branch.
- Parallel agents work in their own git worktree and their own `CARGO_TARGET_DIR` (see "Parallel agents" below).
- Before every commit and push, check `git branch --show-current`; push by name (`git push origin <branch>`).

### Architecture
- **Headless first.** Every capability works without the GUI: engine → tools → CLI/MCP, with the GUI as one
  thin client. Orchestration, persistence and process control never live in `ui-egui` or `apps/*`. If the UI
  needs something, it calls the same engine API (or tool) the CLI does.
- **Extend through seams.** New target kinds, checks, builders, asset providers and engines are trait
  implementations registered in one place. Don't add another arm to a `match` over a closed enum. Prefer traits
  and generics with sensible built-in implementations, so forks can swap parts without editing core code.
- **Data over code.** Catalogues (stacks, engine recipes, model ids, prices, install pins) are typed tables, not
  string matches or prompt text.
- **Structured results.** Decide on typed fields, never on English text.
- **Versioned files.** Anything we persist has a version field, a schema and a migration path.
- Respect the layers (`cargo xtask layers`); put code at the lowest layer that can own it.

### Done means
- The checks in "Before you finish" pass for the crates you touched. New behaviour has tests; crash fixes have
  regression tests.
- Docs updated in the same PR: the roadmap item ticked, STATUS.md if what works changed, `docs/tools.md` if you
  added tools.
- Report what you verified and what you didn't. Never claim a live run you didn't do.
- Made a mistake worth not repeating? Add it to `docs/pitfalls.md` in the same PR.
- Found work that's missing or left for later? Add it as a `- [ ]` line under its roadmap item in the same PR
  (`cargo xtask pending` lists all open work).

## Extending

`docs/extending.md` says where each kind of addition goes (tools, target kinds, checks, stacks, coding agents,
asset providers, engines, plugins).

## Pitfalls

`docs/pitfalls.md` lists mistakes already made here (git, tests, builds, design) and the rule for each.
It is part of these rules: read it before your first change (Claude Code loads it automatically through
`CLAUDE.md`).

## Before you finish

```sh
cargo fmt --all
cargo test -p <crates you touched>
cargo clippy -p <crates> --all-targets -- -D warnings
cargo xtask layers
cargo xtask locks
cargo xtask secrets       # no keys, tokens or local paths in what you commit
cargo xtask wasm          # if you touched L0–L2
cargo xtask tools         # if you added tools (commit docs/tools.md)
```

Then append a terse entry to `log/devlog.md` (what landed, numbers, what's still open). `log/` is gitignored:
the devlog is a local scratch record; anything others need goes in the PR, `docs/STATUS.md` or `docs/ROADMAP.md`.

## Parallel agents

Own target dir (`CARGO_TARGET_DIR=target/agent-<name>`), own files. Shared files (`engine/src/tools/mod.rs`,
`engine/src/lib.rs`, workspace `Cargo.toml`) get small surgical edits; re-read right before editing. Write manifests
atomically (temp file outside `crates/`, then `mv`). If someone else's edit breaks the build, wait and retry.
