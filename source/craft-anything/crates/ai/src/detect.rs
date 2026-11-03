//! Find AI that's ready to use on this machine: env keys, local servers (also those set up in
//! OpenCode), agent CLIs, ssh hosts. Probes run in parallel and the whole scan is bounded (about a
//! second).

use crate::openai::{LOCAL_SERVERS, OpenAi};
use crate::{BackendConfig, BackendKind, Detected};
use craft_anything_evidence::ErrorCode;
use std::net::{SocketAddr, TcpStream, ToSocketAddrs};
use std::path::PathBuf;
use std::sync::mpsc;
use std::time::{Duration, Instant};

/// Per-server connect bound.
pub const PROBE: Duration = Duration::from_millis(300);
/// Whole-scan bound.
pub const TOTAL: Duration = Duration::from_millis(1500);

fn cfg(name: &str, kind: BackendKind, model: &str) -> BackendConfig {
    BackendConfig { name: name.into(), kind, model: model.into(), base_url: None, ssh_host: None, enabled: true }
}

/// Environment keys that are set.
pub fn env_keys(get: impl Fn(&str) -> Option<String>) -> Vec<Detected> {
    let mut out = Vec::new();
    for (var, name, kind, model) in [
        ("ANTHROPIC_API_KEY", "Claude", BackendKind::Anthropic, crate::anthropic::DEFAULT_MODEL),
        ("OPENAI_API_KEY", "OpenAI", BackendKind::Openai, crate::openai::OPENAI_DEFAULT_MODEL),
        ("OPENROUTER_API_KEY", "OpenRouter", BackendKind::Openrouter, crate::openai::OPENROUTER_DEFAULT_MODEL),
    ] {
        if get(var).is_some_and(|v| !v.trim().is_empty()) {
            out.push(Detected { suggestion: cfg(name, kind, model), reason: format!("Found {var} in your environment"), needs_key: false });
        }
    }
    // Kimi K3 builds through OpenRouter: with its key found, or one the person pastes.
    let found = get("OPENROUTER_API_KEY").is_some_and(|v| !v.trim().is_empty());
    out.push(Detected {
        suggestion: cfg(KIMI_NAME, BackendKind::Openrouter, crate::openai::KIMI_K3),
        reason: if found {
            "Kimi K3 through OpenRouter, with the OPENROUTER_API_KEY in your environment".into()
        } else {
            "Kimi K3 through OpenRouter: paste your OpenRouter key".into()
        },
        needs_key: !found,
    });
    out
}

/// The name Kimi K3 is added under.
pub const KIMI_NAME: &str = "Kimi K3 (OpenRouter)";

/// Is something listening at this URL's host:port? (bounded TCP connect)
pub fn port_open(base_url: &str, timeout: Duration) -> bool {
    let hostport = base_url.split("://").nth(1).unwrap_or(base_url).split('/').next().unwrap_or_default();
    let addrs: Vec<SocketAddr> = hostport.to_socket_addrs().map(|a| a.collect()).unwrap_or_default();
    addrs.iter().any(|a| TcpStream::connect_timeout(a, timeout).is_ok())
}

/// Words in the names of models that turn text into numbers, rank or transcribe, and can't chat:
/// an embedding model listed first was used for every message and each one failed (#127).
const NOT_CHAT: &[&str] = &["embed", "minilm", "bge-", "rerank", "whisper", "tts"];

/// The first model a server lists that can chat (else its first, so something is chosen).
pub(crate) fn chat_model(models: &[String]) -> Option<String> {
    let chats = |m: &&String| !NOT_CHAT.iter().any(|w| m.to_ascii_lowercase().contains(w));
    models.iter().find(chats).or(models.first()).cloned()
}

/// One local server: connect, then list models.
pub fn probe_local(label: &str, base: &str) -> Option<Detected> {
    if !port_open(base, PROBE) {
        return None;
    }
    let models = match OpenAi::compatible(label, base, None, "").list_models(Duration::from_millis(700)) {
        Ok(m) => m,
        // Something else listens there (another app's web server on 8080 answering 404): no model
        // server, so chats with it could only fail (#30).
        Err(e) if e.code == ErrorCode::GarbledOutput || e.details.as_ref().is_some_and(|d| d.get("status").is_some()) => return None,
        // No answer in time: it may still be loading a model.
        Err(_) => Vec::new(),
    };
    let model = chat_model(&models).unwrap_or_default();
    let reason = match models.len() {
        0 => format!("Found {label} running at {base}"),
        1 => format!("Found {label} running with 1 model"),
        n => format!("Found {label} running with {n} models"),
    };
    let mut c = cfg(&format!("{label} (local)"), BackendKind::OpenaiCompatible, &model);
    c.base_url = Some(base.to_string());
    Some(Detected { suggestion: c, reason, needs_key: false })
}

/// Agent CLIs on PATH.
pub fn agent_clis() -> Vec<Detected> {
    crate::cli_agents::KNOWN
        .iter()
        .filter_map(|(id, prog, display)| {
            craft_anything_platform::which(prog).map(|p| Detected {
                suggestion: cfg(display, BackendKind::AgentCli, id),
                reason: format!("Found {display} at {}", p.display()),
                needs_key: false,
            })
        })
        .collect()
}

/// The most servers taken from OpenCode's settings.
const OPENCODE_MAX: usize = 6;

/// Where OpenCode keeps its settings (as setup registers it): `OPENCODE_CONFIG`, else
/// `opencode.jsonc` or `opencode.json` in `$XDG_CONFIG_HOME/opencode` (`~/.config/opencode`).
fn opencode_config(var: impl Fn(&str) -> Option<String>, home: Option<PathBuf>) -> Option<PathBuf> {
    if let Some(p) = var("OPENCODE_CONFIG").filter(|p| !p.trim().is_empty()) {
        return Some(PathBuf::from(p));
    }
    let dir = var("XDG_CONFIG_HOME").map(PathBuf::from).or_else(|| home.map(|h| h.join(".config")))?.join("opencode");
    ["opencode.jsonc", "opencode.json"].iter().map(|n| dir.join(n)).find(|p| p.is_file())
}

/// The OpenAI-compatible servers OpenCode's settings name on this computer or its network
/// (`provider.<id>.options.baseURL`), as (name, base URL): one on another port or machine is
/// offered too (#83, #73). Hosted services are left out; they need a key this scan doesn't have.
pub fn opencode_servers(text: &str) -> Vec<(String, String)> {
    let Ok(doc) = craft_anything_formats::jsonc::parse(text, false) else { return Vec::new() };
    let config = doc.to_value();
    let Some(providers) = config.get("provider").and_then(serde_json::Value::as_object) else { return Vec::new() };
    providers
        .iter()
        .filter_map(|(id, p)| {
            let base = p.pointer("/options/baseURL")?.as_str()?.trim().trim_end_matches('/');
            let name = p.get("name").and_then(serde_json::Value::as_str).filter(|n| !n.trim().is_empty()).unwrap_or(id);
            on_this_network(base).then(|| (format!("{} from OpenCode", name.trim()), base.to_string()))
        })
        .take(OPENCODE_MAX)
        .collect()
}

/// Name endings kept for local networks, which public DNS never answers.
const LAN_SUFFIXES: &[&str] = &[".local", ".lan", ".home.arpa", ".internal"];

/// An http(s) address on this computer or its local network: a private or loopback IP, or a name
/// that only a local network can answer (`localhost`, a bare name such as Docker's `ollama`, or a
/// [`LAN_SUFFIXES`] name). Nothing is looked up.
pub(crate) fn on_this_network(url: &str) -> bool {
    let Some(rest) = url.strip_prefix("http://").or_else(|| url.strip_prefix("https://")) else { return false };
    let host = rest.split('/').next().unwrap_or_default();
    // `[::1]:1234`, `127.0.0.1:1234` or `name:1234`.
    let host = match host.strip_prefix('[') {
        Some(v6) => v6.split(']').next().unwrap_or_default(),
        None => host.rsplit_once(':').map_or(host, |(h, _)| h),
    };
    match host.parse::<std::net::IpAddr>() {
        Ok(std::net::IpAddr::V4(ip)) => ip.is_loopback() || ip.is_private() || ip.is_link_local(),
        Ok(std::net::IpAddr::V6(ip)) => ip.is_loopback() || ip.is_unique_local() || ip.is_unicast_link_local(),
        Err(_) => {
            let host = host.to_ascii_lowercase();
            !host.is_empty() && (!host.contains('.') || LAN_SUFFIXES.iter().any(|s| host.ends_with(s)))
        }
    }
}

/// Every local server to probe: the usual addresses, then those OpenCode names elsewhere.
fn local_servers() -> Vec<(String, String)> {
    let mut all: Vec<(String, String)> = LOCAL_SERVERS.iter().map(|(l, b)| (l.to_string(), b.to_string())).collect();
    let config = opencode_config(|v| std::env::var(v).ok(), dirs::home_dir());
    let text = config.filter(|p| std::fs::metadata(p).is_ok_and(|m| m.len() <= 1024 * 1024)).and_then(|p| std::fs::read_to_string(p).ok());
    for (label, base) in text.as_deref().map(opencode_servers).unwrap_or_default() {
        if !all.iter().any(|(_, b)| b.trim_end_matches('/') == base) {
            all.push((label, base));
        }
    }
    all
}

/// Everything, bounded by [`TOTAL`].
pub fn detect_all() -> Vec<Detected> {
    let start = Instant::now();
    let (tx, rx) = mpsc::channel::<(usize, Vec<Detected>)>();
    let mut jobs = 0usize;
    for (i, (label, base)) in local_servers().into_iter().enumerate() {
        let tx = tx.clone();
        if std::thread::Builder::new()
            .name("ai-detect".into())
            .spawn(move || {
                let _ = tx.send((i + 10, probe_local(&label, &base).into_iter().collect()));
            })
            .is_ok()
        {
            jobs += 1;
        }
    }
    {
        let tx = tx.clone();
        if std::thread::Builder::new()
            .name("ai-detect".into())
            .spawn(move || {
                let _ = tx.send((5, agent_clis()));
            })
            .is_ok()
        {
            jobs += 1;
        }
    }
    drop(tx);
    let mut parts: Vec<(usize, Vec<Detected>)> = vec![(0, env_keys(|v| std::env::var(v).ok()))];
    while jobs > 0 {
        let left = TOTAL.saturating_sub(start.elapsed());
        match rx.recv_timeout(left) {
            Ok(p) => {
                parts.push(p);
                jobs -= 1;
            }
            Err(_) => break,
        }
    }
    let mut hosts = crate::ssh::ssh_hosts();
    hosts.truncate(5);
    let ssh: Vec<Detected> = hosts
        .into_iter()
        .map(|h| {
            let mut c = cfg(&format!("Claude Code on {h}"), BackendKind::AgentCli, "claude-code");
            c.ssh_host = Some(h.clone());
            Detected { suggestion: c, reason: format!("SSH host {h} from ~/.ssh/config (runs an agent CLI there)"), needs_key: false }
        })
        .collect();
    parts.push((100, ssh));
    parts.sort_by_key(|(i, _)| *i);
    parts.into_iter().flat_map(|(_, v)| v).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn env_detection() {
        let d = env_keys(|v| (v == "OPENROUTER_API_KEY").then(|| "k".to_string()));
        assert_eq!(d.len(), 2);
        assert_eq!(d[0].suggestion.kind, BackendKind::Openrouter);
        assert!(d[0].reason.contains("OPENROUTER_API_KEY"));
        // Kimi K3 rides on the same key, so it needs none of its own.
        assert_eq!((d[1].suggestion.model.as_str(), d[1].needs_key), (crate::openai::KIMI_K3, false));
        // Without a key, Kimi K3 is still offered, asking for one.
        let none = env_keys(|_| Some("  ".into()));
        assert_eq!(none.len(), 1);
        assert!(none[0].needs_key && none[0].suggestion.name == KIMI_NAME);
    }

    #[test]
    fn closed_port_is_fast_and_negative() {
        let l = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let port = l.local_addr().unwrap().port();
        drop(l);
        let t = Instant::now();
        assert!(probe_local("X", &format!("http://127.0.0.1:{port}/v1")).is_none());
        assert!(t.elapsed() < Duration::from_secs(1));
    }

    /// #30: another program on a model server's port isn't offered as one.
    #[test]
    fn only_a_server_that_lists_models_is_offered() {
        use crate::tests::serve;
        assert!(probe_local("llama.cpp server", &serve("404 Not Found", "404 page not found")).is_none(), "a Go web server's 404");
        assert!(probe_local("llama.cpp server", &serve("200 OK", "<html><body>Admin</body></html>")).is_none(), "a web page");
        let found = probe_local("llama.cpp server", &serve("200 OK", r#"{"object":"list","data":[{"id":"qwen3-8b"}]}"#)).unwrap();
        assert_eq!((found.suggestion.name.as_str(), found.suggestion.model.as_str()), ("llama.cpp server (local)", "qwen3-8b"));
        assert!(probe_local("Ollama", &serve("200 OK", r#"{"object":"list","data":[]}"#)).is_some(), "running with no model yet");
    }

    /// #127: an embedding model listed first isn't the one chatted with.
    #[test]
    fn a_chat_model_is_picked_over_an_embedding_model() {
        let names = |l: &[&str]| l.iter().map(|s| s.to_string()).collect::<Vec<_>>();
        assert_eq!(chat_model(&names(&["nomic-embed-text:latest", "llama3.2:3b"])).as_deref(), Some("llama3.2:3b"));
        assert_eq!(chat_model(&names(&["mxbai-embed-large", "all-MiniLM-L6-v2", "qwen3:8b"])).as_deref(), Some("qwen3:8b"));
        assert_eq!(chat_model(&names(&["nomic-embed-text"])).as_deref(), Some("nomic-embed-text"), "something is chosen");
        assert_eq!(chat_model(&[]), None);
        let url = crate::tests::serve("200 OK", r#"{"object":"list","data":[{"id":"nomic-embed-text:latest"},{"id":"gemma3:4b"}]}"#);
        assert_eq!(probe_local("Ollama", &url).unwrap().suggestion.model, "gemma3:4b");
    }

    /// #83: a server set up in OpenCode (here LM Studio on another port) is offered; hosted
    /// services and broken settings aren't.
    #[test]
    fn servers_set_up_in_opencode_are_offered() {
        let config = r#"{
          // LM Studio on its own port, as in #73
          "provider": {
            "lmstudio": { "name": "LM Studio", "options": { "baseURL": "http://127.0.0.1:1235/v1/" } },
            "box": { "options": { "baseURL": "http://192.168.1.20:11434/v1" } },
            "cloud": { "name": "Hosted", "options": { "baseURL": "https://api.example.com/v1" } },
            "nourl": { "name": "No address" },
          },
        }"#;
        assert_eq!(
            opencode_servers(config),
            [
                // In the order of their ids.
                ("box from OpenCode".to_string(), "http://192.168.1.20:11434/v1".to_string()),
                ("LM Studio from OpenCode".to_string(), "http://127.0.0.1:1235/v1".to_string()),
            ]
        );
        assert!(opencode_servers("not json {").is_empty());
        assert!(opencode_servers(r#"{"provider": []}"#).is_empty());
        let many: String =
            (0..20).map(|i| format!(r#""p{i}": {{"options": {{"baseURL": "http://localhost:{}/v1"}}}}"#, 9000 + i)).collect::<Vec<_>>().join(",");
        assert_eq!(opencode_servers(&format!(r#"{{"provider": {{{many}}}}}"#)).len(), OPENCODE_MAX);
        // Found the same way as a server at a usual address.
        let url = crate::tests::serve("200 OK", r#"{"object":"list","data":[{"id":"gemma"}]}"#);
        let found = opencode_servers(&format!(r#"{{"provider": {{"lmstudio": {{"name": "LM Studio", "options": {{"baseURL": "{url}"}}}}}}}}"#));
        let (label, base) = found.first().unwrap();
        assert_eq!(probe_local(label, base).unwrap().suggestion.name, "LM Studio from OpenCode (local)");
    }

    #[test]
    fn only_addresses_on_this_computer_or_network_count() {
        for url in [
            "http://localhost:1234/v1",
            "http://127.0.0.1/v1",
            "http://[::1]:8080",
            "http://[fe80::1]:11434/v1",
            "http://10.0.0.5:8000/v1",
            "https://studio.local:1234/v1",
            "http://172.20.0.2:1234",
            "http://ollama:11434/v1",
            "http://GPU-Box:8000",
            "http://gpu.lan:1234/v1",
            "http://studio.home.arpa/v1",
            "http://llm.internal:8080",
        ] {
            assert!(on_this_network(url), "{url}");
        }
        for url in [
            "https://api.openai.com/v1",
            "http://8.8.8.8/v1",
            "ftp://127.0.0.1",
            "127.0.0.1:1234",
            "",
            "http://",
            "https://lan.example.com",
            "https://internal.example.com/v1",
        ] {
            assert!(!on_this_network(url), "{url}");
        }
    }

    #[test]
    fn opencode_settings_are_found_where_opencode_keeps_them() {
        let d = tempfile::tempdir().unwrap();
        assert_eq!(opencode_config(|k| (k == "OPENCODE_CONFIG").then(|| "/x/oc.json".to_string()), None), Some(PathBuf::from("/x/oc.json")));
        assert_eq!(opencode_config(|_| None, Some(d.path().to_path_buf())), None, "nothing there");
        let dir = d.path().join(".config").join("opencode");
        std::fs::create_dir_all(&dir).unwrap();
        std::fs::write(dir.join("opencode.json"), "{}").unwrap();
        assert_eq!(opencode_config(|_| None, Some(d.path().to_path_buf())), Some(dir.join("opencode.json")));
        std::fs::write(dir.join("opencode.jsonc"), "{}").unwrap();
        assert_eq!(opencode_config(|_| None, Some(d.path().to_path_buf())), Some(dir.join("opencode.jsonc")), "jsonc first");
        let xdg = d.path().join(".config").to_string_lossy().into_owned();
        assert_eq!(opencode_config(|k| (k == "XDG_CONFIG_HOME").then(|| xdg.clone()), None), Some(dir.join("opencode.jsonc")));
    }

    #[test]
    fn whole_scan_is_bounded() {
        let t = Instant::now();
        let _ = detect_all();
        assert!(t.elapsed() < TOTAL + Duration::from_millis(1500));
    }
}
