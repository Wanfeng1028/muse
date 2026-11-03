//! Native workflows: overview, function dossier, call graph, call path, feature trace, batch
//! decompile, xrefs by name, API boundary, value flow, Objective-C/Swift metadata, dispatch
//! metadata and UI-action tracing. The heavy lifting lives in `craft_anything_analysis::native`.

use super::native_common::{from_report, hex, image, native, params_json, resolve_function, select_document, spec, user_names};
use crate::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use craft_anything_analysis::native as an;
use craft_anything_disasm::pseudo::lift;
use craft_anything_evidence::{Confidence, Coverage, Limitation, Location, ToolError};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};

pub fn specs() -> Vec<ToolSpec> {
    use Toolset::{Apple, Core, Native};
    let e = Effects::EVIDENCE;
    let trace = Effects::MUTATES_SESSION;
    let t = Requires::Target;
    vec![
        spec(
            "core_overview_show",
            "Overview",
            "One-page summary of a program: format, architecture, entry, segments, counts of functions/strings/imports/exports, libraries, hardening, toolchain hints. detail=summary keeps the full record and returns counts plus a reference to page with core_evidence_browse.",
            "Get the big picture of a program.",
            Core,
            e,
            t,
            schema_of::<OverviewParams>,
            core_overview_show,
        ),
        spec(
            "native_function_study",
            "Function dossier",
            "Everything about one function in one record: facts, pseudo-C, assembly, basic blocks, callers, callees, references, strings, unresolved calls, API boundary and register value flow. Page through big facets with core_evidence_browse; detail=summary returns counts plus a reference first.",
            "Get the full story of one function.",
            Core,
            e | Effects::CARRIES_TARGET_CONTENT,
            t,
            schema_of::<FunctionParams>,
            native_function_study,
        ),
        spec(
            "native_call_graph_show",
            "Call graph",
            "Callees (forward) or callers (backward) of a function, level by level, with edges and honest truncation.",
            "See what a function leads to, or what leads to it.",
            Native,
            e,
            t,
            schema_of::<CallGraphParams>,
            native_call_graph_show,
        ),
        spec(
            "core_feature_find",
            "Trace a feature",
            "Literal text → matching strings, functions and imports → the code that uses them → the functions involved.",
            "Follow a word you see in the app to the code behind it.",
            Core,
            trace,
            t,
            schema_of::<TraceFeatureParams>,
            core_feature_find,
        ),
        spec(
            "native_call_path_find",
            "Call path",
            "Shortest direct-call path from one function to another (forward or backward), with goal status and residual unknowns. Forward, the goal may also be an import (e.g. CreateWindowExW): the path ends at the call to it.",
            "Find how one function gets to another.",
            Native,
            trace,
            t,
            schema_of::<CallPathParams>,
            native_call_path_find,
        ),
        spec(
            "native_functions_decompile",
            "Decompile many",
            "Pseudo-C for several functions at once (up to 64); each item succeeds or fails on its own.",
            "Read several functions as C-like code at once.",
            Native,
            e | Effects::CARRIES_TARGET_CONTENT,
            t,
            schema_of::<BatchParams>,
            native_functions_decompile,
        ),
        spec(
            "native_name_xrefs_list",
            "References to a name",
            "Exact name (function, data symbol or import) → its address and every reference to it. Gives reason name_not_found when nothing has that name.",
            "Find everything that uses a named thing.",
            Native,
            e,
            t,
            schema_of::<NameParams>,
            native_name_xrefs_list,
        ),
        spec(
            "native_api_show",
            "API boundary",
            "The system and library APIs a function calls, grouped by purpose (files, network, processes, crypto…), plus internal calls, indirect calls and jump tables.",
            "See which outside services a function uses.",
            Native,
            trace | Effects::CARRIES_TARGET_CONTENT,
            t,
            schema_of::<ProcParams>,
            native_api_show,
        ),
        spec(
            "native_value_flow_show",
            "Value flow",
            "Register def-use graph of a function (which instruction's result each instruction reads), parameter uses and side effects, following callees to max_depth. Nodes are paged (offset/limit).",
            "See where values in a function come from and go.",
            Native,
            e,
            t,
            schema_of::<ValueParams>,
            native_value_flow_show,
        ),
        spec(
            "apple_objc_classes_list",
            "Objective-C classes",
            "Deduplicated Objective-C class and category names (with method counts), optionally filtered by a substring.",
            "List the Objective-C classes in a Mac or iPhone program.",
            Apple,
            e,
            t,
            schema_of::<PatternParams>,
            apple_objc_classes_list,
        ),
        spec(
            "apple_objc_protocols_list",
            "Objective-C protocols",
            "Objective-C protocols with their methods, plus Swift protocols from symbols.",
            "List the protocols (interfaces) a Mac or iPhone program defines.",
            Apple,
            e,
            t,
            schema_of::<DocParams>,
            apple_objc_protocols_list,
        ),
        spec(
            "apple_swift_types_list",
            "Swift types",
            "Swift symbols grouped into classes, structs, enums, protocols, extensions and other, by type path and role (accessor, descriptor, method…).",
            "See the Swift types in a program.",
            Apple,
            e,
            t,
            schema_of::<SwiftParams>,
            apple_swift_types_list,
        ),
        spec(
            "apple_dispatch_show",
            "Dispatch metadata",
            "Objective-C method dispatch (class, selector, implementation) and Swift dispatch-related symbols, up to max_records.",
            "See which code runs for each Objective-C message.",
            Apple,
            e,
            t,
            schema_of::<DispatchParams>,
            apple_dispatch_show,
        ),
        spec(
            "apple_ui_action_trace",
            "Trace a UI action",
            "UI action or selector (e.g. `saveDocument:`) → handlers (Objective-C methods, matching names, code using the string) → the static calls they make, bounded by max_depth/max_nodes/max_edges. Best effort; limits are listed.",
            "Find the code that runs when a button or menu item is used.",
            Apple,
            e,
            t,
            schema_of::<UiActionParams>,
            apple_ui_action_trace,
        ),
    ]
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
pub struct ProcParams {
    /// Open target (document) to use; the active one when omitted.
    #[serde(default)]
    pub document: Option<String>,
    /// Function name or address.
    pub function: String,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct OverviewParams {
    /// Open target (document) to use; the active one when omitted.
    #[serde(default)]
    pub document: Option<String>,
    /// complete (default) returns the full record; summary returns counts plus a reference to page
    /// with core_evidence_browse.
    #[serde(default)]
    pub detail: super::Detail,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct FunctionParams {
    /// Open target (document) to use; the active one when omitted.
    #[serde(default)]
    pub document: Option<String>,
    /// Function name or address.
    pub function: String,
    /// complete (default) returns the full dossier; summary returns counts plus a reference to page
    /// big facets (assembly, callers…) with core_evidence_browse.
    #[serde(default)]
    pub detail: super::Detail,
}

#[derive(Debug, Clone, Copy, Default, Deserialize, Serialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Dir {
    #[default]
    Forward,
    Backward,
}

fn d_depth() -> usize {
    8
}
fn d_nodes() -> usize {
    500
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct CallGraphParams {
    /// Open target (document) to use; the active one when omitted.
    #[serde(default)]
    pub document: Option<String>,
    /// Start function (name or address).
    pub address: String,
    /// forward (callees, default) or backward (callers).
    #[serde(default)]
    pub direction: Dir,
    /// Levels to follow (1..=64, default 8).
    #[serde(default = "d_depth")]
    pub max_depth: usize,
    /// Most functions to include (1..=20000, default 500).
    #[serde(default = "d_nodes")]
    pub max_nodes: usize,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct TraceFeatureParams {
    /// Open target (document) to use; the active one when omitted.
    #[serde(default)]
    pub document: Option<String>,
    /// Text to look for (e.g. a label or message you see in the app).
    pub query: String,
    /// Match case exactly (default false).
    #[serde(default)]
    pub case_sensitive: bool,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct CallPathParams {
    /// Open target (document) to use; the active one when omitted.
    #[serde(default)]
    pub document: Option<String>,
    /// Start function (name or address).
    pub start: String,
    /// Goal function (name or address), or an import's name when tracing forward; without it,
    /// everything reachable is listed.
    #[serde(default)]
    pub goal: Option<String>,
    /// forward (start calls … goal, default) or backward (goal is reached from start's callers).
    #[serde(default)]
    pub direction: Dir,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct BatchParams {
    /// Open target (document) to use; the active one when omitted.
    #[serde(default)]
    pub document: Option<String>,
    /// Function names or addresses (at most 64).
    #[serde(default)]
    pub addresses: Vec<String>,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct NameParams {
    /// Open target (document) to use; the active one when omitted.
    #[serde(default)]
    pub document: Option<String>,
    /// Exact name of a function, data symbol or import.
    pub name: String,
}

fn v_depth() -> usize {
    3
}
fn v_funcs() -> usize {
    16
}
fn v_sites() -> usize {
    256
}
fn v_nodes() -> usize {
    5000
}
fn v_edges() -> usize {
    10_000
}
fn v_limit() -> usize {
    1000
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ValueParams {
    /// Open target (document) to use; the active one when omitted.
    #[serde(default)]
    pub document: Option<String>,
    /// Function name or address.
    pub function: String,
    /// Callee levels to follow (0..=16, default 3).
    #[serde(default = "v_depth")]
    pub max_depth: usize,
    /// Most functions to follow (1..=64, default 16).
    #[serde(default = "v_funcs")]
    pub max_functions: usize,
    /// Most call sites to examine (1..=4096, default 256).
    #[serde(default = "v_sites")]
    pub max_call_sites: usize,
    /// Most nodes (≤20000, default 5000).
    #[serde(default = "v_nodes")]
    pub max_nodes: usize,
    /// Most edges (≤40000, default 10000).
    #[serde(default = "v_edges")]
    pub max_edges: usize,
    /// First node of the page.
    #[serde(default)]
    pub offset: usize,
    /// Nodes per page (1..=5000, default 1000).
    #[serde(default = "v_limit")]
    pub limit: usize,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct PatternParams {
    /// Open target (document) to use; the active one when omitted.
    #[serde(default)]
    pub document: Option<String>,
    /// Only names containing this (case-insensitive); everything when empty.
    #[serde(default)]
    pub pattern: String,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct SwiftParams {
    /// Open target (document) to use; the active one when omitted.
    #[serde(default)]
    pub document: Option<String>,
    /// classes, structs, enums, protocols, extensions or other.
    #[serde(default)]
    pub category: Option<String>,
    /// Only type paths containing this (case-insensitive).
    #[serde(default)]
    pub pattern: Option<String>,
}

fn d_records() -> usize {
    5000
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct DispatchParams {
    /// Open target (document) to use; the active one when omitted.
    #[serde(default)]
    pub document: Option<String>,
    /// Most records (1..=20000, default 5000).
    #[serde(default = "d_records")]
    pub max_records: usize,
}

fn u_depth() -> usize {
    8
}
fn u_nodes() -> usize {
    250
}
fn u_edges() -> usize {
    500
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct UiActionParams {
    /// Open target (document) to use; the active one when omitted.
    #[serde(default)]
    pub document: Option<String>,
    /// Action or selector, e.g. `saveDocument:`.
    pub action: String,
    /// Call levels to follow (0..=32, default 8).
    #[serde(default = "u_depth")]
    pub max_depth: usize,
    /// Most functions (1..=2000, default 250).
    #[serde(default = "u_nodes")]
    pub max_nodes: usize,
    /// Most call edges (1..=5000, default 500).
    #[serde(default = "u_edges")]
    pub max_edges: usize,
}

fn range(name: &str, v: usize, lo: usize, hi: usize) -> Result<usize, ToolError> {
    if v < lo || v > hi { Err(ToolError::invalid(format!("{name} must be {lo}..={hi}"))) } else { Ok(v) }
}

fn core_overview_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: OverviewParams = parse_params(params)?;
    select_document(ctx, &p.document)?;
    let st = native(ctx)?;
    let name = ctx.session.active()?.target.name.clone();
    let r = an::overview(&st.img, &st.prog, &name);
    let cov = super::native_common::program_coverage(&st.prog, Coverage::complete(1));
    let e = super::native_common::report_evidence_with(ctx, "core_overview_show", params_json(&p), r, cov)?;
    let extras = super::native_common::counts_of(&e.result);
    super::detailed(ctx, e, p.detail, extras)
}

fn native_function_study(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: FunctionParams = parse_params(params)?;
    select_document(ctx, &p.document)?;
    let st = native(ctx)?;
    let t = ctx.session.active()?;
    let f = resolve_function(t, &st.prog, &p.function)?;
    let user = user_names(t);
    let names = |a: u64| user.get(&a).cloned();
    let mut r = an::dossier(&st.img, &st.prog, f, &names);
    // Comments the user wrote inside the function.
    let comments: Vec<Value> = t
        .annotations
        .comments
        .iter()
        .chain(t.annotations.inline_comments.iter())
        .filter(|(a, _)| f.contains(**a))
        .map(|(a, c)| json!({"address": hex(*a), "comment": c}))
        .collect();
    r.result["comments"] = json!(comments);
    let e = super::native_common::report_evidence(ctx, "native_function_study", params_json(&p), r)?;
    let extras = super::native_common::counts_of(&e.result);
    super::detailed(ctx, e, p.detail, extras)
}

fn native_call_graph_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: CallGraphParams = parse_params(params)?;
    select_document(ctx, &p.document)?;
    let depth = range("max_depth", p.max_depth, 1, 64)?;
    let nodes = range("max_nodes", p.max_nodes, 1, 20_000)?;
    let st = native(ctx)?;
    let t = ctx.session.active()?;
    let f = resolve_function(t, &st.prog, &p.address)?;
    let user = user_names(t);
    let names = |a: u64| user.get(&a).cloned();
    let r = an::call_graph(&st.prog, f.entry, matches!(p.direction, Dir::Forward), depth, nodes, &names);
    from_report(ctx, "native_call_graph_show", params_json(&p), r)
}

fn core_feature_find(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: TraceFeatureParams = parse_params(params)?;
    select_document(ctx, &p.document)?;
    if p.query.trim().is_empty() {
        return Err(ToolError::invalid("query is empty"));
    }
    let st = native(ctx)?;
    let t = ctx.session.active()?;
    let user = user_names(t);
    let names = |a: u64| user.get(&a).cloned();
    let r = an::feature_paths(&st.prog, &p.query, p.case_sensitive, &names);
    from_report(ctx, "core_feature_find", params_json(&p), r)
}

fn native_call_path_find(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: CallPathParams = parse_params(params)?;
    select_document(ctx, &p.document)?;
    let st = native(ctx)?;
    let t = ctx.session.active()?;
    let start = resolve_function(t, &st.prog, &p.start)?.entry;
    let forward = matches!(p.direction, Dir::Forward);
    let goal = match p.goal.as_deref() {
        None => None,
        Some(g) => match resolve_function(t, &st.prog, g) {
            Ok(f) => Some(an::Goal::Function(f.entry)),
            Err(e) => match st.img.bin.imports.iter().find(|i| i.name.eq_ignore_ascii_case(g.trim())) {
                Some(i) if forward => Some(an::Goal::Import(&i.name)),
                Some(_) => return Err(ToolError::invalid("An import can only be the goal when tracing forward.").with_remediation("Use direction forward.")),
                None => return Err(e),
            },
        },
    };
    let user = user_names(t);
    let names = |a: u64| user.get(&a).cloned();
    let r = an::call_path(&st.prog, start, goal, forward, &names);
    from_report(ctx, "native_call_path_find", params_json(&p), r)
}

fn native_functions_decompile(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: BatchParams = parse_params(params)?;
    select_document(ctx, &p.document)?;
    if p.addresses.len() > 64 {
        return Err(ToolError::invalid("at most 64 functions per batch"));
    }
    let st = native(ctx)?;
    let t = ctx.session.active()?;
    let user = user_names(t);
    let names = |a: u64| user.get(&a).cloned();
    let mut items = Vec::new();
    let mut ok = 0;
    let mut locations = Vec::new();
    for (i, a) in p.addresses.iter().enumerate() {
        ctx.cancel.check()?;
        ctx.report(Some(i as f32 / p.addresses.len().max(1) as f32), format!("decompiling {a}"));
        match resolve_function(t, &st.prog, a) {
            Ok(f) => {
                let ps = lift(&st.img, &st.prog, f, &names);
                ok += 1;
                locations.push(Location::address(f.entry));
                items.push(json!({"input": a, "ok": true, "entry": hex(f.entry), "signature": ps.signature, "pseudo_code": ps.text, "structured": ps.structured, "limitations": ps.limitations.iter().map(|(c, _)| c.clone()).collect::<Vec<_>>()}));
            }
            Err(e) => items.push(json!({"input": a, "ok": false, "error": e.message})),
        }
    }
    let n = p.addresses.len();
    let e = super::native_common::ev(ctx, "native_functions_decompile", params_json(&p))?
        .result(json!({"items": items, "succeeded": ok, "failed": n - ok}))
        .summary(format!("Decompiled {ok} of {n} functions."))
        .confidence(Confidence::Inferred)
        .coverage(Coverage::complete(n as u64))
        .locations(locations)
        .limitation(Limitation::new("pseudo_code_inferred", "pseudo-C from the clean-room lifter is register-level and approximate"))
        .build()?;
    Ok(ToolOutput::evidence(e))
}

fn native_name_xrefs_list(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: NameParams = parse_params(params)?;
    select_document(ctx, &p.document)?;
    let st = native(ctx)?;
    let t = ctx.session.active()?;
    let user = user_names(t);
    let names = |a: u64| user.get(&a).cloned();
    let r = an::xrefs_to_name(&st.prog, &user, p.name.trim(), &names);
    from_report(ctx, "native_name_xrefs_list", params_json(&p), r)
}

fn native_api_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ProcParams = parse_params(params)?;
    select_document(ctx, &p.document)?;
    let st = native(ctx)?;
    let t = ctx.session.active()?;
    let f = resolve_function(t, &st.prog, &p.function)?;
    let user = user_names(t);
    let names = |a: u64| user.get(&a).cloned();
    let r = an::native_api(&st.prog, f, &names);
    from_report(ctx, "native_api_show", params_json(&p), r)
}

fn native_value_flow_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ValueParams = parse_params(params)?;
    select_document(ctx, &p.document)?;
    let o = an::ValueTraceOpts {
        max_depth: range("max_depth", p.max_depth, 0, 16)?,
        max_functions: range("max_functions", p.max_functions, 1, 64)?,
        max_call_sites: range("max_call_sites", p.max_call_sites, 1, 4096)?,
        max_nodes: range("max_nodes", p.max_nodes, 1, 20_000)?,
        max_edges: range("max_edges", p.max_edges, 1, 40_000)?,
        offset: p.offset,
        limit: range("limit", p.limit, 1, 5000)?,
    };
    let st = native(ctx)?;
    let t = ctx.session.active()?;
    let f = resolve_function(t, &st.prog, &p.function)?;
    let user = user_names(t);
    let names = |a: u64| user.get(&a).cloned();
    let r = an::value_trace(&st.img, &st.prog, f, &o, &names);
    let total = r.result["page"]["total"].as_u64().unwrap_or(0);
    let shown = r.result["nodes"].as_array().map(Vec::len).unwrap_or(0) as u64;
    let e = super::native_common::ev(ctx, "native_value_flow_show", params_json(&p))?
        .result(r.result)
        .summary(r.summary)
        .confidence(r.confidence)
        .limitations(r.limitations)
        .locations(r.locations)
        .coverage(Coverage::page(shown, total, p.offset as u64))
        .build()?;
    Ok(ToolOutput::evidence(e))
}

fn apple_objc_classes_list(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: PatternParams = parse_params(params)?;
    select_document(ctx, &p.document)?;
    let img = image(ctx)?;
    let r = an::objc_classes(&img.0, &p.pattern);
    from_report(ctx, "apple_objc_classes_list", params_json(&p), r)
}

fn apple_objc_protocols_list(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: DocParams = parse_params(params)?;
    select_document(ctx, &p.document)?;
    let img = image(ctx)?;
    let r = an::objc_protocols(&img.0);
    from_report(ctx, "apple_objc_protocols_list", params_json(&p), r)
}

fn apple_swift_types_list(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: SwiftParams = parse_params(params)?;
    select_document(ctx, &p.document)?;
    if let Some(c) = &p.category
        && !["classes", "structs", "enums", "protocols", "extensions", "other"].contains(&c.as_str())
    {
        return Err(ToolError::invalid("category must be classes, structs, enums, protocols, extensions or other"));
    }
    let img = image(ctx)?;
    let r = an::swift_types(&img.0.bin, p.category.as_deref(), p.pattern.as_deref());
    from_report(ctx, "apple_swift_types_list", params_json(&p), r)
}

fn apple_dispatch_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: DispatchParams = parse_params(params)?;
    select_document(ctx, &p.document)?;
    let max = range("max_records", p.max_records, 1, 20_000)?;
    let st = native(ctx)?;
    let t = ctx.session.active()?;
    let user = user_names(t);
    let names = |a: u64| user.get(&a).cloned();
    let r = an::dispatch_metadata(&st.img, &st.prog, max, &names);
    from_report(ctx, "apple_dispatch_show", params_json(&p), r)
}

fn apple_ui_action_trace(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: UiActionParams = parse_params(params)?;
    select_document(ctx, &p.document)?;
    if p.action.trim().is_empty() {
        return Err(ToolError::invalid("action is empty"));
    }
    let depth = range("max_depth", p.max_depth, 0, 32)?;
    let nodes = range("max_nodes", p.max_nodes, 1, 2000)?;
    let edges = range("max_edges", p.max_edges, 1, 5000)?;
    let st = native(ctx)?;
    let t = ctx.session.active()?;
    let user = user_names(t);
    let names = |a: u64| user.get(&a).cloned();
    let r = an::ui_action(&st.img, &st.prog, p.action.trim(), depth, nodes, edges, &names);
    from_report(ctx, "apple_ui_action_trace", params_json(&p), r)
}

#[cfg(test)]
mod tests {
    use super::super::native_common::test_support::*;
    use craft_anything_testkit as tk;
    use serde_json::json;

    #[test]
    fn detail_summary_is_smaller_and_pageable() {
        let (elf, _) = tk::elf64(tk::ElfArch::X86_64, true);
        let e = engine_with("prog", &elf);
        let complete = call(&e, "native_function_study", json!({"function": "main"}));
        let summary = call(&e, "native_function_study", json!({"function": "main", "detail": "summary"}));

        // The summary body is smaller and carries a retained reference plus the paging hint.
        let full_len = serde_json::to_string(&complete).unwrap().len();
        let sum_len = serde_json::to_string(&summary).unwrap().len();
        assert!(sum_len < full_len, "summary ({sum_len}) should be smaller than complete ({full_len})");
        assert_eq!(summary["result"]["continue_with"], "core_evidence_browse");
        let id = summary["result"]["saved_evidence"]["evidence_id"].as_str().unwrap().to_string();
        assert!(id.starts_with("ev_"));
        assert!(summary["result"]["counts"].is_object(), "counts extras present");
        // The id is the same whether summary or complete was asked (detail is not part of the id).
        assert_eq!(complete["id"].as_str().unwrap(), id);

        // The full record is retained and can be paged facet by facet with core_evidence_browse.
        let view = call(&e, "core_evidence_browse", json!({"source": {"kind": "saved", "evidence_id": id}, "show": {"kind": "summary"}}));
        assert_eq!(view["result"]["from_tool"], "native_function_study");

        // core_overview_show too.
        let bo = call(&e, "core_overview_show", json!({"detail": "summary"}));
        assert_eq!(bo["result"]["continue_with"], "core_evidence_browse");
        assert!(bo["result"]["saved_evidence"]["evidence_id"].as_str().unwrap().starts_with("ev_"));
    }

    #[test]
    fn workflows_end_to_end() {
        let (elf, _) = tk::elf64(tk::ElfArch::X86_64, true);
        let e = engine_with("prog", &elf);
        let r = call(&e, "core_overview_show", json!({}));
        assert_eq!(r["result"]["counts"]["functions"], 4);
        let r = call(&e, "native_function_study", json!({"function": "main"}));
        assert!(r["result"]["pseudocode"].as_str().unwrap().contains("puts"));
        assert!(r["result"]["flow_effects"].as_array().unwrap().iter().any(|x| x["text"] == "puts"));
        let r = call(&e, "native_call_graph_show", json!({"address": "main"}));
        assert!(r["result"]["levels"]["1"].is_array());
        let r = call(&e, "native_call_graph_show", json!({"address": "helper", "direction": "backward"}));
        assert_eq!(r["result"]["levels"]["1"][0]["name"], "main");
        let r = call(&e, "core_feature_find", json!({"query": "hello"}));
        assert_eq!(r["result"]["functions"][0]["name"], "main");
        let r = call(&e, "native_call_path_find", json!({"start": "main", "goal": "dispatch"}));
        assert_eq!(r["result"]["goal_result"], "reached");
        // An import is a goal when tracing forward, and only then.
        let r = call(&e, "native_call_path_find", json!({"start": "main", "goal": "puts"}));
        assert_eq!(r["result"]["goal_result"], "reached");
        assert_eq!(r["result"]["path"].as_array().unwrap().last().unwrap()["import"], true);
        let err = call_err(&e, "native_call_path_find", json!({"start": "main", "goal": "puts", "direction": "backward"}));
        assert!(err.message.contains("forward"), "{}", err.message);
        let r = call(&e, "native_functions_decompile", json!({"addresses": ["main", "helper", "nope"]}));
        assert_eq!(r["result"]["succeeded"], 2);
        assert_eq!(r["result"]["failed"], 1);
        let r = call(&e, "native_name_xrefs_list", json!({"name": "helper"}));
        assert_eq!(r["result"]["references"].as_array().unwrap().len(), 1);
        let r = call(&e, "native_api_show", json!({"function": "main"}));
        assert_eq!(r["result"]["api_calls_by_category"]["text"][0]["name"], "puts");
        let r = call(&e, "native_value_flow_show", json!({"function": "main", "limit": 3}));
        assert_eq!(r["result"]["nodes"].as_array().unwrap().len(), 3);
        assert_eq!(r["coverage"]["status"], "partial");
        assert!(call_err(&e, "native_value_flow_show", json!({"function": "main", "max_depth": 99})).message.contains("max_depth"));
        // Apple tools on an ELF: empty and honest
        let r = call(&e, "apple_objc_classes_list", json!({}));
        assert_eq!(r["result"]["classes"].as_array().unwrap().len(), 0);
        assert!(r["limitations"].as_array().unwrap().iter().any(|l| l["code"] == "not_macho"));
    }

    #[test]
    fn apple_workflows_end_to_end() {
        let e = engine_with("app", &tk::macho64());
        let r = call(&e, "apple_objc_classes_list", json!({"pattern": "widget"}));
        assert_eq!(r["result"]["classes"][0], tk::OBJC_CLASS);
        let r = call(&e, "apple_objc_protocols_list", json!({}));
        assert_eq!(r["result"]["protocols"][0]["name"], tk::OBJC_PROTOCOL);
        let r = call(&e, "apple_swift_types_list", json!({}));
        assert!(r["result"]["counts"].is_object());
        let r = call(&e, "apple_dispatch_show", json!({}));
        assert_eq!(r["result"]["records"][0]["implementation_name"], "-[CAWidget tapButton:]");
        let r = call(&e, "apple_ui_action_trace", json!({"action": "tapButton:"}));
        assert_eq!(r["result"]["handlers"].as_array().unwrap().len(), 1);
        assert_eq!(r["confidence"], "inferred");
        let r = call(&e, "core_feature_find", json!({"query": "settings"}));
        assert_eq!(r["result"]["functions"][0]["name"], "-[CAWidget tapButton:]");
    }
}
