//! Cutter sessions the person shares with us (`=h& 9090` in Cutter's console), through
//! [`craft_anything_engines::cutter`]: find which ports answer, and run read-only Rizin commands
//! (the same allow-list as native_rizin_command_run) in what they have open. Only this computer is
//! contacted; nothing is sent unless the person opened the session to us.

use super::external_disasm_tools::check_rizin_command;
use super::native_common::{params_json, spec};
use super::static_input::builder;
use crate::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use craft_anything_engines::cutter::{self, DEFAULT_PORT, HOW_TO_OPEN};
use craft_anything_evidence::{Authority, Confidence, Coverage, Limitation, Subject, ToolError};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::time::Duration;

pub fn specs() -> Vec<ToolSpec> {
    vec![
        spec(
            "native_cutter_sessions_list",
            "List shared Cutter sessions",
            "Find Cutter (or Rizin) sessions shared on this computer: each port given (default 9090) is asked what it has open (file, format, architecture). A session is shared by running `=h& 9090` in Cutter's console; nothing else is reachable.",
            "See which Cutter windows you've shared.",
            Toolset::Native,
            Effects::ACCESSES_NETWORK | Effects::IDEMPOTENT,
            Requires::Nothing,
            schema_of::<ListParams>,
            native_cutter_sessions_list,
        ),
        spec(
            "native_cutter_command_run",
            "Cutter command",
            "Run one read-only Rizin command in a shared Cutter session (port, default 9090) and return its text, paged by lines: information (i…), printing and disassembly (p…, x…), analysis (a…), search (/…), seek (s…), flags (f…), comments (C…), types (t…) and help (?…). Writes, shell escapes, scripts, debugging, pipes and chaining are refused. Analysis and seek commands change what the Cutter window shows, as if typed in its console.",
            "Ask a Cutter window you've shared for information.",
            Toolset::Native,
            Effects::ACCESSES_NETWORK | Effects::MUTATES_TARGET,
            Requires::Nothing,
            schema_of::<CommandParams>,
            native_cutter_command_run,
        ),
    ]
}

fn d_port() -> u16 {
    DEFAULT_PORT
}

fn d_limit() -> usize {
    2000
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ListParams {
    /// Ports to ask (default [9090]); at most 16.
    #[serde(default)]
    pub ports: Vec<u16>,
}

#[derive(Debug, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct CommandParams {
    /// One read-only Rizin command, for example `afl`, `pdf @ main` or `iz`.
    pub command: String,
    /// The shared session's port (default 9090).
    #[serde(default = "d_port")]
    pub port: u16,
    /// First output line of the page.
    #[serde(default)]
    pub offset: usize,
    /// Lines per page (1–20000, default 2000).
    #[serde(default = "d_limit")]
    pub limit: usize,
}

fn cutter_subject(port: u16) -> Subject {
    Subject { kind: "session".into(), sha256: None, name: Some(format!("Cutter session on port {port}")) }
}

fn native_cutter_sessions_list(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ListParams = parse_params(params)?;
    if p.ports.len() > 16 || p.ports.contains(&0) {
        return Err(ToolError::invalid("ports takes up to 16 port numbers (1–65535)"));
    }
    let ports = if p.ports.is_empty() { vec![DEFAULT_PORT] } else { p.ports.clone() };
    ctx.report(None, "Looking for shared Cutter sessions");
    let sessions: Vec<Value> = ports.iter().filter_map(|port| cutter::probe(*port)).collect();
    let mut lims = vec![Limitation::new("shared_only", "Only sessions shared with `=h& <port>` in Cutter's console, on the ports asked, can be found.")];
    if sessions.is_empty() {
        lims.push(Limitation::new("none_found", HOW_TO_OPEN));
    }
    let e = builder(ctx, "native_cutter_sessions_list", Subject { kind: "session".into(), sha256: None, name: Some("Cutter".into()) }, params_json(&p))
        .result(json!({"ports_asked": ports, "sessions": sessions, "how_to_share": HOW_TO_OPEN}))
        .summary(format!("{} shared Cutter session(s) found on {} port(s).", sessions.len(), ports.len()))
        .confidence(Confidence::Observed)
        .authority(Authority::OutsideService)
        .limitations(lims)
        .coverage(Coverage::complete(ports.len() as u64))
        .build()?;
    Ok(ToolOutput::evidence(e))
}

fn native_cutter_command_run(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: CommandParams = parse_params(params)?;
    let cmd = check_rizin_command(&p.command)?.to_string();
    if p.port == 0 {
        return Err(ToolError::invalid("port must be 1–65535"));
    }
    ctx.report(None, format!("cutter: {cmd}"));
    let (text, truncated) = cutter::command(p.port, &cmd, Duration::from_secs(120))?;
    let limit = p.limit.clamp(1, 20_000);
    let total = text.lines().count();
    let page: Vec<&str> = text.lines().skip(p.offset).take(limit).collect();
    let mut lims = vec![
        Limitation::new("live_session", "Output reflects the Cutter window at this moment; the person may change it at any time."),
        Limitation::new("raw_tool_output", "This is Rizin's own text; its format can change between versions."),
    ];
    if truncated {
        lims.push(Limitation::new("output_capped", "More than 4 MiB of text arrived; the rest was cut off. Narrow the command (an address or a count)."));
    }
    let e = builder(ctx, "native_cutter_command_run", cutter_subject(p.port), params_json(&p))
        .result(json!({"port": p.port, "command": cmd, "total_lines": total, "offset": p.offset, "limit": limit, "output": page.join("\n")}))
        .summary(format!("cutter `{cmd}`: {total} lines of output."))
        .confidence(Confidence::Observed)
        .authority(Authority::OutsideService)
        .limitations(lims)
        .coverage(Coverage::page(page.len() as u64, total as u64, p.offset as u64))
        .build()?;
    Ok(ToolOutput::evidence(e))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{CallOptions, Caller, Engine};

    #[test]
    fn only_read_only_commands_reach_a_session() {
        let e = Engine::new(crate::testing::session());
        let call = |v: Value| e.call("native_cutter_command_run", v, CallOptions::new(Caller::Mcp));
        // Refused before anything is contacted.
        for bad in ["!calc", "wx 90 @ main", "afl; !calc", "pd 1 > out.txt", "dc", "", "aei"] {
            assert!(call(json!({"command": bad})).is_err(), "{bad}");
        }
        assert!(call(json!({"command": "afl", "port": 0})).is_err());
        assert!(e.call("native_cutter_sessions_list", json!({"ports": [0]}), CallOptions::new(Caller::Mcp)).is_err());
    }

    #[test]
    fn no_session_is_found_where_nothing_listens() {
        let free = std::net::TcpListener::bind("127.0.0.1:0").unwrap().local_addr().unwrap().port();
        let e = Engine::new(crate::testing::session());
        let Ok(ToolOutput::Evidence(ev)) = e.call("native_cutter_sessions_list", json!({"ports": [free]}), CallOptions::new(Caller::Mcp)) else { panic!() };
        let r = serde_json::to_value(&*ev).unwrap();
        assert_eq!(r["result"]["sessions"], json!([]), "{r}");
        assert!(e.call("native_cutter_command_run", json!({"command": "afl", "port": free}), CallOptions::new(Caller::Mcp)).is_err());
    }
}
