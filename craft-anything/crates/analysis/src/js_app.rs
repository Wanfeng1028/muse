//! The JavaScript application graph: every source of an Electron app, web bundle or Node
//! package analysed and joined into one graph of modules, functions, windows, IPC channels,
//! the preload bridge, endpoints, routes, storage, platform effects and native modules.
//!
//! Pure: the caller supplies file bytes (from an ASAR, folder or ZIP). Nothing is executed.

use craft_anything_evidence::sha256_hex;
use craft_anything_js::html::{HtmlFacts, scan_html};
use craft_anything_js::{self as js, ModuleFacts, PrefValue};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet, HashMap, VecDeque};

/// One input file. `path` is relative with `/` separators.
#[derive(Debug, Clone)]
pub struct AppFile {
    pub path: String,
    pub bytes: Vec<u8>,
}

#[derive(Debug, Clone, Default)]
pub struct AppInput {
    /// What was analysed (file or folder name).
    pub label: String,
    /// `asar`, `directory`, `zip`, `file`.
    pub format: String,
    pub files: Vec<AppFile>,
    /// Every path seen (including ones not read), with sizes.
    pub listing: Vec<(String, u64)>,
    /// Things the reader skipped or noticed.
    pub notes: Vec<String>,
}

#[derive(Debug, Clone, Copy)]
pub struct AppOptions {
    pub limits: js::Limits,
    pub max_nodes: usize,
}

impl Default for AppOptions {
    fn default() -> Self {
        AppOptions { limits: js::Limits::default(), max_nodes: 25_000 }
    }
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct Node {
    pub id: String,
    pub kind: String,
    pub label: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub module: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub line: Option<u32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub role: Option<String>,
    #[serde(default, skip_serializing_if = "Value::is_null")]
    pub attrs: Value,
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
pub struct Edge {
    pub from: String,
    pub to: String,
    pub kind: String,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct ResolvedImport {
    pub kind: String,
    pub specifier: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub resolved: Option<String>,
    pub line: u32,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct BundleModuleSummary {
    pub id: String,
    pub format: String,
    pub sha256: String,
    pub fingerprint: String,
    pub deps: Vec<String>,
    pub line: u32,
    pub start: u32,
    pub end: u32,
    #[serde(default)]
    pub strings: Vec<String>,
    #[serde(default)]
    pub functions: Vec<String>,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct ModuleSummary {
    pub path: String,
    /// `main`, `preload`, `renderer`, `worker`, `page`, `package`, `unknown`.
    pub role: String,
    /// `script`, `html`, `json`, `source-map`, `native`, `other`.
    pub kind: String,
    pub bytes: u64,
    pub sha256: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub fingerprint: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub parse_mode: Option<js::ParseMode>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub parse_note: Option<String>,
    #[serde(default)]
    pub imports: Vec<ResolvedImport>,
    #[serde(default)]
    pub exports: js::ExportShape,
    #[serde(default)]
    pub bundlers: Vec<String>,
    #[serde(default)]
    pub chunk_ids: Vec<String>,
    #[serde(default)]
    pub bundle_modules: Vec<BundleModuleSummary>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub source_map: Option<String>,
    #[serde(default)]
    pub functions: Vec<String>,
    #[serde(default)]
    pub strings: Vec<String>,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct Site {
    pub module: String,
    pub line: u32,
    pub method: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub function: Option<String>,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct IpcChannel {
    pub channel: String,
    /// Main-process `handle`/`handleOnce`.
    pub handlers: Vec<Site>,
    /// Main-process `on`/`once` listeners.
    pub main_listeners: Vec<Site>,
    /// Renderer/preload `invoke`/`sendSync`.
    pub invokers: Vec<Site>,
    /// Renderer/preload `send`.
    pub senders: Vec<Site>,
    /// Renderer listeners for main → renderer messages.
    pub renderer_handlers: Vec<Site>,
    /// Main → renderer `webContents.send`.
    pub main_senders: Vec<Site>,
    /// Exposed bridge members that use the channel.
    pub bridge_members: Vec<String>,
    /// True when a renderer side and a main side were both found.
    pub paired: bool,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct SourceMapRef {
    pub script: String,
    pub url: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub resolved: Option<String>,
    pub present: bool,
    pub inline: bool,
    #[serde(default)]
    pub sources: Vec<String>,
    #[serde(default)]
    pub sources_with_content: usize,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct EntryPoints {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub main: Option<String>,
    pub preloads: Vec<String>,
    pub renderers: Vec<String>,
    pub pages: Vec<String>,
    pub workers: Vec<String>,
}

/// The whole application graph.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct AppGraph {
    /// `ag_` + sha256 of the canonical nodes and edges.
    pub graph_id: String,
    pub label: String,
    pub input_format: String,
    /// `electron`, `web`, `node`, `unknown`.
    pub app_kind: String,
    pub package: Option<Value>,
    pub entry_points: EntryPoints,
    pub modules: Vec<ModuleSummary>,
    pub windows: Vec<Value>,
    pub ipc: Vec<IpcChannel>,
    pub exposed: Vec<Value>,
    pub endpoints: Vec<Value>,
    pub routes: Vec<Value>,
    /// GraphQL operations and tRPC procedures, each row labelled inferred.
    pub api_operations: Vec<Value>,
    pub storage: Vec<Value>,
    pub effects: Vec<Value>,
    pub native_modules: Vec<Value>,
    pub vendors: Vec<Value>,
    pub source_maps: Vec<SourceMapRef>,
    pub bundlers: Vec<String>,
    pub nodes: Vec<Node>,
    pub edges: Vec<Edge>,
    pub limitations: Vec<(String, String)>,
    pub stats: Value,
}

impl AppGraph {
    pub fn node(&self, id: &str) -> Option<&Node> {
        self.nodes.iter().find(|n| n.id == id)
    }

    pub fn module(&self, path: &str) -> Option<&ModuleSummary> {
        self.modules.iter().find(|m| m.path == path)
    }
}

/// The analysis was cancelled.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Cancelled;

// ---------------------------------------------------------------------------------------------
// Paths

/// Directory part of a relative path ("" for top level).
pub fn dir_of(path: &str) -> &str {
    path.rsplit_once('/').map_or("", |(d, _)| d)
}

/// Join and normalise; `None` when the result would escape the root.
pub fn join_rel(base_dir: &str, rel: &str) -> Option<String> {
    let rel = rel.split(['?', '#']).next().unwrap_or(rel);
    let mut parts: Vec<&str> = if rel.starts_with('/') { Vec::new() } else { base_dir.split('/').filter(|p| !p.is_empty()).collect() };
    for p in rel.split(['/', '\\']) {
        match p {
            "" | "." => {}
            ".." => {
                parts.pop()?;
            }
            other => parts.push(other),
        }
    }
    Some(parts.join("/"))
}

const SCRIPT_EXTS: &[&str] = &[".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".mts", ".cts"];

pub fn is_script(path: &str) -> bool {
    let l = path.to_ascii_lowercase();
    SCRIPT_EXTS.iter().any(|e| l.ends_with(e)) && !l.ends_with(".d.ts")
}

fn is_html(path: &str) -> bool {
    let l = path.to_ascii_lowercase();
    l.ends_with(".html") || l.ends_with(".htm")
}

struct Resolver<'a> {
    files: &'a BTreeSet<String>,
}

impl Resolver<'_> {
    fn resolve(&self, from_dir: &str, spec: &str) -> Option<String> {
        if !(spec.starts_with('.') || spec.starts_with('/')) {
            return None;
        }
        let base = join_rel(from_dir, spec)?;
        let candidates = [
            base.clone(),
            format!("{base}.js"),
            format!("{base}.mjs"),
            format!("{base}.cjs"),
            format!("{base}.ts"),
            format!("{base}.tsx"),
            format!("{base}.jsx"),
            format!("{base}.json"),
            format!("{base}/index.js"),
            format!("{base}/index.ts"),
            format!("{base}/index.mjs"),
        ];
        candidates.into_iter().find(|c| self.files.contains(c))
    }

    /// A path written in code (`preload.js`, `renderer/index.html`), tried from the module's
    /// folder first and then from the app root.
    fn resolve_path(&self, module_dir: &str, root: &str, p: &str) -> Option<String> {
        let p = p.trim_start_matches("file://");
        for base in [module_dir, root] {
            if let Some(j) = join_rel(base, p)
                && self.files.contains(&j)
            {
                return Some(j);
            }
        }
        // Last resort: a unique file with that tail.
        let tail = p.trim_start_matches("./").trim_start_matches('/');
        let hits: Vec<&String> = self.files.iter().filter(|f| f.ends_with(&format!("/{tail}")) || f.as_str() == tail).collect();
        if hits.len() == 1 { hits.first().map(|s| (*s).clone()) } else { None }
    }
}

// ---------------------------------------------------------------------------------------------
// Builder

struct Builder {
    nodes: Vec<Node>,
    index: HashMap<String, usize>,
    edges: BTreeSet<Edge>,
    max_nodes: usize,
    dropped_nodes: usize,
}

impl Builder {
    fn node(&mut self, id: String, kind: &str, label: String, module: Option<&str>, line: Option<u32>, attrs: Value) -> Option<String> {
        if self.index.contains_key(&id) {
            return Some(id);
        }
        if self.nodes.len() >= self.max_nodes {
            self.dropped_nodes += 1;
            return None;
        }
        self.index.insert(id.clone(), self.nodes.len());
        self.nodes.push(Node { id: id.clone(), kind: kind.into(), label, module: module.map(String::from), line, role: None, attrs });
        Some(id)
    }

    fn edge(&mut self, from: Option<&str>, to: Option<&str>, kind: &str) {
        if let (Some(f), Some(t)) = (from, to)
            && f != t
            && self.edges.len() < self.max_nodes.saturating_mul(4)
        {
            self.edges.insert(Edge { from: f.into(), to: t.into(), kind: kind.into() });
        }
    }
}

fn module_id(path: &str) -> String {
    format!("module:{path}")
}

fn fn_id(module: &str, name: &str, line: u32) -> String {
    format!("fn:{module}#{name}@{line}")
}

struct Analysed {
    path: String,
    facts: ModuleFacts,
    bundle: js::BundleInfo,
    html: Option<HtmlFacts>,
    /// For inline HTML scripts: the page they came from.
    host: Option<String>,
    /// For inline HTML scripts: the hash of their code (they have no file of their own, #236).
    code_sha256: Option<String>,
}

/// Build the application graph.
pub fn analyze_application(input: &AppInput, opts: &AppOptions, cancelled: &dyn Fn() -> bool) -> Result<AppGraph, Cancelled> {
    let file_set: BTreeSet<String> = input.files.iter().map(|f| f.path.clone()).chain(input.listing.iter().map(|(p, _)| p.clone())).collect();
    let resolver = Resolver { files: &file_set };
    let mut g = AppGraph { label: input.label.clone(), input_format: input.format.clone(), ..Default::default() };
    for n in &input.notes {
        g.limitations.push(("input".into(), n.clone()));
    }

    // ---- package.json (the shallowest one outside node_modules) ----
    let mut vendor_pkgs: Vec<Value> = Vec::new();
    let mut pkg_root = String::new();
    let mut pkgs: Vec<&AppFile> =
        input.files.iter().filter(|f| f.path.ends_with("package.json") && (f.path == "package.json" || f.path.ends_with("/package.json"))).collect();
    pkgs.sort_by_key(|f| (f.path.contains("node_modules/"), f.path.matches('/').count()));
    for f in &pkgs {
        let Ok(v) = serde_json::from_slice::<Value>(&f.bytes) else { continue };
        if f.path.contains("node_modules/") {
            if vendor_pkgs.len() < 5000 {
                vendor_pkgs.push(json!({"name": v.get("name"), "version": v.get("version"), "source": "package-json", "path": f.path}));
            }
        } else if g.package.is_none() {
            pkg_root = dir_of(&f.path).to_string();
            g.package = Some(json!({
                "path": f.path,
                "name": v.get("name"),
                "product_name": v.get("productName"),
                "version": v.get("version"),
                "main": v.get("main"),
                "type": v.get("type"),
                "dependencies": v.get("dependencies"),
                "dev_dependencies": v.get("devDependencies"),
                "electron_dependency": v.pointer("/devDependencies/electron").or_else(|| v.pointer("/dependencies/electron")),
            }));
        }
    }

    // ---- analyse every source ----
    let mut analysed: Vec<Analysed> = Vec::new();
    for (i, f) in input.files.iter().enumerate() {
        if i % 8 == 0 && cancelled() {
            return Err(Cancelled);
        }
        if f.path.contains("node_modules/") {
            continue;
        }
        if is_script(&f.path) {
            let text = String::from_utf8_lossy(&f.bytes);
            let a = js::analyze(&f.path, &text, &opts.limits);
            analysed.push(Analysed { path: f.path.clone(), facts: a.facts, bundle: a.bundle, html: None, host: None, code_sha256: None });
        } else if is_html(&f.path) {
            let text = String::from_utf8_lossy(&f.bytes);
            let h = scan_html(&text);
            for (n, s) in h.scripts.iter().enumerate() {
                if let Some((a, z)) = s.inline {
                    let code = craft_anything_js::util::slice(&text, a, z);
                    let name = format!("{}#inline-{n}", f.path);
                    let an = js::analyze(&name, code, &opts.limits);
                    let code_sha256 = Some(sha256_hex(code.as_bytes()));
                    analysed.push(Analysed { path: name, facts: an.facts, bundle: an.bundle, html: None, host: Some(f.path.clone()), code_sha256 });
                }
            }
            analysed.push(Analysed {
                path: f.path.clone(),
                facts: ModuleFacts::default(),
                bundle: js::BundleInfo::default(),
                html: Some(h),
                host: None,
                code_sha256: None,
            });
        }
    }

    let mut b = Builder { nodes: Vec::new(), index: HashMap::new(), edges: BTreeSet::new(), max_nodes: opts.max_nodes.max(16), dropped_nodes: 0 };
    let pkg_node = g.package.as_ref().map(|p| {
        let name = p.get("name").and_then(Value::as_str).unwrap_or("package").to_string();
        b.node(format!("package:{name}"), "package", name, p.get("path").and_then(Value::as_str), None, json!({"version": p.get("version")}))
    });
    let pkg_node = pkg_node.flatten();

    // Module nodes first (so they survive a node cap).
    for a in &analysed {
        let kind = if a.html.is_some() { "html" } else { "module" };
        let id = b.node(module_id(&a.path), kind, a.path.clone(), Some(&a.path), None, Value::Null);
        b.edge(pkg_node.as_deref(), id.as_deref(), "contains");
    }

    // ---- entry points and roles ----
    let main = g
        .package
        .as_ref()
        .and_then(|p| p.get("main").and_then(Value::as_str))
        .and_then(|m| resolver.resolve(&pkg_root, &if m.starts_with('.') { m.to_string() } else { format!("./{m}") }))
        .or_else(|| {
            ["main.js", "index.js", "main.cjs", "dist/main.js", "dist/main/index.js"]
                .iter()
                .map(|c| join_rel(&pkg_root, c).unwrap_or_default())
                .find(|c| file_set.contains(c))
        });
    let mut roles: HashMap<String, String> = HashMap::new();
    let by_path: HashMap<&str, &Analysed> = analysed.iter().map(|a| (a.path.as_str(), a)).collect();

    // Resolve imports once.
    let mut resolved_imports: HashMap<String, Vec<ResolvedImport>> = HashMap::new();
    for a in &analysed {
        let dir = dir_of(a.host.as_deref().unwrap_or(&a.path)).to_string();
        let mut v = Vec::new();
        for imp in a.facts.imports.iter().take(2000) {
            let resolved = if imp.literal { resolver.resolve(&dir, &imp.specifier) } else { None };
            v.push(ResolvedImport { kind: imp.kind.clone(), specifier: imp.specifier.clone(), resolved, line: imp.line });
        }
        if let Some(h) = &a.html {
            for s in &h.scripts {
                if let Some(src) = &s.src
                    && !src.contains("://")
                {
                    let r = join_rel(&dir, src).filter(|p| file_set.contains(p)).or_else(|| resolver.resolve_path(&dir, &pkg_root, src));
                    v.push(ResolvedImport { kind: "html-script".into(), specifier: src.clone(), resolved: r, line: s.line });
                }
            }
            for p in &h.preloads {
                let r = join_rel(&dir, p).filter(|x| file_set.contains(x));
                v.push(ResolvedImport { kind: "modulepreload".into(), specifier: p.clone(), resolved: r, line: 0 });
            }
        }
        resolved_imports.insert(a.path.clone(), v);
    }

    // Windows: preload and loaded pages.
    let mut preloads = Vec::new();
    let mut renderer_roots = Vec::new();
    for a in &analysed {
        let dir = dir_of(&a.path).to_string();
        for w in &a.facts.windows {
            if let Some(p) = &w.preload
                && let Some(r) = resolver.resolve_path(&dir, &pkg_root, p)
            {
                preloads.push(r);
            }
        }
        for l in &a.facts.loads {
            if let Some(t) = &l.target
                && !t.starts_with("http")
                && let Some(r) = resolver.resolve_path(&dir, &pkg_root, t)
            {
                renderer_roots.push(r);
            }
        }
    }
    let has_electron = analysed.iter().any(|a| a.facts.imports.iter().any(|i| i.specifier == "electron" || i.specifier.starts_with("electron/")))
        || g.package.as_ref().is_some_and(|p| !p.get("electron_dependency").unwrap_or(&Value::Null).is_null());
    let pages: Vec<String> = if has_electron { Vec::new() } else { analysed.iter().filter(|a| a.html.is_some()).map(|a| a.path.clone()).collect() };

    let assign = |roots: &[String], role: &str, roles: &mut HashMap<String, String>| {
        let mut q: VecDeque<String> = roots.iter().cloned().collect();
        let mut seen = 0usize;
        while let Some(p) = q.pop_front() {
            seen += 1;
            if seen > 100_000 || roles.contains_key(&p) {
                continue;
            }
            roles.insert(p.clone(), role.to_string());
            for imp in resolved_imports.get(&p).into_iter().flatten() {
                if let Some(r) = &imp.resolved {
                    q.push_back(r.clone());
                }
            }
            // Inline scripts of a page share its role.
            for a in analysed.iter().filter(|a| a.host.as_deref() == Some(p.as_str())) {
                q.push_back(a.path.clone());
            }
        }
    };
    if let Some(m) = &main {
        assign(std::slice::from_ref(m), if has_electron { "main" } else { "package" }, &mut roles);
    }
    assign(&preloads, "preload", &mut roles);
    assign(&renderer_roots, "renderer", &mut roles);
    assign(&pages, "page", &mut roles);
    let mut workers = Vec::new();
    for a in &analysed {
        for imp in resolved_imports.get(&a.path).into_iter().flatten() {
            if matches!(imp.kind.as_str(), "worker" | "service-worker" | "utility-process")
                && let Some(r) = &imp.resolved
            {
                workers.push(r.clone());
            }
        }
    }
    assign(&workers, "worker", &mut roles);
    g.entry_points = EntryPoints {
        main: main.clone(),
        preloads: dedup(preloads.clone()),
        renderers: dedup(renderer_roots.clone()),
        pages: pages.clone(),
        workers: dedup(workers),
    };
    g.app_kind = if has_electron {
        "electron"
    } else if !pages.is_empty() {
        "web"
    } else if g.package.is_some() {
        "node"
    } else {
        "unknown"
    }
    .into();
    let role_of = |p: &str| roles.get(p).cloned().unwrap_or_else(|| "unknown".into());

    // ---- per-module facts into the graph ----
    let mut channels: BTreeMap<String, IpcChannel> = BTreeMap::new();
    let mut exposed_keys: Vec<ExposedKey> = Vec::new();
    let mut bundlers: BTreeSet<String> = BTreeSet::new();
    let mut dynamic_channels = 0usize;
    // Calls like `window.api.invoke("channel")` only count when `api` is an exposed bridge key.
    let bridge_keys: BTreeSet<String> = analysed.iter().flat_map(|a| a.facts.exposed.iter().filter_map(|e| e.key.clone())).collect();
    for a in &analysed {
        if cancelled() {
            return Err(Cancelled);
        }
        let m = a.path.as_str();
        let mid = module_id(m);
        let role = role_of(m);
        let f = &a.facts;
        // Imports.
        for imp in resolved_imports.get(m).into_iter().flatten() {
            let to = match &imp.resolved {
                Some(r) => Some(module_id(r)),
                None if !imp.specifier.starts_with('.') && !imp.specifier.starts_with('/') && !imp.specifier.contains('{') => {
                    let pkg = package_name(&imp.specifier);
                    b.node(format!("external:{pkg}"), "external", pkg.clone(), None, None, Value::Null)
                }
                None => None,
            };
            b.edge(Some(&mid), to.as_deref(), &imp.kind);
        }
        // Functions (named ones, plus any that matter for tracing).
        let interesting: BTreeSet<&str> = f
            .ipc
            .iter()
            .filter_map(|u| u.function.as_deref().or(u.handler.as_deref()))
            .chain(f.effects.iter().filter_map(|u| u.function.as_deref()))
            .chain(f.endpoints.iter().filter_map(|u| u.function.as_deref()))
            .chain(f.storage.iter().filter_map(|u| u.function.as_deref()))
            .chain(f.events.iter().filter_map(|u| u.handler.as_deref()))
            .collect();
        let mut fn_ids: HashMap<&str, String> = HashMap::new();
        for func in &f.functions {
            let anonymous = func.name.starts_with("<anonymous@") || func.name.contains(" callback@");
            if anonymous && !interesting.contains(func.name.as_str()) {
                continue;
            }
            let id = fn_id(m, &func.name, func.line);
            let attrs = json!({
                "kind": func.kind, "params": func.params, "calls": func.calls, "strings": func.strings,
                "end_line": func.end_line, "exported": func.exported, "parent": func.parent, "start": func.start, "end": func.end,
            });
            if let Some(id) = b.node(id, "function", func.name.clone(), Some(m), Some(func.line), attrs) {
                b.edge(Some(&mid), Some(&id), "defines");
                fn_ids.entry(func.name.as_str()).or_insert(id);
            }
        }
        let fnode = |name: Option<&str>| -> String { name.and_then(|n| fn_ids.get(n).cloned()).unwrap_or_else(|| mid.clone()) };
        // Calls within the module.
        for func in &f.functions {
            let Some(from) = fn_ids.get(func.name.as_str()).cloned() else { continue };
            for c in &func.calls {
                let last = c.rsplit('.').next().unwrap_or(c);
                let target = fn_ids.get(c.as_str()).or_else(|| fn_ids.get(last).filter(|_| !c.contains('.')));
                if let Some(t) = target.cloned() {
                    b.edge(Some(&from), Some(&t), "calls");
                }
            }
        }
        // IPC.
        for u in &f.ipc {
            if u.side == "bridge" && !u.method.split('.').next().is_some_and(|root| bridge_keys.contains(root)) {
                continue;
            }
            let Some(ch) = u.channel.as_ref().filter(|c| !c.is_empty()) else {
                dynamic_channels += 1;
                continue;
            };
            let entry = channels.entry(ch.clone()).or_insert_with(|| IpcChannel { channel: ch.clone(), ..Default::default() });
            let site = Site { module: m.into(), line: u.line, method: u.method.clone(), function: u.function.clone() };
            let cid = b.node(format!("ipc:{ch}"), "ipc-channel", ch.clone(), None, None, Value::Null);
            let caller = fnode(u.function.as_deref());
            match (u.side.as_str(), u.method.as_str()) {
                ("main", "handle" | "handleOnce") => {
                    entry.handlers.push(site);
                    let h = u.handler.as_deref().map(|h| fnode(Some(h)));
                    b.edge(cid.as_deref(), h.as_deref(), "handled-by");
                }
                ("main", "on" | "once" | "addListener") => {
                    entry.main_listeners.push(site);
                    let h = u.handler.as_deref().map(|h| fnode(Some(h)));
                    b.edge(cid.as_deref(), h.as_deref(), "handled-by");
                }
                ("main", _) => {}
                ("renderer", "invoke" | "sendSync") | ("bridge", _) => {
                    entry.invokers.push(site);
                    b.edge(Some(&caller), cid.as_deref(), "invokes");
                }
                ("renderer", "send" | "sendTo" | "sendToHost" | "postMessage") => {
                    entry.senders.push(site);
                    b.edge(Some(&caller), cid.as_deref(), "sends");
                }
                ("renderer", "on" | "once" | "addListener") => {
                    entry.renderer_handlers.push(site);
                    let h = u.handler.as_deref().map(|h| fnode(Some(h)));
                    b.edge(cid.as_deref(), h.as_deref(), "delivers-to");
                }
                ("web-contents", _) => {
                    entry.main_senders.push(site);
                    b.edge(Some(&caller), cid.as_deref(), "sends");
                }
                _ => {}
            }
        }
        // Bridge exposure.
        for e in &f.exposed {
            let key = e.key.clone().unwrap_or_else(|| "?".into());
            let api = b.node(format!("api:{key}"), "exposed-api", format!("window.{key}"), Some(m), Some(e.line), json!({"method": e.method}));
            b.edge(Some(&mid), api.as_deref(), "exposes");
            let mut members = Vec::new();
            for mem in &e.members {
                let mid2 =
                    b.node(format!("member:{key}.{}", mem.name), "exposed-member", format!("window.{key}.{}", mem.name), Some(m), Some(e.line), Value::Null);
                b.edge(api.as_deref(), mid2.as_deref(), "has-member");
                if let Some(func) = &mem.function {
                    let t = fn_ids.get(func.as_str()).cloned();
                    b.edge(mid2.as_deref(), t.as_deref(), "implemented-by");
                }
                members.push((mem.name.clone(), mem.function.clone()));
            }
            exposed_keys.push((m.to_string(), key, members));
        }
        // Windows.
        for (wi, w) in f.windows.iter().enumerate() {
            let preload = w.preload.as_deref().and_then(|p| resolver.resolve_path(dir_of(m), &pkg_root, p));
            let findings = window_findings(&w.web_preferences, preload.is_some());
            let wid = b.node(
                format!("window:{m}@{}", w.line),
                "window",
                w.binding.clone().unwrap_or_else(|| format!("{} #{wi}", w.class)),
                Some(m),
                Some(w.line),
                json!({"class": w.class, "web_preferences": w.web_preferences, "preload": preload, "findings": findings}),
            );
            b.edge(Some(&fnode(w.function.as_deref())), wid.as_deref(), "creates");
            b.edge(wid.as_deref(), preload.as_deref().map(module_id).as_deref(), "preload");
            let loads: Vec<String> =
                f.loads.iter().filter(|l| l.receiver.is_none() || l.receiver == w.binding || f.windows.len() == 1).filter_map(|l| l.target.clone()).collect();
            let mut resolved_loads = Vec::new();
            for t in &loads {
                if let Some(r) = resolver.resolve_path(dir_of(m), &pkg_root, t) {
                    b.edge(wid.as_deref(), Some(&module_id(&r)), "loads");
                    resolved_loads.push(r);
                } else {
                    let u = b.node(format!("url:{t}"), "url", t.clone(), None, None, Value::Null);
                    b.edge(wid.as_deref(), u.as_deref(), "loads");
                    resolved_loads.push(t.clone());
                }
            }
            g.windows.push(json!({
                "module": m, "line": w.line, "class": w.class, "binding": w.binding, "preload": preload, "preload_as_written": w.preload,
                "web_preferences": w.web_preferences, "options_from": w.options_from, "loads": resolved_loads, "findings": findings,
            }));
        }
        // Endpoints, routes, storage, effects, events, native modules.
        for e in &f.endpoints {
            let label = match &e.method {
                Some(mm) => format!("{mm} {}", e.url),
                None => e.url.clone(),
            };
            let eid = b.node(format!("endpoint:{label}"), "endpoint", label.clone(), None, None, json!({"api": e.api, "literal": e.literal}));
            b.edge(Some(&fnode(e.function.as_deref())), eid.as_deref(), if e.api == "literal" { "mentions" } else { "requests" });
            if g.endpoints.len() < 10_000 {
                g.endpoints.push(json!({"url": e.url, "method": e.method, "api": e.api, "literal": e.literal, "module": m, "line": e.line, "function": e.function, "role": role}));
            }
        }
        for r in &f.routes {
            let rid = b.node(format!("route:{}", r.path), "route", r.path.clone(), Some(m), Some(r.line), json!({"source": r.source, "method": r.method}));
            b.edge(Some(&mid), rid.as_deref(), "declares-route");
            if g.routes.len() < 10_000 {
                g.routes.push(json!({"path": r.path, "source": r.source, "method": r.method, "module": m, "line": r.line}));
            }
        }
        for o in &f.api_operations {
            if g.api_operations.len() < 10_000 {
                g.api_operations.push(json!({"protocol": o.protocol, "kind": o.kind, "name": o.name, "url": o.url, "literal": o.literal, "source": o.source, "confidence": "inferred", "module": m, "line": o.line, "function": o.function, "role": role}));
            }
        }
        for (list, kind, out) in [(&f.storage, "storage", &mut g.storage), (&f.effects, "effect", &mut g.effects)] {
            for u in list {
                let label = match &u.arg {
                    Some(a) if kind == "storage" => format!("{} {a}", u.api),
                    _ => u.api.clone(),
                };
                let nid = b.node(format!("{kind}:{label}"), kind, label, None, None, Value::Null);
                b.edge(Some(&fnode(u.function.as_deref())), nid.as_deref(), "uses");
                if out.len() < 10_000 {
                    out.push(json!({"api": u.api, "arg": u.arg, "module": m, "line": u.line, "function": u.function, "role": role}));
                }
            }
        }
        for e in &f.events {
            let label = format!("{}:{}", e.target, e.event);
            let ev = b.node(format!("event:{m}#{label}"), "event", label, Some(m), Some(e.line), Value::Null);
            b.edge(Some(&fnode(e.function.as_deref())), ev.as_deref(), "listens");
            if let Some(h) = &e.handler {
                let t = fn_ids.get(h.as_str()).cloned();
                b.edge(ev.as_deref(), t.as_deref(), "handled-by");
            }
        }
        for n in &f.native_modules {
            let nid = b.node(format!("native:{n}"), "native-module", n.clone(), None, None, Value::Null);
            b.edge(Some(&mid), nid.as_deref(), "loads-native");
            g.native_modules.push(json!({"name": n, "module": m}));
        }
        for v in &f.vendors {
            g.vendors.push(json!({"name": v.name, "version": v.version, "source": v.source, "module": m}));
        }
        // Bundles.
        for bn in &a.bundle.bundlers {
            bundlers.insert(bn.clone());
        }
        let mut bundle_modules = Vec::new();
        for bm in &a.bundle.modules {
            let bid = b.node(
                format!("bundle-module:{m}#{}", bm.id),
                "bundle-module",
                bm.id.clone(),
                Some(m),
                Some(bm.line),
                json!({"format": bm.format, "sha256": bm.sha256}),
            );
            b.edge(Some(&mid), bid.as_deref(), "bundles");
            let inside: Vec<&js::FunctionFact> = f.functions.iter().filter(|x| x.start >= bm.start && x.end <= bm.end).collect();
            for x in &inside {
                if let Some(fid) = fn_ids.get(x.name.as_str()) {
                    b.edge(bid.as_deref(), Some(fid), "defines");
                }
            }
            let mut strings: Vec<String> = Vec::new();
            for x in &inside {
                for s in &x.strings {
                    if strings.len() < 200 && !strings.contains(s) {
                        strings.push(s.clone());
                    }
                }
            }
            bundle_modules.push(BundleModuleSummary {
                id: bm.id.clone(),
                format: bm.format.clone(),
                sha256: bm.sha256.clone(),
                fingerprint: bm.fingerprint.clone(),
                deps: bm.deps.clone(),
                line: bm.line,
                start: bm.start,
                end: bm.end,
                strings,
                functions: inside.iter().filter(|x| !x.name.starts_with('<')).map(|x| x.name.clone()).take(200).collect(),
            });
        }
        for bm in &a.bundle.modules {
            for d in &bm.deps {
                b.edge(Some(&format!("bundle-module:{m}#{}", bm.id)), Some(&format!("bundle-module:{m}#{d}")), "requires");
            }
        }
        // Module summary.
        let bytes_len = input.files.iter().find(|x| x.path == a.path).map_or(f.bytes as u64, |x| x.bytes.len() as u64);
        let sha = input.files.iter().find(|x| x.path == a.path).map(|x| sha256_hex(&x.bytes)).or_else(|| a.code_sha256.clone()).unwrap_or_default();
        g.modules.push(ModuleSummary {
            path: a.path.clone(),
            role,
            kind: if a.html.is_some() { "html".into() } else { "script".into() },
            bytes: bytes_len,
            sha256: sha,
            fingerprint: f.fingerprint.clone(),
            parse_mode: a.html.is_none().then_some(f.mode),
            parse_note: f.mode_reason.clone(),
            imports: resolved_imports.get(m).cloned().unwrap_or_default(),
            exports: f.exports.clone(),
            bundlers: a.bundle.bundlers.clone(),
            chunk_ids: a.bundle.chunk_ids.clone(),
            bundle_modules,
            source_map: f.source_map_url.clone(),
            functions: f.functions.iter().filter(|x| !x.name.starts_with('<') && !x.name.contains(" callback@")).map(|x| x.name.clone()).take(500).collect(),
            strings: f.strings.iter().take(300).cloned().collect(),
        });
    }

    // Renderer calls into the bridge: `api.exportNotes(...)` → member node.
    for a in &analysed {
        let m = a.path.as_str();
        for func in &a.facts.functions {
            let from = fn_id(m, &func.name, func.line);
            if !b.index.contains_key(&from) {
                continue;
            }
            for c in &func.calls {
                for (pm, key, members) in &exposed_keys {
                    if pm == m {
                        continue;
                    }
                    if let Some(rest) = c.strip_prefix(&format!("{key}.")) {
                        let name = rest.split('.').next().unwrap_or(rest);
                        if members.iter().any(|(n, _)| n == name) {
                            b.edge(Some(&from), Some(&format!("member:{key}.{name}")), "calls-bridge");
                        }
                    }
                }
            }
        }
    }
    // Pair channels and attach bridge members.
    for (pm, key, members) in &exposed_keys {
        let Some(a) = by_path.get(pm.as_str()) else { continue };
        for (name, func) in members {
            let Some(func) = func else { continue };
            for u in a.facts.ipc.iter().filter(|u| u.function.as_deref() == Some(func.as_str())) {
                if let Some(ch) = &u.channel
                    && let Some(c) = channels.get_mut(ch)
                {
                    let label = format!("window.{key}.{name}");
                    if !c.bridge_members.contains(&label) {
                        c.bridge_members.push(label);
                    }
                }
            }
        }
        g.exposed.push(json!({
            "module": pm, "key": key,
            "members": members.iter().map(|(n, f)| json!({"name": n, "function": f})).collect::<Vec<_>>(),
        }));
    }
    for c in channels.values_mut() {
        let renderer_side = !c.invokers.is_empty() || !c.senders.is_empty() || !c.renderer_handlers.is_empty();
        let main_side = !c.handlers.is_empty() || !c.main_listeners.is_empty() || !c.main_senders.is_empty();
        c.paired = renderer_side && main_side;
    }
    g.ipc = channels.into_values().collect();
    if dynamic_channels > 0 {
        g.limitations.push((
            "dynamic_ipc_channels".into(),
            format!("{dynamic_channels} IPC call(s) use a channel name computed at run time; they are not in the channel map."),
        ));
    }

    // HTML pages → scripts.
    for a in analysed.iter().filter(|a| a.html.is_some()) {
        for imp in resolved_imports.get(&a.path).into_iter().flatten() {
            if let Some(r) = &imp.resolved {
                b.edge(Some(&module_id(&a.path)), Some(&module_id(r)), &imp.kind);
            }
        }
        if let Some(h) = &a.html
            && let Some(csp) = &h.csp
            && let Some(n) = b.index.get(&module_id(&a.path)).copied().and_then(|i| b.nodes.get_mut(i))
        {
            n.attrs = json!({"csp": csp, "title": h.title});
        }
    }

    // Source maps.
    for a in &analysed {
        let Some(url) = &a.facts.source_map_url else { continue };
        let mut r = SourceMapRef { script: a.path.clone(), url: url.chars().take(256).collect(), ..Default::default() };
        let map_bytes: Option<Vec<u8>> = if url.starts_with("data:") {
            r.inline = true;
            craft_anything_formats::sourcemap::decode_data_url(url)
        } else {
            let p = join_rel(dir_of(&a.path), url);
            r.resolved = p.clone();
            p.and_then(|p| input.files.iter().find(|f| f.path == p).map(|f| f.bytes.clone()))
        };
        if let Some(bytes) = map_bytes {
            r.present = true;
            if let Ok(map) = craft_anything_formats::sourcemap::parse(&bytes, craft_anything_formats::sourcemap::Limits::default()) {
                r.sources = map.all_sources().into_iter().take(5000).collect();
                r.sources_with_content = map.sources_content.iter().filter(|c| c.is_some()).count();
            }
            if let Some(res) = &r.resolved {
                let to = b.node(module_id(res), "source-map", res.clone(), Some(res), None, Value::Null);
                b.edge(Some(&module_id(&a.path)), to.as_deref(), "source-map");
            }
        } else {
            r.present = file_set.contains(r.resolved.as_deref().unwrap_or(""));
        }
        g.source_maps.push(r);
    }
    // Stand-alone .map files without a comment pointing at them.
    for (p, _) in &input.listing {
        if p.ends_with(".map") && !p.contains("node_modules/") && !g.source_maps.iter().any(|s| s.resolved.as_deref() == Some(p.as_str())) {
            g.source_maps.push(SourceMapRef {
                script: p.trim_end_matches(".map").to_string(),
                url: String::new(),
                resolved: Some(p.clone()),
                present: true,
                ..Default::default()
            });
        }
    }
    // Native binaries present in the listing.
    for (p, _) in &input.listing {
        if p.ends_with(".node") && !g.native_modules.iter().any(|n| n.get("file").and_then(Value::as_str) == Some(p.as_str())) {
            b.node(format!("native:{p}"), "native-module", p.clone(), Some(p), None, json!({"present": true}));
            g.native_modules.push(json!({"name": p.rsplit('/').next().unwrap_or(p), "file": p}));
        }
    }
    g.vendors.extend(vendor_pkgs);
    g.bundlers = bundlers.into_iter().collect();
    if b.dropped_nodes > 0 {
        g.limitations
            .push(("node_cap".into(), format!("{} graph nodes were dropped at the {}-node cap; raise max_nodes to keep them.", b.dropped_nodes, b.max_nodes)));
    }
    let lexed = g.modules.iter().filter(|m| m.parse_mode == Some(js::ParseMode::Lexer)).count();
    if lexed > 0 {
        g.limitations.push((
            "lexer_fallback".into(),
            format!(
                "{lexed} source(s) were too large, too deep or too broken to parse; their facts come from a token scan (no functions, windows or aliases)."
            ),
        ));
    }
    for n in &mut b.nodes {
        if let Some(m) = &n.module {
            let host = m.split("#inline-").next().unwrap_or(m);
            n.role = Some(role_of(host));
        }
    }
    if !g.api_operations.is_empty() {
        g.limitations.push((
            "api_operations_inferred".into(),
            "GraphQL operations and tRPC procedures are inferred from how the code is written, and nothing was run. A row with literal false depends on text only known at run time; documents built up by joining strings, and clients whose names were minified away, may be missing.".into(),
        ));
    }
    g.nodes = b.nodes;
    g.edges = b.edges.into_iter().collect();
    g.stats = json!({
        "files": input.files.len(),
        "listed": input.listing.len(),
        "modules": g.modules.len(),
        "nodes": g.nodes.len(),
        "edges": g.edges.len(),
        "functions": g.nodes.iter().filter(|n| n.kind == "function").count(),
        "ipc_channels": g.ipc.len(),
        "paired_channels": g.ipc.iter().filter(|c| c.paired).count(),
        "endpoints": g.endpoints.len(),
        "api_operations": g.api_operations.len(),
        "bundle_modules": g.modules.iter().map(|m| m.bundle_modules.len()).sum::<usize>(),
    });
    g.graph_id = graph_id(&g.nodes, &g.edges);
    Ok(g)
}

/// (preload module, bridge key, members as (name, implementing function)).
type ExposedKey = (String, String, Vec<(String, Option<String>)>);

fn dedup(mut v: Vec<String>) -> Vec<String> {
    let mut seen = BTreeSet::new();
    v.retain(|x| seen.insert(x.clone()));
    v
}

/// `@scope/pkg/sub` → `@scope/pkg`; `pkg/sub` → `pkg`; `node:fs` → `fs`.
pub fn package_name(spec: &str) -> String {
    let s = spec.strip_prefix("node:").unwrap_or(spec);
    let mut parts = s.split('/');
    match (parts.next(), parts.next()) {
        (Some(scope), Some(name)) if scope.starts_with('@') => format!("{scope}/{name}"),
        (Some(first), _) => first.to_string(),
        _ => s.to_string(),
    }
}

/// Security-relevant observations about a window's webPreferences (Electron 20+ defaults:
/// contextIsolation on, nodeIntegration off, sandbox on).
fn window_findings(p: &BTreeMap<String, PrefValue>, has_preload: bool) -> Vec<String> {
    let mut out = Vec::new();
    let get = |k: &str| p.get(k);
    if get("contextIsolation") == Some(&PrefValue::Bool(false)) {
        out.push("contextIsolation is turned off: page scripts share the preload's JavaScript world".to_string());
    }
    if get("nodeIntegration") == Some(&PrefValue::Bool(true)) {
        out.push("nodeIntegration is on: page scripts can use Node.js directly".to_string());
    }
    if get("sandbox") == Some(&PrefValue::Bool(false)) {
        out.push("sandbox is turned off for this renderer".to_string());
    }
    if get("webSecurity") == Some(&PrefValue::Bool(false)) {
        out.push("webSecurity is off: same-origin checks are disabled".to_string());
    }
    if get("allowRunningInsecureContent") == Some(&PrefValue::Bool(true)) {
        out.push("allowRunningInsecureContent is on".to_string());
    }
    if get("webviewTag") == Some(&PrefValue::Bool(true)) {
        out.push("the <webview> tag is enabled".to_string());
    }
    if get("webPreferences") == Some(&PrefValue::Text("dynamic".into())) {
        out.push("webPreferences are computed at run time; their values could not be read statically".to_string());
        return out;
    }
    for k in ["contextIsolation", "nodeIntegration", "sandbox"] {
        if !p.contains_key(k) {
            out.push(format!("{k} is not set; the Electron version's default applies"));
        }
    }
    if !has_preload && p.contains_key("preload") {
        out.push("the preload script could not be found in the input".to_string());
    }
    out
}

/// Content id of a graph.
pub fn graph_id(nodes: &[Node], edges: &[Edge]) -> String {
    let mut ids: Vec<(&String, &String)> = nodes.iter().map(|n| (&n.id, &n.kind)).collect();
    ids.sort();
    let mut es: Vec<&Edge> = edges.iter().collect();
    es.sort();
    let v = json!({"nodes": ids, "edges": es});
    format!("ag_{}", sha256_hex(craft_anything_evidence::canonical_json(&v).as_bytes()))
}

#[cfg(test)]
pub(crate) mod tests_support {
    use super::*;
    use craft_anything_testkit::electron as fx;

    pub fn graph_of(files: Vec<(&str, String)>) -> AppGraph {
        let files = files.into_iter().map(|(p, c)| AppFile { path: p.into(), bytes: c.into_bytes() }).collect::<Vec<_>>();
        let listing = files.iter().map(|f| (f.path.clone(), f.bytes.len() as u64)).collect();
        let input = AppInput { label: "notes".into(), format: "directory".into(), files, listing, notes: vec![] };
        analyze_application(&input, &AppOptions::default(), &|| false).unwrap()
    }

    pub fn notes_graph() -> AppGraph {
        graph_of(fx::notes_app_files())
    }
}

#[cfg(test)]
mod tests {
    use super::tests_support::notes_graph;
    use super::*;
    use craft_anything_testkit::electron as fx;

    #[test]
    fn notes_app_graph() {
        let g = notes_graph();
        assert_eq!(g.app_kind, "electron");
        assert_eq!(g.entry_points.main.as_deref(), Some("main.js"));
        assert_eq!(g.entry_points.preloads, vec!["preload.js"]);
        assert_eq!(g.entry_points.renderers, vec!["renderer/index.html"]);
        assert_eq!(g.module("renderer/app.js").unwrap().role, "renderer");
        assert_eq!(g.module("preload.js").unwrap().role, "preload");
        let ch = g.ipc.iter().find(|c| c.channel == "export-notes").unwrap();
        assert!(ch.paired);
        assert_eq!(ch.bridge_members, vec!["window.api.exportNotes"]);
        assert_eq!(g.windows.len(), 1);
        assert_eq!(g.windows[0]["preload"], "preload.js");
        assert_eq!(g.windows[0]["loads"][0], "renderer/index.html");
        assert!(g.edges.iter().any(|e| e.kind == "calls-bridge" && e.to == "member:api.exportNotes"));
        assert!(g.edges.iter().any(|e| e.kind == "handled-by" && e.from == "ipc:export-notes"));
        assert!(g.edges.iter().any(|e| e.kind == "uses" && e.to == "effect:fs.writeFileSync"));
        assert!(g.endpoints.iter().any(|e| e["url"] == "https://api.notes.example/v1/sync"));
        assert!(g.graph_id.starts_with("ag_"));
        // Deterministic.
        assert_eq!(notes_graph().graph_id, g.graph_id);
    }

    #[test]
    fn paths() {
        assert_eq!(join_rel("a/b", "../c.js").as_deref(), Some("a/c.js"));
        assert_eq!(join_rel("", "../c.js"), None);
        assert_eq!(join_rel("a", "/x/y.js").as_deref(), Some("x/y.js"));
        assert_eq!(package_name("@s/p/x"), "@s/p");
        assert_eq!(package_name("lodash/fp"), "lodash");
    }

    #[test]
    fn cancel_is_honoured() {
        let files = fx::notes_app_files().into_iter().map(|(p, c)| AppFile { path: p.into(), bytes: c.into_bytes() }).collect::<Vec<_>>();
        let input = AppInput { files, ..Default::default() };
        assert!(analyze_application(&input, &AppOptions::default(), &|| true).is_err());
    }
}

#[cfg(test)]
mod api_operation_tests {
    use super::tests_support::graph_of;
    use serde_json::json;

    #[test]
    fn rows_reach_the_app_map_labelled_inferred_without_changing_the_graph() {
        let src = "const q = gql`query Feed { items { id } }`;\nconst a = trpc.post.byId.useQuery();\nconst d = trpc[name].useQuery();\n";
        let g = graph_of(vec![("src/app.js", src.to_string())]);
        assert_eq!(g.api_operations.len(), 3, "{:?}", g.api_operations);
        assert!(g.api_operations.iter().all(|o| o["confidence"] == "inferred"));
        let feed = g.api_operations.iter().find(|o| o["name"] == "Feed").unwrap();
        assert_eq!(
            (&feed["protocol"], &feed["kind"], &feed["module"], &feed["line"], &feed["literal"]),
            (&json!("graphql"), &json!("query"), &json!("src/app.js"), &json!(1), &json!(true))
        );
        assert!(g.api_operations.iter().any(|o| o["protocol"] == "trpc" && o["kind"] == "unknown" && o["literal"] == false));
        assert!(g.limitations.iter().any(|(k, _)| k == "api_operations_inferred"));
        assert_eq!(g.stats["api_operations"], 3);

        // The graph's identity comes from nodes and edges, which these rows don't add to.
        let without = graph_of(vec![("src/app.js", "const q = 1;\nconst a = 2;\nconst d = 3;\n".to_string())]);
        assert!(without.api_operations.is_empty());
        assert!(!without.limitations.iter().any(|(k, _)| k == "api_operations_inferred"));
        assert!(g.nodes.iter().all(|n| !n.id.contains("Feed")), "no new node kinds");
    }

    #[test]
    fn a_graph_saved_before_this_field_still_loads() {
        let mut v = serde_json::to_value(graph_of(vec![("a.js", "const q = 1;".to_string())])).unwrap();
        v.as_object_mut().unwrap().remove("api_operations");
        let g: super::AppGraph = serde_json::from_value(v).unwrap();
        assert!(g.api_operations.is_empty());
    }
}
