//! `doctor`: read-only health checks for the install, app registrations, skills, engines and the
//! MCP server itself.

use crate::clients::{Format, Host, clients, entry_command, is_owned_entry};
use crate::config;
use crate::skill::{self, SkillState};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::path::{Path, PathBuf};
use std::time::Duration;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CheckStatus {
    Ok,
    Warn,
    Fail,
    Info,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Check {
    pub name: String,
    pub status: CheckStatus,
    pub message: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub remediation: Option<String>,
}

impl Check {
    pub fn new(name: impl Into<String>, status: CheckStatus, message: impl Into<String>) -> Check {
        Check { name: name.into(), status, message: message.into(), remediation: None }
    }

    pub fn fix(mut self, r: impl Into<String>) -> Check {
        self.remediation = Some(r.into());
        self
    }
}

#[derive(Debug, Clone)]
pub struct DoctorRequest {
    /// Only these clients (ids); empty = every detected client.
    pub clients: Vec<String>,
    /// The CLI to check and self-test; defaults to this machine's `craft-anything-cli`.
    pub cli_path: Option<PathBuf>,
    /// Checks computed elsewhere (e.g. AI backend reachability from the CLI).
    pub extra: Vec<Check>,
    /// Spawn `<cli> mcp` and talk to it.
    pub self_test: bool,
    /// Look for optional analysis engines.
    pub engines: bool,
}

impl Default for DoctorRequest {
    fn default() -> Self {
        DoctorRequest { clients: Vec::new(), cli_path: None, extra: Vec::new(), self_test: true, engines: true }
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct DoctorReport {
    /// False when any check failed.
    pub healthy: bool,
    pub checks: Vec<Check>,
}

pub fn doctor(host: &Host, req: &DoctorRequest) -> DoctorReport {
    let mut checks = Vec::new();

    // The CLI binary.
    let cli = req.cli_path.clone().or_else(craft_anything_platform::self_cli_path);
    match &cli {
        Some(p) if p.is_file() => checks.push(Check::new("binary", CheckStatus::Ok, format!("craft-anything-cli is at {}", p.display()))),
        Some(p) => checks.push(Check::new("binary", CheckStatus::Fail, format!("{} does not exist.", p.display())).fix("Reinstall Craft Anything.")),
        None => checks.push(
            Check::new("binary", CheckStatus::Fail, "craft-anything-cli was not found.").fix("Install Craft Anything; the CLI ships next to the desktop app."),
        ),
    }
    let on_path = craft_anything_platform::which_all("craft-anything-cli");
    if on_path.len() > 1 {
        let list: Vec<String> = on_path.iter().map(|p| p.display().to_string()).collect();
        checks.push(
            Check::new("binary:duplicates", CheckStatus::Warn, format!("Several copies are on PATH: {}", list.join(", ")))
                .fix("Remove the copies you don't use so every app runs the same version."),
        );
    }

    // Registrations.
    let all = clients(host);
    let explicit = !req.clients.is_empty();
    let selected: Vec<_> = all.iter().filter(|c| if explicit { req.clients.iter().any(|id| c.is(id)) } else { c.detected() }).collect();
    let mut skill_dirs: Vec<PathBuf> = Vec::new();
    for c in &selected {
        let name = format!("registration:{}", c.id);
        if c.format == Format::Manual {
            checks.push(Check::new(name, CheckStatus::Info, format!("{} is set up by hand.", c.display)).fix(c.manual.unwrap_or_default()));
            continue;
        }
        if !skill_dirs.contains(&c.skills_dir) {
            skill_dirs.push(c.skills_dir.clone());
        }
        let setup_cmd = format!("craft-anything-cli setup --client {}", c.id);
        let text = match std::fs::read_to_string(&c.config) {
            Ok(t) => t,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
                let st = if explicit { CheckStatus::Fail } else { CheckStatus::Info };
                checks.push(Check::new(name, st, format!("{} is installed but not connected.", c.display)).fix(setup_cmd));
                continue;
            }
            Err(e) => {
                checks.push(Check::new(name, CheckStatus::Fail, format!("Can't read {}: {e}", c.config.display())).fix("Check the file's permissions."));
                continue;
            }
        };
        let check = match config::read_entry(c, &text) {
            Err(e) => Check::new(name, CheckStatus::Fail, format!("{} can't be parsed: {e}", c.config.display()))
                .fix(format!("Fix {} by hand; setup won't edit a file it can't read.", c.config.display())),
            Ok(None) => {
                Check::new(name, if explicit { CheckStatus::Fail } else { CheckStatus::Info }, format!("{} is installed but not connected.", c.display))
                    .fix(setup_cmd)
            }
            Ok(Some(e)) if !is_owned_entry(&e) => {
                Check::new(name, CheckStatus::Warn, format!("{} has a \"craft-anything\" entry that doesn't launch craft-anything-cli.", c.display))
                    .fix(format!("{setup_cmd} (replaces it)"))
            }
            Ok(Some(e)) => {
                let desired = cli.as_ref().map(|p| c.desired_entry(&[p.display().to_string(), "mcp".into()]));
                let program_ok = entry_command(&e).and_then(|v| v.into_iter().next()).is_some_and(|p| Path::new(&p).is_file());
                if config::is_disabled(c, &text) {
                    Check::new(name, CheckStatus::Warn, format!("{} lists Craft Anything as disabled.", c.display)).fix(setup_cmd)
                } else if !program_ok {
                    Check::new(name, CheckStatus::Fail, format!("{} points to a craft-anything-cli that no longer exists.", c.display)).fix(setup_cmd)
                } else if desired.as_ref() == Some(&e) {
                    Check::new(name, CheckStatus::Ok, format!("{} is connected.", c.display))
                } else {
                    Check::new(name, CheckStatus::Warn, format!("{} is connected to a different copy or shape of the command.", c.display)).fix(setup_cmd)
                }
            }
        };
        checks.push(check);
    }

    // Skills.
    for d in &skill_dirs {
        let name = format!("skill:{}", d.display());
        checks.push(match skill::inspect(d) {
            SkillState::Current => Check::new(name, CheckStatus::Ok, "The Craft Anything skill is installed and current."),
            SkillState::Outdated => Check::new(name, CheckStatus::Warn, "The Craft Anything skill is out of date.").fix("craft-anything-cli setup --yes"),
            SkillState::Missing => Check::new(name, CheckStatus::Info, "The Craft Anything skill isn't installed here.").fix("craft-anything-cli setup --yes"),
            SkillState::Foreign => Check::new(name, CheckStatus::Warn, "Another skill uses the craft-anything folder name."),
        });
    }

    // Optional engines.
    if req.engines {
        let settings = craft_anything_engine::Settings::load();
        for e in craft_anything_engines::ENGINES {
            let name = format!("engine:{}", e.id);
            checks.push(match settings.engine_path(e.id) {
                Some(p) => Check::new(name, CheckStatus::Ok, format!("{}: {}", e.name, p.display())),
                None => Check::new(name, CheckStatus::Info, format!("{} not found (optional; {}).", e.name, e.needed_for)),
            });
        }
    }

    // MCP self-test.
    if req.self_test
        && let Some(p) = cli.as_ref().filter(|p| p.is_file())
    {
        checks.push(mcp_self_test(&p.display().to_string(), &["mcp".to_string()], Duration::from_secs(20)));
    }

    checks.extend(req.extra.iter().cloned());
    let healthy = !checks.iter().any(|c| c.status == CheckStatus::Fail);
    DoctorReport { healthy, checks }
}

/// Start an MCP server over stdio, send `initialize` + `initialized` + `tools/list`, close stdin,
/// and check the answers.
pub fn mcp_self_test(program: &str, args: &[String], timeout: Duration) -> Check {
    let name = "mcp:self-test";
    let reqs = [
        json!({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "craft-anything-doctor", "version": env!("CARGO_PKG_VERSION")}}}),
        json!({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        json!({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
    ];
    let mut input = String::new();
    for r in &reqs {
        input.push_str(&r.to_string());
        input.push('\n');
    }
    let out = match craft_anything_platform::Process::new(program)
        .args(args)
        .stdin_bytes(input.into_bytes())
        .timeout(timeout)
        .stdout_cap(32 * 1024 * 1024)
        .label("craft-anything-cli mcp")
        .run()
    {
        Ok(o) => o,
        Err(e) => {
            return Check::new(name, CheckStatus::Fail, format!("The MCP server didn't answer: {}", e.message))
                .fix(e.remediation.unwrap_or_else(|| "Run this in a terminal to see the error: craft-anything-cli mcp".into()));
        }
    };
    let mut init = None;
    let mut list = None;
    for line in out.stdout_text().lines() {
        let Ok(v) = serde_json::from_str::<Value>(line) else { continue };
        match v.get("id").and_then(Value::as_i64) {
            Some(1) => init = Some(v),
            Some(2) => list = Some(v),
            _ => {}
        }
    }
    let Some(init) = init else {
        return Check::new(name, CheckStatus::Fail, "The MCP server sent no reply to initialize.")
            .fix("Run this in a terminal to see the error: craft-anything-cli mcp");
    };
    let server = init["result"]["serverInfo"]["name"].as_str().unwrap_or_default();
    let protocol = init["result"]["protocolVersion"].as_str().unwrap_or_default();
    if server != "craft-anything" || protocol.is_empty() {
        return Check::new(name, CheckStatus::Fail, format!("Unexpected initialize reply (server {server:?}, protocol {protocol:?})."));
    }
    let tools: Vec<&str> =
        list.as_ref().and_then(|l| l["result"]["tools"].as_array()).map(|a| a.iter().filter_map(|t| t["name"].as_str()).collect()).unwrap_or_default();
    if tools.is_empty() {
        return Check::new(name, CheckStatus::Fail, "The MCP server listed no tools.");
    }
    // The session tool under any name a client may report it by.
    let registry = craft_anything_engine::registry::Registry::with_all_tools();
    let session = craft_anything_engine::tools::session_tools::SESSION_TOOL;
    if !tools.iter().any(|t| registry.canonical(t) == Some(session)) {
        return Check::new(name, CheckStatus::Fail, format!("The MCP server's tool list is missing {session}."));
    }
    Check::new(name, CheckStatus::Ok, format!("MCP server answered (protocol {protocol}, {} tools listed).", tools.len()))
}

#[cfg(all(test, unix))]
mod tests {
    use super::*;

    fn sh(script: &str) -> Check {
        mcp_self_test("sh", &["-c".to_string(), script.to_string()], Duration::from_secs(5))
    }

    #[test]
    fn self_test_against_fake_servers() {
        let good = r#"cat >/dev/null; echo '{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2025-06-18","serverInfo":{"name":"craft-anything","version":"0"}}}'; echo '{"jsonrpc":"2.0","id":2,"result":{"tools":[{"name":"core_session_show"}]}}'"#;
        assert_eq!(sh(good).status, CheckStatus::Ok);
        let wrong = r#"echo '{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"x","serverInfo":{"name":"other"}}}'"#;
        assert_eq!(sh(wrong).status, CheckStatus::Fail);
        assert_eq!(sh("echo nonsense").status, CheckStatus::Fail);
        let no_tools = r#"echo '{"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"1","serverInfo":{"name":"craft-anything"}}}'"#;
        assert_eq!(sh(no_tools).status, CheckStatus::Fail);
        let hang = mcp_self_test("sleep", &["30".to_string()], Duration::from_millis(300));
        assert_eq!(hang.status, CheckStatus::Fail);
        assert_eq!(mcp_self_test("/no/such/craft-anything-cli", &[], Duration::from_secs(1)).status, CheckStatus::Fail);
    }
}
