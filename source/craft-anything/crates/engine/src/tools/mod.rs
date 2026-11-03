//! Tool modules. Each module exposes `specs()`; register a new module with one line in [`all`].
//! Parallel contributors: add a new module rather than growing someone else's.
//!
//! # Summary-first detail convention
//!
//! Every tool that can return a large result takes a uniform `detail` parameter:
//! `detail: "summary" | "complete"` (default `complete`). With `detail=summary` the tool still
//! builds and **retains** the full evidence record in the session ledger, but returns a compact
//! body: a one-line `summary`, light `counts`/extras, a `record` ([`Evidence::summary_view`]) and
//! an `saved_evidence` (`{"kind":"saved","evidence_id":"ev_…"}`) plus
//! `"continue_with":"core_evidence_browse"`. The caller then pages the full record facet by facet
//! with `core_evidence_browse` (facets, items, pages) without resending it. Build this with the
//! shared [`detailed`] helper (or [`Detail`]), so the shape is identical across tools. The MCP
//! server applies the same idea at the transport layer: a response over the connection's byte
//! budget collapses to this summary form (pointing at the retained record) rather than only an
//! error, whenever the result is a retained evidence record.

use crate::session::Session;
use craft_anything_evidence::{Environment, EvidenceBuilder, ToolError};

pub mod investigation_tools;
// Readable Markdown/HTML investigation reports from findings + evidence.
pub mod native_annotate;
pub mod native_common;
pub mod native_formats;
pub mod native_function;
pub mod native_listing;
pub mod native_workflows;
pub mod report_tools;
pub mod session_tools;
// Shared input helpers for the built-in format tools.
pub mod static_input;
// Android apps (APK, DEX, resources, Flutter, JEB).
pub mod android_tools;
// Java programs: .class/JAR/WAR parsing, JVM bytecode and pseudo-Java.
pub mod java_tools;
// A connected Android phone or emulator over adb, plus managed engine installs.
pub mod adb_tools;
// Frida instrumentation driven through the Frida CLI.
pub mod frida_tools;
// Target-free formats: Go, WebAssembly, EVM.
pub mod format_tools;
// Database files: read-only SQLite inspection.
pub mod database_tools;
// Solana sBPF / classic eBPF programs (built-in decoder + ELF parser).
pub mod sbpf_tools;
// Firmware images (built-in signature scan, entropy, carving).
pub mod firmware_tools;
pub mod game_archive_tools;
// Unity IL2CPP global-metadata.dat: images, types, methods and string literals.
pub mod il2cpp_tools;
// What an installed app of unknown make is built on, from its folder alone.
pub mod install_tools;
// JavaScript, web, archive and app graph tools.
pub mod application_tools;
// Apple: Mach-O, code signing, plists, Swift, Interface Builder, asset catalogs, dyld.
pub mod apple_tools;
pub mod artifact_tools;
pub mod js_tools;
// .NET assemblies (built-in ECMA-335 reader).
pub mod managed_tools;
pub mod web_tools;
// Browser via the Chrome DevTools Protocol (loopback CDP): transport and shared helpers.
pub mod web_common;
// Browser (CDP) tools: passive inspection, bundle analysis, screenshots, comparisons, walkthroughs.
pub mod browser_tools;
// Websites as targets: a browser this session starts, page capture for rebuilding.
pub mod website_tools;
// A stand-in backend answering a rebuilt front end from a network recording.
pub mod standin_tools;
pub mod window_tools;
// Asking the person a question, and approving a coding agent's actions, through the inbox.
pub mod asset_tools;
pub mod interaction_tools;
pub mod project_tools;
// Pinned builds: kept copies of a project's build, and what they started.
pub mod pin_tools;
pub mod setup_tools;
// Electron and V8-inspector tools over loopback CDP.
pub mod electron_runtime_tools;
// Web runtime over CDP: coverage, event listeners, module-import graph.
pub mod web_runtime_tools;
// The Deep-mode (Ghidra) hook the native decompile path consults.
pub mod deep;
// Running programs: process capture under a PTY, and capture comparison.
pub mod process_tools;
// Comparison and verification session tools (pure, in-process).
pub mod compare_tools;
// Apple runtime: accessibility UI and native call tracing (macOS; wrong_os elsewhere).
pub mod apple_runtime;
// Byte-signature and text search over a file, with native addresses.
pub mod build_tools;
pub mod byte_search;
// Rust programs: toolchain, crates, panic paths, symbols, cargo-auditable data.
pub mod rust_tools;
// Imports, exports, signature blocks, AI model headers, matching builds, exporting pseudo-C.
pub mod program_facts_tools;
// Electron fuse wire in a packaged Electron executable.
pub mod electron_fuse_tools;
// Interface diff between two WebAssembly modules.
pub mod wasm_compare_tools;
// Saved packet captures (pcap/pcapng): built-in decoder, optional tshark.
pub mod packed_tools;
pub mod packet_tools;
pub mod python_tools;
// Thin read-only wrappers over optional objdump and rizin.
pub mod external_disasm_tools;
// GDB sessions over the machine interface (optional GDB).
pub mod cutter_tools;
pub mod gdb_tools;
pub mod java_decompile_tools;
pub mod radio_tools;
pub mod rizin_session_tools;

/// Every tool, in registration order.
pub fn all() -> Vec<crate::ToolSpec> {
    let mut v = Vec::new();
    v.extend(session_tools::specs());
    v.extend(artifact_tools::specs());
    v.extend(js_tools::specs());
    v.extend(web_tools::specs());
    v.extend(browser_tools::specs());
    v.extend(website_tools::specs());
    v.extend(standin_tools::specs());
    v.extend(interaction_tools::specs());
    v.extend(project_tools::specs());
    v.extend(pin_tools::specs());
    v.extend(setup_tools::specs());
    v.extend(build_tools::specs());
    v.extend(window_tools::specs());
    v.extend(asset_tools::specs());
    v.extend(electron_runtime_tools::specs());
    v.extend(web_runtime_tools::specs());
    v.extend(application_tools::specs());
    v.extend(investigation_tools::specs());
    v.extend(report_tools::specs());
    v.extend(native_listing::specs());
    v.extend(native_function::specs());
    v.extend(native_annotate::specs());
    v.extend(native_workflows::specs());
    v.extend(native_formats::specs());
    v.extend(apple_tools::specs());
    v.extend(android_tools::specs());
    v.extend(java_tools::specs());
    v.extend(adb_tools::specs());
    v.extend(frida_tools::specs());
    v.extend(format_tools::specs());
    v.extend(database_tools::specs());
    v.extend(sbpf_tools::specs());
    v.extend(firmware_tools::specs());
    v.extend(packed_tools::specs());
    v.extend(python_tools::specs());
    v.extend(game_archive_tools::specs());
    v.extend(il2cpp_tools::specs());
    v.extend(install_tools::specs());
    v.extend(managed_tools::specs());
    v.extend(process_tools::specs());
    v.extend(compare_tools::specs());
    v.extend(apple_runtime::specs());
    v.extend(byte_search::specs());
    v.extend(rust_tools::specs());
    v.extend(program_facts_tools::specs());
    v.extend(electron_fuse_tools::specs());
    v.extend(wasm_compare_tools::specs());
    v.extend(packet_tools::specs());
    v.extend(external_disasm_tools::specs());
    v.extend(gdb_tools::specs());
    v.extend(rizin_session_tools::specs());
    v.extend(radio_tools::specs());
    v.extend(cutter_tools::specs());
    v.extend(java_decompile_tools::specs());
    v
}

/// The uniform summary-first detail control (see the module docs). `complete` is the default and
/// returns the full evidence record; `summary` returns a compact, pageable view.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, serde::Deserialize, serde::Serialize, schemars::JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Detail {
    #[default]
    Complete,
    Summary,
}

/// Return a built evidence record either in full (`detail=complete`) or as the compact,
/// summary-first body (`detail=summary`): the full record is retained in the session and the
/// caller is pointed at `core_evidence_browse` to page it. `extras` is merged into the summary
/// body (counts, a headline figure…); pass `Value::Null` for none.
pub fn detailed(
    ctx: &mut crate::tool::Ctx<'_>,
    e: craft_anything_evidence::Evidence,
    detail: Detail,
    extras: serde_json::Value,
) -> Result<crate::tool::ToolOutput, ToolError> {
    use serde_json::{Value, json};
    if detail == Detail::Complete {
        return Ok(crate::tool::ToolOutput::evidence(e));
    }
    let id = e.id.clone();
    let summary = e.summary.clone();
    let view = e.summary_view();
    ctx.session.record(e)?;
    let mut body = json!({
        "saved_evidence": {"kind": "saved", "evidence_id": id},
        "summary": summary,
        "record": view,
        "continue_with": "core_evidence_browse",
    });
    if let (Value::Object(m), Value::Object(x)) = (&mut body, extras) {
        m.extend(x);
    }
    Ok(crate::tool::ToolOutput::Value(body))
}

/// Start an evidence record about the active target with the session's environment.
pub fn evidence_for_active(session: &Session, operation: &str) -> Result<EvidenceBuilder, ToolError> {
    let t = session.active()?;
    Ok(EvidenceBuilder::new(operation, t.target.subject(), Environment::builtin(session.clean_room())))
}

/// Parse an address given as `0x…` hex, plain hex with a leading letter, or decimal.
pub fn parse_address(s: &str) -> Result<u64, ToolError> {
    let t = s.trim();
    let parsed = if let Some(h) = t.strip_prefix("0x").or_else(|| t.strip_prefix("0X")) {
        u64::from_str_radix(h, 16).ok()
    } else if t.chars().any(|c| c.is_ascii_alphabetic()) {
        u64::from_str_radix(t.trim_end_matches(['h', 'H']), 16).ok()
    } else {
        t.parse::<u64>().ok()
    };
    parsed.ok_or_else(|| ToolError::invalid(format!("not an address: {s:?} (use 0x-hex)")))
}

#[cfg(test)]
mod tests {
    use super::parse_address;

    #[test]
    fn addresses() {
        assert_eq!(parse_address("0x401000").unwrap(), 0x401000);
        assert_eq!(parse_address("401000h").unwrap(), 0x401000);
        assert_eq!(parse_address("4096").unwrap(), 4096);
        assert!(parse_address("0xZZ").is_err());
        assert!(parse_address("").is_err());
    }
}
