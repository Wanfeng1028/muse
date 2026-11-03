//! `setup`, `doctor`, `uninstall`.

use crate::output::Format;
use crate::{emit, fail, out};
use clap::Args;
use craft_anything_setup::{ActionKind, CheckStatus, DoctorRequest, Host, PlanRequest};
use serde_json::{Value, json};
use std::io::IsTerminal as _;

#[derive(Debug, Args)]
pub struct SetupArgs {
    /// Show what would change without writing anything.
    #[arg(long)]
    pub dry_run: bool,
    /// Client to configure (repeatable): claude_code, codex, cursor, …
    #[arg(long = "client")]
    pub clients: Vec<String>,
    /// Configure every detected client.
    #[arg(long)]
    pub all_detected: bool,
    /// Apply without asking.
    #[arg(long, short = 'y')]
    pub yes: bool,
    /// Don't install the skill.
    #[arg(long)]
    pub no_skill: bool,
}

#[derive(Debug, Args)]
pub struct DoctorArgs {
    /// Only check these clients (repeatable).
    #[arg(long = "client")]
    pub clients: Vec<String>,
}

#[derive(Debug, Args)]
pub struct UninstallArgs {}

fn human(f: Format) -> bool {
    matches!(f, Format::Text | Format::Md)
}

fn confirm(question: &str) -> bool {
    if !(std::io::stdin().is_terminal() && std::io::stderr().is_terminal()) {
        return false;
    }
    eprint!("{question} [y/N] ");
    let mut line = String::new();
    std::io::stdin().read_line(&mut line).is_ok() && matches!(line.trim(), "y" | "Y" | "yes")
}

fn print_plan(plan: &craft_anything_setup::Plan) {
    out(&format!("Register: {}", plan.command.join(" ")));
    for a in &plan.actions {
        let v = serde_json::to_value(a).unwrap_or(Value::Null);
        out(&format!("[{}] {} — {}", v["action"].as_str().unwrap_or_default(), a.display, v["path"].as_str().unwrap_or_default()));
        if let Some(r) = v["reason"].as_str() {
            out(&format!("    {r}"));
        }
        if let Some(r) = v["remediation"].as_str() {
            out(&format!("    → {r}"));
        }
        if matches!(a.action, ActionKind::Create | ActionKind::Update) {
            for l in v["preview"].as_str().unwrap_or_default().lines() {
                out(&format!("    {l}"));
            }
        }
    }
    for s in &plan.skills {
        let v = serde_json::to_value(s).unwrap_or(Value::Null);
        out(&format!("[skill] {}", v["dir"].as_str().unwrap_or_default()));
    }
    for n in &plan.notes {
        out(&format!("note: {n}"));
    }
}

pub fn setup(a: &SetupArgs, f: Format) -> u8 {
    let host = Host::current();
    let command = match craft_anything_setup::default_command() {
        Ok(c) => c,
        Err(e) => return fail(&e, f),
    };
    let req = PlanRequest { clients: a.clients.clone(), all_detected: a.all_detected, command, include_skill: !a.no_skill };
    let plan = match craft_anything_setup::plan(&host, &req) {
        Ok(p) => p,
        Err(e) => return fail(&e, f),
    };
    let status = if plan.blocked {
        "blocked"
    } else if a.dry_run {
        "planned"
    } else if plan.change_count() == 0 {
        "unchanged"
    } else {
        ""
    };
    if !status.is_empty() {
        if human(f) {
            print_plan(&plan);
            out(&format!("status: {status}"));
        } else {
            emit(&json!({"status": status, "plan": plan}), f);
        }
        return if plan.blocked { 1 } else { 0 };
    }
    let approved = a.yes || {
        if human(f) {
            print_plan(&plan);
        }
        confirm(&format!("Apply these {} changes?", plan.change_count()))
    };
    if !approved {
        if human(f) {
            out("status: needs_confirmation (re-run with --yes to apply)");
        } else {
            emit(&json!({"status": "needs_confirmation", "plan": plan}), f);
        }
        return 1;
    }
    let report = craft_anything_setup::apply(&plan);
    if human(f) {
        for r in &report.results {
            let v = serde_json::to_value(r).unwrap_or(Value::Null);
            out(&format!(
                "[{}] {} {}",
                v["outcome"].as_str().unwrap_or_default(),
                v["client"].as_str().unwrap_or_default(),
                v["error"].as_str().unwrap_or_default()
            ));
        }
        out(&format!("status: {}", report.status));
        if !report.restart.is_empty() {
            out(&format!("Restart {} to load Craft Anything.", report.restart.join(", ")));
        }
    } else {
        emit(&serde_json::to_value(&report).unwrap_or(Value::Null), f);
    }
    if matches!(report.status, "configured" | "unchanged") { 0 } else { 1 }
}

pub fn doctor(a: &DoctorArgs, f: Format) -> u8 {
    let host = Host::current();
    let req = DoctorRequest { clients: a.clients.clone(), extra: crate::ai_cmd::doctor_checks(), ..DoctorRequest::default() };
    let report = craft_anything_setup::doctor(&host, &req);
    if human(f) {
        for c in &report.checks {
            let st = match c.status {
                CheckStatus::Ok => "ok",
                CheckStatus::Warn => "warn",
                CheckStatus::Fail => "FAIL",
                CheckStatus::Info => "info",
            };
            out(&format!("[{st}] {}: {}", c.name, c.message));
            if let Some(r) = &c.remediation {
                out(&format!("       → {r}"));
            }
        }
        out(if report.healthy { "healthy" } else { "problems found" });
    } else {
        emit(&serde_json::to_value(&report).unwrap_or(Value::Null), f);
    }
    if report.healthy { 0 } else { 1 }
}

pub fn uninstall(_a: &UninstallArgs, f: Format) -> u8 {
    let report = craft_anything_setup::uninstall(&Host::current());
    let v = serde_json::to_value(&report).unwrap_or(Value::Null);
    if human(f) {
        for r in &report.removed_entries {
            let e = serde_json::to_value(r).unwrap_or(Value::Null);
            out(&format!("removed {} ({})", e["client"].as_str().unwrap_or_default(), e["path"].as_str().unwrap_or_default()));
        }
        for p in &report.removed_skill_files {
            out(&format!("removed {}", p.display()));
        }
        for b in &report.blocking {
            out(&format!("blocked by {} — fix or move that file first", b.display));
        }
        out(&format!("status: {}", report.status));
    } else {
        emit(&v, f);
    }
    if matches!(report.status, "removed" | "nothing_to_remove") { 0 } else { 1 }
}
