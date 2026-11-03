//! End-to-end tests of the built binary (run through the process runner).

use craft_anything_platform::process::{Output, Process};
use serde_json::{Value, json};
use std::time::Duration;

fn cli(args: &[&str], config: &std::path::Path) -> Output {
    Process::new(env!("CARGO_BIN_EXE_craft-anything-cli")).args(args).env("CRAFT_ANYTHING_CONFIG_DIR", config).timeout(Duration::from_secs(60)).run().unwrap()
}

#[test]
fn commands_and_exit_codes() {
    let cfg = tempfile::tempdir().unwrap();
    let out = cli(&["commands", "--format", "json"], cfg.path());
    assert!(out.success);
    let v: Value = serde_json::from_slice(&out.stdout).unwrap();
    assert!(v.as_array().unwrap().iter().any(|c| c["command"] == "core-session-show"));
    assert_eq!(cli(&["no-such-tool"], cfg.path()).code, Some(2));
    assert_eq!(cli(&["--bogus-flag"], cfg.path()).code, Some(2));
    let fail = cli(&["core-finding-record", "--statement", "x", "--evidence-ids", "ev_nope"], cfg.path());
    assert_eq!(fail.code, Some(1));
    let e: Value = serde_json::from_slice(&fail.stdout).unwrap();
    assert_eq!(e["error"]["code"], "bad_input");
}

/// #249: in Clean room a target tool the mode refuses was listed as available, because nothing
/// being open yet was waived for every target tool.
#[test]
fn capabilities_keep_the_clean_room_refusal() {
    let cfg = tempfile::tempdir().unwrap();
    let tool = |args: &[&str], id: &str| {
        let out = cli(args, cfg.path());
        let v: Value = serde_json::from_slice(&out.stdout).unwrap();
        let tools = v["toolsets"].as_array().unwrap().iter().flat_map(|t| t["tools"].as_array().unwrap().clone());
        tools.into_iter().find(|t| t["tool"] == id).unwrap_or_else(|| panic!("{id} not in {v}"))
    };
    let clean = tool(&["--format", "json", "capabilities"], "native_function_pseudocode");
    assert_eq!((clean["available"].as_bool(), clean["needs_target"].as_bool()), (Some(false), Some(true)), "{clean}");
    assert!(clean["reason"].as_str().is_some_and(|r| !r.is_empty()), "{clean}");
    let deep = tool(&["--deep", "--format", "json", "capabilities"], "native_function_pseudocode");
    assert_eq!((deep["available"].as_bool(), deep["reason"].is_null()), (Some(true), true), "{deep}");
}

/// After the tool name, `--project` is the tool's own option when it has one (it used to be taken
/// as the global investigation folder, which was then created there).
#[test]
fn a_tools_own_project_option_reaches_the_tool() {
    let cfg = tempfile::tempdir().unwrap();
    let folder = tempfile::tempdir().unwrap();
    let out = cli(&["project-show", "--project", folder.path().to_str().unwrap()], cfg.path());
    let v: Value = serde_json::from_slice(&out.stdout).unwrap();
    // project_show read the folder (it isn't a project, so it says so) instead of missing its option.
    let msg = v["error"]["message"].as_str().unwrap_or_default();
    assert!(!msg.contains("missing field") && !msg.contains("`project`"), "{v}");
    assert_eq!(std::fs::read_dir(folder.path()).unwrap().count(), 0, "no investigation was created in the folder");
}

#[test]
fn target_tools_open_then_close_and_project_journal() {
    let cfg = tempfile::tempdir().unwrap();
    let dir = tempfile::tempdir().unwrap();
    let file = dir.path().join("sample.bin");
    std::fs::write(&file, b"\x7fELF not really").unwrap();
    let proj = dir.path().join("p.cany");
    let out = cli(&["--deep", "native-cursor-show", file.to_str().unwrap(), "--format", "json", "--project", proj.to_str().unwrap()], cfg.path());
    assert!(out.success, "{}", out.stdout_text());
    let v: Value = serde_json::from_slice(&out.stdout).unwrap();
    assert_eq!(v["result"]["document"], "sample.bin");
    let days: Vec<_> = std::fs::read_dir(proj.join("journal")).unwrap().collect();
    assert_eq!(days.len(), 1);
}

#[test]
fn clean_room_refuses_to_look_inside_and_says_how_to_turn_on_deep_mode() {
    let cfg = tempfile::tempdir().unwrap();
    let dir = tempfile::tempdir().unwrap();
    let file = dir.path().join("sample.bin");
    std::fs::write(&file, b"\x7fELF not really").unwrap();
    let out = cli(&["core-target-open", file.to_str().unwrap()], cfg.path());
    assert_eq!(out.code, Some(1), "{}", out.stdout_text());
    let v: Value = serde_json::from_slice(&out.stdout).unwrap();
    assert_eq!(v["error"]["details"]["reason"], "clean_room", "{v}");
    assert!(v["error"]["remediation"].as_str().unwrap_or_default().contains("--deep"), "{v}");
    // --deep is for this run only: nothing is saved.
    assert!(cli(&["--deep", "core-target-open", file.to_str().unwrap()], cfg.path()).success);
    assert!(!cfg.path().join("config.toml").exists(), "the run's mode isn't saved");
    assert_eq!(cli(&["--deep", "--clean-room", "core-session-show"], cfg.path()).code, Some(2));
    assert_eq!(cli(&["core-session-show", "--deep", "--clean-room"], cfg.path()).code, Some(2));
}

#[test]
fn mcp_over_stdio() {
    let cfg = tempfile::tempdir().unwrap();
    let input = [
        json!({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}}),
        json!({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        json!({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
        json!({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "core_session_show", "arguments": {}}}),
    ]
    .iter()
    .map(|v| format!("{v}\n"))
    .collect::<String>();
    let out = Process::new(env!("CARGO_BIN_EXE_craft-anything-cli"))
        .arg("mcp")
        .env("CRAFT_ANYTHING_CONFIG_DIR", cfg.path())
        .stdin_bytes(input)
        .timeout(Duration::from_secs(30))
        .run()
        .unwrap();
    assert!(out.success);
    let msgs: Vec<Value> = out.stdout_text().lines().map(|l| serde_json::from_str(l).unwrap()).collect();
    let by_id = |id: u64| msgs.iter().find(|m| m["id"] == json!(id)).unwrap().clone();
    assert_eq!(by_id(1)["result"]["serverInfo"]["name"], "craft-anything");
    assert!(by_id(2)["result"]["tools"].as_array().unwrap().iter().any(|t| t["name"] == "core_session_show"));
    assert_eq!(by_id(3)["result"]["isError"], false);
}

#[test]
fn raw_binary_open_params_tool_format_and_project_evidence_across_processes() {
    let cfg = tempfile::tempdir().unwrap();
    let dir = tempfile::tempdir().unwrap();
    let raw = dir.path().join("raw.bin");
    // push rbp; mov rbp, rsp; xor eax, eax; pop rbp; ret
    std::fs::write(&raw, [0x55, 0x48, 0x89, 0xe5, 0x31, 0xc0, 0x5d, 0xc3]).unwrap();
    let raw = raw.to_str().unwrap();
    let proj = dir.path().join("p.cany");
    let proj = proj.to_str().unwrap();

    // A tool's own --format reaches the tool; the output format has --output-format.
    let out = cli(
        &["core-target-open", raw, "--format", "raw-binary", "--architecture", "x86_64", "--entry-point", "0x1000", "--output-format", "json", "--deep"],
        cfg.path(),
    );
    assert!(out.success, "{}", out.stdout_text());
    let v: Value = serde_json::from_slice(&out.stdout).unwrap();
    assert_eq!(v["result"]["kind"], "raw-binary", "{v}");

    // A target tool reopens the path with the raw-binary options.
    let out = cli(
        &["--deep", "native-function-pseudocode", raw, "--architecture", "x86_64", "--entry-point", "0x1000", "--function", "0x1000", "--project", proj],
        cfg.path(),
    );
    assert!(out.success, "{}", out.stdout_text());

    // A new process on the same project sees the stored evidence.
    let out = cli(&["core-evidence-show", "--detail", "summary", "--project", proj], cfg.path());
    assert!(out.success, "{}", out.stdout_text());
    let v: Value = serde_json::from_slice(&out.stdout).unwrap();
    assert!(v["result"]["total"].as_u64().unwrap() >= 1, "{v}");
    let out = cli(&["core-session-show", "--project", proj], cfg.path());
    let v: Value = serde_json::from_slice(&out.stdout).unwrap();
    assert!(v["result"]["evidence_records"].as_u64().unwrap() >= 1, "{v}");
}

fn cli_with_stdin(args: &[&str], config: &std::path::Path, input: &[u8]) -> Output {
    Process::new(env!("CARGO_BIN_EXE_craft-anything-cli"))
        .args(args)
        .env("CRAFT_ANYTHING_CONFIG_DIR", config)
        .stdin_bytes(input.to_vec())
        .timeout(Duration::from_secs(60))
        .run()
        .unwrap()
}

/// `--json -` takes a tool's parameters from a pipe, and `-` isn't read as the shorthand for JSON output.
#[test]
fn parameters_can_come_from_a_pipe() {
    let cfg = tempfile::tempdir().unwrap();
    let dir = tempfile::tempdir().unwrap();
    let file = dir.path().join("plain.txt");
    std::fs::write(&file, b"nothing packed here").unwrap();
    let params = json!({"path": file}).to_string();
    let out = cli_with_stdin(&["core-packed-files-list", "--deep", "--json", "-"], cfg.path(), params.as_bytes());
    let v: Value = serde_json::from_slice(&out.stdout).unwrap();
    // The file reached the tool: it says the file isn't packed, not that the path is missing.
    assert_eq!(v["error"]["code"], "not_supported", "{v}");
    let bad = cli_with_stdin(&["core-packed-files-list", "--deep", "--json", "-"], cfg.path(), b"not json");
    assert_eq!(bad.code, Some(2), "{}", String::from_utf8_lossy(&bad.stderr));
    let empty = cli_with_stdin(&["core-packed-files-list", "--deep", "--json", "-"], cfg.path(), b"");
    assert_eq!(empty.code, Some(2), "an empty pipe is an error, not a wait");
}

#[test]
fn csv_and_tsv_output_show_a_tools_rows() {
    let cfg = tempfile::tempdir().unwrap();
    let out = cli(&["core-session-show", "--output-format", "csv"], cfg.path());
    assert!(out.success);
    let text = String::from_utf8_lossy(&out.stdout);
    let mut lines = text.lines();
    assert!(lines.next().unwrap().split(',').any(|c| c == "clean_room"), "{text}");
    let tsv = cli(&["core-session-show", "--output-format", "tsv"], cfg.path());
    assert!(String::from_utf8_lossy(&tsv.stdout).lines().next().unwrap().split('\t').any(|c| c == "clean_room"));
}

/// A bare argument is the file, not whichever string option sorts first (`contains`, `detail`).
#[test]
fn a_bare_argument_is_the_path_even_when_other_options_sort_first() {
    let cfg = tempfile::tempdir().unwrap();
    let dir = tempfile::tempdir().unwrap();
    let file = dir.path().join("plain.txt");
    std::fs::write(&file, b"nothing packed here").unwrap();
    let path = file.to_str().unwrap();
    let packed: Value = serde_json::from_slice(&cli(&["core-packed-files-list", "--deep", path], cfg.path()).stdout).unwrap();
    assert_eq!(packed["error"]["code"], "not_supported", "the file was read: {packed}");
    let model: Value = serde_json::from_slice(&cli(&["formats-ai-weights-show", "--deep", path], cfg.path()).stdout).unwrap();
    assert!(!model["error"]["message"].as_str().unwrap_or_default().contains("unknown variant"), "{model}");
}

/// #254: the top-level help must not advise `report --format`, which the parser sends to the global output format.
#[test]
fn help_does_not_advise_a_report_format_option() {
    let cfg = tempfile::tempdir().unwrap();
    let help = cli(&["--help"], cfg.path());
    assert!(help.success);
    assert!(!help.stdout_text().contains("(core-target-open, report"));
    assert_eq!(cli(&["report", "--format", "html"], cfg.path()).code, Some(2));
}
