//! Reference sources: a `.gitignore`-aware matcher, a summary graph of a source tree, and the
//! matching of source files to the modules of a shipped bundle.

use crate::js_app::{AppGraph, Cancelled, is_script};
use craft_anything_evidence::sha256_hex;
use craft_anything_js as js;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet, HashMap};

// ---------------------------------------------------------------------------------------------
// .gitignore

#[derive(Debug, Clone, PartialEq, Eq)]
enum Tok {
    Lit(char),
    Any,
    Star,
    /// `**` (any characters, slashes included).
    Globstar,
    /// `**/` (nothing, or anything ending in a slash).
    GlobstarSlash,
    Class(Vec<(char, char)>, bool),
}

fn tokenize_glob(p: &str) -> Vec<Tok> {
    let chars: Vec<char> = p.chars().collect();
    let mut out = Vec::new();
    let mut i = 0;
    while let Some(&c) = chars.get(i) {
        match c {
            '*' if chars.get(i + 1) == Some(&'*') => {
                if chars.get(i + 2) == Some(&'/') {
                    out.push(Tok::GlobstarSlash);
                    i += 3;
                } else {
                    out.push(Tok::Globstar);
                    i += 2;
                }
            }
            '*' => {
                out.push(Tok::Star);
                i += 1;
            }
            '?' => {
                out.push(Tok::Any);
                i += 1;
            }
            '[' => {
                let mut j = i + 1;
                let neg = matches!(chars.get(j), Some('!' | '^'));
                if neg {
                    j += 1;
                }
                let mut ranges = Vec::new();
                let start = j;
                while let Some(&d) = chars.get(j) {
                    if d == ']' && j > start {
                        break;
                    }
                    if chars.get(j + 1) == Some(&'-') && chars.get(j + 2).is_some_and(|e| *e != ']') {
                        ranges.push((d, chars.get(j + 2).copied().unwrap_or(d)));
                        j += 3;
                    } else {
                        ranges.push((d, d));
                        j += 1;
                    }
                }
                if chars.get(j) == Some(&']') {
                    out.push(Tok::Class(ranges, neg));
                    i = j + 1;
                } else {
                    out.push(Tok::Lit('['));
                    i += 1;
                }
            }
            '\\' => {
                if let Some(&n) = chars.get(i + 1) {
                    out.push(Tok::Lit(n));
                }
                i += 2;
            }
            _ => {
                out.push(Tok::Lit(c));
                i += 1;
            }
        }
    }
    out
}

/// Glob match by dynamic programming (no backtracking blow-up).
fn glob_match(tokens: &[Tok], s: &str) -> bool {
    let s: Vec<char> = s.chars().take(4096).collect();
    let (n, m) = (tokens.len(), s.len());
    // dp[j] for the current token row: tokens[i..] matches s[j..].
    let mut next = vec![false; m + 1];
    next[m] = true; // empty pattern matches empty string
    for i in (0..n).rev() {
        let mut cur = vec![false; m + 1];
        for j in (0..=m).rev() {
            let c = s.get(j).copied();
            cur[j] = match tokens.get(i) {
                Some(Tok::Lit(l)) => c == Some(*l) && next.get(j + 1).copied().unwrap_or(false),
                Some(Tok::Any) => c.is_some_and(|c| c != '/') && next.get(j + 1).copied().unwrap_or(false),
                Some(Tok::Class(r, neg)) => {
                    c.is_some_and(|c| c != '/' && (r.iter().any(|(a, b)| *a <= c && c <= *b) != *neg)) && next.get(j + 1).copied().unwrap_or(false)
                }
                Some(Tok::Star) => next[j] || (c.is_some_and(|c| c != '/') && cur.get(j + 1).copied().unwrap_or(false)),
                Some(Tok::Globstar) => next[j] || (c.is_some() && cur.get(j + 1).copied().unwrap_or(false)),
                Some(Tok::GlobstarSlash) => {
                    // Empty, or any run ending in '/'.
                    next[j] || (j..m).any(|k| s.get(k) == Some(&'/') && next.get(k + 1).copied().unwrap_or(false))
                }
                None => false,
            };
        }
        next = cur;
    }
    next[0]
}

#[derive(Debug, Clone)]
struct Rule {
    base: String,
    tokens: Vec<Tok>,
    negate: bool,
    dir_only: bool,
    anchored: bool,
}

/// `.gitignore` rules collected while walking a tree. Later rules win, `!` re-includes.
#[derive(Debug, Clone, Default)]
pub struct Ignore {
    rules: Vec<Rule>,
}

impl Ignore {
    /// Add the rules of a `.gitignore` found in `base_dir` (relative, "" for the root).
    pub fn add_file(&mut self, base_dir: &str, text: &str) {
        for line in text.lines().take(10_000) {
            let line = line.trim_end();
            if line.is_empty() || line.starts_with('#') {
                continue;
            }
            let (negate, pat) = match line.strip_prefix('!') {
                Some(p) => (true, p),
                None => (false, line.strip_prefix("\\").unwrap_or(line)),
            };
            let dir_only = pat.ends_with('/');
            let pat = pat.trim_end_matches('/');
            if pat.is_empty() || pat.len() > 512 {
                continue;
            }
            let anchored = pat.contains('/');
            let pat = pat.trim_start_matches('/');
            self.rules.push(Rule { base: base_dir.trim_matches('/').to_string(), tokens: tokenize_glob(pat), negate, dir_only, anchored });
        }
    }

    /// Whether `path` (relative to the walk root) is ignored.
    pub fn is_ignored(&self, path: &str, is_dir: bool) -> bool {
        let mut ignored = false;
        for r in &self.rules {
            if r.dir_only && !is_dir {
                continue;
            }
            let rel = if r.base.is_empty() {
                path
            } else {
                match path.strip_prefix(&r.base).and_then(|p| p.strip_prefix('/')) {
                    Some(p) => p,
                    None => continue,
                }
            };
            let target = if r.anchored { rel } else { rel.rsplit('/').next().unwrap_or(rel) };
            if glob_match(&r.tokens, target) {
                ignored = !r.negate;
            }
        }
        ignored
    }
}

// ---------------------------------------------------------------------------------------------
// Source graph

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default)]
pub struct SourceFile {
    pub path: String,
    pub bytes: u64,
    pub sha256: String,
    pub language: String,
    pub exports: Vec<String>,
    pub imports: Vec<String>,
    pub functions: Vec<String>,
    pub strings: Vec<String>,
    pub fingerprint: Option<String>,
    pub parse_mode: Option<js::ParseMode>,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default)]
pub struct SourceGraph {
    /// `sg_` + sha256 of the (path, sha256) list.
    pub source_graph_id: String,
    pub label: String,
    pub files: Vec<SourceFile>,
    pub ignored: usize,
    pub truncated: bool,
    pub languages: BTreeMap<String, usize>,
}

fn language(path: &str) -> &'static str {
    let l = path.to_ascii_lowercase();
    match l.rsplit('.').next().unwrap_or("") {
        "ts" | "mts" | "cts" => "typescript",
        "tsx" => "typescript-jsx",
        "js" | "mjs" | "cjs" => "javascript",
        "jsx" => "javascript-jsx",
        "json" => "json",
        "html" | "htm" => "html",
        "css" | "scss" | "less" => "stylesheet",
        "vue" => "vue",
        "svelte" => "svelte",
        "rs" => "rust",
        "go" => "go",
        "py" => "python",
        "java" | "kt" => "jvm",
        "swift" | "m" | "mm" => "apple",
        "c" | "h" | "cc" | "cpp" | "hpp" => "c-family",
        "md" => "markdown",
        _ => "other",
    }
}

/// Summarise a source tree. `files` are (relative path, bytes); ignored count comes from the walker.
pub fn build_source_graph(
    label: &str,
    files: &[(String, Vec<u8>)],
    ignored: usize,
    truncated: bool,
    limits: &js::Limits,
    cancelled: &dyn Fn() -> bool,
) -> Result<SourceGraph, Cancelled> {
    let mut g = SourceGraph { label: label.to_string(), ignored, truncated, ..Default::default() };
    for (i, (path, bytes)) in files.iter().enumerate() {
        if i % 16 == 0 && cancelled() {
            return Err(Cancelled);
        }
        let lang = language(path);
        *g.languages.entry(lang.to_string()).or_default() += 1;
        let mut f = SourceFile { path: path.clone(), bytes: bytes.len() as u64, sha256: sha256_hex(bytes), language: lang.into(), ..Default::default() };
        if is_script(path) {
            let text = String::from_utf8_lossy(bytes);
            let a = js::analyze(path, &text, limits);
            f.exports = a.facts.exports.esm.iter().chain(a.facts.exports.cjs.iter()).cloned().collect();
            f.imports = a.facts.imports.iter().map(|i| i.specifier.clone()).take(500).collect();
            f.functions =
                a.facts.functions.iter().filter(|x| !x.name.starts_with('<') && !x.name.contains(" callback@")).map(|x| x.name.clone()).take(500).collect();
            f.strings = a.facts.strings.iter().take(500).cloned().collect();
            f.fingerprint = a.facts.fingerprint;
            f.parse_mode = Some(a.facts.mode);
        }
        g.files.push(f);
    }
    let ids: Vec<(&String, &String)> = g.files.iter().map(|f| (&f.path, &f.sha256)).collect();
    g.source_graph_id = format!("sg_{}", sha256_hex(craft_anything_evidence::canonical_json(&json!(ids)).as_bytes()));
    Ok(g)
}

// ---------------------------------------------------------------------------------------------
// Source ↔ bundle

/// Normalise a module id or source-map source to a comparable path without extension.
pub fn norm_path(p: &str) -> String {
    let mut s = p.trim();
    for pre in ["webpack:///", "webpack://", "file://", "vite:", "rollup:", "esbuild:"] {
        if let Some(r) = s.strip_prefix(pre) {
            s = r;
        }
    }
    // `webpack://appname/./src/x.js` → keep the part after the first "./"
    if let Some(i) = s.find("/./") {
        s = s.get(i + 3..).unwrap_or(s);
    }
    let parts: Vec<&str> = s.split(['/', '\\']).filter(|p| !p.is_empty() && *p != "." && *p != "..").collect();
    let joined = parts.join("/");
    let stem = match joined.rsplit_once('.') {
        Some((a, ext)) if ext.len() <= 5 && !a.is_empty() && !ext.contains('/') => a.to_string(),
        _ => joined,
    };
    stem.to_ascii_lowercase()
}

fn tail_match(a: &str, b: &str) -> bool {
    !a.is_empty() && !b.is_empty() && (a == b || a.ends_with(&format!("/{b}")) || b.ends_with(&format!("/{a}")))
}

fn overlap(a: &BTreeSet<&str>, b: &BTreeSet<&str>) -> (usize, f64) {
    let shared = a.intersection(b).count();
    let min = a.len().min(b.len());
    (shared, if min == 0 { 0.0 } else { shared as f64 / min as f64 })
}

struct Unit<'a> {
    id: String,
    file: &'a str,
    kind: &'static str,
    norm: String,
    strings: BTreeSet<&'a str>,
    functions: BTreeSet<&'a str>,
    exports: BTreeSet<&'a str>,
}

/// Match reference source files to the shipped bundle's files and bundle modules.
pub fn diff_source_and_bundle(src: &SourceGraph, app: &AppGraph, max_rows: usize) -> Value {
    let mut units: Vec<Unit<'_>> = Vec::new();
    for m in app.modules.iter().filter(|m| m.kind == "script") {
        units.push(Unit {
            id: m.path.clone(),
            file: &m.path,
            kind: "file",
            norm: norm_path(&m.path),
            strings: m.strings.iter().map(String::as_str).filter(|s| s.len() >= 4).collect(),
            functions: m.functions.iter().map(String::as_str).collect(),
            exports: m.exports.esm.iter().chain(m.exports.cjs.iter()).map(String::as_str).collect(),
        });
        for b in &m.bundle_modules {
            units.push(Unit {
                id: b.id.clone(),
                file: &m.path,
                kind: "bundle-module",
                norm: norm_path(&b.id),
                strings: b.strings.iter().map(String::as_str).filter(|s| s.len() >= 4).collect(),
                functions: b.functions.iter().map(String::as_str).collect(),
                exports: BTreeSet::new(),
            });
        }
    }
    // Source-map sources → generated script.
    let mut mapped: Vec<(String, &str)> = Vec::new();
    for sm in &app.source_maps {
        for s in &sm.sources {
            mapped.push((norm_path(s), sm.script.as_str()));
        }
    }
    // Inverted index: string/function → units.
    let mut index: HashMap<&str, Vec<usize>> = HashMap::new();
    for (i, u) in units.iter().enumerate() {
        for s in u.strings.iter().chain(u.functions.iter()) {
            let v = index.entry(*s).or_default();
            if v.len() < 64 {
                v.push(i);
            }
        }
    }
    let mut matches = Vec::new();
    let mut unmatched = Vec::new();
    let mut claimed: BTreeSet<usize> = BTreeSet::new();
    let mut by_quality: BTreeMap<&str, usize> = BTreeMap::new();
    for f in src.files.iter().filter(|f| is_script(&f.path)).take(max_rows) {
        let norm = norm_path(&f.path);
        let fs: BTreeSet<&str> = f.strings.iter().map(String::as_str).filter(|s| s.len() >= 4).collect();
        let ff: BTreeSet<&str> = f.functions.iter().map(String::as_str).collect();
        let fe: BTreeSet<&str> = f.exports.iter().map(String::as_str).collect();
        let mut cands: BTreeSet<usize> = units.iter().enumerate().filter(|(_, u)| tail_match(&u.norm, &norm)).map(|(i, _)| i).collect();
        for s in fs.iter().chain(ff.iter()) {
            for i in index.get(s).into_iter().flatten() {
                if cands.len() < 512 {
                    cands.insert(*i);
                }
            }
        }
        let mut best: Option<(f64, usize, Vec<String>)> = None;
        for i in cands {
            let Some(u) = units.get(i) else { continue };
            let mut reasons = Vec::new();
            let mut score: f64 = 0.0;
            if tail_match(&u.norm, &norm) {
                score = 1.0;
                reasons.push("same path".to_string());
            }
            let (ss, so) = overlap(&fs, &u.strings);
            let (fsh, fo) = overlap(&ff, &u.functions);
            let (es, eo) = overlap(&fe, &u.exports);
            let combined = (0.5 * if ss >= 2 { so } else { 0.0 } + 0.4 * if fsh >= 1 { fo } else { 0.0 } + 0.3 * if es >= 1 { eo } else { 0.0 }).min(0.95);
            if ss >= 2 {
                reasons.push(format!("{ss} shared strings"));
            }
            if fsh >= 1 {
                reasons.push(format!("{fsh} shared function names"));
            }
            if es >= 1 {
                reasons.push(format!("{es} shared export names"));
            }
            score = score.max(combined);
            if best.as_ref().is_none_or(|(b, _, _)| score > *b) {
                best = Some((score, i, reasons));
            }
        }
        let via_map = mapped.iter().find(|(s, _)| tail_match(s, &norm)).map(|(_, script)| *script);
        match best.filter(|(s, _, _)| *s >= 0.3) {
            Some((score, i, reasons)) => {
                claimed.insert(i);
                let quality = if score >= 0.99 {
                    "strong"
                } else if score >= 0.6 {
                    "probable"
                } else {
                    "weak"
                };
                *by_quality.entry(quality).or_default() += 1;
                let u = units.get(i);
                matches.push(json!({
                    "source": f.path, "unit": u.map(|u| &u.id), "file": u.map(|u| u.file), "unit_kind": u.map(|u| u.kind),
                    "score": (score * 100.0).round() / 100.0, "quality": quality, "reasons": reasons, "listed_in_source_map_of": via_map,
                }));
            }
            None => match via_map {
                Some(script) => {
                    *by_quality.entry("source-map-only").or_default() += 1;
                    matches.push(json!({"source": f.path, "unit": script, "file": script, "unit_kind": "file", "score": 0.9, "quality": "source-map", "reasons": ["listed in the bundle's source map"]}));
                }
                None => unmatched.push(f.path.clone()),
            },
        }
    }
    let unclaimed: Vec<Value> = units
        .iter()
        .enumerate()
        .filter(|(i, u)| !claimed.contains(i) && !u.id.contains("node_modules"))
        .map(|(_, u)| json!({"unit": u.id, "file": u.file, "kind": u.kind}))
        .take(max_rows)
        .collect();
    json!({
        "source_graph_id": src.source_graph_id,
        "graph_id": app.graph_id,
        "summary": {"source_scripts": src.files.iter().filter(|f| is_script(&f.path)).count(), "bundle_units": units.len(), "matched": matches.len(), "unmatched_sources": unmatched.len(), "bundle_units_without_source": unclaimed.len(), "by_quality": by_quality},
        "matches": matches,
        "unmatched_sources": unmatched,
        "bundle_units_without_source": unclaimed,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use craft_anything_testkit::electron as fx;

    #[test]
    fn gitignore_rules() {
        let mut ig = Ignore::default();
        ig.add_file("", "node_modules/\n*.log\n/dist\n!keep.log\nsrc/**/gen/*.js\n# comment\n");
        ig.add_file("pkg", "secret.txt\n");
        assert!(ig.is_ignored("node_modules", true));
        assert!(!ig.is_ignored("node_modules", false), "dir-only rule");
        assert!(ig.is_ignored("a/b/debug.log", false));
        assert!(!ig.is_ignored("keep.log", false));
        assert!(ig.is_ignored("dist", true));
        assert!(!ig.is_ignored("x/dist", true), "anchored to the root");
        assert!(ig.is_ignored("src/a/b/gen/x.js", false));
        assert!(ig.is_ignored("src/gen/x.js", false));
        assert!(ig.is_ignored("pkg/secret.txt", false));
        assert!(!ig.is_ignored("secret.txt", false));
        assert!(glob_match(&tokenize_glob("[a-c]?.js"), "bz.js"));
        assert!(!glob_match(&tokenize_glob("[!a-c]?.js"), "bz.js"));
        // Pathological patterns stay fast.
        let _ = glob_match(&tokenize_glob(&"*a".repeat(100)), &"a".repeat(2000));
    }

    #[test]
    fn sources_match_bundle_modules() {
        let a = craft_anything_js::analyze("main.js", fx::WEBPACK_BUNDLE, &js::Limits::default());
        assert!(!a.bundle.modules.is_empty());
        let app = crate::js_app::tests_support::graph_of(vec![("dist/main.js", fx::WEBPACK_BUNDLE.to_string())]);
        let files = vec![
            ("src/api.js".to_string(), b"const base = 'https://api.example.test'; module.exports = { list: () => fetch(base + '/items') };".to_vec()),
            ("src/util.js".to_string(), b"exports.sum = (a, b) => a + b;".to_vec()),
            ("src/orphan.js".to_string(), b"export const nothing = 1;".to_vec()),
            ("README.md".to_string(), b"# hi".to_vec()),
        ];
        let sg = build_source_graph("src", &files, 0, false, &js::Limits::default(), &|| false).unwrap();
        assert!(sg.source_graph_id.starts_with("sg_"));
        let d = diff_source_and_bundle(&sg, &app, 1000);
        let m = d["matches"].as_array().unwrap();
        assert!(m.iter().any(|x| x["source"] == "src/api.js" && x["unit"] == "./src/api.js" && x["quality"] == "strong"), "{d}");
        assert_eq!(d["unmatched_sources"], json!(["src/orphan.js"]));
    }

    #[test]
    fn norm() {
        assert_eq!(norm_path("webpack://notes/./src/App.tsx"), "src/app");
        assert_eq!(norm_path("../src/x.js"), "src/x");
        assert_eq!(norm_path("./src/index.js"), "src/index");
    }
}
