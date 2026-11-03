//! .NET assemblies with the built-in ECMA-335 reader: inventory, members (with decoded IL facts),
//! native boundaries, and workflows over that evidence: cross-build member comparison, P/Invoke
//! verification against native exports, checking decompiled C# against metadata, and an
//! application graph.

use super::artifact_tools::{WalkOptions, is_path_input, resolve_evidence_input, walk_dir};
use super::native_common::{page, spec};
use super::static_input::{Input, builder, format_err, load, load_path};
use crate::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use craft_anything_evidence::{Authority, Confidence, Coverage, CoverageStatus, ErrorCode, Limitation, Location, Subject, ToolError};
use craft_anything_formats::dotnet::{self, Assembly, MemberOptions, Members, MethodInfo, NativeBoundaries, csharp};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};
use std::path::PathBuf;

/// Largest assembly read (the parser's own limit).
const MAX_ASSEMBLY: u64 = 128 << 20;

pub fn specs() -> Vec<ToolSpec> {
    use Toolset::Managed;
    let e = Effects::EVIDENCE;
    vec![
        spec(
            "managed_assembly_show",
            ".NET assembly overview",
            "Built-in ECMA-335 reader: PE/CLI header (runtime version, IL-only/32-bit/strong-name flags, entry point, ReadyToRun), metadata streams and table row counts, assembly identity, assembly and module references, manifest resources, forwarded types, assembly attributes (TargetFramework decoded) and a classification (runtime family, implementation, managed architecture). Uses the active target unless path is given.",
            "See what a .NET program is: its name, version, which .NET it targets and what it depends on.",
            Managed,
            e,
            Requires::Nothing,
            schema_of::<PathParams>,
            managed_assembly_show,
        ),
        spec(
            "managed_members_list",
            ".NET types and methods",
            "Types, fields, properties, events and methods of a .NET assembly with C#-like signatures; for each IL method body: header kind, max stack, locals, exception clauses, IL size, il_hash, an il_shape_hash that survives renames, call targets, field accesses and string literals (optionally the IL listing). Filter with type_names; paged by type (offset/limit).",
            "List the classes and methods inside a .NET program and what each method calls.",
            Managed,
            e,
            Requires::Nothing,
            schema_of::<MembersParams>,
            managed_members_list,
        ),
        spec(
            "managed_native_calls_list",
            ".NET native calls",
            "Where a .NET assembly crosses into native code: P/Invoke (DllImport) rows with module, entry point, charset, calling convention, SetLastError, best-fit and PreserveSig; internal calls; native-code (mixed-mode) and runtime-implemented methods; UnmanagedCallersOnly and LibraryImport declarations; module references and vtable fixups.",
            "See which native (non-.NET) libraries and functions a .NET program calls.",
            Managed,
            e,
            Requires::Nothing,
            schema_of::<PathParams>,
            managed_native_calls_list,
        ),
        spec(
            "managed_assemblies_compare",
            "Compare two .NET builds",
            "Compare the members of two assemblies (managed_members_list evidence or absolute paths) with tiered unique matching: identical IL and signature (survives renames), then type+name+signature, then the same structure. Reports unchanged, changed (body differs), renamed or moved, added, removed and ambiguous methods, plus added/removed types and fields.",
            "See which methods changed between two versions of a .NET program.",
            Managed,
            e,
            Requires::Nothing,
            schema_of::<CompareParams>,
            managed_assemblies_compare,
        ),
        spec(
            "managed_native_calls_verify",
            "Check .NET native calls",
            "Check each P/Invoke of a managed assembly (managed_native_calls_list evidence or a path) against the exports of native libraries (native_layout_show evidence or absolute paths): found, found as an A/W or stdcall-decorated variant, case mismatch, missing, or undetermined when the module wasn't supplied.",
            "Check that the native functions a .NET program calls really exist in the libraries it ships with.",
            Managed,
            e,
            Requires::Nothing,
            schema_of::<VerifyParams>,
            managed_native_calls_verify,
        ),
        spec(
            "managed_reconstruction_check",
            "Check decompiled C#",
            "Check user-supplied C# (a file, a folder of .cs files, or text) against the assembly's member evidence: declarations matched, signature mismatches, members missing from the source, extra source members, compiler-implicit members, and missing/extra types. Declarations only, not behaviour.",
            "Check that rebuilt or decompiled C# source declares the same classes and methods as the original program.",
            Managed,
            e,
            Requires::Nothing,
            schema_of::<ImportParams>,
            managed_reconstruction_check,
        ),
        spec(
            "managed_app_graph_build",
            ".NET application graph",
            "Project a .NET assembly (managed evidence or a path) into an application graph: assembly, referenced assemblies, types, methods, external members, native modules and resources, joined by contains, references, inherits, calls and pinvoke edges. Bounded by max_nodes.",
            "Draw a map of a .NET program: its parts and how they call each other and native code.",
            Managed,
            e,
            Requires::Nothing,
            schema_of::<GraphParams>,
            managed_app_graph_build,
        ),
    ]
}

// ---------------------------------------------------------------------------------------------
// Params

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct PathParams {
    /// Absolute path of a .NET assembly (.dll/.exe); the active target when omitted.
    #[serde(default)]
    pub path: Option<String>,
}

fn d_limit() -> usize {
    100
}
fn d_max_instructions() -> usize {
    20_000
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct MembersParams {
    /// Absolute path of a .NET assembly; the active target when omitted.
    #[serde(default)]
    pub path: Option<String>,
    /// Only these types (full name like `Ns.Type`, nested as `Ns.Outer/Inner`, or simple name).
    #[serde(default)]
    pub type_names: Option<Vec<String>>,
    /// First type of the page.
    #[serde(default)]
    pub offset: usize,
    /// Types per page (1–5000).
    #[serde(default = "d_limit")]
    pub limit: usize,
    /// Include each method's IL listing.
    #[serde(default)]
    pub include_il: bool,
    /// Most instructions decoded per method (1–1000000).
    #[serde(default = "d_max_instructions")]
    pub max_instructions: usize,
}

fn d_rows() -> usize {
    500
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct CompareParams {
    /// The older build: managed_members_list evidence (inline, {"kind":"saved","evidence_id":…} or an id) or an absolute path.
    pub left: Value,
    /// The newer build, in the same forms.
    pub right: Value,
    /// Most rows per list.
    #[serde(default = "d_rows")]
    pub max_rows: usize,
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct VerifyParams {
    /// The managed side: managed_native_calls_list evidence or an absolute assembly path.
    pub managed: Value,
    /// Native libraries: native_layout_show evidence or absolute paths (ELF, PE or Mach-O).
    pub native: Vec<Value>,
}

fn d_max_files() -> usize {
    5000
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ImportParams {
    /// The assembly: managed_members_list evidence or an absolute path.
    pub members: Value,
    /// Absolute path of a .cs file or a folder of .cs files.
    #[serde(default)]
    pub source_path: Option<String>,
    /// C# source text (instead of source_path).
    #[serde(default)]
    pub source_text: Option<String>,
    /// Most .cs files read from a folder.
    #[serde(default = "d_max_files")]
    pub max_files: usize,
    /// Most rows per list.
    #[serde(default = "d_rows")]
    pub max_rows: usize,
}

fn d_nodes() -> usize {
    2000
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct GraphParams {
    /// Managed evidence (managed_assembly_show, managed_members_list or managed_native_calls_list) or an absolute path; the active target when omitted.
    #[serde(default)]
    pub input: Option<Value>,
    /// Most nodes (10–20000).
    #[serde(default = "d_nodes")]
    pub max_nodes: usize,
}

// ---------------------------------------------------------------------------------------------
// Helpers

fn open_assembly(input: &Input) -> Result<Assembly<'_>, ToolError> {
    dotnet::open(&input.bytes).map_err(|e| {
        format_err(e, "a .NET assembly").with_remediation("Pass a .NET .dll or .exe (a PE file with a CLI header); run triage to check what the file is.")
    })
}

/// An assembly named by evidence (re-read from its recorded path and checked unchanged) or a path.
struct ManagedSource {
    input: Input,
    evidence_id: Option<String>,
    type_names: Option<Vec<String>>,
}

const MANAGED_OPS: &[&str] = &["managed_assembly_show", "managed_members_list", "managed_native_calls_list"];

fn managed_source(ctx: &Ctx<'_>, v: &Value, ops: &[&str]) -> Result<ManagedSource, ToolError> {
    if let Some(p) = is_path_input(v) {
        return Ok(ManagedSource { input: load_path(p, MAX_ASSEMBLY)?, evidence_id: None, type_names: None });
    }
    let ev = resolve_evidence_input(ctx, v, ops)?;
    let path = ev.params.get("path").and_then(Value::as_str).ok_or_else(|| ToolError::invalid(format!("evidence {} records no path", ev.id)))?;
    let input = load_path(path, MAX_ASSEMBLY)?;
    if input.subject.sha256 != ev.subject.sha256 {
        return Err(ToolError::new(ErrorCode::FileChanged, format!("{path} changed since evidence {} was recorded", ev.id))
            .with_remediation("Run the inspect tool again, or pass the path directly."));
    }
    let type_names = ev.params.get("type_names").and_then(|t| serde_json::from_value(t.clone()).ok()).flatten();
    Ok(ManagedSource { input, evidence_id: Some(ev.id), type_names })
}

fn managed_limitations(a: &Assembly<'_>) -> Vec<Limitation> {
    let mut l = Vec::new();
    if a.pe.ready_to_run {
        l.push(Limitation::new(
            "ready_to_run",
            "Precompiled (ReadyToRun) native code is present; this reader describes the IL and metadata, not the native code.",
        ));
    }
    if a.pe.cli.flags & dotnet::pe::COMIMAGE_FLAGS_ILONLY == 0 {
        l.push(Limitation::new("mixed_mode", "The image is not IL-only (mixed-mode); native code inside it is not described here."));
    }
    for w in a.md.warnings.iter().take(20) {
        l.push(Limitation::new("metadata", w.clone()));
    }
    l
}

fn member_options(type_names: Option<Vec<String>>, include_il: bool, max_instructions: usize) -> MemberOptions {
    MemberOptions { type_filter: type_names, include_il, max_instructions, max_types: 0, skip_bodies: false }
}

// ---------------------------------------------------------------------------------------------
// Static tools

fn managed_assembly_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: PathParams = parse_params(params)?;
    let input = load(ctx, p.path.as_deref(), MAX_ASSEMBLY)?;
    let a = open_assembly(&input)?;
    let inv = dotnet::inventory(&a);
    let md = &a.md;
    let types = md.rows(dotnet::meta::t::TYPE_DEF);
    let methods = md.rows(dotnet::meta::t::METHOD_DEF);
    let ident = inv.assembly.as_ref().map(|x| format!("{} {}", x.name, x.version)).unwrap_or_else(|| format!("module {}", input.name));
    let summary = format!(
        "{ident}: {} ({}, {}, {}), {types} types, {methods} methods, {} assembly references, {} module references{}.",
        if inv.is_dll { "library" } else { "program" },
        inv.classification.dotnet_family,
        inv.classification.implementation,
        inv.classification.dotnet_arch,
        inv.assembly_refs.len(),
        inv.module_refs.len(),
        inv.target_frameworks.first().map(|t| format!(", targets {t}")).unwrap_or_default()
    );
    let mut lims = managed_limitations(&a);
    lims.push(Limitation::new("static_only", "Read from the file only; nothing was loaded or run, so reflection and runtime-generated code are not seen."));
    let result = serde_json::to_value(&inv).unwrap_or(Value::Null);
    let ev = builder(ctx, "managed_assembly_show", input.subject.clone(), json!({"path": input.path}))
        .result(result)
        .summary(summary)
        .confidence(Confidence::Observed)
        .authority(Authority::OriginalFiles)
        .limitations(lims)
        .coverage(Coverage::complete(1))
        .location(Location::new("path", input.path.display().to_string()))
        .build()?;
    Ok(ToolOutput::evidence(ev))
}

fn managed_members_list(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: MembersParams = parse_params(params)?;
    if !(1..=1_000_000).contains(&p.max_instructions) {
        return Err(ToolError::invalid("max_instructions must be 1..=1000000"));
    }
    let input = load(ctx, p.path.as_deref(), MAX_ASSEMBLY)?;
    let a = open_assembly(&input)?;
    ctx.report(None, format!("Reading members of {}", input.name));
    let m = dotnet::members(&a, &member_options(p.type_names.clone(), p.include_il, p.max_instructions));
    if let Some(names) = &p.type_names
        && m.types.is_empty()
    {
        return Err(ToolError::invalid(format!("no type named {}", names.join(", ")))
            .with_remediation("List all types by omitting type_names, then pass full names such as Ns.Type."));
    }
    let limit = p.limit.clamp(1, 5000);
    let (types, cov) = page(&m.types, p.offset, limit);
    let bodies = m.types.iter().flat_map(|t| t.methods.iter()).filter(|x| x.body.is_some()).count();
    let calls: usize = m.types.iter().flat_map(|t| t.methods.iter()).filter_map(|x| x.body.as_ref()).map(|b| b.calls.len()).sum();
    let issues: Vec<Value> = m
        .types
        .iter()
        .flat_map(|t| t.methods.iter())
        .filter_map(|x| x.body.as_ref().and_then(|b| b.decode_issue.as_ref()).map(|i| json!({"method": x.key, "issue": i})))
        .take(100)
        .collect();
    let summary = format!(
        "{} types ({} listed from {}), {} methods ({bodies} with IL bodies, {calls} call sites), {} fields.",
        m.types.len(),
        types.len(),
        p.offset,
        m.total_methods,
        m.total_fields
    );
    let mut lims = managed_limitations(&a);
    lims.push(Limitation::new(
        "static_calls",
        "Call targets are the tokens named by call/callvirt/newobj/ldftn; virtual dispatch, delegates and reflection are not resolved.",
    ));
    if !issues.is_empty() {
        lims.push(Limitation::new("il_decode", format!("{} method bodies could not be fully decoded (see decode_issues)", issues.len())));
    }
    let ev = builder(
        ctx,
        "managed_members_list",
        input.subject.clone(),
        json!({"path": input.path, "type_names": p.type_names, "offset": p.offset, "limit": limit, "include_il": p.include_il}),
    )
    .result(json!({
        "total_types": m.types.len(),
        "assembly_type_count": m.total_types,
        "total_methods": m.total_methods,
        "total_fields": m.total_fields,
        "methods_with_bodies": bodies,
        "call_sites": calls,
        "decode_issues": issues,
        "types": types,
    }))
    .summary(summary)
    .confidence(Confidence::Observed)
    .authority(Authority::OriginalFiles)
    .limitations(lims)
    .coverage(cov)
    .location(Location::new("path", input.path.display().to_string()))
    .build()?;
    Ok(ToolOutput::evidence(ev))
}

fn managed_native_calls_list(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: PathParams = parse_params(params)?;
    let input = load(ctx, p.path.as_deref(), MAX_ASSEMBLY)?;
    let a = open_assembly(&input)?;
    let nb = dotnet::native_boundaries(&a);
    let modules: BTreeSet<&str> = nb.pinvokes.iter().map(|x| x.module.as_str()).collect();
    let summary = format!(
        "{} P/Invoke declarations into {} module(s){}; {} internal calls, {} native-code methods, {} UnmanagedCallersOnly, {} LibraryImport.",
        nb.pinvokes.len(),
        modules.len(),
        if modules.is_empty() { String::new() } else { format!(" ({})", modules.iter().take(8).copied().collect::<Vec<_>>().join(", ")) },
        nb.internal_calls.len(),
        nb.native_code_methods.len(),
        nb.unmanaged_callers_only.len(),
        nb.library_imports.len()
    );
    let mut lims = managed_limitations(&a);
    lims.push(Limitation::new("declared_only", "These are declared boundaries; whether each native function exists is checked by managed_native_calls_verify. Calls through function pointers or NativeLibrary.Load at run time are not listed."));
    let total = nb.pinvokes.len() + nb.internal_calls.len() + nb.native_code_methods.len();
    let ev = builder(ctx, "managed_native_calls_list", input.subject.clone(), json!({"path": input.path}))
        .result(serde_json::to_value(&nb).unwrap_or(Value::Null))
        .summary(summary)
        .confidence(Confidence::Observed)
        .authority(Authority::OriginalFiles)
        .limitations(lims)
        .coverage(Coverage::complete(total as u64))
        .locations(modules.iter().take(32).map(|m| Location::new("module", *m)))
        .build()?;
    Ok(ToolOutput::evidence(ev))
}

// ---------------------------------------------------------------------------------------------
// Compare

#[derive(Debug, Clone)]
struct MRow<'m> {
    m: &'m MethodInfo,
    type_name: &'m str,
    /// Parameters and return type only (no names).
    sig: String,
    hash: Option<&'m str>,
    shape: String,
}

fn rows_of(m: &Members) -> Vec<MRow<'_>> {
    m.types
        .iter()
        .flat_map(|t| {
            t.methods.iter().map(move |x| {
                let sig = format!("({}):{}", x.params.iter().map(|p| p.ty.as_str()).collect::<Vec<_>>().join(", "), x.return_type);
                let hash = x.body.as_ref().map(|b| b.il_shape_hash.as_str()).filter(|h| !h.is_empty());
                let shape = format!("{}|{}|{}|{}", t.full_name, sig, x.body.as_ref().map(|b| b.code_size).unwrap_or(0), x.modifiers.join(","));
                MRow { m: x, type_name: &t.full_name, sig, hash, shape }
            })
        })
        .collect()
}

fn mrow_json(r: &MRow<'_>) -> Value {
    json!({"key": r.m.key, "token": r.m.token, "signature": r.m.signature, "il_shape_hash": r.hash})
}

/// Pair unmatched rows whose `key` is unique on both sides.
fn tier<'m, F: Fn(&MRow<'m>) -> Option<String>>(
    l: &[MRow<'m>],
    r: &[MRow<'m>],
    lu: &mut [bool],
    ru: &mut [bool],
    key: F,
    ambiguous: &mut BTreeSet<String>,
) -> Vec<(usize, usize)> {
    let mut lk: BTreeMap<String, Vec<usize>> = BTreeMap::new();
    let mut rk: BTreeMap<String, Vec<usize>> = BTreeMap::new();
    for (i, x) in l.iter().enumerate() {
        if !lu.get(i).copied().unwrap_or(true)
            && let Some(k) = key(x)
        {
            lk.entry(k).or_default().push(i);
        }
    }
    for (i, x) in r.iter().enumerate() {
        if !ru.get(i).copied().unwrap_or(true)
            && let Some(k) = key(x)
        {
            rk.entry(k).or_default().push(i);
        }
    }
    let mut out = Vec::new();
    for (k, li) in &lk {
        let Some(ri) = rk.get(k) else { continue };
        match (li.as_slice(), ri.as_slice()) {
            ([a], [b]) => {
                if let (Some(x), Some(y)) = (lu.get_mut(*a), ru.get_mut(*b)) {
                    *x = true;
                    *y = true;
                }
                out.push((*a, *b));
            }
            _ => {
                ambiguous.insert(k.clone());
            }
        }
    }
    out
}

fn managed_assemblies_compare(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: CompareParams = parse_params(params)?;
    let max_rows = p.max_rows.clamp(1, 100_000);
    let ls = managed_source(ctx, &p.left, &["managed_members_list"])?;
    ctx.cancel.check()?;
    let rs = managed_source(ctx, &p.right, &["managed_members_list"])?;
    let la = open_assembly(&ls.input)?;
    let ra = open_assembly(&rs.input)?;
    let filter = ls.type_names.clone().or_else(|| rs.type_names.clone());
    let lm = dotnet::members(&la, &member_options(filter.clone(), false, 1_000_000));
    ctx.cancel.check()?;
    let rm = dotnet::members(&ra, &member_options(filter, false, 1_000_000));
    let l = rows_of(&lm);
    let r = rows_of(&rm);
    let mut lu = vec![false; l.len()];
    let mut ru = vec![false; r.len()];
    let mut ambiguous_keys = BTreeSet::new();
    // Tier 1: identical IL and signature (survives renames); tier 2: type + name + signature;
    // tier 3: same structure.
    let t1 = tier(&l, &r, &mut lu, &mut ru, |x| x.hash.map(|h| format!("{}|{h}", x.sig)), &mut ambiguous_keys);
    let t2 = tier(&l, &r, &mut lu, &mut ru, |x| Some(x.m.key.clone()), &mut ambiguous_keys);
    let t3 = tier(&l, &r, &mut lu, &mut ru, |x| x.hash.map(|_| x.shape.clone()), &mut ambiguous_keys);
    let mut unchanged = Vec::new();
    let mut changed = Vec::new();
    let mut renamed = Vec::new();
    let mut push_pair = |a: usize, b: usize, tier: &str| {
        let (Some(x), Some(y)) = (l.get(a), r.get(b)) else { return };
        let same_key = x.m.key == y.m.key;
        let same_body = x.hash == y.hash;
        let row = json!({"left": mrow_json(x), "right": mrow_json(y), "tier": tier});
        if same_key && same_body {
            unchanged.push(row);
        } else if same_key {
            changed.push(row);
        } else {
            renamed.push(
                json!({"left": mrow_json(x), "right": mrow_json(y), "tier": tier, "body_identical": same_body, "moved_type": x.type_name != y.type_name}),
            );
        }
    };
    for (a, b) in t1 {
        push_pair(a, b, "identical-il-and-signature");
    }
    for (a, b) in t2 {
        push_pair(a, b, "type-name-signature");
    }
    for (a, b) in t3 {
        push_pair(a, b, "same-structure");
    }
    let removed: Vec<Value> = l.iter().zip(&lu).filter(|(_, u)| !**u).map(|(x, _)| mrow_json(x)).collect();
    let added: Vec<Value> = r.iter().zip(&ru).filter(|(_, u)| !**u).map(|(x, _)| mrow_json(x)).collect();
    let lt: BTreeSet<&str> = lm.types.iter().map(|t| t.full_name.as_str()).collect();
    let rt: BTreeSet<&str> = rm.types.iter().map(|t| t.full_name.as_str()).collect();
    let fields = |m: &Members| -> BTreeMap<String, String> {
        m.types.iter().flat_map(|t| t.fields.iter().map(move |f| (format!("{}::{}", t.full_name, f.name), f.ty.clone()))).collect()
    };
    let (lf, rf) = (fields(&lm), fields(&rm));
    let field_changes: Vec<Value> = lf
        .iter()
        .filter_map(|(k, v)| match rf.get(k) {
            None => Some(json!({"field": k, "change": "removed", "type": v})),
            Some(w) if w != v => Some(json!({"field": k, "change": "type-changed", "from": v, "to": w})),
            _ => None,
        })
        .chain(rf.iter().filter(|(k, _)| !lf.contains_key(*k)).map(|(k, v)| json!({"field": k, "change": "added", "type": v})))
        .collect();
    let counts = json!({
        "unchanged": unchanged.len(), "changed": changed.len(), "renamed_or_moved": renamed.len(),
        "added": added.len(), "removed": removed.len(), "ambiguous_keys": ambiguous_keys.len(),
        "types_added": rt.difference(&lt).count(), "types_removed": lt.difference(&rt).count(), "field_changes": field_changes.len(),
    });
    let cap = |v: Vec<Value>| v.into_iter().take(max_rows).collect::<Vec<_>>();
    let truncated = [unchanged.len(), changed.len(), renamed.len(), added.len(), removed.len()].iter().any(|n| *n > max_rows);
    let summary = format!(
        "{} → {}: {} methods unchanged, {} changed, {} renamed or moved, {} added, {} removed{}.",
        ls.input.name,
        rs.input.name,
        unchanged.len(),
        changed.len(),
        renamed.len(),
        added.len(),
        removed.len(),
        if ambiguous_keys.is_empty() { String::new() } else { format!(", {} ambiguous", ambiguous_keys.len()) }
    );
    let mut b = builder(
        ctx,
        "managed_assemblies_compare",
        Subject { kind: "managed-pair".into(), sha256: None, name: Some(format!("{} vs {}", ls.input.name, rs.input.name)) },
        json!({"left": ls.input.subject.sha256, "right": rs.input.subject.sha256, "max_rows": max_rows}),
    )
    .result(json!({
        "counts": counts,
        "changed": cap(changed), "renamed_or_moved": cap(renamed), "added": cap(added), "removed": cap(removed),
        "unchanged": cap(unchanged),
        "ambiguous_keys": ambiguous_keys.iter().take(max_rows).collect::<Vec<_>>(),
        "types_added": rt.difference(&lt).take(max_rows).collect::<Vec<_>>(),
        "types_removed": lt.difference(&rt).take(max_rows).collect::<Vec<_>>(),
        "field_changes": field_changes.into_iter().take(max_rows).collect::<Vec<_>>(),
    }))
    .summary(summary)
    .confidence(Confidence::Derived)
    .limitation(Limitation::new(
        "matching_heuristic",
        "Renames are matched only when the IL and signature (or the structure) are unique on both sides; duplicates stay ambiguous and appear as added/removed.",
    ))
    .coverage(Coverage { status: if truncated { CoverageStatus::Partial } else { CoverageStatus::Complete }, examined: Some((l.len() + r.len()) as u64), total: Some((l.len() + r.len()) as u64), next_offset: None });
    if truncated {
        b = b.limitation(Limitation::new("rows_capped", format!("lists are capped at max_rows={max_rows}; counts are complete")));
    }
    for id in [ls.evidence_id, rs.evidence_id].into_iter().flatten() {
        b = b.link(id);
    }
    Ok(ToolOutput::evidence(b.build()?))
}

// ---------------------------------------------------------------------------------------------
// Verify P/Invoke against native exports

struct NativeLib {
    name: String,
    norm: String,
    exports: BTreeSet<String>,
    source: String,
}

/// `libFoo.so.1`, `Foo.dll`, `foo` → `foo`.
fn norm_module(m: &str) -> String {
    let base = m.rsplit(['/', '\\']).next().unwrap_or(m).to_ascii_lowercase();
    let mut s = base.as_str();
    for ext in [".dll", ".exe", ".dylib", ".so"] {
        if let Some(i) = s.find(ext)
            && (s.len() == i + ext.len() || s.get(i + ext.len()..).is_some_and(|r| r.starts_with('.')))
        {
            s = s.get(..i).unwrap_or(s);
            break;
        }
    }
    let s = s.strip_prefix("lib").filter(|r| !r.is_empty()).unwrap_or(s);
    s.to_string()
}

fn native_lib(ctx: &Ctx<'_>, v: &Value) -> Result<NativeLib, ToolError> {
    let from_path = |p: &str| -> Result<NativeLib, ToolError> {
        let input = load_path(p, 2 << 30)?;
        let bin = craft_anything_formats::parse_binary(&input.bytes).map_err(|e| format_err(e, "an ELF, PE or Mach-O library"))?;
        let mut exports: BTreeSet<String> = bin.exports.iter().map(|e| e.name.clone()).collect();
        // Mach-O exports carry a leading underscore.
        if matches!(bin.format, craft_anything_formats::Format::MachO) {
            exports = exports.into_iter().map(|e| e.strip_prefix('_').map(String::from).unwrap_or(e)).collect();
        }
        Ok(NativeLib { norm: norm_module(&input.name), name: input.name, exports, source: p.to_string() })
    };
    if let Some(p) = is_path_input(v) {
        return from_path(p);
    }
    let ev = resolve_evidence_input(ctx, v, &["native_layout_show"])?;
    let name = ev.subject.name.clone().unwrap_or_default();
    match ev.result.get("exports").and_then(Value::as_array) {
        Some(list) => {
            let macho = ev.result.get("format").and_then(Value::as_str).is_some_and(|f| f.to_ascii_lowercase().contains("mach"));
            let exports = list
                .iter()
                .filter_map(|e| e.get("name").and_then(Value::as_str))
                .map(|n| if macho { n.strip_prefix('_').unwrap_or(n).to_string() } else { n.to_string() })
                .collect();
            Ok(NativeLib { norm: norm_module(&name), name, exports, source: ev.id })
        }
        None => match ev.params.get("path").and_then(Value::as_str) {
            Some(p) => from_path(p),
            None => Err(ToolError::invalid(format!("evidence {} has no export list (was it recorded with detail=summary?)", ev.id))
                .with_remediation("Pass the native library's absolute path instead.")),
        },
    }
}

fn managed_native_calls_verify(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: VerifyParams = parse_params(params)?;
    if p.native.is_empty() || p.native.len() > 256 {
        return Err(ToolError::invalid("native must list 1..=256 libraries"));
    }
    let ms = managed_source(ctx, &p.managed, &["managed_native_calls_list"])?;
    let a = open_assembly(&ms.input)?;
    let nb: NativeBoundaries = dotnet::native_boundaries(&a);
    let mut libs = Vec::new();
    for v in &p.native {
        ctx.cancel.check()?;
        libs.push(native_lib(ctx, v)?);
    }
    let mut rows = Vec::new();
    let mut counts: BTreeMap<&'static str, usize> = BTreeMap::new();
    for pi in &nb.pinvokes {
        let want = norm_module(&pi.module);
        let lib = libs.iter().find(|l| l.norm == want);
        let (status, matched, note): (&'static str, Option<String>, String) = match lib {
            _ if pi.module == "__Internal" || pi.module.eq_ignore_ascii_case("QCall") => {
                ("undetermined", None, format!("{} resolves inside the process or runtime, not a separate library", pi.module))
            }
            None => ("undetermined", None, format!("no native library named like {} was supplied", pi.module)),
            Some(l) if l.exports.is_empty() => ("undetermined", None, format!("{} has no export table to check", l.name)),
            Some(l) => {
                let e = &pi.entry_point;
                let mut variants: Vec<String> = Vec::new();
                if !pi.exact_spelling {
                    match pi.charset {
                        "unicode" => variants.push(format!("{e}W")),
                        "auto" => {
                            variants.push(format!("{e}W"));
                            variants.push(format!("{e}A"));
                        }
                        _ => variants.push(format!("{e}A")),
                    }
                }
                let decorated = l.exports.iter().find(|x| {
                    let s = x.strip_prefix('_').unwrap_or(x);
                    s.split_once('@').is_some_and(|(n, d)| n == e && !d.is_empty() && d.bytes().all(|b| b.is_ascii_digit()))
                });
                if l.exports.contains(e) {
                    ("found", Some(e.clone()), format!("exported by {}", l.name))
                } else if let Some(v) = variants.iter().find(|v| l.exports.contains(*v)) {
                    ("found-variant", Some(v.clone()), format!("the runtime also probes {v} for charset {}", pi.charset))
                } else if let Some(d) = decorated {
                    ("found-decorated", Some(d.clone()), "stdcall-decorated name (x86)".into())
                } else if let Some(c) = l.exports.iter().find(|x| x.eq_ignore_ascii_case(e)) {
                    ("case-mismatch", Some(c.clone()), "only a different-case export exists; symbol lookup is case-sensitive".into())
                } else {
                    ("missing", None, format!("{} does not export {e}", l.name))
                }
            }
        };
        *counts.entry(status).or_default() += 1;
        rows.push(json!({
            "method": format!("{}::{}", pi.declaring_type, pi.method), "token": pi.token, "module": pi.module, "entry_point": pi.entry_point,
            "charset": pi.charset, "exact_spelling": pi.exact_spelling, "status": status, "matched_export": matched,
            "library": lib.map(|l| l.name.clone()), "note": note,
        }));
    }
    let supplied: Vec<Value> = libs.iter().map(|l| json!({"name": l.name, "normalized": l.norm, "exports": l.exports.len(), "source": l.source})).collect();
    let missing = counts.get("missing").copied().unwrap_or(0);
    let undetermined = counts.get("undetermined").copied().unwrap_or(0);
    let summary = format!(
        "{} P/Invoke declarations: {} found, {} missing, {} undetermined.",
        nb.pinvokes.len(),
        counts.get("found").copied().unwrap_or(0) + counts.get("found-variant").copied().unwrap_or(0) + counts.get("found-decorated").copied().unwrap_or(0),
        missing,
        undetermined
    );
    let mut b = builder(ctx, "managed_native_calls_verify", ms.input.subject.clone(), json!({"managed": ms.input.subject.sha256, "native": supplied}))
        .result(json!({"counts": counts, "pinvokes": rows, "native_libraries": supplied, "internal_calls": nb.internal_calls.len()}))
        .summary(summary)
        .confidence(Confidence::Derived)
        .limitation(Limitation::new(
            "name_only",
            "Checks that an export with the right name exists; argument types, calling conventions and the library the runtime would actually load at run time are not checked.",
        ))
        .coverage(Coverage { status: if undetermined > 0 { CoverageStatus::Partial } else { CoverageStatus::Complete }, examined: Some(nb.pinvokes.len() as u64), total: Some(nb.pinvokes.len() as u64), next_offset: None });
    if let Some(id) = ms.evidence_id {
        b = b.link(id);
    }
    for v in &p.native {
        if let Some(id) = v.as_str().filter(|s| craft_anything_evidence::is_evidence_id(s)).or_else(|| v.get("evidence_id").and_then(Value::as_str)) {
            b = b.link(id.to_string());
        }
    }
    Ok(ToolOutput::evidence(b.build()?))
}

// ---------------------------------------------------------------------------------------------
// Import a reconstruction

/// (file name, text) pairs and notes about what was skipped.
type Sources = (Vec<(String, String)>, Vec<String>);

fn read_sources(p: &ImportParams, ctx: &Ctx<'_>) -> Result<Sources, ToolError> {
    const MAX_TOTAL: u64 = 64 << 20;
    let mut notes = Vec::new();
    match (&p.source_text, &p.source_path) {
        (Some(t), None) => {
            if t.len() as u64 > MAX_TOTAL {
                return Err(ToolError::new(ErrorCode::OverLimit, "source_text is larger than 64 MiB"));
            }
            Ok((vec![("source_text".into(), t.clone())], notes))
        }
        (None, Some(sp)) => {
            let path = PathBuf::from(sp);
            if !path.is_absolute() {
                return Err(ToolError::invalid(format!("source_path must be absolute, got {sp:?}")));
            }
            let meta = std::fs::metadata(&path).map_err(|e| ToolError::io(sp, e))?;
            if meta.is_file() {
                if meta.len() > MAX_TOTAL {
                    return Err(ToolError::new(ErrorCode::OverLimit, format!("{sp} is larger than 64 MiB")));
                }
                let bytes = std::fs::read(&path).map_err(|e| ToolError::io(sp, e))?;
                return Ok((vec![(sp.clone(), String::from_utf8_lossy(&bytes).into_owned())], notes));
            }
            let skip = |_: &str| false;
            let walked = walk_dir(
                &path,
                &WalkOptions {
                    max_files: p.max_files.clamp(1, 100_000).saturating_mul(4),
                    max_depth: 32,
                    skip_dir: &skip,
                    gitignore: true,
                    include_hidden: false,
                },
                &ctx.cancel,
            )?;
            let mut out = Vec::new();
            let mut total = 0u64;
            for f in walked.files.iter().filter(|f| f.rel.to_ascii_lowercase().ends_with(".cs")) {
                if out.len() >= p.max_files.clamp(1, 100_000) || total.saturating_add(f.size) > MAX_TOTAL {
                    notes.push("file count or size limit reached; some .cs files were not read".into());
                    break;
                }
                match std::fs::read(&f.abs) {
                    Ok(b) => {
                        total += b.len() as u64;
                        out.push((f.rel.clone(), String::from_utf8_lossy(&b).into_owned()));
                    }
                    Err(e) => notes.push(format!("{}: {e}", f.rel)),
                }
            }
            if walked.truncated {
                notes.push("the folder walk stopped at a limit".into());
            }
            if out.is_empty() {
                return Err(ToolError::invalid(format!("no .cs files under {sp}")));
            }
            Ok((out, notes))
        }
        _ => Err(ToolError::invalid("pass exactly one of source_path or source_text")),
    }
}

fn managed_reconstruction_check(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ImportParams = parse_params(params)?;
    let max_rows = p.max_rows.clamp(1, 100_000);
    let ms = managed_source(ctx, &p.members, &["managed_members_list"])?;
    let (sources, notes) = read_sources(&p, ctx)?;
    let a = open_assembly(&ms.input)?;
    let members = dotnet::members(&a, &MemberOptions { type_filter: ms.type_names.clone(), skip_bodies: true, ..MemberOptions::default() });
    let mut scan = csharp::CsScan::default();
    for (i, (name, text)) in sources.iter().enumerate() {
        if i % 32 == 0 {
            ctx.cancel.check()?;
        }
        let s = csharp::scan(text);
        scan.types.extend(s.types);
        scan.members.extend(s.members);
        scan.warnings.extend(s.warnings.into_iter().map(|w| format!("{name}: {w}")));
    }
    let r = csharp::reconcile(&members, &scan);
    let considered = r.matched.len() + r.signature_mismatch.len() + r.missing.len();
    let ratio = if considered == 0 { 0.0 } else { r.matched.len() as f64 / considered as f64 };
    let summary = format!(
        "{} of {considered} declared members match ({:.0}%); {} signature mismatches, {} missing from the source, {} extra in the source; types {} matched, {} missing, {} extra.",
        r.matched.len(),
        ratio * 100.0,
        r.signature_mismatch.len(),
        r.missing.len(),
        r.extra.len(),
        r.matched_types,
        r.missing_types.len(),
        r.extra_types.len()
    );
    let cap = |v: &[csharp::MemberMatch]| serde_json::to_value(v.iter().take(max_rows).collect::<Vec<_>>()).unwrap_or(Value::Null);
    let mut lims = vec![
        Limitation::new("declarations_only", "Only declarations are compared; method bodies are not checked, so a match says nothing about behaviour."),
        Limitation::new(
            "lightweight_parser",
            "The C# scanner reads declarations without a full parse; unusual syntax, macros-like source generators or partial types split oddly may be missed.",
        ),
    ];
    lims.extend(notes.iter().map(|n| Limitation::new("source_read", n.clone())));
    lims.extend(scan.warnings.iter().take(20).map(|w| Limitation::new("source_scan", w.clone())));
    let mut b = builder(
        ctx,
        "managed_reconstruction_check",
        ms.input.subject.clone(),
        json!({"members": ms.input.subject.sha256, "source_path": p.source_path, "source_files": sources.len(), "max_rows": max_rows}),
    )
    .result(json!({
        "counts": {
            "matched": r.matched.len(), "signature_mismatch": r.signature_mismatch.len(), "missing": r.missing.len(), "extra": r.extra.len(),
            "implicit": r.implicit.len(), "matched_types": r.matched_types, "missing_types": r.missing_types.len(), "extra_types": r.extra_types.len(),
        },
        "declaration_match_ratio": ratio,
        "signature_mismatch": cap(&r.signature_mismatch),
        "missing": cap(&r.missing),
        "extra": cap(&r.extra),
        "implicit": cap(&r.implicit),
        "matched": cap(&r.matched),
        "missing_types": r.missing_types.iter().take(max_rows).collect::<Vec<_>>(),
        "extra_types": r.extra_types.iter().take(max_rows).collect::<Vec<_>>(),
        "source_files": sources.iter().map(|(n, _)| n.as_str()).take(max_rows).collect::<Vec<_>>(),
    }))
    .summary(summary)
    .confidence(Confidence::Derived)
    .authority(Authority::Reasoning)
    .limitations(lims)
    .coverage(Coverage::complete(considered as u64));
    if let Some(id) = ms.evidence_id {
        b = b.link(id);
    }
    Ok(ToolOutput::evidence(b.build()?))
}

// ---------------------------------------------------------------------------------------------
// Application graph

struct Graph {
    nodes: Vec<Value>,
    ids: BTreeSet<String>,
    edges: Vec<Value>,
    max: usize,
    truncated: bool,
}

impl Graph {
    fn node(&mut self, id: String, kind: &str, label: String, extra: Value) -> bool {
        if self.ids.contains(&id) {
            return true;
        }
        if self.nodes.len() >= self.max {
            self.truncated = true;
            return false;
        }
        let mut n = json!({"id": id, "kind": kind, "label": label});
        if let (Value::Object(m), Value::Object(x)) = (&mut n, extra) {
            m.extend(x);
        }
        self.ids.insert(id);
        self.nodes.push(n);
        true
    }

    fn edge(&mut self, from: &str, to: &str, kind: &str) {
        if self.ids.contains(from) && self.ids.contains(to) && self.edges.len() < self.max.saturating_mul(8) {
            self.edges.push(json!({"from": from, "to": to, "kind": kind}));
        } else if self.edges.len() >= self.max.saturating_mul(8) {
            self.truncated = true;
        }
    }
}

fn managed_app_graph_build(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: GraphParams = parse_params(params)?;
    let max_nodes = p.max_nodes.clamp(10, 20_000);
    let src = match &p.input {
        Some(v) => managed_source(ctx, v, MANAGED_OPS)?,
        None => ManagedSource { input: load(ctx, None, MAX_ASSEMBLY)?, evidence_id: None, type_names: None },
    };
    let a = open_assembly(&src.input)?;
    let inv = dotnet::inventory(&a);
    let members = dotnet::members(&a, &member_options(src.type_names.clone(), false, 1_000_000));
    let nb = dotnet::native_boundaries(&a);
    let name = inv.assembly.as_ref().map(|x| x.name.clone()).unwrap_or_else(|| src.input.name.clone());
    let root = format!("app:{name}");
    let mut g = Graph { nodes: Vec::new(), ids: BTreeSet::new(), edges: Vec::new(), max: max_nodes, truncated: false };
    g.node(root.clone(), "application", name.clone(), json!({"dotnet_family": inv.classification.dotnet_family, "target_frameworks": inv.target_frameworks}));
    for r in &inv.assembly_refs {
        let id = format!("assembly-ref:{}", r.name);
        if g.node(id.clone(), "assembly-ref", format!("{} {}", r.name, r.version), json!({})) {
            g.edge(&root, &id, "references");
        }
    }
    for r in &inv.manifest_resources {
        let id = format!("resource:{}", r.name);
        if g.node(id.clone(), "resource", r.name.clone(), json!({"implementation": r.implementation})) {
            g.edge(&root, &id, "contains");
        }
    }
    for m in &nb.module_refs {
        let id = format!("native-module:{m}");
        if g.node(id.clone(), "native-module", m.clone(), json!({})) {
            g.edge(&root, &id, "references");
        }
    }
    // Types and methods first, then edges between them.
    let mut method_ids: BTreeMap<&str, String> = BTreeMap::new();
    for t in members.types.iter().filter(|t| t.kind != "module" || !t.methods.is_empty()) {
        let tid = format!("type:{}", t.full_name);
        if !g.node(tid.clone(), "type", t.full_name.clone(), json!({"type_kind": t.kind, "visibility": t.visibility})) {
            break;
        }
        g.edge(&root, &tid, "contains");
        for m in &t.methods {
            let mid = format!("method:{}", m.token);
            if !g.node(mid.clone(), "method", format!("{}::{}", t.full_name, m.name), json!({"signature": m.signature, "pinvoke": m.pinvoke})) {
                break;
            }
            g.edge(&tid, &mid, "contains");
            method_ids.insert(m.token.as_str(), mid);
        }
    }
    for t in &members.types {
        let tid = format!("type:{}", t.full_name);
        if let Some(base) = &t.extends {
            let bid = format!("type:{base}");
            if g.ids.contains(&bid) {
                g.edge(&tid, &bid, "inherits");
            }
        }
        for m in &t.methods {
            let Some(mid) = method_ids.get(m.token.as_str()).cloned() else { continue };
            for c in m.body.iter().flat_map(|b| b.calls.iter()) {
                let target = match method_ids.get(c.token.as_str()) {
                    Some(id) => id.clone(),
                    None => {
                        let id = format!("external:{}", c.target);
                        if !g.node(id.clone(), "external-member", c.target.clone(), json!({})) {
                            continue;
                        }
                        id
                    }
                };
                g.edge(&mid, &target, "calls");
            }
        }
    }
    for pi in &nb.pinvokes {
        if let Some(mid) = method_ids.get(pi.token.as_str()).cloned() {
            g.edge(&mid, &format!("native-module:{}", pi.module), "pinvoke");
        }
    }
    let mut kinds: BTreeMap<String, usize> = BTreeMap::new();
    for n in &g.nodes {
        *kinds.entry(n["kind"].as_str().unwrap_or("?").to_string()).or_default() += 1;
    }
    let node_count = g.nodes.len();
    let summary = format!(
        "{name}: {} nodes ({}) and {} edges{}.",
        g.nodes.len(),
        kinds.iter().map(|(k, v)| format!("{v} {k}")).collect::<Vec<_>>().join(", "),
        g.edges.len(),
        if g.truncated { "; cut short at max_nodes" } else { "" }
    );
    let mut b = builder(ctx, "managed_app_graph_build", src.input.subject.clone(), json!({"path": src.input.path, "max_nodes": max_nodes}))
        .result(json!({"platform": "dotnet", "recognised": true, "graph": {"nodes": g.nodes, "edges": g.edges}, "counts": kinds, "truncated": g.truncated}))
        .summary(summary)
        .confidence(Confidence::Derived)
        .limitation(Limitation::new("static_calls", "Call edges come from IL call tokens; virtual dispatch, delegates and reflection are not resolved."))
        .coverage(if g.truncated { super::static_input::partial(node_count as u64) } else { Coverage::complete(node_count as u64) });
    if g.truncated {
        b = b.limitation(Limitation::new("truncated", format!("the graph stops at max_nodes={max_nodes}")));
    }
    if let Some(id) = src.evidence_id {
        b = b.link(id);
    }
    Ok(ToolOutput::evidence(b.build()?))
}

#[cfg(test)]
mod tests {
    use super::super::native_common::test_support::{call, call_err, engine_with};
    use crate::Engine;
    use craft_anything_testkit::managed as fx;
    use serde_json::{Value, json};

    fn retained(v: &Value) -> Value {
        json!({"kind": "saved", "evidence_id": v["id"]})
    }

    #[test]
    fn static_tools_on_the_active_target() {
        let e = engine_with("Sample.dll", &fx::managed_assembly(1));
        let inv = call(&e, "managed_assembly_show", json!({}));
        assert_eq!(inv["result"]["assembly"]["name"], "Sample");
        assert_eq!(inv["result"]["classification"]["dotnet_family"], "dotnet-core");
        assert!(inv["summary"].as_str().unwrap().contains("targets .NETCoreApp,Version=v8.0"), "{}", inv["summary"]);
        let m = call(&e, "managed_members_list", json!({"limit": 2, "include_il": true}));
        assert_eq!(m["result"]["total_types"], 4);
        assert_eq!(m["result"]["types"].as_array().unwrap().len(), 2);
        assert_eq!(m["coverage"]["next_offset"], 2);
        let calc = &m["result"]["types"][1];
        assert_eq!(calc["full_name"], "Sample.Calculator");
        assert_eq!(calc["methods"][0]["signature"], "public int Add(int a, int b)");
        assert!(calc["methods"][0]["body"]["il"].is_array());
        let f = call(&e, "managed_members_list", json!({"type_names": ["Sample.NativeMethods"]}));
        assert_eq!(f["result"]["total_types"], 1);
        let err = call_err(&e, "managed_members_list", json!({"type_names": ["Nope"]}));
        assert_eq!(err.code, craft_anything_evidence::ErrorCode::BadInput);
        let nb = call(&e, "managed_native_calls_list", json!({}));
        assert_eq!(nb["result"]["pinvokes"].as_array().unwrap().len(), 2);
        assert_eq!(nb["result"]["internal_calls"][0]["method"], "GetTicks");
    }

    #[test]
    fn non_managed_input_is_a_clear_error() {
        let e = engine_with("prog.exe", &craft_anything_testkit::pe64());
        let err = call_err(&e, "managed_assembly_show", json!({}));
        assert!(err.message.contains(".NET"), "{}", err.message);
        let p = craft_anything_testkit::temp_file("junk.dll", b"MZjunk");
        assert!(call_err(&Engine::new(crate::testing::session()), "managed_members_list", json!({"path": p})).remediation.is_some());
    }

    #[test]
    fn compare_two_builds() {
        let e = Engine::new(crate::testing::session());
        let p1 = craft_anything_testkit::temp_file("v1.dll", &fx::managed_assembly(1));
        let p2 = craft_anything_testkit::temp_file("v2.dll", &fx::managed_assembly(2));
        let m1 = call(&e, "managed_members_list", json!({"path": p1}));
        let d = call(&e, "managed_assemblies_compare", json!({"left": retained(&m1), "right": p2}));
        let c = &d["result"]["counts"];
        assert_eq!(c["changed"], 1, "{}", d["result"]);
        assert_eq!(c["added"], 1);
        assert_eq!(c["removed"], 1);
        assert_eq!(d["result"]["changed"][0]["left"]["key"], "Sample.Calculator::Add(int, int):int");
        assert_eq!(d["result"]["added"][0]["key"], "Sample.Calculator::Multiply(int, int):int");
        assert_eq!(d["result"]["removed"][0]["key"], "Sample.NativeMethods::MissingFn():void");
        assert!(d["links"].as_array().unwrap().iter().any(|l| l == &m1["id"]));
        // A changed file behind retained evidence is refused.
        std::fs::write(&p1, fx::managed_assembly(2)).unwrap();
        let err = call_err(&e, "managed_assemblies_compare", json!({"left": retained(&m1), "right": p2}));
        assert_eq!(err.code, craft_anything_evidence::ErrorCode::FileChanged);
    }

    #[test]
    fn verify_pinvokes_against_a_native_library() {
        let e = Engine::new(crate::testing::session());
        let asm = craft_anything_testkit::temp_file("Sample.dll", &fx::managed_assembly(1));
        // The native export library is named like the P/Invoke module.
        let lib = craft_anything_testkit::temp_file("craft.dll", &craft_anything_testkit::pe64());
        let nb = call(&e, "managed_native_calls_list", json!({"path": asm}));
        let layout = call(&e, "native_layout_show", json!({"path": lib}));
        let v = call(&e, "managed_native_calls_verify", json!({"managed": retained(&nb), "native": [retained(&layout)]}));
        let rows = v["result"]["pinvokes"].as_array().unwrap();
        assert_eq!(rows[0]["status"], "found", "{}", v["result"]);
        assert_eq!(rows[1]["status"], "missing");
        let v2 = call(
            &e,
            "managed_native_calls_verify",
            json!({"managed": asm, "native": [craft_anything_testkit::temp_file("other.dll", &craft_anything_testkit::pe64())]}),
        );
        assert_eq!(v2["result"]["counts"]["undetermined"], 2);
        assert_eq!(super::norm_module("libcraft.so.1"), "craft");
        assert_eq!(super::norm_module("C:\\x\\Craft.DLL"), "craft");
        assert_eq!(super::norm_module("lib"), "lib");
    }

    #[test]
    fn reconstruction_and_graph() {
        let e = Engine::new(crate::testing::session());
        let asm = craft_anything_testkit::temp_file("Sample.dll", &fx::managed_assembly(1));
        let m = call(&e, "managed_members_list", json!({"path": asm}));
        let r = call(&e, "managed_reconstruction_check", json!({"members": retained(&m), "source_text": fx::RECONSTRUCTION_CS}));
        assert_eq!(r["result"]["counts"]["signature_mismatch"], 1, "{}", r["result"]);
        assert_eq!(r["result"]["counts"]["extra"], 1);
        assert_eq!(r["result"]["counts"]["missing"], 0);
        let dir = tempfile::tempdir().unwrap();
        std::fs::create_dir_all(dir.path().join("src")).unwrap();
        std::fs::write(dir.path().join("src/Calc.cs"), fx::RECONSTRUCTION_CS).unwrap();
        let r2 = call(&e, "managed_reconstruction_check", json!({"members": asm, "source_path": dir.path()}));
        assert_eq!(r2["result"]["counts"], r["result"]["counts"]);
        assert!(call_err(&e, "managed_reconstruction_check", json!({"members": asm})).message.contains("exactly one"));
        let g = call(&e, "managed_app_graph_build", json!({"input": retained(&m)}));
        let edges = g["result"]["graph"]["edges"].as_array().unwrap();
        assert!(edges.iter().any(|x| x["kind"] == "pinvoke" && x["to"] == "native-module:craft"));
        assert!(edges.iter().any(|x| x["kind"] == "calls" && x["to"] == "external:System.Console::WriteLine(string)"));
        assert!(edges.iter().any(|x| x["kind"] == "calls" && x["to"] == "method:0x06000001"));
        let small = call(&e, "managed_app_graph_build", json!({"input": asm, "max_nodes": 10}));
        assert_eq!(small["result"]["truncated"], true);
    }
}
