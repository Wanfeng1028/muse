//! End-to-end tests: a tiny std TcpListener HTTP server stands in for the model APIs, and a real
//! engine runs the tools. No real network.

use super::*;
use craft_anything_platform::sync::Mutex;
use serde_json::{Value, json};
use std::io::{BufRead, BufReader, Read, Write};
use std::net::TcpListener;

#[derive(Debug, Clone)]
struct Seen {
    path: String,
    headers: Vec<(String, String)>,
    body: Value,
}

impl Seen {
    fn header(&self, k: &str) -> Option<&str> {
        self.headers.iter().find(|(n, _)| n.eq_ignore_ascii_case(k)).map(|(_, v)| v.as_str())
    }
}

/// Serve canned responses `(status, content_type, body)` in order; record requests.
fn mock(responses: Vec<(u16, &'static str, String)>) -> (String, Arc<Mutex<Vec<Seen>>>) {
    let l = TcpListener::bind("127.0.0.1:0").unwrap();
    let url = format!("http://{}", l.local_addr().unwrap());
    let seen = Arc::new(Mutex::new(Vec::new()));
    let s2 = seen.clone();
    std::thread::spawn(move || {
        for (status, ctype, reply) in responses {
            let Ok((stream, _)) = l.accept() else { return };
            let mut r = BufReader::new(stream.try_clone().unwrap());
            let mut line = String::new();
            r.read_line(&mut line).unwrap();
            let path = line.split_whitespace().nth(1).unwrap_or_default().to_string();
            let mut headers = Vec::new();
            let mut len = 0usize;
            loop {
                let mut h = String::new();
                r.read_line(&mut h).unwrap();
                let h = h.trim_end().to_string();
                if h.is_empty() {
                    break;
                }
                if let Some((k, v)) = h.split_once(':') {
                    if k.eq_ignore_ascii_case("content-length") {
                        len = v.trim().parse().unwrap();
                    }
                    headers.push((k.trim().to_string(), v.trim().to_string()));
                }
            }
            let mut buf = vec![0; len];
            r.read_exact(&mut buf).unwrap();
            let body = serde_json::from_slice(&buf).unwrap_or(Value::Null);
            s2.lock().unwrap().push(Seen { path, headers, body });
            let mut w = stream;
            let reason = if status == 200 { "OK" } else { "Error" };
            write!(w, "HTTP/1.1 {status} {reason}\r\ncontent-type: {ctype}\r\ncontent-length: {}\r\nconnection: close\r\n\r\n{reply}", reply.len()).unwrap();
            w.flush().unwrap();
        }
    });
    (url, seen)
}

/// A stand-in server on a free port that answers every request (and any number of them, unlike
/// [`mock`]) with `status` and `body`; its `/v1` address.
pub(crate) fn serve(status: &'static str, body: &'static str) -> String {
    let l = TcpListener::bind("127.0.0.1:0").unwrap();
    let base = format!("http://{}/v1", l.local_addr().unwrap());
    std::thread::spawn(move || {
        for mut s in l.incoming().flatten() {
            let (mut got, mut buf) = (Vec::new(), [0u8; 4096]);
            while !got.windows(4).any(|w| w == b"\r\n\r\n") {
                match s.read(&mut buf) {
                    Ok(0) | Err(_) => break,
                    Ok(n) => got.extend_from_slice(&buf[..n]),
                }
            }
            if !got.is_empty() {
                let _ = write!(s, "HTTP/1.1 {status}\r\ncontent-length: {}\r\nconnection: close\r\n\r\n{body}", body.len());
            }
        }
    });
    base
}

/// #48: a coding agent's test only runs `--version`, and its report says so.
#[test]
fn a_coding_agent_test_says_it_only_checked_the_version() {
    let (h, _d) = hub();
    let config = BackendConfig { name: "Agent".into(), kind: BackendKind::AgentCli, model: "opencode".into(), base_url: None, ssh_host: None, enabled: true };
    // cargo stands in for the agent's program: it's there wherever these tests run.
    let options = BackendOptions { command: Some("cargo".into()), ..Default::default() };
    h.add_backend_with(BackendEntry { config, options }, None).unwrap();
    let r = h.test_backend("Agent").unwrap();
    assert!(r.version_only && r.reply.starts_with("cargo "), "{r:?}");
    assert_eq!(serde_json::to_value(&r).unwrap()["version_only"], true, "the CLI's ai test prints it");
}

/// Every known agent with an adapter of its own is offered when adding a coding agent.
#[test]
fn every_agent_with_its_own_adapter_is_offered() {
    let adapters = cli_agents::adapters::AgentAdapters::built_in();
    let own: Vec<&str> = cli_agents::KNOWN.iter().map(|(id, _, _)| *id).filter(|id| adapters.for_agent(id).ids().contains(id)).collect();
    assert!(own.contains(&"maki"), "{own:?}");
    for id in own {
        assert!(BackendKind::AgentCli.suggested_models().contains(&id), "{id} isn't offered");
    }
}

/// #37: doctor asks a local server for its models instead of trusting an open port.
#[test]
fn a_local_server_is_reachable_only_when_it_lists_models() {
    let (h, _d) = hub();
    add(&h, "Web page", BackendKind::OpenaiCompatible, &serve("404 Not Found", "404 page not found"), None);
    add(&h, "Real", BackendKind::OpenaiCompatible, &serve("200 OK", r#"{"data":[{"id":"qwen3-8b"}]}"#), None);
    let reach = h.check_reachability();
    let of = |n: &str| reach.iter().find(|(name, _)| name == n).map(|(_, r)| r.clone()).unwrap();
    assert!(of("Web page").is_err_and(|e| e.contains("404 page not found")), "{reach:?}");
    assert!(of("Real").is_ok(), "{reach:?}");
}

fn sse(events: &[Value]) -> String {
    events.iter().map(|e| format!("event: {}\r\ndata: {}\r\n\r\n", e["type"].as_str().unwrap_or("message"), e)).collect()
}

fn chat_sse(chunks: &[Value]) -> String {
    let mut s: String = chunks.iter().map(|c| format!("data: {c}\n\n")).collect();
    s.push_str("data: [DONE]\n\n");
    s
}

fn hub() -> (AiHub, tempfile::TempDir) {
    let dir = tempfile::tempdir().unwrap();
    let engine = Arc::new(Engine::new(craft_anything_engine::testing::session()));
    let h = AiHub::with_stores(engine, dir.path().join("config.toml"), KeyStore::file_only(dir.path().join("ai-keys.toml")));
    (h, dir)
}

#[test]
fn a_failed_save_changes_nothing() {
    let dir = tempfile::tempdir().unwrap();
    // The settings "file" can't be written: its folder is a file.
    std::fs::write(dir.path().join("blocked"), "").unwrap();
    let engine = Arc::new(Engine::new(craft_anything_engine::testing::session()));
    let h = AiHub::with_stores(engine, dir.path().join("blocked").join("config.toml"), KeyStore::file_only(dir.path().join("ai-keys.toml")));
    let cfg = BackendConfig { name: "Kimi".into(), kind: BackendKind::Openrouter, model: "m".into(), base_url: None, ssh_host: None, enabled: true };
    assert!(h.add_backend(cfg, None).is_err());
    assert!(h.backends().is_empty(), "the app shows only what was saved");
}

/// #261: one bad price made the whole [ai] section read as empty, and adding a backend saved
/// that over the backends, roles and prices.
#[test]
fn ai_settings_that_cant_be_read_are_never_saved_over() {
    let (h, d) = hub();
    add(&h, "Claude Code", BackendKind::AgentCli, "http://127.0.0.1:9", None);
    add(&h, "Kimi K3 (OpenRouter)", BackendKind::Openrouter, "http://127.0.0.1:9", None);
    h.set_role(Role::Builder, Some("Kimi K3 (OpenRouter)")).unwrap();
    let file = d.path().join("config.toml");
    let mut bad = h.engine.session().settings.clone();
    let price: toml::Table = toml::from_str(
        "[m]
input_per_mtok = 1.0
",
    )
    .unwrap();
    bad.ai.insert("prices".into(), toml::Value::Table(price));
    bad.save_to(&file).unwrap();
    h.engine.session().settings = bad;
    let before = std::fs::read(&file).unwrap();
    let cfg = BackendConfig { name: "Other".into(), kind: BackendKind::Openrouter, model: "m".into(), base_url: None, ssh_host: None, enabled: true };
    let e = h.add_backend(cfg, Some("sk-test".into())).unwrap_err();
    assert_eq!(e.code, ErrorCode::BadSettings, "{e:?}");
    assert!(h.set_role(Role::Builder, None).is_err());
    assert!(h.set_enabled("Claude Code", false).is_err());
    assert!(h.remove_backend("Claude Code").is_err());
    assert_eq!(std::fs::read(&file).unwrap(), before, "the settings file was changed");
    assert!(h.keys.get("Other").is_none(), "a refused add stored its key");
}

#[test]
fn the_person_chooses_who_builds() {
    let (h, _d) = hub();
    add(&h, "Claude Code", BackendKind::AgentCli, "http://127.0.0.1:9", None);
    add(&h, "Kimi K3 (OpenRouter)", BackendKind::Openrouter, "http://127.0.0.1:9", Some("sk-test"));
    assert_eq!(h.chosen(Role::Builder), None, "automatic until chosen");
    assert!(h.set_role(Role::Builder, Some("Nobody")).is_err(), "only a configured backend");
    h.set_role(Role::Builder, Some("Kimi K3 (OpenRouter)")).unwrap();
    assert_eq!(h.chosen(Role::Builder).as_deref(), Some("Kimi K3 (OpenRouter)"));
    // The extractor is chosen the same way, and has no default.
    assert_eq!(h.chosen(Role::Extractor), None);
    h.set_role(Role::Extractor, Some("Kimi K3 (OpenRouter)")).unwrap();
    assert_eq!(h.chosen(Role::Extractor).as_deref(), Some("Kimi K3 (OpenRouter)"));
    // A removed backend can't stay the builder.
    h.remove_backend("Kimi K3 (OpenRouter)").unwrap();
    assert_eq!((h.chosen(Role::Builder), h.chosen(Role::Extractor)), (None, None));
    h.set_role(Role::Builder, Some("Claude Code")).unwrap();
    h.set_role(Role::Builder, None).unwrap();
    assert_eq!(h.chosen(Role::Builder), None, "back to automatic");
}

/// #53: an agent app installed where it isn't looked for gets its program set (and cleared).
#[test]
fn an_agent_apps_program_is_set_and_cleared() {
    let (h, _d) = hub();
    add(&h, "OpenCode", BackendKind::AgentCli, "http://127.0.0.1:9", None);
    let program = |h: &AiHub| h.options().get("OpenCode").and_then(|o| o.command.clone());
    assert_eq!(program(&h), None);
    assert!(h.set_command("OpenCode", Some("  /opt/oc/bin/opencode ")).unwrap());
    assert_eq!(program(&h).as_deref(), Some("/opt/oc/bin/opencode"));
    assert!(!h.set_command("Nobody", Some("/x")).unwrap(), "only a configured backend");
    assert!(h.set_command("OpenCode", Some(" ")).unwrap());
    assert_eq!(program(&h), None, "blank finds it by its usual name again");
}

/// #123, #127: the model an AI uses is changed; Claude Code is offered Claude's models.
#[test]
fn an_ais_model_is_changed() {
    let (h, _d) = hub();
    let url = serve("200 OK", r#"{"object":"list","data":[{"id":"nomic-embed-text"},{"id":"qwen3:8b"}]}"#);
    h.add_server("Box", &url, Some("nomic-embed-text"), None).unwrap();
    assert_eq!(h.model_choices("Box").unwrap(), ["nomic-embed-text", "qwen3:8b"], "the server's own list");
    assert!(h.set_model("Box", " qwen3:8b ").unwrap());
    assert_eq!(h.backends().into_iter().find(|b| b.name == "Box").unwrap().model, "qwen3:8b");
    let claude =
        BackendConfig { name: "Claude Code".into(), kind: BackendKind::AgentCli, model: "claude-code".into(), base_url: None, ssh_host: None, enabled: true };
    h.add_backend(claude, None).unwrap();
    assert_eq!(h.model_choices("Claude Code").unwrap(), crate::anthropic::MODELS);
    assert!(h.set_model("Claude Code", "claude-sonnet-5-5").unwrap());
    let claude = h.options().get("Claude Code").and_then(|o| o.cli_model.clone());
    assert_eq!(claude.as_deref(), Some("claude-sonnet-5-5"), "the CLI is asked for it; the agent stays Claude Code");
    assert_eq!(h.backends().into_iter().find(|b| b.name == "Claude Code").unwrap().model, "claude-code");
    assert!(!h.set_model("Nobody", "m").unwrap());
    assert!(h.set_model("Box", " ").is_err());
}

/// Every Claude effort level can be chosen for the Claude API and Claude Code, and only for them.
#[test]
fn a_claude_ais_effort_is_changed() {
    let (h, _d) = hub();
    let b = |name: &str, kind, model: &str| BackendConfig { name: name.into(), kind, model: model.into(), base_url: None, ssh_host: None, enabled: true };
    h.add_backend(b("Claude Code", BackendKind::AgentCli, "claude-code"), None).unwrap();
    h.add_backend(b("Codex", BackendKind::AgentCli, "codex"), None).unwrap();
    let effort = |h: &AiHub, name: &str| {
        let config = h.backends().into_iter().find(|b| b.name == name).unwrap();
        crate::effort_in_use(&config, h.options().get(name))
    };
    assert_eq!(effort(&h, "Claude Code"), Some(Effort::High), "high until it's chosen");
    for level in Effort::ALL {
        assert!(h.set_effort("Claude Code", Some(level)).unwrap());
        assert_eq!(effort(&h, "Claude Code"), Some(level));
    }
    assert!(h.set_effort("Claude Code", None).unwrap());
    assert_eq!(effort(&h, "Claude Code"), Some(Effort::High), "back to the usual level");
    assert_eq!(effort(&h, "Codex"), None, "an agent that doesn't take Claude's levels");
    assert!(h.set_effort("Codex", Some(Effort::Max)).is_err());
    assert!(!h.set_effort("Nobody", Some(Effort::Low)).unwrap());
}

/// #54, #98: a server on another computer is added by its address, with a model that can chat
/// when none is named; one that doesn't answer with its models isn't added.
#[test]
fn a_server_is_added_by_its_address() {
    let (h, _d) = hub();
    let url = serve("200 OK", r#"{"object":"list","data":[{"id":"nomic-embed-text"},{"id":"qwen3:8b"}]}"#);
    assert_eq!(h.add_server(" Studio box ", &format!("{url}/"), None, Some(" sk-test ".into())).unwrap(), "qwen3:8b");
    let b = h.backends().into_iter().find(|b| b.name == "Studio box").unwrap();
    assert_eq!((b.kind, b.model.as_str(), b.base_url.as_deref()), (BackendKind::OpenaiCompatible, "qwen3:8b", Some(url.as_str())));
    assert_eq!(h.add_server("Named", &url, Some("llama3"), None).unwrap(), "llama3", "a named model is kept");
    assert!(h.add_server("Web page", &serve("404 Not Found", "nope"), None, None).is_err(), "not a model server");
    assert!(h.add_server("Empty", &serve("200 OK", r#"{"object":"list","data":[]}"#), None, None).is_err(), "no models to use");
    assert!(h.add_server("No scheme", "192.168.1.20:11434/v1", None, None).is_err());
    assert!(h.add_server(" ", &url, None, None).is_err());
    assert_eq!(h.backends().len(), 2, "only the ones that answered");
}

/// #374: a remote OpenAI-compatible service was treated as a local model: a 24K-token context
/// and a cost of nothing. Only a server on this computer or its network is local.
#[test]
fn only_an_openai_compatible_server_nearby_is_local() {
    let (h, _d) = hub();
    for (name, base, local) in [
        ("Ollama", "http://127.0.0.1:11434/v1", true),
        ("LM Studio box", "http://192.168.1.20:1234/v1", true),
        ("Docker Ollama", "http://ollama:11434/v1", true),
        ("IPv6 link-local", "http://[fe80::1]:11434/v1", true),
        ("Z.ai", "https://api.z.ai/api/coding/paas/v4", false),
        ("Public vLLM", "http://8.8.8.8:8000/v1", false),
    ] {
        add(&h, name, BackendKind::OpenaiCompatible, base, None);
        let slot = h.build_model(&h.entry(name).unwrap()).unwrap();
        assert_eq!(slot.local, local, "{name} at {base}");
    }
    h.add_backend(
        BackendConfig { name: "Default".into(), kind: BackendKind::OpenaiCompatible, model: String::new(), base_url: None, ssh_host: None, enabled: true },
        None,
    )
    .unwrap();
    assert!(h.build_model(&h.entry("Default").unwrap()).unwrap().local, "no address means Ollama on this computer");
    add(&h, "OpenAI", BackendKind::Openai, "http://127.0.0.1:9/v1", Some("sk-test"));
    assert!(!h.build_model(&h.entry("OpenAI").unwrap()).unwrap().local, "only OpenAI-compatible servers can be local");
}

fn add(h: &AiHub, name: &str, kind: BackendKind, base: &str, key: Option<&str>) {
    h.add_backend(
        BackendConfig { name: name.into(), kind, model: String::new(), base_url: Some(base.into()), ssh_host: None, enabled: true },
        key.map(str::to_string),
    )
    .unwrap();
}

fn run(c: &mut Box<dyn Conversation>, text: &str) -> Vec<AgentEvent> {
    c.send(text);
    let deadline = Instant::now() + Duration::from_secs(20);
    let mut all = Vec::new();
    while Instant::now() < deadline {
        for e in c.poll() {
            let done = matches!(e, AgentEvent::TurnDone { .. });
            all.push(e);
            if done {
                return all;
            }
        }
        std::thread::sleep(Duration::from_millis(5));
    }
    panic!("timed out: {all:?}");
}

#[test]
fn anthropic_streaming_tool_loop_through_the_engine() {
    let turn1 = sse(&[
        json!({"type":"message_start","message":{"model":"claude-opus-5-5","usage":{"input_tokens":100,"output_tokens":1}}}),
        json!({"type":"ping"}),
        json!({"type":"content_block_start","index":0,"content_block":{"type":"thinking","thinking":""}}),
        json!({"type":"content_block_delta","index":0,"delta":{"type":"thinking_delta","thinking":"plan"}}),
        json!({"type":"content_block_delta","index":0,"delta":{"type":"signature_delta","signature":"SIG"}}),
        json!({"type":"content_block_stop","index":0}),
        json!({"type":"content_block_start","index":1,"content_block":{"type":"text","text":""}}),
        json!({"type":"content_block_delta","index":1,"delta":{"type":"text_delta","text":"Checking"}}),
        json!({"type":"content_block_stop","index":1}),
        json!({"type":"content_block_start","index":2,"content_block":{"type":"tool_use","id":"tu_1","name":"core_session_show","input":{}}}),
        json!({"type":"content_block_delta","index":2,"delta":{"type":"input_json_delta","partial_json":"{"}}),
        json!({"type":"content_block_delta","index":2,"delta":{"type":"input_json_delta","partial_json":"}"}}),
        json!({"type":"content_block_stop","index":2}),
        json!({"type":"content_block_start","index":3,"content_block":{"type":"tool_use","id":"tu_2","name":"core_targets_list","input":{}}}),
        json!({"type":"content_block_stop","index":3}),
        json!({"type":"message_delta","delta":{"stop_reason":"tool_use"},"usage":{"output_tokens":40}}),
        json!({"type":"message_stop"}),
    ]);
    let turn2 = sse(&[
        json!({"type":"message_start","message":{"model":"claude-opus-5-5","usage":{"input_tokens":200,"cache_read_input_tokens":90}}}),
        json!({"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}}),
        json!({"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":" Nothing is open."}}),
        json!({"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":10}}),
        json!({"type":"message_stop"}),
    ]);
    let (url, seen) = mock(vec![(200, "text/event-stream", turn1), (200, "text/event-stream", turn2)]);
    let (h, _d) = hub();
    add(&h, "Claude", BackendKind::Anthropic, &url, Some("sk-test-123"));
    let mut c = h.start(None, true).unwrap();
    let ev = run(&mut c, "How does the session look?");
    let text: String = ev.iter().filter_map(|e| if let AgentEvent::TextDelta { text } = e { Some(text.as_str()) } else { None }).collect();
    assert_eq!(text, "Checking Nothing is open.");
    assert!(ev.iter().any(|e| matches!(e, AgentEvent::ToolFinished { tool, ok: true, .. } if tool == "core_session_show")));
    assert!(ev.iter().any(|e| matches!(e, AgentEvent::ToolFinished { tool, ok: true, .. } if tool == "core_targets_list")));
    let AgentEvent::TurnDone { backend, input_tokens, output_tokens, cost_usd, .. } = ev.last().unwrap().clone() else { panic!() };
    assert_eq!((backend.as_str(), input_tokens, output_tokens), ("Claude", 300, 50));
    assert!(cost_usd.unwrap() > 0.0);

    let seen = seen.lock().unwrap();
    assert_eq!(seen.len(), 2);
    let r1 = &seen[0];
    assert_eq!(r1.path, "/v1/messages");
    assert_eq!(r1.header("x-api-key"), Some("sk-test-123"));
    assert_eq!(r1.header("anthropic-version"), Some("2023-06-01"));
    assert_eq!(r1.header("anthropic-beta"), Some("server-side-fallback-2026-07-01"));
    assert_eq!(r1.header("user-agent"), Some("CraftAnything-dev"));
    let b = &r1.body;
    assert_eq!(b["model"], "claude-opus-5-5");
    assert_eq!(b["stream"], true);
    assert_eq!(b["max_tokens"], 64000);
    assert_eq!(b["thinking"]["type"], "adaptive");
    assert_eq!(b["output_config"]["effort"], "high");
    assert_eq!(b["fallbacks"], "default");
    assert_eq!(b["tool_choice"]["type"], "auto");
    assert_eq!(b["system"][0]["cache_control"]["type"], "ephemeral");
    assert!(b["system"][0]["text"].as_str().unwrap().contains("Investigation so far"));
    let tools = b["tools"].as_array().unwrap();
    let names: Vec<&str> = tools.iter().map(|t| t["name"].as_str().unwrap()).collect();
    let mut sorted = names.clone();
    sorted.sort();
    assert_eq!(names, sorted, "tool order is deterministic");
    assert!(names.contains(&"core_session_show") && names.contains(&"enable_toolset") && names.contains(&"core_handoff_write"));
    assert!(!names.contains(&"native_cursor_show"), "non-Core tools wait for enable_toolset");
    assert_eq!(tools.last().unwrap()["cache_control"]["type"], "ephemeral");
    assert!(tools.iter().all(|t| t["input_schema"]["type"] == "object"));
    // Turn 2 replays thinking (with signature) and returns BOTH results in ONE user message.
    let msgs = seen[1].body["messages"].as_array().unwrap();
    assert_eq!(msgs.len(), 3);
    assert_eq!(msgs[1]["content"][0], json!({"type":"thinking","thinking":"plan","signature":"SIG"}));
    let results = msgs[2]["content"].as_array().unwrap();
    assert_eq!(msgs[2]["role"], "user");
    assert_eq!(results.len(), 2);
    assert_eq!(results[0]["tool_use_id"], "tu_1");
    assert_eq!(results[1]["tool_use_id"], "tu_2");
    assert_eq!(results[0]["is_error"], false);
    assert!(results[0]["content"].as_str().unwrap().contains("deep"), "test sessions are in Deep mode");
    // the key is never stored in settings
    let saved = std::fs::read_to_string(_d.path().join("config.toml")).unwrap();
    assert!(!saved.contains("sk-test-123"));
}

#[test]
fn anthropic_refusal_and_http_errors() {
    let refusal = sse(&[
        json!({"type":"message_start","message":{"model":"claude-opus-5-5","usage":{"input_tokens":5}}}),
        json!({"type":"message_delta","delta":{"stop_reason":"refusal"},"usage":{"output_tokens":0}}),
        json!({"type":"message_stop"}),
    ]);
    let (url, _seen) = mock(vec![
        (200, "text/event-stream", refusal),
        (401, "application/json", r#"{"type":"error","error":{"type":"authentication_error","message":"invalid x-api-key"}}"#.into()),
    ]);
    let (h, _d) = hub();
    add(&h, "Claude", BackendKind::Anthropic, &url, Some("k"));
    let mut c = h.start(Some("Claude"), false).unwrap();
    let ev = run(&mut c, "q");
    assert!(ev.iter().any(|e| matches!(e, AgentEvent::Error { message, .. } if message.contains("declined"))));
    let ev = run(&mut c, "q2");
    assert!(
        ev.iter().any(|e| matches!(e, AgentEvent::Error { message, remediation: Some(r), .. } if message.contains("invalid x-api-key") && r.contains("key"))),
        "{ev:?}"
    );
}

#[test]
fn openai_streaming_tool_loop() {
    let t1 = chat_sse(&[
        json!({"model":"gpt-x","choices":[{"delta":{"role":"assistant","tool_calls":[{"index":0,"id":"call_a","type":"function","function":{"name":"core_session_show","arguments":""}}]}}]}),
        json!({"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"{}"}}]}}]}),
        json!({"choices":[{"delta":{},"finish_reason":"tool_calls"}]}),
        json!({"choices":[],"usage":{"prompt_tokens":20,"completion_tokens":3}}),
    ]);
    let t2 = chat_sse(&[json!({"choices":[{"delta":{"content":"Nothing open."},"finish_reason":"stop"}]})]);
    let (url, seen) = mock(vec![(200, "text/event-stream", t1), (200, "text/event-stream", t2)]);
    let (h, _d) = hub();
    add(&h, "GPT", BackendKind::Openai, &url, Some("sk-o"));
    let mut c = h.start(Some("GPT"), true).unwrap();
    let ev = run(&mut c, "status?");
    assert!(ev.iter().any(|e| matches!(e, AgentEvent::TextDelta { text } if text == "Nothing open.")));
    let seen = seen.lock().unwrap();
    assert_eq!(seen[0].path, "/chat/completions");
    assert_eq!(seen[0].header("authorization"), Some("Bearer sk-o"));
    assert_eq!(seen[0].body["stream_options"]["include_usage"], true);
    assert_eq!(seen[0].body["tool_choice"], "auto");
    let msgs = seen[1].body["messages"].as_array().unwrap();
    assert_eq!(msgs[2]["tool_calls"][0]["id"], "call_a");
    assert_eq!(msgs[3]["role"], "tool");
    assert_eq!(msgs[3]["tool_call_id"], "call_a");
}

#[test]
fn local_server_without_tools_falls_back_to_react() {
    let t1 = chat_sse(&[json!({"choices":[{"delta":{"content":"Thought: check\nAction: core_session_show\nAction Input: {}"},"finish_reason":"stop"}]})]);
    let t2 = chat_sse(&[json!({"choices":[{"delta":{"content":"Final Answer: nothing is open"},"finish_reason":"stop"}]})]);
    let (url, seen) = mock(vec![
        (400, "application/json", r#"{"error":{"message":"registry.ollama.ai/library/tiny does not support tools"}}"#.into()),
        (200, "text/event-stream", t1),
        (200, "text/event-stream", t2),
    ]);
    let (h, _d) = hub();
    add(&h, "Tiny", BackendKind::OpenaiCompatible, &format!("{url}/v1"), None);
    let mut c = h.start(Some("Tiny"), true).unwrap();
    let ev = run(&mut c, "status?");
    assert!(ev.iter().any(|e| matches!(e, AgentEvent::ToolFinished { tool, ok: true, .. } if tool == "core_session_show")), "{ev:?}");
    assert!(matches!(ev.last(), Some(AgentEvent::TurnDone { cost_usd: Some(c), .. }) if *c == 0.0));
    let seen = seen.lock().unwrap();
    assert!(seen[0].body.get("tools").is_some());
    assert!(seen[0].header("authorization").is_none());
    assert!(seen[1].body.get("tools").is_none());
    let last = seen[2].body["messages"].as_array().unwrap().last().unwrap().clone();
    assert!(last["content"].as_str().unwrap().starts_with("Observation:"));
}

#[test]
fn hub_config_keys_and_test_backend() {
    let t = sse(&[
        json!({"type":"message_start","message":{"model":"claude-haiku-5-5","usage":{"input_tokens":3}}}),
        json!({"type":"content_block_start","index":0,"content_block":{"type":"text","text":"ready"}}),
        json!({"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":1}}),
        json!({"type":"message_stop"}),
    ]);
    let models = json!({"data":[{"id":"claude-opus-5-5"},{"id":"claude-haiku-5-5"}]}).to_string();
    let (url, seen) = mock(vec![(200, "text/event-stream", t), (200, "application/json", models.clone()), (200, "application/json", models)]);
    let (h, d) = hub();
    assert!(h.backends().is_empty());
    assert!(h.start(None, true).is_err());
    add(&h, "Claude", BackendKind::Anthropic, &url, Some("k1"));
    add(&h, "Local", BackendKind::OpenaiCompatible, "http://127.0.0.1:9/v1", None);
    assert_eq!(h.backends().len(), 2);
    assert!(h.has_key("Claude") && h.has_key("Local"));
    let r = h.test_backend("Claude").unwrap();
    assert_eq!((r.reply.as_str(), r.version_only), ("ready", false));
    assert_eq!(r.model, "claude-haiku-5-5");
    assert_eq!(seen.lock().unwrap()[0].body["output_config"]["effort"], "high");
    assert_eq!(h.list_models("Claude").unwrap(), vec!["claude-opus-5-5", "claude-haiku-5-5"]);
    let reach = h.check_reachability();
    assert_eq!(reach.len(), 2);
    assert!(reach[0].1.is_ok(), "{reach:?}");
    assert!(reach[1].1.is_err());
    // settings persisted to the file; reload shows both
    let s = Settings::load_from(&d.path().join("config.toml"));
    assert_eq!(AiConfig::from_settings(&s).backends.len(), 2);
    assert!(h.remove_backend("Claude").unwrap());
    assert!(!h.remove_backend("Claude").unwrap());
    assert!(h.test_backend("Claude").is_err());
    // missing key is a clear error
    h.add_backend(
        BackendConfig {
            name: "NoKey".into(),
            kind: BackendKind::Openrouter,
            model: String::new(),
            base_url: Some("http://127.0.0.1:9".into()),
            ssh_host: None,
            enabled: true,
        },
        None,
    )
    .unwrap();
    if std::env::var("OPENROUTER_API_KEY").is_err() {
        let e = h.start(Some("NoKey"), true).err().unwrap();
        assert_eq!(e.code, ErrorCode::BadSettings);
    }
    assert!(h.compare("Local", "Local", true).is_err());
}
