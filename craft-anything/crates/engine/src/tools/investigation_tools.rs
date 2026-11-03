//! Investigation memory: brief, plan, hypotheses, findings and handoff, plus the journal reader.
//!
//! With a project open these live in `<project>/investigation/` as `state.json` (the structured
//! source of truth, revisioned) and readable Markdown renders (`brief.md`, `plan.md`,
//! `hypotheses.md`, `findings.md`, `handoff.md`). Without a project they live in the session only.
//! Any agent (ours or an external one over MCP) keeps them current so long investigations survive
//! context limits, restarts and handoffs between agents.

use crate::journal;
use crate::project::write_atomic;
use crate::session::Session;
use crate::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, empty_schema, parse_params, schema_of};
use craft_anything_evidence::{Confidence, ErrorCode, ToolError};
use craft_anything_platform::sync::Mutex;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::path::PathBuf;
use std::sync::{Arc, PoisonError};

pub fn specs() -> Vec<ToolSpec> {
    let w = Effects::MUTATES_SESSION.union(Effects::WRITES_FILESYSTEM);
    vec![
        ToolSpec {
            id: "core_investigation_show",
            title: "Investigation so far",
            summary: "The working memory of this investigation: brief, plan with step status, hypotheses, findings (with evidence ids) and the latest handoff. Read it first when starting or resuming.",
            beginner: "See what we're trying to find out, the plan, and what we know so far.",
            toolset: Toolset::Core,
            effects: Effects::READ_ONLY,
            requires: Requires::Nothing,
            input_schema: empty_schema,
            run: core_investigation_show,
        },
        ToolSpec {
            id: "core_brief_write",
            title: "Write the brief",
            summary: "Set the investigation brief: the question, purpose, targets, constraints and what 'done' means. Write it before the first analysis call on a new question.",
            beginner: "Write down the question we're answering and what a good answer looks like.",
            toolset: Toolset::Core,
            effects: w,
            requires: Requires::Nothing,
            input_schema: schema_of::<BriefParams>,
            run: core_brief_write,
        },
        ToolSpec {
            id: "core_plan_update",
            title: "Update the plan",
            summary: "Replace the plan with a numbered list of steps, each todo/doing/done/blocked with a short why. Pass based_on_revision to avoid overwriting someone else's update.",
            beginner: "Update the step-by-step plan.",
            toolset: Toolset::Core,
            effects: w,
            requires: Requires::Nothing,
            input_schema: schema_of::<PlanParams>,
            run: core_plan_update,
        },
        ToolSpec {
            id: "core_hypothesis_record",
            title: "Record a hypothesis",
            summary: "Record a claim being tested, ideally with the prediction that would confirm or refute it, plus any supporting/contradicting evidence ids.",
            beginner: "Write down a guess we're going to check.",
            toolset: Toolset::Core,
            effects: w,
            requires: Requires::Nothing,
            input_schema: schema_of::<HypothesisParams>,
            run: core_hypothesis_record,
        },
        ToolSpec {
            id: "core_hypothesis_update",
            title: "Update a hypothesis",
            summary: "Change a hypothesis's status (testing/supported/refuted/abandoned) and attach supporting or contradicting evidence ids and notes.",
            beginner: "Mark a guess as confirmed, wrong, or still being checked.",
            toolset: Toolset::Core,
            effects: w,
            requires: Requires::Nothing,
            input_schema: schema_of::<UpdateHypothesisParams>,
            run: core_hypothesis_update,
        },
        ToolSpec {
            id: "core_finding_record",
            title: "Record a finding",
            summary: "Record a settled answer. Requires at least one evidence id; every id is checked against the ledger. Findings are the source for reports.",
            beginner: "Save something we now know for sure, with the proof.",
            toolset: Toolset::Core,
            effects: w,
            requires: Requires::Nothing,
            input_schema: schema_of::<FindingParams>,
            run: core_finding_record,
        },
        ToolSpec {
            id: "core_handoff_write",
            title: "Write the handoff",
            summary: "Rewrite the handoff note: where we are, what's next, traps to avoid. Write it at the end of every turn so the next turn (or agent) resumes without re-deriving.",
            beginner: "Leave a note so we can pick up exactly where we left off.",
            toolset: Toolset::Core,
            effects: w,
            requires: Requires::Nothing,
            input_schema: schema_of::<HandoffParams>,
            run: core_handoff_write,
        },
        ToolSpec {
            id: "core_journal_read",
            title: "Read the journal",
            summary: "Page through the project's append-only journal (tool calls, model turns, consents, errors), filtered by day, kind or tool. Needs an open project.",
            beginner: "See a log of everything that happened in this project.",
            toolset: Toolset::Core,
            effects: Effects::READ_ONLY,
            requires: Requires::Nothing,
            input_schema: schema_of::<JournalParams>,
            run: core_journal_read,
        },
    ]
}

// ---- state ----

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize, JsonSchema)]
pub struct Brief {
    pub question: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub purpose: Option<String>,
    #[serde(default)]
    pub targets: Vec<String>,
    #[serde(default)]
    pub constraints: Vec<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub done_when: Option<String>,
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, Deserialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum StepStatus {
    #[default]
    Todo,
    Doing,
    Done,
    Blocked,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
pub struct PlanStep {
    pub title: String,
    #[serde(default)]
    pub status: StepStatus,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub why: Option<String>,
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, Deserialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum HypothesisStatus {
    #[default]
    Testing,
    Supported,
    Refuted,
    Abandoned,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Hypothesis {
    pub id: String,
    pub claim: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub prediction: Option<String>,
    pub status: HypothesisStatus,
    #[serde(default)]
    pub supporting: Vec<String>,
    #[serde(default)]
    pub contradicting: Vec<String>,
    #[serde(default)]
    pub notes: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Finding {
    pub id: String,
    pub statement: String,
    pub evidence_ids: Vec<String>,
    pub confidence: Confidence,
}

#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Investigation {
    pub revision: u64,
    #[serde(default)]
    pub brief: Option<Brief>,
    #[serde(default)]
    pub plan: Vec<PlanStep>,
    #[serde(default)]
    pub hypotheses: Vec<Hypothesis>,
    #[serde(default)]
    pub findings: Vec<Finding>,
    #[serde(default)]
    pub handoff: Option<String>,
    #[serde(default)]
    pub updated: Option<String>,
}

type Slot = Mutex<Investigation>;

fn dir(session: &Session) -> Option<PathBuf> {
    session.project.as_ref().map(|p| p.root.join("investigation"))
}

/// The current investigation state (from the project when one is open, else the session).
pub fn load(session: &Session) -> Investigation {
    if let Some(d) = dir(session) {
        return std::fs::read(d.join("state.json")).ok().and_then(|b| serde_json::from_slice(&b).ok()).unwrap_or_default();
    }
    session.ext.get::<Slot>().map(|s| s.lock().unwrap_or_else(PoisonError::into_inner).clone()).unwrap_or_default()
}

fn save(session: &mut Session, mut inv: Investigation) -> Result<Investigation, ToolError> {
    inv.revision = inv.revision.saturating_add(1);
    let (_, date, time) = journal::now_utc();
    inv.updated = Some(format!("{date}T{time}Z"));
    if let Some(d) = dir(session) {
        let text = serde_json::to_vec_pretty(&inv).map_err(|e| ToolError::internal(e.to_string()))?;
        write_atomic(&d.join("state.json"), &text)?;
        for (name, body) in render(&inv) {
            write_atomic(&d.join(name), body.as_bytes())?;
        }
    } else {
        match session.ext.get::<Slot>() {
            Some(slot) => *slot.lock().unwrap_or_else(PoisonError::into_inner) = inv.clone(),
            None => session.ext.insert(Arc::new(Mutex::new(inv.clone()))),
        }
    }
    Ok(inv)
}

/// The Markdown files, rendered from the structured state.
pub fn render(inv: &Investigation) -> Vec<(&'static str, String)> {
    let mut brief = String::from("# Brief\n\n");
    match &inv.brief {
        Some(b) => {
            brief.push_str(&format!("**Question:** {}\n\n", b.question));
            if let Some(p) = &b.purpose {
                brief.push_str(&format!("**Purpose:** {p}\n\n"));
            }
            if !b.targets.is_empty() {
                brief.push_str("**Targets:**\n");
                for t in &b.targets {
                    brief.push_str(&format!("- {t}\n"));
                }
                brief.push('\n');
            }
            if !b.constraints.is_empty() {
                brief.push_str("**Constraints:**\n");
                for c in &b.constraints {
                    brief.push_str(&format!("- {c}\n"));
                }
                brief.push('\n');
            }
            if let Some(d) = &b.done_when {
                brief.push_str(&format!("**Done when:** {d}\n"));
            }
        }
        None => brief.push_str("_No brief yet._\n"),
    }
    let mut plan = String::from("# Plan\n\n");
    if inv.plan.is_empty() {
        plan.push_str("_No plan yet._\n");
    }
    for (i, s) in inv.plan.iter().enumerate() {
        let st = match s.status {
            StepStatus::Todo => "todo",
            StepStatus::Doing => "doing",
            StepStatus::Done => "done",
            StepStatus::Blocked => "blocked",
        };
        plan.push_str(&format!("{}. [{st}] {}", i + 1, s.title));
        if let Some(w) = &s.why {
            plan.push_str(&format!(" — {w}"));
        }
        plan.push('\n');
    }
    let mut hyp = String::from("# Hypotheses\n\n");
    if inv.hypotheses.is_empty() {
        hyp.push_str("_None yet._\n");
    }
    for h in &inv.hypotheses {
        hyp.push_str(&format!("## {} ({:?})\n\n{}\n\n", h.id, h.status, h.claim));
        if let Some(p) = &h.prediction {
            hyp.push_str(&format!("Prediction: {p}\n\n"));
        }
        if !h.supporting.is_empty() {
            hyp.push_str(&format!("Supporting: {}\n\n", h.supporting.join(", ")));
        }
        if !h.contradicting.is_empty() {
            hyp.push_str(&format!("Contradicting: {}\n\n", h.contradicting.join(", ")));
        }
        for n in &h.notes {
            hyp.push_str(&format!("- {n}\n"));
        }
    }
    let mut fnd = String::from("# Findings\n\n");
    if inv.findings.is_empty() {
        fnd.push_str("_None yet._\n");
    }
    for f in &inv.findings {
        fnd.push_str(&format!("- **{}** {} ({}; evidence: {})\n", f.id, f.statement, f.confidence.plain_label(), f.evidence_ids.join(", ")));
    }
    let handoff = format!("# Handoff\n\n{}\n", inv.handoff.clone().unwrap_or_else(|| "_No handoff yet._".into()));
    vec![("brief.md", brief), ("plan.md", plan), ("hypotheses.md", hyp), ("findings.md", fnd), ("handoff.md", handoff)]
}

fn out(inv: &Investigation, session: &Session) -> ToolOutput {
    ToolOutput::Value(json!({
        "revision": inv.revision,
        "updated": inv.updated,
        "brief": inv.brief,
        "plan": inv.plan,
        "hypotheses": inv.hypotheses,
        "findings": inv.findings,
        "handoff": inv.handoff,
        "stored_in": dir(session).map(|d| d.display().to_string()).unwrap_or_else(|| "session (no project open)".into()),
    }))
}

fn check_ids(session: &Session, ids: &[String]) -> Result<(), ToolError> {
    for id in ids {
        session.resolve_evidence(id).map_err(|_| {
            ToolError::invalid(format!("Unknown evidence id {id}")).with_remediation("Cite ids returned by analysis tools (see core_evidence_show).")
        })?;
    }
    Ok(())
}

fn check_revision(inv: &Investigation, expected: Option<u64>) -> Result<(), ToolError> {
    match expected {
        Some(r) if r != inv.revision => Err(ToolError::new(ErrorCode::StaleRevision, format!("The investigation is at revision {}, not {r}.", inv.revision))
            .with_remediation("Call core_investigation_show, merge your change, and retry with the current revision.")),
        _ => Ok(()),
    }
}

// ---- tools ----

fn core_investigation_show(ctx: &mut Ctx<'_>, _p: Value) -> Result<ToolOutput, ToolError> {
    let inv = load(ctx.session);
    Ok(out(&inv, ctx.session))
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct BriefParams {
    /// The question being answered, in one or two sentences.
    pub question: String,
    /// Why the user is asking (interoperability, security review, learning…).
    #[serde(default)]
    pub purpose: Option<String>,
    /// Targets involved (paths, packages, URLs).
    #[serde(default)]
    pub targets: Vec<String>,
    /// Constraints (clean room, no running the target, time budget…).
    #[serde(default)]
    pub constraints: Vec<String>,
    /// What a finished answer looks like.
    #[serde(default)]
    pub done_when: Option<String>,
}

fn core_brief_write(ctx: &mut Ctx<'_>, p: Value) -> Result<ToolOutput, ToolError> {
    let p: BriefParams = parse_params(p)?;
    if p.question.trim().is_empty() {
        return Err(ToolError::invalid("The brief needs a question."));
    }
    let mut inv = load(ctx.session);
    inv.brief = Some(Brief { question: p.question, purpose: p.purpose, targets: p.targets, constraints: p.constraints, done_when: p.done_when });
    let inv = save(ctx.session, inv)?;
    Ok(out(&inv, ctx.session))
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct PlanParams {
    /// The whole plan, in order (replaces the previous one).
    pub steps: Vec<PlanStep>,
    /// The revision your change is based on (from core_investigation_show); omit to overwrite.
    #[serde(default)]
    pub based_on_revision: Option<u64>,
}

fn core_plan_update(ctx: &mut Ctx<'_>, p: Value) -> Result<ToolOutput, ToolError> {
    let p: PlanParams = parse_params(p)?;
    if p.steps.len() > 200 {
        return Err(ToolError::invalid("A plan can have at most 200 steps."));
    }
    let mut inv = load(ctx.session);
    check_revision(&inv, p.based_on_revision)?;
    inv.plan = p.steps;
    let inv = save(ctx.session, inv)?;
    Ok(out(&inv, ctx.session))
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct HypothesisParams {
    /// The claim being tested.
    pub claim: String,
    /// What we expect to observe if the claim is true.
    #[serde(default)]
    pub prediction: Option<String>,
    #[serde(default)]
    pub evidence_for: Vec<String>,
    #[serde(default)]
    pub evidence_against: Vec<String>,
}

fn core_hypothesis_record(ctx: &mut Ctx<'_>, p: Value) -> Result<ToolOutput, ToolError> {
    let p: HypothesisParams = parse_params(p)?;
    if p.claim.trim().is_empty() {
        return Err(ToolError::invalid("A hypothesis needs a claim."));
    }
    check_ids(ctx.session, &p.evidence_for)?;
    check_ids(ctx.session, &p.evidence_against)?;
    let mut inv = load(ctx.session);
    let id = format!("hyp_{}", inv.hypotheses.len() + 1);
    inv.hypotheses.push(Hypothesis {
        id: id.clone(),
        claim: p.claim,
        prediction: p.prediction,
        status: HypothesisStatus::Testing,
        supporting: p.evidence_for,
        contradicting: p.evidence_against,
        notes: Vec::new(),
    });
    let inv = save(ctx.session, inv)?;
    Ok(ToolOutput::Value(json!({"hypothesis_id": id, "revision": inv.revision})))
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct UpdateHypothesisParams {
    pub hypothesis_id: String,
    #[serde(default)]
    pub status: Option<HypothesisStatus>,
    #[serde(default)]
    pub add_supporting_evidence_ids: Vec<String>,
    #[serde(default)]
    pub add_contradicting_evidence_ids: Vec<String>,
    #[serde(default)]
    pub note: Option<String>,
}

fn core_hypothesis_update(ctx: &mut Ctx<'_>, p: Value) -> Result<ToolOutput, ToolError> {
    let p: UpdateHypothesisParams = parse_params(p)?;
    check_ids(ctx.session, &p.add_supporting_evidence_ids)?;
    check_ids(ctx.session, &p.add_contradicting_evidence_ids)?;
    let mut inv = load(ctx.session);
    let h = inv
        .hypotheses
        .iter_mut()
        .find(|h| h.id == p.hypothesis_id)
        .ok_or_else(|| ToolError::invalid(format!("No hypothesis {}", p.hypothesis_id)).with_remediation("See core_investigation_show for the ids."))?;
    if let Some(s) = p.status {
        h.status = s;
    }
    for id in p.add_supporting_evidence_ids {
        if !h.supporting.contains(&id) {
            h.supporting.push(id);
        }
    }
    for id in p.add_contradicting_evidence_ids {
        if !h.contradicting.contains(&id) {
            h.contradicting.push(id);
        }
    }
    if let Some(n) = p.note.filter(|n| !n.trim().is_empty()) {
        h.notes.push(n);
    }
    let snapshot = h.clone();
    let inv = save(ctx.session, inv)?;
    Ok(ToolOutput::Value(json!({"hypothesis": snapshot, "revision": inv.revision})))
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct FindingParams {
    /// The settled answer, in one or two sentences.
    pub statement: String,
    /// Evidence ids that establish it (at least one).
    pub evidence_ids: Vec<String>,
    /// observed (read directly), derived (computed from observations) or inferred (best guess).
    #[serde(default = "inferred")]
    pub confidence: ConfidenceParam,
}

#[derive(Debug, Clone, Copy, Deserialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum ConfidenceParam {
    Observed,
    Derived,
    Inferred,
}

fn inferred() -> ConfidenceParam {
    ConfidenceParam::Inferred
}

fn core_finding_record(ctx: &mut Ctx<'_>, p: Value) -> Result<ToolOutput, ToolError> {
    let p: FindingParams = parse_params(p)?;
    if p.statement.trim().is_empty() {
        return Err(ToolError::invalid("A finding needs a statement."));
    }
    if p.evidence_ids.is_empty() {
        return Err(ToolError::invalid("A finding must cite at least one evidence id.")
            .with_remediation("Run the analysis that shows it, then cite the evidence id it returns."));
    }
    check_ids(ctx.session, &p.evidence_ids)?;
    let mut inv = load(ctx.session);
    let id = format!("fnd_{}", inv.findings.len() + 1);
    let confidence = match p.confidence {
        ConfidenceParam::Observed => Confidence::Observed,
        ConfidenceParam::Derived => Confidence::Derived,
        ConfidenceParam::Inferred => Confidence::Inferred,
    };
    inv.findings.push(Finding { id: id.clone(), statement: p.statement, evidence_ids: p.evidence_ids, confidence });
    let inv = save(ctx.session, inv)?;
    Ok(ToolOutput::Value(json!({"finding_id": id, "revision": inv.revision})))
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct HandoffParams {
    /// Where we are, what's next, and traps to avoid. Replaces the previous handoff.
    pub text: String,
}

fn core_handoff_write(ctx: &mut Ctx<'_>, p: Value) -> Result<ToolOutput, ToolError> {
    let p: HandoffParams = parse_params(p)?;
    let mut inv = load(ctx.session);
    inv.handoff = Some(p.text);
    let inv = save(ctx.session, inv)?;
    Ok(ToolOutput::Value(json!({"revision": inv.revision})))
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct JournalParams {
    /// Day to read (`YYYY-MM-DD`); the latest day when omitted.
    #[serde(default)]
    pub day: Option<String>,
    /// Only entries of this kind (`tool_call`, `model_turn`, `consent`, `user_message`, `error`…).
    #[serde(default)]
    pub kind: Option<String>,
    /// Only calls of this tool.
    #[serde(default)]
    pub tool: Option<String>,
    #[serde(default)]
    pub offset: usize,
    /// At most 500; default 50.
    #[serde(default)]
    pub limit: Option<usize>,
}

fn core_journal_read(ctx: &mut Ctx<'_>, p: Value) -> Result<ToolOutput, ToolError> {
    let p: JournalParams = parse_params(p)?;
    let root = ctx.session.project.as_ref().map(|pr| pr.root.clone()).ok_or_else(|| {
        ToolError::unavailable("The journal is kept per project, and no project is open.").with_remediation("Open or create a project (.cany) first.")
    })?;
    let days = journal::days(&root);
    let day = p.day.or_else(|| days.last().cloned()).unwrap_or_default();
    let entries: Vec<Value> = journal::read_day(&root, &day)
        .into_iter()
        .filter(|e| p.kind.as_ref().is_none_or(|k| e["kind"] == *k))
        .filter(|e| p.tool.as_ref().is_none_or(|t| e["tool"] == *t))
        .collect();
    let limit = p.limit.unwrap_or(50).clamp(1, 500);
    let total = entries.len();
    let page: Vec<Value> = entries.into_iter().skip(p.offset).take(limit).collect();
    let next = p.offset.saturating_add(page.len());
    Ok(ToolOutput::Value(json!({
        "day": day,
        "days": days,
        "total": total,
        "entries": page,
        "next_offset": if next < total { Some(next) } else { None },
    })))
}

#[cfg(test)]
mod tests {
    use crate::project::{Project, Purpose};
    use crate::{CallOptions, Caller, Engine};
    use serde_json::json;

    fn call(e: &Engine, id: &str, p: serde_json::Value) -> Result<serde_json::Value, craft_anything_evidence::ToolError> {
        e.call(id, p, CallOptions::new(Caller::Agent)).map(|o| o.to_json())
    }

    #[test]
    fn memory_round_trip_without_project() {
        let e = Engine::new(crate::testing::session());
        call(&e, "core_brief_write", json!({"question": "How does save work?"})).unwrap();
        call(&e, "core_plan_update", json!({"steps": [{"title": "find save", "status": "doing"}]})).unwrap();
        let h = call(&e, "core_hypothesis_record", json!({"claim": "writes JSON", "prediction": "a .json string near the save path"})).unwrap();
        assert_eq!(h["result"]["hypothesis_id"], "hyp_1");
        call(&e, "core_hypothesis_update", json!({"hypothesis_id": "hyp_1", "status": "supported", "note": "seen"})).unwrap();
        // findings need real evidence
        assert!(call(&e, "core_finding_record", json!({"statement": "x", "evidence_ids": []})).is_err());
        assert!(call(&e, "core_finding_record", json!({"statement": "x", "evidence_ids": ["ev_00"]})).is_err());
        call(&e, "core_handoff_write", json!({"text": "next: check the loader"})).unwrap();
        let inv = call(&e, "core_investigation_show", json!({})).unwrap();
        assert_eq!(inv["result"]["brief"]["question"], "How does save work?");
        assert_eq!(inv["result"]["hypotheses"][0]["status"], "supported");
        assert_eq!(inv["result"]["handoff"], "next: check the loader");
        let rev = inv["result"]["revision"].as_u64().unwrap();
        let err = call(&e, "core_plan_update", json!({"steps": [], "based_on_revision": rev + 7})).unwrap_err();
        assert_eq!(err.code, craft_anything_evidence::ErrorCode::StaleRevision);
        assert!(call(&e, "core_journal_read", json!({})).is_err());
    }

    #[test]
    fn project_files_and_journal() {
        let dir = tempfile::tempdir().unwrap();
        let project = Project::create(&dir.path().join("p.cany"), "p", Purpose::Education).unwrap();
        let mut s = crate::testing::session();
        s.open_project(project).unwrap();
        let e = Engine::new(s);
        call(&e, "core_brief_write", json!({"question": "Q?", "targets": ["/bin/ls"]})).unwrap();
        call(&e, "core_handoff_write", json!({"text": "resume here"})).unwrap();
        let inv_dir = dir.path().join("p.cany").join("investigation");
        for f in ["state.json", "brief.md", "plan.md", "hypotheses.md", "findings.md", "handoff.md"] {
            assert!(inv_dir.join(f).exists(), "{f}");
        }
        assert!(std::fs::read_to_string(inv_dir.join("handoff.md")).unwrap().contains("resume here"));
        let _ = call(&e, "no_such_tool", json!({}));
        let j = call(&e, "core_journal_read", json!({"kind": "tool_call"})).unwrap();
        let entries = j["result"]["entries"].as_array().unwrap();
        assert!(entries.len() >= 3);
        assert_eq!(entries[0]["tool"], "core_brief_write");
        assert_eq!(entries[0]["ok"], true);
        assert!(entries.iter().any(|e| e["tool"] == "no_such_tool" && e["ok"] == false));
        let only = call(&e, "core_journal_read", json!({"tool": "core_handoff_write"})).unwrap();
        assert_eq!(only["result"]["total"], 1);
    }
}
