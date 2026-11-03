//! Target-free format tools with built-in parsers: Go programs (build information and function
//! table), WebAssembly modules (structure, validation, text form) and EVM contract bytecode
//! (dispatcher selectors). Each takes an absolute path or uses the active target.

use super::native_common::{page, spec};
use super::static_input::{self, Input, builder, format_err};
use crate::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use craft_anything_evidence::{Authority, Confidence, Coverage, Limitation, Location, Subject, ToolError, sha256_hex};
use craft_anything_formats::{evm, go, wasm};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

pub fn specs() -> Vec<ToolSpec> {
    let e = Effects::EVIDENCE;
    vec![
        spec(
            "native_go_binary_show",
            "Go program details",
            "Read a Go program (ELF, PE or Mach-O; pick a universal-binary slice with architecture): the build information block (Go version, main module, dependencies with versions, sums and replacements, build settings such as -ldflags, CGO_ENABLED, GOOS/GOARCH, vcs.revision) and the function name table (pclntab, Go 1.2–1.20+ layouts) with every function's name and entry address, paged, plus functions per package. Built-in parser.",
            "Find out which Go version and libraries built a program, and list its functions.",
            Toolset::Formats,
            e,
            Requires::Nothing,
            schema_of::<GoParams>,
            native_go_binary_show,
        ),
        spec(
            "formats_wasm_module_show",
            "WebAssembly module",
            "Validate a WebAssembly module and list its sections, imports, exports, functions (signature, body size, name), memories, tables, globals, custom sections (names, producers, target features, source map URL), start function and data segments; optionally the text form (WAT), paged by characters; optionally scan JavaScript glue files for .wasm references and matching import names. Built-in parser.",
            "See what a WebAssembly module imports, exports and contains.",
            Toolset::Formats,
            e,
            Requires::Nothing,
            schema_of::<WasmParams>,
            formats_wasm_module_show,
        ),
        spec(
            "formats_evm_interface_show",
            "Smart contract interface",
            "Find the public function selectors in EVM contract bytecode (raw or hex, from a file or inline): where the dispatcher sends each selector, whether the function refuses payments (CALLVALUE check), fallback/receive presence, binary-search dispatch, and the compiler metadata (solc/vyper version, IPFS/Swarm hash). Function names are not recoverable without an ABI. Never executes the code.",
            "List the functions a smart contract exposes, from its bytecode.",
            Toolset::Formats,
            e,
            Requires::Nothing,
            schema_of::<EvmParams>,
            formats_evm_interface_show,
        ),
    ]
}

fn d_limit() -> usize {
    200
}
fn d_true() -> bool {
    true
}
fn d_wat_limit() -> usize {
    20_000
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct GoParams {
    /// Absolute path of an ELF, PE or Mach-O file; the active target when omitted.
    #[serde(default)]
    pub path: Option<String>,
    /// For a universal (fat) Mach-O: the slice to read (x86_64, arm64…). The first slice otherwise.
    #[serde(default)]
    pub architecture: Option<String>,
    /// Include the function list page (default true).
    #[serde(default = "d_true")]
    pub include_functions: bool,
    /// Only functions whose name contains this text (case-insensitive).
    #[serde(default)]
    pub query: Option<String>,
    /// First function of the page.
    #[serde(default)]
    pub offset: usize,
    /// Functions per page (1–5000, default 200).
    #[serde(default = "d_limit")]
    pub limit: usize,
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum WasmDetail {
    /// Counts, validation, exports and producers.
    Summary,
    /// Everything, with functions paged.
    #[default]
    Complete,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct WasmParams {
    /// Absolute path of a .wasm file; the active target when omitted.
    #[serde(default)]
    pub path: Option<String>,
    /// summary or complete (default).
    #[serde(default)]
    pub detail: WasmDetail,
    /// Include a page of the text form (WAT). Only valid modules are rendered.
    #[serde(default)]
    pub include_wat: bool,
    /// First character of the WAT page.
    #[serde(default)]
    pub wat_offset: usize,
    /// Characters per WAT page (1–200000, default 20000).
    #[serde(default = "d_wat_limit")]
    pub wat_limit: usize,
    /// First function of the page.
    #[serde(default)]
    pub offset: usize,
    /// Functions per page (1–5000, default 200).
    #[serde(default = "d_limit")]
    pub limit: usize,
    /// Up to 16 absolute paths of JavaScript glue files to scan for .wasm references and import names.
    #[serde(default)]
    pub js_glue_files: Vec<String>,
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum EvmEncoding {
    /// Hex when the content is only hex digits (optional 0x), raw bytes otherwise.
    #[default]
    Auto,
    Raw,
    Hex,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct EvmParams {
    /// Absolute path of a file holding the bytecode; the active target when neither path nor bytecode is given.
    #[serde(default)]
    pub path: Option<String>,
    /// The bytecode as a hex string (optional 0x), instead of a file.
    #[serde(default)]
    pub bytecode: Option<String>,
    /// auto (default), raw or hex.
    #[serde(default)]
    pub encoding: EvmEncoding,
}

const WAT_CAP: usize = 8 << 20;

// ---------------------------------------------------------------------------------------------
// Go

fn native_go_binary_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: GoParams = parse_params(params)?;
    let input = static_input::load(ctx, p.path.as_deref(), go::MAX_INPUT as u64)?;
    ctx.report(None, format!("Reading Go structures in {}", input.name));
    let r = go::inspect(&input.bytes, p.architecture.as_deref()).map_err(|e| format_err(e, "an ELF, PE or Mach-O program"))?;
    ctx.cancel.check()?;
    let limit = p.limit.clamp(1, 5000);
    let q = p.query.as_deref().map(str::to_lowercase).filter(|q| !q.is_empty());
    let all_funcs: Vec<&go::GoFunction> =
        r.pclntab.as_ref().map(|t| t.functions.iter().filter(|f| q.as_deref().is_none_or(|q| f.name.to_lowercase().contains(q))).collect()).unwrap_or_default();
    let (funcs, cov) = if p.include_functions { page(&all_funcs, p.offset, limit) } else { (Vec::new(), Coverage::complete(1)) };
    let b = r.buildinfo.as_ref();
    let mut summary = match b {
        Some(b) => format!(
            "Go {} program ({}, {}): main module {}, {} dependencies, {} build settings",
            b.go_version.as_deref().unwrap_or("(unknown version)"),
            r.container,
            r.architecture,
            b.main.as_ref().map(|m| m.path.as_str()).or(b.path.as_deref()).unwrap_or("(none)"),
            b.deps.len(),
            b.settings.len()
        ),
        None if r.is_go => format!("Go program ({}, {}) without readable build information", r.container, r.architecture),
        None => format!("No Go build information or function table found in this {} file", r.container),
    };
    if let Some(t) = &r.pclntab {
        summary.push_str(&format!("; {} functions in {} packages (function table, Go {} layout)", t.functions.len(), r.packages.len(), t.layout));
    }
    summary.push('.');
    let mut lims = vec![Limitation::new(
        "names_only",
        "Functions come from the function name table: names and entry addresses only, no types, arguments or sizes; inlined functions have no entry of their own.",
    )];
    if !r.is_go {
        lims.push(Limitation::new(
            "absence_not_proof",
            "Not finding Go structures does not prove the program isn't Go: they can be stripped, compressed or packed.",
        ));
    }
    if let Some(b) = b
        && !b.complete
    {
        lims.push(Limitation::new(
            "buildinfo_incomplete",
            "Some build information lines were not understood or the module text is missing; see unparsed_lines and warnings.",
        ));
    }
    if let Some(t) = &r.pclntab {
        if t.located_by == "scan" {
            lims.push(Limitation::new(
                "pclntab_scanned",
                "The function table was found by scanning for its header (no named section); the header checks passed but this is a heuristic.",
            ));
        }
        if t.truncated {
            lims.push(Limitation::new("truncated", format!("Read the first {} of {} declared functions.", t.functions.len(), t.declared_functions)));
        }
    }
    if let Some(s) = &r.slice {
        lims.push(Limitation::new("one_slice", format!("Universal binary: only the {s} slice was read (available: {}).", r.slices_available.join(", "))));
    }
    let pcl = r.pclntab.as_ref().map(|t| {
        json!({"layout": t.layout, "offset": t.offset, "located_by": t.located_by, "section": t.section, "pointer_size": t.pointer_size,
               "quantum": t.quantum, "big_endian": t.big_endian, "declared_functions": t.declared_functions,
               "functions_read": t.functions.len(), "truncated": t.truncated, "warnings": t.warnings})
    });
    let mut ev = builder(
        ctx,
        "native_go_binary_show",
        input.subject.clone(),
        json!({"path": input.path, "architecture": p.architecture, "query": p.query, "offset": p.offset, "limit": limit}),
    )
    .result(json!({
        "container": r.container, "slice": r.slice, "slices_available": r.slices_available, "architecture": r.architecture,
        "is_64": r.is_64, "big_endian": r.big_endian, "is_go": r.is_go,
        "search_region": r.search_region, "mappings": r.mappings, "zero_fills": r.zero_fills,
        "buildinfo": r.buildinfo, "pclntab": pcl,
        "packages": r.packages.iter().take(500).collect::<Vec<_>>(), "package_count": r.packages.len(),
        "functions_matching": all_funcs.len(), "functions": funcs,
        "warnings": r.warnings,
    }))
    .summary(summary)
    .confidence(if r.is_go { Confidence::Observed } else { Confidence::Inferred })
    .authority(Authority::OriginalFiles)
    .limitations(lims)
    .coverage(cov)
    .location(Location::new("path", input.path.display().to_string()));
    if let Some(b) = b {
        ev = ev.location(Location::new("file_offset", format!("{:#x}", b.offset)).with_label("build information"));
    }
    Ok(ToolOutput::evidence(ev.build()?))
}

// ---------------------------------------------------------------------------------------------
// WebAssembly

fn formats_wasm_module_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: WasmParams = parse_params(params)?;
    if p.js_glue_files.len() > 16 {
        return Err(ToolError::invalid("js_glue_files takes at most 16 files"));
    }
    let input = static_input::load(ctx, p.path.as_deref(), wasm::MAX_INPUT as u64)?;
    ctx.report(None, format!("Reading WebAssembly module {}", input.name));
    let r = wasm::inspect(&input.bytes).map_err(|e| format_err(e, "a WebAssembly module"))?;
    ctx.cancel.check()?;
    let limit = p.limit.clamp(1, 5000);
    let wat_limit = p.wat_limit.clamp(1, 200_000);
    let mut lims = Vec::new();
    let mut wat = Value::Null;
    if p.include_wat {
        if !r.validation.valid {
            lims.push(Limitation::new("wat_not_rendered", "The module failed validation, so no text form was produced."));
        } else {
            match wasm::to_wat(&input.bytes, WAT_CAP) {
                Ok((text, truncated)) => {
                    let total = text.chars().count();
                    let page_text: String = text.chars().skip(p.wat_offset).take(wat_limit).collect();
                    let shown = page_text.chars().count();
                    let end = p.wat_offset.saturating_add(shown);
                    if truncated {
                        lims.push(Limitation::new("wat_capped", format!("The text form was cut at {WAT_CAP} bytes.")));
                    }
                    wat = json!({"text": page_text, "offset": p.wat_offset, "chars": shown, "total_chars": total,
                                 "next_offset": (end < total).then_some(end), "capped": truncated});
                }
                Err(e) => lims.push(Limitation::new("wat_not_rendered", format!("The text form could not be produced: {e}"))),
            }
        }
    }
    let mut glue = Vec::new();
    for g in &p.js_glue_files {
        ctx.cancel.check()?;
        let gi = static_input::load_path(g, 8 << 20)?;
        let text = String::from_utf8_lossy(&gi.bytes);
        glue.push(json!({"path": g, "scan": wasm::scan_glue(&text, &r.imports)}));
    }
    let (funcs, cov) = page(&r.functions, p.offset, limit);
    let validity = if r.validation.valid {
        "valid".to_string()
    } else {
        format!("INVALID ({} at byte {})", r.validation.error.as_deref().unwrap_or("?"), r.validation.offset.unwrap_or(0))
    };
    let summary = format!(
        "WebAssembly {} ({validity}): {} imports, {} exports, {} functions, {} memories{}{}.",
        r.encoding,
        r.imports.len(),
        r.exports.len(),
        r.functions.len(),
        r.memories.len(),
        r.module_name.as_ref().map(|n| format!(", module name \"{n}\"")).unwrap_or_default(),
        r.producers.iter().find(|f| f.field == "language").and_then(|f| f.values.first()).map(|v| format!(", written in {}", v.name)).unwrap_or_default()
    );
    if r.truncated {
        lims.push(Limitation::new("truncated", format!("Lists stop at {} entries.", wasm::MAX_ITEMS)));
    }
    if r.parse_error.is_some() {
        lims.push(Limitation::new("parse_stopped", "Reading stopped at a damaged section; later sections are missing from the lists."));
    }
    if r.encoding == "component" {
        lims.push(Limitation::new("component", "Components are validated and their top-level layout listed; inner modules are not described."));
    }
    lims.push(Limitation::new(
        "static_only",
        "Nothing was executed; behaviour depends on the host's import implementations, which are not part of the module.",
    ));
    let result = match p.detail {
        WasmDetail::Summary => json!({
            "encoding": r.encoding, "version": r.version, "size": r.size, "validation": r.validation, "parse_error": r.parse_error,
            "counts": {"sections": r.sections.len(), "types": r.types, "imports": r.imports.len(), "exports": r.exports.len(),
                       "functions": r.functions.len(), "memories": r.memories.len(), "tables": r.tables.len(), "globals": r.globals.len(),
                       "data_segments": r.data_segments, "element_segments": r.element_segments, "custom_sections": r.custom_sections.len()},
            "exports": r.exports.iter().take(50).collect::<Vec<_>>(),
            "module_name": r.module_name, "producers": r.producers, "target_features": r.target_features,
            "source_mapping_url": r.source_mapping_url, "wat": wat, "glue": glue, "warnings": r.warnings,
        }),
        WasmDetail::Complete => json!({
            "encoding": r.encoding, "version": r.version, "size": r.size, "validation": r.validation, "parse_error": r.parse_error,
            "sections": r.sections, "types": r.types, "imports": r.imports, "imported_functions": r.imported_functions, "exports": r.exports,
            "functions_total": r.functions.len(), "functions": funcs,
            "memories": r.memories, "tables": r.tables, "globals": r.globals, "start_function": r.start_function,
            "data_segments": r.data_segments, "element_segments": r.element_segments, "data_count": r.data_count,
            "custom_sections": r.custom_sections, "module_name": r.module_name, "producers": r.producers,
            "target_features": r.target_features, "source_mapping_url": r.source_mapping_url, "external_debug_info": r.external_debug_info,
            "truncated": r.truncated, "wat": wat, "glue": glue, "warnings": r.warnings,
        }),
    };
    let ev = builder(
        ctx,
        "formats_wasm_module_show",
        input.subject.clone(),
        json!({"path": input.path, "detail": p.detail, "include_wat": p.include_wat, "wat_offset": p.wat_offset, "wat_limit": wat_limit, "offset": p.offset, "limit": limit, "js_glue_files": p.js_glue_files}),
    )
    .result(result)
    .summary(summary)
    .confidence(Confidence::Observed)
    .authority(Authority::OriginalFiles)
    .limitations(lims)
    .coverage(if p.detail == WasmDetail::Complete { cov } else { Coverage::complete(1) })
    .location(Location::new("path", input.path.display().to_string()))
    .build()?;
    Ok(ToolOutput::evidence(ev))
}

// ---------------------------------------------------------------------------------------------
// EVM

fn formats_evm_interface_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: EvmParams = parse_params(params)?;
    let enc = match p.encoding {
        EvmEncoding::Auto => evm::Encoding::Auto,
        EvmEncoding::Raw => evm::Encoding::Raw,
        EvmEncoding::Hex => evm::Encoding::Hex,
    };
    let (raw, subject, where_from): (Vec<u8>, Option<Subject>, String) = match (&p.path, &p.bytecode) {
        (Some(_), Some(_)) => return Err(ToolError::invalid("pass either path or bytecode, not both")),
        (None, Some(b)) => {
            if b.len() > 2 * evm::MAX_CODE + 16 {
                return Err(ToolError::invalid("bytecode is too long"));
            }
            (b.as_bytes().to_vec(), None, "inline bytecode".to_string())
        }
        (path, None) => {
            let i: Input = static_input::load(ctx, path.as_deref(), 2 * evm::MAX_CODE as u64 + 16)?;
            let w = i.path.display().to_string();
            (i.bytes.to_vec(), Some(i.subject), w)
        }
    };
    let (code, used) = evm::decode_input(&raw, enc).map_err(|e| {
        format_err(e, "EVM bytecode")
            .with_remediation("Pass raw bytes, or hex with an optional 0x prefix and an even number of digits (encoding=hex forces hex).")
    })?;
    let r = evm::analyze(&code).map_err(|e| format_err(e, "EVM bytecode"))?;
    let subject = match subject {
        Some(mut s) => {
            if used == "hex" {
                // The id is about the decoded code; the file hash stays recorded in params.
                s.kind = "evm".into();
            }
            s
        }
        None => Subject { kind: "evm".into(), sha256: Some(sha256_hex(&code)), name: Some("inline bytecode".into()) },
    };
    let shown: Vec<String> = r.functions.iter().take(8).map(|f| format!("{} {}", f.selector, f.mutability)).collect();
    let summary = format!(
        "{} selector(s) found ({} dispatcher{}): {}{}; fallback {}{}.",
        r.functions.len(),
        r.style,
        r.selector_extraction.map(|s| format!(", selector via {s}")).unwrap_or_default(),
        if shown.is_empty() { "none".to_string() } else { shown.join(", ") },
        if r.functions.len() > 8 { ", …" } else { "" },
        r.fallback,
        r.metadata.as_ref().and_then(|m| m.compiler.clone()).map(|c| format!("; compiled by {c}")).unwrap_or_default()
    );
    let mut lims = vec![
        Limitation::new(
            "names_unknown",
            "Function names and argument types are not in the bytecode; match the selectors against an ABI or a signature list to name them.",
        ),
        Limitation::new(
            "mutability_inferred",
            "Payable/non-payable comes from the presence of a CALLVALUE check near each entry; view/pure cannot be told from bytecode alone.",
        ),
        Limitation::new(
            "pattern_dispatch",
            "Dispatchers are recognised by instruction patterns (compare-and-jump, binary-search splits, compare-and-fall-through). Jump-table or hashed dispatchers, proxies and hand-written code may not be recognised.",
        ),
    ];
    if r.style == "vyper-like" || r.style == "mixed" {
        lims.push(Limitation::new("fallthrough_dispatch", "Compare-and-fall-through dispatch was recognised; function entry is the instruction after the check, so offsets point inside the dispatcher region."));
    }
    if r.functions.is_empty() {
        lims.push(Limitation::new(
            "absence_not_proof",
            "No dispatcher found; this does not prove the contract has no public functions (it may be creation code, a proxy or use another dispatch scheme).",
        ));
    }
    let n = r.functions.len() as u64;
    let ev = builder(ctx, "formats_evm_interface_show", subject, json!({"source": where_from, "encoding": p.encoding, "decoded_as": used}))
        .result(json!({
            "decoded_as": used,
            "code_size": r.code_size, "analysed_size": r.analysed_size, "metadata": r.metadata,
            "instructions": r.instructions, "jumpdests": r.jumpdests,
            "selector_extraction": r.selector_extraction, "dispatcher_offset": r.dispatcher_offset, "style": r.style,
            "functions": r.functions, "binary_search_splits": r.binary_search_splits,
            "callvalue_check_before_dispatch": r.callvalue_check_before_dispatch, "short_calldata_check": r.short_calldata_check,
            "fallback": r.fallback, "receive": r.receive,
            "dispatcher_listing": r.dispatcher_listing, "warnings": r.warnings,
        }))
        .summary(summary)
        .confidence(if r.functions.is_empty() { Confidence::Inferred } else { Confidence::Derived })
        .authority(Authority::OriginalFiles)
        .limitations(lims)
        .coverage(Coverage::complete(n))
        .locations(r.functions.iter().take(64).map(|f| Location::new("bytecode_offset", format!("{:#x}", f.bytecode_offset)).with_label(f.selector.clone())))
        .build()?;
    Ok(ToolOutput::evidence(ev))
}

#[cfg(test)]
mod tests {
    use super::super::native_common::test_support::{call, call_err, engine_with};
    use crate::Engine;
    use craft_anything_testkit::formats as fx;
    use craft_anything_testkit::temp_file;
    use serde_json::json;

    #[test]
    fn go_binary_from_path_and_active_target() {
        let e = Engine::new(crate::testing::session());
        let p = temp_file("hello", &fx::go_elf());
        let v = call(&e, "native_go_binary_show", json!({"path": p, "limit": 2}));
        let r = &v["result"];
        assert_eq!(r["buildinfo"]["go_version"], fx::GO_VERSION);
        assert_eq!(r["buildinfo"]["deps"].as_array().unwrap().len(), 2);
        assert_eq!(r["functions"].as_array().unwrap().len(), 2);
        assert_eq!(r["functions"][0]["name"], "main.main");
        assert_eq!(v["coverage"]["next_offset"], 2);
        assert!(v["summary"].as_str().unwrap().contains("go1.21.5"));
        let q = call(&e, "native_go_binary_show", json!({"path": p, "query": "CLIENT"}));
        assert_eq!(q["result"]["functions_matching"], 1);
        let e2 = engine_with("hello-macho", &fx::go_macho());
        let m = call(&e2, "native_go_binary_show", json!({}));
        assert_eq!(m["result"]["buildinfo"]["encoding"], "pointer");
        assert!(m["limitations"].as_array().unwrap().iter().any(|l| l["code"] == "pclntab_scanned"));
        let not_go = engine_with("plain", &craft_anything_testkit::elf64(craft_anything_testkit::ElfArch::X86_64, true).0);
        let n = call(&not_go, "native_go_binary_show", json!({}));
        assert_eq!(n["result"]["is_go"], false);
        let err = call_err(&e, "native_go_binary_show", json!({"path": "relative"}));
        assert_eq!(err.code, craft_anything_evidence::ErrorCode::BadInput);
    }

    #[test]
    fn wasm_module_with_wat_and_glue() {
        let e = Engine::new(crate::testing::session());
        let p = temp_file("demo.wasm", &fx::wasm_module());
        let g = temp_file("demo.js", fx::WASM_GLUE.as_bytes());
        let v = call(&e, "formats_wasm_module_show", json!({"path": p, "include_wat": true, "wat_limit": 30, "js_glue_files": [g]}));
        let r = &v["result"];
        assert_eq!(r["validation"]["valid"], true);
        assert_eq!(r["functions"][0]["name"], "add");
        assert_eq!(r["wat"]["chars"], 30);
        assert_eq!(r["wat"]["next_offset"], 30);
        assert_eq!(r["glue"][0]["scan"]["matched_imports"][0], "env.log");
        let s = call(&e, "formats_wasm_module_show", json!({"path": p, "detail": "summary"}));
        assert_eq!(s["result"]["counts"]["exports"], 3);
        let mut bad = fx::wasm_module();
        bad.truncate(bad.len() - 7);
        let b = call(&e, "formats_wasm_module_show", json!({"path": temp_file("bad.wasm", &bad), "include_wat": true}));
        assert_eq!(b["result"]["validation"]["valid"], false);
        assert!(b["summary"].as_str().unwrap().contains("INVALID"));
        call_err(&e, "formats_wasm_module_show", json!({"path": temp_file("x.wasm", b"nope")}));
    }

    #[test]
    fn evm_interface_inline_and_file() {
        let e = Engine::new(crate::testing::session());
        let (code, _) = fx::evm_runtime();
        let v = call(&e, "formats_evm_interface_show", json!({"bytecode": fx::to_hex(&code)}));
        let r = &v["result"];
        assert_eq!(r["decoded_as"], "hex");
        assert_eq!(r["functions"].as_array().unwrap().len(), 3);
        assert_eq!(r["functions"][2]["mutability"], "payable");
        assert!(v["summary"].as_str().unwrap().contains("solc 0.8.19"));
        let f = call(&e, "formats_evm_interface_show", json!({"path": temp_file("c.bin", &code), "encoding": "raw"}));
        assert_eq!(f["result"]["functions"], r["functions"]);
        let err = call_err(&e, "formats_evm_interface_show", json!({"bytecode": "0x123"}));
        assert!(err.message.contains("odd"));
        call_err(&e, "formats_evm_interface_show", json!({"bytecode": "0xef0001"}));
        call_err(&e, "formats_evm_interface_show", json!({"bytecode": "00", "path": "/x"}));
    }
}
