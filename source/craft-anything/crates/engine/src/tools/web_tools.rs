//! Web scripts and captures, offline: exporting captured scripts, mapping bundle positions back
//! through source maps, inspecting HAR network captures, and recovering readable sources from
//! minified bundles.

use super::artifact_tools::{WalkOptions, abs_path, create_absent_dir, env, read_capped, rel_to, resolve_evidence_input, walk_dir, write_new_file};
use crate::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use craft_anything_analysis::web_har::{HarOptions, inspect_har};
use craft_anything_analysis::web_scripts::{CapturedScript, parse_map, plan_layout, scripts_from_capture, scripts_from_har, trace_location};
use craft_anything_evidence::{
    Authority, Confidence, Coverage, CoverageStatus, ErrorCode, EvidenceBuilder, Limitation, Location, Subject, ToolError, sha256_hex,
};
use craft_anything_js::recover::{RewriteLevel, pretty_print, recover_modules, safe_module_path};
use schemars::JsonSchema;
use serde::Deserialize;
use serde_json::{Value, json};
use std::path::{Path, PathBuf};

pub fn specs() -> Vec<ToolSpec> {
    vec![
        ToolSpec {
            id: "web_scripts_save",
            title: "Export captured scripts",
            summary: "Write the scripts held by a web capture (page inspection or walkthrough evidence, a capture JSON file, or a HAR with saved bodies) into a new folder as files/<host>/<path> plus manifest.json; query variants and collisions get content-hash names with a stated reason. The result names the folder to pass to js_app_map.",
            beginner: "Save the JavaScript a website loaded into a folder you can analyse.",
            toolset: Toolset::Javascript,
            effects: Effects::MUTATES_SESSION.union(Effects::WRITES_FILESYSTEM),
            requires: Requires::Nothing,
            input_schema: schema_of::<ExportParams>,
            run: web_scripts_save,
        },
        ToolSpec {
            id: "js_source_locate",
            title: "Find the original source line",
            summary: "Map a position in generated (bundled/minified) JavaScript back to its original file, line, column and name through a source map (a .map file, a script's sourceMappingURL, or an inline data: map). Lines are 1-based, columns 0-based UTF-16. Returns every original position at that point and nearby original source when the map embeds it.",
            beginner: "Turn a location in squashed website code back into the original source file and line.",
            toolset: Toolset::Javascript,
            effects: Effects::EVIDENCE,
            requires: Requires::Nothing,
            input_schema: schema_of::<TraceLocationParams>,
            run: js_source_locate,
        },
        ToolSpec {
            id: "web_recording_show",
            title: "Inspect a network recording",
            summary: "Read a HAR capture offline: requests, methods, statuses, hosts, timings and an API surface grouped by method + origin + path template, with JSON bodies reduced to outlines (no values). Cookies, credential headers, URL user-info and credential-like query values are never kept; secrets the caller names are redacted in raw, URL-encoded and JSON-escaped forms. Paged (offset/limit) or pick entries with record_numbers.",
            beginner: "Understand which servers an app talked to and what it asked for, from a saved recording, without exposing passwords or cookies.",
            toolset: Toolset::Formats,
            effects: Effects::EVIDENCE,
            requires: Requires::Nothing,
            input_schema: schema_of::<NetworkCaptureParams>,
            run: web_recording_show,
        },
        ToolSpec {
            id: "js_sources_restore",
            title: "Recover readable sources",
            summary: "Turn minified bundles back into readable files in a new folder: split webpack/esbuild/browserify module tables into one file per module, pretty-print everything, apply safe unminify rewrites (!0→true, void 0→undefined, statement sequences, webpack module parameter names via scope analysis) and write original files embedded in source maps. manifest.json records every input digest, module byte range and output file.",
            beginner: "Make squashed JavaScript readable again and split a bundle back into its original pieces.",
            toolset: Toolset::Javascript,
            effects: Effects::MUTATES_SESSION.union(Effects::WRITES_FILESYSTEM),
            requires: Requires::Nothing,
            input_schema: schema_of::<RecoverParams>,
            run: js_sources_restore,
        },
    ]
}

// ---------------------------------------------------------------------------------------------
// web_scripts_save

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ExportParams {
    /// Capture evidence (inline or {"kind":"saved","evidence_id":…}) whose result lists scripts with url and source.
    #[serde(default)]
    pub capture: Option<Value>,
    /// Or an absolute path to a capture JSON file or a HAR file.
    #[serde(default)]
    pub capture_path: Option<String>,
    /// Absolute path of a folder that does not exist yet.
    pub output_directory: String,
    /// Most scripts written.
    #[serde(default = "default_max_scripts")]
    pub max_scripts: usize,
    /// Most bytes written in total.
    #[serde(default = "default_max_bytes")]
    pub max_bytes: u64,
}

fn default_max_scripts() -> usize {
    5_000
}
fn default_max_bytes() -> u64 {
    512 * 1024 * 1024
}

fn web_scripts_save(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ExportParams = parse_params(params)?;
    let mut links = Vec::new();
    let (scripts, source_name): (Vec<CapturedScript>, String) = match (&p.capture, &p.capture_path) {
        (Some(c), None) => {
            let ev = resolve_evidence_input(ctx, c, &[])?;
            links.push(ev.id.clone());
            (scripts_from_capture(&ev.result), ev.subject.name.clone().unwrap_or_else(|| ev.id.clone()))
        }
        (None, Some(path)) => {
            let path = abs_path(path, "capture_path")?;
            let bytes = read_capped(&path, 512 * 1024 * 1024)?;
            let v: Value = serde_json::from_slice(&bytes).map_err(|e| ToolError::invalid(format!("{} is not JSON: {e}", path.display())))?;
            let s = if v.pointer("/log/entries").is_some() { scripts_from_har(&bytes, 200_000).map_err(ToolError::invalid)? } else { scripts_from_capture(&v) };
            (s, path.display().to_string())
        }
        _ => return Err(ToolError::invalid("pass exactly one of capture or capture_path")),
    };
    if scripts.is_empty() {
        return Err(ToolError::invalid("the capture holds no script sources")
            .with_remediation("Captures need script text (url + source); HAR files need saved response bodies."));
    }
    let out = create_absent_dir(&p.output_directory)?;
    let plan = plan_layout(&scripts);
    let mut written = Vec::new();
    let mut skipped = Vec::new();
    let mut total = 0u64;
    for (i, (s, f)) in scripts.iter().zip(plan.iter()).enumerate() {
        if i % 64 == 0 {
            ctx.cancel.check()?;
        }
        if written.len() >= p.max_scripts || total.saturating_add(s.text.len() as u64) > p.max_bytes {
            skipped.push(json!({"url": s.url, "reason": "count or size limit reached"}));
            continue;
        }
        let comps: Vec<String> = f.path.split('/').map(String::from).collect();
        match write_new_file(&out, &comps, s.text.as_bytes()) {
            Ok(_) => {
                total += s.text.len() as u64;
                written.push(f.clone());
            }
            Err(r) => skipped.push(json!({"url": s.url, "reason": r})),
        }
    }
    let manifest = json!({"format": "craft-anything-web-script-export", "version": 1, "source": source_name, "scripts": written, "skipped": skipped});
    let manifest_bytes = serde_json::to_vec_pretty(&manifest).map_err(|e| ToolError::internal(e.to_string()))?;
    write_new_file(&out, &["manifest.json".to_string()], &manifest_bytes).map_err(|e| ToolError::new(ErrorCode::FileError, e))?;
    let files_dir = out.join("files");
    let summary = format!("Exported {} script(s) ({total} bytes) to {}.", written.len(), out.display());
    let mut b = EvidenceBuilder::new("web_scripts_save", Subject { kind: "web-capture".into(), sha256: None, name: Some(source_name) }, env(ctx))
        .params(json!({"output_directory": out, "max_scripts": p.max_scripts}))
        .result(json!({"output_directory": out, "manifest": out.join("manifest.json"), "files_folder": files_dir, "scripts": written, "skipped": skipped, "bytes": total}))
        .summary(summary)
        .confidence(Confidence::Derived)
        .coverage(Coverage { status: if skipped.is_empty() { CoverageStatus::Complete } else { CoverageStatus::Partial }, examined: Some(written.len() as u64), total: Some(scripts.len() as u64), next_offset: None })
        .location(Location::new("path", out.display().to_string()));
    for l in links {
        b = b.link(l);
    }
    Ok(ToolOutput::evidence(b.build()?))
}

// ---------------------------------------------------------------------------------------------
// js_source_locate

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct TraceLocationParams {
    /// Absolute path of the .map file.
    #[serde(default)]
    pub source_map_path: Option<String>,
    /// Or the generated script: its sourceMappingURL (a sibling file or an inline data: URL) is followed.
    #[serde(default)]
    pub script_path: Option<String>,
    /// Generated line, 1-based.
    pub line: u32,
    /// Generated column, 0-based (UTF-16 code units).
    #[serde(default)]
    pub column: u32,
    /// Original-source lines of context around each hit.
    #[serde(default = "default_context")]
    pub context_lines: u32,
}

fn default_context() -> u32 {
    3
}

fn js_source_locate(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: TraceLocationParams = parse_params(params)?;
    if p.line == 0 {
        return Err(ToolError::invalid("line is 1-based; 0 is not a line"));
    }
    let (map_bytes, map_label): (Vec<u8>, String) = match (&p.source_map_path, &p.script_path) {
        (Some(m), _) => {
            let path = abs_path(m, "source_map_path")?;
            (read_capped(&path, 64 * 1024 * 1024)?, path.display().to_string())
        }
        (None, Some(s)) => {
            let path = abs_path(s, "script_path")?;
            let text = String::from_utf8_lossy(&read_capped(&path, 256 * 1024 * 1024)?).into_owned();
            let url = craft_anything_formats::sourcemap::find_source_mapping_url(&text).ok_or_else(|| {
                ToolError::new(ErrorCode::FeatureMissing, format!("{} has no sourceMappingURL comment", path.display()))
                    .with_remediation("Pass source_map_path if you have the map file.")
            })?;
            if url.starts_with("data:") {
                (
                    craft_anything_formats::sourcemap::decode_data_url(&url).ok_or_else(|| ToolError::invalid("the inline source map is not valid base64"))?,
                    "inline map".to_string(),
                )
            } else if url.contains("://") {
                return Err(ToolError::new(ErrorCode::FeatureMissing, format!("the source map lives at {url}; this tool does not download"))
                    .with_remediation("Download the map and pass source_map_path."));
            } else {
                let rel = url.split(['?', '#']).next().unwrap_or(&url);
                let comps = super::artifact_tools::safe_components(rel).map_err(|r| ToolError::invalid(format!("sourceMappingURL {url:?}: {r}")))?;
                let mp = comps.iter().fold(path.parent().map(Path::to_path_buf).unwrap_or_default(), |acc, c| acc.join(c));
                (read_capped(&mp, 64 * 1024 * 1024)?, mp.display().to_string())
            }
        }
        (None, None) => return Err(ToolError::invalid("pass source_map_path or script_path")),
    };
    let map = parse_map(&map_bytes).map_err(|e| ToolError::new(ErrorCode::GarbledOutput, e))?;
    let r = trace_location(&map, p.line, p.column, p.context_lines.min(50));
    let first = r["original_positions"].get(0).cloned();
    let summary = match &first {
        Some(f) => format!(
            "{}:{}:{} maps to {}:{}:{}{}",
            "generated",
            p.line,
            p.column,
            f["source"].as_str().unwrap_or("?"),
            f["line"],
            f["column"],
            f["name"].as_str().map(|n| format!(" ({n})")).unwrap_or_default()
        ),
        None => format!("No mapping at generated {}:{}.", p.line, p.column),
    };
    let ev =
        EvidenceBuilder::new("js_source_locate", Subject { kind: "source-map".into(), sha256: Some(sha256_hex(&map_bytes)), name: Some(map_label) }, env(ctx))
            .params(json!({"line": p.line, "column": p.column, "source_map_path": p.source_map_path, "script_path": p.script_path}))
            .result(r)
            .summary(summary)
            .confidence(Confidence::Derived)
            .limitation(Limitation::new("map_trust", "A source map is the bundler's claim about origins; it can be stale or wrong."))
            .build()?;
    Ok(ToolOutput::evidence(ev))
}

// ---------------------------------------------------------------------------------------------
// web_recording_show

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Deserialize, JsonSchema)]
#[serde(rename_all = "kebab-case")]
pub enum CaptureFormat {
    #[default]
    Auto,
    Har,
    Mitmproxy,
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct NetworkCaptureParams {
    /// Absolute path of the capture file.
    pub path: String,
    #[serde(default)]
    pub format: CaptureFormat,
    /// Only these entries (0-based), in full.
    #[serde(default)]
    pub record_numbers: Option<Vec<usize>>,
    /// Values to redact wherever they appear (tokens, emails, ids). Only their count is recorded.
    #[serde(default)]
    pub hidden_values: Vec<String>,
    #[serde(default)]
    pub offset: usize,
    /// Entries per page (1–1000).
    #[serde(default = "default_entry_limit")]
    pub limit: usize,
}

fn default_entry_limit() -> usize {
    50
}

fn web_recording_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: NetworkCaptureParams = parse_params(params)?;
    let path = abs_path(&p.path, "path")?;
    let bytes = read_capped(&path, 512 * 1024 * 1024)?;
    let looks_json = bytes.iter().find(|b| !b.is_ascii_whitespace()).is_some_and(|b| *b == b'{');
    let lower = path.to_string_lossy().to_ascii_lowercase();
    let mitm_name = lower.ends_with(".mitm") || lower.ends_with(".flow") || lower.ends_with(".flows");
    if p.format == CaptureFormat::Mitmproxy || (p.format == CaptureFormat::Auto && (!looks_json || mitm_name)) {
        return Err(ToolError::new(ErrorCode::FeatureMissing, "native mitmproxy flow files are not read by the built-in engine yet")
            .with_remediation("Export the flows to HAR first (in mitmproxy: `mitmdump -nr flows.mitm --set hardump=capture.har`), then inspect the HAR."));
    }
    let limit = p.limit.clamp(1, 1000);
    let opts = HarOptions { hidden_values: p.hidden_values.clone(), offset: p.offset, limit, record_numbers: p.record_numbers.clone(), max_entries: 500_000 };
    let r = inspect_har(&bytes, &opts).map_err(|e| {
        ToolError::new(ErrorCode::GarbledOutput, format!("{}: {e}", path.display()))
            .with_remediation("Pass a HAR 1.2 file (browser dev tools: Save all as HAR).")
    })?;
    let total = r["entries_total"].as_u64().unwrap_or(0);
    let shown = r["entries"].as_array().map_or(0, Vec::len) as u64;
    let file_digest = sha256_hex(&bytes);
    // A file whose digest is itself a declared secret must not leak through the subject.
    let digest_is_secret = p.hidden_values.contains(&file_digest);
    let name = path.file_name().map(|n| n.to_string_lossy().into_owned()).filter(|n| !p.hidden_values.iter().any(|s| !s.is_empty() && n.contains(s.as_str())));
    let summary = format!(
        "{} requests to {} host(s); {} API operation(s); statuses {}.",
        r["summary"]["entries"],
        r["summary"]["hosts"].as_object().map_or(0, |m| m.len()),
        r["api_surface"].as_array().map_or(0, Vec::len),
        r["summary"]["statuses"].as_object().map(|m| m.iter().map(|(k, v)| format!("{k}×{v}")).collect::<Vec<_>>().join(", ")).unwrap_or_default()
    );
    let coverage = if p.record_numbers.is_some() {
        Coverage { status: CoverageStatus::Partial, examined: Some(shown), total: Some(total), next_offset: None }
    } else {
        Coverage::page(shown, total, p.offset as u64)
    };
    let mut b = EvidenceBuilder::new(
        "web_recording_show",
        Subject { kind: "capture".into(), sha256: (!digest_is_secret).then_some(file_digest), name },
        env(ctx),
    )
    .params(
        json!({"format": "har", "offset": p.offset, "limit": limit, "record_numbers": p.record_numbers, "sensitive_value_declarations": p.hidden_values.len()}),
    )
    .result(r)
    .summary(summary)
    .confidence(Confidence::Observed)
    .authority(Authority::EarlierRecord)
    .limitation(Limitation::new("values_not_kept", "Body values, cookies and credentials are deliberately not kept; JSON bodies are reduced to their outline."))
    .limitation(Limitation::new("historical", "A recording shows what happened once, not every request the app can make."))
    .coverage(coverage);
    if total == 0 {
        b = b.limitation(Limitation::new("empty", "The capture has no entries."));
    }
    Ok(ToolOutput::evidence(b.build()?))
}

// ---------------------------------------------------------------------------------------------
// js_sources_restore

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Deserialize, JsonSchema)]
#[serde(rename_all = "kebab-case")]
pub enum ExtractionMode {
    /// Split only recognised bundle module tables; pretty-print everything; write source-map originals.
    #[default]
    Structural,
    /// Pretty-print only (no splitting, no source-map originals).
    Inspection,
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Deserialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum RewriteParam {
    None,
    #[default]
    Standard,
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct RecoverParams {
    /// Absolute path of a script or a folder of scripts.
    pub path: String,
    /// Up to 16 more scripts or folders.
    #[serde(default)]
    pub additional_paths: Vec<String>,
    #[serde(default)]
    pub extraction_mode: ExtractionMode,
    #[serde(default)]
    pub rewrite_level: RewriteParam,
    /// Absolute path of a folder that does not exist yet.
    pub output_directory: String,
    /// Most input scripts.
    #[serde(default = "default_recover_files")]
    pub max_files: usize,
    /// Largest input script.
    #[serde(default = "default_recover_bytes")]
    pub max_file_bytes: u64,
    #[serde(default)]
    pub offset: usize,
    /// Output files listed per page in the result.
    #[serde(default = "default_recover_limit")]
    pub limit: usize,
}

fn default_recover_files() -> usize {
    2_000
}
fn default_recover_bytes() -> u64 {
    64 * 1024 * 1024
}
fn default_recover_limit() -> usize {
    500
}

type Scripts = Vec<(String, PathBuf)>;

fn collect_scripts(ctx: &Ctx<'_>, roots: &[String], max_files: usize) -> Result<(Scripts, Vec<String>), ToolError> {
    let mut out = Vec::new();
    let mut notes = Vec::new();
    for r in roots {
        let path = abs_path(r, "path")?;
        let meta = std::fs::metadata(&path).map_err(|e| ToolError::io(path.display(), e))?;
        let base = path.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_else(|| "input".into());
        if meta.is_dir() {
            let skip = |rel: &str| rel.ends_with("node_modules");
            let w = walk_dir(
                &path,
                &WalkOptions { max_files: max_files.saturating_mul(4), max_depth: 32, skip_dir: &skip, gitignore: false, include_hidden: false },
                &ctx.cancel,
            )?;
            if w.truncated {
                notes.push(format!("{base}: the folder listing was cut short by the file-count or depth limit"));
            }
            for f in w.files.into_iter().filter(|f| craft_anything_analysis::js_app::is_script(&f.rel)) {
                out.push((format!("{base}/{}", f.rel), f.abs));
            }
        } else {
            out.push((base, path));
        }
        if out.len() >= max_files {
            out.truncate(max_files);
            break;
        }
    }
    Ok((out, notes))
}

fn js_sources_restore(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: RecoverParams = parse_params(params)?;
    if p.additional_paths.len() > 16 {
        return Err(ToolError::invalid("at most 16 additional_paths"));
    }
    let mut roots = vec![p.path.clone()];
    roots.extend(p.additional_paths.iter().cloned());
    let (inputs, mut notes) = collect_scripts(ctx, &roots, p.max_files.max(1))?;
    if inputs.is_empty() {
        return Err(ToolError::invalid("no JavaScript files found in the inputs"));
    }
    let out = create_absent_dir(&p.output_directory)?;
    let level = match p.rewrite_level {
        RewriteParam::None => RewriteLevel::None,
        RewriteParam::Standard => RewriteLevel::Standard,
    };
    let limits = craft_anything_js::Limits::default();
    let mut outputs: Vec<Value> = Vec::new();
    let mut provenance: Vec<Value> = Vec::new();
    let (mut modules_total, mut originals_total, mut printed) = (0usize, 0usize, 0usize);
    for (n, (rel, abs)) in inputs.iter().enumerate() {
        ctx.cancel.check()?;
        ctx.report(Some(n as f32 / inputs.len() as f32), format!("Recovering {rel}"));
        let bytes = match read_capped(abs, p.max_file_bytes) {
            Ok(b) => b,
            Err(e) => {
                notes.push(format!("{rel}: {}", e.message));
                continue;
            }
        };
        let text = String::from_utf8_lossy(&bytes).into_owned();
        let in_sha = sha256_hex(&bytes);
        let stem = safe_module_path(rel, ".js");
        let mut record = json!({"input": rel, "sha256": in_sha, "bytes": bytes.len()});
        // Whole-file pretty print.
        match pretty_print(rel, &text, level, &limits) {
            Ok((pretty, rewrites)) => {
                let comps: Vec<String> = format!("pretty/{stem}").split('/').map(String::from).collect();
                if let Ok(written) = write_new_file(&out, &comps, pretty.as_bytes()) {
                    printed += 1;
                    outputs.push(
                        json!({"path": rel_to(&out, &written), "kind": "pretty", "from": rel, "sha256": sha256_hex(pretty.as_bytes()), "rewrites": rewrites}),
                    );
                }
            }
            Err(e) => notes.push(format!("{rel}: not pretty-printed ({e})")),
        }
        if p.extraction_mode == ExtractionMode::Structural {
            let a = craft_anything_js::analyze(rel, &text, &limits);
            if !a.bundle.modules.is_empty() {
                let recovered = recover_modules(&text, &a.bundle.modules, level, &limits);
                let dir = format!("modules/{}", stem.trim_end_matches(".js"));
                let mut mods = Vec::new();
                for m in recovered {
                    ctx.cancel.check()?;
                    let comps: Vec<String> = format!("{dir}/{}", m.file_name).split('/').map(String::from).collect();
                    match write_new_file(&out, &comps, m.text.as_bytes()) {
                        Ok(w) => {
                            modules_total += 1;
                            let path = rel_to(&out, &w);
                            mods.push(json!({"id": m.id, "format": m.format, "byte_range": [m.start, m.end], "source_sha256": m.source_sha256, "output": path, "renamed": m.renamed, "rewrites": m.rewrites, "printed": m.printed, "note": m.note}));
                            outputs.push(json!({"path": path, "kind": "module", "from": rel, "id": m.id}));
                        }
                        Err(e) => notes.push(format!("{rel} module {}: {e}", m.id)),
                    }
                }
                record["bundlers"] = json!(a.bundle.bundlers);
                record["modules"] = json!(mods);
            } else if !a.bundle.bundlers.is_empty() {
                notes
                    .push(format!("{rel}: {} output has no module boundaries left to split (scope-hoisted); pretty-printed only", a.bundle.bundlers.join("/")));
            }
            // Originals embedded in a source map.
            if let Some(map) = find_map(abs, a.facts.source_map_url.as_deref()) {
                for i in 0..map.sources.len() as u32 {
                    let (Some(src), Some(content)) = (map.source_path(i), map.source_content(i)) else { continue };
                    if map.ignore_list.contains(&i) || src.contains("node_modules") {
                        continue;
                    }
                    let target = format!("sources/{}/{}", stem.trim_end_matches(".js"), safe_module_path(&src, ""));
                    let comps: Vec<String> = target.split('/').filter(|c| !c.is_empty()).map(String::from).collect();
                    match write_new_file(&out, &comps, content.as_bytes()) {
                        Ok(w) => {
                            originals_total += 1;
                            outputs.push(json!({"path": rel_to(&out, &w), "kind": "original-source", "from": rel, "source_map_source": src}));
                        }
                        Err(e) => notes.push(format!("{rel} original {src}: {e}")),
                    }
                }
            }
        }
        provenance.push(record);
    }
    let manifest = json!({"format": "craft-anything-recovery", "version": 1, "rewrite_level": format!("{level:?}").to_lowercase(), "inputs": provenance, "outputs": outputs, "notes": notes});
    let mb = serde_json::to_vec_pretty(&manifest).map_err(|e| ToolError::internal(e.to_string()))?;
    write_new_file(&out, &["manifest.json".to_string()], &mb).map_err(|e| ToolError::new(ErrorCode::FileError, e))?;
    let limit = p.limit.clamp(1, 10_000);
    let page: Vec<&Value> = outputs.iter().skip(p.offset).take(limit).collect();
    let summary = format!(
        "Recovered {} input(s) into {}: {printed} pretty-printed, {modules_total} bundle module file(s), {originals_total} original source(s) from maps.",
        inputs.len(),
        out.display()
    );
    let ev = EvidenceBuilder::new("js_sources_restore", Subject { kind: "javascript".into(), sha256: None, name: Some(p.path.clone()) }, env(ctx))
        .params(json!({"path": p.path, "additional_paths": p.additional_paths, "output_directory": out, "extraction_mode": format!("{:?}", p.extraction_mode).to_lowercase(), "rewrite_level": format!("{level:?}").to_lowercase()}))
        .result(json!({"output_directory": out, "manifest": out.join("manifest.json"), "inputs": provenance, "outputs": page, "outputs_total": outputs.len(), "notes": notes}))
        .summary(summary)
        .confidence(Confidence::Derived)
        .limitation(Limitation::new("rewrites_conservative", "Only rewrites that provably keep meaning are applied; local variable names stay minified."))
        .limitation(Limitation::new("scope_hoisted", "Rollup/Vite production chunks merge modules into one scope; they are pretty-printed but not split."))
        .coverage(Coverage::page(page.len() as u64, outputs.len() as u64, p.offset as u64))
        .location(Location::new("path", out.display().to_string()))
        .build()?;
    Ok(ToolOutput::evidence(ev))
}

fn find_map(script: &Path, url: Option<&str>) -> Option<craft_anything_formats::sourcemap::SourceMap> {
    let bytes = match url {
        Some(u) if u.starts_with("data:") => craft_anything_formats::sourcemap::decode_data_url(u)?,
        Some(u) if !u.contains("://") => {
            let comps = super::artifact_tools::safe_components(u.split(['?', '#']).next().unwrap_or(u)).ok()?;
            let p = comps.iter().fold(script.parent()?.to_path_buf(), |acc, c| acc.join(c));
            read_capped(&p, 64 * 1024 * 1024).ok()?
        }
        _ => {
            let side = script.with_file_name(format!("{}.map", script.file_name()?.to_string_lossy()));
            read_capped(&side, 64 * 1024 * 1024).ok()?
        }
    };
    parse_map(&bytes).ok()
}

#[cfg(test)]
mod tests {
    use crate::{CallOptions, Caller, Engine};
    use craft_anything_evidence::{ErrorCode, ToolError};
    use craft_anything_testkit::electron as fx;
    use serde_json::{Value, json};

    fn call(e: &Engine, id: &str, p: Value) -> Result<Value, ToolError> {
        e.call(id, p, CallOptions::new(Caller::Mcp)).map(|o| o.to_json())
    }

    #[test]
    fn recover_splits_and_writes_originals() {
        let dir = tempfile::tempdir().unwrap();
        let src = dir.path().join("dist");
        std::fs::create_dir(&src).unwrap();
        std::fs::write(src.join("main.js"), fx::WEBPACK_BUNDLE).unwrap();
        std::fs::write(src.join("179.js"), fx::WEBPACK_CHUNK).unwrap();
        std::fs::write(src.join("main.js.map"), r#"{"version":3,"sources":["webpack:///./src/api.js","webpack:///./node_modules/x/y.js"],"sourcesContent":["export const api = 1;\n","vendor"],"names":[],"mappings":"AAAA"}"#).unwrap();
        let out = dir.path().join("recovered");
        let e = Engine::new(crate::testing::session());
        let r = call(&e, "js_sources_restore", json!({"path": src, "output_directory": out})).unwrap();
        assert!(out.join("manifest.json").exists());
        let m179 = std::fs::read_to_string(out.join("modules/dist/179/512.js")).unwrap();
        assert!(m179.contains("module.exports = function"), "{m179}");
        assert!(out.join("modules/dist/main/src/api.js").exists());
        assert_eq!(std::fs::read_to_string(out.join("sources/dist/main/src/api.js")).unwrap(), "export const api = 1;\n");
        assert!(!out.join("sources/dist/main/node_modules").exists());
        let pretty = std::fs::read_to_string(out.join("pretty/dist/main.js")).unwrap();
        assert!(pretty.contains("true") && pretty.lines().count() > 5);
        assert!(r["summary"].as_str().unwrap().contains("bundle module"));
        // The output folder must not exist.
        let again = call(&e, "js_sources_restore", json!({"path": src, "output_directory": out})).unwrap_err();
        assert_eq!(again.code, ErrorCode::BadInput);
    }

    #[test]
    fn recover_records_folder_truncation_notes() {
        let dir = tempfile::tempdir().unwrap();
        let dist = dir.path().join("dist");
        std::fs::create_dir(&dist).unwrap();
        std::fs::write(dist.join("aa-app.js"), "console.log(1);\n").unwrap();
        std::fs::write(dist.join("zz-app.js"), "console.log(2);\n").unwrap();
        for n in 0..7 {
            std::fs::write(dist.join(format!("asset-{n}.txt")), "x\n").unwrap();
        }
        let e = Engine::new(crate::testing::session());
        let out_capped = dir.path().join("capped");
        let r = call(&e, "js_sources_restore", json!({"path": dist, "output_directory": out_capped, "max_files": 2})).unwrap();
        let expected = json!(["dist: the folder listing was cut short by the file-count or depth limit"]);
        assert_eq!(r["result"]["notes"], expected);
        let manifest: Value = serde_json::from_slice(&std::fs::read(out_capped.join("manifest.json")).unwrap()).unwrap();
        assert_eq!(manifest["notes"], expected);

        let out_full = dir.path().join("full");
        let r_full = call(&e, "js_sources_restore", json!({"path": dist, "output_directory": out_full, "max_files": 3})).unwrap();
        assert_eq!(r_full["result"]["notes"], json!([]));
    }

    #[test]
    fn source_location_via_script() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join("app.js"), "a();b();\n//# sourceMappingURL=app.js.map\n").unwrap();
        std::fs::write(
            dir.path().join("app.js.map"),
            r#"{"version":3,"sources":["src/app.ts"],"names":["start"],"mappings":"AAAA,IAEEA","sourcesContent":["// x\n\nfunction start() {}\n"]}"#,
        )
        .unwrap();
        let e = Engine::new(crate::testing::session());
        let r = call(&e, "js_source_locate", json!({"script_path": dir.path().join("app.js"), "line": 1, "column": 5})).unwrap();
        assert_eq!(r["result"]["original_positions"][0]["source"], "src/app.ts");
        assert_eq!(r["result"]["original_positions"][0]["line"], 3);
        assert_eq!(r["result"]["original_positions"][0]["name"], "start");
        assert!(call(&e, "js_source_locate", json!({"script_path": dir.path().join("app.js"), "line": 0})).is_err());
    }

    #[test]
    fn network_capture_and_export() {
        let dir = tempfile::tempdir().unwrap();
        let har = json!({"log": {"version": "1.2", "entries": [
            {"startedDateTime": "2026-01-01T00:00:00Z", "time": 10, "request": {"method": "GET", "url": "https://app.test/assets/index-abc.js", "headers": [{"name": "Cookie", "value": "s=SECRETCOOKIE"}]},
             "response": {"status": 200, "headers": [], "content": {"size": 9, "mimeType": "application/javascript", "text": "fetch('/api/notes')"}}},
            {"startedDateTime": "2026-01-01T00:00:01Z", "time": 20, "request": {"method": "POST", "url": "https://app.test/api/notes/12", "headers": [{"name": "Authorization", "value": "Bearer tok-123"}],
             "postData": {"mimeType": "application/json", "text": "{\"title\":\"my diary tok-123\"}"}},
             "response": {"status": 201, "headers": [], "content": {"size": 2, "mimeType": "application/json", "text": "{\"id\":12}"}}}
        ]}});
        let hp = dir.path().join("cap.har");
        std::fs::write(&hp, serde_json::to_vec(&har).unwrap()).unwrap();
        let e = Engine::new(crate::testing::session());
        let r = call(&e, "web_recording_show", json!({"path": hp, "hidden_values": ["tok-123"]})).unwrap();
        let text = r.to_string();
        assert!(!text.contains("SECRETCOOKIE") && !text.contains("tok-123") && !text.contains("my diary"), "{text}");
        assert_eq!(r["authority"], "earlier-record");
        assert_eq!(r["params"]["sensitive_value_declarations"], 1);
        assert!(r["result"]["api_surface"].as_array().unwrap().iter().any(|o| o["operation"] == "POST https://app.test/api/notes/{n}"));
        let mitm = dir.path().join("flows.mitm");
        std::fs::write(&mitm, b"\x00\x01binary").unwrap();
        assert_eq!(call(&e, "web_recording_show", json!({"path": mitm})).unwrap_err().code, ErrorCode::FeatureMissing);
        // Export the scripts the HAR saved, then analyse the folder.
        let out = dir.path().join("export");
        let x = call(&e, "web_scripts_save", json!({"capture_path": hp, "output_directory": out})).unwrap();
        assert!(out.join("files/app.test/assets/index-abc.js").exists());
        let input = x["result"]["files_folder"].as_str().unwrap().to_string();
        let a = call(&e, "js_app_map", json!({"input_path": input})).unwrap();
        assert!(a["result"]["endpoints"].as_array().unwrap().iter().any(|ep| ep["url"] == "/api/notes"));
    }
}
