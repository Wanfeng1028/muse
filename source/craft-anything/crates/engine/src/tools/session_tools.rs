//! Session lifecycle, evidence bundles and unknowns.

use crate::project::write_atomic;
use crate::target::{RawSpec, Target, TargetKind};
use crate::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, empty_schema, parse_params, schema_of};
use craft_anything_evidence::{ErrorCode, Evidence, Severity, ToolError, Unknown, UnknownStatus};
use schemars::JsonSchema;
use serde::Deserialize;
use serde_json::{Value, json};
use std::path::PathBuf;

/// The session tool's id: every MCP server lists it, so `doctor` looks for it.
pub const SESSION_TOOL: &str = "core_session_show";

pub fn specs() -> Vec<ToolSpec> {
    vec![
        ToolSpec {
            id: "core_target_open",
            title: "Open",
            summary: "Open a file, app bundle or folder as the active target. Detects what it is from its contents. For raw machine code pass format=raw-binary with architecture and entry_point.",
            beginner: "Open a program, app or file so we can look inside it.",
            toolset: Toolset::Core,
            effects: Effects::MUTATES_SESSION,
            requires: Requires::Nothing,
            input_schema: schema_of::<OpenParams>,
            run: core_target_open,
        },
        ToolSpec {
            id: "core_target_close",
            title: "Close",
            summary: "Close the active target (or the one named). Evidence stays in the project.",
            beginner: "Close what you're looking at. Your findings are kept.",
            toolset: Toolset::Core,
            effects: Effects::MUTATES_SESSION,
            requires: Requires::Target,
            input_schema: schema_of::<CloseParams>,
            run: core_target_close,
        },
        ToolSpec {
            id: SESSION_TOOL,
            title: "Session status",
            summary: "What's open, which target is active, Clean room or Deep mode, evidence and unknown counts, version.",
            beginner: "See what's open and how the analysis is set up.",
            toolset: Toolset::Core,
            effects: Effects::READ_ONLY,
            requires: Requires::Nothing,
            input_schema: empty_schema,
            run: core_session_show,
        },
        ToolSpec {
            id: "core_targets_list",
            title: "List open targets",
            summary: "Every open target with its id, kind and sha256.",
            beginner: "See everything you have open.",
            toolset: Toolset::Core,
            effects: Effects::READ_ONLY,
            requires: Requires::Nothing,
            input_schema: empty_schema,
            run: core_targets_list,
        },
        ToolSpec {
            id: "core_target_select",
            title: "Switch target",
            summary: "Make another open target the active one.",
            beginner: "Switch to another thing you have open.",
            toolset: Toolset::Core,
            effects: Effects::MUTATES_SESSION.union(Effects::IDEMPOTENT),
            requires: Requires::Nothing,
            input_schema: schema_of::<SelectParams>,
            run: core_target_select,
        },
        ToolSpec {
            id: "native_cursor_show",
            title: "Where am I",
            summary: "The current cursor address in the active target.",
            beginner: "Where you are in the program right now.",
            toolset: Toolset::Native,
            effects: Effects::READ_ONLY,
            requires: Requires::Target,
            input_schema: empty_schema,
            run: native_cursor_show,
        },
        ToolSpec {
            id: "core_evidence_show",
            title: "Evidence so far",
            summary: "All evidence recorded in this session (detail=summary for a compact list; filter by operation or evidence_id).",
            beginner: "Everything we've found so far, with the proof.",
            toolset: Toolset::Core,
            effects: Effects::READ_ONLY,
            requires: Requires::Nothing,
            input_schema: schema_of::<BundleParams>,
            run: core_evidence_show,
        },
        ToolSpec {
            id: "core_evidence_export",
            title: "Export evidence",
            summary: "Write every evidence record and unknown to a JSON bundle file.",
            beginner: "Save your findings to a file you can share.",
            toolset: Toolset::Core,
            effects: Effects::WRITES_FILESYSTEM.union(Effects::MAY_DISCARD_DATA),
            requires: Requires::Nothing,
            input_schema: schema_of::<ExportParams>,
            run: core_evidence_export,
        },
        ToolSpec {
            id: "core_evidence_import",
            title: "Import evidence",
            summary: "Load a bundle written by core_evidence_export. Tampered records are rejected.",
            beginner: "Load findings someone saved.",
            toolset: Toolset::Core,
            effects: Effects::MUTATES_SESSION,
            requires: Requires::Nothing,
            input_schema: schema_of::<ImportParams>,
            run: core_evidence_import,
        },
        ToolSpec {
            id: "core_unknowns_show",
            title: "Open questions",
            summary: "Recorded unknowns, filtered by status, severity or domain.",
            beginner: "Questions we haven't answered yet.",
            toolset: Toolset::Core,
            effects: Effects::READ_ONLY,
            requires: Requires::Nothing,
            input_schema: schema_of::<ListUnknownsParams>,
            run: core_unknowns_show,
        },
        ToolSpec {
            id: "core_unknown_add",
            title: "Record an open question",
            summary: "Record something not yet known, with what would settle it.",
            beginner: "Write down a question we still need to answer.",
            toolset: Toolset::Core,
            effects: Effects::MUTATES_SESSION,
            requires: Requires::Nothing,
            input_schema: schema_of::<RecordUnknownParams>,
            run: core_unknown_add,
        },
        ToolSpec {
            id: "core_unknown_edit",
            title: "Update an open question",
            summary: "Change an unknown's status, evidence or resolution. Pass based_on_revision; a stale revision gives stale_revision.",
            beginner: "Mark a question as answered (or still stuck).",
            toolset: Toolset::Core,
            effects: Effects::MUTATES_SESSION,
            requires: Requires::Nothing,
            input_schema: schema_of::<UpdateUnknownParams>,
            run: core_unknown_edit,
        },
        ToolSpec {
            id: "core_unknown_verify",
            title: "Check an answer",
            summary: "Check that a resolved unknown has a resolution and cites evidence that exists and is intact.",
            beginner: "Check that an answered question really has proof.",
            toolset: Toolset::Core,
            effects: Effects::READ_ONLY,
            requires: Requires::Nothing,
            input_schema: schema_of::<UnknownIdParams>,
            run: core_unknown_verify,
        },
    ]
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct OpenParams {
    /// Absolute path to a file, app bundle or folder.
    pub path: String,
    /// Force a format: `raw-binary` or `dos-com`.
    #[serde(default)]
    pub format: Option<String>,
    /// Required with raw-binary: x86, x86_64, arm, arm64.
    #[serde(default)]
    pub architecture: Option<String>,
    /// Required with raw-binary: load/entry address (0x-hex).
    #[serde(default)]
    pub entry_point: Option<String>,
    /// Optional Deep-mode processor pin: a Ghidra language id such as `RISCV:LE:64:RV64GC`,
    /// `PowerPC:BE:32:default`, `6502:LE:16:default`, `MIPS:BE:32:default` or `ARM:LE:32:v7`.
    /// Takes effect only in Deep mode (Ghidra); it lets Deep target processors the built-in
    /// clean-room engine doesn't cover, and overrides the `ghidra.language_id` setting for this
    /// target. Ignored in Clean room.
    #[serde(default)]
    pub language_id: Option<String>,
}

fn core_target_open(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: OpenParams = parse_params(params)?;
    let path = PathBuf::from(&p.path);
    if !path.is_absolute() {
        return Err(ToolError::invalid(format!("{} is not an absolute path", p.path))
            .with_remediation("Pass the full path, e.g. /Users/me/Downloads/app.exe or C:\\Apps\\app.exe."));
    }
    let mut target = Target::load(&path)?;
    match p.format.as_deref() {
        None => {}
        Some("raw-binary") => {
            let architecture = p.architecture.ok_or_else(|| ToolError::invalid("raw-binary needs architecture"))?;
            if !["x86", "x86_64", "arm", "arm64"].contains(&architecture.as_str()) {
                return Err(ToolError::invalid(format!("unsupported architecture {architecture}")));
            }
            let entry = p.entry_point.as_deref().ok_or_else(|| ToolError::invalid("raw-binary needs entry_point"))?;
            target.kind = TargetKind::RawBinary;
            target.raw = Some(RawSpec { architecture, entry_point: super::parse_address(entry)? });
        }
        Some("dos-com") => target.kind = TargetKind::DosCom,
        Some(other) => return Err(ToolError::invalid(format!("unknown format {other}; use raw-binary or dos-com"))),
    }
    // Opening the same content twice keeps one target per sha256; new raw-binary settings replace
    // it (and what was worked out with the old ones), rather than being dropped (#305).
    let existing = ctx
        .session
        .targets()
        .find(|t| t.target.sha256 == target.sha256 && t.target.kind == target.kind && t.target.raw == target.raw)
        .map(|t| t.target.id.clone());
    if let Some(existing) = existing {
        ctx.session.set_active(&existing)?;
    } else {
        ctx.session.add_target(target.clone());
    }
    // Record an optional Deep-mode language pin on the active target (used only in Deep mode).
    if let Some(lang) = p.language_id.map(|s| s.trim().to_string()).filter(|s| !s.is_empty())
        && let Ok(t) = ctx.session.active_mut()
    {
        t.ext.insert(std::sync::Arc::new(super::deep::LanguageOverride(lang)));
    }
    let t = ctx.session.active()?;
    Ok(ToolOutput::Value(target_json(&t.target)))
}

fn target_json(t: &Target) -> Value {
    json!({
        "target_id": t.id,
        "path": t.path,
        "name": t.name,
        "kind": t.kind,
        "description": t.kind.plain(),
        "sha256": t.sha256,
        "bytes": t.bytes.len(),
        "raw": t.raw,
    })
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct CloseParams {
    /// Target to close; the active one when omitted.
    #[serde(default)]
    pub target_id: Option<String>,
}

fn core_target_close(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: CloseParams = parse_params(params)?;
    let id = match p.target_id {
        Some(id) => id,
        None => ctx.session.active()?.target.id.clone(),
    };
    ctx.session.save_annotations()?;
    let closed = ctx.session.close_target(&id).ok_or_else(|| ToolError::new(ErrorCode::NotFound, format!("No open target {id}")))?;
    Ok(ToolOutput::Value(json!({"closed": closed.target.id, "evidence_records": ctx.session.ledger_len()})))
}

fn core_session_show(ctx: &mut Ctx<'_>, _params: Value) -> Result<ToolOutput, ToolError> {
    let s = &*ctx.session;
    let targets: Vec<Value> = s.targets().map(|t| target_json(&t.target)).collect();
    Ok(ToolOutput::Value(json!({
        "open": s.active_id().is_some(),
        "active_target": s.active_id(),
        "targets": targets,
        "analysis_mode": if s.clean_room() { "clean-room" } else { "deep" },
        "clean_room": s.clean_room(),
        "evidence_records": s.ledger_len(),
        "evidence_not_loaded": s.unloaded_evidence(),
        "unknowns": s.unknowns().count(),
        "project": s.project.as_ref().map(|p| json!({"name": p.meta.name, "path": p.root, "purpose": p.meta.purpose})),
        "server": {"name": "craft-anything", "version": env!("CARGO_PKG_VERSION")},
        "host": craft_anything_evidence::host_triple(),
    })))
}

fn core_targets_list(ctx: &mut Ctx<'_>, _params: Value) -> Result<ToolOutput, ToolError> {
    let targets: Vec<Value> = ctx.session.targets().map(|t| target_json(&t.target)).collect();
    Ok(ToolOutput::Value(json!({"active": ctx.session.active_id(), "targets": targets})))
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct SelectParams {
    pub target_id: String,
}

fn core_target_select(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: SelectParams = parse_params(params)?;
    ctx.session.set_active(&p.target_id)?;
    Ok(ToolOutput::Value(json!({"active": p.target_id})))
}

fn native_cursor_show(ctx: &mut Ctx<'_>, _params: Value) -> Result<ToolOutput, ToolError> {
    let t = ctx.session.active()?;
    Ok(ToolOutput::Value(json!({
        "document": t.target.name,
        "target_id": t.target.id,
        "address": t.cursor.address.map(|a| format!("{a:#x}")),
    })))
}

#[derive(Debug, Default, Deserialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Detail {
    #[default]
    Complete,
    Summary,
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct BundleParams {
    #[serde(default)]
    pub detail: Detail,
    /// Only records produced by this operation.
    #[serde(default)]
    pub operation: Option<String>,
    /// Only this record.
    #[serde(default)]
    pub evidence_id: Option<String>,
}

fn core_evidence_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: BundleParams = parse_params(params)?;
    let mut records: Vec<Evidence> = ctx
        .session
        .ledger()
        .filter(|e| p.operation.as_deref().is_none_or(|o| e.operation == o))
        .filter(|e| p.evidence_id.as_deref().is_none_or(|i| e.id == i))
        .cloned()
        .collect();
    // A record a large project left on disk still resolves by id (integrity-checked).
    if records.is_empty()
        && let Some(id) = &p.evidence_id
        && let Ok(e) = ctx.session.resolve_evidence(id)
        && p.operation.as_deref().is_none_or(|o| e.operation == o)
    {
        records.push(e);
    }
    let unknowns: Vec<&Unknown> = ctx.session.unknowns().collect();
    let records_json: Vec<Value> = match p.detail {
        Detail::Complete => records.iter().filter_map(|e| serde_json::to_value(e).ok()).collect(),
        Detail::Summary => records.iter().map(|e| e.summary_view()).collect(),
    };
    Ok(ToolOutput::Value(json!({
        "records": records_json,
        "unknowns": unknowns,
        "total": records_json.len(),
        "not_loaded": ctx.session.unloaded_evidence(),
    })))
}

pub const BUNDLE_FORMAT: &str = "craft-anything-evidence-bundle";

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ExportParams {
    /// Absolute path of the bundle file to write.
    pub path: String,
    #[serde(default)]
    pub overwrite: bool,
}

fn core_evidence_export(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ExportParams = parse_params(params)?;
    let path = PathBuf::from(&p.path);
    if !path.is_absolute() {
        return Err(ToolError::invalid("path must be absolute"));
    }
    if path.exists() && !p.overwrite {
        return Err(ToolError::invalid(format!("{} exists", path.display())).with_remediation("Pass overwrite=true or pick another name."));
    }
    let records: Vec<&Evidence> = ctx.session.ledger().collect();
    let unknowns: Vec<&Unknown> = ctx.session.unknowns().collect();
    let bundle = json!({"format": BUNDLE_FORMAT, "version": 1, "records": records, "unknowns": unknowns});
    let bytes = serde_json::to_vec_pretty(&bundle).map_err(|e| ToolError::internal(e.to_string()))?;
    write_atomic(&path, &bytes)?;
    Ok(ToolOutput::Value(json!({
        "path": path,
        "bytes": bytes.len(),
        "records": records.len(),
        "unknowns": unknowns.len(),
        "not_loaded": ctx.session.unloaded_evidence(),
    })))
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ImportParams {
    /// Absolute path of a bundle file.
    pub path: String,
}

/// Bundles bigger than this are refused (a bundle is text; 512 MiB is far beyond any real one).
const MAX_BUNDLE_BYTES: u64 = 512 * 1024 * 1024;

fn core_evidence_import(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ImportParams = parse_params(params)?;
    let path = PathBuf::from(&p.path);
    let len = std::fs::metadata(&path).map_err(|e| ToolError::io(path.display(), e))?.len();
    if len > MAX_BUNDLE_BYTES {
        return Err(ToolError::new(ErrorCode::OverLimit, "bundle is too large"));
    }
    let bytes = std::fs::read(&path).map_err(|e| ToolError::io(path.display(), e))?;
    let v: Value = serde_json::from_slice(&bytes).map_err(|e| ToolError::invalid(format!("not a bundle: {e}")))?;
    if v.get("format").and_then(Value::as_str) != Some(BUNDLE_FORMAT) {
        return Err(ToolError::invalid("not a Craft Anything evidence bundle"));
    }
    let mut imported = 0usize;
    let mut rejected = Vec::new();
    for r in v.get("records").and_then(Value::as_array).into_iter().flatten() {
        match serde_json::from_value::<Evidence>(r.clone()) {
            Ok(e) if e.verify() => {
                ctx.session.record(e)?;
                imported += 1;
            }
            Ok(e) => rejected.push(e.id),
            Err(_) => rejected.push("unparseable".into()),
        }
    }
    let mut unknowns_added = 0usize;
    for u in v.get("unknowns").and_then(Value::as_array).into_iter().flatten() {
        if let Ok(u) = serde_json::from_value::<Unknown>(u.clone())
            && ctx.session.unknown(&u.id).is_none()
        {
            ctx.session.put_unknown(u)?;
            unknowns_added += 1;
        }
    }
    if !rejected.is_empty() && imported == 0 {
        return Err(ToolError::new(ErrorCode::EvidenceHashMismatch, format!("{} records failed their integrity check", rejected.len()))
            .with_details(json!({"rejected": rejected})));
    }
    Ok(ToolOutput::Value(json!({"imported": imported, "rejected": rejected, "unknowns_added": unknowns_added, "total": ctx.session.ledger_len()})))
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ListUnknownsParams {
    #[serde(default)]
    pub status: Option<UnknownStatusParam>,
    #[serde(default)]
    pub severity: Option<SeverityParam>,
    #[serde(default)]
    pub domain: Option<String>,
}

/// Mirrors [`UnknownStatus`] for the schema.
#[derive(Debug, Clone, Copy, Deserialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum UnknownStatusParam {
    Open,
    Investigating,
    Blocked,
    Contradicted,
    Resolved,
}

impl From<UnknownStatusParam> for UnknownStatus {
    fn from(s: UnknownStatusParam) -> Self {
        match s {
            UnknownStatusParam::Open => UnknownStatus::Open,
            UnknownStatusParam::Investigating => UnknownStatus::Investigating,
            UnknownStatusParam::Blocked => UnknownStatus::Blocked,
            UnknownStatusParam::Contradicted => UnknownStatus::Contradicted,
            UnknownStatusParam::Resolved => UnknownStatus::Resolved,
        }
    }
}

#[derive(Debug, Clone, Copy, Deserialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum SeverityParam {
    Low,
    Medium,
    High,
    Critical,
}

impl From<SeverityParam> for Severity {
    fn from(s: SeverityParam) -> Self {
        match s {
            SeverityParam::Low => Severity::Low,
            SeverityParam::Medium => Severity::Medium,
            SeverityParam::High => Severity::High,
            SeverityParam::Critical => Severity::Critical,
        }
    }
}

fn core_unknowns_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ListUnknownsParams = parse_params(params)?;
    let items: Vec<&Unknown> = ctx
        .session
        .unknowns()
        .filter(|u| p.status.is_none_or(|s| u.status == s.into()))
        .filter(|u| p.severity.is_none_or(|s| u.severity == s.into()))
        .filter(|u| p.domain.as_deref().is_none_or(|d| u.domain == d))
        .collect();
    Ok(ToolOutput::Value(json!({"items": items, "total": items.len()})))
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct RecordUnknownParams {
    pub question: String,
    #[serde(default = "default_domain")]
    pub domain: String,
    #[serde(default)]
    pub severity: Option<SeverityParam>,
    /// What would settle it.
    #[serde(default)]
    pub probes: Vec<String>,
    #[serde(default)]
    pub evidence_for: Vec<String>,
    #[serde(default)]
    pub evidence_against: Vec<String>,
}

fn default_domain() -> String {
    "general".into()
}

fn core_unknown_add(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: RecordUnknownParams = parse_params(params)?;
    if p.question.trim().is_empty() {
        return Err(ToolError::invalid("question is empty"));
    }
    let mut u = Unknown::new(p.question.trim(), p.domain, p.severity.map(Into::into).unwrap_or_default());
    if ctx.session.unknown(&u.id).is_some() {
        return Err(ToolError::invalid(format!("{} is already recorded", u.id)).with_remediation("Use core_unknown_edit to change it."));
    }
    u.probes = p.probes;
    u.evidence_for = p.evidence_for;
    u.evidence_against = p.evidence_against;
    ctx.session.put_unknown(u.clone())?;
    Ok(ToolOutput::Value(serde_json::to_value(u).unwrap_or(Value::Null)))
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct UpdateUnknownParams {
    pub unknown_id: String,
    pub based_on_revision: u64,
    #[serde(default)]
    pub status: Option<UnknownStatusParam>,
    #[serde(default)]
    pub severity: Option<SeverityParam>,
    #[serde(default)]
    pub probes: Option<Vec<String>>,
    #[serde(default)]
    pub evidence_for: Option<Vec<String>>,
    #[serde(default)]
    pub evidence_against: Option<Vec<String>>,
    #[serde(default)]
    pub resolution: Option<String>,
}

fn core_unknown_edit(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: UpdateUnknownParams = parse_params(params)?;
    let current = ctx.session.unknown(&p.unknown_id).cloned().ok_or_else(|| ToolError::invalid(format!("No unknown {}", p.unknown_id)))?;
    let mut next = current.clone();
    if let Some(s) = p.status {
        next.status = s.into();
    }
    if let Some(s) = p.severity {
        next.severity = s.into();
    }
    if let Some(v) = p.probes {
        next.probes = v;
    }
    if let Some(v) = p.evidence_for {
        next.evidence_for = v;
    }
    if let Some(v) = p.evidence_against {
        next.evidence_against = v;
    }
    if p.resolution.is_some() {
        next.resolution = p.resolution;
    }
    let u = ctx.session.unknown_mut(&p.unknown_id).ok_or_else(|| ToolError::invalid(format!("No unknown {}", p.unknown_id)))?;
    u.apply_update(p.based_on_revision, next)?;
    let updated = u.clone();
    ctx.session.put_unknown(updated.clone())?;
    Ok(ToolOutput::Value(serde_json::to_value(updated).unwrap_or(Value::Null)))
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct UnknownIdParams {
    pub unknown_id: String,
}

fn core_unknown_verify(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: UnknownIdParams = parse_params(params)?;
    let u = ctx.session.unknown(&p.unknown_id).cloned().ok_or_else(|| ToolError::invalid(format!("No unknown {}", p.unknown_id)))?;
    let mut problems = Vec::new();
    if u.status != UnknownStatus::Resolved {
        problems.push("not marked resolved".to_string());
    }
    if u.resolution.as_deref().is_none_or(|r| r.trim().is_empty()) {
        problems.push("no resolution text".to_string());
    }
    if u.evidence_for.is_empty() {
        problems.push("cites no evidence".to_string());
    }
    for id in &u.evidence_for {
        match ctx.session.resolve_evidence(id) {
            Ok(e) if e.verify() => {}
            Ok(_) => problems.push(format!("{id} failed its integrity check")),
            Err(_) => problems.push(format!("{id} not found")),
        }
    }
    Ok(ToolOutput::Value(json!({"valid": problems.is_empty(), "problems": problems, "unknown": u})))
}

#[cfg(test)]
mod tests {
    use crate::{CallOptions, Caller, Engine};
    use serde_json::json;

    #[test]
    fn open_session_close_round_trip() {
        let dir = tempfile::tempdir().unwrap();
        let f = dir.path().join("a.bin");
        std::fs::write(&f, b"\x7fELF\x02\x01\x01").unwrap();
        let e = Engine::new(crate::testing::session());
        let out = e.call("core_target_open", json!({"path": f}), CallOptions::new(Caller::Cli)).unwrap().to_json();
        assert_eq!(out["result"]["kind"], "elf");
        let st = e.call("core_session_show", json!({}), CallOptions::new(Caller::Cli)).unwrap().to_json();
        assert_eq!(st["result"]["open"], true);
        assert_eq!(st["result"]["clean_room"], false, "test sessions are in Deep mode");
        e.call("core_target_close", json!(null), CallOptions::new(Caller::Cli)).unwrap();
        let st = e.call("core_session_show", json!({}), CallOptions::new(Caller::Cli)).unwrap().to_json();
        assert_eq!(st["result"]["open"], false);
    }

    /// #305: reopening the same raw bytes with another architecture or address kept the first.
    #[test]
    fn reopening_raw_bytes_with_new_settings_uses_them() {
        let dir = tempfile::tempdir().unwrap();
        let f = dir.path().join("code.bin");
        std::fs::write(&f, [0xc0, 0x03, 0x5f, 0xd6]).unwrap(); // arm64 `ret`
        let e = Engine::new(crate::testing::session());
        let call = |id: &str, p: serde_json::Value| e.call(id, p, CallOptions::new(Caller::Mcp)).unwrap().to_json();
        let open = |arch: &str, at: &str| call("core_target_open", json!({"path": f, "format": "raw-binary", "architecture": arch, "entry_point": at}));
        assert_eq!(open("x86", "0x1000")["result"]["raw"], json!({"architecture": "x86", "entry_point": 0x1000}));
        call("native_instruction_show", json!({"address": "0x1000"}));
        let again = open("arm64", "0x8000");
        assert_eq!(again["result"]["raw"], json!({"architecture": "arm64", "entry_point": 0x8000}));
        let insn = call("native_instruction_show", json!({"address": "0x8000"}));
        assert!(insn["result"].to_string().contains("ret"), "{insn}");
        assert_eq!(open("arm64", "0x8000")["result"]["raw"]["entry_point"], 0x8000, "the same settings reuse the target");
        assert_eq!(call("core_session_show", json!({}))["result"]["targets"].as_array().map(Vec::len), Some(1), "still one target");
    }

    #[test]
    fn relative_paths_and_bad_params_are_errors() {
        let e = Engine::new(crate::testing::session());
        assert!(e.call("core_target_open", json!({"path": "rel/a.exe"}), CallOptions::new(Caller::Mcp)).is_err());
        assert!(e.call("core_target_open", json!({"nope": 1}), CallOptions::new(Caller::Mcp)).is_err());
        assert!(e.call("core_target_open", json!("string"), CallOptions::new(Caller::Mcp)).is_err());
    }

    #[test]
    fn unknown_lifecycle() {
        let e = Engine::new(crate::testing::session());
        let u = e
            .call("core_unknown_add", json!({"question": "Where is the key derived?", "severity": "high"}), CallOptions::new(Caller::Agent))
            .unwrap()
            .to_json();
        let id = u["result"]["id"].as_str().unwrap().to_string();
        let up = e
            .call(
                "core_unknown_edit",
                json!({"unknown_id": id, "based_on_revision": 1, "status": "resolved", "resolution": "In kdf()"}),
                CallOptions::new(Caller::Agent),
            )
            .unwrap()
            .to_json();
        assert_eq!(up["result"]["revision"], 2);
        let stale = e.call("core_unknown_edit", json!({"unknown_id": id, "based_on_revision": 1}), CallOptions::new(Caller::Agent)).unwrap_err();
        assert_eq!(stale.code, craft_anything_evidence::ErrorCode::StaleRevision);
        let v = e.call("core_unknown_verify", json!({"unknown_id": id}), CallOptions::new(Caller::Agent)).unwrap().to_json();
        assert_eq!(v["result"]["valid"], false, "cites no evidence");
    }

    #[test]
    fn project_evidence_is_loaded_in_a_new_session() {
        use crate::project::{Project, Purpose};
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path().join("p.cany");
        let project = Project::create(&root, "p", Purpose::Education).unwrap();
        let ev = |n: i64| {
            craft_anything_evidence::EvidenceBuilder::new("x", craft_anything_evidence::Subject::default(), craft_anything_evidence::Environment::builtin(true))
                .result(json!(n))
                .build()
                .unwrap()
        };
        let (good, bad) = (ev(1), ev(2));
        project.store_evidence(&good).unwrap();
        project.store_evidence(&bad).unwrap();
        // Tamper with one stored record: it must not be loaded.
        let bad_path = root.join("evidence").join(&bad.id[3..5]).join(format!("{}.json", bad.id));
        let text = std::fs::read_to_string(&bad_path).unwrap().replace("\"result\": 2", "\"result\": 3");
        std::fs::write(&bad_path, text).unwrap();

        // A fresh process: a new session opening the same project.
        let mut s = crate::testing::session();
        s.open_project(Project::open(&root).unwrap()).unwrap();
        let e = Engine::new(s);
        let b = e.call("core_evidence_show", json!({"detail": "summary"}), CallOptions::new(Caller::Cli)).unwrap().to_json();
        assert_eq!(b["result"]["total"], 1);
        assert_eq!(b["result"]["records"][0]["evidence_id"], good.id.as_str());
        let st = e.call("core_session_show", json!({}), CallOptions::new(Caller::Cli)).unwrap().to_json();
        assert_eq!(st["result"]["evidence_records"], 1);
        let path = dir.path().join("b.json");
        let x = e.call("core_evidence_export", json!({"path": path}), CallOptions::new(Caller::Cli)).unwrap().to_json();
        assert_eq!(x["result"]["records"], 1);
    }

    #[test]
    fn bundle_export_import() {
        let dir = tempfile::tempdir().unwrap();
        let e = Engine::new(crate::testing::session());
        e.call("core_unknown_add", json!({"question": "q"}), CallOptions::new(Caller::Cli)).unwrap();
        let path = dir.path().join("b.json");
        e.call("core_evidence_export", json!({"path": path}), CallOptions::new(Caller::Cli)).unwrap();
        assert!(e.call("core_evidence_export", json!({"path": path}), CallOptions::new(Caller::Cli)).is_err());
        let e2 = Engine::new(crate::testing::session());
        let r = e2.call("core_evidence_import", json!({"path": path}), CallOptions::new(Caller::Cli)).unwrap().to_json();
        assert_eq!(r["result"]["unknowns_added"], 1);
    }
}
