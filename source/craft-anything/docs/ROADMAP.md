# Roadmap

The shared plan for reaching the product described in the README, for people and agents alike.
`docs/STATUS.md` says what works today; this file says what comes next, who owns it and what an
agent may pick up. Drafted 2026-10-18 from a survey of `main` at `1d47a3e` (624 tests passing);
brought up to date on 2026-10-22.

## How to use this file

- Each item has an **id** (`R<milestone>.<n>`), an **owner**, a **status** and a list of
  **pending changes**. Pending changes are small, independently mergeable units.
- **Claiming:** before you start, put `— claimed: <name>, branch <branch>` on the pending change
  and push your branch early (or open a draft PR) so others see it. Don't take a change someone
  else has claimed. The full working rules are in `AGENTS.md` ("Working rules", mandatory). Items owned by **maintainers** are steered by the
  project maintainers: agents may take their *unclaimed pending changes*, but design decisions
  marked **decision** wait for a maintainer.
- **Finishing:** tick the change (`[x]`), add the commit or PR, update `docs/STATUS.md` if what
  works changed, and add a line to `log/devlog.md`.
- **Status:** `todo` · `in progress` · `blocked (<why>)` · `done`.
- Follow `AGENTS.md` (layering, never crash, everything is a tool, `platform::process` for every
  external program) and the architecture rules below.

## Architecture rules for new work

The project should be easy to fork and bend. New features land behind a seam, not inside a
`match`:

1. **Traits plus a registry, not enums.** Target kinds, checks, builders, asset providers and
   external engines are traits with a registry that holds built-in implementations. Adding one
   means adding a file and one registration line (as tools already work).
2. **Data over code for catalogues.** Stacks, game-engine build recipes, model ids and prices,
   and engine install pins live in typed tables (or TOML files embedded with `include_str!`), not
   in string matches or prompt text.
3. **Headless first; flows are tools.** Everything works without the GUI. Anything a person
   can start from the UI (rebuild, follow-ups, answering questions, engine installs, launching a
   result) is reachable through `Engine::call` and the CLI, so MCP, agents, scripts and other
   frontends get it for free. Orchestration, persistence and process control never live in
   `ui-egui` or `apps/*`.
4. **Versioned files.** Every file we write and read back (`craft.json`, `config.toml`,
   `project.toml`) carries a version, has a JSON schema, and has a migration path.
5. **Structured results.** Decisions such as "did the build pass" read typed fields, never
   English text prefixes.

## Milestones at a glance

| Milestone | Goal | Owner | Where it stands (2026-10-22) |
|---|---|---|---|
| M0 Foundations | Docs match the code, licences checked, rule violations fixed, one live end-to-end run | maintainers | Done; protecting `main` is a maintainer setting still to switch on |
| M1 Extensibility | Seams for target kinds, checks, builders, asset providers, engines, plugins | maintainers | Done except runtime and behaviour checks (with R2.4, R2.5) and engine transports (R1.5) |
| M2 Product completeness | Every target kind gets study → build → check → refine with a real check; building works without an agent app | maintainers | Websites complete; apps and games build and run; API-key builds and other agents are built but not yet run live |
| M3 Engine depth | More tools, and the known partial ones | open | 284 tools; device-backed tools wait for an Android device; game asset export continues |
| M4 Release | Packaging, CI, signing, managed tier | maintainers (later) | CI passes; release workflows for every platform are on `main`; v0.1.0 is released, signed, on every platform |

## Open work

Every unticked `- [ ]` line in this file is open work, under the item it belongs to.
`cargo xtask pending` lists them all, grouped by item (`--count` for the totals). When you find
work that's missing, add it as a `- [ ]` line under the right item in the same PR, rather than
leaving it in a PR description or a chat.

## Order and dependencies

Work in phases. Items in the same phase can run in parallel. An item starts only when everything
in its **Depends on** column is done; a *soft* dependency should come first but doesn't block.
M3 is an open lane that can run at any time.

| Phase | Item | Depends on | Why here |
|---|---|---|---|
| 0 Baseline | R0.1 Docs match `main` | — | Every agent reads them |
| 0 | R0.7 Live end-to-end run | — (needs a signed-in `claude`) | A working reference before refactors |
| 0 | R0.3 Licence hygiene | — | Cheap; parallel |
| 0 | R0.4 Rule-10 fixes | — | Clears direct process calls before R1.6 moves them |
| 0 | R0.5 Small correctness items | — | Parallel |
| 0 | R0.2 Salvage PR #1 | **decision** | Unblocks M4 later |
| 0 | R0.8 Tests never touch the real machine | — | Found when a test started a real download |
| 0 | R0.6 Tool naming | **decision** | Fixes ids before new tools (R1.6) and plugins (R1.8) |
| 1 Seams | R1.1 `TargetKind`, split `rebuild.rs` | R0.7 *(soft)* | Most scattered `match` code; everything in M2 builds on it |
| 1 | R1.2 `Check` trait | R1.1 | Checks hang off the target kind |
| 1 | R1.3 Builder adapter registry | — | Independent of R1.1; parallel |
| 1 | R1.4 Asset provider trait | — | Parallel |
| 1 | R1.5 External engine trait in L3 | — | Engine installs in R1.6 sit on it |
| 1 | R1.9 Versioned files | — | The project service in R1.6 writes new files |
| 2 Headless | R1.6 GUI stops being the glue | R1.1, R1.5, R1.9, R0.4, R0.6 | Everything after it is reachable without the GUI |
| 3 Product | R2.1 Building with API keys | R1.3, R1.6 | Removes the agent-app requirement |
| 3 | R2.2 More coding agents | R1.3 | |
| 3 | R2.3 Website coverage, better metric | R1.2 | |
| 3 | R2.6 Several rebuilds at once | R1.6 | |
| 3 | R2.7 The request decides how to build | — | A request that names a stack was ignored |
| 3 | R2.8 Clean room means clean room | — | Clean room still read the original's code and files |
| 3 | R2.9 Everyday use: typing, projects, settings | — | Found by live use of the app |
| 3 | R2.10 Pinned builds | — | Keep a build to open while the project changes |
| 4 Depth | R2.4 Runtime study for apps and games | R1.2, R1.6 | |
| 4 | R2.5 Behaviour checks for non-web builds | R1.2 | |
| 4 | R1.7 Dynamic tool registry | R1.6 | |
| 4 | R1.8 Plugins | R1.7, R0.6 | Freezes the extension API, so it comes last |
| Any | R3.1–R3.10 Engine depth, game archives and assets, app facts | — | Open lane |
| Last | M4 Release | R0.2, R0.3 and phase 3 | |

---

## M0 Foundations

### R0.1 Bring the docs up to date with `main`
Owner: maintainers · Status: done (branch `docs/r0.1-status-refresh`)
STATUS.md is dated 2026-10-16 (branch `feat/simple-mode-mvp`). It doesn't cover games, engine
detection and builds, fal.ai assets, Deep/Auto mode or the long-run limits.
- [x] Refresh STATUS.md: games, Deep mode with Ghidra, Auto mode, asset budget, current limits
- [x] ATTRIBUTION.md lists the third-party material the repository ships
- [x] AGENTS.md: `log/` is gitignored; say the devlog is local, or track it
- [x] Regenerate the tool list (asset tools); README tool count (228); claude-code.md rounds

### R0.2 Salvage PR #1 (`ci-release`)
Owner: maintainers · Status: done (branch `chore/r0.2-release-pipeline`, supersedes #1)
The PR branches from the initial commit, about 35 commits behind `main`. CI isn't a priority, but
its packaging, `cargo xtask version` and web viewer are worth keeping.
- [x] **decision**: rebase completely onto `main` (all six commits kept, `ci-release` untouched)
- [x] Port `apps/craft-anything-web` (wasm viewer) and `cargo xtask version`
- [x] Port the platform fixes: capture is Linux and macOS only (FreeBSD loses output); the spawn
      lock was reverted inside the PR itself
- [x] Keep workflows parked until M4: manual-only (`workflow_dispatch`); `release.yml` unchanged

### R0.3 Licence hygiene
Owner: open · Status: done (branch `chore/r0.3-licences`)
No `deny.toml` exists. The survey found no GPL, AGPL or SSPL crates, and only MPL-2.0
`option-ext` (via `dirs`) in the shipped app.
- [x] Add `deny.toml` (allow MIT, Apache-2.0, BSD-2/3, ISC, Zlib, 0BSD, Unicode-3.0, BSL-1.0,
      CDLA-Permissive-2.0, OFL-1.1, MPL-2.0 as an explicit exception), and `cargo xtask licenses`
- [x] Generate a third-party licence bundle (`cargo about`) for releases (`about.toml`; first run at M4)
- [x] NOTICE/ATTRIBUTION: egui's embedded default fonts (OFL-1.1, Ubuntu Font Licence)
- [x] Policy in this file: external programs we *run* (Ghidra, rizin, tshark, Frida, JADX) may
      have any licence. We never link or bundle copyleft code. (Lives in `docs/licences.md`.)
- [x] Follow-ups from the first `cargo deny check`: rustls 0.23.46; ruzstd 0.9.1 (a tiny `.zst`
      could exhaust memory); `publish = false` in every workspace crate; `cargo deny check` passes
      (advisories, bans, licences, sources)
- [ ] Revisit the two advisory exceptions in `deny.toml`: `rsa` (no fix; we only verify with public
      keys) when rsa 0.10 lands, and unmaintained `zbus_names`/`zvariant` (Linux-only via keyring
      and accesskit) when those move on
- [x] `crates/engines/src/game.rs` (installer, PowerShell signature check: no deadline)
- [x] `crates/ui-egui/src/project.rs`, `crates/ui-egui/src/engine_ui.rs`
- [x] Add a check to `cargo xtask layers` that fails on `std::process::Command` outside `platform`

### R0.5 Small correctness items from the survey
Owner: open · Status: done (branch chore/r0.5-cleanups)
- [x] Disclosed partially read SQLite cell payloads, preserved column positions, and withheld hashes of incomplete BLOBs.
- [x] Filled missing trailing SQLite record fields from literal column defaults and disclosed unsupported defaults as NULL.
- [x] Restored rowid aliases in SQLite INTEGER primary-key columns while preserving stored values and non-alias keys.
- [x] Read and counted WITHOUT ROWID table records from leaf and interior index pages, restored declaration column order, and reported absent rowids as null.
- [x] Decode Objective-C chained pointer offsets past file-empty PAGEZERO mappings (#296).
- [x] Recognise root-relative macOS bundles and nested XPC services in Apple app graphs (#282).
- [x] Checked arithmetic on file offsets in `elf.rs`: `va_to_off` adds a segment's file offset to an
      address delta unchecked, so a `PT_LOAD` at offset `u64::MAX` overflows, found by a lint scan
      of `crates/formats` (#43)
- [x] Capped allocation in `unreal_iostore.rs`: a `.utoc` header naming 2^31 compression methods of
      length 0 collected empty names until memory ran out (6 GiB from a 559-byte file); only the
      255 a block can point at are read, the rest skipped. Found by mutation fuzzing of `crates/formats`
- [x] No endless loop on code at the top of the address space in `disasm/src/program.rs`: the
      prologue and PLT scans stepped past `u64::MAX`, which in release wrapped to 0 and walked the
      whole 64-bit space (`native_functions_list` on a 4 KB ELF whose `.text` is at
      `0xffffffffffffffc0` never returned, and Stop couldn't end it). Found by mutation fuzzing of `crates/disasm`
- [x] The Agent console keeps its size: its history and prompt box came out 17 points taller than
      the bottom panel, which grew by that every frame until its maximum and then cut off the top
      of the Agent / Jobs / Log tabs (`chat::conversation`)
- [x] `yaxpeax-arm` 0.5.0 panicked ("register number out of range") on an A32 `STRD`/`LDRD` with
      Rt = 15 (e.g. the word `0xc0c7fef3`), so one such word failed the whole analysis of a 32-bit
      ARM program; the word now decodes as invalid
- [x] ARM32 value-flow graphs use r0 for word results and ARM scratch registers for calls (#239).
- [x] Unchecked `o + 4`/`o + 8` on section and program header offsets in `formats/src/dart.rs`
      (`Elf::parse`): a header table near `usize::MAX` panicked in debug builds (in release the
      wrapped reads were thrown away, since the entry's first field was already out of range); an
      entry that starts past the end of the file is now skipped
- [x] `cargo xtask layers` also scans `apps/`
- [x] WebAssembly interface comparisons resolve exported tag parameter types (#309).
- [x] Engines in `KNOWN` without a `ToolPaths` override (tshark, objdump, rizin, java)
- [x] Class-usage search includes the component class of multidimensional object arrays (#325).
- [x] Missing `database` icon for SQLite in the UI (`kind_icon`)
- [x] Deduplicate the five private `fn spec(` helpers in the tool modules
- [x] Keep dependencies between recognised esbuild wrappers after identifier minification (#270).
- [x] rustfmt drift on main (11 files)
- [x] Checked arithmetic on file offsets in `fsread/extfs.rs`: an inode offset near `usize::MAX`
      overflows `o + 128` (two sites), found by a lint scan of `crates/formats` (#42)
- [x] Read extended SquashFS directory offsets correctly (#338). — claimed: Afloat16, branch bugfix/r0.5-squashfs-extended-directory-20261102
- [x] `macho.rs` `method_list`: `list + 8 + i * entsize` adds to a pointer read from the file, so a
      segment that ends at `u64::MAX` overflowed it (found by a lint scan; now reproduced by a
      regression test, and the entry addresses are checked)
- [x] ELF files whose section headers were removed (common in NAS and router firmware, also big-endian
      MIPS) show their dynamic symbols: `elf::dynamic_table` reads `DT_SYMTAB`/`DT_STRTAB` and the count
      from `DT_HASH` or `DT_GNU_HASH` (moved out of `dart.rs`), `Binary` symbols, imports and exports are
      filled from it, `elf::dynamic_symbols` reads versions through `DT_VERSYM`/`DT_VERDEF`/`DT_VERNEED`,
      and the prologue scan walks executable segments (#223)
- [x] Cut external-tool stderr at a character boundary, so a 64 KiB (objdump, rizin) or 16 KiB (rtl_433) cap
      inside a multibyte character no longer drops the whole stderr (#287).

### R0.8 Tests never touch the real machine
Owner: open · Status: done, except protecting `main` (a maintainer setting)
`Session::default()` points at the real config folder and engine store, so a test can read, write
or download into them.
- [x] `Session::isolated(dir)` and `engine::testing::session()`: config, plugin caches, engine store
      and projects in a temp folder; `settings_set` and plugins follow `Session::config_dir()`
- [x] Every test uses it (41 files); `cargo xtask layers` fails on `Session::default()` anywhere
- [ ] Main maintainers: protect `main` (PRs required, squash only)

### R0.6 Tool naming
Owner: maintainers · Status: done
Craft Anything's own ids, grouped by what a person does (`native_functions_list`,
`web_page_capture`…). Each tool answers to its id (and CLI spelling) only.
- [x] Id scheme in `docs/tool-ids.md`: `<area>_<object>_<action>` (no dots: MCP and model APIs
      allow only letters, digits, `_` and `-` in tool names)
- [x] A test keeps every id in the scheme
- [x] **decision** (2026-10-20): rename properly, before launch
- [x] Code decides on a tool's own id and declared effects, never its name as text
      (`Registry::canonical`, `Effects::CARRIES_TARGET_CONTENT`, id constants next to their tools)
- [x] Renamed at the source: 227 tools get their own ids and a duplicate install tool is retired;
      text naming tools uses the ids; each tool's Rust function has its id as its name
- [x] Earlier names retired before launch: tools, MCP prompts and their arguments answer only to
      their own names (2026-10-22)
- [x] New tools (R1.6 onwards) use the new scheme from the start (`project_*`, `engines_*`,
      `settings_*`, `rebuild_*`, `build_*`, `plugins_*`)
- [x] A second naming pass before launch (2026-10-22): 81 tool ids and two MCP prompts get plainer
      names (`adb_apps_list`, `native_function_study`, `web_walkthrough_record`…), tool inputs say
      `function` instead of `procedure`, the error codes are regrouped (`bad_input`, `not_found`,
      `engine_missing`, `over_limit`…; categories say what to do: `input`, `engine`, `missing`…),
      and the rebuild ledger uses its own words (strengths `unit-test` … `outside-check`, cases
      `works`, `refuses`, `bad-input`, `cancel`, `shutdown`)

### R0.7 One live end-to-end rebuild, kept as an opt-in test
Owner: maintainers · Status: done (branch `test/r0.7-live-e2e`; runs on 2026-10-18, Windows 10)
- [x] `craft-anything-cli rebuild https://example.com "Clone this website" --rounds 1` completes:
      Ready in 1.5 min, 96% alike (98% at 1440 px, 94% at 390 px)
- [x] App target: a small desktop app → Rust + egui, Ready in 9 min (checked by "does it build" only)
- [x] Game target: Muck → Rust reached Build (game written and compiled, the builder screenshotting
      its own result) and was stopped on purpose before Check; a polished game isn't the goal.
      It first failed at once because "in Rust" was ignored (fixed in #4)
- [x] Opt-in test (`CRAFT_E2E=1`) that runs the website case
      (`apps/craft-anything-cli/tests/live_rebuild.rs`)

---

## M1 Extensibility

### R1.1 `TargetKind` trait; split `rebuild.rs`
Owner: maintainers · Status: done
Today `enum Kind {Website, Game, App}` is matched in about ten places across `ai/src/rebuild.rs`
(1.5k lines) and the UI.
- [x] **decision** (approved 2026-10-18): `TargetKind` (`id`, `words`, `detect` → score,
      `default_stack`, `named_stack`, `goal`, `brief_sections`, `checks`, `refine`…) and `Check`
      (`id`, `run(CheckCx)` → `CheckResult`) as trait objects in a `KindRegistry`
- [x] Split `rebuild.rs` into `rebuild/{mod,kind,study,check,brief,locate,output,tests}.rs` with
      no change in behaviour (branch `refactor/r1.1-split-rebuild`)
- [x] Website, App and Game become implementations (`rebuild/kinds/`); `RunOptions::kinds` holds
      the registry; briefs proven byte-identical to before across 162 combinations
- [x] The UI reads labels from the trait (`CraftApp::kinds`); the `Kind` enum, `choose` and
      `kind_of` are gone
- [x] Data table for stacks: `rebuild/stacks.toml` (steps, phrases that ask for a stack, engine),
      read by `rebuild::stacks`; game engines' own names stay in `engines::game::Builder`

### R1.2 `Check` (comparator) trait with structured results
Owner: maintainers · Status: in progress (runtime-visual and behaviour checks: R2.4, R2.5)
- [x] `CheckResult { check, passed, similarity, note, artifacts }` replaces
      `note.starts_with("Build succeeded")`; older `craft.json` checks are read compatibly
- [x] Built-in checks: `BuildCheck` (per engine recipe) and `WebVisualCheck` (per width)
- [x] Web routes (R2.3: every captured page is compared)
- [ ] Later checks: runtime-visual and behaviour (R2.4, R2.5)
- [x] Widths, thresholds and rounds come from settings (`[build]`: `good_enough`, `max_rounds`,
      `web_widths`, `max_pages`, `picture_good_enough`); a check may carry its own bar
      (`CheckResult::good_enough`)
- [x] The builder tests its own work during its turn, for every kind: `rebuild_check` asks the
      running build (through `checks/asks/`) to run the same checks as round 0, not counted as a
      round; refusals for an in-process API builder, whose tools hold the engine
- [x] What a check couldn't compare is kept (`CheckResult::unknowns`) and keeps it from being good
      enough: missing evidence never counts as alike
- [x] Claims: a check lists what the build must do, each judged on its own (`CheckResult::claims`);
      one that fails keeps it from being good enough. Websites claim per page: no sideways scroll
      where the original has none, no new errors, every file loads, the original's landmarks; and
      that each of the original's menus and pop-ups opens (`page_claims`)
- [x] A windowed app pictured by runtime study claims each of the original's interactive controls
      (buttons, menus, tabs, check boxes, fields, links; `screenshot::INTERACTIVE`) by label; text
      labels stay advisory, since they may hold content the builder replaces
- [x] Apps and games make claims too: each self-test step of a game (the core loop's, an untested
      one failing, then the game's own) and each number from the original in the mechanics sheet
      being used in the code
- [x] Console apps: with runtime study on, a console original (PE console subsystem) is run with each
      input in `runs::CASES` (no arguments, --help, --version) through `runtime_walkthrough_record` and
      kept in capture/runs/; `RunsCheck` runs the rebuild the same way and claims, per input, the same
      exit and the same output (80% of the words, the programs' own names set aside); the brief asks
      for a console program instead of a picture
- [x] Console originals on Linux and macOS: an ELF or Mach-O executable that loads no windowing library
      (`runs::WINDOW_LIBRARIES`) is taken for one; on every platform, a program that sat silent and
      open through every input is treated as windowed after all and pictured instead (`ran_like_console`)
- [x] The brief is the builder's own loop for every kind: study overview first, focused follow-ups
      with the tools, `app/UNKNOWNS.md`, build, `rebuild_check` until it would pass, then review the
      checklist and unknowns before replying
- [x] The builder's open questions are unknown records (`core_unknown_add` / `core_unknown_edit` /
      `core_unknowns_show` in the project's investigation folder) instead of a markdown file; its own
      check lists the open ones and the finished run says how many are left
- [x] The brief says which toolsets to turn on (`enable_toolset`: browser, javascript, native,
      managed, formats) and, for websites, how to study behaviour with the web debugging tools
      (event listeners, execution, scripted walkthroughs, exported scripts), never pasting the code
- [x] A console original is rebuilt with the "Rust (console)" stack by default (`AppKind::default_stack`
      reads the file); live: a small console tool rebuilt end to end, the builder used `rebuild_check`
      and unknown records, and all 6 run claims held
- [x] Live run where a coding agent uses `rebuild_check` mid-turn on a game: a request-only snake game
      in Rust passed build, picture, mechanics and all 5 self-test claims (2 steps of its own)
- [x] A round's verdict is one line over all its checks and claims (`self_check::summary`), in the
      builder's own check and the finished run's status, not the last check's note

### R1.3 Builder adapter registry
Owner: maintainers · Status: in progress (Codex resume needs a real install)
- [x] `AgentAdapter` trait (`ai::cli_agents::adapters`): ids, args, required flags, stream
      parsing, resume, process setup, sign-in preflight; `AgentAdapters` registry in
      `CliSpec`/`RunOptions`; unknown agents get the plain adapter. The rebuild's Claude-only
      sign-in check now asks whichever adapter runs
- [x] ACP evaluated: it's a long-lived, session-based JSON-RPC protocol, so it fits as another
      `Conversation` implementation (an `AcpConversation` beside `CliConversation`), not as a
      per-turn `AgentAdapter`. Claude Code stays native (unmodified binary, documented flags).
      Follow-up: R2.2
- [ ] Codex: resume support (`codex exec resume <id>`), verified on a real install

### R1.4 Asset provider trait
Owner: open · Status: done (branch `feature/r1.4-asset-providers`)
- [x] `AssetProvider` (image, 3D, later audio) with a cost estimate; fal becomes one impl
- [x] Model ids and prices in a table; prompts read prices from it (today `assets_note` repeats
      "$0.53")
- [x] Default budget as a setting (each project stores its own, but the default is the constant
      `ASSET_BUDGET_USD`)
- [x] Follow-ups from R1.4: Settings → Builds sets the default budget and the picture model; the
      app's "raise budget" adds the setting through `project_assets_budget`; the tally no longer
      shows "$-0.00"; the app's price text comes from the asset table
- [x] Each asset provider its own key: `assets:<id>` in the key store, `AssetProvider::key_env`,
      `AssetKeys` in the builder's tool server, `provider` on the `assets_key_*` tools
- [x] Settings → AI shows a key field for each asset provider (`AssetProvider::keys_page` gives
      its "Get a key" link; the app keeps which providers have a key, by id)
- [x] Check the FLUX schnell price in `assets.toml` against fal's current list: FLUX schnell
      $0.003/MP, FLUX dev $0.025/MP, Tripo P1 $0.40 / $0.50 textured all match (2026-10-19)
- [x] Game assets are the person's choice: a per-project opt-in (`generate_assets` in craft.json,
      the switch on Make and on the project, `project_assets_allow`, `rebuild --generate-assets`
      and `rebuild_start`'s `generate_assets` for the CLI and MCP) that the brief and the asset
      tools need along with a key; turning it on without a fal.ai key asks for one; Nano Banana Pro (`fal-ai/nano-banana-pro`, $0.15 a picture, checked 2026-10-20) is the
      default picture model, and the table prices per picture or per megapixel
- [x] A run no longer overwrites what the person changed while it builds: the fields they own
      (asset budget, generated assets, always-allowed actions) change only through
      `Workspace::set_person`, and every other save keeps them as they are on disk. The app's
      asset switch works during a build again
- [x] A resumed builder hears the asset choice as it is now: `TargetKind::follow_up_sections`; a
      game's follow-up carries the asset note (budget, spent) when assets are on with a key, or
      says they're now off when some were made before
- [ ] Run Nano Banana Pro once with a real key (a picture, then a 3D model from it) and check the
      picture's size and the invoice ($0.15)
- [ ] fal bills pictures "by rounding up to the nearest megapixel"; estimates use the exact size.
      Confirm on a real invoice whether a 1024×1024 picture bills as 1 or 2 megapixels, then round
      in the table (needs a key)

### R1.5 External engine trait in L3
Owner: open · Status: in progress (branch `feature/r1.5-engine-table`: table and pins done; transports pending)
- [x] One engine table drives `KNOWN`, `ToolPaths`, install pins and the Engines settings page
      (`engines::ENGINES` in `engines/src/table.rs`; a test keeps `tool_paths!` identical to it)
- [x] Install pins: SHA-256 for every download; tar.gz/tar.xz (TODOs in `install.rs`)
      (adb r37.0.1 on all three desktops, JADX 1.5.6, Ghidra and its Windows Java; tars unpack
      in memory up to 512 MB)

Pending changes:
- [x] Move the CDP client from `engine/src/tools` (L4) to `engines` (L3) (`engines::cdp`; `CancelToken`
      now lives in `platform::cancel`, re-exported from the engine)
- [x] Move the GDB and JADX transports from `engine/src/tools` (L4) to `engines` (L3) (`engines::gdb`:
      the MI session; `engines::jadx`: the single-class run)
- [x] Single-file pins (`ArchiveFormat::File { name }`, found by `locate` under that name in the
      engine store); Vineflower 1.12.0 is pinned with it (Maven Central's SHA-256, the same as the
      GitHub asset digest), and Apktool 3.0.3 (GitHub asset digest); a located `.jar` runs with the
      configured Java (`external_disasm_tools::program_for`)
- [x] Temurin Java 21 pinned for Linux and macOS (x64 and arm64; Adoptium's `.sha256.txt`, the same
      as the GitHub digests); macOS archives are stripped to `Contents/Home`, so Ghidra's setup
      (`ghidra::get::can_install`) now works there too
- [ ] Ghidra setup tried for real on Linux and macOS (the Java pins were checked by tests only)
- [x] Rizin 0.9.1 pinned for Windows x64 (the static zip; GitHub asset digest), installed for real
      by the opt-in `a_pinned_engine_installs_for_real` (`CRAFT_ANYTHING_TEST_INSTALL`)
- [ ] More pins once their hashes are checked against the publisher: Chromium (no published
      checksums found yet), Rizin for Linux (the tar.xz unpacks to ~800 MB, so it needs streaming
      extraction) and macOS (a .pkg)

### R1.6 Headless first: the GUI stops being the glue
Owner: maintainers · Status: done
The rebuild run itself lives in `ai::rebuild` and the CLI uses it, but the GUI still owns parts of
the product that a headless run doesn't get:
- **Project feed:** `feed.json` is written and rebuilt only by `ui-egui/src/project.rs`
  (`load_feed`, `save_feed`, `history`), so a CLI run leaves no feed and the app can't show it.
- **Game engine and Ghidra setup:** inventory, downloads and guided installs run from
  `ui-egui/src/engine_ui.rs` (calling `engines::game` and `engines::ghidra` directly).
- **Launching and previewing results:** `project.rs` and `engine_ui.rs` start programs with
  `std::process::Command` and manage the preview server.
- **Decisions in the view:** target kind and stack (`rebuild::choose`, `kind_of`) and asset
  readiness are worked out in `make.rs` and `project.rs`.
- **CLI is missing:** list/show projects, answer the inbox, follow-ups on a finished project,
  engine installs, play/preview, settings get/set.

Pending changes:
- [x] The project feed moves to `ai::rebuild::feed` (versioned `feed.json`); `RebuildRun` writes
      it (events, the person's messages and notes, answers), so CLI runs keep it too; the app only
      shows it
- [x] Projects as tools (`Projects` toolset): `project_list`, `project_show` (status, checks,
      waiting questions, paged conversation), `project_inbox_answer`; the feed's data and file
      live in `engine::feed`, the run's folding in `ai::rebuild::feed`
- [x] Follow-ups and rebuild control as tools (`rebuild_start` with pictures, `rebuild_status`,
      `rebuild_note`, `rebuild_note_withdraw`, `rebuild_stop`), registered from the AI layer (R1.7);
      the CLI's `rebuild` and the tool share `rebuild::project::new_project`
- [x] A note sent while Claude Code builds reaches it at its next step, not after the turn: the run
      leaves it in `inbox/notes/`, a PostToolUse hook (`--settings`, `craft-anything-cli
      builder-notes`) claims it and hands it to the model as context, and the run shows it as read;
      unclaimed notes still go in after the turn (`rebuild::notes`)
- [ ] The same for other coding agents with tool hooks, and for the API-backend loop (between tool calls)
- [x] Engines and settings as tools (`Setup` toolset): `engines_list` (external engines, Ghidra,
      game engines and readiness), `engines_install` (Ghidra, Godot, pinned engines, with
      progress; Unity/Unreal get their download page), `settings_show`, `settings_set`
- [x] Find registered Linux Unreal installations and their bundled Clang toolchain; support an
      explicit `UE_ROOT` ([PR #191](https://github.com/storytold/craft-anything/pull/191))
      — claimed: one-bit, branch `bugfix/r1.6-linux-unreal-detection`
- [ ] Give Linux-specific Clang guidance in Unreal's guided installer when the bundled compiler
      is missing (the requirements summary is already platform-specific).
- [x] The app's Godot, Unity/Unreal installer and Ghidra flows, and its play, preview and
      open-folder buttons, call the tools (`CraftApp::act`); inventory reads stay in the UI
- [x] Launch, preview and open-folder as tools: `project_play` (needs consent: it runs the
      builder's code), `project_preview` (loopback; `wait` serves until cancelled),
      `project_open_folder`; what a build produced lives in `engine::outputs`
- [x] Setup and doctor as tools (`setup_plan`, `setup_apply`, `setup_doctor`, `setup_uninstall`,
      registered from the setup crate; changing other apps' configs asks first)
- [x] Tools for the fal.ai key (`assets_key_status`, `assets_key_set`, `assets_key_remove`, from the
      AI layer; the journal redacts secret-named fields) and a project's asset budget
      (`project_assets_budget`)
- [x] CLI `rebuild --build-with <engine|stack>` (the app's "Build with"; `stacks::resolve`)
- [x] Headless runs use the game's own engine: `GameKind::default_stack` detects it (Unreal,
      Godot) from the target, as the app's Make screen does
- [x] CLI: `project-list`, `project-show`, `project-inbox-answer` (from the tools)
- [x] CLI: `engines-list`, `engines-install`, `settings-show`, `settings-set` (from the tools)
- [x] CLI: `project-play`, `project-preview --wait`, `project-open-folder` (from the tools)
- [x] Headless test: every UI action maps to a tool id or CLI command
      (`ui-egui/tests/headless_parity.rs`: covered, pending with the roadmap reason, or UI-only;
      every `CraftApp` method must have a row; checked in CI later)
- [x] `cargo xtask layers`: `ui-egui` may not use `std::fs` writes or `std::process` directly
      (`ui_has_no_side_effects`, with a baseline allowlist of today's offenders that can only shrink)
- [x] Empty that allowlist: report export (`core_report_save`) and opening Unity Hub or the Epic
      Games Launcher (`engines_app_open`) go through tools; the UI now writes no files and starts no
      programs itself

### R1.7 Dynamic tool registry
Owner: maintainers · Status: done
`ToolSpec` is `&'static` with fn pointers and the registry is fixed at build time.
- [x] Higher layers register their own (static) tools: `Engine::shared(session, extra)`, with an
      `EngineRef` in the session so those tools can reach the engine; the apps pass
      `craft_anything_ai::tools()`
- [x] Tools defined at run time: `registry::RuntimeTool` (owned names, a JSON schema, a function
      that tells its tools apart by `Ctx::tool`), via `Engine::shared_with`;
      `Registry::input_schema` serves every client the right schema
- [x] Toolsets are open: `Toolset::Custom(id)` (`registry::custom_toolset`), and
      `Registry::toolsets()`/`toolset(id)` replace `Toolset::ALL` in MCP, the CLI and the agent

### R1.8 Plugins
Owner: maintainers · Status: done
- [x] Phase 1: external MCP servers as toolsets: `[[plugins.mcp]]` in config.toml,
      `engines::mcp_client` (stdio JSON-RPC through `platform::process`), cached tool lists
      (`plugins_refresh`, `plugins_list`), servers started on first call, effects from the
      server's annotations, consent by default, results as outside-service evidence
- [x] Settings → Plugins lists `[[plugins.mcp]]`, turns each on or off and reads its tools
      (`plugins_refresh`); adding one is still done in config.toml
- [x] MCP servers over Streamable HTTP (`url`, `headers`; JSON or event-stream replies, session
      id); `mcp_client::Transport` for other transports
- [x] Adding a plugin from Settings: `plugins_add` and `plugins_remove` (CLI and MCP too); a plugin
      added this way always asks before each call; the app re-reads the list after the tool runs
- [x] **decision**: wasmtime with a WIT interface, behind the off-by-default `wasm-plugins` build
      feature (it's a large build)
- [x] Phase 2, tools: `[[plugins.wasm]]` components exporting `craft-anything:plugin/tools`
      (`crates/engines/wit/plugin.wit`: `describe`, `call`, JSON strings). They import nothing (no
      files, network, environment); each call is a fresh instance with a fuel and 256 MiB memory
      limit, so their tools run without asking
- [x] **decision**: plugin checks get the build as JSON (every file's path and size, plus the text
      of the extensions they ask for); asset providers stay out of plugins (they'd need the network)
- [x] Phase 2, checks: `craft-anything:plugin/checks` (`describe` with kinds and extensions, `run`
      on the build JSON → passed, similarity, summary), run after a kind's own checks; a plugin that
      fails to run passes with a note instead of failing the build
- [x] WASM plugins: Settings → Plugins lists, adds (a `.wasm` path), turns on or off and removes
      them, `plugins_add`/`plugins_remove`/`plugins_list` take both kinds (`wasm`), and
      `cargo xtask ci` lints and tests the engine with `--features wasm-plugins`
- [x] WASM plugins: `examples/wasm-plugin-wordcount` (Rust, wit-bindgen 0.63,
      `wasm32-unknown-unknown`, `wasm-tools component new`), built and loaded through the host
      (opt-in test `CRAFT_ANYTHING_TEST_WASM_PLUGIN`)
- [x] Plugin API versions: semver for `package craft-anything:plugin@…`; the host finds a plugin's
      interfaces by name and accepts any compatible version (same major, and same minor while 0.x),
      refusing others by name; patch versions only add optional JSON fields (docs/extending.md)
- [x] A check plugin in Rust: `examples/wasm-plugin-readme-check` (does the build's README say how
      to run it), built and loaded for real (opt-in test `CRAFT_ANYTHING_TEST_WASM_CHECK`)
- [x] `docs/extending.md`: how to add a tool, a target kind, a check, a builder or a plugin

### R1.9 Versioned files
Owner: open · Status: done (branch `feature/r1.9-versioned-files`)
- [x] `craft.json`: `version` field, JSON schema (schemars) published in `docs/schemas/`
- [x] `config.toml`: version field and migration hook
- [x] `.cany` `FORMAT_VERSION`: migration function stub and test

---

## M2 Product completeness

### R2.1 Building with API-key backends
Owner: maintainers · Status: in progress (built; live runs need keys)
- [x] Include successful context-summary calls in message usage, build cost and the model-turn journal (#272).
- [x] File and command tools for our own agent (`Build` toolset): `build_files_list`,
      `build_file_read`, `build_file_write`, `build_file_edit`, `build_command_run`, in the session's
      workspace, through `platform::process` and the same approval policy as Claude Code builds
      (`interaction_tools::approve`)
- [x] `RebuildRun` accepts Anthropic, OpenAI, OpenRouter and local backends: our agent loop with
      the Build toolset (`AiHub::start_builder`, up to 400 steps a message), Build tools' consent
      answered by the run, follow-ups continue the kept conversation (`transcript.json`); the builder is
      the named backend, else the Builder role, else an agent app, else any enabled AI backend
- [ ] A live API-key build (needs a key on the test machine)
- [x] Kimi K3 through OpenRouter (`moonshotai/kimi-k3`, offered by Detect with a pasted key, priced
      at OpenRouter's list price), and choosing who builds: "Build with this" in Settings → AI and
      `ai builder <name>` set the Builder role, which the app now honours before an agent app
- [x] An extraction step for Deep-mode game rebuilds: a backend chosen for the Extractor role ("Extract
      with this", `ai extractor <name>`; an API backend such as Kimi K3) takes the game's own files
      out into `app/Original/` after the study, with the game archive tools, and lists them in
      `app/Original/MANIFEST.md`; the builder is told to use them. A failed extraction says why and
      the build goes on
- [ ] A live extraction run with Kimi K3 (needs the person's OpenRouter key)
- [x] A checklist tool for API builders: `build_checklist` (TodoWrite's shape), shown pinned like
      Claude Code's checklist
- [x] Context management for long builds (`ai::context`): past the budget (150k input tokens,
      24k for local models, `LoopConfig::context_tokens`) old tool results are trimmed, then the
      oldest part is replaced by a summary the model writes; the conversation is kept in
      `transcript.json` after every step and a follow-up resumes it
- [x] Only an OpenAI-compatible server on this computer or its network counts as local (24k
      context, no cost); a remote one gets the cloud budget and its price (#374)
- [ ] A per-backend context budget in `[[ai.backends]]` (`LoopConfig::context_tokens` exists), for
      services whose real window differs from 150k (#374)
- [x] A project moved to another computer (or folder) keeps building with Claude Code: when the saved
      `agent_session` isn't there (`Conversation::session_lost`), a fresh session starts from the brief,
      the builder's last summary and what's in `app/` instead of failing; questions about the build put
      the kept session back first, else are answered from the files and forget the missing one (#452)
- [x] The coding agent's conversation travels with the project folder (#451): after every turn the
      project keeps a copy of Claude Code's session (`agent-session.jsonl`, `AgentAdapter::session_file`);
      on a computer without it, the copy is put back where Claude Code finds it (`restore_session`) so
      the same session carries on, and if that fails the new session is handed the kept requests and
      replies (`handoff`, up to 16k characters)
- [ ] A live run of a project copied between two real computers with Claude Code (#451, #452); done on
      one Mac with a second `CLAUDE_CONFIG_DIR` standing in for the other computer (STATUS.md)
- [ ] Session copies for other agents that keep sessions (ACP agents' `session/load`) (#451)

### R2.2 More coding agents
Owner: open · Status: in progress
- [x] `AcpConversation`: chat with agents that speak ACP (`cli_agents::acp`; agents and their ACP
      arguments in `ACP_AGENTS`: Gemini CLI, Qwen Code, opencode, goose, Hermes, Maki). Opt-in per backend
      (`acp = true` in its options); one agent process per chat, permission requests become
      consent questions, sessions continue with `session/load`
- [x] Builder runs over ACP: with `acp = true`, rebuild runs use `AcpConversation`; the agent's
      permission requests go through the approval policy (`interaction_tools::approve_with`:
      allowed, refused, or asked through the project's inbox; Auto mode honoured)
- [ ] Gemini CLI, opencode, goose via ACP or native adapters; each verified live, then turn ACP on
      by default for the ones that pass
- [ ] **decision** One approval behaviour across agents, and whether we want an auto-approve mode
      apart from Clean room and Deep (Auto mode only governs what's asked through us). Today it
      differs by agent: Claude Code asks our approval tool; OpenCode's builder runs with `--auto`;
      Hermes's `-z` turns its approvals off on every run, chats included. Clean room's approval
      rule doesn't reach an agent that never asks us
- [ ] Say on each adapter, as typed data, what it can be held to (asks us, its own sandbox, nothing),
      and have runs act on that, once the decision above is made
- [ ] Check live what Hermes over ACP asks about: whether its file reads reach our approval policy
- [x] Maki as a coding agent: one message per `maki -p`, and over ACP (`maki acp -m <cli_model>`);
      run live as an ACP builder (a page to Ready, a follow-up continued with `session/load`, its
      requests refused unattended with Auto mode off)
- [ ] Over ACP, a continued session shows the earlier conversation again: `session/load` replays it
      as `session/update`s, which we show as new; drop updates until the load answers
- [ ] Over ACP, turns report 0 tokens: the protocol sends only `usage_update` (context used and
      size). Read real counts where an agent keeps them (Maki: `token_usage` in its session file
      under `~/.local/state/maki/sessions/`) or say the count is unknown instead of 0
- [ ] Maki's plain `maki -p` builder doesn't ask us before commands, and in Clean room its reads
      aren't checked (as with every agent that never asks us): say so in the approval decision
      above, or run Maki over ACP by default once that passes. Outside a build, tools the person
      allowed in Maki's own permissions (an MCP server's, or all of them with `always_yolo`) still
      run; the adapter can't see that config
- [ ] Maki over ACP writes inside its working folder without a permission request (its built-in
      rule), and that folder is a build's project folder, so writes to our own records (inbox,
      manifest) skip the approval policy; `maki acp` takes no tool flags to stop it (0.7.0). Start
      it in `app/` (paths in the prompt relative to that), or ask Maki for a way to make those
      writes ask; part of the approval decision above
- [ ] Codex, Gemini CLI, OpenCode, Hermes, Maki and the plain adapter still take the message in
      argv, so a long one can pass Windows' command-line limit as Claude Code's did (#402); hand
      each its message on stdin or in a file where its CLI reads one

### R2.3 Website coverage and a better visual metric
Owner: open · Status: done
- [x] Study: up to 4 same-site pages from the start page's links, each captured into
      `capture/routes/<page>/` (`capture/routes.json`); the brief asks for each at the same path
- [x] Study: open menus, dialogs and tabs; record states (`web_page_states_capture`: up to 4 on the start
      page, pictured in capture/states/ and listed in the brief; never form controls)
- [x] Study: links more than one level deep (pages linked from the captured pages fill the rest of
      `build.max_pages`; `pick_deeper_routes`)
- [x] Perceptual metric next to tile similarity: `perceptual_similarity` (mean SSIM of
      brightness, own code) in `web_pixels_compare`; a website check's likeness is the mean
      of layout and detail, both shown in its note
- [x] Check: every captured page compared on the build at the same path; the likeness is the
      mean over pages, each page's score in the note (live: info.cern.ch, 95% + 83% → 89%)
- [x] Check: interaction states (the build's menus, pop-ups and tabs opened like the original's, paired
      by kind and label, pictures compared) and structure (`structure_likeness`: landmarks, headings,
      lists, media and controls in order, missing parts named); both in the note, the score stays visual
- [x] Check: text/token diff with the original's missing headings and words (`text_likeness`;
      in the check's note and the builder's refine message; the score stays visual)
- [x] Report: per-route likeness on the project page (`CheckResult::pages`; a page is picked to see its pictures)
- [x] Stacks and libraries named in a request reach the builder: a Next.js stack (static export to
      app/out) and a `[[library]]` table in `stacks.toml` (shadcn/ui, Tailwind CSS) whose steps join
      the stack's; phrases match the request's words, so "Next.js", "nextjs" and "next js" all count
- [x] A website whose request names no stack leaves it to the builder ("Builder's choice", told to
      match the original's); the stack it used is recorded from app/package.json (`stacks::used_in`)
- [x] Fidelity at every width: Study and check use the same widths (default 1440, 768, 390);
      `web_site_capture` records CSS breakpoints, spacing and content widths, hex colours, font
      files and the layout at each width; menus are also opened at the phone width; the check's
      note names missing colours, fonts, text sizes and spacing, sideways scrolling, heading sizes
      and per-section padding, items per row and content column (`design_notes`)
- [x] Page health: `web_site_open` reads script, console and log errors and failed requests (400+,
      failed loads) from the browser's events (`page_health`, no query strings); `web_site_capture`
      records them with an accessibility outline (language, landmarks, unnamed controls, pictures
      without alt); the check names what the build adds (`health_notes`, failing paths compared)
- [x] Parts that change by themselves aren't compared: Study photographs each width three times at
      uneven gaps (`web_site_capture` `noise_pass`) and keeps the moving squares as noise-<width>.png;
      `web_pixels_compare` `ignore` leaves them out of layout and detail (`NoiseMask`,
      `block_similarity_masked`, `perceptual_similarity_masked`), and the website check passes it
- [x] Live clone (2026-10-21) of a fixture page of our own with known values at three breakpoints
      (type 48/36/28, padding 64/48/32, a 1100 px column, 3/2/1 cards per row), in Next.js +
      shadcn/ui, 2 rounds: Ready, 96% alike (97/96/95% at 1440/768/390 px), page heights equal.
      The build matched every measured value exactly, so the thresholds (4 px padding, 2 px type,
      8 px column) stay: no note fired from noise. It found two real faults, fixed: sections were
      paired by heading only, so a section the builder renamed (as it must) was never compared,
      and now pairs by tag in page order; and a nav's link count read as "items per row" (a link
      under 40 px was dropped) and gave a false note, so per-row isn't compared for nav or header
- [ ] Thresholds under pressure: a clone that's off by a few pixels (a page with fluid type or
      `clamp()` spacing) to see whether 4 / 2 / 8 px is too strict

### R2.4 Runtime study for apps and games (with consent)
Owner: maintainers · Status: in progress
- [x] Window screenshots: `platform::window` (xcap) and the `native_window_capture` tool (start,
      wait, picture the largest window of the process or its app, close; consent required); Study
      saves `capture/window.png` when the `runtime_study` setting is on (off by default); the
      screenshot check compares the rebuild with it too; the CLI is DPI-aware on Windows
- [x] UI tree on Windows and macOS: `runtime_ui_read` reads UI Automation on Windows (a PowerShell
      script we ship; role, title, id, value, class, position; never password values) as well as
      the macOS accessibility tree; `Requires::Os` names the hosts a tool runs on
- [ ] UI tree on Linux (AT-SPI)
- [x] Scripted UI steps on Windows: `runtime_ui_walkthrough_record` presses, expands, collapses,
      toggles, selects or focuses controls by title or id through UI Automation (no mouse or
      keyboard) and records the tree before and after; each step reports its outcome
- [x] Study saves the original's UI tree next to `capture/window.png` when runtime study is on
      (`native_window_capture` `ui_tree`, read just before the program closes; `capture/ui-tree.json`,
      pointed to in the capture README)
- [x] A Settings control for `runtime_study` (Safety → "Study apps by running them")
- [ ] Window capture tried on macOS and Linux (only Windows so far); games behind a launcher
- [ ] Short scripted input sessions (enigo) to record screens of the original
- [x] Same capture of the rebuild: with runtime study on, the screenshot check also starts the build
      normally and pictures it like the original (`checks/round-<n>/window.png`, `ui-tree.json`);
      the note says how alike the windows look and names the original's labelled controls the
      build lacks (`controls_likeness`); advisory, the score is unchanged

### R2.5 Behaviour checks for non-web builds
Owner: open · Status: in progress
- [x] Standard `--screenshot <path>` contract in every app and game brief, enforced by
      `ScreenshotCheck` after the build check (no picture, an unreadable or blank picture fails);
      checks run in order and a failed one stops the rest
- [x] Compare against the person's reference pictures: the closest PNG's likeness is in the note
- [x] Let picture likeness decide: with `build.picture_good_enough` set, the screenshot check's
      likeness has that bar and refining continues until it's met (unset: reported only)
- [x] Compare JPEG, WebP and GIF reference pictures too (`web_common::decode_picture`)
- [x] `MECHANICS.md` gains a structured twin (`app/mechanics.json`, `engine::mechanics`, schema in
      `docs/schemas/`): `MechanicsCheck` fails a game without a readable sheet and notes values
      without a source and numbers not in the code as written
- [x] Apps in Deep mode keep the sheet too: the brief asks for it when a program target is
      decompiled, and `DeepOnly(MechanicsCheck)` checks it only then (`Check::applies`)
- [x] Honest game checks (a Deep-mode Unreal rebuild reached Ready as a first slice: a cave, no
      player, enemies, mission or HUD): every game brief asks for `--self-test <file.json>` (play
      the core loop with scripted input, measure it from the game's own state) and
      `SelfTestCheck` runs it after the screenshot, failing until `move`, `act` and `hud` all pass;
      `MechanicsCheck` fails when a sourced number isn't in the code as written (estimates may
      stay out; Unreal's generated folders aren't read as code); in Deep mode on a program,
      `DeepOnly(CreditsCheck)` requires `app/CREDITS.md` and `app/README.md` opening with the
      brief's private-use line
- [ ] Behaviour checks that use the sheet: run the build with scripted input and measure values
      (speed, jump height, fire rate) against it (needs R2.4's scripted input)
- [ ] Hold the self-test to what the check can see too: picture the game after its scripted
      input and require it to differ from the `--screenshot` picture (a report alone is the
      build's own word)
- [x] Publish the self-test report's schema in `docs/schemas/`: `engine::self_test` owns the
      report's types, `cargo xtask schemas` writes `self-test.schema.json`

### R2.6 Several rebuilds at once
Owner: open · Status: done
- [x] More than one `RebuildRun` per window: `rebuild::RunSet` runs up to `build.parallel` (Settings →
      Builds) and queues the rest, for the app and the rebuild tools alike; events come by project
      folder and a building project's feed is taken from its run (`feed_now`)
- [x] Start queued builds from MCP without waiting for the next rebuild tool call:
      `rebuild::keep_queue_moving` polls the tools' `RunSet` every 2 s while builds wait
- [x] A UI test with stand-in runs: `rebuild::StandIns` makes runs without a builder; the smoke
      test queues a second project and follows it on screen until it starts

### R2.7 The request decides how to build
Owner: open · Status: in progress
"Build it in Electron" was built in Rust: the brief gave the kind's default stack as a firm
instruction after the request, and the app, the build check and Play followed the recorded stack.
What the person asks for comes first, in every kind; the stack table is only the default.
- [x] The brief puts the request first: a rule says what it names (a language, framework, engine,
      library or platform) wins, and the kind's stack is given as "How to build it, unless their
      request says otherwise"; a website's default no longer says to copy the original's stack
      over the request, and its refinements no longer say `npm run build`
- [x] The build check, the recorded stack and Play follow what was built in app/: an engine's own
      build runs only for its project, a non-engine stack is re-recorded from package.json after
      each turn, and an Electron app opens in the Electron it installed (and is never a website)
- [x] Make: a game engine is required only when the person picks one or the request names none
      ("Built with Electron, as you asked, so no game engine is needed")
- [x] Electron in the stack table (asked by name, recorded from package.json, with steps that fit
      the build check, Play and --screenshot). Live: "A small notes app in Electron" was built in
      Electron and reached Ready with both checks passing
- [ ] Screenshot check: in that live run the final check once got no picture from the Electron app
      within 90 s while the same check passed in the builder's turn and on a re-run; not
      reproduced. The app waited on animation frames, which a window behind others may not get;
      the Electron steps now say to capture after loading instead
- [ ] Make: a game whose request names a technology the stack table doesn't know (Phaser, Bevy…)
      still needs the default engine installed to start, though the builder is told to use what
      was named; ask the person, or let such a game start without an engine
- [x] Build check: a page asked for in plain HTML and CSS has nothing to build, and the check
      failed it for having no manifest, so a builder added a placeholder package.json to pass. A
      static site, as the preview finds it (`site_dir`), now passes as it is unless its page is
      blank or a game engine's project sits beside it, and says nothing was built (#496)
- [x] CLI: after the tool name, `--project` is the tool's own option when it has one
      (`rebuild-check --project <folder>`, `project-show --project <folder>`), as `--format` is;
      otherwise, and always before the tool name, it's the global investigation folder

---

### R2.8 Clean room means clean room
Owner: maintainers · Status: done (branch `feature/r2.8-clean-room`)
**decision** (2026-10-23, maintainers): Clean room never looks inside the original. Only Deep mode
reads its code, files or page source, with our own engines and with Ghidra when it's installed.
Deep mode is its own switch, not tied to Ghidra.
- [x] Deep mode as its own setting (`deep_mode`, config.toml version 2 moves `engines.ghidra.enabled`
      there); Ghidra is used in Deep mode when it's installed
- [x] A table of the tools Clean room allows (no target, or watching from outside: the visible
      website, screenshots, pictures of a window, recorded runs, the screen's controls); every other
      tool is refused in Clean room, everywhere (app, CLI, MCP, agents), pointing at Deep mode
- [x] Clean room website capture keeps what a visitor sees: screenshots, visible text, measured
      layout, colours, fonts and spacing, menus opened; no HTML, CSS rules, scripts, requests or
      script errors
- [x] Clean room builds: the study reads nothing inside an app or game (pictures, the person's
      description, and watching it run when Settings allows); the builder can't read the original's
      files, fetch its pages or run commands on it (its Read, Glob and Grep go through the approval
      policy); briefs say so
- [x] App: Just look inside, Game files and the Advanced workbench ask for Deep mode in Clean room;
      the mode switch explains both modes
- [x] CLI `--deep` for one run; MCP lists only Clean room's tools in Clean room
- [x] Deep mode uses every tool: the builder sees them all (`--all-tools`, every toolset for API
      builders), a website's study also reads its JavaScript and watches its start page
      (capture/how-it-works.md), and briefs name the tools for each kind of target
- [ ] A live Clean room build of a website and of an app, checked end to end
- [ ] A remote (SSH) builder needs a craft-anything-cli that knows `--deep` and `--clean-room`:
      check its version first and say so when it's older
- [ ] A remote (SSH) builder doesn't get the time limits or effort set through `Process::env`
      (`MCP_TOOL_TIMEOUT`, `CLAUDE_CODE_EFFORT_LEVEL`…): they're set on the local `ssh`, which doesn't
      pass them on. Set them in the remote command
- [ ] Failure logs for the other ways an AI stops (API backends, MCP server start-up), like the
      ones agent CLIs write to `logs/` in the config folder

### R2.9 Everyday use: typing, projects, settings
Owner: maintainers · Status: in progress
Gaps found while using the app for real projects.
- [x] Up at the start of the prompt box takes back the last note still waiting for the builder,
      to edit it (as the x beside it does)
- [x] With nothing waiting, Up and Down in the prompt box cycle through previous prompts, as in a
      terminal: a project's are read from its feed, so they survive a restart, questions come
      back starting with `/btw` so they stay questions, Down past the newest returns what was being
      typed, and the assistant's box does the same
- [x] Up and Down only cycle prompts from the very start or end of the text, and move the cursor
      otherwise, so a prompt of several lines can be walked through line by line
- [x] Slash commands in a project's prompt box: `/btw` asks about the build in place of the old
      `?` prefix; a new one is a `slash::Command` and a row in `COMMANDS`. A mistyped command stays
      in the box rather than starting a build; a path like `/usr/bin` is a plain message
- [x] Typing `/` lists the commands, and Tab completes one
- [x] Questions about a build show in the conversation where they were asked, so a long answer
      scrolls with it and leaves the prompt box alone; each folds to one line, and they're kept in
      the project (`questions.json`, the newest 200, `rebuild_questions_list`), in their place
      among its prompts for Up and Down
- [x] A folded sidebar stays lined up with the open one: its button is centred over the row
      icons, its sections keep their height, so nothing moves when it folds, and a rule takes the
      place of each heading, with Refresh and the Pinned arrow still there
- [ ] A prompt brought back with Up keeps its pictures (only the text comes back now)
- [x] The smoke test `a_game_project_shows_its_asset_spending_and_can_raise_the_budget` failed
      once in a full run and passed in the next 11: wait for `a.facts.assets.0 == 1` instead of a fixed frame step
- [x] The prompt box no longer jumps while typing: a frame laid out with its old height is
      thrown away and laid out again before it's shown
- [x] A message sent to a project waiting its turn stays in the box instead of being lost
- [x] Several project folders: list projects from any number of folders, and start a project in
      a folder the person picks, which may already have files; ask whether those files are the
      app to edit in place or material to start from, with "don't ask again" in Settings
      (`Workspace::create_at`, `project_folders`, `existing_files`, `rebuild --project-folder
      --existing`, `rebuild_start`'s `project_folder`; craft.json version 2, config.toml version 3)
- [ ] A live build in a picked folder each way (edit in place, start from), checked end to end
- [x] Start sits below the fold on the Make screen at common window heights (900 px)
- [x] The project list notices projects added, moved or removed on disk (on focus, and a Refresh)
- [x] Rename, delete and duplicate a project (`project_rename`, `project_duplicate`, `project_delete`:
      a delete keeps the person's own files, and a copy leaves out dependencies and build output)
- [x] Remove or turn off an AI from Settings (`ai on`/`ai off` in the CLI); a pasted key isn't
      kept in the app after it's added
- [x] Simple mode keeps the Project screen in Advanced mode too, so builds and approvals stay in sight
      (the workbench is a screen beside the projects: a Workbench row in the sidebar, a Projects
      button on the workbench)
- [x] One answer to "can it build?" (`craft_anything_ai::default_builder`: Make's warning and
      the builder chosen agree), and a setup dialog with what was found, Look again and API keys
      instead of "Got it"
- [x] "Built by" on Make: every AI that can build, by name, even when one is set up and builds
      by default; a pick stays with the project (`craft.json` `builder`, also from `rebuild
      --backend` and `rebuild_start`), and its later changes are built by it while it's on
- [ ] Change a project's builder from its page (a tool, so the CLI and MCP can too)
- [x] Settings are saved after typing stops (one save at a time), and path fields keep spaces
- [x] No file reads while drawing: the project's outcome, reference pictures, screenshots and
      side panel come from a worker when something changes (at most once a second)
- [x] Making a project and copying pictures (of the original, or attached to a message) run on
      a worker, not on the click
- [x] A build repaints the window when it has news instead of a 10-a-second timer; animations
      run at 15 frames a second, and once a second while the window is in the background
- [x] The feed isn't copied every frame and a paragraph is one label, not one per word;
      screenshot thumbnails are scaled down and dropped when another project opens
- [x] The "Working" row's clock counts from the build's start instead of restarting whenever
      it reappears
- [x] Stop on the Ask screen stops only its own answer, not downloads and builds, and "Working on
      your answer" shows only for it
- [x] Opening another target starts a new conversation, so answers about two things don't mix
- [x] Closing the Ghidra question without downloading means the project doesn't start later; one
      that waits for the download starts as it was when Start was pressed
- [x] Make's Clean room / Deep choice says it's the app's setting, not the project's
- [x] A project that needs an answer says so in words in the sidebar, and the taskbar flashes when
      a build asks something while the window is behind others
- [x] One Pause (in the prompt box); the plan card carries the clock instead of a second Working
      card; Progress shows where a paused build stopped, and its steps have names for screen readers
- [x] App or game is the tile picked (and a project's engine), not whether the path is a folder
- [x] The website dialog's field is ready to type into
- [x] Typed drafts survive a restart, and each project keeps its own unsent text
- [x] Narrow windows: the sidebar folds to icons (by itself below 900 px, or by its button) and the
      project's side panel moves into "Project details" above the feed below 860 px
- [x] Messages float over the bottom of the window instead of pushing the screen up; errors stay
      until dismissed, so a later message never hides one
- [x] Simple-mode text is 12 pt or more (captions, buttons, the title bar, Progress)
- [x] The Language menu shows once there's a second language
- [x] French UI (`fr.tsv`, Settings → General → Language); a test checks every translation keeps its
      `{placeholders}`; `--lang fr` on the snapshot example
- [x] Simplified and Traditional Chinese UI catalogs, system-locale selection and translated
      tool-title search; catalog integrity, coverage checks and isolated language-switch tests
      ([localisation](localization.md))
- [ ] A Simplified Chinese README (`README.zh.md`) translated from `README.md`, linked from the
      language switcher in `README.md` and `README.ja.md` — claimed: maple323, branch docs/readme-zh
- [x] A Korean README (`README.ko.md`) was translated from `README.md` and linked from the
      language switcher in every README
- [ ] `README.ja.md` is behind `README.md`: the whole Craft App Suite section is missing, so the
      Japanese translation needs a catch-up pass
- [x] First run sets up who builds, not only who answers, and no longer says the purpose is saved
      with projects (it stays on the computer); its Back has a name for screen readers
- [x] An error whose fix quotes a command (`claude auth login`, `codex login`) offers to copy it,
      instead of the app matching Claude Code's English wording
- [x] A consent card's id is a short number, with the call it stands for kept in memory, not the
      call serialised into the id
- [x] The workbench's list isn't copied every frame (it can hold thousands of rows)
- [x] Simple-mode text sizes checked by a test (no literal sizes under 12 pt outside the workbench)
- [x] Typed text no longer blinks in the prompt box; Open folder opens the project's folder
- [x] Scroll bars show at rest (6 px, the text colour at 3:1 or more on every surface), not
      only on hover
- [x] Play starts a Rust workspace's window app (from its manifests), not whichever program was
      built last (a CLI that quit at once)
- [x] Play says when what it started quit straight away (with its last output), instead of
      "Starting…" and nothing, and that it's already open instead of starting it twice
- [x] Questions from the builder reach the person: "Builder's questions: Ask me / Decide
      yourself" under each project's prompt box (`project_questions_set`, craft.json `questions`)
      and a default in Settings (`questions`, which follows Auto mode until picked), apart from
      Auto mode's approvals; a builder that decides starts its next message with "I decided:"
- [ ] When the builder decides a question, show the question and its choice as an answered card
      in the feed (the run sees only the tool call today; the builder's words say what it chose)
- [x] Ask questions about a build without starting one: "Just ask" under the prompt box (or a
      message starting with `/btw`), answered as a card, never a round (`rebuild_question_ask`).
      Claude Code answers from a copy of the builder's session (`--fork-session`, not kept) with
      Read/Glob/Grep only (none in Clean room) and no tool server; an API AI with the tools that
      change nothing (`agent::ReadOnlyHost`); other agents are refused
- [ ] A question's own cost: a forked Claude Code session reports the whole session's running
      total, so a forked answer shows none; count questions in the project's usage
- [ ] "Make this change" on an answer that suggests one (sends it as a normal message)
- [ ] A program started from the CLI (`project_play`) keeps the shell's output pipe open, so the
      command doesn't return until it closes: start it without inheriting the CLI's handles (#207)
- [x] "It's done" beside Continue and Try again: the person keeps a build as it is and it stops
      offering to carry on (`project_build_finish`, #210)
- [x] The desktop app keeps `desktop.log` beside its settings: startup steps, warnings, a window
      that couldn't start, panics
- [x] The cost says when it's an estimate: Claude Code's figure is its own guess at API prices,
      so the project page says "AI cost (estimate)" with a note that it isn't the bill, and the
      title bar says "(estimate)"; what an API key was charged is kept apart (`api_billed_usd`
      in usage.json; older files count as estimates)
- [x] A running build says what it's on ("Now: Running cargo test (42s)", the last action between
      them), and "More detail" opens its activity as it arrives: stages, every command and file
      with how it ended, what the builder said and what programs printed outside the
      conversation, with secrets hidden. Kept in `build-activity.log` ("Open log",
      `rebuild_activity_show`, and every tool the CLI's `rebuild` prints)
- [ ] Show a command's output while it runs: Claude Code reports a tool's result only when it
      ends, so a long `cargo build` is one quiet line until then. Watching the agent's child
      processes from outside could say what's running and for how long
- [ ] The keep-awake helper once outlived a CLI `rebuild` on Windows by more than 9 minutes and held
      the caller's output pipe; not reproduced in 8 more runs, where it ended with the CLI. Dropping
      its guard only raises a flag (`RunningProcess::drop` waits only for `hands_off` programs), so
      ending on time rests on the Job Object closing, and its time limit is 7 days
- [ ] Sometimes starting the app shows nothing: find why from `desktop.log` (a GOG Galaxy Vulkan
      overlay layer loads into the app; try DX12 first on Windows if that's it)
- [x] Try again picks up where a run stopped instead of starting over: a project whose builder
      has worked isn't studied again or given the first brief; when the builder had finished and
      only the check didn't (`awaiting_check` in craft.json), only the check runs. A check that
      returns an error gets a second go, and then the run says the build is finished but couldn't
      be checked
- [ ] Find why a site capture lost its browser ("the WebSocket is closed", 419 ms into
      `web_site_capture` for a second page, seen once; the same capture passed 41 s earlier)
- [ ] Two engine tests fail on a Mac, on `main` too: `real_binary_end_to_end_if_present` expects
      `/bin/ls` to be Linux, and `auto_mode_keeps_going_but_never_does_the_dangerous_things` is
      refused `rm -rf` in a temp folder under `/var/folders`
- [x] Every effort level Claude offers: `xhigh` and `max` next to low, medium and high, for the
      Claude API and Claude Code, a level a model lacks stepping down to the nearest one it has,
      and a way to choose it in Settings → AI and `ai effort` (only `config.toml` sets it now)
- [ ] Claude Code's own extras: its Ultracode switch (a setting, not an effort level; the
      effort environment variable we use can't turn it on) and its model names beyond the list
      (`opusplan`, `[1m]` variants) offered in Settings → AI; `ai model` already takes any name
- [ ] `a_helper_is_judged_by_whether_it_runs` (ai crate) sometimes fails when several crates'
      tests run at once and passes alone: it writes a script and runs it straight away, which a
      busy machine can refuse while another test's child still holds the file open

### R2.10 Pinned builds
Owner: maintainers · Status: in progress
Keep a build that works at hand: pin it, and open it from the sidebar whatever the builder does
to the project next. Pins are the engine's (tools), kept in the project's `pinned/` folder.
- [x] Keep runtime assets in `obj` folders when pinning or copying a project; only exclude recognised compiler intermediates, and retain the selected direct-launch program in a pin (#274).
- [x] Pin a build as a frozen copy (the default: the app's files and the program, without what
      a build makes again, in `pinned/<n>/`, with its size shown first) or as a live pin that runs
      the project's app as it is; open, stop, rename and remove pins; one copy runs per folder
      (pins and Play alike) unless another is asked for; a start that quits at once says so with
      its last output (`project_pin_create`, `project_pins_list`, `project_pin_open`,
      `project_pin_stop`, `project_pin_rename`, `project_pin_delete`; `pin.json` version 2 (version 1 still reads);
      `platform::Launched`)
- [x] A light pin in place of the live one, which only opened what Play opens: the program, the
      code and anything a program may write to are copied, dependencies and media are hard-linked
      to the project's (`SHARED_KINDS`), and a file that can't be linked is copied. Replacing or
      deleting a shared file in the project leaves the pin's as it was; rewriting one in place
      changes both. Old live pins still open; new ones are refused
- [x] Pins leave out what a compiler keeps beside a program that nothing needs to run it (`.pdb`
      debug symbols, `.lib`, `.d`, lock files): measured on real Rust projects, that took a
      291 MB pin to 49 MB, far more than sharing could
- [x] Leave out a project's old program copies (`*.running-*.exe`, 22 MB each in one project), which
      a pin can't tell from the program's helpers by their name alone
- [ ] Say when a light pin ended up copying what it meant to share (a drive without hard links)
- [ ] Pins of one project sharing with each other, so a third frozen copy of the same assets
      takes no more space
- [ ] Pin a website (a frozen copy of the built site, each served on its own port)
- [ ] A pin started before the app restarted shows as running (keep its process id and start
      time in the pin, and check both), and can be stopped
- [ ] Cap a run's log (`last-run.log`, `play.log`): it grows as long as the program prints
- [x] A collapsible Pinned section in the sidebar (icons with a running dot when folded; open,
      open another copy, close, go to the project, rename, remove), Pin this build on the project
      page with the frozen/light choice and each copy's size; the pin tools are in the command
      palette with every other tool
- [ ] Opening a pin that's already running brings its window to the front, instead of a message
- [ ] How much space pins take in Settings. Showing a pin's folder is done in the right-click menu,
      through `project_open_folder` with `pin` — claimed: muraa-p, branch bugfix/r2.10-pin-folder
- [ ] Live check on Windows: rebuild a project while its frozen pin runs, and the build isn't blocked

## M3 Engine depth

### R3.1 More tools (all 22 built)
Owner: open · Status: in progress (a live Cutter test is left)
- [x] Radio signal decoding: `radio_recording_decode`, `radio_decoders_list`, with rtl_433 run as a
      program (an optional engine, path in Settings → Engines)
- [x] Cutter sessions: `native_cutter_sessions_list`, `native_cutter_command_run`, for sessions
      the person shares with `=h& 9090` in Cutter's console (read-only commands, 127.0.0.1 only)
- [ ] Cutter sessions: try them against a real Cutter, including whether `=h&` keeps Cutter
      responsive (only a stand-in server so far)
- [x] rizin debug sessions: `native_rizin_session_begin` (a program, stopped at its start, or a
      pid), `_command_run`, `_show`, `_end`, driving `rizin -d` with a marker after each command
- [x] Rizin sessions: live test passed again with Rizin 0.9.1 installed from its pin (program
      arguments reach the program; a `dc` that outlasts its wait keeps the session busy and the next
      command waits for it; nothing left running)
- [x] Every tool is listed in `docs/tools.md` (`cargo xtask tools`)

### R3.2 Known partial tools (see tool-status.md)
Owner: open · Status: done
- [x] Pseudo-C arguments for imports without prototypes: a table of common libc and Win32 argument
      counts (`disasm::arity`, plus stdcall `@bytes` names) shows every argument, unset ones as the
      register
- [x] `calls_out` counts tail calls (and `tail_calls` reports them on their own)
- [x] Imports as search hits and call-path goals: `native_functions_search` lists matching imports
      (`kind: "import"`); `native_call_path_find` takes an import as a forward goal (`native::Goal`)
- [x] `native_strings_browse` section filter (`section`, any case; an unknown one names those with strings)
- [x] Edge vs Electron labelling: `js_electron_pages_list` names the runtime from `/json/version`
      (`web_common::runtime_of`) and says when a plain Edge or Chrome answered
- [x] `core_evidence_exports_compare` tampered record: every record is checked against its own id; edited records
      are reported and never count as unchanged; duplicate keys are listed
- [x] AnyCPU .NET bitness: triage says "any CPU" from the CLI flags (`PeImage::dotnet_arch`,
      shared with the .NET inventory) and reports `dotnet_arch`
- [x] `apple_app_graph_build` on bare Mach-O: only a bundle counts as an app; the result says
      `shape` (app-bundle, bare-executable, none)
- [x] Nested field names in CLI help: fields inside object options (and arrays of objects) are listed
      as `option.field`, two levels deep
- [x] `native_function_pseudocode` on an address no analysis made a function: the hint says so and points
      to `native_function_find` and xrefs, instead of claiming the built-in decompiler answered
- [x] Ghidra: decompile code its quick analysis never made a function (reached only through pointer
      tables, as seen in a live run): disassemble and create the function on demand in
      the bridge, in memory only (the analysis stays read-only)
- [x] Ghidra: when the bridge stops before it starts, its logs are copied beside the analysis
      (`<analysis>.bridge.log`, as the analysis log is) and the error points there, since the
      runtime folder is removed with the error

### R3.3 Frida sessions for real
Owner: open · Status: todo
- [ ] Replace the in-memory session bookkeeping with real attach, resume and detach
- [x] `frida_devices_find` with `remote`: `frida-ls-devices` has no `-H`, so listing a remote's devices fails - return a single device entry for the remote instead of calling frida-ls-devices

### R3.4 Decompilers for managed code (external engines)
Owner: open · Status: in progress
- [x] C#: ILSpy's command-line tool (MIT): `managed_ilspy_decompile` (C# of the whole assembly or one
      type, the IL, or its types; update check off; native files refused before it runs)
- [x] Java: Vineflower (Apache-2.0): `java_vineflower_decompile` (a .class or JAR; its .jar run with
      the configured Java, or a `vineflower` script; sources read back from a temp folder)
- [x] Vineflower: a checked install pin (Settings → Engines or `engines_install`)
- [ ] Vineflower: run it once on a real JAR (no Java on the machine it was written on)

### R3.5 Device-backed tools
Owner: open · Status: blocked (needs an Android device or emulator)
- [ ] Verify the 23 unverified adb tools; record results in tool-status.md

### R3.6 Browser walkthroughs in depth
Owner: open · Status: done
Scripted web sessions (`web_walkthrough_record`) should be repeatable and see what a person
needs to understand a site.
- [x] Fixed environment: viewport, scale, locale, time zone, colour scheme, reduced motion,
      service workers (defaults 1280x720, en-US, UTC, light); the result says what was applied
- [x] Start with given cookies and local/session storage (`storage`; every value is treated as a
      secret and redacted; results name what was set, never values)
- [x] Optional request/response bodies and header values per run (`keep_bodies`, off by
      default; text capped at 64 KiB, digested after redaction; credential headers always redacted)
- [x] Locators by role and accessible name (accessibility tree), and by test id, next to CSS
      selectors; an optional `step_id` per step, echoed in the result
- [x] Artifacts at the end or after each step (`capture`): screenshot, DOM (redacted, capped),
      accessibility tree, history, storage key and cookie names
- [x] Event families (`capture.events`): console, page errors, WebSockets, frames, workers, popups,
      downloads (blocked), each with its step and a sequence number; a goto no longer drops events
- [x] Compare two walkthrough runs step by step (`web_snapshots_compare`: steps aligned by `step_id`,
      network and event-count differences), with plain text `normalization` rules

### R3.7 Program runs you can compare
Owner: open · Status: done
Running the same app or game twice (`runtime_walkthrough_record`) should only differ where its
behaviour differs, so `runtime_captures_compare` can say what changed.
- [x] Normalise captures (`normalization`): process ids, loopback ports, working/temp paths, literal
      patterns and time buckets, with what was replaced recorded
- [x] `runtime_captures_compare` reports which terminal lines changed (first changed line, lines only
      on each side with line numbers), not only their counts
- [x] Windows: `runtime_walkthrough_record` runs the program through `platform::process` (its Job
      Object ends every child) and reads its output through pipes, in the same result shape, saying
      so (`pty_backend: "pipes"`, a `no_terminal` limitation); typed input, resizes, signals and
      watched files still need the terminal capture (Linux, macOS) and are refused

---

### R3.8 Game archives
Owner: open · Status: done
Games keep their files in archives; someone studying a game first wants to see what's inside.
- [x] Unreal `.pak`: version, mount point, compression, file list (v1–v11 indexes); an encrypted
      index or encrypted files are named, never guessed (`game_pak_list`; `formats::unreal_pak`;
      checked live on large archives)
- [x] Unreal `.pak`: extract a file, or a whole folder a page at a time (stored or zlib;
      `game_pak_extract`, streamed, SHA-256, output folders made, files already there skipped; encrypted
      and Oodle files refused with the reason; checked live)
- [x] Unreal IoStore (`.utoc`/`.ucas`): list the files (`game_iostore_list`, `formats::unreal_iostore`,
      TOC versions 1–8, signed and partitioned containers; encrypted names counted, never guessed;
      checked live)
- [x] Unity: `*.assets` and level files (serialized files): list the objects by class, with their
      names (`game_unity_list`, `formats::unity_serialized`, format 14+ (Unity 5 on), either byte
      order; checked live on files from Unity 2017 to Unity 6)
- [x] Unity: UnityFS bundles (`*.bundle`, `data.unity3d`): list the files inside, and the objects
      by class in each serialized file (`game_unity_bundle_list`, `formats::unity_bundle`, LZ4 and
      LZMA; checked live)

### R3.9 Game assets out
Owner: open · Status: in progress
After seeing what a game packs (R3.8), the next step is taking its pictures and sounds out in
formats anyone can open.
- [x] Unity: textures to PNG (uncompressed formats and DXT1/DXT5, pixels inline or in a `.resS`
      file, from `*.assets` files and bundles; `game_unity_asset_export`, `formats::unity_texture`;
      the Texture2D layout of Unity 2017.3–6000 checked live on thousands of textures)
- [ ] Unity: sounds out (the stored stream, usually FSB5; PCM ones as WAV)
- [x] Unity: BC7 and BC6H textures (every BC7 mode; BC6H unsigned and signed, tone-mapped to 8-bit
      sRGB, brighter than white clips; `formats::bptc`, written from the Khronos Data Format
      Specification; Unreal's PF_BC7 and PF_BC6H too; checked on two Unity games: 11 of 11 BC7
      textures and 2 BC6H lightmaps saved and looked at)
- [ ] Unity: crunched textures (DXT1Crunched, DXT5Crunched; two of the games checked use them) and
      the float formats (RHalf, RGHalf, RGBAHalf, RFloat, RGFloat, RGBAFloat)
- [x] Unreal: textures from `.uasset`/`.uexp` files taken out of a pak, only when the person
      confirms they may unpack the game (`game_unreal_texture_export`, `permission: true`;
      `formats::unreal_texture` for Unreal 4.26–4.27 cooked packages, `formats::pixels` shared with
      Unity, which also gains BC4/BC5; checked live: every texture tried was saved)
- [ ] Unreal 5 and Oodle: IoStore packages, unversioned properties and Oodle-compressed paks
- [x] App: a Game files screen: pick a game, see its archives, and take its pictures out after the
      person confirms they have permission (sidebar → Game files; `game_archives_list` finds a
      folder's paks, IoStore files, Unity files and bundles; the permission question is asked once
      per game, then a save dialog)
- [x] Game files: save pictures from Unity bundles (`game_unity_list` lists a bundle's objects by
      path id, from every serialized file inside it, each naming its `file`; bundles built without
      their Unity version use the one in the game's globalgamemanagers; checked on a Unity game's
      bundles: 27 of 27 sprite atlases saved, and a scene bundle with two serialized files listed)
- [ ] Game files: save pictures from IoStore containers (needs the Unreal 5 support above)
- [x] The rebuild's Deep-mode brief points the builder at these tools (`enable_toolset` formats,
      then the `game_*` tools) before any outside converter; a live run had set
      up a third-party unpacker instead
- [ ] Unreal: sounds and meshes out (so a Deep-mode rebuild needs no outside converter for them)

### R3.10 Narrow reads of saved results, and more of an app's set-up
Owner: open · Status: in progress
A saved analysis should answer a narrow question without running again, and an app's own code
should give away more of how it is set up.
- [x] Preserve every unassigned window when comparing application preferences (#237).
- [x] `core_evidence_browse` pages keep only the rows that match (`matching`: field → value or list
      of values, `a.b` inside a row, null for a missing field), return only chosen fields (`fields`)
      and list the field names of the matching rows (`field_names`); offsets count matching rows.
      Checked on a saved analysis of a 1,706-file Electron package: 4,472 effects → 12 process starts
- [x] `android_resources_read` takes several locales in one call (`only_locales`, added to
      `locale`), each with its own string table; ones the app lacks are named (`locales_not_found`),
      and a table cut at 5,000 strings says so
- [x] Electron windows whose options sit in a local object (`const opts = {…}; new
      BrowserWindow(opts)`, or `webPreferences: prefs`) have their webPreferences and preload read,
      with the object's name and line (`options_from`); an object that is written to, exported or
      used any other way, anywhere in the module, keeps the window `dynamic`
- [x] A spread or computed key in window options or webPreferences makes what it may replace
      unknown (`dynamic`), instead of "not set": found on an installed app whose preferences
      spread in another object. Nine installed Electron apps (19 windows) read the same otherwise
- [x] An app's file inventory tells a Java class from a universal Mach-O by its contents, not its
      file name
- [ ] Android locales: try `only_locales` on a real APK (only the test fixture so far)
- [x] `app_graphs_compare`: chunks whose names differ only by a build hash
      (`Doctor-DIpf_I7N.js` → `Doctor-DrkWsav4.js`, `main.3f2a9c1b.js`, `chunk-UGNM3QZK.mjs`) are one
      changed module with the old name (`was`), not removed + added; only when the name without
      its hash is unique on each side (Vite's several `index-<hash>.js` aren't guessed between)
- [ ] `app_graphs_compare` on the two real Electron releases again, to count how many of the
      162 "removed" now pair (and pair the `index-<hash>` chunks by structure if many stay)
- [x] Results over Claude Code's tool-output limit (about 25k tokens) come back summary-first: a
      connection whose client is Claude Code (`clientInfo.name` = `claude-code`, checked against
      Claude Code 2.1.305) gets an 80 KB response budget instead of 8 MiB, so a bigger evidence
      record collapses to its summary with `core_evidence_browse` to page it;
      `CRAFT_ANYTHING_MCP_MAX_RESPONSE_BYTES` still sets it explicitly
- [ ] A live chat run with a big comparison result, to see Claude Code page it with
      `core_evidence_browse` (and whether 80 KB is the right size)

### R3.11 Single-file apps, game files and stand-in backends
Owner: open · Status: in progress
Read what real apps and games ship as (one file carrying the rest), and let a rebuilt website run
against what its original was recorded answering.
- [x] Identify Bun UTF-16LE text members (#257). — claimed: Afloat16, branch bugfix/r3.11-bun-text-encoding-20261102
- [x] One seam for files packed inside a file (`formats::packed`), with `core_packed_files_list`
      and `core_packed_files_unpack`; a new kind is one reader and one table line
- [x] Readers: Bun and Node.js single-file programs, .NET single-file apps, PyInstaller, Godot PCK.
      A real 279 MB Bun program read and unpacked (2,889 modules); real Node blobs read
- [x] `formats_bytecode_show` (Python bytecode), `game_unity_code_names_show` (Unity IL2CPP metadata),
      `formats_ai_weights_show` (GGUF, safetensors; a real file of each read), `native_publisher_show`, `native_library_calls_list`
      (delay-load too), `native_offered_symbols_list`, Zstandard ZIP members
- [x] `app_folder_explain`: what an install folder is made with, and what to run next, from a table
      of runtimes; checked against about 25 installed Mac apps
- [x] A stand-in backend from a network recording (`web_standin_build`, `_start`, `_stop`, `_show`),
      GraphQL and tRPC operations in app maps, and `web_walkthrough_check`
- [x] `js_app_map` keeps a literal GraphQL document that begins with a comment, as it already
      does without one (#260)
- [x] `app_builds_line_up` (two real builds of a 276 MB program in 42 s),
      `native_source_folder_write` (resumable), `android_components_list`
- [x] CLI: `--json -` takes parameters from a pipe; `--format csv` and `tsv` write a result's rows,
      with spreadsheet formulas kept as text. Kimi Code, Factory Droid and WorkBuddy in setup
- [x] Real samples built with the real tools and read back (none are kept in the repo): PyInstaller
      with Python 3.9 and 3.14 (every archive member the same bytes as PyInstaller's own reader,
      on the 3.14 program), .NET 8 for macOS, Linux and Windows, plain and compressed self-contained,
      Godot 3.6, 4.3 and 4.5 (formats 1, 2, 3; MD5s match on the files checked), a real APK. 214 real
      Python modules read the same as CPython's `marshal`
- [ ] A real IL2CPP `global-metadata.dat` (needs a Unity build or a shipped game); synthetic so far.
      Compare a real APK's components against another tool's reading
- [ ] Stand-in backend: a browser-made HAR and a real front end talking to it (only a hand-written
      HAR so far); GraphQL and tRPC on real bundles (only hand-written minified shapes)
- [ ] Stand-in backend: writes that change later reads (recorded answers are replayed as they are)
- [ ] Tell the builder about the stand-in backend in a website's brief, and start one from a recording
- [ ] Stand-in backend: a 304 recorded with no body is replayed as a bare 304, which a fresh browser can't use; say so or leave it out
- [ ] Check the Kimi Code, Factory Droid and WorkBuddy registrations in the real apps
- [ ] Godot format 4 and IL2CPP metadata 38 and 39 are header-only; read their tables once a real
      file can be checked
- [ ] Bun: take source maps and bytecode out as files; a standalone `.pyz`; PyInstaller scripts carry
      no Python version of their own, so `formats_bytecode_show` needs `python_version`
- [ ] `native_source_folder_write` uses the built-in decompiler only: use Ghidra in Deep mode when it's there
- [ ] `native_publisher_show` hashes the file minus the signature fields, not section by section;
      a file with unusual gaps between sections can read as different
- [ ] Two engine tests fail on a Mac, on `main` too: `real_binary_end_to_end_if_present` expects
      `/bin/ls` to be Linux, and `auto_mode_keeps_going_but_never_does_the_dangerous_things`
      refuses `rm -rf` of a temp path under `/var/folders`
- [ ] Looked at and left for later, as niche for now: firmware image kinds (ESP32, U-Boot, device
      trees, Intel HEX), Erlang BEAM, GPU code objects, kernel modules, GameCube DOL, Mac crash
      reports, SAZ and qlog captures, protobuf bodies, R8 mappings, JNI links, MCP over HTTP

## M4 Release (later)

Owner: maintainers · Status: in progress (v0.1.0 is released; managed tier and follow-ups remain)
- [x] Secret scan: `cargo xtask secrets` (in `cargo xtask ci` and `.githooks/pre-commit`); files and full
      history scanned clean on 2026-10-19
- [x] **decision**: commit author emails stay as they are (they're public on other repos too)
- [x] Before going public: `cargo xtask secrets --history` on every branch: clean on 2026-10-20
      (all 16 remote branches); run it again right before the switch if more lands
- [x] `CONTRIBUTING.md` and `SECURITY.md` (private reports through GitHub's "Report a vulnerability")

Launch checklist (source-only first; signed installers can follow):
- [ ] Maintainers: protect `main` (PRs required, squash only) and turn on private vulnerability
      reporting (Settings → Code security), which SECURITY.md points to
- [x] Live website build on current `main` (2026-10-20, Claude Code, `example.com`, 1 round):
      Ready, 91% alike (95% / 91% / 87% at 1440 / 768 / 390 px); the builder used `rebuild_check`
      mid-turn (89% → 91%); no processes left. App and game left for after launch (maintainers'
      choice)
- [x] R0.6: the tool-id mapping table and both ids working, before the ids are public
- [x] STATUS: a last pass so everything not run live says so (2026-10-20: ACP agents, WASM checks
      from Rust, Cutter, Vineflower/Apktool, and Ghidra's guided install off Windows are marked)
- [x] Pull request and issue templates (`.github/`): the roadmap item, what was and wasn't
      verified, the checks; security reports go to private reporting
- [x] README quick start for someone new: Rust version, Linux packages (as CI installs them),
      clone, run the app, `cargo install` the CLI, `doctor`, then a first rebuild
- [ ] Follow the README quick start on a clean machine (Windows, and Linux or macOS)
- [x] CI runs on every pull request and push to `main` once the repository is public (skipped while
      it's private, so it costs nothing now): fmt, clippy, all tests with `--no-fail-fast`,
      layers, the tool list, schemas and the secret scan, plus the wasm32 check
- [x] CI and release workflows on `main`: Linux builds no longer need screen-capture libraries,
      so CI passes there; the README lists each download (2026-10-22)
- [x] Packaging like the other Crafting Apps (2026-10-22): `packaging/icons.sh` rebuilds every app
      icon from the SVG (`cargo xtask ico` packs the Windows .ico); the DMG opens on a laid-out
      window (`packaging/macos/dmg`: background, icon positions) and is built with
      `hdiutil create`, with the app inside the mounted image checked by `codesign --strict`; the
      FreeBSD workflow runs on main and packaging PRs (when public) with a package-contents check
- [ ] Build the new DMG on a Mac (release dry run) and look at the window once
- [ ] macOS CLI zip blocked by Gatekeeper when downloaded in a browser (#94), though Apple has its
      notarization tickets: find why the online lookup fails for people (it passes on our Mac, which
      may be exempt), on a machine that shows it
- [ ] **decision** A standalone macOS CLI that can carry its ticket, such as a stapled `.pkg`; that
      needs a Developer ID Installer certificate in the release secrets
- [x] The first release: v0.1.0 built from `release`, signed (Apple Developer ID and notarization,
      Azure Trusted Signing) and published on 2026-10-31
- [ ] Move the release workflows off actions that target Node.js 20 (`actions/checkout@v4`,
      `upload-artifact@v4`, `download-artifact@v4`); GitHub warns on every job and forces them onto Node.js 24
- [x] **decision**: the free, open-source release doesn't wait on Anthropic. Each person runs their
      own Claude Code under their own account and Anthropic's terms (claude-code.md)
- [ ] Managed tier: account backend, usage metering (Claude API under our own key only)
- [ ] Before the managed tier or any paid offering: confirm the Claude Code orchestration question
      with Anthropic (claude-code.md)
