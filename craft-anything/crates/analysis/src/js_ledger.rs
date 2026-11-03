//! Rebuild ledgers: what a clean-room rebuild must do, where in the rebuild each expectation
//! lives, and whether strong enough evidence and checks prove it.
//!
//! An expectation is proven only when one place in the rebuild owns it, its parser type is named
//! (where the layer needs one), every case it must cover has evidence at least as strong as it
//! asks for, and a passing check of that strength lists it and cites its result. So a unit test
//! never proves something only the built app can show, and static facts never prove runtime ones.

use crate::js_app::AppGraph;
use craft_anything_evidence::sha256_hex;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::BTreeMap;

/// How strong a piece of proof is, weakest first.
pub const STRENGTH: [&str; 8] = ["unit-test", "module-test", "network-test", "page-test", "built-app", "native-call", "live-run", "outside-check"];

pub fn strength_rank(s: &str) -> Option<usize> {
    STRENGTH.iter().position(|x| *x == s)
}

pub const CASE_KINDS: [&str; 5] = ["works", "refuses", "bad-input", "cancel", "shutdown"];

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default)]
pub struct Expectation {
    pub expectation_id: String,
    /// `shell`, `network`, `page`, `storage`, `system`, `native`, `install`.
    pub layer: String,
    pub target: String,
    pub title: String,
    pub must_cover: Vec<String>,
    pub min_strength: String,
    pub needs_parser_type: bool,
    /// Graph node this came from.
    pub source_node: String,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Owner {
    pub module_path: String,
    pub symbol: String,
    pub impl_sha256: Option<String>,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Case {
    pub kind: String,
    pub evidence_id: String,
    pub strength: String,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Verifier {
    pub command: String,
    pub strength: String,
    /// `pass` or `fail`.
    pub status: String,
    pub result_evidence: String,
    pub expectation_ids: Vec<String>,
    /// `deterministic`, `retried`, `flaky` (informational).
    pub nondeterminism: Option<String>,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Binding {
    pub expectation_id: String,
    pub owner: Owner,
    pub parser_type: Option<String>,
    pub cases: Vec<Case>,
    pub verifier: Option<Verifier>,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct Review {
    pub expectation_id: String,
    /// `required`, `skipped`, `waiting`.
    pub decision: String,
    pub reason: Option<String>,
}

fn expectation_key(layer: &str, target: &str) -> String {
    let h = sha256_hex(format!("{layer}\u{0}{target}").as_bytes());
    format!("ex_{}", h.get(..16).unwrap_or(&h))
}

fn expectation(layer: &str, target: String, title: String, cases: &[&str], strength: &str, parser: bool, node: String) -> Expectation {
    Expectation {
        expectation_id: expectation_key(layer, &target),
        layer: layer.into(),
        target,
        title,
        must_cover: cases.iter().map(|c| (*c).to_string()).collect(),
        min_strength: strength.into(),
        needs_parser_type: parser,
        source_node: node,
    }
}

/// Candidate expectations from an application graph.
pub fn candidate_expectations(g: &AppGraph) -> Vec<Expectation> {
    let mut v = Vec::new();
    if let Some(m) = &g.entry_points.main {
        v.push(expectation("install", format!("entry:{m}"), format!("The app starts from {m}"), &["works"], "built-app", false, format!("module:{m}")));
    }
    for c in &g.ipc {
        if !c.handlers.is_empty() || !c.main_listeners.is_empty() {
            v.push(expectation(
                "shell",
                format!("ipc:{}", c.channel),
                format!("IPC channel '{}' is handled in the main process", c.channel),
                &["works", "refuses", "bad-input"],
                "module-test",
                true,
                format!("ipc:{}", c.channel),
            ));
        }
    }
    for e in &g.exposed {
        let key = e.get("key").and_then(Value::as_str).unwrap_or("?");
        for m in e.get("members").and_then(Value::as_array).into_iter().flatten() {
            let name = m.get("name").and_then(Value::as_str).unwrap_or("?");
            v.push(expectation(
                "shell",
                format!("bridge:{key}.{name}"),
                format!("window.{key}.{name} is exposed to the page"),
                &["works", "refuses"],
                "page-test",
                false,
                format!("member:{key}.{name}"),
            ));
        }
    }
    for w in &g.windows {
        let m = w.get("module").and_then(Value::as_str).unwrap_or("?");
        let line = w.get("line").and_then(Value::as_u64).unwrap_or(0);
        v.push(expectation(
            "shell",
            format!("window:{m}@{line}"),
            "A window with the same webPreferences and preload".into(),
            &["works"],
            "built-app",
            false,
            format!("window:{m}@{line}"),
        ));
    }
    let mut seen = std::collections::BTreeSet::new();
    for e in &g.endpoints {
        if e.get("api").and_then(Value::as_str) == Some("literal") {
            continue;
        }
        let label = format!("{} {}", e.get("method").and_then(Value::as_str).unwrap_or("*"), e.get("url").and_then(Value::as_str).unwrap_or(""));
        if seen.insert(label.clone()) {
            v.push(expectation(
                "network",
                format!("endpoint:{label}"),
                format!("Request {label}"),
                &["works", "refuses", "bad-input"],
                "network-test",
                true,
                format!("endpoint:{label}"),
            ));
        }
    }
    for r in &g.routes {
        let p = r.get("path").and_then(Value::as_str).unwrap_or("");
        if seen.insert(format!("route:{p}")) {
            v.push(expectation("page", format!("route:{p}"), format!("Route {p}"), &["works"], "page-test", false, format!("route:{p}")));
        }
    }
    for (list, layer) in [(&g.storage, "storage"), (&g.effects, "system")] {
        for u in list {
            let api = u.get("api").and_then(Value::as_str).unwrap_or("");
            let interesting = layer == "storage"
                || api.starts_with("fs.write")
                || api.starts_with("fs.append")
                || api.starts_with("fs.mkdir")
                || api.starts_with("fs.rm")
                || api.starts_with("fs.unlink")
                || api.starts_with("child_process.")
                || api.starts_with("shell.");
            let target = format!("{api} {}", u.get("arg").and_then(Value::as_str).unwrap_or("")).trim().to_string();
            if interesting && seen.insert(format!("{layer}:{target}")) {
                let layer = if api.starts_with("fs.") { "storage" } else { layer };
                v.push(expectation(
                    layer,
                    format!("effect:{target}"),
                    format!("Side effect {target}"),
                    &["works", "refuses"],
                    "module-test",
                    layer == "storage",
                    format!("effect:{api}"),
                ));
            }
        }
    }
    for n in &g.native_modules {
        let name = n.get("name").and_then(Value::as_str).unwrap_or("?");
        if seen.insert(format!("native:{name}")) {
            v.push(expectation(
                "native",
                format!("native:{name}"),
                format!("Native module {name}"),
                &["works"],
                "native-call",
                false,
                format!("native:{name}"),
            ));
        }
    }
    v
}

/// Build the ledger. `evidence_ok(id)` says whether an evidence id resolves and verifies.
pub fn build_ledger(g: &AppGraph, bindings: &[Binding], reviews: &[Review], evidence_ok: &dyn Fn(&str) -> bool) -> Value {
    let expectations = candidate_expectations(g);
    let mut rows = Vec::new();
    let mut counts: BTreeMap<String, usize> = BTreeMap::new();
    let known: std::collections::BTreeSet<&str> = expectations.iter().map(|o| o.expectation_id.as_str()).collect();
    let stray: Vec<&str> = bindings.iter().map(|b| b.expectation_id.as_str()).filter(|id| !known.contains(id)).collect();
    let mut closed = Vec::new();
    for o in &expectations {
        let review = reviews.iter().rev().find(|r| r.expectation_id == o.expectation_id);
        let mine: Vec<&Binding> = bindings.iter().filter(|b| b.expectation_id == o.expectation_id).collect();
        let mut missing: Vec<String> = Vec::new();
        let need = strength_rank(&o.min_strength).unwrap_or(0);
        let status = match review.map(|r| r.decision.as_str()) {
            Some("skipped") => "skipped".to_string(),
            Some("waiting") => "waiting".to_string(),
            _ => {
                let owners: std::collections::BTreeSet<(&str, &str)> = mine.iter().map(|b| (b.owner.module_path.as_str(), b.owner.symbol.as_str())).collect();
                if mine.is_empty() {
                    missing.push("no owner in the rebuild".into());
                    "no-owner".to_string()
                } else if owners.len() > 1 {
                    missing.push(format!("{} different owners claim it", owners.len()));
                    "disproved".to_string()
                } else {
                    let b = mine.first().copied().cloned().unwrap_or_default();
                    let mut unknown = false;
                    if b.owner.module_path.trim().is_empty() || b.owner.symbol.trim().is_empty() {
                        missing.push("owner needs module_path and symbol".into());
                    }
                    if o.needs_parser_type && b.parser_type.as_deref().is_none_or(|p| p.trim().is_empty()) {
                        missing.push("parser_type is required for this layer".into());
                    }
                    let mut cases_ok = true;
                    for kind in &o.must_cover {
                        let covered = b.cases.iter().any(|c| {
                            if c.kind != *kind {
                                return false;
                            }
                            if !evidence_ok(&c.evidence_id) {
                                unknown = true;
                                return false;
                            }
                            strength_rank(&c.strength).is_some_and(|r| r >= need)
                        });
                        if !covered {
                            cases_ok = false;
                            missing.push(format!("{kind} case with {} (or stronger) evidence", o.min_strength));
                        }
                    }
                    let verifier_state = match &b.verifier {
                        None => {
                            missing.push("no verifier".into());
                            "none"
                        }
                        Some(v) if v.status == "fail" => "failed",
                        Some(v) => {
                            let mut ok = v.status == "pass";
                            if !ok {
                                missing.push(format!("verifier status is {:?}", v.status));
                            }
                            if strength_rank(&v.strength).is_none_or(|r| r < need) {
                                ok = false;
                                missing.push(format!("check strength {:?} is below {}", v.strength, o.min_strength));
                            }
                            if !v.expectation_ids.contains(&o.expectation_id) {
                                ok = false;
                                missing.push("verifier does not list this expectation".into());
                            }
                            if !evidence_ok(&v.result_evidence) {
                                ok = false;
                                unknown = true;
                                missing.push("verifier result evidence is missing or tampered".into());
                            }
                            if ok { "passed" } else { "too-weak" }
                        }
                    };
                    if verifier_state == "failed" {
                        missing.push("verifier failed".into());
                        "disproved".to_string()
                    } else if missing.is_empty() {
                        closed.push((o.expectation_id.clone(), b.verifier.as_ref().map(|v| v.result_evidence.clone()).unwrap_or_default()));
                        "proven".to_string()
                    } else if unknown {
                        "unclear".to_string()
                    } else if cases_ok && !b.owner.symbol.is_empty() {
                        "built".to_string()
                    } else {
                        "described".to_string()
                    }
                }
            }
        };
        *counts.entry(status.clone()).or_default() += 1;
        rows.push(json!({
            "expectation_id": o.expectation_id, "layer": o.layer, "target": o.target, "title": o.title,
            "must_cover": o.must_cover, "min_strength": o.min_strength, "needs_parser_type": o.needs_parser_type,
            "source_node": o.source_node, "status": status, "missing": missing, "review": review.map(|r| json!({"decision": r.decision, "reason": r.reason})),
        }));
    }
    let c = |k: &str| counts.get(k).copied().unwrap_or(0);
    let ledger_status = if c("disproved") > 0 {
        "failing"
    } else if c("unclear") > 0 {
        "unclear"
    } else if c("proven") + c("skipped") == expectations.len() {
        "ready"
    } else {
        "open"
    };
    let statuses: Vec<(&str, &str)> = rows.iter().filter_map(|r| Some((r.get("expectation_id")?.as_str()?, r.get("status")?.as_str()?))).collect();
    closed.sort();
    json!({
        "ledger_id": format!("lg_{}", sha256_hex(craft_anything_evidence::canonical_json(&json!({"graph": g.graph_id, "statuses": statuses})).as_bytes())),
        "closed_hash": sha256_hex(craft_anything_evidence::canonical_json(&json!(closed)).as_bytes()),
        "graph_id": g.graph_id,
        "status": ledger_status,
        "counts": counts,
        "expectations": rows,
        "stray_bindings": stray,
        "strength_ladder": STRENGTH,
    })
}

/// Coverage figures for a ledger produced by [`build_ledger`].
pub fn evaluate_coverage(ledger: &Value) -> Value {
    let rows = ledger.get("expectations").and_then(Value::as_array).cloned().unwrap_or_default();
    let mut by_layer: BTreeMap<String, BTreeMap<String, usize>> = BTreeMap::new();
    let mut gaps = Vec::new();
    for r in &rows {
        let layer = r.get("layer").and_then(Value::as_str).unwrap_or("?").to_string();
        let status = r.get("status").and_then(Value::as_str).unwrap_or("?").to_string();
        *by_layer.entry(layer.clone()).or_default().entry(status.clone()).or_default() += 1;
        if !matches!(status.as_str(), "proven" | "skipped") && gaps.len() < 500 {
            gaps.push(
                json!({"expectation_id": r.get("expectation_id"), "layer": layer, "target": r.get("target"), "status": status, "missing": r.get("missing")}),
            );
        }
    }
    let in_scope = rows.iter().filter(|r| r.get("status").and_then(Value::as_str) != Some("skipped")).count();
    let proven = rows.iter().filter(|r| r.get("status").and_then(Value::as_str) == Some("proven")).count();
    let pct = if in_scope == 0 { 100.0 } else { (proven as f64 * 1000.0 / in_scope as f64).round() / 10.0 };
    json!({
        "ledger_id": ledger.get("ledger_id"),
        "ledger_status": ledger.get("status"),
        "expectations": rows.len(),
        "in_scope": in_scope,
        "proven": proven,
        "proven_percent": pct,
        "by_layer": by_layer,
        "gaps": gaps,
        "ready": ledger.get("status").and_then(Value::as_str) == Some("ready"),
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::js_app::tests_support::notes_graph;

    #[test]
    fn ledger_proves_only_with_strong_enough_evidence() {
        let g = notes_graph();
        let obs = candidate_expectations(&g);
        let ipc = obs.iter().find(|o| o.target == "ipc:export-notes").unwrap().clone();
        assert!(obs.iter().any(|o| o.target == "bridge:api.exportNotes"));
        assert!(obs.iter().any(|o| o.layer == "network"));
        let ok = |id: &str| id.starts_with("ev_good");
        let case = |k: &str, a: &str| Case { kind: k.into(), evidence_id: "ev_good1".into(), strength: a.into() };
        let binding = |auth: &str, status: &str| Binding {
            expectation_id: ipc.expectation_id.clone(),
            owner: Owner { module_path: "src/ipc.rs".into(), symbol: "export_notes".into(), impl_sha256: None },
            parser_type: Some("NotesPayload".into()),
            cases: vec![case("works", "module-test"), case("refuses", "module-test"), case("bad-input", "module-test")],
            verifier: Some(Verifier {
                command: "cargo test".into(),
                strength: auth.into(),
                status: status.into(),
                result_evidence: "ev_good2".into(),
                expectation_ids: vec![ipc.expectation_id.clone()],
                nondeterminism: None,
            }),
        };
        let status_of = |l: &Value| l["expectations"].as_array().unwrap().iter().find(|r| r["target"] == "ipc:export-notes").unwrap()["status"].clone();
        let l = build_ledger(&g, &[binding("module-test", "pass")], &[], &ok);
        assert_eq!(status_of(&l), "proven");
        assert_eq!(l["status"], "open");
        let weak = build_ledger(&g, &[binding("unit-test", "pass")], &[], &ok);
        assert_eq!(status_of(&weak), "built");
        let failed = build_ledger(&g, &[binding("module-test", "fail")], &[], &ok);
        assert_eq!(failed["status"], "failing");
        let missing_ev = build_ledger(&g, &[binding("module-test", "pass")], &[], &|_: &str| false);
        assert_eq!(status_of(&missing_ev), "unclear");
        let all_out: Vec<Review> = obs.iter().map(|o| Review { expectation_id: o.expectation_id.clone(), decision: "skipped".into(), reason: None }).collect();
        let ready = build_ledger(&g, &[], &all_out, &ok);
        assert_eq!(ready["status"], "ready");
        let cov = evaluate_coverage(&l);
        assert_eq!(cov["proven"], 1);
        assert!(cov["gaps"].as_array().unwrap().len() >= 3);
    }
}
