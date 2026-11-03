//! Comparison and verification session tools: pure, in-process, no external engine.
//!
//! These compose evidence that other tools already produced (passed inline, as a
//! `{"kind":"saved","evidence_id":…}` reference, or as a bare `ev_…` id) and turn it
//! into higher-level findings: how two functions differ, what changed across two evidence bundles,
//! a call path between two addresses, a correlation of static and runtime comparisons, and a check
//! that a reconstruction goal is backed by intact evidence. `native_address_show` reports the
//! name/function/comment/bookmark facets of one address in the active native target.

use super::artifact_tools::resolve_evidence_input;
use super::native_common::{name_of, native};
use crate::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use craft_anything_evidence::{Confidence, Coverage, Environment, EvidenceBuilder, Location, Subject, ToolError};
use schemars::JsonSchema;
use serde::Deserialize;
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet, VecDeque};

pub fn specs() -> Vec<ToolSpec> {
    use Toolset::{Application, Native};
    vec![
        ToolSpec {
            id: "native_address_show",
            title: "What's at this address",
            summary: "The name, containing function, comment, inline comment and bookmarks at one address in the active target. Each facet is a value or a clear 'unavailable' with a reason.",
            beginner: "See everything we know about one spot in the program.",
            toolset: Native,
            effects: Effects::EVIDENCE,
            requires: Requires::Target,
            input_schema: schema_of::<AddressParams>,
            run: native_address_show,
        },
        ToolSpec {
            id: "app_function_versions_compare",
            title: "Compare two functions",
            summary: "Compare two native_function_study evidence records: name, size, blocks, instructions, callee set and pseudo-code. Reports what changed.",
            beginner: "See how one function differs between two versions.",
            toolset: Application,
            effects: Effects::EVIDENCE,
            requires: Requires::Nothing,
            input_schema: schema_of::<PairParams>,
            run: app_function_versions_compare,
        },
        ToolSpec {
            id: "core_evidence_exports_compare",
            title: "Compare two evidence bundles",
            summary: "Compare two exported evidence bundles (core_evidence_export files) and report which records were added, removed or changed, matched by operation and subject. Every record is checked against its own id, so one edited after export is reported, never counted as unchanged.",
            beginner: "See what two saved sets of findings have in common and where they differ.",
            toolset: Application,
            effects: Effects::MUTATES_SESSION,
            requires: Requires::Nothing,
            input_schema: schema_of::<BundlesParams>,
            run: core_evidence_exports_compare,
        },
        ToolSpec {
            id: "app_changes_summarize",
            title: "Summarise what changed",
            summary: "Combine several comparison evidence records (app_function_versions_compare, core_archives_compare, runtime_captures_compare) into one summary of what changed and what stayed the same.",
            beginner: "Pull all your comparisons together into one 'what changed' answer.",
            toolset: Application,
            effects: Effects::EVIDENCE,
            requires: Requires::Nothing,
            input_schema: schema_of::<ComparisonsParams>,
            run: app_changes_summarize,
        },
        ToolSpec {
            id: "app_call_path_find",
            title: "Find a call path",
            summary: "Find a path of calls from a start address to a goal address over a call graph assembled from native_function_study evidence records.",
            beginner: "Find how one function reaches another through the calls between them.",
            toolset: Application,
            effects: Effects::EVIDENCE,
            requires: Requires::Nothing,
            input_schema: schema_of::<CallPathParams>,
            run: app_call_path_find,
        },
        ToolSpec {
            id: "app_runtime_correlate",
            title: "Line up code and behaviour",
            summary: "Correlate static comparisons (app_function_versions_compare/core_archives_compare) with runtime comparisons (runtime_captures_compare) through caller-supplied mappings, and report where they agree or disagree.",
            beginner: "Check whether a change you see in the code matches a change you see when it runs.",
            toolset: Application,
            effects: Effects::EVIDENCE,
            requires: Requires::Nothing,
            input_schema: schema_of::<CorrelateParams>,
            run: app_runtime_correlate,
        },
        ToolSpec {
            id: "app_rebuild_claim_check",
            title: "Check a rebuild claim",
            summary: "Check a reconstruction specification: every expectation must cite evidence that exists and is intact. Reports which expectations are satisfied.",
            beginner: "Check that a claim about rebuilding something is actually backed by proof.",
            toolset: Application,
            effects: Effects::EVIDENCE,
            requires: Requires::Nothing,
            input_schema: schema_of::<VerifyParams>,
            run: app_rebuild_claim_check,
        },
    ]
}

// --------------------------------------------------------------------------------------------
// native_address_show

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct AddressParams {
    /// Address as 0x-hex or decimal.
    pub address: String,
    /// Target id or name; the active target when omitted.
    #[serde(default)]
    pub document: Option<String>,
}

fn facet_value(v: Value) -> Value {
    json!({"state": "available", "value": v})
}

fn facet_unavailable(reason: &str, remediation: &str) -> Value {
    json!({"state": "unavailable", "reason": reason, "remediation": remediation})
}

fn native_address_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: AddressParams = parse_params(params)?;
    super::native_common::select_document(ctx, &p.document)?;
    let addr = super::parse_address(&p.address)?;
    let st = native(ctx)?;
    let t = ctx.session.active()?;

    let name = match name_of(t, &st.prog, addr) {
        Some(n) => facet_value(json!(n)),
        None => facet_unavailable("no name at this address", "Give it one with native_name_set."),
    };
    let function = match st.prog.function_containing(addr) {
        Some(f) => facet_value(json!({"name": name_of(t, &st.prog, f.entry), "entry": format!("{:#x}", f.entry), "offset": addr.saturating_sub(f.entry)})),
        None => facet_unavailable(
            if st.img.is_exec(addr) { "not inside any discovered function" } else { "not in executable code" },
            "Run native_functions_list or native_functions_search to find nearby functions.",
        ),
    };
    let comment = match t.annotations.comments.get(&addr) {
        Some(c) => facet_value(json!(c)),
        None => facet_unavailable("no comment here", "Add one with native_comment_write."),
    };
    let inline_comment = match t.annotations.inline_comments.get(&addr) {
        Some(c) => facet_value(json!(c)),
        None => facet_unavailable("no inline comment here", "Add one with native_inline_comment_write."),
    };
    let bookmark = match t.annotations.bookmarks.get(&addr) {
        Some(b) => facet_value(json!(b)),
        None => facet_unavailable("not bookmarked", "Bookmark it with native_bookmark_add."),
    };

    let facets = json!({
        "address": format!("{addr:#x}"),
        "name": name,
        "function": function,
        "comment": comment,
        "inline_comment": inline_comment,
        "bookmarks": bookmark,
    });
    let name_label = st.prog.name_at(addr).unwrap_or_else(|| format!("{addr:#x}"));
    let e = super::evidence_for_active(ctx.session, "native_address_show")?
        .params(json!({"address": format!("{addr:#x}")}))
        .result(facets)
        .summary(format!("Context for {name_label}."))
        .confidence(Confidence::Observed)
        .location(Location::address(addr))
        .build()?;
    // Move the cursor so native_cursor_show agrees with where we looked.
    ctx.session.active_mut()?.cursor.address = Some(addr);
    Ok(ToolOutput::evidence(e))
}

// --------------------------------------------------------------------------------------------
// app_function_versions_compare

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct PairParams {
    /// Left (older) native_function_study evidence.
    pub left: Value,
    /// Right (newer) native_function_study evidence.
    pub right: Value,
}

fn app_function_versions_compare(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: PairParams = parse_params(params)?;
    let l = resolve_evidence_input(ctx, &p.left, &["native_function_study"])?;
    let r = resolve_evidence_input(ctx, &p.right, &["native_function_study"])?;

    let lf = FnFacts::from_result(&l.result);
    let rf = FnFacts::from_result(&r.result);

    let mut changes = Vec::new();
    if lf.name != rf.name {
        changes.push(field("name", json!(lf.name), json!(rf.name)));
    }
    if lf.size != rf.size {
        changes.push(field("size", json!(lf.size), json!(rf.size)));
    }
    if lf.blocks != rf.blocks {
        changes.push(field("basic_blocks", json!(lf.blocks), json!(rf.blocks)));
    }
    if lf.instructions != rf.instructions {
        changes.push(field("instructions", json!(lf.instructions), json!(rf.instructions)));
    }
    let added: Vec<&String> = rf.callees.difference(&lf.callees).collect();
    let removed: Vec<&String> = lf.callees.difference(&rf.callees).collect();
    if !added.is_empty() || !removed.is_empty() {
        changes.push(json!({"field": "callees", "added": added, "removed": removed}));
    }
    let pseudo_changed = lf.pseudocode != rf.pseudocode;
    if pseudo_changed {
        changes.push(json!({"field": "pseudocode", "changed": true}));
    }

    let status = if changes.is_empty() { "unchanged" } else { "changed" };
    let summary = if changes.is_empty() {
        format!("{} is unchanged between the two versions.", lf.name)
    } else {
        format!("{} → {}: {} field(s) changed.", lf.name, rf.name, changes.len())
    };

    let b = EvidenceBuilder::new(
        "app_function_versions_compare",
        Subject { kind: "function-pair".into(), sha256: None, name: Some(format!("{} vs {}", lf.name, rf.name)) },
        Environment::builtin(ctx.session.clean_room()),
    )
    .params(json!({"left": l.id, "right": r.id}))
    .result(json!({"status": status, "changes": changes, "left": lf.summary(), "right": rf.summary()}))
    .summary(summary)
    .confidence(Confidence::Derived)
    .link(l.id.clone())
    .link(r.id.clone());
    Ok(ToolOutput::evidence(b.build()?))
}

fn field(name: &str, left: Value, right: Value) -> Value {
    json!({"field": name, "left": left, "right": right})
}

struct FnFacts {
    name: String,
    size: u64,
    blocks: usize,
    instructions: u64,
    callees: BTreeSet<String>,
    pseudocode: String,
}

impl FnFacts {
    fn from_result(result: &Value) -> Self {
        let proc = result.get("function");
        let name = proc.and_then(|p| p.get("name")).and_then(Value::as_str).map(String::from).unwrap_or_else(|| "?".into());
        let size = proc.and_then(|p| p.get("size")).and_then(Value::as_u64).unwrap_or(0);
        let blocks = result.get("basic_blocks").and_then(Value::as_array).map(Vec::len).unwrap_or(0);
        let instructions = proc.and_then(|p| p.get("instructions")).and_then(Value::as_u64).unwrap_or(0);
        let callees = result
            .get("callees")
            .and_then(Value::as_array)
            .map(|a| {
                a.iter()
                    .filter_map(|c| {
                        c.get("name").and_then(Value::as_str).map(String::from).or_else(|| c.get("target").and_then(Value::as_str).map(String::from))
                    })
                    .collect()
            })
            .unwrap_or_default();
        let pseudocode = result.get("pseudocode").and_then(Value::as_str).map(String::from).unwrap_or_default();
        FnFacts { name, size, blocks, instructions, callees, pseudocode }
    }

    fn summary(&self) -> Value {
        json!({"name": self.name, "size": self.size, "basic_blocks": self.blocks, "instructions": self.instructions, "callee_count": self.callees.len()})
    }
}

// --------------------------------------------------------------------------------------------
// core_evidence_exports_compare

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct BundlesParams {
    /// Absolute path to the first evidence bundle.
    pub older_bundle: String,
    /// Absolute path to the second evidence bundle.
    pub newer_bundle: String,
    /// Include the matched record-id pairs in the result.
    #[serde(default)]
    pub keep_pairs: bool,
}

fn core_evidence_exports_compare(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: BundlesParams = parse_params(params)?;
    let left = load_bundle(&p.older_bundle)?;
    let right = load_bundle(&p.newer_bundle)?;

    // Match records by (operation, subject sha256 + name). A matched pair is "changed" when its
    // evidence id differs (the id is the content hash), "unchanged" otherwise.
    let lmap = bundle_index(&left);
    let rmap = bundle_index(&right);
    let integrity_of = |m: &Value| m.get("integrity").and_then(Value::as_str).unwrap_or("unverifiable").to_string();
    // Records that fail their own id, or can't be read as evidence, on either side.
    let mut failing = Vec::new();
    for (side, recs) in [("left", &left), ("right", &right)] {
        for (key, meta) in recs.iter() {
            let state = integrity_of(meta);
            if state != "verified" {
                failing.push(json!({"side": side, "key": key, "evidence_id": meta.get("id"), "integrity": state}));
            }
        }
    }
    let duplicates = |recs: &[Rec]| -> Vec<String> {
        let mut seen = std::collections::BTreeSet::new();
        recs.iter().filter(|(k, _)| !seen.insert(k.clone())).map(|(k, _)| k.clone()).collect()
    };
    let duplicate_keys = json!({"left": duplicates(&left), "right": duplicates(&right)});
    let mut added = Vec::new();
    let mut removed = Vec::new();
    let mut changed = Vec::new();
    let mut unchanged = 0usize;
    let mut pairs = Vec::new();
    for (key, (lid, lmeta)) in &lmap {
        match rmap.get(key) {
            None => removed.push(json!({"key": key, "evidence_id": lid})),
            Some((rid, rmeta)) => {
                let (li, ri) = (integrity_of(lmeta), integrity_of(rmeta));
                if li == "tampered" || ri == "tampered" {
                    // Equal ids prove nothing when a record doesn't match its own id.
                    changed.push(json!({"key": key, "left": lid, "right": rid, "reason": "integrity", "left_integrity": li, "right_integrity": ri}));
                } else if lid == rid {
                    unchanged += 1;
                } else {
                    changed.push(json!({"key": key, "left": lid, "right": rid}));
                }
                if p.keep_pairs {
                    pairs.push(json!({"key": key, "left": lid, "right": rid}));
                }
            }
        }
    }
    for (key, (rid, _)) in &rmap {
        if !lmap.contains_key(key) {
            added.push(json!({"key": key, "evidence_id": rid}));
        }
    }

    let tampered = failing.iter().filter(|f| f["integrity"] == "tampered").count();
    let summary = format!(
        "{} vs {} records: {} added, {} removed, {} changed, {} unchanged.{}",
        left.len(),
        right.len(),
        added.len(),
        removed.len(),
        changed.len(),
        unchanged,
        if tampered > 0 { format!(" {tampered} record(s) don't match their own id: they were edited after they were recorded.") } else { String::new() }
    );
    let mut result = json!({
        "counts": {"left": left.len(), "right": right.len(), "added": added.len(), "removed": removed.len(), "changed": changed.len(), "unchanged": unchanged, "tampered": tampered},
        "added": added, "removed": removed, "changed": changed,
        "integrity": {"failing": failing, "duplicate_keys": duplicate_keys},
    });
    if p.keep_pairs
        && let Value::Object(m) = &mut result
    {
        m.insert("keep_pairs".into(), json!(pairs));
    }

    let b = EvidenceBuilder::new(
        "core_evidence_exports_compare",
        Subject { kind: "bundle-pair".into(), sha256: None, name: Some("two evidence bundles".into()) },
        Environment::builtin(ctx.session.clean_room()),
    )
    .params(json!({"older_bundle": p.older_bundle, "newer_bundle": p.newer_bundle}))
    .result(result)
    .summary(summary)
    .confidence(Confidence::Derived);
    Ok(ToolOutput::evidence(b.build()?))
}

/// A record's (operation, subject) key and its evidence id.
type Rec = (String, Value);

fn load_bundle(path: &str) -> Result<Vec<Rec>, ToolError> {
    let pb = super::artifact_tools::abs_path(path, "bundle path")?;
    let meta = std::fs::metadata(&pb).map_err(|e| ToolError::io(pb.display(), e))?;
    if meta.len() > 512 * 1024 * 1024 {
        return Err(ToolError::new(craft_anything_evidence::ErrorCode::OverLimit, "bundle is too large"));
    }
    let bytes = std::fs::read(&pb).map_err(|e| ToolError::io(pb.display(), e))?;
    let v: Value = serde_json::from_slice(&bytes).map_err(|e| ToolError::invalid(format!("not a bundle: {e}")))?;
    if v.get("format").and_then(Value::as_str) != Some(super::session_tools::BUNDLE_FORMAT) {
        return Err(ToolError::invalid(format!("{path} is not a Craft Anything evidence bundle")));
    }
    let mut out = Vec::new();
    for r in v.get("records").and_then(Value::as_array).into_iter().flatten() {
        let op = r.get("operation").and_then(Value::as_str).unwrap_or("").to_string();
        let id = r.get("id").cloned().unwrap_or(Value::Null);
        let subject = r.get("subject").cloned().unwrap_or(Value::Null);
        // The id is the content hash: a record whose content no longer matches it was edited.
        let integrity = match serde_json::from_value::<craft_anything_evidence::Evidence>(r.clone()) {
            Ok(ev) if ev.verify() => "verified",
            Ok(_) => "tampered",
            Err(_) => "unverifiable",
        };
        out.push((format!("{op}|{}", subject_key(&subject)), json!({"id": id, "subject": subject, "integrity": integrity})));
    }
    Ok(out)
}

fn subject_key(subject: &Value) -> String {
    let sha = subject.get("sha256").and_then(Value::as_str).unwrap_or("");
    let name = subject.get("name").and_then(Value::as_str).unwrap_or("");
    let kind = subject.get("kind").and_then(Value::as_str).unwrap_or("");
    format!("{kind}:{sha}:{name}")
}

fn bundle_index(recs: &[Rec]) -> BTreeMap<String, (String, Value)> {
    let mut m = BTreeMap::new();
    for (key, meta) in recs {
        let id = meta.get("id").and_then(Value::as_str).unwrap_or("").to_string();
        m.insert(key.clone(), (id, meta.clone()));
    }
    m
}

// --------------------------------------------------------------------------------------------
// app_changes_summarize

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ComparisonsParams {
    /// One or more comparison evidence records (app_function_versions_compare / core_archives_compare /
    /// runtime_captures_compare / core_evidence_exports_compare), inline or by reference.
    pub comparisons: Vec<Value>,
}

const COMPARISON_OPS: &[&str] = &["app_function_versions_compare", "core_archives_compare", "runtime_captures_compare", "core_evidence_exports_compare"];

fn app_changes_summarize(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ComparisonsParams = parse_params(params)?;
    if p.comparisons.is_empty() {
        return Err(ToolError::invalid("comparisons must have at least one record"));
    }
    let mut items = Vec::new();
    let mut changed = 0usize;
    let mut links = Vec::new();
    for c in &p.comparisons {
        let ev = resolve_evidence_input(ctx, c, COMPARISON_OPS)?;
        let is_changed = comparison_is_changed(&ev.result);
        if is_changed {
            changed += 1;
        }
        links.push(ev.id.clone());
        items.push(json!({"evidence_id": ev.id, "operation": ev.operation, "changed": is_changed, "summary": ev.summary}));
    }
    let total = items.len();
    let summary = format!("{changed} of {total} comparisons found changes.");
    let b = EvidenceBuilder::new(
        "app_changes_summarize",
        Subject { kind: "comparison-set".into(), sha256: None, name: Some(format!("{total} comparisons")) },
        Environment::builtin(ctx.session.clean_room()),
    )
    .params(json!({"comparison_count": total}))
    .result(json!({"total": total, "changed": changed, "unchanged": total - changed, "items": items}))
    .summary(summary)
    .confidence(Confidence::Derived)
    .coverage(Coverage::complete(total as u64));
    let mut b = b;
    for id in links {
        b = b.link(id);
    }
    Ok(ToolOutput::evidence(b.build()?))
}

/// Read the change status out of any of our comparison records.
fn comparison_is_changed(result: &Value) -> bool {
    if let Some(s) = result.get("status").and_then(Value::as_str) {
        return s != "unchanged";
    }
    if let Some(s) = result.get("overall").and_then(Value::as_str) {
        return s != "unchanged";
    }
    // A comparison that says whether the two are identical decides; a moved file counts (#286).
    if let Some(same) = result.get("identical").and_then(Value::as_bool) {
        return !same;
    }
    if let Some(counts) = result.get("counts") {
        let n = |k: &str| counts.get(k).and_then(Value::as_u64).unwrap_or(0);
        return n("added") + n("removed") + n("changed") + n("moved") > 0;
    }
    false
}

// --------------------------------------------------------------------------------------------
// app_call_path_find

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct CallPathParams {
    /// native_function_study evidence records that describe the functions and their callees.
    pub functions: Vec<Value>,
    /// Start address (0x-hex or decimal).
    pub start: String,
    /// Goal address (0x-hex or decimal).
    pub goal: String,
    /// Longest path to search (default 64).
    #[serde(default = "d_depth")]
    pub max_depth: usize,
}

fn d_depth() -> usize {
    64
}

fn app_call_path_find(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: CallPathParams = parse_params(params)?;
    if p.functions.is_empty() {
        return Err(ToolError::invalid("functions must have at least one native_function_study record"));
    }
    let start = super::parse_address(&p.start)?;
    let goal = super::parse_address(&p.goal)?;

    // Build adjacency entry -> {callee entries}, and a name table.
    let mut adj: BTreeMap<u64, BTreeSet<u64>> = BTreeMap::new();
    let mut names: BTreeMap<u64, String> = BTreeMap::new();
    let mut links = Vec::new();
    for f in &p.functions {
        let ev = resolve_evidence_input(ctx, f, &["native_function_study"])?;
        links.push(ev.id.clone());
        let proc = ev.result.get("function");
        let entry = proc.and_then(|p| p.get("entry")).and_then(Value::as_str).and_then(|h| super::parse_address(h).ok());
        let Some(entry) = entry else { continue };
        if let Some(n) = proc.and_then(|p| p.get("name")).and_then(Value::as_str) {
            names.insert(entry, n.to_string());
        }
        let set = adj.entry(entry).or_default();
        for c in ev.result.get("callees").and_then(Value::as_array).into_iter().flatten() {
            if let Some(t) = c.get("target").and_then(Value::as_str).and_then(|h| super::parse_address(h).ok()) {
                set.insert(t);
                if let Some(n) = c.get("name").and_then(Value::as_str) {
                    names.entry(t).or_insert_with(|| n.to_string());
                }
            }
        }
    }

    // Breadth-first search for a shortest path.
    let path = bfs(&adj, start, goal, p.max_depth.clamp(1, 4096));
    let found = path.is_some();
    let path_json: Vec<Value> = path.unwrap_or_default().into_iter().map(|a| json!({"address": format!("{a:#x}"), "name": names.get(&a)})).collect();

    let summary = if found {
        format!("Found a call path of {} functions from {start:#x} to {goal:#x}.", path_json.len())
    } else {
        format!("No call path from {start:#x} to {goal:#x} within the given functions (depth {}).", p.max_depth)
    };
    let b = EvidenceBuilder::new(
        "app_call_path_find",
        Subject { kind: "call-path".into(), sha256: None, name: Some(format!("{start:#x} → {goal:#x}")) },
        Environment::builtin(ctx.session.clean_room()),
    )
    .params(json!({"start": format!("{start:#x}"), "goal": format!("{goal:#x}"), "function_count": p.functions.len()}))
    .result(json!({"found": found, "start": format!("{start:#x}"), "goal": format!("{goal:#x}"), "path": path_json, "nodes": adj.len()}))
    .summary(summary)
    .confidence(Confidence::Derived)
    .location(Location::address(start).with_label("start"))
    .location(Location::address(goal).with_label("goal"));
    let mut b = b;
    for id in links {
        b = b.link(id);
    }
    Ok(ToolOutput::evidence(b.build()?))
}

fn bfs(adj: &BTreeMap<u64, BTreeSet<u64>>, start: u64, goal: u64, max_depth: usize) -> Option<Vec<u64>> {
    if start == goal {
        return Some(vec![start]);
    }
    let mut prev: BTreeMap<u64, u64> = BTreeMap::new();
    let mut seen: BTreeSet<u64> = BTreeSet::new();
    let mut queue: VecDeque<(u64, usize)> = VecDeque::new();
    seen.insert(start);
    queue.push_back((start, 0));
    while let Some((cur, depth)) = queue.pop_front() {
        if depth >= max_depth {
            continue;
        }
        for &next in adj.get(&cur).into_iter().flatten() {
            if !seen.insert(next) {
                continue;
            }
            prev.insert(next, cur);
            if next == goal {
                // Reconstruct.
                let mut path = vec![goal];
                let mut n = goal;
                while let Some(&pr) = prev.get(&n) {
                    path.push(pr);
                    n = pr;
                    if n == start {
                        break;
                    }
                }
                path.reverse();
                return Some(path);
            }
            queue.push_back((next, depth + 1));
        }
    }
    None
}

// --------------------------------------------------------------------------------------------
// app_runtime_correlate

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct CorrelateParams {
    /// Static comparison evidence (app_function_versions_compare / core_archives_compare).
    #[serde(default)]
    pub static_checks: Vec<Value>,
    /// Runtime comparison evidence (runtime_captures_compare).
    #[serde(default)]
    pub runtime_checks: Vec<Value>,
    /// Each mapping links a static record to a runtime record by their evidence ids.
    pub mappings: Vec<Mapping>,
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Mapping {
    pub static_evidence_id: String,
    pub runtime_evidence_id: String,
    #[serde(default)]
    pub note: Option<String>,
}

fn app_runtime_correlate(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: CorrelateParams = parse_params(params)?;
    if p.mappings.is_empty() {
        return Err(ToolError::invalid("mappings must have at least one entry"));
    }
    // Index the supplied comparisons by id.
    let mut by_id: BTreeMap<String, (String, bool)> = BTreeMap::new();
    let mut links = Vec::new();
    for c in p.static_checks.iter().chain(p.runtime_checks.iter()) {
        let ev = resolve_evidence_input(ctx, c, COMPARISON_OPS)?;
        by_id.insert(ev.id.clone(), (ev.operation.clone(), comparison_is_changed(&ev.result)));
        links.push(ev.id);
    }

    let mut rows = Vec::new();
    let mut agree = 0usize;
    let mut disagree = 0usize;
    let mut incomplete = 0usize;
    for m in &p.mappings {
        let s = by_id.get(&m.static_evidence_id);
        let r = by_id.get(&m.runtime_evidence_id);
        let (verdict, s_changed, r_changed) = match (s, r) {
            (Some((_, sc)), Some((_, rc))) => {
                if sc == rc {
                    agree += 1;
                    ("agree", Some(*sc), Some(*rc))
                } else {
                    disagree += 1;
                    ("disagree", Some(*sc), Some(*rc))
                }
            }
            _ => {
                incomplete += 1;
                ("incomplete", s.map(|x| x.1), r.map(|x| x.1))
            }
        };
        rows.push(json!({
            "static_evidence_id": m.static_evidence_id,
            "runtime_evidence_id": m.runtime_evidence_id,
            "note": m.note,
            "verdict": verdict,
            "static_changed": s_changed,
            "runtime_changed": r_changed,
        }));
    }

    let summary = format!("{} mappings: {agree} agree, {disagree} disagree, {incomplete} incomplete.", p.mappings.len());
    let b = EvidenceBuilder::new(
        "app_runtime_correlate",
        Subject { kind: "correlation".into(), sha256: None, name: Some(format!("{} mappings", p.mappings.len())) },
        Environment::builtin(ctx.session.clean_room()),
    )
    .params(json!({"mapping_count": p.mappings.len()}))
    .result(json!({"agree": agree, "disagree": disagree, "incomplete": incomplete, "correlations": rows}))
    .summary(summary)
    .confidence(Confidence::Derived);
    let mut b = b;
    for id in links {
        b = b.link(id);
    }
    Ok(ToolOutput::evidence(b.build()?))
}

// --------------------------------------------------------------------------------------------
// app_rebuild_claim_check

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct VerifyParams {
    pub specification: Specification,
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Specification {
    /// What is claimed to have been reconstructed.
    pub goal: String,
    /// Each expectation must be backed by evidence that exists and is intact.
    pub expectations: Vec<Expectation>,
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct Expectation {
    pub description: String,
    #[serde(default)]
    pub evidence_ids: Vec<String>,
}

fn app_rebuild_claim_check(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: VerifyParams = parse_params(params)?;
    if p.specification.goal.trim().is_empty() {
        return Err(ToolError::invalid("goal is empty"));
    }
    if p.specification.expectations.is_empty() {
        return Err(ToolError::invalid("a specification needs at least one expectation"));
    }
    let mut rows = Vec::new();
    let mut satisfied = 0usize;
    let mut links = Vec::new();
    for ob in &p.specification.expectations {
        let mut problems = Vec::new();
        if ob.evidence_ids.is_empty() {
            problems.push("cites no evidence".to_string());
        }
        for id in &ob.evidence_ids {
            match ctx.session.resolve_evidence(id) {
                Ok(e) if e.verify() => links.push(id.clone()),
                Ok(_) => problems.push(format!("{id} failed its integrity check")),
                Err(_) => problems.push(format!("{id} not found")),
            }
        }
        let ok = problems.is_empty();
        if ok {
            satisfied += 1;
        }
        rows.push(json!({"description": ob.description, "evidence_ids": ob.evidence_ids, "satisfied": ok, "problems": problems}));
    }
    let total = p.specification.expectations.len();
    let verified = satisfied == total;
    let summary = format!("\"{}\": {satisfied} of {total} expectations satisfied{}.", p.specification.goal, if verified { ", verified" } else { "" });
    let b = EvidenceBuilder::new(
        "app_rebuild_claim_check",
        Subject { kind: "reconstruction".into(), sha256: None, name: Some(p.specification.goal.clone()) },
        Environment::builtin(ctx.session.clean_room()),
    )
    .params(json!({"goal": p.specification.goal, "expectation_count": total}))
    .result(json!({"verified": verified, "satisfied": satisfied, "total": total, "expectations": rows}))
    .summary(summary)
    .confidence(Confidence::Derived)
    .coverage(Coverage::complete(total as u64));
    let mut b = b;
    for id in links {
        b = b.link(id);
    }
    Ok(ToolOutput::evidence(b.build()?))
}

#[cfg(test)]
mod tests {
    use crate::tools::native_common::test_support::{call, engine_with};
    use crate::{CallOptions, Caller, Engine};
    use craft_anything_testkit as tk;
    use serde_json::{Value, json};

    /// #286: an archive comparison where a file only moved was summarised as unchanged.
    #[test]
    fn a_moved_file_is_a_change() {
        let moved = json!({"identical": false, "counts": {"added": 0, "removed": 0, "changed": 0, "moved": 1, "unchanged": 0}});
        assert!(super::comparison_is_changed(&moved));
        assert!(super::comparison_is_changed(&json!({"counts": {"moved": 1}})));
        assert!(!super::comparison_is_changed(&json!({"identical": true, "counts": {"unchanged": 3}})));
    }

    fn call_val(e: &Engine, id: &str, p: Value) -> Result<Value, craft_anything_evidence::ToolError> {
        e.call(id, p, CallOptions::new(Caller::Cli)).map(|o| o.to_json())
    }

    fn elf() -> Vec<u8> {
        tk::elf64(tk::ElfArch::X86_64, true).0
    }

    #[test]
    fn address_context_facets() {
        let e = engine_with("prog.elf", &elf());
        let d = call(&e, "native_function_study", json!({"function": "main"}));
        let addr = d["result"]["function"]["entry"].as_str().unwrap().to_string();
        let _ = call_val(&e, "native_comment_write", json!({"address": addr, "comment": "the start"}));
        let ctx = call_val(&e, "native_address_show", json!({"address": addr})).unwrap();
        assert!(ctx["result"]["address"].as_str().is_some());
        assert!(ctx["result"]["name"]["state"].is_string());
        assert_eq!(ctx["result"]["function"]["state"], "available");
        assert_eq!(ctx["result"]["comment"]["state"], "available");
    }

    #[test]
    fn compare_bundles_catches_a_record_edited_after_export() {
        let e = engine_with("prog.elf", &elf());
        let _ = call(&e, "native_function_study", json!({"function": "main"}));
        let _ = call(&e, "native_strings_browse", json!({}));
        let dir = tempfile::tempdir().unwrap();
        let (a, b) = (dir.path().join("a.json"), dir.path().join("b.json"));
        call_val(&e, "core_evidence_export", json!({"path": a.to_string_lossy()})).unwrap();
        // Same bundle, but one record's result is edited while its id is kept.
        let mut bundle: Value = serde_json::from_slice(&std::fs::read(&a).unwrap()).unwrap();
        let rec = bundle["records"].as_array_mut().unwrap().iter_mut().find(|r| r["operation"] == "native_strings_browse").unwrap();
        rec["result"]["total"] = json!(999_999);
        std::fs::write(&b, serde_json::to_vec(&bundle).unwrap()).unwrap();

        let same = call_val(&e, "core_evidence_exports_compare", json!({"older_bundle": a.to_string_lossy(), "newer_bundle": a.to_string_lossy()})).unwrap();
        assert_eq!(same["result"]["counts"]["changed"], 0);
        assert_eq!(same["result"]["counts"]["tampered"], 0);

        let v = call_val(&e, "core_evidence_exports_compare", json!({"older_bundle": a.to_string_lossy(), "newer_bundle": b.to_string_lossy()})).unwrap();
        let r = &v["result"];
        assert_eq!(r["counts"]["tampered"], 1, "{r}");
        assert_eq!(r["counts"]["changed"], 1, "an equal id no longer counts as unchanged");
        assert_eq!(r["changed"][0]["reason"], "integrity");
        assert_eq!(r["integrity"]["failing"][0]["side"], "right");
        assert!(v["summary"].as_str().unwrap().contains("edited after they were recorded"));
    }

    #[test]
    fn compare_functions_detects_change() {
        let e = engine_with("prog.elf", &elf());
        let a = call(&e, "native_function_study", json!({"function": "main"}));
        // Compare a record with itself -> unchanged.
        let same = call_val(&e, "app_function_versions_compare", json!({"left": a.clone(), "right": a.clone()})).unwrap();
        assert_eq!(same["result"]["status"], "unchanged");
        // Two different real functions -> changed.
        let other = call(&e, "native_function_study", json!({"function": "helper"}));
        let diff = call_val(&e, "app_function_versions_compare", json!({"left": a, "right": other})).unwrap();
        assert_eq!(diff["result"]["status"], "changed");
    }

    #[test]
    fn verify_reconstruction_checks_evidence() {
        let e = engine_with("prog.elf", &elf());
        let a = call(&e, "native_function_study", json!({"function": "main"}));
        let id = a["id"].as_str().unwrap().to_string();
        let good = call_val(
            &e,
            "app_rebuild_claim_check",
            json!({"specification": {"goal": "rebuilt main", "expectations": [{"description": "main analysed", "evidence_ids": [id]}]}}),
        )
        .unwrap();
        assert_eq!(good["result"]["verified"], true);
        let bad = call_val(
            &e,
            "app_rebuild_claim_check",
            json!({"specification": {"goal": "x", "expectations": [{"description": "missing", "evidence_ids": ["ev_".to_owned() + &"0".repeat(64)]}]}}),
        )
        .unwrap();
        assert_eq!(bad["result"]["verified"], false);
    }

    #[test]
    fn build_call_path_finds_a_path() {
        let e = engine_with("prog.elf", &elf());
        // Collect native_function_study for every function.
        let list = call(&e, "native_functions_list", json!({"limit": 50}));
        let procs = list["result"]["functions"].as_array().cloned().unwrap_or_default();
        let mut funcs = Vec::new();
        let mut addrs = Vec::new();
        for p in procs.iter().take(10) {
            if let Some(name) = p.get("name").and_then(Value::as_str) {
                let d = call(&e, "native_function_study", json!({"function": name}));
                if let Some(entry) = d["result"]["function"]["entry"].as_str() {
                    addrs.push(entry.to_string());
                }
                funcs.push(d);
            }
        }
        if let Some(start) = addrs.first().cloned() {
            // Path to itself is always found.
            let r = call_val(&e, "app_call_path_find", json!({"functions": funcs, "start": start, "goal": start})).unwrap();
            assert_eq!(r["result"]["found"], true);
        }
    }

    #[test]
    fn find_changed_behavior_aggregates() {
        let e = Engine::new(crate::testing::session());
        // Build two folders and compare them to get a real comparison record.
        let dir = tempfile::tempdir().unwrap();
        let a = craft_anything_testkit::electron::write_files(&dir.path().join("v1"), &craft_anything_testkit::electron::notes_app_files()).unwrap();
        let b = craft_anything_testkit::electron::write_files(&dir.path().join("v2"), &craft_anything_testkit::electron::notes_app_v2_files()).unwrap();
        let cmp = call_val(&e, "core_archives_compare", json!({"left": a, "right": b})).unwrap();
        let out = call_val(&e, "app_changes_summarize", json!({"comparisons": [cmp]})).unwrap();
        assert_eq!(out["result"]["total"], 1);
        assert_eq!(out["result"]["changed"], 1);
    }
}
