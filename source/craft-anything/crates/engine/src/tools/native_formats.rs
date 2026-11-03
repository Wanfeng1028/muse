//! Format-level diagnostics with built-in parsers (no external tools): PE resources, binary
//! layout (ELF/PE/Mach-O), recorded crashes (ELF core files), DOS load images; plus `triage`
//! (what is this and where do I start) and `core_evidence_browse` (paging over stored evidence).

use super::native_common::{hex, image, select_document, spec};
use crate::target::{Target, TargetKind};
use crate::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use craft_anything_analysis::native as an;
use craft_anything_evidence::{Confidence, Coverage, Environment, ErrorCode, Evidence, EvidenceBuilder, Limitation, Location, Subject, ToolError, sha256_hex};
use craft_anything_formats::Format;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};
use std::path::PathBuf;
use std::sync::Arc;

pub fn specs() -> Vec<ToolSpec> {
    use Toolset::{Core, Formats, Native};
    let e = Effects::EVIDENCE;
    vec![
        spec(
            "native_pe_resources_list",
            "Windows resources",
            "PE32/PE32+ resource tree (type → name → language) with SHA-256 of each item, icon groups, version information and the manifest. Built-in parser. Uses the active target unless path is given.",
            "See a Windows program's icons, version details and other resources.",
            Formats,
            e,
            Requires::Nothing,
            schema_of::<PeResourcesParams>,
            native_pe_resources_list,
        ),
        spec(
            "native_layout_show",
            "Binary layout",
            "Sections, segments (ELF program headers), symbols, relocations, linkage and hardening (NX, PIE, RELRO, canary, fortify, CFG…) of an ELF, PE or Mach-O file. detail=summary returns counts and keeps the complete record in the session.",
            "See how a program file is built and how well it is hardened.",
            Formats,
            e,
            Requires::Nothing,
            schema_of::<LayoutParams>,
            native_layout_show,
        ),
        spec(
            "native_crash_show",
            "Crash dump",
            "Read a Linux ELF core dump: the signal and its meaning, the faulting address, registers of each thread, the process name and arguments, mapped files, and which file the crash happened in.",
            "Find out why and where a program crashed.",
            Formats,
            e,
            Requires::Nothing,
            schema_of::<CrashParams>,
            native_crash_show,
        ),
        spec(
            "native_dos_image_show",
            "DOS load image",
            "Check a DOS MZ or .COM program's load image: header, SHA-256 digests (file, header, load module), relocations, entry point and stack, with any inconsistencies.",
            "Check how a DOS program is loaded into memory.",
            Native,
            e,
            Requires::Target,
            schema_of::<DocParams>,
            native_dos_image_show,
        ),
        spec(
            "core_target_triage",
            "What is this?",
            "Say what a file is in plain English (format, OS, architecture, language/toolchain hints such as Go, Rust, .NET, Electron, Flutter, Delphi, packers) and which toolsets and tools to use next. Uses the active target unless path is given.",
            "Find out what a file is and where to start.",
            Core,
            e,
            Requires::Nothing,
            schema_of::<TriageParams>,
            core_target_triage,
        ),
        spec(
            "core_evidence_browse",
            "Page through evidence",
            "View part of a stored (or inline) evidence record: the summary, one part, one row of a list, a page of a list's rows (optionally only the rows matching given field values, cut to chosen fields, with the field names listed), or a part of a function dossier (pseudocode, assembly, basic_blocks, callers, callees, flow_*…), with coverage and next_offset. Nothing is analysed again.",
            "Read a big result a page at a time.",
            Core,
            e,
            Requires::Nothing,
            schema_of::<ShowParams>,
            core_evidence_browse,
        ),
    ]
}

fn d_max_file() -> u64 {
    64 << 20
}
fn d_entries() -> usize {
    16_384
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct PeResourcesParams {
    /// Absolute path of a PE file; the active target when omitted.
    #[serde(default)]
    pub path: Option<String>,
    /// Refuse files bigger than this (64 MiB..512 MiB, default 64 MiB).
    #[serde(default = "d_max_file")]
    pub max_file_bytes: u64,
    /// Most resource entries (1..=65536, default 16384).
    #[serde(default = "d_entries")]
    pub max_entries: usize,
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Detail {
    #[default]
    Complete,
    Summary,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct LayoutParams {
    /// Absolute path of an ELF, PE or Mach-O file; the active target when omitted.
    #[serde(default)]
    pub path: Option<String>,
    /// complete (default) or summary.
    #[serde(default)]
    pub detail: Detail,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct CrashParams {
    /// Absolute path of an ELF core file; the active target when omitted.
    #[serde(default)]
    pub path: Option<String>,
    /// Ask for live debugger context (not available in clean-room mode; reported as a limitation).
    #[serde(default)]
    pub with_debugger_context: bool,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct DocParams {
    /// Open target (document) to use; the active one when omitted.
    #[serde(default)]
    pub document: Option<String>,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct TriageParams {
    /// Absolute path of a file or folder; the active target when omitted.
    #[serde(default)]
    pub path: Option<String>,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(tag = "kind", rename_all = "kebab-case", deny_unknown_fields)]
pub enum RecordSource {
    /// Evidence already recorded in this session or project.
    Saved { evidence_id: String },
    /// A full evidence record passed inline.
    Inline { evidence: Value },
}

fn d_show_limit() -> usize {
    64
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(tag = "kind", rename_all = "kebab-case", deny_unknown_fields)]
pub enum Show {
    /// The record without its result.
    Summary,
    /// One named part of the result (e.g. mitigations, linkage).
    Part { name: String },
    /// One row of a list: by index, or the first whose name/address equals `pick`.
    Row { list: String, pick: String },
    /// A page of a list (sections, symbols, functions…).
    Rows {
        list: String,
        /// Counts matching rows when `matching` is given.
        #[serde(default)]
        offset: usize,
        #[serde(default = "d_show_limit")]
        limit: usize,
        /// Keep only the rows whose fields equal these values, e.g. `{"kind": "require", "path":
        /// ["main.js", "preload.js"]}`: every field must match, a list means any of its values,
        /// `a.b` reaches inside a row and null matches a field the row doesn't have.
        #[serde(default)]
        matching: BTreeMap<String, Value>,
        /// Return only these fields of each row (`a.b` reaches inside); a row without one leaves it out.
        #[serde(default)]
        fields: Vec<String>,
        /// Also list the field names of the matching rows, to see what to match or pick.
        #[serde(default)]
        field_names: bool,
    },
    /// A part of a native function dossier (pseudocode, assembly, basic_blocks, callers, callees,
    /// incoming_references, outgoing_references, unresolved_calls, referenced_strings,
    /// referenced_names, native_api, flow_summary, flow_nodes,
    /// flow_edges, flow_effects, flow_parameters, flow_parameter_uses,
    /// comments, function). Text facets page by UTF-16 units.
    FunctionPart {
        name: String,
        #[serde(default)]
        offset: usize,
        #[serde(default = "d_show_limit")]
        limit: usize,
    },
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ShowParams {
    /// Where the evidence comes from.
    pub source: RecordSource,
    /// What part of it to show.
    pub show: Show,
}

/// Bytes, a subject and a display name: from `path`, or the active target.
fn input(ctx: &Ctx<'_>, path: &Option<String>, max: u64) -> Result<(Arc<[u8]>, Subject), ToolError> {
    match path {
        Some(p) => {
            let pb = PathBuf::from(p);
            if !pb.is_absolute() {
                return Err(ToolError::invalid(format!("{p} is not an absolute path")));
            }
            let meta = std::fs::metadata(&pb).map_err(|e| ToolError::io(p, e))?;
            if meta.is_dir() {
                return Err(ToolError::invalid(format!("{p} is a folder; pass a file")));
            }
            if meta.len() > max {
                return Err(ToolError::new(ErrorCode::OverLimit, format!("{p} is {} bytes; the limit is {max}", meta.len()))
                    .with_remediation("Raise max_file_bytes (up to 512 MiB) if you really need it."));
            }
            let bytes = std::fs::read(&pb).map_err(|e| ToolError::io(p, e))?;
            let name = pb.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_else(|| p.clone());
            let t = Target::from_bytes(pb, name, bytes);
            Ok((t.bytes.clone(), t.subject()))
        }
        None => {
            let t = ctx.session.active()?;
            if t.target.bytes.len() as u64 > max {
                return Err(ToolError::new(ErrorCode::OverLimit, format!("the target is {} bytes; the limit is {max}", t.target.bytes.len())));
            }
            Ok((t.target.bytes.clone(), t.target.subject()))
        }
    }
}

fn builder(ctx: &Ctx<'_>, op: &str, subject: Subject, params: Value) -> EvidenceBuilder {
    EvidenceBuilder::new(op, subject, Environment::builtin(ctx.session.clean_room())).params(params)
}

fn native_pe_resources_list(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: PeResourcesParams = parse_params(params.clone())?;
    if !(64 << 20..=512 << 20).contains(&p.max_file_bytes) {
        return Err(ToolError::invalid("max_file_bytes must be 64 MiB..=512 MiB"));
    }
    if !(1..=65_536).contains(&p.max_entries) {
        return Err(ToolError::invalid("max_entries must be 1..=65536"));
    }
    let (data, subject) = input(ctx, &p.path, p.max_file_bytes)?;
    let res = craft_anything_formats::pe::parse_resources(&data, p.max_entries).map_err(|e| ToolError::unsupported(format!("Not a readable PE file: {e}")))?;
    let entries: Vec<Value> = res
        .entries
        .iter()
        .map(|e| {
            let sha = e.file_offset.and_then(|o| usize::try_from(o).ok()).and_then(|o| data.get(o..o.saturating_add(e.size as usize))).map(sha256_hex);
            json!({"type": e.type_name, "name": e.name, "language": e.language, "rva": hex(e.rva), "size": e.size, "file_offset": e.file_offset, "codepage": e.codepage, "sha256": sha})
        })
        .collect();
    let n = entries.len();
    let summary = format!(
        "{n} resources{}{}.",
        if res.icon_groups.is_empty() { String::new() } else { format!(", {} icon groups", res.icon_groups.len()) },
        res.version.as_ref().and_then(|v| v.strings.get("ProductName").cloned()).map(|p| format!(", product \"{p}\"")).unwrap_or_default()
    );
    let mut b = builder(ctx, "native_pe_resources_list", subject, json!({"path": p.path, "max_entries": p.max_entries}))
        .result(json!({"entries": entries, "icon_groups": res.icon_groups, "version": res.version, "manifest": res.manifest, "truncated": res.truncated}))
        .summary(summary)
        .coverage(if res.truncated {
            Coverage { status: craft_anything_evidence::CoverageStatus::Partial, examined: Some(n as u64), total: None, next_offset: None }
        } else {
            Coverage::complete(n as u64)
        });
    if res.truncated {
        b = b.limitation(Limitation::new("truncated", format!("stopped at max_entries={}", p.max_entries)));
    }
    b = b.limitations(res.warnings.iter().map(|w| Limitation::new("resource_parse", w.clone())));
    Ok(ToolOutput::evidence(b.build()?))
}

fn native_layout_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: LayoutParams = parse_params(params)?;
    let (data, subject) = input(ctx, &p.path, 2 << 30)?;
    let bin = craft_anything_formats::parse_binary(&data).map_err(|e| ToolError::unsupported(format!("Not a readable ELF, PE or Mach-O file: {e}")))?;
    const CAP: usize = 20_000;
    let syms: Vec<Value> = bin.symbols.iter().take(CAP).map(|s| json!({"name": s.name, "demangled": s.demangled, "address": hex(s.addr), "size": s.size, "kind": s.kind, "global": s.global, "weak": s.weak, "defined": s.defined, "dynamic": s.dynamic})).collect();
    let relocs: Vec<Value> =
        bin.relocations.iter().take(CAP).map(|r| json!({"address": hex(r.addr), "kind": r.kind, "symbol": r.symbol, "addend": r.addend})).collect();
    let linkage = json!({"interpreter": bin.info.get("interpreter"), "libraries": bin.libraries, "soname": bin.info.get("soname"), "rpath": bin.info.get("rpath"), "runpath": bin.info.get("runpath"), "imports": bin.imports.len(), "exports": bin.exports.len()});
    let full = json!({
        "format": bin.format,
        "kind": bin.kind,
        "architecture": bin.arch.name(),
        "bits": bin.bits,
        "entry_point": bin.entry.map(hex),
        "image_base": hex(bin.image_base),
        "sections": bin.sections,
        "segments": bin.segments,
        "details": bin.details,
        "symbols": syms,
        "relocations": relocs,
        "relocation_count": bin.relocation_count,
        "imports": bin.imports,
        "exports": bin.exports,
        "mitigations": bin.mitigations,
        "linkage": linkage,
        "info": bin.info,
        "warnings": bin.warnings,
    });
    let m = &bin.mitigations;
    let summary = format!(
        "{} {} ({}): {} sections, {} symbols, {} relocations; NX {}, PIE {}, RELRO {}, canary {}.",
        bin.format.plain(),
        bin.kind,
        bin.arch.name(),
        bin.sections.len(),
        bin.symbols.len(),
        bin.relocation_count,
        yn(m.nx),
        yn(m.pie),
        m.relro.as_deref().unwrap_or("n/a"),
        yn(m.canary)
    );
    let mut lims = Vec::new();
    if bin.symbols.len() > CAP || bin.symbols_truncated {
        lims.push(Limitation::new("symbols_capped", format!("the record keeps the first {CAP} symbols")));
    }
    if bin.relocations.len() > CAP || bin.relocation_count > bin.relocations.len() {
        lims.push(Limitation::new("relocations_capped", "only part of the relocation list is kept"));
    }
    if bin.format == Format::Pe {
        lims.push(Limitation::new("pe_base_relocations", "PE base relocations are counted by the loader, not listed"));
    }
    let ev = builder(ctx, "native_layout_show", subject, json!({"path": p.path, "detail": "complete"}))
        .result(full)
        .summary(summary.clone())
        .limitations(lims)
        .coverage(Coverage::complete(1))
        .location(Location::new("file_offset", "0x0"))
        .build()?;
    if p.detail == Detail::Summary {
        let id = ev.id.clone();
        let counts = json!({"sections": bin.sections.len(), "segments": bin.segments.len(), "symbols": bin.symbols.len(), "relocations": bin.relocation_count, "imports": bin.imports.len(), "exports": bin.exports.len()});
        let view = ev.summary_view();
        ctx.session.record(ev)?;
        return Ok(ToolOutput::Value(
            json!({"saved_evidence": {"kind": "saved", "evidence_id": id}, "summary": summary, "counts": counts, "mitigations": bin.mitigations, "record": view, "continue_with": "core_evidence_browse"}),
        ));
    }
    Ok(ToolOutput::evidence(ev))
}

fn yn(b: Option<bool>) -> &'static str {
    match b {
        Some(true) => "yes",
        Some(false) => "no",
        None => "n/a",
    }
}

fn native_crash_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: CrashParams = parse_params(params)?;
    let (data, subject) = input(ctx, &p.path, 2 << 30)?;
    let core = craft_anything_formats::elf::parse_core(&data).map_err(|e| {
        ToolError::unsupported(format!("Not a readable ELF core dump: {e}"))
            .with_remediation("Pass a Linux core file (from a crash, `gcore`, or systemd-coredump after extraction).")
    })?;
    let pc = core.pc();
    let location = pc.and_then(|pc| core.locate(pc)).map(|(m, off)| json!({"file": m.path, "file_offset": hex(off), "mapping_start": hex(m.start)}));
    let fault = core.signal.as_ref().and_then(|s| s.fault_addr);
    let fault_location = fault.and_then(|a| core.locate(a)).map(|(m, off)| json!({"file": m.path, "file_offset": hex(off)}));
    let sig = core.signal.as_ref().map(|s| format!("{} ({})", s.name, s.meaning)).unwrap_or_else(|| "an unknown signal".into());
    let who = core.process.as_ref().map(|p| p.name.clone()).unwrap_or_else(|| "The process".into());
    let summary = format!(
        "{who} stopped with {sig}{}{}.",
        pc.map(|pc| format!(" at {pc:#x}")).unwrap_or_default(),
        location.as_ref().and_then(|l| l["file"].as_str().map(|f| format!(" in {f}"))).unwrap_or_default()
    );
    let mut lims: Vec<Limitation> = core.warnings.iter().map(|w| Limitation::new("core_parse", w.clone())).collect();
    if p.with_debugger_context {
        lims.push(Limitation::new(
            "debugger_context_unavailable",
            "no debugger runs in clean-room mode; backtraces need the matching binaries and symbols, which aren't loaded here",
        ));
    }
    lims.push(Limitation::new("no_backtrace", "only the crashing registers are read; the call stack is not unwound"));
    let mut b = builder(ctx, "native_crash_show", subject, json!({"path": p.path, "with_debugger_context": p.with_debugger_context}))
        .result(json!({
            "plain_english": summary,
            "process": core.process,
            "signal": core.signal,
            "program_counter": pc.map(hex),
            "crash_location": location,
            "fault_location": fault_location,
            "threads": core.threads,
            "mapped_files": core.mapped_files,
            "auxv": core.auxv,
            "notes": core.notes,
            "memory_segments": core.memory_segments.len(),
            "architecture": core.arch.name(),
        }))
        .summary(summary)
        .authority(craft_anything_evidence::Authority::EarlierRecord)
        .limitations(lims)
        .coverage(Coverage::complete(core.notes.len() as u64));
    if let Some(pc) = pc {
        b = b.location(Location::address(pc).with_label("program counter"));
    }
    Ok(ToolOutput::evidence(b.build()?))
}

fn native_dos_image_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: DocParams = parse_params(params)?;
    select_document(ctx, &p.document)?;
    let t = ctx.session.active()?;
    let data = t.target.bytes.clone();
    let is_com = t.target.kind == TargetKind::DosCom;
    let file_sha = t.target.sha256.clone();
    let (result, summary, ok) = if is_com {
        let size = data.len();
        let ok = size <= 0xff00;
        let problems: Vec<String> = if ok { vec![] } else { vec![format!("{size} bytes is too big for a .COM program (max 65280)")] };
        (
            json!({"format": "dos-com", "file_sha256": file_sha, "load_module_sha256": sha256_hex(&data), "load_segment_offset": "0x100", "entry": "0x100", "size": size, "relocations": [], "problems": problems, "consistent": ok}),
            format!(".COM program of {size} bytes, loaded at offset 0x100 and started there."),
            ok,
        )
    } else if data.starts_with(b"MZ") || data.starts_with(b"ZM") {
        let mz = craft_anything_formats::dos::parse_mz(&data).map_err(|e| ToolError::unsupported(format!("Not a readable DOS MZ header: {e}")))?;
        let hdr = data.get(..(mz.header_bytes as usize).min(data.len())).unwrap_or(&[]);
        let start = mz.load_module_offset as usize;
        let module = data.get(start.min(data.len())..start.saturating_add(mz.load_module_size as usize).min(data.len())).unwrap_or(&[]);
        let ok = mz.problems.is_empty();
        (
            json!({
                "format": "dos-mz",
                "file_sha256": file_sha,
                "header_sha256": sha256_hex(hdr),
                "load_module_sha256": sha256_hex(module),
                "header": mz,
                "entry": format!("{:04x}:{:04x}", mz.entry_cs, mz.entry_ip),
                "entry_linear": hex(u64::from(mz.entry_linear)),
                "stack": format!("{:04x}:{:04x}", mz.stack_ss, mz.stack_sp),
                "consistent": ok,
            }),
            format!(
                "DOS MZ program: {}-byte load module, {} relocations, entry {:04x}:{:04x}{}.",
                mz.load_module_size,
                mz.relocations.len(),
                mz.entry_cs,
                mz.entry_ip,
                if ok { "" } else { "; the header has problems" }
            ),
            ok,
        )
    } else {
        return Err(ToolError::unsupported("This isn't a DOS MZ or .COM program.")
            .with_remediation("Open a DOS program (for .COM files use core_target_open with format=dos-com)."));
    };
    let _ = image(ctx);
    let mut b = super::native_common::ev(ctx, "native_dos_image_show", json!({}))?.result(result).summary(summary).coverage(Coverage::complete(1));
    if !ok {
        b = b.limitation(Limitation::new("inconsistent_image", "the header disagrees with the file; see problems"));
    }
    Ok(ToolOutput::evidence(b.build()?))
}

fn non_native_triage(t: &Target) -> (String, Vec<&'static str>, Vec<(&'static str, &'static str)>) {
    let n = &t.name;
    match t.kind {
        TargetKind::Apk => (
            format!("{n} is an Android app package."),
            vec!["core", "android"],
            vec![("android_package_show", "manifest, permissions, components and code"), ("android_classes_find", "find classes by name")],
        ),
        TargetKind::Dex => (
            format!("{n} is Android app code (DEX)."),
            vec!["core", "android"],
            vec![("android_classes_find", "find classes"), ("android_class_show", "read a class")],
        ),
        TargetKind::Asar => (
            format!("{n} is the packed web app inside an Electron desktop app."),
            vec!["core", "javascript"],
            vec![("js_app_map", "map the app's JavaScript, IPC and routes")],
        ),
        TargetKind::Wasm => {
            (format!("{n} is a WebAssembly module."), vec!["core", "formats"], vec![("formats_wasm_module_show", "exports, imports and sections")])
        }
        TargetKind::Jar => (format!("{n} is a Java archive."), vec!["core", "artifacts"], vec![("core_archive_show", "list what's inside")]),
        TargetKind::JavaClass => (
            format!("{n} is a compiled Java class."),
            vec!["core", "java"],
            vec![("java_class_show", "fields, methods and code of the class"), ("java_classes_find", "find classes by name")],
        ),
        TargetKind::Zip => (format!("{n} is a ZIP archive."), vec!["core"], vec![("core_archive_show", "list what's inside")]),
        TargetKind::Directory => (
            format!("{n} is a folder (an app bundle, an unpacked app or a project)."),
            vec!["core"],
            vec![("core_archive_show", "inventory the folder"), ("core_target_triage", "triage the main executable inside it by path")],
        ),
        TargetKind::Script => {
            (format!("{n} is a script or web page."), vec!["core", "javascript"], vec![("js_app_map", "parse the code, modules and endpoints")])
        }
        TargetKind::NetworkCapture => {
            (format!("{n} is a recording of network traffic."), vec!["core", "browser"], vec![("web_recording_show", "list requests and APIs")])
        }
        TargetKind::Plist => (format!("{n} is an Apple settings file (property list)."), vec!["core", "apple"], vec![("apple_plist_show", "read it as JSON")]),
        TargetKind::Evm => (format!("{n} is smart-contract bytecode."), vec!["core", "formats"], vec![("formats_evm_interface_show", "function selectors")]),
        TargetKind::Sqlite => {
            (format!("{n} is a SQLite database (how an app stores its data)."), vec!["core", "database"], vec![("db_sqlite_show", "tables, schema and rows")])
        }
        _ => (
            format!("{n} isn't a format we recognise yet."),
            vec!["core"],
            vec![("native_bytes_show", "look at the raw bytes"), ("core_target_open", "reopen with format=raw-binary if it is machine code")],
        ),
    }
}

fn core_target_triage(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: TriageParams = parse_params(params)?;
    let t: Target = match &p.path {
        Some(path) => {
            let pb = PathBuf::from(path);
            if !pb.is_absolute() {
                return Err(ToolError::invalid(format!("{path} is not an absolute path")));
            }
            Target::load(&pb)?
        }
        None => ctx.session.active()?.target.clone(),
    };
    let native_kind = matches!(
        t.kind,
        TargetKind::Elf | TargetKind::Pe | TargetKind::MachO | TargetKind::MachOFat | TargetKind::Managed | TargetKind::DosCom | TargetKind::RawBinary
    );
    let parsed = if native_kind || t.kind == TargetKind::Unknown { super::native_common::image_for(&t).map(Some) } else { Ok(None) };
    let builder = EvidenceBuilder::new("core_target_triage", t.subject(), Environment::builtin(ctx.session.clean_room())).params(json!({"path": p.path}));
    let ev = match parsed {
        Ok(Some(img)) => {
            let mut r = an::triage(&img.bin, &img.data, &t.name);
            if t.kind == TargetKind::Managed {
                r.result["plain_english"] = json!(format!("{} This is a .NET assembly: use the .NET tools for readable C#-level results.", r.summary));
                r.summary = r.result["plain_english"].as_str().unwrap_or_default().to_string();
            }
            builder.result(r.result).summary(r.summary).confidence(r.confidence).limitations(r.limitations).locations(r.locations).build()?
        }
        fallback => {
            let (mut plain, mut toolsets, mut tools) = non_native_triage(&t);
            let mut builder = builder;
            if let Err(error) = fallback
                && native_kind
            {
                let kind = t.kind.plain();
                plain = format!(
                    "{} starts like {}{}, but we couldn't read it as one. Check that the file is complete and undamaged.",
                    t.name,
                    kind.get(..1).unwrap_or_default().to_lowercase(),
                    kind.get(1..).unwrap_or_default()
                );
                tools = vec![("native_bytes_show", "inspect the unreadable file's raw bytes")];
                builder = builder.limitation(Limitation::new("native_parse_failed", error.message));
            }
            // A game's folder: what it's made with, its libraries and its size.
            let game = (t.kind == TargetKind::Directory).then(|| craft_anything_engines::game::profile(&t.path));
            let game = game.and_then(|g| g.summary(&t.name).map(|s| (g, s)));
            if let Some((_, summary)) = &game {
                plain.clone_from(summary);
                toolsets = vec!["core", "formats"];
                tools = vec![("game_archives_list", "find the archives it packs its files in"), ("game_pak_list", "list what's in an Unreal pak")];
            }
            let mut result = json!({
                "plain_english": plain,
                "kind": t.kind,
                "description": t.kind.plain(),
                "size": t.bytes.len(),
                "recommended_toolsets": toolsets,
                "next_steps": tools.iter().map(|(tool, why)| json!({"tool": tool, "why": why})).collect::<Vec<_>>(),
            });
            if let Some((g, _)) = game {
                result["game"] = json!(g);
            }
            builder
                .result(result)
                .summary(plain)
                .confidence(Confidence::Inferred)
                .limitation(Limitation::new("detected_by_content", "the kind is detected from the first bytes and, to break ties, the file name"))
                .build()?
        }
    };
    Ok(ToolOutput::evidence(ev))
}

// ---------------------------------------------------------------------------------------------
// Analysis view

/// Find a value by key anywhere in the first levels of `v`.
fn find_key<'a>(v: &'a Value, key: &str, depth: usize) -> Option<&'a Value> {
    if depth > 4 {
        return None;
    }
    match v {
        Value::Object(m) => m.get(key).or_else(|| m.values().find_map(|x| find_key(x, key, depth + 1))),
        _ => None,
    }
}

/// Page text by UTF-16 code units without splitting a surrogate pair.
fn page_text(s: &str, offset: usize, limit: usize) -> (String, usize, Option<usize>) {
    let total: usize = s.encode_utf16().count();
    let mut out = String::new();
    let mut pos = 0usize;
    let mut taken = 0usize;
    let mut next = None;
    for c in s.chars() {
        let w = c.len_utf16();
        if pos >= offset {
            if taken + w > limit {
                next = Some(pos);
                break;
            }
            out.push(c);
            taken += w;
        } else if pos + w > offset {
            // offset lands inside a surrogate pair: start at the next character
        }
        pos += w;
    }
    (out, total, next)
}

fn core_evidence_browse(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ShowParams = parse_params(params.clone())?;
    let parent: Evidence = match &p.source {
        RecordSource::Saved { evidence_id } => ctx.session.resolve_evidence(evidence_id)?,
        RecordSource::Inline { evidence } => {
            let e: Evidence =
                serde_json::from_value(evidence.clone()).map_err(|e| ToolError::invalid(format!("inline evidence isn't an evidence record: {e}")))?;
            if !e.verify() {
                return Err(ToolError::new(ErrorCode::EvidenceHashMismatch, "the inline evidence doesn't match its id (it was changed)"));
            }
            e
        }
    };
    let r = &parent.result;
    let (shown, coverage) = match &p.show {
        Show::Summary => (parent.summary_view(), Coverage::complete(1)),
        Show::Part { name } => {
            let v =
                find_key(r, name, 0).ok_or_else(|| ToolError::invalid(format!("no part {name} in this record")).with_details(json!({"available": keys(r)})))?;
            (json!({"part": name, "value": v}), Coverage::complete(1))
        }
        Show::Row { list, pick } => {
            let arr = find_key(r, list, 0)
                .and_then(Value::as_array)
                .ok_or_else(|| ToolError::invalid(format!("no list {list} in this record")).with_details(json!({"available": keys(r)})))?;
            let row = pick.parse::<usize>().ok().and_then(|i| arr.get(i)).or_else(|| {
                arr.iter().find(|x| ["name", "address", "id", "text", "type"].iter().any(|k| x.get(*k).and_then(Value::as_str) == Some(pick.as_str())))
            });
            let row = row.ok_or_else(|| ToolError::invalid(format!("nothing in {list} matches {pick}")))?;
            (json!({"list": list, "pick": pick, "row": row}), Coverage::complete(1))
        }
        Show::Rows { list, offset, limit, matching, fields, field_names } => page_of(r, list, *offset, *limit, matching, fields, *field_names)?,
        Show::FunctionPart { name, offset, limit } => page_of(r, name, *offset, *limit, &BTreeMap::new(), &[], false)?,
    };
    let status = match coverage.status {
        craft_anything_evidence::CoverageStatus::Complete
            if matches!(p.show, Show::Rows { .. } | Show::FunctionPart { .. }) && coverage.examined == Some(0) =>
        {
            "empty"
        }
        craft_anything_evidence::CoverageStatus::Complete if matches!(p.show, Show::Rows { .. } | Show::FunctionPart { .. }) => "page",
        craft_anything_evidence::CoverageStatus::Partial => "page",
        _ => "all-in-view",
    };
    let at_end = coverage.next_offset.is_none();
    let e = EvidenceBuilder::new("core_evidence_browse", parent.subject.clone(), Environment::builtin(ctx.session.clean_room()))
        .params(params)
        .result(json!({"from_evidence": parent.id, "from_tool": parent.operation, "shown": shown, "coverage": {"status": status, "examined": coverage.examined, "total": coverage.total, "next_offset": coverage.next_offset, "at_end": at_end}}))
        .summary(format!("Part of {} evidence ({status}).", parent.operation))
        .confidence(parent.confidence)
        .authority(parent.authority)
        .coverage(coverage)
        .link(parent.id.clone())
        .build()?;
    Ok(ToolOutput::evidence(e))
}

/// A row's field; `a.b` reaches inside when the row has no field named `a.b` itself.
fn field<'a>(row: &'a Value, name: &str) -> Option<&'a Value> {
    row.get(name).or_else(|| name.split('.').try_fold(row, |v, k| v.get(k)))
}

/// Every wanted field equals its value, or one of a list of them; null also matches a missing field.
fn row_matches(row: &Value, matching: &BTreeMap<String, Value>) -> bool {
    matching.iter().all(|(name, want)| {
        let got = field(row, name);
        let is = |w: &Value| got == Some(w) || (got.is_none() && w.is_null());
        match want {
            Value::Array(any) => any.iter().any(is),
            w => is(w),
        }
    })
}

/// A page of a list: its rows (only the matching ones, cut to `fields`) or text by
/// UTF-16 units.
fn page_of(
    r: &Value,
    list: &str,
    offset: usize,
    limit: usize,
    matching: &BTreeMap<String, Value>,
    fields: &[String],
    field_names: bool,
) -> Result<(Value, Coverage), ToolError> {
    let limit = limit.clamp(1, 5000);
    let v = find_key(r, list, 0).ok_or_else(|| ToolError::invalid(format!("no {list} in this record")).with_details(json!({"available": keys(r)})))?;
    let narrowed = !matching.is_empty() || !fields.is_empty() || field_names;
    Ok(match v {
        Value::Array(a) => {
            let rows: Vec<&Value> = a.iter().filter(|x| row_matches(x, matching)).collect();
            let items: Vec<Value> = rows
                .iter()
                .skip(offset)
                .take(limit)
                .map(|x| match x {
                    Value::Object(_) if !fields.is_empty() => {
                        Value::Object(fields.iter().filter_map(|f| field(x, f).map(|v| (f.clone(), v.clone()))).collect())
                    }
                    x => (*x).clone(),
                })
                .collect();
            let cov = Coverage::page(items.len() as u64, rows.len() as u64, offset as u64);
            let mut out = json!({"list": list, "offset": offset, "items": items, "total": rows.len()});
            if !matching.is_empty() {
                out["list_total"] = json!(a.len());
            }
            if field_names {
                let names: BTreeSet<&String> = rows.iter().filter_map(|x| x.as_object()).flat_map(|m| m.keys()).take(100_000).collect();
                out["field_names"] = json!(names);
            }
            (out, cov)
        }
        _ if narrowed => {
            return Err(ToolError::invalid(format!("{list} isn't a list of records, so matching, fields and field_names don't apply"))
                .with_remediation("Leave them out to page it as it is."));
        }
        Value::String(s) => {
            let (text, total, next) = page_text(s, offset, limit.saturating_mul(64));
            let cov = Coverage {
                status: if next.is_some() { craft_anything_evidence::CoverageStatus::Partial } else { craft_anything_evidence::CoverageStatus::Complete },
                examined: Some(text.encode_utf16().count() as u64),
                total: Some(total as u64),
                next_offset: next.map(|n| n as u64),
            };
            (json!({"list": list, "offset": offset, "text": text, "total_utf16_units": total}), cov)
        }
        other => (json!({"list": list, "value": other}), Coverage::complete(1)),
    })
}

fn keys(v: &Value) -> Vec<String> {
    v.as_object().map(|m| m.keys().cloned().collect()).unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::super::native_common::test_support::*;
    use craft_anything_testkit as tk;
    use serde_json::json;

    #[test]
    fn triage_explains_an_unreadable_elf_header() {
        let mut header = vec![0u8; 64];
        header[..16].copy_from_slice(b"\x7fELF\x02\x01\x01\0\0\0\0\0\0\0\0\0");
        header[16..20].copy_from_slice(&[2, 0, 62, 0]);
        header[20] = 1;
        header[52] = 64;
        header[54] = 56;
        header[58] = 64;
        let e = engine_with("truncated.elf", &header[..16]);
        let path = tk::temp_file("truncated.elf", &header[..16]);
        let parse_error = craft_anything_formats::parse_binary(&header[..16]).unwrap_err().to_string();
        for params in [json!({}), json!({"path": path.to_string_lossy()})] {
            let r = call(&e, "core_target_triage", params.clone());
            assert_eq!(r["result"]["kind"], "elf");
            let plain = r["result"]["plain_english"].as_str().unwrap();
            assert!(plain.starts_with("truncated.elf starts like a Linux (or Unix) program, but we couldn't read it"), "{plain}");
            assert!(!plain.contains("isn't a format we recognise yet"));
            let error = call_err(&e, "native_layout_show", params);
            let limitation = r["limitations"].as_array().unwrap().iter().find(|l| l["code"] == "native_parse_failed").unwrap();
            assert!(limitation["message"].as_str().unwrap().ends_with(&parse_error));
            assert!(error.message.ends_with(&parse_error));
            assert!(r["limitations"].as_array().unwrap().iter().any(|l| l["code"] == "detected_by_content"));
        }
        let complete = engine_with("complete.elf", &header);
        let r = call(&complete, "core_target_triage", json!({}));
        assert!(r["summary"].as_str().unwrap().contains("Linux"));
        assert!(r["summary"].as_str().unwrap().contains("x86_64"));
        call(&complete, "native_layout_show", json!({}));
        let text = engine_with("notes.txt", b"plain text");
        let r = call(&text, "core_target_triage", json!({}));
        assert_eq!(r["result"]["kind"], "unknown");
        assert!(r["summary"].as_str().unwrap().contains("isn't a format we recognise yet"));
        assert!(!r["limitations"].as_array().unwrap().iter().any(|l| l["code"] == "native_parse_failed"));
    }

    #[test]
    fn pe_resources_and_layout() {
        let pe = tk::pe64();
        let e = engine_with("craft.exe", &pe);
        let r = call(&e, "native_pe_resources_list", json!({}));
        assert_eq!(r["result"]["entries"].as_array().unwrap().len(), 3);
        assert_eq!(r["result"]["version"]["strings"]["CompanyName"], "Craft Test");
        assert_eq!(r["result"]["entries"][0]["sha256"].as_str().unwrap().len(), 64);
        let r = call(&e, "native_layout_show", json!({}));
        assert_eq!(r["result"]["mitigations"]["nx"], true);
        assert_eq!(r["result"]["imports"][0]["name"], "puts");
        let r = call(&e, "core_target_triage", json!({}));
        assert!(r["result"]["plain_english"].as_str().unwrap().contains("Windows"));
        assert!(r["result"]["next_steps"].as_array().unwrap().iter().any(|s| s["tool"] == "native_pe_resources_list"));
        // path input
        let p = tk::temp_file("other.exe", &pe);
        let r = call(&e, "native_pe_resources_list", json!({"path": p.to_string_lossy()}));
        assert_eq!(r["subject"]["name"], "other.exe");
        assert!(call_err(&e, "native_pe_resources_list", json!({"path": "relative.exe"})).message.contains("absolute"));
    }

    #[test]
    fn layout_summary_keeps_full_record_and_view_pages_it() {
        let (elf, _) = tk::elf64(tk::ElfArch::X86_64, true);
        let e = engine_with("prog", &elf);
        let r = call(&e, "native_layout_show", json!({"detail": "summary"}));
        let id = r["result"]["saved_evidence"]["evidence_id"].as_str().unwrap().to_string();
        assert!(r["result"]["counts"]["symbols"].as_u64().unwrap() > 0);
        let v = call(
            &e,
            "core_evidence_browse",
            json!({"source": {"kind": "saved", "evidence_id": id}, "show": {"kind": "rows", "list": "sections", "offset": 0, "limit": 2}}),
        );
        assert_eq!(v["result"]["shown"]["items"].as_array().unwrap().len(), 2);
        assert_eq!(v["result"]["coverage"]["status"], "page");
        assert_eq!(v["links"][0], id);
        let v = call(&e, "core_evidence_browse", json!({"source": {"kind": "saved", "evidence_id": id}, "show": {"kind": "part", "name": "mitigations"}}));
        assert_eq!(v["result"]["shown"]["value"]["nx"], true);
        let v = call(
            &e,
            "core_evidence_browse",
            json!({"source": {"kind": "saved", "evidence_id": id}, "show": {"kind": "row", "list": "sections", "pick": ".text"}}),
        );
        assert_eq!(v["result"]["shown"]["row"]["name"], ".text");
        // dossier facets, text paging
        let d = call(&e, "native_function_study", json!({"function": "helper"}));
        let did = d["id"].as_str().unwrap().to_string();
        let v = call(
            &e,
            "core_evidence_browse",
            json!({"source": {"kind": "saved", "evidence_id": did}, "show": {"kind": "function-part", "name": "pseudocode", "offset": 0, "limit": 1}}),
        );
        assert_eq!(v["result"]["shown"]["text"].as_str().unwrap().encode_utf16().count(), 64);
        assert!(v["result"]["coverage"]["next_offset"].is_number());
        let v = call(&e, "core_evidence_browse", json!({"source": {"kind": "inline", "evidence": d}, "show": {"kind": "function-part", "name": "callers"}}));
        assert_eq!(v["result"]["shown"]["items"][0]["name"], "main");
        let mut tampered = d.clone();
        tampered["summary"] = json!("changed words are fine");
        call(&e, "core_evidence_browse", json!({"source": {"kind": "inline", "evidence": tampered}, "show": {"kind": "summary"}}));
        let mut tampered = d;
        tampered["result"]["pseudocode"] = json!("evil");
        assert_eq!(
            call_err(&e, "core_evidence_browse", json!({"source": {"kind": "inline", "evidence": tampered}, "show": {"kind": "summary"}})).code,
            craft_anything_evidence::ErrorCode::EvidenceHashMismatch
        );
        assert!(
            call_err(&e, "core_evidence_browse", json!({"source": {"kind": "saved", "evidence_id": "ev_missing"}, "show": {"kind": "summary"}}))
                .details
                .is_some()
        );
    }

    #[test]
    fn pages_keep_matching_rows_and_chosen_fields() {
        let (elf, _) = tk::elf64(tk::ElfArch::X86_64, true);
        let e = engine_with("prog", &elf);
        let r = call(&e, "native_layout_show", json!({"detail": "summary"}));
        let src = json!({"kind": "saved", "evidence_id": r["result"]["saved_evidence"]["evidence_id"]});
        let page = |view: serde_json::Value| call(&e, "core_evidence_browse", json!({"source": src, "show": view}))["result"].clone();
        let all = page(json!({"kind": "rows", "list": "sections", "limit": 5000}));
        let names: Vec<String> = all["shown"]["items"].as_array().unwrap().iter().map(|s| s["name"].as_str().unwrap().to_string()).collect();
        assert!(names.len() > 2 && names.contains(&".text".to_string()), "{names:?}");

        // one value, then a list of values; offsets count matching rows
        let v = page(json!({"kind": "rows", "list": "sections", "matching": {"name": ".text"}}));
        assert_eq!((v["shown"]["total"].as_u64(), v["shown"]["list_total"].as_u64()), (Some(1), Some(names.len() as u64)));
        assert_eq!(v["shown"]["items"][0]["name"], ".text");
        let two = json!([names[0], names[1], "no-such-section"]);
        let v = page(json!({"kind": "rows", "list": "sections", "matching": {"name": two}, "offset": 1, "limit": 5}));
        assert_eq!(v["shown"]["total"], 2);
        assert_eq!(v["shown"]["items"][0]["name"], names[1].as_str());
        assert_eq!(v["coverage"]["at_end"], true);

        // chosen fields only, a missing one left out; field names of the matching rows
        let v = page(json!({"kind": "rows", "list": "sections", "matching": {"name": ".text"}, "fields": ["name", "no_such_field"], "field_names": true}));
        assert_eq!(v["shown"]["items"][0], json!({"name": ".text"}));
        let keys = v["shown"]["field_names"].as_array().unwrap();
        assert!(keys.contains(&json!("name")) && keys.len() > 1, "{keys:?}");

        // null matches a field a row doesn't have; nothing matching is an empty page
        assert_eq!(page(json!({"kind": "rows", "list": "sections", "matching": {"no_such_field": null}}))["shown"]["total"], names.len());
        let v = page(json!({"kind": "rows", "list": "sections", "matching": {"name": "nothing"}}));
        assert_eq!((v["shown"]["total"].as_u64(), v["coverage"]["status"].as_str()), (Some(0), Some("empty")));

        // text and single values can't be narrowed
        let d = call(&e, "native_function_study", json!({"function": "helper"}));
        let err = call_err(
            &e,
            "core_evidence_browse",
            json!({"source": {"kind": "inline", "evidence": d}, "show": {"kind": "rows", "list": "pseudocode", "fields": ["x"]}}),
        );
        assert!(err.message.contains("isn't a list of records"), "{}", err.message);
    }

    #[test]
    fn crash_dumps() {
        let core = tk::elf64_core(0x400010, 0);
        let e = engine_with("core.4242", &core);
        let r = call(&e, "native_crash_show", json!({"with_debugger_context": true}));
        assert_eq!(r["result"]["signal"]["name"], "SIGSEGV");
        assert_eq!(r["result"]["crash_location"]["file"], "/usr/bin/crashy");
        assert!(r["summary"].as_str().unwrap().contains("crashy"));
        assert!(r["limitations"].as_array().unwrap().iter().any(|l| l["code"] == "debugger_context_unavailable"));
        let (elf, _) = tk::elf64(tk::ElfArch::X86_64, true);
        let e = engine_with("prog", &elf);
        assert_eq!(call_err(&e, "native_crash_show", json!({})).code, craft_anything_evidence::ErrorCode::NotSupported);
    }

    #[test]
    fn dos_load_images_and_triage() {
        let e = engine_with("game.exe", &tk::dos_mz());
        let r = call(&e, "native_dos_image_show", json!({}));
        assert_eq!(r["result"]["format"], "dos-mz");
        assert_eq!(r["result"]["consistent"], true);
        assert_eq!(r["result"]["header"]["relocations"].as_array().unwrap().len(), 2);
        let r = call(&e, "core_target_triage", json!({}));
        assert!(r["result"]["plain_english"].as_str().unwrap().contains("DOS"));
        let r = call(&e, "native_functions_list", json!({}));
        assert!(r["result"]["total"].as_u64().unwrap() >= 1);
        let e = engine_with("hi.com", &tk::dos_com());
        let r = call(&e, "native_dos_image_show", json!({}));
        assert_eq!(r["result"]["entry"], "0x100");
        let r = call(&e, "native_function_pseudocode", json!({"function": "0x100"}));
        assert!(r["result"]["pseudo_code"].as_str().is_some());
        let e = engine_with("notes.txt", b"plain text");
        let r = call(&e, "core_target_triage", json!({}));
        assert!(r["result"]["plain_english"].as_str().unwrap().contains("recognise"));
        assert_eq!(call_err(&e, "native_dos_image_show", json!({})).code, craft_anything_evidence::ErrorCode::NotSupported);
        let e = engine_with("app.asar", b"\x04\0\0\0\0\0\0\0\0\0\0\0\0\0\0\0{\"files\":{}}");
        let r = call(&e, "core_target_triage", json!({}));
        assert!(r["result"]["recommended_toolsets"].as_array().unwrap().iter().any(|t| t == "javascript"));
    }

    #[test]
    fn bare_java_class_triage_recommends_java_tools() {
        let hex = "cafebabe00000031000801000550726f62650700010100106a6176612f6c616e672f4f626a656374070003010006616e73776572010003282949010004436f6465002100020004000000000001000900050006000100070000000f0001000000000003102aac000000000000";
        let bytes: Vec<u8> = (0..hex.len() / 2).map(|i| u8::from_str_radix(&hex[i * 2..i * 2 + 2], 16).unwrap()).collect();
        let e = engine_with("Probe.class", &bytes);
        let r = call(&e, "core_target_triage", json!({}));
        assert_eq!(r["result"]["kind"], "java-class");
        assert!(!r["result"]["plain_english"].as_str().unwrap().contains("recognise"));
        assert!(r["result"]["recommended_toolsets"].as_array().unwrap().iter().any(|t| t == "java"));
        assert_eq!(r["result"]["next_steps"][0]["tool"], "java_class_show");
    }

    #[test]
    fn real_binary_end_to_end_if_present() {
        let Ok(bytes) = std::fs::read("/bin/ls") else { return };
        let e = engine_with("ls", &bytes);
        let r = call(&e, "core_target_triage", json!({}));
        assert!(r["result"]["plain_english"].as_str().unwrap().contains("Linux"));
        let r = call(&e, "core_overview_show", json!({}));
        assert!(r["result"]["counts"]["functions"].as_u64().unwrap() > 50);
        let r = call(&e, "native_layout_show", json!({"detail": "summary"}));
        assert!(r["result"]["counts"]["sections"].as_u64().unwrap() > 10);
        let r = call(&e, "native_function_study", json!({"function": "entry"}));
        assert!(r["result"]["pseudocode"].as_str().is_some());
    }
}
