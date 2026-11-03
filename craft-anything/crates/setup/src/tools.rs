//! Connecting Craft Anything to coding-agent apps, as tools (registered next to the engine's own
//! through `Engine::shared`), so it can be done without the app: what would change, applying it,
//! the health checks, and removing our entries again. Ids follow docs/tool-ids.md.

use crate::{DoctorRequest, Host, PlanRequest};
use craft_anything_engine::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use craft_anything_evidence::ToolError;
use schemars::JsonSchema;
use serde::Deserialize;
use serde_json::{Value, json};

pub fn specs() -> Vec<ToolSpec> {
    let spec = |id, title, summary, beginner, effects, input_schema, run| ToolSpec {
        id,
        title,
        summary,
        beginner,
        toolset: Toolset::Setup,
        effects,
        requires: Requires::Nothing,
        input_schema,
        run,
    };
    // Applying and removing change other apps' config files on this computer: they ask first.
    let changes_apps = Effects::WRITES_FILESYSTEM.union(Effects::EXECUTES_FOREIGN_CODE);
    vec![
        spec(
            "setup_plan",
            "Plan connecting agent apps",
            "What connecting Craft Anything to coding-agent apps (Claude Code, Codex, Cursor…) would change: each config file, the lines that change, and the skill files. Writes nothing.",
            "Shows what connecting your agent apps would change.",
            Effects::READ_ONLY,
            schema_of::<SetupParams>,
            setup_plan,
        ),
        spec(
            "setup_apply",
            "Connect agent apps",
            "Connect Craft Anything to coding-agent apps: register its MCP server in their config files (backing each up first) and install the skill. Changes other apps' files, so it asks first.",
            "Connects your agent apps to Craft Anything.",
            changes_apps,
            schema_of::<SetupParams>,
            setup_apply,
        ),
        spec(
            "setup_doctor",
            "Check the setup",
            "Check the install, each agent app's registration, engines, and that the MCP server answers.",
            "Checks that everything is set up right.",
            Effects::LAUNCHES_PROCESS,
            schema_of::<DoctorParams>,
            setup_doctor,
        ),
        spec(
            "setup_uninstall",
            "Disconnect agent apps",
            "Remove Craft Anything's entries and skill from every agent app's config. Changes other apps' files, so it asks first.",
            "Disconnects your agent apps.",
            changes_apps.union(Effects::MAY_DISCARD_DATA),
            schema_of::<NoParams>,
            setup_uninstall,
        ),
    ]
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct SetupParams {
    /// Client ids to set up (claude_code, codex, cursor…); empty refreshes the ones already set up.
    #[serde(default)]
    pub clients: Vec<String>,
    /// Every agent app found on this computer.
    #[serde(default)]
    pub all_detected: bool,
    /// Also install the skill (default true).
    #[serde(default = "yes")]
    pub skill: bool,
}

fn yes() -> bool {
    true
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct DoctorParams {
    /// Only these clients; empty checks every detected one.
    #[serde(default)]
    pub clients: Vec<String>,
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct NoParams {}

fn the_plan(p: &SetupParams) -> Result<crate::Plan, ToolError> {
    let req = PlanRequest { clients: p.clients.clone(), all_detected: p.all_detected, command: crate::default_command()?, include_skill: p.skill };
    crate::plan(&Host::current(), &req)
}

fn setup_plan(_ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: SetupParams = parse_params(params)?;
    let plan = the_plan(&p)?;
    Ok(ToolOutput::Value(json!({"changes": plan.change_count(), "blocked": plan.blocked, "plan": plan})))
}

fn setup_apply(_ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: SetupParams = parse_params(params)?;
    let plan = the_plan(&p)?;
    if plan.blocked {
        return Ok(ToolOutput::Value(json!({"status": "blocked", "plan": plan})));
    }
    Ok(ToolOutput::Value(serde_json::to_value(crate::apply(&plan)).unwrap_or(Value::Null)))
}

fn setup_doctor(_ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: DoctorParams = parse_params(params)?;
    let req = DoctorRequest { clients: p.clients, ..DoctorRequest::default() };
    Ok(ToolOutput::Value(serde_json::to_value(crate::doctor(&Host::current(), &req)).unwrap_or(Value::Null)))
}

fn setup_uninstall(_ctx: &mut Ctx<'_>, _params: Value) -> Result<ToolOutput, ToolError> {
    Ok(ToolOutput::Value(serde_json::to_value(crate::uninstall(&Host::current())).unwrap_or(Value::Null)))
}

#[cfg(test)]
mod tests {
    use super::*;
    use craft_anything_engine::{CallOptions, Caller, Engine};

    // These tools read and change real agent apps' configs, so tests never call them for real
    // (docs/pitfalls.md): only registration, consent and input checks.
    #[test]
    fn setup_tools_are_registered_and_changes_ask_first() {
        let e = Engine::shared(craft_anything_engine::testing::session(), specs());
        for id in ["setup_plan", "setup_apply", "setup_doctor", "setup_uninstall"] {
            assert!(e.registry().get(id).is_some(), "{id}");
        }
        for id in ["setup_apply", "setup_uninstall"] {
            let err = e.call(id, json!({}), CallOptions::new(Caller::Mcp)).unwrap_err();
            assert_eq!(err.code, craft_anything_evidence::ErrorCode::ConsentRequired, "{id}");
        }
        assert!(e.call("setup_plan", json!({"nope": 1}), CallOptions::new(Caller::Mcp)).is_err(), "unknown fields refused");
    }
}
