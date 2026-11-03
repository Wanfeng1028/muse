//! Plugins end to end: Craft Anything's own MCP server (`craft-anything-cli mcp`) configured as a
//! plugin, refreshed, listed and called through the CLI. Everything stays in temp folders.

use craft_anything_platform::process::{Output, Process};
use serde_json::Value;
use std::time::Duration;

fn cli(args: &[&str], config: &std::path::Path) -> Output {
    Process::new(env!("CARGO_BIN_EXE_craft-anything-cli")).args(args).env("CRAFT_ANYTHING_CONFIG_DIR", config).timeout(Duration::from_secs(120)).run().unwrap()
}

#[test]
fn an_mcp_server_becomes_a_toolset_of_proxied_tools() {
    let cfg = tempfile::tempdir().unwrap();
    let projects = tempfile::tempdir().unwrap();
    let exe = env!("CARGO_BIN_EXE_craft-anything-cli");
    std::fs::write(
        cfg.path().join("config.toml"),
        format!("version = 1\n\n[[plugins.mcp]]\nid = \"selfmcp\"\nname = \"Itself\"\ncommand = '{exe}'\nargs = [\"mcp\", \"--all-tools\"]\nconsent = false\n"),
    )
    .unwrap();

    // Before a refresh nothing is cached, so no proxied tools.
    let list = cli(&["plugins-list", "--format", "json"], cfg.path());
    assert!(list.success, "{}", list.stdout_text());
    let v: Value = serde_json::from_slice(&list.stdout).unwrap();
    assert_eq!(v["result"]["plugins"][0]["id"], "selfmcp");
    assert_eq!(v["result"]["plugins"][0]["cached_tools"].as_array().map(Vec::len), Some(0));

    // Refreshing starts the server (it's a program, so it needs --allow-run) and caches its tools.
    assert!(!cli(&["plugins-refresh", "--format", "json"], cfg.path()).success, "refused without consent");
    let r = cli(&["plugins-refresh", "--allow-run", "--format", "json"], cfg.path());
    assert!(r.success, "{}", r.stdout_text());
    let v: Value = serde_json::from_slice(&r.stdout).unwrap();
    let tools = v["result"]["refreshed"][0]["tools"].as_array().cloned().unwrap_or_default();
    assert!(tools.iter().any(|t| t == "project_list"), "{v}");

    // The next start offers them as a toolset of its own.
    let c = cli(&["commands", "--format", "json"], cfg.path());
    let v: Value = serde_json::from_slice(&c.stdout).unwrap();
    let ours = v.as_array().unwrap().iter().find(|c| c["command"] == "selfmcp-project-list").cloned();
    assert_eq!(ours.as_ref().map(|c| c["toolset"].clone()), Some(Value::from("selfmcp")), "{v}");

    // A plugin's tool may look at anything, so Clean room doesn't run it.
    let dir = projects.path().to_str().unwrap();
    let refused = cli(&["selfmcp-project-list", "--projects-dir", dir, "--format", "json"], cfg.path());
    let v: Value = serde_json::from_slice(&refused.stdout).unwrap();
    assert_eq!(v["error"]["details"]["reason"], "clean_room", "{v}");

    // In Deep mode a call goes through the server and comes back as evidence from an external service.
    let call = cli(&["--deep", "selfmcp-project-list", "--projects-dir", dir, "--format", "json"], cfg.path());
    assert!(call.success, "{}", call.stdout_text());
    let v: Value = serde_json::from_slice(&call.stdout).unwrap();
    assert_eq!(v["authority"], "outside-service", "{v}");
    assert!(v.to_string().contains("projects_dir"), "{v}");
}
