//! Shared plumbing for the native-code tools: loading and caching the built-in engine's
//! analysis per target, resolving functions and addresses, names with user annotations on top,
//! paging, and evidence assembly.

use crate::session::{OpenTarget, Session};
use crate::target::{Target, TargetKind};
use crate::tool::{CancelToken, Ctx, Progress, ProgressFn, ToolOutput};
use craft_anything_analysis::native::Report;
use craft_anything_disasm::{Control, DisasmError, Function, Image, Limits, Program};
use craft_anything_evidence::{Coverage, ErrorCode, EvidenceBuilder, ToolError};
use craft_anything_formats::Arch;
use serde_json::Value;
use std::collections::BTreeMap;
use std::sync::Arc;

/// Default page size for big lists.
pub const DEFAULT_LIMIT: usize = 200;
pub const MAX_LIMIT: usize = 5000;

/// The parsed image and its whole-program analysis, cached on the target.
pub struct NativeState {
    pub img: Arc<Image>,
    pub prog: Program,
}

/// Just the parsed image (cheap; used by tools that don't need the full analysis).
pub struct NativeImage(pub Arc<Image>);

/// A tool call's cancel token and progress, as the native engine asks for them.
pub struct CtxControl<'a> {
    cancel: CancelToken,
    progress: &'a ProgressFn,
}

impl<'a> CtxControl<'a> {
    pub fn of(ctx: &Ctx<'a>) -> Self {
        CtxControl { cancel: ctx.cancel.clone(), progress: ctx.progress }
    }
}

impl Control for CtxControl<'_> {
    fn cancelled(&self) -> bool {
        self.cancel.is_cancelled()
    }

    fn progress(&self, fraction: f32, message: &str) {
        (self.progress)(Progress { fraction: Some(fraction), message: message.to_string() });
    }
}

pub fn disasm_err(e: DisasmError) -> ToolError {
    match e {
        DisasmError::Cancelled => ToolError::cancelled(),
        DisasmError::Unsupported(m) => ToolError::unsupported(m).with_remediation("Run triage to see which tools fit this file."),
        DisasmError::Format(f) => ToolError::new(ErrorCode::NotSupported, format!("Couldn't read this as a program: {f}"))
            .with_remediation("Check that the file is a complete ELF, PE, Mach-O or DOS program; run triage for other kinds of file."),
    }
}

/// Build an image for a target of any native kind.
pub fn image_for(t: &Target) -> Result<Image, ToolError> {
    match t.kind {
        TargetKind::Elf | TargetKind::Pe | TargetKind::MachO | TargetKind::MachOFat | TargetKind::Managed | TargetKind::Unknown => {
            Image::parse(t.bytes.clone()).map_err(disasm_err)
        }
        TargetKind::DosCom => Image::dos_com(t.bytes.clone()).map_err(disasm_err),
        TargetKind::RawBinary => {
            let raw = t.raw.as_ref().ok_or_else(|| ToolError::invalid("raw binary without an architecture"))?;
            let arch = Arch::from_name(&raw.architecture).ok_or_else(|| ToolError::invalid(format!("unknown architecture {}", raw.architecture)))?;
            Ok(Image::raw(t.bytes.clone(), arch, raw.entry_point))
        }
        other => Err(ToolError::unsupported(format!("{} is not native machine code.", other.plain()))
            .with_remediation("Run triage to see which tools fit this kind of file.")),
    }
}

/// Use `document` (a target id) as the active target when given.
pub fn select_document(ctx: &mut Ctx<'_>, document: &Option<String>) -> Result<(), ToolError> {
    if let Some(d) = document {
        let id = ctx.session.targets().find(|t| t.target.id == *d || t.target.name == *d).map(|t| t.target.id.clone());
        match id {
            Some(id) => ctx.session.set_active(&id)?,
            None => {
                return Err(ToolError::new(ErrorCode::NotFound, format!("No open document {d}")).with_remediation("List them with native_open_documents_list."));
            }
        }
    }
    Ok(())
}

/// The parsed image of the active target (cached).
pub fn image(ctx: &mut Ctx<'_>) -> Result<Arc<NativeImage>, ToolError> {
    let t = ctx.session.active_mut()?;
    if let Some(s) = t.ext.get::<NativeState>() {
        return Ok(Arc::new(NativeImage(s.img.clone())));
    }
    if let Some(i) = t.ext.get::<NativeImage>() {
        return Ok(i);
    }
    let img = Arc::new(NativeImage(Arc::new(image_for(&t.target)?)));
    t.ext.insert(img.clone());
    Ok(img)
}

/// The full analysis of the active target, running it the first time (cancellable, with
/// progress).
pub fn native(ctx: &mut Ctx<'_>) -> Result<Arc<NativeState>, ToolError> {
    if let Some(s) = ctx.session.active()?.ext.get::<NativeState>() {
        return Ok(s);
    }
    let img = image(ctx)?.0.clone();
    let control = CtxControl { cancel: ctx.cancel.clone(), progress: ctx.progress };
    ctx.report(Some(0.0), "analysing the program (first time only)");
    let prog = Program::analyze(&img, &Limits::default(), &control).map_err(disasm_err)?;
    let state = Arc::new(NativeState { img, prog });
    ctx.session.active_mut()?.ext.insert(state.clone());
    Ok(state)
}

/// User names first, then the engine's.
pub fn name_of(t: &OpenTarget, prog: &Program, a: u64) -> Option<String> {
    t.annotations.names.get(&a).cloned().or_else(|| prog.name_at(a))
}

/// A function by name (user or engine), entry address, or any address inside it.
pub fn resolve_function<'a>(t: &OpenTarget, prog: &'a Program, s: &str) -> Result<&'a Function, ToolError> {
    let s = s.trim();
    if s.is_empty() {
        return Err(ToolError::invalid("function is empty"));
    }
    if let Some((a, _)) = t.annotations.names.iter().find(|(_, n)| n.as_str() == s)
        && let Some(f) = prog.functions.get(a)
    {
        return Ok(f);
    }
    if let Some(f) = prog.function_by_name(s) {
        return Ok(f);
    }
    if let Ok(a) = super::parse_address(s)
        && let Some(f) = prog.functions.get(&a).or_else(|| prog.function_containing(a))
    {
        return Ok(f);
    }
    Err(ToolError::invalid(format!("No function named or at {s}"))
        .with_remediation("Find it with native_functions_search or native_functions_list; pass a name or a 0x address.")
        .with_details(serde_json::json!({"reason": "function_not_found", "function": s})))
}

/// The address param, or the cursor when omitted.
pub fn address_or_cursor(session: &Session, a: &Option<String>) -> Result<u64, ToolError> {
    match a {
        Some(a) => super::parse_address(a),
        None => session.active()?.cursor.address.ok_or_else(|| {
            ToolError::invalid("No address given and the cursor isn't set.").with_remediation("Pass address, or move the cursor with native_cursor_goto.")
        }),
    }
}

/// A page of a list, with honest coverage.
pub fn page<T: serde::Serialize>(items: &[T], offset: usize, limit: usize) -> (Vec<Value>, Coverage) {
    let limit = limit.clamp(1, MAX_LIMIT);
    let total = items.len();
    let slice: Vec<Value> = items.iter().skip(offset).take(limit).map(|x| serde_json::to_value(x).unwrap_or(Value::Null)).collect();
    let cov = Coverage::page(slice.len() as u64, total as u64, offset as u64);
    (slice, cov)
}

/// Start an evidence record about the active target.
pub fn ev(ctx: &Ctx<'_>, op: &str, params: Value) -> Result<EvidenceBuilder, ToolError> {
    Ok(super::evidence_for_active(ctx.session, op)?.params(params))
}

/// Build evidence from an analysis report (without wrapping it), for the summary-first helper.
pub fn report_evidence(ctx: &Ctx<'_>, op: &str, params: Value, r: Report) -> Result<craft_anything_evidence::Evidence, ToolError> {
    report_evidence_with(ctx, op, params, r, Coverage::complete(1))
}

/// [`report_evidence`] with an explicit coverage.
pub fn report_evidence_with(ctx: &Ctx<'_>, op: &str, params: Value, r: Report, cov: Coverage) -> Result<craft_anything_evidence::Evidence, ToolError> {
    ev(ctx, op, params)?.result(r.result).summary(r.summary).confidence(r.confidence).limitations(r.limitations).locations(r.locations).coverage(cov).build()
}

/// `cov`, downgraded to partial when function discovery hit a cap (the list it pages is incomplete).
pub fn program_coverage(prog: &craft_anything_disasm::Program, mut cov: Coverage) -> Coverage {
    if prog.discovery_capped() {
        cov.status = craft_anything_evidence::CoverageStatus::Partial;
    }
    cov
}

/// Turn an analysis report into evidence.
pub fn from_report(ctx: &Ctx<'_>, op: &str, params: Value, r: Report) -> Result<ToolOutput, ToolError> {
    Ok(ToolOutput::evidence(report_evidence(ctx, op, params, r)?))
}

/// Lengths of the top-level array facets in a result, as `{"counts": {...}}`, for summary bodies.
pub fn counts_of(result: &Value) -> Value {
    let mut counts = serde_json::Map::new();
    if let Value::Object(m) = result {
        for (k, v) in m {
            if let Value::Array(a) = v {
                counts.insert(k.clone(), Value::from(a.len()));
            }
        }
    }
    serde_json::json!({"counts": Value::Object(counts)})
}

/// Params as JSON for the evidence record (minus `document`, a selector, and `detail`, a
/// presentation choice — so the same analysis has one id whether summary or complete was asked).
pub fn params_json<T: serde::Serialize>(p: &T) -> Value {
    let mut v = serde_json::to_value(p).unwrap_or(Value::Null);
    if let Value::Object(m) = &mut v {
        m.remove("document");
        m.remove("detail");
    }
    v
}

pub fn hex(a: u64) -> String {
    format!("{a:#x}")
}

/// Names map for analysis closures.
pub fn user_names(t: &OpenTarget) -> BTreeMap<u64, String> {
    t.annotations.names.clone()
}

/// Shorthand for a native tool spec.
#[allow(clippy::too_many_arguments)]
pub fn spec(
    id: &'static str,
    title: &'static str,
    summary: &'static str,
    beginner: &'static str,
    toolset: crate::tool::Toolset,
    effects: crate::tool::Effects,
    requires: crate::tool::Requires,
    input_schema: fn() -> Value,
    run: crate::tool::ToolFn,
) -> crate::tool::ToolSpec {
    crate::tool::ToolSpec { id, title, summary, beginner, toolset, effects, requires, input_schema, run }
}

#[cfg(test)]
pub mod test_support {
    use crate::{CallOptions, Caller, Engine, ToolOutput};
    use serde_json::{Value, json};

    /// An engine with `bytes` opened as the active target.
    pub fn engine_with(name: &str, bytes: &[u8]) -> Engine {
        let e = Engine::new(crate::testing::session());
        let p = craft_anything_testkit::temp_file(name, bytes);
        e.call("core_target_open", json!({"path": p.to_string_lossy()}), CallOptions::new(Caller::Cli)).unwrap();
        e
    }

    pub fn call(e: &Engine, id: &str, params: Value) -> Value {
        match e.call(id, params, CallOptions::new(Caller::Mcp)) {
            Ok(ToolOutput::Evidence(ev)) => {
                assert!(ev.verify());
                serde_json::to_value(&*ev).unwrap()
            }
            Ok(ToolOutput::Value(v)) => json!({"result": v}),
            Err(err) => panic!("{id} failed: {err:?}"),
        }
    }

    pub fn call_err(e: &Engine, id: &str, params: Value) -> craft_anything_evidence::ToolError {
        match e.call(id, params, CallOptions::new(Caller::Mcp)) {
            Ok(v) => panic!("{id} should fail, got {v:?}"),
            Err(err) => err,
        }
    }
}
