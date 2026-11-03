//! Walking the application graph: feature traces across renderer ↔ preload ↔ main, function-level
//! semantic slices, and reconciling static modules with scripts seen at run time.

use crate::js_app::{AppGraph, Edge, Node};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet, HashMap, VecDeque};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "kebab-case")]
pub enum SeedKind {
    /// An exact graph node id.
    Node,
    Module,
    Function,
    /// A string literal used in code (or any label containing it).
    String,
    IpcChannel,
    Endpoint,
    Route,
    /// An exposed bridge API or member (`window.api.exportNotes`).
    Api,
    /// Search every node label.
    #[default]
    Any,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "kebab-case")]
pub enum Direction {
    Outgoing,
    Incoming,
    #[default]
    Both,
}

/// Node kinds we report but never walk through (they connect everything to everything).
const TERMINAL: &[&str] = &["module", "html", "package", "external", "source-map", "vendor"];

fn label_matches(label: &str, value: &str, exact: bool) -> bool {
    if exact { label == value } else { label.to_lowercase().contains(&value.to_lowercase()) }
}

/// Nodes matching a seed (at most 32).
pub fn find_seeds(g: &AppGraph, kind: SeedKind, value: &str, exact: bool) -> Vec<String> {
    let kinds: &[&str] = match kind {
        SeedKind::Node => return g.nodes.iter().filter(|n| n.id == value).map(|n| n.id.clone()).collect(),
        SeedKind::Module => &["module", "html"],
        SeedKind::Function => &["function"],
        SeedKind::IpcChannel => &["ipc-channel"],
        SeedKind::Endpoint => &["endpoint"],
        SeedKind::Route => &["route"],
        SeedKind::Api => &["exposed-api", "exposed-member"],
        SeedKind::String | SeedKind::Any => &[],
    };
    let mut out: Vec<String> = Vec::new();
    for n in &g.nodes {
        let kind_ok = kinds.is_empty() || kinds.contains(&n.kind.as_str());
        let mut hit = kind_ok && label_matches(&n.label, value, exact);
        if !hit && kind == SeedKind::Function && exact {
            hit = n.kind == "function" && n.label.rsplit('.').next() == Some(value);
        }
        if !hit && kind == SeedKind::Module && n.kind == "module" {
            hit = n.label.ends_with(&format!("/{value}"));
        }
        if !hit && kind == SeedKind::String && n.kind == "function" {
            hit = n.attrs.get("strings").and_then(Value::as_array).is_some_and(|a| a.iter().filter_map(Value::as_str).any(|s| label_matches(s, value, exact)));
        }
        if hit && !out.contains(&n.id) {
            out.push(n.id.clone());
        }
        if out.len() >= 32 {
            break;
        }
    }
    out
}

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct FeatureTrace {
    pub seeds: Vec<String>,
    pub nodes: Vec<Node>,
    pub edges: Vec<Edge>,
    /// Paths from the seed outwards (what it leads to), as readable steps.
    pub outgoing_chains: Vec<Vec<String>>,
    /// Paths into the seed (what leads to it), nearest step first.
    pub incoming_chains: Vec<Vec<String>>,
    /// The longest incoming chain, the seed, then the longest outgoing chain.
    pub story: Vec<String>,
    /// Node labels grouped by process role (renderer, preload, main…).
    pub by_role: BTreeMap<String, Vec<String>>,
    pub truncated: bool,
}

pub fn describe(n: &Node) -> String {
    match (&n.module, n.line) {
        (Some(m), Some(l)) if n.kind != "module" => format!("{}: {} ({m}:{l})", n.kind, n.label),
        _ => format!("{}: {}", n.kind, n.label),
    }
}

struct Adjacency<'g> {
    out: HashMap<&'g str, Vec<&'g Edge>>,
    inc: HashMap<&'g str, Vec<&'g Edge>>,
}

fn adjacency(g: &AppGraph) -> Adjacency<'_> {
    let mut out: HashMap<&str, Vec<&Edge>> = HashMap::new();
    let mut inc: HashMap<&str, Vec<&Edge>> = HashMap::new();
    for e in &g.edges {
        out.entry(e.from.as_str()).or_default().push(e);
        inc.entry(e.to.as_str()).or_default().push(e);
    }
    Adjacency { out, inc }
}

/// Nodes and edges gathered across walks.
#[derive(Default)]
struct Collected {
    seen: BTreeSet<String>,
    edges: BTreeSet<Edge>,
}

/// Breadth-first walk from the seeds in one direction. Returns parent links (child → parent).
fn walk<'g>(
    g: &'g AppGraph,
    adj: &Adjacency<'g>,
    seeds: &[String],
    forward: bool,
    max_depth: usize,
    max_nodes: usize,
    acc: &mut Collected,
) -> (HashMap<String, String>, bool) {
    let Collected { seen, edges } = acc;
    let index: HashMap<&str, &Node> = g.nodes.iter().map(|n| (n.id.as_str(), n)).collect();
    let mut parent: HashMap<String, String> = HashMap::new();
    let mut q: VecDeque<(String, usize)> = seeds.iter().map(|s| (s.clone(), 0)).collect();
    let mut visited: BTreeSet<String> = seeds.iter().cloned().collect();
    let mut truncated = false;
    while let Some((id, depth)) = q.pop_front() {
        let is_seed = seeds.contains(&id);
        if depth >= max_depth {
            continue;
        }
        if !is_seed && index.get(id.as_str()).is_some_and(|n| TERMINAL.contains(&n.kind.as_str())) {
            continue;
        }
        let list = if forward { adj.out.get(id.as_str()) } else { adj.inc.get(id.as_str()) };
        for e in list.into_iter().flatten() {
            // From a module seed, only follow what it defines/creates, not every import.
            let next = if forward { &e.to } else { &e.from };
            if seen.len() >= max_nodes && !seen.contains(next) {
                truncated = true;
                continue;
            }
            edges.insert((*e).clone());
            seen.insert(next.clone());
            if visited.insert(next.clone()) {
                parent.insert(next.clone(), id.clone());
                q.push_back((next.clone(), depth + 1));
            }
        }
    }
    (parent, truncated)
}

fn chains(g: &AppGraph, parent: &HashMap<String, String>, limit: usize) -> Vec<Vec<String>> {
    let index: HashMap<&str, &Node> = g.nodes.iter().map(|n| (n.id.as_str(), n)).collect();
    let has_child: BTreeSet<&String> = parent.values().collect();
    let mut leaves: Vec<&String> = parent.keys().filter(|k| !has_child.contains(k)).collect();
    leaves.sort();
    let mut out = Vec::new();
    for leaf in leaves {
        let mut path = vec![leaf.clone()];
        let mut cur = leaf;
        let mut guard = 0;
        while let Some(p) = parent.get(cur) {
            path.push(p.clone());
            cur = p;
            guard += 1;
            if guard > 256 {
                break;
            }
        }
        path.reverse();
        out.push(path.iter().map(|id| index.get(id.as_str()).map_or_else(|| id.clone(), |n| describe(n))).collect());
        if out.len() >= limit {
            break;
        }
    }
    out.sort_by_key(|c: &Vec<String>| std::cmp::Reverse(c.len()));
    out
}

/// Trace a feature from its seed nodes.
pub fn follow_feature(g: &AppGraph, seeds: &[String], direction: Direction, max_depth: usize, max_nodes: usize) -> FeatureTrace {
    let adj = adjacency(g);
    let mut acc = Collected { seen: seeds.iter().cloned().collect(), edges: BTreeSet::new() };
    let mut t = FeatureTrace { seeds: seeds.to_vec(), ..Default::default() };
    if matches!(direction, Direction::Outgoing | Direction::Both) {
        let (p, tr) = walk(g, &adj, seeds, true, max_depth, max_nodes, &mut acc);
        t.outgoing_chains = chains(g, &p, 50);
        t.truncated |= tr;
    }
    if matches!(direction, Direction::Incoming | Direction::Both) {
        let (p, tr) = walk(g, &adj, seeds, false, max_depth, max_nodes, &mut acc);
        t.incoming_chains = chains(g, &p, 50);
        t.truncated |= tr;
    }
    let index: HashMap<&str, &Node> = g.nodes.iter().map(|n| (n.id.as_str(), n)).collect();
    t.nodes = acc.seen.iter().filter_map(|id| index.get(id.as_str()).map(|n| (*n).clone())).collect();
    t.edges = acc.edges.into_iter().collect();
    for n in &t.nodes {
        let role = n.role.clone().unwrap_or_else(|| if n.module.is_none() { "shared".into() } else { "unknown".into() });
        t.by_role.entry(role).or_default().push(describe(n));
    }
    let incoming = t.incoming_chains.first().cloned().unwrap_or_default();
    let outgoing = t.outgoing_chains.first().cloned().unwrap_or_default();
    let mut story: Vec<String> = incoming.into_iter().rev().collect();
    let skip = usize::from(!story.is_empty());
    story.extend(outgoing.into_iter().skip(skip));
    if story.is_empty() {
        story = seeds.iter().filter_map(|s| index.get(s.as_str()).map(|n| describe(n))).collect();
    }
    t.story = story;
    t
}

/// A function-level view: what it calls, who calls it, what it touches.
pub fn trace_semantics(g: &AppGraph, seeds: &[String], max_depth: usize, max_functions: usize) -> Value {
    let adj = adjacency(g);
    let index: HashMap<&str, &Node> = g.nodes.iter().map(|n| (n.id.as_str(), n)).collect();
    let functions: Vec<&Node> = g.nodes.iter().filter(|n| n.kind == "function").collect();
    let mut reports = Vec::new();
    let mut unresolved: BTreeSet<String> = BTreeSet::new();
    // Expand seeds to the functions they denote (a module seed means its functions).
    let mut fn_seeds: Vec<String> = Vec::new();
    for s in seeds {
        match index.get(s.as_str()) {
            Some(n) if n.kind == "function" => fn_seeds.push(s.clone()),
            Some(_) => {
                for e in adj.out.get(s.as_str()).into_iter().flatten().chain(adj.inc.get(s.as_str()).into_iter().flatten()) {
                    for end in [&e.from, &e.to] {
                        if index.get(end.as_str()).is_some_and(|n| n.kind == "function") && !fn_seeds.contains(end) {
                            fn_seeds.push(end.clone());
                        }
                    }
                }
            }
            None => {}
        }
    }
    fn_seeds.truncate(max_functions);
    for id in &fn_seeds {
        let Some(n) = index.get(id.as_str()) else { continue };
        let calls: Vec<String> =
            n.attrs.get("calls").and_then(Value::as_array).map(|a| a.iter().filter_map(|v| v.as_str().map(String::from)).collect()).unwrap_or_default();
        let resolved: BTreeMap<&str, &str> = adj
            .out
            .get(id.as_str())
            .into_iter()
            .flatten()
            .filter(|e| e.kind == "calls")
            .filter_map(|e| index.get(e.to.as_str()).map(|t| (t.label.as_str(), e.to.as_str())))
            .collect();
        let call_rows: Vec<Value> = calls
            .iter()
            .map(|c| {
                let last = c.rsplit('.').next().unwrap_or(c);
                let r = resolved.get(c.as_str()).or_else(|| resolved.get(last));
                if r.is_none() && !c.contains('.') && !is_builtin(c) {
                    unresolved.insert(c.clone());
                }
                json!({"callee": c, "resolved": r})
            })
            .collect();
        // Callers: resolved edges, plus same-named calls elsewhere (inferred).
        let mut callers: Vec<Value> =
            adj.inc.get(id.as_str()).into_iter().flatten().filter(|e| e.kind == "calls").map(|e| json!({"function": e.from, "how": "resolved"})).collect();
        let short = n.label.rsplit('.').next().unwrap_or(&n.label);
        for f in &functions {
            if f.id == *id || callers.iter().any(|c| c["function"] == f.id.as_str()) {
                continue;
            }
            let calls_it = f
                .attrs
                .get("calls")
                .and_then(Value::as_array)
                .is_some_and(|a| a.iter().filter_map(Value::as_str).any(|c| c == n.label || (c.ends_with(&format!(".{short}")) && n.label.contains('.'))));
            if calls_it && callers.len() < 64 {
                callers.push(json!({"function": f.id, "how": "same name (inferred)"}));
            }
        }
        let touches: Vec<Value> = adj
            .out
            .get(id.as_str())
            .into_iter()
            .flatten()
            .filter(|e| e.kind != "calls")
            .filter_map(|e| index.get(e.to.as_str()).map(|t| json!({"relation": e.kind, "node": t.id, "kind": t.kind, "label": t.label})))
            .collect();
        // Callee tree (resolved calls only), depth-limited.
        let mut tree = Vec::new();
        let mut q: VecDeque<(String, usize)> = VecDeque::from([(id.clone(), 0)]);
        let mut seen = BTreeSet::from([id.clone()]);
        while let Some((cur, d)) = q.pop_front() {
            if d >= max_depth || tree.len() >= 256 {
                continue;
            }
            for e in adj.out.get(cur.as_str()).into_iter().flatten().filter(|e| e.kind == "calls") {
                if seen.insert(e.to.clone()) {
                    if let Some(t) = index.get(e.to.as_str()) {
                        tree.push(json!({"depth": d + 1, "function": t.label, "node": t.id, "from": cur}));
                    }
                    q.push_back((e.to.clone(), d + 1));
                }
            }
        }
        reports.push(json!({
            "node": n.id, "name": n.label, "module": n.module, "line": n.line, "role": n.role,
            "params": n.attrs.get("params"), "strings": n.attrs.get("strings"), "exported": n.attrs.get("exported"),
            "calls": call_rows, "callers": callers, "touches": touches, "callee_tree": tree,
        }));
    }
    json!({"functions": reports, "unresolved_calls": unresolved.into_iter().take(200).collect::<Vec<_>>(), "seed_functions": fn_seeds.len()})
}

fn is_builtin(name: &str) -> bool {
    matches!(
        name,
        "require"
            | "String"
            | "Number"
            | "Boolean"
            | "Array"
            | "Object"
            | "JSON"
            | "Promise"
            | "Error"
            | "Symbol"
            | "parseInt"
            | "parseFloat"
            | "setTimeout"
            | "setInterval"
            | "clearTimeout"
            | "clearInterval"
            | "fetch"
            | "encodeURIComponent"
            | "decodeURIComponent"
            | "isNaN"
            | "Date"
            | "Map"
            | "Set"
            | "RegExp"
            | "console"
    )
}

/// A script seen at run time (from a browser/Electron capture or a script export manifest).
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct RuntimeScript {
    pub url: String,
    #[serde(default)]
    pub sha256: Option<String>,
}

/// Pull runtime scripts out of an observation's result, wherever it lists them.
pub fn runtime_scripts_from(result: &Value) -> Vec<RuntimeScript> {
    let mut out = Vec::new();
    let mut stack = vec![(result, 0usize)];
    while let Some((v, depth)) = stack.pop() {
        if depth > 8 || out.len() >= 50_000 {
            break;
        }
        match v {
            Value::Object(m) => {
                if let Some(url) = m.get("url").and_then(Value::as_str)
                    && (m.contains_key("sha256") || m.contains_key("source_sha256") || m.contains_key("script_id") || m.contains_key("path"))
                {
                    let sha = m.get("sha256").or_else(|| m.get("source_sha256")).and_then(Value::as_str).map(String::from);
                    out.push(RuntimeScript { url: url.to_string(), sha256: sha });
                    continue;
                }
                for x in m.values() {
                    stack.push((x, depth + 1));
                }
            }
            Value::Array(a) => {
                for x in a {
                    stack.push((x, depth + 1));
                }
            }
            _ => {}
        }
    }
    out
}

/// Reconcile static layers with runtime observations.
pub fn reconcile(layers: &[(String, &AppGraph)], scripts: &[RuntimeScript]) -> Value {
    let mut rows = Vec::new();
    let mut matched_runtime: BTreeSet<usize> = BTreeSet::new();
    let mut counts: BTreeMap<String, usize> = BTreeMap::new();
    for (role, g) in layers {
        for m in g.modules.iter().filter(|m| m.kind == "script") {
            let by_digest = scripts.iter().position(|s| s.sha256.as_deref() == Some(m.sha256.as_str()));
            let by_location = scripts.iter().position(|s| url_matches_path(&s.url, &m.path));
            let (status, how, idx) = match (by_digest, by_location) {
                (Some(i), _) => ("loaded", "digest", Some(i)),
                (None, Some(i)) => {
                    let differs = scripts.get(i).and_then(|s| s.sha256.as_deref()).is_some_and(|s| s != m.sha256);
                    (if differs { "loaded-with-different-content" } else { "loaded" }, "location", Some(i))
                }
                (None, None) if m.sha256.is_empty() => ("unknown", "no digest", None),
                (None, None) => ("not-seen-running", "", None),
            };
            if let Some(i) = idx {
                matched_runtime.insert(i);
            }
            *counts.entry(status.to_string()).or_default() += 1;
            rows.push(json!({"layer": role, "graph_id": g.graph_id, "module": m.path, "status": status, "matched_by": how, "runtime_url": idx.and_then(|i| scripts.get(i)).map(|s| &s.url)}));
            for bm in &m.bundle_modules {
                let st = if status == "loaded" { "inside-loaded-bundle" } else { "not-seen-running" };
                *counts.entry(st.to_string()).or_default() += 1;
                if rows.len() < 20_000 {
                    rows.push(json!({"layer": role, "graph_id": g.graph_id, "module": format!("{}#{}", m.path, bm.id), "status": st, "matched_by": "containing file"}));
                }
            }
        }
    }
    let runtime_only: Vec<&RuntimeScript> = scripts.iter().enumerate().filter(|(i, _)| !matched_runtime.contains(i)).map(|(_, s)| s).collect();
    json!({"modules": rows, "counts": counts, "runtime_only": runtime_only, "runtime_scripts": scripts.len()})
}

/// True when a runtime URL points at a static path (`file:///…/app.asar/renderer/app.js`, `https://host/assets/x.js`).
pub fn url_matches_path(url: &str, path: &str) -> bool {
    let u = url.split(['?', '#']).next().unwrap_or(url);
    let u = u.strip_prefix("file://").unwrap_or(u);
    let p = path.trim_start_matches("./");
    !p.is_empty() && (u.ends_with(&format!("/{p}")) || u == p || u.ends_with(&format!(".asar/{p}")))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn g() -> AppGraph {
        crate::js_app::tests_support::notes_graph()
    }

    #[test]
    fn export_feature_crosses_all_three_layers() {
        let g = g();
        let seeds = find_seeds(&g, SeedKind::IpcChannel, "export-notes", true);
        assert_eq!(seeds, vec!["ipc:export-notes"]);
        let t = follow_feature(&g, &seeds, Direction::Both, 8, 500);
        let story = t.story.join(" -> ");
        assert!(story.contains("exportNotes (renderer/app.js"), "{story}");
        assert!(story.contains("exposed-member: window.api.exportNotes"), "{story}");
        assert!(story.contains("ipcMain.handle(export-notes)"), "{story}");
        assert!(story.contains("fs.writeFileSync") || t.outgoing_chains.iter().flatten().any(|s| s.contains("fs.writeFileSync")), "{story}");
        assert!(t.by_role.contains_key("renderer") && t.by_role.contains_key("preload") && t.by_role.contains_key("main"), "{:?}", t.by_role.keys());
    }

    #[test]
    fn seeds_by_function_and_string() {
        let g = g();
        assert!(!find_seeds(&g, SeedKind::Function, "toCsv", true).is_empty());
        assert!(!find_seeds(&g, SeedKind::String, "notes.csv", false).is_empty());
        assert!(find_seeds(&g, SeedKind::Function, "nope", true).is_empty());
        let s = trace_semantics(&g, &find_seeds(&g, SeedKind::Function, "toCsv", true), 4, 16);
        let callers = s["functions"][0]["callers"].as_array().unwrap();
        assert!(callers.iter().any(|c| c["function"].as_str().unwrap().contains("ipcMain.handle(export-notes)")), "{s}");
    }

    #[test]
    fn reconcile_statuses() {
        let g = g();
        let app = g.module("renderer/app.js").unwrap().sha256.clone();
        let scripts = vec![
            RuntimeScript { url: "file:///opt/Notes/resources/app.asar/renderer/app.js".into(), sha256: Some(app) },
            RuntimeScript { url: "https://cdn.example/x.js".into(), sha256: None },
        ];
        let r = reconcile(&[("application".into(), &g)], &scripts);
        assert_eq!(r["counts"]["loaded"], 1);
        assert_eq!(r["runtime_only"].as_array().unwrap().len(), 1);
        assert!(r["counts"]["not-seen-running"].as_u64().unwrap() >= 2);
        let found = runtime_scripts_from(&json!({"capture": {"scripts": [{"url": "a.js", "sha256": "x"}]}}));
        assert_eq!(found.len(), 1);
    }
}
