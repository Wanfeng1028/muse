//! Connect Craft Anything to coding-agent apps: detect them, plan the change, merge our MCP
//! server entry into their config without disturbing anything else (comments included), back up,
//! verify, roll back on failure, install our skill, check health (`doctor`) and uninstall.
//!
//! Typical flow (what `craft-anything-cli setup` does):
//! ```no_run
//! use craft_anything_setup::*;
//! let host = Host::current();
//! let req = PlanRequest { clients: vec!["codex".into()], all_detected: false, command: default_command()?, include_skill: true };
//! let plan = plan(&host, &req)?;      // read-only; print it for --dry-run
//! if !plan.blocked { let report = apply(&plan); }
//! # Ok::<(), craft_anything_evidence::ToolError>(())
//! ```
#![deny(clippy::unwrap_used, clippy::expect_used, clippy::panic, clippy::unimplemented, clippy::todo, clippy::unreachable)]

pub mod clients;
pub mod config;
pub mod doctor;
pub mod plan;
pub mod skill;
pub mod tools;
pub mod yaml;

pub use clients::{Client, Format, Host, Os, SERVER_NAME, Shape, clients, is_owned_entry};
pub use doctor::{Check, CheckStatus, DoctorReport, DoctorRequest, doctor, mcp_self_test};
pub use plan::{Action, ActionKind, ApplyReport, FileResult, Outcome, Plan, PlanRequest, SkillPlan, UninstallReport, apply, default_command, plan, uninstall};

/// Ids of the clients detected on this host.
pub fn detected(host: &Host) -> Vec<&'static str> {
    clients(host).into_iter().filter(|c| c.detected()).map(|c| c.id).collect()
}

#[cfg(test)]
mod tests;
