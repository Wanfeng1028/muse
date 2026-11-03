//! End-to-end setup tests on a temporary home with fixture configs that carry comments.

use crate::plan::apply_with;
use crate::*;
use craft_anything_evidence::ToolError;
use std::path::{Path, PathBuf};

const CLAUDE: &str =
    "// Claude Code state\n{\n  \"numStartups\": 3, /* keep */\n  \"mcpServers\": {\n    \"other\": {\"command\": \"other-server\"}, // theirs\n  },\n}\n";
const CODEX: &str = "# Codex config\nmodel = \"o\" # chosen\n\n[mcp_servers.other]\ncommand = \"other-server\" # theirs\n";
const HERMES: &str = "# Hermes\nmodel: x # inline\nmcp_servers:\n  # friend\n  other:\n    command: other-server\n";

struct Fx {
    _dir: tempfile::TempDir,
    host: Host,
    cli: PathBuf,
}

fn fixture() -> Fx {
    let dir = tempfile::tempdir().unwrap();
    let home = dir.path().to_path_buf();
    let mut host = Host::with_home(&home);
    host.os = Os::Linux;
    std::fs::create_dir_all(home.join(".claude")).unwrap();
    std::fs::write(home.join(".claude.json"), CLAUDE).unwrap();
    std::fs::create_dir_all(home.join(".codex")).unwrap();
    std::fs::write(home.join(".codex/config.toml"), CODEX).unwrap();
    std::fs::create_dir_all(home.join(".hermes")).unwrap();
    std::fs::write(home.join(".hermes/config.yaml"), HERMES).unwrap();
    std::fs::create_dir_all(home.join(".cursor")).unwrap(); // detected, no config yet
    let cli = home.join("bin").join("craft-anything-cli");
    std::fs::create_dir_all(cli.parent().unwrap()).unwrap();
    std::fs::write(&cli, "#!/bin/sh\n").unwrap();
    Fx { _dir: dir, host, cli }
}

fn req(fx: &Fx, clients: &[&str]) -> PlanRequest {
    PlanRequest {
        clients: clients.iter().map(|s| s.to_string()).collect(),
        all_detected: clients.is_empty(),
        command: vec![fx.cli.display().to_string(), "mcp".into()],
        include_skill: true,
    }
}

fn read(p: impl AsRef<Path>) -> String {
    std::fs::read_to_string(p).unwrap()
}

#[test]
fn detects_installed_clients() {
    let fx = fixture();
    let d = detected(&fx.host);
    for id in ["claude_code", "codex", "hermes", "cursor"] {
        assert!(d.contains(&id), "{id}");
    }
    assert!(!d.contains(&"windsurf"));
}

#[test]
fn full_setup_preserves_comments_backs_up_and_is_idempotent() {
    let fx = fixture();
    let h = &fx.host.home;
    let p = plan(&fx.host, &req(&fx, &[])).unwrap();
    assert!(!p.blocked);
    let kinds: Vec<(String, ActionKind)> = p.actions.iter().map(|a| (a.client.clone(), a.action)).collect();
    assert!(kinds.contains(&("cursor".into(), ActionKind::Create)));
    assert!(kinds.contains(&("codex".into(), ActionKind::Update)));
    assert!(p.actions.iter().find(|a| a.client == "codex").unwrap().preview.contains("+ "));
    // planning writes nothing
    assert_eq!(read(h.join(".codex/config.toml")), CODEX);

    let r = apply(&p);
    assert_eq!(r.status, "configured", "{r:?}");
    let claude = read(h.join(".claude.json"));
    assert!(claude.contains("// Claude Code state") && claude.contains("/* keep */") && claude.contains("// theirs"));
    let codex = read(h.join(".codex/config.toml"));
    assert!(codex.contains("# chosen") && codex.contains("# theirs") && codex.contains("startup_timeout_sec = 30"));
    let hermes = read(h.join(".hermes/config.yaml"));
    assert!(hermes.contains("# friend") && hermes.contains("enabled: true"));
    assert!(h.join(".cursor/mcp.json").exists());
    // backups hold the originals; created files get none
    assert_eq!(read(h.join(".codex/config.toml.craft-anything.backup")), CODEX);
    assert!(!h.join(".cursor/mcp.json.craft-anything.backup").exists());
    // skill landed in the shared folder and Claude Code's own
    assert!(h.join(".agents/skills/craft-anything/SKILL.md").exists());
    assert!(h.join(".claude/skills/craft-anything/SKILL.md").exists());
    assert!(h.join(".hermes/skills/craft-anything/SKILL.md").exists());
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt as _;
        assert_eq!(std::fs::metadata(h.join(".codex/config.toml")).unwrap().permissions().mode() & 0o777, 0o600);
    }

    // Second run: nothing to do.
    let p2 = plan(&fx.host, &req(&fx, &[])).unwrap();
    assert_eq!(p2.change_count(), 0, "{:?}", p2.actions.iter().map(|a| (&a.client, a.action)).collect::<Vec<_>>());
    assert_eq!(apply(&p2).status, "unchanged");
    // With no scope, setup refreshes exactly the apps we already own.
    let refresh = plan(&fx.host, &PlanRequest { clients: vec![], all_detected: false, ..req(&fx, &[]) }).unwrap();
    assert_eq!(refresh.actions.len(), 4);

    // A new command updates; the first backup is never overwritten.
    let mut moved = req(&fx, &["codex"]);
    moved.command = vec!["/opt/new/craft-anything-cli".into(), "mcp".into()];
    let r = apply(&plan(&fx.host, &moved).unwrap());
    assert_eq!(r.status, "configured");
    assert_eq!(read(h.join(".codex/config.toml.craft-anything.backup")), CODEX);

    // Doctor sees the aligned registrations and the stale one.
    let rep = doctor(&fx.host, &DoctorRequest { cli_path: Some(fx.cli.clone()), self_test: false, engines: false, ..Default::default() });
    let get = |n: &str| rep.checks.iter().find(|c| c.name == n).unwrap().status;
    assert_eq!(get("registration:claude_code"), CheckStatus::Ok);
    assert_eq!(get("registration:codex"), CheckStatus::Fail); // points at a missing binary
    assert!(!rep.healthy);

    // Uninstall removes only ours and keeps comments and the other servers.
    let u = uninstall(&fx.host);
    assert_eq!(u.status, "removed", "{u:?}");
    let claude = read(h.join(".claude.json"));
    assert!(claude.contains("// theirs") && claude.contains("other-server") && !claude.contains("craft-anything-cli"));
    let codex = read(h.join(".codex/config.toml"));
    assert!(codex.contains("# theirs") && !codex.contains("craft-anything-cli"));
    let hermes = read(h.join(".hermes/config.yaml"));
    assert_eq!(hermes, HERMES);
    assert!(!h.join(".agents/skills/craft-anything/SKILL.md").exists());
    assert_eq!(uninstall(&fx.host).status, "nothing_to_remove");
}

#[test]
fn malformed_config_blocks_plan_and_uninstall() {
    let fx = fixture();
    let h = &fx.host.home;
    assert_eq!(apply(&plan(&fx.host, &req(&fx, &["cursor"])).unwrap()).status, "configured");
    std::fs::write(h.join(".codex/config.toml"), "model = [broken").unwrap();
    let p = plan(&fx.host, &req(&fx, &["codex", "claude_code"])).unwrap();
    assert!(p.blocked);
    assert_eq!(p.actions.iter().find(|a| a.client == "codex").unwrap().action, ActionKind::Invalid);
    let r = apply(&p);
    assert_eq!(r.status, "blocked");
    assert_eq!(read(h.join(".claude.json")), CLAUDE);
    let u = uninstall(&fx.host);
    assert_eq!(u.status, "blocked");
    assert!(read(h.join(".cursor/mcp.json")).contains("craft-anything-cli"));
}

/// #238: Pi's folder exists but its mcp.json doesn't yet; setup creates it. An empty file is
/// still refused.
#[test]
fn pi_config_is_created_when_missing() {
    let fx = fixture();
    let pi = fx.host.home.join(".pi/agent/mcp.json");
    std::fs::create_dir_all(pi.parent().unwrap()).unwrap();
    let p = plan(&fx.host, &req(&fx, &["pi"])).unwrap();
    assert!(!p.blocked, "{p:?}");
    assert_eq!(apply(&p).status, "configured");
    let v: serde_json::Value = serde_json::from_str(&read(&pi)).unwrap();
    assert_eq!(v["mcpServers"]["craft-anything"]["args"][0], "mcp");
    std::fs::write(&pi, "").unwrap();
    assert!(plan(&fx.host, &req(&fx, &["pi"])).unwrap().blocked);
}

#[test]
fn strict_json_client_rejects_comments() {
    let fx = fixture();
    let pi = fx.host.home.join(".pi/agent/mcp.json");
    std::fs::create_dir_all(pi.parent().unwrap()).unwrap();
    std::fs::write(&pi, "{ // nope\n}").unwrap();
    let p = plan(&fx.host, &req(&fx, &["pi"])).unwrap();
    assert!(p.blocked);
    std::fs::write(&pi, "{\"mcpServers\": {}}").unwrap();
    let p = plan(&fx.host, &req(&fx, &["pi"])).unwrap();
    assert!(!p.blocked);
    assert_eq!(apply(&p).status, "configured");
    let v: serde_json::Value = serde_json::from_str(&read(&pi)).unwrap();
    assert_eq!(v["mcpServers"]["craft-anything"]["type"], "stdio");
}

#[test]
fn failed_readback_rolls_everything_back() {
    let fx = fixture();
    let h = &fx.host.home;
    let p = plan(&fx.host, &req(&fx, &["claude_code", "cursor", "codex"])).unwrap();
    // Writes "succeed" but the third file's content is wrong, so its read-back fails.
    let calls = std::cell::Cell::new(0);
    let bad = |path: &Path, b: &[u8]| -> Result<(), ToolError> {
        calls.set(calls.get() + 1);
        if calls.get() == 3 { craft_anything_platform::write_atomic(path, b"[mcp_servers]\n") } else { craft_anything_platform::write_atomic(path, b) }
    };
    let r = apply_with(&p, &bad);
    assert_eq!(r.status, "failed");
    assert_eq!(read(h.join(".claude.json")), CLAUDE);
    assert_eq!(read(h.join(".codex/config.toml")), CODEX);
    assert!(!h.join(".cursor/mcp.json").exists(), "created file must be removed");
    assert!(r.results.iter().any(|x| x.outcome == Outcome::RolledBack));
    assert!(r.results.iter().any(|x| x.outcome == Outcome::Failed));
}

#[test]
fn file_changed_after_plan_is_refused() {
    let fx = fixture();
    let p = plan(&fx.host, &req(&fx, &["codex"])).unwrap();
    std::fs::write(fx.host.home.join(".codex/config.toml"), "# edited meanwhile\n").unwrap();
    let r = apply(&p);
    assert_eq!(r.status, "failed");
    assert_eq!(read(fx.host.home.join(".codex/config.toml")), "# edited meanwhile\n");
}

#[test]
fn unknown_client_and_manual_client() {
    let fx = fixture();
    let e = plan(&fx.host, &req(&fx, &["nope"])).unwrap_err();
    assert!(e.remediation.unwrap().contains("claude_code"));
    let p = plan(&fx.host, &req(&fx, &["dsh"])).unwrap();
    assert_eq!(p.actions[0].action, ActionKind::Manual);
    assert!(p.actions[0].remediation.is_some());
    assert!(!p.blocked);
    let p = plan(&fx.host, &req(&fx, &["claude-code"])).unwrap();
    assert_eq!(p.actions[0].client, "claude_code");
}

#[test]
fn foreign_entry_with_our_name_is_replaced_but_not_uninstalled() {
    let fx = fixture();
    let cursor = fx.host.home.join(".cursor/mcp.json");
    std::fs::write(&cursor, "{\"mcpServers\": {\"craft-anything\": {\"command\": \"npx\", \"args\": [\"something\"]}}}").unwrap();
    assert_eq!(uninstall(&fx.host).status, "nothing_to_remove");
    let p = plan(&fx.host, &req(&fx, &["cursor"])).unwrap();
    assert!(p.actions[0].reason.as_deref().unwrap_or_default().contains("replaced"));
}
