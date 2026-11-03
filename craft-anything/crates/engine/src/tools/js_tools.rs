//! JavaScript applications: static analysis of Electron apps (ASAR or unpacked), web bundles and
//! Node packages into an application graph, and reconciling that graph with runtime captures.

use super::artifact_tools::{WalkOptions, abs_path, env, is_path_input, read_capped, resolve_evidence_input, walk_dir};
use crate::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use craft_anything_analysis::js_app::{AppFile, AppGraph, AppInput, AppOptions, analyze_application, is_script};
use craft_anything_analysis::js_trace::{RuntimeScript, reconcile, runtime_scripts_from};
use craft_anything_evidence::{Confidence, Coverage, ErrorCode, EvidenceBuilder, Limitation, Location, Subject, ToolError, sha256_hex};
use craft_anything_formats::{asar, zip};
use schemars::JsonSchema;
use serde::Deserialize;
use serde_json::{Value, json};
use std::path::{Path, PathBuf};

pub fn specs() -> Vec<ToolSpec> {
    vec![
        ToolSpec {
            id: "js_app_map",
            title: "Analyse a JavaScript app",
            summary: "Static analysis of an Electron app (app.asar or unpacked folder), a web bundle folder, a ZIP or a single script into an application graph: package and entry points (main, preload, renderer), BrowserWindow webPreferences, the IPC channel map (ipcMain.handle/on ↔ ipcRenderer.invoke/send, contextBridge members), module imports, bundler and chunk splitting (webpack, esbuild, browserify; Vite/Rollup detected), routes, HTTP endpoints, storage, platform effects, native modules, vendors and source maps. Built-in parser; nothing is executed.",
            beginner: "Look inside a desktop app built with web technology (Electron) or a website's code, and map how its pieces talk to each other.",
            toolset: Toolset::Javascript,
            effects: Effects::EVIDENCE,
            requires: Requires::Nothing,
            input_schema: schema_of::<AnalyzeParams>,
            run: js_app_map,
        },
        ToolSpec {
            id: "js_runtime_code_match",
            title: "Match static code to what ran",
            summary: "Match app graph evidence against what was seen running (captured scripts with URLs and sha256): each static module is loaded, resident in a loaded bundle, loaded with different content, not observed, or unknown; runtime-only scripts are listed. Pure computation over evidence.",
            beginner: "Check which parts of an app's code actually ran in a recording.",
            toolset: Toolset::Javascript,
            effects: Effects::EVIDENCE,
            requires: Requires::Nothing,
            input_schema: schema_of::<ReconcileParams>,
            run: js_runtime_code_match,
        },
    ]
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Deserialize, JsonSchema)]
#[serde(rename_all = "kebab-case")]
pub enum InputFormat {
    /// Detect from the path: folder, ASAR, ZIP or single file.
    #[default]
    Auto,
    Asar,
    Directory,
    Zip,
    File,
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Deserialize, JsonSchema)]
#[serde(rename_all = "kebab-case")]
pub enum IntegrityPolicy {
    /// Stop when an ASAR integrity hash does not match its file.
    #[default]
    Fail,
    /// Record the mismatch as a limitation and continue.
    Continue,
}

#[derive(Debug, Clone, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct AnalyzeParams {
    /// Absolute path of an app.asar, an unpacked Electron app or web bundle folder, a ZIP, or one .js/.html file.
    pub input_path: String,
    #[serde(default)]
    pub format: InputFormat,
    #[serde(default)]
    pub if_tampered: IntegrityPolicy,
    /// Extra absolute files or folders to include (for example an `app.asar.unpacked` folder kept elsewhere).
    #[serde(default)]
    pub source_paths: Vec<String>,
    /// Also parse code under node_modules (off: only their package.json files are read, as vendor facts).
    #[serde(default)]
    pub include_node_modules: bool,
    /// Most files read.
    #[serde(default = "default_max_files")]
    pub max_files: usize,
    /// Largest single file read.
    #[serde(default = "default_max_file_bytes")]
    pub max_file_bytes: u64,
    /// Most bytes read in total.
    #[serde(default = "default_max_total_bytes")]
    pub max_total_bytes: u64,
    /// Most graph nodes kept.
    #[serde(default = "default_max_nodes")]
    pub max_nodes: usize,
    /// First module of the module page in the result.
    #[serde(default)]
    pub offset: usize,
    /// Modules per page in the result (the graph itself is always complete up to max_nodes).
    #[serde(default = "default_module_limit")]
    pub limit: usize,
}

fn default_max_files() -> usize {
    20_000
}
fn default_max_file_bytes() -> u64 {
    32 * 1024 * 1024
}
fn default_max_total_bytes() -> u64 {
    512 * 1024 * 1024
}
fn default_max_nodes() -> usize {
    25_000
}
fn default_module_limit() -> usize {
    500
}

impl AnalyzeParams {
    pub(crate) fn for_path(p: &str) -> Self {
        AnalyzeParams {
            input_path: p.into(),
            format: InputFormat::Auto,
            if_tampered: IntegrityPolicy::Continue,
            source_paths: Vec::new(),
            include_node_modules: false,
            max_files: default_max_files(),
            max_file_bytes: default_max_file_bytes(),
            max_total_bytes: default_max_total_bytes(),
            max_nodes: default_max_nodes(),
            offset: 0,
            limit: default_module_limit(),
        }
    }
}

/// Which files we read bytes for (everything else is listed only).
fn wanted(path: &str, include_node_modules: bool) -> bool {
    let l = path.to_ascii_lowercase();
    if l.contains("node_modules/") {
        if include_node_modules {
            return is_script(&l) || l.ends_with("package.json");
        }
        // node_modules/<pkg>/package.json or node_modules/@scope/<pkg>/package.json only.
        let after = l.rsplit("node_modules/").next().unwrap_or("");
        let depth = after.matches('/').count();
        return l.ends_with("/package.json") && (depth == 1 || (after.starts_with('@') && depth == 2));
    }
    is_script(&l) || l.ends_with(".html") || l.ends_with(".htm") || l.ends_with(".json") || l.ends_with(".map")
}

struct Budget {
    files: usize,
    bytes: u64,
    max_files: usize,
    max_bytes: u64,
    max_file: u64,
    skipped: usize,
}

impl Budget {
    fn admit(&mut self, size: u64) -> bool {
        if self.files >= self.max_files || size > self.max_file || self.bytes.saturating_add(size) > self.max_bytes {
            self.skipped += 1;
            return false;
        }
        self.files += 1;
        self.bytes += size;
        true
    }
}

/// Read an input into files for the analyser. Returns the input, its subject, integrity problems
/// and the folders that couldn't be listed, as (path, reason).
#[allow(clippy::type_complexity)]
pub(crate) fn load_app_input(ctx: &Ctx<'_>, p: &AnalyzeParams) -> Result<(AppInput, Subject, Vec<String>, Vec<(String, String)>), ToolError> {
    let path = abs_path(&p.input_path, "input_path")?;
    let meta = std::fs::metadata(&path).map_err(|e| ToolError::io(path.display(), e))?;
    let label = path.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_else(|| path.display().to_string());
    let mut budget = Budget { files: 0, bytes: 0, max_files: p.max_files.max(1), max_bytes: p.max_total_bytes, max_file: p.max_file_bytes, skipped: 0 };
    let mut input = AppInput { label: label.clone(), ..Default::default() };
    let mut integrity = Vec::new();
    let mut unlisted = Vec::new();
    let format = match p.format {
        InputFormat::Auto if meta.is_dir() => InputFormat::Directory,
        InputFormat::Auto => {
            let head = read_head(&path)?;
            if asar::looks_like_asar(&head) {
                InputFormat::Asar
            } else if zip::looks_like_zip(&head) {
                InputFormat::Zip
            } else {
                InputFormat::File
            }
        }
        f => f,
    };
    let subject;
    match format {
        InputFormat::Directory => {
            input.format = "directory".into();
            let include = p.include_node_modules;
            let skip = move |rel: &str| !include && rel.ends_with("node_modules") && rel.matches("node_modules").count() > 1;
            let walked = walk_dir(
                &path,
                &WalkOptions { max_files: p.max_files.saturating_mul(4).max(1000), max_depth: 48, skip_dir: &skip, gitignore: false, include_hidden: false },
                &ctx.cancel,
            )?;
            if walked.truncated {
                input.notes.push("the folder listing was cut short by the file-count or depth limit".into());
            }
            unlisted.extend(walked.unlisted.iter().cloned());
            // A packaged app folder: analyse its app.asar when there is no package.json of its own.
            let has_pkg = walked.files.iter().any(|f| f.rel == "package.json" || (f.rel.ends_with("/package.json") && !f.rel.contains("node_modules/")));
            let asars: Vec<&super::artifact_tools::WalkedFile> = walked.files.iter().filter(|f| f.rel.ends_with("app.asar")).collect();
            if !has_pkg
                && asars.len() == 1
                && let Some(a) = asars.first()
            {
                let mut q = p.clone();
                q.input_path = a.abs.display().to_string();
                q.format = InputFormat::Asar;
                let (mut inp, subj, integ, mut gaps) = load_app_input(ctx, &q)?;
                inp.notes.push(format!("analysed {} found inside the folder", a.rel));
                unlisted.append(&mut gaps);
                return Ok((inp, subj, integ, unlisted));
            }
            let mut listing_hash = Vec::new();
            for f in &walked.files {
                ctx.cancel.check()?;
                input.listing.push((f.rel.clone(), f.size));
                listing_hash.push(json!([f.rel, f.size]));
                if wanted(&f.rel, p.include_node_modules) && budget.admit(f.size) {
                    match std::fs::read(&f.abs) {
                        Ok(b) => input.files.push(AppFile { path: f.rel.clone(), bytes: b }),
                        Err(e) => input.notes.push(format!("{}: {e}", f.rel)),
                    }
                }
            }
            let digest = sha256_hex(
                craft_anything_evidence::canonical_json(&json!(input.files.iter().map(|f| (&f.path, sha256_hex(&f.bytes))).collect::<Vec<_>>())).as_bytes(),
            );
            subject = Subject { kind: "js-app".into(), sha256: Some(digest), name: Some(label) };
        }
        InputFormat::Asar => {
            input.format = "asar".into();
            let bytes = read_capped(&path, crate::target::MAX_TARGET_BYTES)?;
            let a = asar::parse(&bytes, p.max_files.saturating_mul(4).max(1000))
                .map_err(|e| ToolError::new(ErrorCode::GarbledOutput, format!("{}: {e}", path.display())))?;
            if a.truncated {
                input.notes.push("the ASAR listing was cut short by the file-count limit".into());
            }
            for r in &a.rejected_names {
                input.notes.push(format!("skipped ASAR entry with an unsafe name: {r}"));
            }
            let unpacked_root = PathBuf::from(format!("{}.unpacked", path.display()));
            for e in a.entries.iter().filter(|e| e.kind == asar::AsarKind::File) {
                ctx.cancel.check()?;
                input.listing.push((e.path.clone(), e.size));
                if !wanted(&e.path, p.include_node_modules) || !budget.admit(e.size) {
                    continue;
                }
                if e.unpacked {
                    if let Ok(comps) = super::artifact_tools::safe_components(&e.path) {
                        let src = comps.iter().fold(unpacked_root.clone(), |acc, c| acc.join(c));
                        if std::fs::symlink_metadata(&src).is_ok_and(|m| m.is_file())
                            && let Ok(b) = std::fs::read(&src)
                        {
                            input.files.push(AppFile { path: e.path.clone(), bytes: b });
                        }
                    }
                    continue;
                }
                match asar::file_bytes(&bytes, &a, e) {
                    Some(d) => {
                        if let Some(i) = &e.integrity
                            && i.algorithm.eq_ignore_ascii_case("sha256")
                            && sha256_hex(d) != i.hash
                        {
                            integrity.push(e.path.clone());
                        }
                        input.files.push(AppFile { path: e.path.clone(), bytes: d.to_vec() });
                    }
                    None => input.notes.push(format!("{}: data lies outside the archive", e.path)),
                }
            }
            subject = Subject { kind: "asar".into(), sha256: Some(sha256_hex(&bytes)), name: Some(label) };
        }
        InputFormat::Zip => {
            input.format = "zip".into();
            let bytes = read_capped(&path, crate::target::MAX_TARGET_BYTES)?;
            let z = zip::parse(&bytes, p.max_files.saturating_mul(4).max(1000))
                .map_err(|e| ToolError::new(ErrorCode::GarbledOutput, format!("{}: {e}", path.display())))?;
            for e in z.entries.iter().filter(|e| !e.is_dir) {
                ctx.cancel.check()?;
                input.listing.push((e.name.clone(), e.uncompressed_size));
                if super::artifact_tools::safe_components(&e.name).is_err() {
                    input.notes.push(format!("skipped ZIP entry with an unsafe name: {}", e.name));
                    continue;
                }
                if !wanted(&e.name, p.include_node_modules) || !budget.admit(e.uncompressed_size) {
                    continue;
                }
                match zip::read_entry(&bytes, e, p.max_file_bytes) {
                    Ok(d) => input.files.push(AppFile { path: e.name.trim_start_matches("./").to_string(), bytes: d }),
                    Err(err) => input.notes.push(format!("{}: {err}", e.name)),
                }
            }
            subject = Subject { kind: "zip".into(), sha256: Some(sha256_hex(&bytes)), name: Some(label) };
        }
        InputFormat::File | InputFormat::Auto => {
            input.format = "file".into();
            let bytes = read_capped(&path, p.max_file_bytes)?;
            subject = Subject { kind: "script".into(), sha256: Some(sha256_hex(&bytes)), name: Some(label.clone()) };
            input.listing.push((label.clone(), bytes.len() as u64));
            // A sibling source map is worth reading.
            let map = path.with_file_name(format!("{label}.map"));
            if let Ok(m) = std::fs::symlink_metadata(&map)
                && m.is_file()
                && m.len() <= p.max_file_bytes
                && let Ok(mb) = std::fs::read(&map)
            {
                input.listing.push((format!("{label}.map"), mb.len() as u64));
                input.files.push(AppFile { path: format!("{label}.map"), bytes: mb });
            }
            input.files.push(AppFile { path: label, bytes });
        }
    }
    for extra in &p.source_paths {
        let ep = abs_path(extra, "source_paths entry")?;
        let base = ep.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
        if ep.is_dir() {
            let skip = |_: &str| false;
            let walked =
                walk_dir(&ep, &WalkOptions { max_files: p.max_files, max_depth: 48, skip_dir: &skip, gitignore: false, include_hidden: false }, &ctx.cancel)?;
            unlisted.extend(walked.unlisted.iter().map(|(rel, e)| (format!("{base}/{rel}"), e.clone())));
            for f in &walked.files {
                let rel = format!("{base}/{}", f.rel);
                input.listing.push((rel.clone(), f.size));
                if wanted(&rel, p.include_node_modules)
                    && budget.admit(f.size)
                    && let Ok(b) = std::fs::read(&f.abs)
                {
                    input.files.push(AppFile { path: rel, bytes: b });
                }
            }
        } else if let Ok(b) = read_capped(&ep, p.max_file_bytes) {
            input.listing.push((base.clone(), b.len() as u64));
            input.files.push(AppFile { path: base, bytes: b });
        }
    }
    if budget.skipped > 0 {
        input.notes.push(format!("{} file(s) were listed but not read because of the size or count limits", budget.skipped));
    }
    Ok((input, subject, integrity, unlisted))
}

fn read_head(path: &Path) -> Result<Vec<u8>, ToolError> {
    use std::io::Read as _;
    let mut f = std::fs::File::open(path).map_err(|e| ToolError::io(path.display(), e))?;
    let mut buf = vec![0u8; 64];
    let n = f.read(&mut buf).map_err(|e| ToolError::io(path.display(), e))?;
    buf.truncate(n);
    Ok(buf)
}

/// Load and analyse; shared with the application tools for path inputs.
/// A graph, its subject, its limitations and (files read, files listed).
pub(crate) type Analyzed = (AppGraph, Subject, Vec<Limitation>, (u64, u64));

pub(crate) fn analyze_to_graph(ctx: &Ctx<'_>, p: &AnalyzeParams) -> Result<Analyzed, ToolError> {
    let (input, subject, integrity, unlisted) = load_app_input(ctx, p)?;
    if !integrity.is_empty() && p.if_tampered == IntegrityPolicy::Fail {
        return Err(ToolError::new(
            ErrorCode::FileHashMismatch,
            format!("{} ASAR file(s) do not match their integrity hash (first: {})", integrity.len(), integrity.first().map(String::as_str).unwrap_or("")),
        )
        .with_remediation("Pass if_tampered=continue to analyse it anyway.")
        .with_details(json!({"paths": integrity.iter().take(50).collect::<Vec<_>>()})));
    }
    let opts = AppOptions { max_nodes: p.max_nodes.clamp(16, 1_000_000), ..AppOptions::default() };
    let cancel = ctx.cancel.clone();
    let check = move || cancel.is_cancelled();
    let graph = analyze_application(&input, &opts, &check).map_err(|_| ToolError::cancelled())?;
    let mut lims: Vec<Limitation> = graph.limitations.iter().map(|(c, m)| Limitation::new(c.clone(), m.clone())).collect();
    for path in &integrity {
        lims.push(Limitation::new("integrity_mismatch", format!("{path} does not match its ASAR integrity hash")));
    }
    lims.extend(super::artifact_tools::unlisted_limitation(&unlisted));
    lims.push(Limitation::new(
        "static_only",
        "Static reading only: code built at run time (eval, computed requires, remote content) is invisible; IPC pairs need literal channel names.",
    ));
    let read = input.files.len() as u64;
    let listed = input.listing.len() as u64;
    Ok((graph, subject, lims, (read, listed)))
}

fn js_app_map(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: AnalyzeParams = parse_params(params)?;
    ctx.report(None, format!("Reading {}", p.input_path));
    let (g, subject, lims, (read, listed)) = analyze_to_graph(ctx, &p)?;
    let name = g.package.as_ref().and_then(|x| x.get("product_name").or(x.get("name"))).and_then(Value::as_str).unwrap_or(&g.label).to_string();
    let version = g.package.as_ref().and_then(|x| x.get("version")).and_then(Value::as_str).map(|v| format!(" {v}")).unwrap_or_default();
    let what = match g.app_kind.as_str() {
        "electron" => "Electron app",
        "web" => "Web app",
        "node" => "Node package",
        _ => "JavaScript code",
    };
    let summary = format!(
        "{what} {name}{version}: {} source files, {} IPC channel(s) ({} paired), {} window(s), {} endpoint(s), {} route(s){}.",
        g.modules.len(),
        g.ipc.len(),
        g.ipc.iter().filter(|c| c.paired).count(),
        g.windows.len(),
        g.endpoints.iter().filter(|e| e.get("api").and_then(Value::as_str) != Some("literal")).count(),
        g.routes.len(),
        if g.bundlers.is_empty() { String::new() } else { format!(", bundled with {}", g.bundlers.join("/")) }
    );
    let mut result = serde_json::to_value(&g).map_err(|e| ToolError::internal(e.to_string()))?;
    let total_modules = g.modules.len();
    if let Some(o) = result.as_object_mut() {
        let page: Vec<Value> = g.modules.iter().skip(p.offset).take(p.limit.max(1)).filter_map(|m| serde_json::to_value(m).ok()).collect();
        o.insert("modules".into(), json!(page));
        o.insert("modules_total".into(), json!(total_modules));
        o.insert("summary".into(), json!(summary));
    }
    let complete_modules = p.offset == 0 && p.limit >= total_modules;
    // A folder that couldn't be listed holds files never counted, so the count can't be complete (#294).
    let unlisted = lims.iter().any(|l| l.code == "unlisted_folders");
    let mut b = EvidenceBuilder::new("js_app_map", subject, env(ctx))
        .params(json!({"input_path": p.input_path, "include_node_modules": p.include_node_modules, "max_nodes": p.max_nodes, "offset": p.offset, "limit": p.limit, "source_paths": p.source_paths}))
        .result(result)
        .summary(summary)
        .confidence(Confidence::Derived)
        .limitations(lims)
        .coverage(if complete_modules { Coverage { status: if read >= listed && !unlisted { craft_anything_evidence::CoverageStatus::Complete } else { craft_anything_evidence::CoverageStatus::Partial }, examined: Some(read), total: Some(listed), next_offset: None } } else { Coverage::page(p.limit.min(total_modules.saturating_sub(p.offset)) as u64, total_modules as u64, p.offset as u64) })
        .location(Location::new("path", p.input_path.clone()));
    if !complete_modules {
        b = b.limitation(Limitation::new("paged_modules", "Only one page of module summaries is included; tools that take this evidence need every module, so pass the input path to them or use offset=0 with a limit above modules_total."));
    }
    if let Some(m) = &g.entry_points.main {
        b = b.location(Location::new("module", m.clone()).with_label("main"));
    }
    Ok(ToolOutput::evidence(b.build()?))
}

/// Read an application graph from evidence or analyse a path. Returns the graph and the evidence id.
pub(crate) fn load_graph(ctx: &Ctx<'_>, v: &Value) -> Result<(AppGraph, Option<String>), ToolError> {
    if let Some(path) = is_path_input(v) {
        let (g, _, _, _) = analyze_to_graph(ctx, &AnalyzeParams::for_path(path))?;
        return Ok((g, None));
    }
    let ev = resolve_evidence_input(ctx, v, &["js_app_map"])?;
    let total = ev.result.get("modules_total").and_then(Value::as_u64).unwrap_or(0);
    let shown = ev.result.get("modules").and_then(Value::as_array).map_or(0, Vec::len) as u64;
    let mut g: AppGraph =
        serde_json::from_value(ev.result.clone()).map_err(|e| ToolError::invalid(format!("evidence {} does not hold an application graph: {e}", ev.id)))?;
    if shown < total {
        // A paged record: re-analyse the recorded input for the full module list.
        if let Some(path) = ev.params.get("input_path").and_then(Value::as_str) {
            let (full, _, _, _) = analyze_to_graph(ctx, &AnalyzeParams::for_path(path))?;
            if full.graph_id != g.graph_id {
                return Err(ToolError::new(ErrorCode::FileChanged, format!("{path} changed since evidence {} was recorded", ev.id)));
            }
            g = full;
        }
    }
    Ok((g, Some(ev.id)))
}

// ---------------------------------------------------------------------------------------------

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct StaticLayer {
    /// js_app_map evidence (inline or {"kind":"saved","evidence_id":…}) or an absolute path.
    pub evidence: Value,
    /// `application`, `cache` or `assets`.
    #[serde(default = "default_role")]
    pub role: String,
}

fn default_role() -> String {
    "application".into()
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct RuntimeScriptParam {
    pub url: String,
    #[serde(default)]
    pub sha256: Option<String>,
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ReconcileParams {
    /// The static side: one or more application graphs.
    pub static_evidence: Vec<StaticLayer>,
    /// Runtime evidence that lists scripts (objects with `url` and `sha256`), inline or retained.
    #[serde(default)]
    pub runtime_evidence: Vec<Value>,
    /// Runtime scripts given directly.
    #[serde(default)]
    pub runtime_scripts: Vec<RuntimeScriptParam>,
}

fn js_runtime_code_match(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ReconcileParams = parse_params(params)?;
    if p.static_evidence.is_empty() {
        return Err(ToolError::invalid("static_evidence is empty"));
    }
    let mut graphs = Vec::new();
    let mut links = Vec::new();
    for l in p.static_evidence.iter().take(16) {
        let (g, id) = load_graph(ctx, &l.evidence)?;
        links.extend(id);
        graphs.push((l.role.clone(), g));
    }
    let mut scripts: Vec<RuntimeScript> = p.runtime_scripts.iter().map(|s| RuntimeScript { url: s.url.clone(), sha256: s.sha256.clone() }).collect();
    for o in p.runtime_evidence.iter().take(64) {
        let ev = resolve_evidence_input(ctx, o, &[])?;
        scripts.extend(runtime_scripts_from(&ev.result));
        links.push(ev.id);
    }
    if scripts.is_empty() {
        return Err(ToolError::invalid("no runtime scripts found in runtime_evidence or runtime_scripts")
            .with_remediation("Pass captures that list scripts with url and sha256, or runtime_scripts directly."));
    }
    let refs: Vec<(String, &AppGraph)> = graphs.iter().map(|(r, g)| (r.clone(), g)).collect();
    let r = reconcile(&refs, &scripts);
    let summary = format!(
        "Reconciled {} static layer(s) with {} runtime script(s): {}.",
        graphs.len(),
        scripts.len(),
        r["counts"].as_object().map(|m| m.iter().map(|(k, v)| format!("{v} {k}")).collect::<Vec<_>>().join(", ")).unwrap_or_default()
    );
    let mut b = EvidenceBuilder::new(
        "js_runtime_code_match",
        Subject { kind: "js-app".into(), sha256: None, name: graphs.first().map(|(_, g)| g.label.clone()) },
        env(ctx),
    )
    .params(json!({"layers": graphs.iter().map(|(r, g)| json!({"role": r, "graph_id": g.graph_id})).collect::<Vec<_>>(), "runtime_scripts": scripts.len()}))
    .result(r)
    .summary(summary)
    .confidence(Confidence::Derived)
    .limitation(Limitation::new("absence_is_not_proof", "'not observed' means the capture didn't see it load, not that it never runs."));
    for id in links {
        b = b.link(id);
    }
    Ok(ToolOutput::evidence(b.build()?))
}

#[cfg(test)]
mod tests {
    use crate::{CallOptions, Caller, Engine};
    use craft_anything_evidence::ToolError;
    use craft_anything_testkit::electron as fx;
    use serde_json::{Value, json};

    fn call(e: &Engine, id: &str, p: Value) -> Result<Value, ToolError> {
        e.call(id, p, CallOptions::new(Caller::Mcp)).map(|o| o.to_json())
    }

    #[test]
    fn analyzes_folder_and_asar_identically() {
        let dir = tempfile::tempdir().unwrap();
        let root = fx::write_notes_app(dir.path()).unwrap();
        let asar = dir.path().join("app.asar");
        std::fs::write(&asar, fx::notes_app_asar()).unwrap();
        let e = Engine::new(crate::testing::session());
        let a = call(&e, "js_app_map", json!({"input_path": root})).unwrap();
        let b = call(&e, "js_app_map", json!({"input_path": asar})).unwrap();
        assert_eq!(a["result"]["graph_id"], b["result"]["graph_id"]);
        assert_eq!(a["result"]["app_kind"], "electron");
        assert_eq!(a["confidence"], "derived");
        assert!(a["summary"].as_str().unwrap().contains("Electron app Notes 1.0.0"), "{}", a["summary"]);
        let ch = a["result"]["ipc"].as_array().unwrap().iter().find(|c| c["channel"] == "export-notes").unwrap().clone();
        assert_eq!(ch["paired"], true);
        assert_eq!(a["result"]["windows"][0]["web_preferences"]["contextIsolation"], true);
        // A packaged folder with only resources/app.asar is analysed through the archive.
        let packaged = dir.path().join("Notes-linux");
        std::fs::create_dir_all(packaged.join("resources")).unwrap();
        std::fs::write(packaged.join("resources/app.asar"), fx::notes_app_asar()).unwrap();
        let c = call(&e, "js_app_map", json!({"input_path": packaged})).unwrap();
        assert_eq!(c["result"]["graph_id"], a["result"]["graph_id"]);
    }

    #[test]
    fn single_bundle_file_and_bad_inputs() {
        let dir = tempfile::tempdir().unwrap();
        let f = dir.path().join("main.js");
        std::fs::write(&f, fx::WEBPACK_BUNDLE).unwrap();
        let e = Engine::new(crate::testing::session());
        let a = call(&e, "js_app_map", json!({"input_path": f})).unwrap();
        assert_eq!(a["result"]["bundlers"], json!(["webpack"]));
        assert_eq!(a["result"]["modules"][0]["bundle_modules"].as_array().unwrap().len(), 3);
        assert!(call(&e, "js_app_map", json!({"input_path": "rel.js"})).is_err());
        assert!(call(&e, "js_app_map", json!({"input_path": dir.path().join("missing")})).is_err());
        assert!(call(&e, "js_app_map", json!({"input_path": f, "bogus": 1})).is_err());
        let junk = dir.path().join("junk.asar");
        std::fs::write(&junk, b"\x04\0\0\0\xff\xff\xff\xff garbage").unwrap();
        assert!(call(&e, "js_app_map", json!({"input_path": junk, "format": "asar"})).is_err());
    }

    /// Smoke test against a real app: `CRAFT_SMOKE_PATH=/path/app.asar cargo test -- --ignored smoke --nocapture`.
    #[test]
    #[ignore]
    fn smoke_real_app() {
        let Ok(path) = std::env::var("CRAFT_SMOKE_PATH") else { return };
        let e = Engine::new(crate::testing::session());
        let t = std::time::Instant::now();
        let a = call(&e, "js_app_map", json!({"input_path": path, "if_tampered": "continue", "limit": 5})).unwrap();
        println!("{} in {:?}", a["summary"], t.elapsed());
        println!("stats {}", a["result"]["stats"]);
        println!("bundlers {} limitations {}", a["result"]["bundlers"], a["limitations"]);
        let ch = a["result"]["ipc"].as_array().map(|v| v.iter().take(5).map(|c| c["channel"].clone()).collect::<Vec<_>>());
        println!("channels {ch:?}");
        println!("windows {}", a["result"]["windows"].to_string().chars().take(800).collect::<String>());
        if let Some(c) = a["result"]["ipc"].as_array().and_then(|v| v.iter().find(|c| c["paired"] == true)) {
            let t = call(
                &e,
                "app_feature_follow",
                json!({"application": {"kind": "saved", "evidence_id": a["id"]}, "seed": {"kind": "ipc-channel", "value": c["channel"], "match": "exact"}}),
            )
            .unwrap();
            println!("story: {}", t["summary"]);
        }
    }

    #[test]
    fn reconcile_with_inline_scripts() {
        let dir = tempfile::tempdir().unwrap();
        let root = fx::write_notes_app(dir.path()).unwrap();
        let e = Engine::new(crate::testing::session());
        let a = call(&e, "js_app_map", json!({"input_path": root})).unwrap();
        let id = a["id"].as_str().unwrap();
        let sha = craft_anything_evidence::sha256_hex(fx::RENDERER_JS.as_bytes());
        let r = call(
            &e,
            "js_runtime_code_match",
            json!({
                "static_evidence": [{"evidence": {"kind": "saved", "evidence_id": id}}],
                "runtime_scripts": [{"url": "file:///app/renderer/app.js", "sha256": sha}],
            }),
        )
        .unwrap();
        assert_eq!(r["result"]["counts"]["loaded"], 1);
        assert_eq!(r["links"][0], id);
        // Inline evidence that was tampered with is refused.
        let mut tampered = a.clone();
        tampered["result"]["app_kind"] = json!("web");
        let err = call(&e, "js_runtime_code_match", json!({"static_evidence": [{"evidence": tampered}], "runtime_scripts": [{"url": "x"}]})).unwrap_err();
        assert_eq!(err.code, craft_anything_evidence::ErrorCode::EvidenceHashMismatch);
    }

    /// #294: a folder that couldn't be listed made a smaller graph that looked complete.
    #[cfg(unix)]
    #[test]
    fn a_folder_that_cant_be_listed_is_said_and_leaves_coverage_partial() {
        use std::os::unix::fs::PermissionsExt;
        let dir = tempfile::tempdir().unwrap();
        let bundle = dir.path().join("bundle");
        let closed = bundle.join("closed");
        std::fs::create_dir_all(&closed).unwrap();
        std::fs::write(closed.join("hidden.js"), "console.log('hidden');\n").unwrap();
        std::fs::write(bundle.join("visible.js"), "console.log('visible');\n").unwrap();
        let main = dir.path().join("main.js");
        std::fs::write(&main, "console.log('main');\n").unwrap();
        let extras = dir.path().join("extras");
        std::fs::create_dir_all(extras.join("closed")).unwrap();
        std::fs::write(extras.join("closed/extra.js"), "console.log('extra');\n").unwrap();
        let e = Engine::new(crate::testing::session());
        let modules = |v: &Value| v["result"]["modules"].as_array().unwrap().iter().map(|m| m["path"].as_str().unwrap().to_string()).collect::<Vec<_>>();
        let readable = call(&e, "js_app_map", json!({"input_path": bundle})).unwrap();
        assert_eq!(modules(&readable), ["closed/hidden.js", "visible.js"]);
        let with_extra = json!({"input_path": main, "source_paths": [extras]});
        assert_eq!(modules(&call(&e, "js_app_map", with_extra.clone()).unwrap()).len(), 2);

        let deny = |p: &std::path::Path| std::fs::set_permissions(p, std::fs::Permissions::from_mode(0o000)).unwrap();
        let allow = |p: &std::path::Path| std::fs::set_permissions(p, std::fs::Permissions::from_mode(0o755)).unwrap();
        deny(&closed);
        if std::fs::read_dir(&closed).is_ok() {
            allow(&closed);
            return; // Run as root: nothing is unreadable.
        }
        let child = call(&e, "js_app_map", json!({"input_path": bundle}));
        let root = call(&e, "js_app_map", json!({"input_path": closed}));
        allow(&closed);
        deny(&extras.join("closed"));
        let extra_child = call(&e, "js_app_map", with_extra.clone());
        allow(&extras.join("closed"));
        deny(&extras);
        let extra_root = call(&e, "js_app_map", with_extra.clone());
        allow(&extras);

        for v in [child.unwrap(), extra_child.unwrap()] {
            assert_eq!(v["coverage"]["status"], "partial", "{v}");
            let lim = v["limitations"].as_array().unwrap().iter().find(|l| l["code"] == "unlisted_folders").cloned();
            assert!(lim.is_some_and(|l| l["message"].as_str().unwrap().contains("closed")), "{v}");
        }
        assert!(root.is_err(), "a root folder that can't be listed is an error, not an empty graph");
        assert!(extra_root.is_err(), "so is an extra source folder that can't be listed");
        let forced = call(&e, "js_app_map", json!({"input_path": main, "format": "directory"}));
        assert!(forced.is_err(), "a regular file read as a folder is an error: {forced:?}");
        assert_eq!(call(&e, "js_app_map", json!({"input_path": bundle})).unwrap()["result"], readable["result"]);
    }
}
