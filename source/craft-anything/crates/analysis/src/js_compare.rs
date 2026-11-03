//! Comparing two application graphs: modules (tiered matching), bundle modules, IPC, endpoints,
//! routes, windows, native modules, vendors and export outlines.

use crate::js_app::{AppGraph, ModuleSummary};
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};

fn set<'a>(it: impl Iterator<Item = &'a str>) -> BTreeSet<String> {
    it.map(String::from).collect()
}

fn diff(left: &BTreeSet<String>, right: &BTreeSet<String>) -> Value {
    json!({
        "added": right.difference(left).take(2000).collect::<Vec<_>>(),
        "removed": left.difference(right).take(2000).collect::<Vec<_>>(),
        "unchanged": left.intersection(right).count(),
    })
}

/// A segment a bundler puts in a file name for its content hash: 6-32 letters, digits or `_` that
/// contain a digit or mix upper and lower case (`DIpf_I7N`, `3f2a9c1b`, `UGNM3QZK`), so plain
/// words (`browser`, `vendors`) aren't taken for one.
fn looks_like_hash(s: &str) -> bool {
    (6..=32).contains(&s.len())
        && s.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'_')
        && (s.bytes().any(|b| b.is_ascii_digit()) || (s.bytes().any(|b| b.is_ascii_uppercase()) && s.bytes().any(|b| b.is_ascii_lowercase())))
}

/// A path with its build hash taken out (`assets/Doctor-DIpf_I7N.js` → `assets/Doctor-*.js`), or
/// None when its name carries none.
fn without_build_hash(path: &str) -> Option<String> {
    let (dir, name) = path.rsplit_once('/').map_or(("", path), |(d, n)| (d, n));
    let (stem, ext) = name.split_once('.').map_or((name, ""), |(s, e)| (s, e));
    // `name-HASH.ext` (Vite, esbuild; Vite's hashes may contain `_`) …
    if let Some((base, hash)) = stem.rsplit_once('-')
        && !base.is_empty()
        && looks_like_hash(hash)
    {
        return Some(format!("{dir}/{base}-*.{ext}"));
    }
    // … or `name.HASH.ext` (webpack): the hash is the second dot-part.
    let parts: Vec<&str> = name.split('.').collect();
    if parts.len() >= 3 && parts.get(1).is_some_and(|h| looks_like_hash(h)) {
        return Some(format!("{dir}/{}.*.{}", parts[0], parts[2..].join(".")));
    }
    None
}

/// Same content: by hash, or, for a module saved without one (an inline script in a map from
/// before #236), by its structure, size and strings.
fn same_content(a: &ModuleSummary, b: &ModuleSummary) -> bool {
    if a.sha256.is_empty() || b.sha256.is_empty() {
        a.fingerprint == b.fingerprint && a.bytes == b.bytes && a.strings == b.strings
    } else {
        a.sha256 == b.sha256
    }
}

/// Match modules: same path and content → unchanged; same path → changed; same content
/// elsewhere → moved; the same name apart from a bundler's build hash (one on each side) →
/// changed, with the old name; same structure (fingerprint) elsewhere → renamed. Each right
/// module is used once.
fn match_modules<'a>(l: &'a [ModuleSummary], r: &'a [ModuleSummary]) -> Value {
    // Names without their build hash that occur exactly once on each side.
    let unique = |mods: &'a [ModuleSummary]| {
        let mut count: BTreeMap<String, usize> = BTreeMap::new();
        for m in mods {
            if let Some(k) = without_build_hash(&m.path) {
                *count.entry(k).or_default() += 1;
            }
        }
        count.into_iter().filter(|(_, n)| *n == 1).map(|(k, _)| k).collect::<BTreeSet<String>>()
    };
    let (unique_l, unique_r) = (unique(l), unique(r));
    let mut used: BTreeSet<usize> = BTreeSet::new();
    let mut unchanged = 0usize;
    let mut changed = Vec::new();
    let mut moved = Vec::new();
    let mut renamed = Vec::new();
    let mut removed = Vec::new();
    for m in l {
        if let Some(i) = r.iter().position(|x| x.path == m.path) {
            used.insert(i);
            match r.get(i) {
                Some(x) if same_content(x, m) => unchanged += 1,
                Some(x) => changed.push(json!({
                    "path": m.path,
                    "same_structure": x.fingerprint.is_some() && x.fingerprint == m.fingerprint,
                    "bytes": [m.bytes, x.bytes],
                    "exports": export_diff(m, x),
                    "functions": diff(&set(m.functions.iter().map(String::as_str)), &set(x.functions.iter().map(String::as_str))),
                })),
                None => {}
            }
            continue;
        }
        if let Some(i) = r.iter().enumerate().position(|(i, x)| !used.contains(&i) && x.sha256 == m.sha256 && !m.sha256.is_empty()) {
            used.insert(i);
            moved.push(json!({"from": m.path, "to": r.get(i).map(|x| &x.path)}));
            continue;
        }
        let hashless = without_build_hash(&m.path).filter(|k| unique_l.contains(k) && unique_r.contains(k));
        if let Some(i) = hashless.and_then(|k| r.iter().enumerate().position(|(i, x)| !used.contains(&i) && without_build_hash(&x.path).as_ref() == Some(&k))) {
            used.insert(i);
            if let Some(x) = r.get(i) {
                changed.push(json!({
                    "path": x.path,
                    "was": m.path,
                    "matched_by": "name without build hash",
                    "same_structure": x.fingerprint.is_some() && x.fingerprint == m.fingerprint,
                    "bytes": [m.bytes, x.bytes],
                    "exports": export_diff(m, x),
                    "functions": diff(&set(m.functions.iter().map(String::as_str)), &set(x.functions.iter().map(String::as_str))),
                }));
            }
            continue;
        }
        if let Some(i) = r.iter().enumerate().position(|(i, x)| !used.contains(&i) && x.fingerprint.is_some() && x.fingerprint == m.fingerprint) {
            used.insert(i);
            renamed.push(json!({"from": m.path, "to": r.get(i).map(|x| &x.path), "matched_by": "structure"}));
            continue;
        }
        removed.push(m.path.clone());
    }
    let added: Vec<&String> = r.iter().enumerate().filter(|(i, _)| !used.contains(i)).map(|(_, x)| &x.path).collect();
    json!({"unchanged": unchanged, "changed": changed, "moved": moved, "renamed": renamed, "added": added, "removed": removed})
}

fn export_diff(a: &ModuleSummary, b: &ModuleSummary) -> Value {
    let l = set(a.exports.esm.iter().chain(a.exports.cjs.iter()).map(String::as_str));
    let r = set(b.exports.esm.iter().chain(b.exports.cjs.iter()).map(String::as_str));
    let mut v = diff(&l, &r);
    if a.exports.cjs_whole != b.exports.cjs_whole
        && let Some(o) = v.as_object_mut()
    {
        o.insert("module_exports".into(), json!([a.exports.cjs_whole, b.exports.cjs_whole]));
    }
    v
}

/// Bundle modules across both graphs: by content, then structure, then id.
fn match_bundle_modules(l: &AppGraph, r: &AppGraph) -> Value {
    let lm: Vec<(&str, &crate::js_app::BundleModuleSummary)> =
        l.modules.iter().flat_map(|m| m.bundle_modules.iter().map(move |b| (m.path.as_str(), b))).collect();
    let rm: Vec<(&str, &crate::js_app::BundleModuleSummary)> =
        r.modules.iter().flat_map(|m| m.bundle_modules.iter().map(move |b| (m.path.as_str(), b))).collect();
    let mut used = BTreeSet::new();
    let mut tiers: BTreeMap<&str, usize> = BTreeMap::new();
    let mut changed = Vec::new();
    let mut removed = Vec::new();
    for (lp, b) in &lm {
        let tier = [
            ("content", rm.iter().enumerate().position(|(i, (_, x))| !used.contains(&i) && x.sha256 == b.sha256)),
            ("structure", rm.iter().enumerate().position(|(i, (_, x))| !used.contains(&i) && x.fingerprint == b.fingerprint)),
            ("id", rm.iter().enumerate().position(|(i, (_, x))| !used.contains(&i) && x.id == b.id)),
        ]
        .into_iter()
        .find_map(|(t, i)| i.map(|i| (t, i)));
        match tier {
            Some((t, i)) => {
                used.insert(i);
                *tiers.entry(t).or_default() += 1;
                if t == "id" && changed.len() < 2000 {
                    changed.push(json!({"id": b.id, "file": lp}));
                }
            }
            None => removed.push(json!({"id": b.id, "file": lp})),
        }
    }
    let added: Vec<Value> = rm.iter().enumerate().filter(|(i, _)| !used.contains(i)).map(|(_, (p, b))| json!({"id": b.id, "file": p})).take(2000).collect();
    json!({"left": lm.len(), "right": rm.len(), "matched_by": tiers, "changed": changed, "added": added, "removed": removed})
}

fn str_field<'a>(v: &'a [Value], key: &'a str) -> impl Iterator<Item = &'a str> {
    v.iter().filter_map(move |x| x.get(key).and_then(Value::as_str))
}

/// The full version comparison.
pub fn compare_versions(l: &AppGraph, r: &AppGraph) -> Value {
    let pkg = |g: &AppGraph, k: &str| g.package.as_ref().and_then(|p| p.get(k)).cloned().unwrap_or(Value::Null);
    let channels = |g: &AppGraph| set(g.ipc.iter().map(|c| c.channel.as_str()));
    let handlers = |g: &AppGraph| set(g.ipc.iter().filter(|c| !c.handlers.is_empty() || !c.main_listeners.is_empty()).map(|c| c.channel.as_str()));
    let endpoints = |g: &AppGraph| {
        g.endpoints
            .iter()
            .filter(|e| e.get("api").and_then(Value::as_str) != Some("literal"))
            .map(|e| format!("{} {}", e.get("method").and_then(Value::as_str).unwrap_or("*"), e.get("url").and_then(Value::as_str).unwrap_or("")))
            .collect::<BTreeSet<_>>()
    };
    let urls = |g: &AppGraph| set(str_field(&g.endpoints, "url"));
    let routes = |g: &AppGraph| set(str_field(&g.routes, "path"));
    let natives = |g: &AppGraph| set(str_field(&g.native_modules, "name"));
    let members = |g: &AppGraph| {
        g.exposed
            .iter()
            .flat_map(|e| {
                let key = e.get("key").and_then(Value::as_str).unwrap_or("?").to_string();
                e.get("members")
                    .and_then(Value::as_array)
                    .into_iter()
                    .flatten()
                    .filter_map(move |m| m.get("name").and_then(Value::as_str).map(|n| format!("window.{key}.{n}")))
            })
            .collect::<BTreeSet<_>>()
    };
    let vendors = |g: &AppGraph| {
        g.vendors
            .iter()
            .filter_map(|v| Some((v.get("name")?.as_str()?.to_string(), v.get("version").and_then(Value::as_str).unwrap_or("").to_string())))
            .collect::<BTreeMap<_, _>>()
    };
    let (lv, rv) = (vendors(l), vendors(r));
    let vendor_changes: Vec<Value> = lv
        .iter()
        .filter_map(|(n, v)| rv.get(n).filter(|w| *w != v).map(|w| json!({"name": n, "from": v, "to": w})))
        .chain(rv.keys().filter(|n| !lv.contains_key(*n)).map(|n| json!({"name": n, "added": true})))
        .chain(lv.keys().filter(|n| !rv.contains_key(*n)).map(|n| json!({"name": n, "removed": true})))
        .take(2000)
        .collect();
    let windows = |g: &AppGraph| {
        // An unassigned constructor has no binding, and local bindings can repeat in different
        // functions. Keep each occurrence instead of overwriting all but the last one. The order
        // within a module and binding is stable when comments shift the source line numbers.
        let mut occurrences = BTreeMap::new();
        g.windows
            .iter()
            .map(|w| {
                let module = w.get("module").and_then(Value::as_str).unwrap_or("").to_string();
                let binding = w.get("binding").and_then(Value::as_str).unwrap_or("").to_string();
                let count = occurrences.entry((module.clone(), binding.clone())).or_insert(0usize);
                let occurrence = *count;
                *count = count.saturating_add(1);
                ((module, binding, occurrence), w.get("web_preferences").cloned().unwrap_or(Value::Null))
            })
            .collect::<BTreeMap<_, _>>()
    };
    let (lw, rw) = (windows(l), windows(r));
    let window_changes: Vec<Value> = lw
        .iter()
        .filter_map(|(key, v)| {
            rw.get(key).filter(|w| *w != v).map(|w| {
                let (module, binding, occurrence) = key;
                let name = if binding.is_empty() || *occurrence > 0 {
                    format!("{module}:{binding}[{}]", occurrence.saturating_add(1))
                } else {
                    format!("{module}:{binding}")
                };
                json!({"window": name, "from": v, "to": w})
            })
        })
        .collect();
    json!({
        "left": {"graph_id": l.graph_id, "label": l.label, "version": pkg(l, "version"), "name": pkg(l, "name")},
        "right": {"graph_id": r.graph_id, "label": r.label, "version": pkg(r, "version"), "name": pkg(r, "name")},
        "identical_graph": l.graph_id == r.graph_id,
        "modules": match_modules(&l.modules, &r.modules),
        "bundle_modules": match_bundle_modules(l, r),
        "ipc_channels": diff(&channels(l), &channels(r)),
        "ipc_handlers": diff(&handlers(l), &handlers(r)),
        "bridge_members": diff(&members(l), &members(r)),
        "endpoints": diff(&endpoints(l), &endpoints(r)),
        "urls": diff(&urls(l), &urls(r)),
        "routes": diff(&routes(l), &routes(r)),
        "native_modules": diff(&natives(l), &natives(r)),
        "vendors": vendor_changes,
        "windows": {"changed": window_changes, "left": lw.len(), "right": rw.len()},
    })
}

/// Export outlines module by module (matched by path, then by structure).
pub fn compare_export_outlines(l: &AppGraph, r: &AppGraph) -> Value {
    let mut rows = Vec::new();
    let mut used = BTreeSet::new();
    let mut changed = 0usize;
    for m in l.modules.iter().filter(|m| m.kind == "script") {
        let idx = r
            .modules
            .iter()
            .position(|x| x.path == m.path)
            .or_else(|| r.modules.iter().position(|x| x.fingerprint.is_some() && x.fingerprint == m.fingerprint));
        match idx.and_then(|i| r.modules.get(i).map(|x| (i, x))) {
            Some((i, x)) => {
                used.insert(i);
                let d = export_diff(m, x);
                let same =
                    d["added"].as_array().is_some_and(Vec::is_empty) && d["removed"].as_array().is_some_and(Vec::is_empty) && d.get("module_exports").is_none();
                if !same {
                    changed += 1;
                }
                rows.push(json!({"left": m.path, "right": x.path, "same": same, "diff": d, "left_outline": m.exports, "right_outline": x.exports}));
            }
            None => rows.push(json!({"left": m.path, "right": null, "removed": true, "left_outline": m.exports})),
        }
    }
    for (i, x) in r.modules.iter().enumerate().filter(|(_, x)| x.kind == "script") {
        if !used.contains(&i) {
            rows.push(json!({"left": null, "right": x.path, "added": true, "right_outline": x.exports}));
        }
    }
    json!({"modules": rows, "changed": changed})
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::js_app::tests_support::{graph_of, notes_graph};
    use craft_anything_testkit::electron as fx;

    #[test]
    fn build_hashes_in_names_are_recognised_and_plain_words_are_not() {
        assert_eq!(without_build_hash("assets/Doctor-DIpf_I7N.js").as_deref(), Some("assets/Doctor-*.js"));
        assert_eq!(without_build_hash("assets/Doctor-DrkWsav4.js").as_deref(), Some("assets/Doctor-*.js"));
        assert_eq!(without_build_hash("dist/main.3f2a9c1b.js").as_deref(), Some("dist/main.*.js"));
        assert_eq!(without_build_hash("out/chunk-UGNM3QZK.mjs").as_deref(), Some("out/chunk-*.mjs"));
        for plain in ["src/index-browser.js", "dist/chunk-vendors.js", "react-dom.js", "main.js", "app.min.js", "a/b-c.js"] {
            assert_eq!(without_build_hash(plain), None, "{plain}");
        }
    }

    /// From comparing two releases of a large Electron app: chunks renamed only by their build
    /// hash were 162 "removed" + "added"; they're one changed module each, and two chunks that
    /// share a name without their hash aren't guessed between.
    #[test]
    fn chunks_renamed_by_their_build_hash_pair_up() {
        let m = |path: &str, sha: &str| ModuleSummary { path: path.into(), sha256: sha.into(), kind: "script".into(), ..Default::default() };
        let left = [m("assets/Doctor-DIpf_I7N.js", "a1"), m("assets/index-Ab12cd34.js", "b1"), m("assets/index-Ef56gh78.js", "c1"), m("main.js", "d1")];
        let right = [m("assets/Doctor-DrkWsav4.js", "a2"), m("assets/index-Zz99yy88.js", "b2"), m("assets/index-Qq77ww66.js", "c2"), m("main.js", "d1")];
        let d = match_modules(&left, &right);
        assert_eq!(d["unchanged"], 1);
        let changed = d["changed"].as_array().unwrap();
        assert_eq!(changed.len(), 1, "{d}");
        assert_eq!((changed[0]["was"].as_str(), changed[0]["path"].as_str()), (Some("assets/Doctor-DIpf_I7N.js"), Some("assets/Doctor-DrkWsav4.js")));
        assert_eq!(d["removed"].as_array().unwrap().len(), 2, "two index chunks: ambiguous, left alone");
        assert_eq!(d["added"].as_array().unwrap().len(), 2);
    }

    #[test]
    fn versions_differ_where_expected() {
        let a = notes_graph();
        let b = graph_of(fx::notes_app_v2_files());
        let d = compare_versions(&a, &b);
        assert_eq!(d["left"]["version"], "1.0.0");
        assert_eq!(d["right"]["version"], "2.0.0");
        assert_eq!(d["ipc_channels"]["added"], json!(["import-notes"]));
        assert_eq!(d["modules"]["changed"][0]["path"], "main.js");
        assert_eq!(d["identical_graph"], false);
        let same = compare_versions(&a, &a);
        assert_eq!(same["identical_graph"], true);
        assert_eq!(same["modules"]["unchanged"], 4);
    }

    fn window_graph(bindings: &[&str], preferences: &[bool], prefix: &str) -> AppGraph {
        let mut source = format!("{prefix}const {{ BrowserWindow }} = require('electron');\n");
        for (i, (binding, preference)) in bindings.iter().zip(preferences).enumerate() {
            let assign = if binding.is_empty() { String::new() } else { format!("const {binding} = ") };
            source.push_str(&format!("function make_{i}() {{ {assign}new BrowserWindow({{ webPreferences: {{ backgroundThrottling: {preference} }} }}); }}\n"));
        }
        graph_of(vec![("package.json", r#"{"name":"window-example","main":"main.js"}"#.into()), ("main.js", source)])
    }

    #[test]
    fn unassigned_windows_keep_each_preference_change() {
        let left = window_graph(&["", ""], &[false, false], "");
        assert_eq!(left.windows.len(), 2);
        let mut ids = Vec::new();
        for prefs in [[true, false], [false, true]] {
            let right = window_graph(&["", ""], &prefs, "");
            let windows = compare_versions(&left, &right)["windows"].clone();
            assert_eq!(windows["left"], 2, "{windows}");
            assert_eq!(windows["right"], 2);
            let changed = windows["changed"].as_array().unwrap();
            assert_eq!(changed.len(), 1, "{windows}");
            assert_eq!(changed[0]["from"]["backgroundThrottling"], false);
            assert_eq!(changed[0]["to"]["backgroundThrottling"], true);
            ids.push(changed[0]["window"].clone());
        }
        assert_ne!(ids[0], ids[1], "the changed constructions are distinguishable");
    }

    #[test]
    fn window_comparisons_keep_named_and_reused_bindings() {
        for bindings in [["primary", "secondary"], ["panel", "panel"]] {
            let left = window_graph(&bindings, &[false, true], "");
            let right = window_graph(&bindings, &[true, true], "");
            let windows = compare_versions(&left, &right)["windows"].clone();
            assert_eq!(windows["left"], 2, "{windows}");
            assert_eq!(windows["right"], 2);
            assert_eq!(windows["changed"].as_array().unwrap().len(), 1, "{windows}");
            if bindings[0] == "primary" {
                assert_eq!(windows["changed"][0]["window"], "main.js:primary", "unique binding identifiers stay stable");
            }
        }
    }

    #[test]
    fn window_comparisons_do_not_depend_on_source_line_numbers() {
        let left = window_graph(&["", ""], &[false, true], "");
        let shifted = window_graph(&["", ""], &[false, true], "// Added explanation\n\n");
        let same = compare_versions(&left, &shifted)["windows"].clone();
        assert_eq!(same, json!({"left": 2, "right": 2, "changed": []}));
        let right = window_graph(&["", "", ""], &[true, true, false], "// Added explanation\n\n");
        let windows = compare_versions(&left, &right)["windows"].clone();
        assert_eq!((windows["left"].as_u64(), windows["right"].as_u64()), (Some(2), Some(3)));
        assert_eq!(windows["changed"].as_array().unwrap().len(), 1, "the first preference change survives shifted lines");
    }

    /// #236: an edited inline script had no hash on either side and counted as unchanged.
    #[test]
    fn an_edited_inline_script_is_changed() {
        let page = |says: &str| graph_of(vec![("index.html", format!("<html><script>console.log(\"{says}\");</script></html>"))]);
        let (a, b) = (page("A"), page("B"));
        assert!(a.modules.iter().all(|m| !m.sha256.is_empty()), "{:?}", a.modules);
        let d = compare_versions(&a, &b);
        let changed: Vec<&str> = d["modules"]["changed"].as_array().unwrap().iter().filter_map(|c| c["path"].as_str()).collect();
        assert_eq!(changed, ["index.html#inline-0", "index.html"], "{d}");
        assert_eq!(compare_versions(&a, &a)["modules"]["unchanged"], 2);
        // Maps saved before inline scripts had a hash.
        let unhashed = |g: &AppGraph| {
            g.modules
                .iter()
                .cloned()
                .map(|m| ModuleSummary { sha256: if m.path.contains("#inline-") { String::new() } else { m.sha256 }, ..m })
                .collect::<Vec<_>>()
        };
        assert_eq!(match_modules(&unhashed(&a), &unhashed(&a))["unchanged"], 2);
        assert_eq!(match_modules(&unhashed(&a), &unhashed(&b))["changed"].as_array().unwrap().len(), 2);
    }

    #[test]
    fn export_outlines() {
        let a = graph_of(vec![("lib.js", "exports.a = 1; exports.b = 2;".into())]);
        let b = graph_of(vec![("lib.js", "exports.a = 1; exports.c = 3;".into())]);
        let d = compare_export_outlines(&a, &b);
        assert_eq!(d["changed"], 1);
        assert_eq!(d["modules"][0]["diff"]["added"], json!(["c"]));
        assert_eq!(d["modules"][0]["diff"]["removed"], json!(["b"]));
    }
}
