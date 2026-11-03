# Tool status (verified)

`docs/tools.md` (generated) lists every tool. This page records whether each one **works**, from a
functional audit on 2026-10-16 (Windows 11, real inputs) and the fixes that followed.

Legend: **Verified** = ran on real input with plausible, spot-checked output · **Partial** = runs
but output is incomplete in a known way · **Fixed** = was broken or partial in the audit, fixed
and re-checked · **Unverified** = implemented, not runnable here (needs a device, engine or OS
we don't have); source reviewed · **New** = added since the audit, unit-tested and smoke-tested.

## Summary by toolset

| Toolset | Verified | Partial | Fixed | Unverified | Notes |
|---|---|---|---|---|---|
| Core (session, evidence, triage, overview, reports) | 19 | 3 | 7 | 0 | evidence bundles, core_session_show, report, core_target_open, triage fixed |
| Native (listings, functions, xrefs, pseudo-C, bytes, annotations) | 43 | 3 | 2 | 0 | see partials below |
| Browser / web | 10 | 1 | 2 | 0 | +3 new website tools (open/capture/close) |
| JavaScript / Electron | 7 | 1 | 0 | 2 | runtime attach needs a debuggable app |
| Application graphs, comparison, reconstruction | 12 | 3 | 0 | 2 | |
| Managed (.NET) | 7 | 0 | 0 | 0 | no C# decompiler (IL + structure only) |
| Java | 5 | 0 | 0 | 1 | `java_vineflower_decompile` (Vineflower) unverified: no Java on the test machine |
| Android (static) | 9 | 0 | 0 | 4 | JADX/Apktool/JEB paths unverified |
| Android device (adb) | 2 | 0 | 0 | 23 | no device attached |
| Apple | 8 | 0 | 0 | 6 | synthetic Mach-O/plist only; runtime tools macOS-only, except `runtime_ui_read` and `runtime_ui_walkthrough_record`, which also read and drive Windows apps (UI Automation; tested against a WinForms window) |
| Formats, firmware, database | 11 | 0 | 0 | 1 | |
| Runtime (process capture, native calls/UI) | 0 | 0 | 0 | 5 | run foreign code; not executed in the audit |
| Frida | 0 | 0 | 0 | 9 | Frida not installed; parts of session handling are simulated in source |
| Added since the audit | — | — | — | — | 14 new: `native_bytes_find`, `native_rust_binary_show`, `js_electron_fuses_show`, `formats_wasm_compare`, `packets_capture_show`, `packets_fields_show`, `engines_tshark_check`, `packets_inventory_show`, `native_objdump_run`, `native_rizin_command_run`, `native_gdb_session_begin`, `native_gdb_command_run`, `native_gdb_session_show`, `native_gdb_session_end` |

## Real-binary run (2026-10-21)

The built-in engine (Clean room) on four real, stripped programs: a Windows system program (MSVC,
x86-64 PE, 340 KB), a Rust command-line tool (x86-64 PE, 1.1 MB), a Rust shared library (x86-64
ELF, 485 KB) and a Go command-line tool (x86-64 PE, 43 MB). Before → after this round:

| Program | Functions | Named functions | Instructions | Strings | Time |
|---|---|---|---|---|---|
| MSVC system program | 872 → 872 | 43 → 43 | 60,358 → 58,637 | 872 → 876 | 0.1 s |
| Rust tool (PE) | 1,317 → 1,318 | 30 → 30 | 2,307,416 → 222,201 | 1,295 → 1,609 | 2.0 s → 0.2 s |
| Rust library (ELF) | 571 → 561 | 17 → 17 | 385,399 → 90,680 | 144 → 298 | 0.3 s → 0.1 s |
| Go tool | 36,536 → 43,687 | 1 → 43,686 | 3,665,388 → 3,708,492 | 127,701 → 134,759 | 3.2 s → 3.1 s |

Fixed:
- **Go function names.** Go keeps every function's name in its function table even when
  stripped; those entries now seed and name functions (`name_source: go_pclntab`). It also found
  7,726 functions nothing else reached.
- **Functions running into their neighbours.** A switch table with no bound before its jump was
  read 256 entries deep, and the entries past its end pulled other functions' code into the
  switch's function (up to the 60,000-instruction cap; the Rust tool's total was ten times its
  real size). Table entries now stay between the function starts around the jump, a branch to
  another function's entry is a tail call, and functions scanned before a later-found entry was
  known are scanned again once every entry is known.
- **Packed strings.** Rust and Go store text back to back without terminators, so two literals
  read as one. Where code points into the middle of a string, a new one now starts there.

## Still partial (known gaps)

- `native_function_pseudocode`, `native_function_study`: imports outside the argument-count table
  (`disasm::arity`) show only the arguments set in the calling block.
- `native_strings_browse`: most strings in a PE come from resources; `section` limits the list to one section.
- `web_page_show` with `launch` but no open website still sees a blank page (by design; open a
  site with `web_site_open` first).
- `web_site_open` keeps its browser for one session, so from the CLI, where each command is a
  session of its own, a later `web-site-capture` finds no site (it says so). Run them together in
  an MCP client (`craft-anything-cli mcp`), the app or `rebuild` (#153).
- `web_coverage_measure`: coverage on a page with no scripts reports 0 of 0.

## Engines and how they're used

- Packet tools use our built-in pcap/pcapng decoder (`packets_capture_show` for an overview,
  `packets_fields_show` for per-packet fields); `packets_inventory_show` uses tshark when it's
  installed.
- Cutter sessions (`native_cutter_sessions_list`, `native_cutter_command_run`): **New**. The person
  shares a session with `=h& 9090` in Cutter's console; commands are read-only (the
  native_rizin_command_run allow-list) and only 127.0.0.1 is contacted. Tested against a stand-in
  HTTP server; **Unverified** against a real Cutter.
- Radio decoding (`radio_recording_decode`, `radio_decoders_list`): **New**, through rtl_433 run as
  a program. Checked with rtl_433 25.12 on Windows against an Acurite rain gauge recording from
  rtl_433's public test samples.
- Rizin debug sessions (`native_rizin_session_begin`, `_command_run`, `_show`, `_end`): **New**.
  Start, registers, error lines and close checked with Rizin 0.9.1 on Windows; the debugged
  program's own console output isn't captured.
- Also: Java (.class/JAR) tools, Solana sBPF, SQLite, investigation memory, the report tool,
  website open/capture, and the rebuild workflow.
