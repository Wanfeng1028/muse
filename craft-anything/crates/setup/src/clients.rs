//! The coding-agent apps we can connect to: where their config lives, how to recognise them, and
//! the exact shape of the registration entry each one expects.

use serde::Serialize;
use std::collections::BTreeMap;
use std::path::PathBuf;

/// The name our server is registered under in every client.
pub const SERVER_NAME: &str = "craft-anything";

/// Environment variables that affect where clients keep their config. Only these are read.
pub const ENV_KEYS: &[&str] = &[
    "XDG_CONFIG_HOME",
    "APPDATA",
    "LOCALAPPDATA",
    "CLAUDE_CONFIG_DIR",
    "CODEX_HOME",
    "GEMINI_CLI_HOME",
    "OPENCODE_CONFIG",
    "COPILOT_HOME",
    "QWEN_HOME",
    "HERMES_HOME",
    "GROK_HOME",
    "QODER_CONFIG_DIR",
    "PI_CODING_AGENT_DIR",
    "DSH_HOME",
    "KIMI_CODE_HOME",
    "FACTORY_HOME_OVERRIDE",
    "ANTIGRAVITY_HOME",
];

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Os {
    Linux,
    Macos,
    Windows,
}

impl Os {
    pub fn current() -> Os {
        match std::env::consts::OS {
            "macos" => Os::Macos,
            "windows" => Os::Windows,
            _ => Os::Linux,
        }
    }
}

/// The machine we're configuring. Injectable so tests use a temporary home.
#[derive(Debug, Clone)]
pub struct Host {
    pub home: PathBuf,
    pub env: BTreeMap<String, String>,
    pub os: Os,
}

impl Host {
    /// The real machine: the user's home and only the config-related environment variables.
    pub fn current() -> Host {
        let home = std::env::var_os("HOME")
            .filter(|h| !h.is_empty())
            .or_else(|| std::env::var_os("USERPROFILE"))
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from("."));
        let env = ENV_KEYS.iter().filter_map(|k| std::env::var(k).ok().filter(|v| !v.is_empty()).map(|v| (k.to_string(), v))).collect();
        Host { home, env, os: Os::current() }
    }

    /// A host rooted at `home` with no environment overrides (tests).
    pub fn with_home(home: impl Into<PathBuf>) -> Host {
        Host { home: home.into(), env: BTreeMap::new(), os: Os::current() }
    }

    pub fn var(&self, k: &str) -> Option<PathBuf> {
        self.env.get(k).filter(|v| !v.is_empty()).map(|v| self.expand(v))
    }

    /// Expand a leading `~` and make relative paths relative to home.
    fn expand(&self, v: &str) -> PathBuf {
        if v == "~" {
            return self.home.clone();
        }
        if let Some(rest) = v.strip_prefix("~/") {
            return self.home.join(rest);
        }
        let p = PathBuf::from(v);
        if p.is_absolute() { p } else { self.home.join(p) }
    }

    pub fn xdg_config(&self) -> PathBuf {
        self.var("XDG_CONFIG_HOME").unwrap_or_else(|| self.home.join(".config"))
    }

    /// Per-user application data (Windows `%APPDATA%`, macOS Application Support, Linux XDG config).
    pub fn app_data(&self) -> PathBuf {
        match self.os {
            Os::Windows => self.var("APPDATA").unwrap_or_else(|| self.home.join("AppData").join("Roaming")),
            Os::Macos => self.home.join("Library").join("Application Support"),
            Os::Linux => self.xdg_config(),
        }
    }

    /// The shared skills folder used by clients without their own.
    pub fn shared_skills(&self) -> PathBuf {
        self.home.join(".agents").join("skills")
    }
}

/// How the config file is parsed and edited.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Format {
    /// JSON with comments and trailing commas tolerated (and preserved).
    Jsonc,
    /// Plain JSON: comments, trailing commas and a BOM are rejected because the client rejects them.
    StrictJson,
    Toml,
    Yaml,
    /// We don't edit this client's config; setup prints what to do by hand.
    Manual,
}

/// The registration entry's shape.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Shape {
    /// `{command, args}`
    Plain,
    /// `{type: "stdio", command, args}`
    Stdio,
    /// `{type: "stdio", command, args, tools: ["*"]}`
    StdioAllTools,
    /// `{type: "local", command: [cmd, ...args], enabled: true}`
    LocalArray,
    /// `{transport: "stdio", enabled: true, command, args}`
    TransportStdio,
    /// `{command, args, enabled: true}`
    Enabled,
    /// `{command, args, startup_timeout_sec: 30}`
    WithStartupTimeout,
}

/// One supported client, resolved for a host.
#[derive(Debug, Clone, Serialize)]
pub struct Client {
    pub id: &'static str,
    pub display: &'static str,
    /// The file we write.
    pub config: PathBuf,
    /// Paths whose existence means the client is installed.
    pub markers: Vec<PathBuf>,
    pub format: Format,
    /// Key path of the servers table, e.g. `["mcpServers"]`.
    pub table: Vec<&'static str>,
    pub shape: Shape,
    /// Where skills go for this client.
    pub skills_dir: PathBuf,
    /// An empty file is an error for this client (strict loaders).
    pub empty_is_invalid: bool,
    /// Instructions for clients we don't edit automatically.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub manual: Option<&'static str>,
}

/// Other names people use for a client (its program's name).
const ALIASES: &[(&str, &str)] = &[("agy", "antigravity")];

impl Client {
    /// Whether `name` (an id, `-` or `_`, or an alias) means this client.
    pub fn is(&self, name: &str) -> bool {
        let name = name.replace('-', "_");
        name == self.id || ALIASES.iter().any(|(alias, id)| name == *alias && *id == self.id)
    }

    pub fn detected(&self) -> bool {
        self.config.exists() || self.markers.iter().any(|m| m.exists())
    }

    /// The table path plus our server name.
    pub fn entry_path(&self) -> Vec<&str> {
        let mut p: Vec<&str> = self.table.clone();
        p.push(SERVER_NAME);
        p
    }

    /// The entry this client should hold for `command` (program followed by args).
    pub fn desired_entry(&self, command: &[String]) -> serde_json::Value {
        use serde_json::json;
        let (program, args) = match command.split_first() {
            Some((p, a)) => (p.clone(), a.to_vec()),
            None => (String::new(), Vec::new()),
        };
        match self.shape {
            Shape::Plain => json!({"command": program, "args": args}),
            Shape::Stdio => json!({"type": "stdio", "command": program, "args": args}),
            Shape::StdioAllTools => json!({"type": "stdio", "command": program, "args": args, "tools": ["*"]}),
            Shape::LocalArray => json!({"type": "local", "command": command, "enabled": true}),
            Shape::TransportStdio => json!({"transport": "stdio", "enabled": true, "command": program, "args": args}),
            Shape::Enabled => json!({"command": program, "args": args, "enabled": true}),
            Shape::WithStartupTimeout => json!({"command": program, "args": args, "startup_timeout_sec": 30}),
        }
    }
}

/// The command line of an existing entry (program + args), whatever its shape.
pub fn entry_command(entry: &serde_json::Value) -> Option<Vec<String>> {
    match entry.get("command")? {
        serde_json::Value::String(p) => {
            let mut v = vec![p.clone()];
            if let Some(args) = entry.get("args").and_then(|a| a.as_array()) {
                v.extend(args.iter().map(|a| a.as_str().map(str::to_string).unwrap_or_else(|| a.to_string())));
            }
            Some(v)
        }
        serde_json::Value::Array(items) => Some(items.iter().map(|a| a.as_str().map(str::to_string).unwrap_or_else(|| a.to_string())).collect()),
        _ => None,
    }
}

/// True when an entry launches our own CLI's MCP server (so we may update or remove it).
pub fn is_owned_entry(entry: &serde_json::Value) -> bool {
    let Some(cmd) = entry_command(entry) else { return false };
    let Some((program, args)) = cmd.split_first() else { return false };
    let file = program.rsplit(['/', '\\']).next().unwrap_or_default();
    (file == "craft-anything-cli" || file.eq_ignore_ascii_case("craft-anything-cli.exe")) && args.first().is_some_and(|a| a == "mcp")
}

/// Every supported client, resolved for `host`.
pub fn clients(host: &Host) -> Vec<Client> {
    let h = &host.home;
    let shared = host.shared_skills();
    let mut v = Vec::new();
    let mut add = |id, display, config: PathBuf, markers: Vec<PathBuf>, format, table: Vec<&'static str>, shape, skills_dir: Option<PathBuf>| {
        v.push(Client {
            id,
            display,
            config,
            markers,
            format,
            table,
            shape,
            skills_dir: skills_dir.unwrap_or_else(|| shared.clone()),
            empty_is_invalid: false,
            manual: None,
        });
    };
    let parent = |p: &PathBuf| p.parent().map(PathBuf::from).into_iter().collect::<Vec<_>>();

    // Claude Code
    let claude_dir = host.var("CLAUDE_CONFIG_DIR");
    let cc_config = claude_dir.as_ref().map(|d| d.join(".claude.json")).unwrap_or_else(|| h.join(".claude.json"));
    let cc_dir = claude_dir.clone().unwrap_or_else(|| h.join(".claude"));
    add("claude_code", "Claude Code", cc_config, vec![cc_dir.clone()], Format::Jsonc, vec!["mcpServers"], Shape::Plain, Some(cc_dir.join("skills")));

    // Claude Desktop
    let cd = host.app_data().join("Claude").join("claude_desktop_config.json");
    add("claude_desktop", "Claude Desktop", cd.clone(), parent(&cd), Format::Jsonc, vec!["mcpServers"], Shape::Plain, None);

    // Codex
    let codex = host.var("CODEX_HOME").unwrap_or_else(|| h.join(".codex"));
    add("codex", "Codex", codex.join("config.toml"), vec![codex.clone()], Format::Toml, vec!["mcp_servers"], Shape::WithStartupTimeout, None);

    // Cursor
    add("cursor", "Cursor", h.join(".cursor").join("mcp.json"), vec![h.join(".cursor")], Format::Jsonc, vec!["mcpServers"], Shape::Plain, None);

    // Gemini CLI
    let gem_home = host.var("GEMINI_CLI_HOME").unwrap_or_else(|| h.clone());
    add(
        "gemini_cli",
        "Gemini CLI",
        gem_home.join(".gemini").join("settings.json"),
        vec![gem_home.join(".gemini")],
        Format::Jsonc,
        vec!["mcpServers"],
        Shape::Plain,
        Some(gem_home.join(".agents").join("skills")),
    );

    // Windsurf
    let ws = h.join(".codeium").join("windsurf");
    add("windsurf", "Windsurf", ws.join("mcp_config.json"), vec![ws.clone()], Format::Jsonc, vec!["mcpServers"], Shape::Plain, None);

    // VS Code
    let code_user = host.app_data().join("Code").join("User");
    add("vscode", "VS Code", code_user.join("mcp.json"), vec![code_user.clone()], Format::Jsonc, vec!["servers"], Shape::Stdio, None);

    // OpenCode
    let oc_dir = host.xdg_config().join("opencode");
    let oc_config = host.var("OPENCODE_CONFIG").unwrap_or_else(|| {
        let jsonc = oc_dir.join("opencode.jsonc");
        if jsonc.exists() { jsonc } else { oc_dir.join("opencode.json") }
    });
    add("opencode", "OpenCode", oc_config, vec![oc_dir.clone()], Format::Jsonc, vec!["mcp"], Shape::LocalArray, None);

    // GitHub Copilot CLI
    let copilot = host.var("COPILOT_HOME").unwrap_or_else(|| h.join(".copilot"));
    add(
        "copilot_cli",
        "GitHub Copilot CLI",
        copilot.join("mcp-config.json"),
        vec![copilot.clone()],
        Format::Jsonc,
        vec!["mcpServers"],
        Shape::StdioAllTools,
        None,
    );

    // Qwen Code
    let qwen = host.var("QWEN_HOME").unwrap_or_else(|| h.join(".qwen"));
    add("qwen_code", "Qwen Code", qwen.join("settings.json"), vec![qwen.clone()], Format::Jsonc, vec!["mcpServers"], Shape::Plain, None);

    // Hermes
    let hermes = host.var("HERMES_HOME").unwrap_or_else(|| match host.os {
        Os::Windows => host.var("LOCALAPPDATA").unwrap_or_else(|| h.join("AppData").join("Local")).join("hermes"),
        _ => h.join(".hermes"),
    });
    add("hermes", "Hermes", hermes.join("config.yaml"), vec![hermes.clone()], Format::Yaml, vec!["mcp_servers"], Shape::Enabled, Some(hermes.join("skills")));

    // Antigravity (agy)
    let ag_home = host.var("ANTIGRAVITY_HOME").unwrap_or_else(|| h.clone());
    let ag = ag_home.join(".gemini").join("config");
    let ag_cli = ag_home.join(".gemini").join("antigravity-cli");
    add(
        "antigravity",
        "Antigravity",
        ag.join("mcp_config.json"),
        vec![ag.clone(), ag_cli],
        Format::Jsonc,
        vec!["mcpServers"],
        Shape::Plain,
        Some(ag.join("skills")),
    );

    // Grok Build
    let grok = host.var("GROK_HOME").unwrap_or_else(|| h.join(".grok"));
    add("grok_build", "Grok Build", grok.join("config.toml"), vec![grok.clone()], Format::Toml, vec!["mcp_servers"], Shape::WithStartupTimeout, None);

    // Trae
    let trae_user = host.app_data().join("Trae").join("User");
    add(
        "trae",
        "Trae",
        trae_user.join("mcp.json"),
        vec![trae_user.clone()],
        Format::Jsonc,
        vec!["mcpServers"],
        Shape::Plain,
        Some(h.join(".trae").join("skills")),
    );

    // Qoder
    let qoder = host.var("QODER_CONFIG_DIR").unwrap_or_else(|| h.join(".qoder"));
    add(
        "qoder",
        "Qoder",
        qoder.join("settings.json"),
        vec![qoder.clone()],
        Format::Jsonc,
        vec!["mcpServers"],
        Shape::Plain,
        Some(h.join(".qoder").join("skills")),
    );

    // Devin
    let devin = match host.os {
        Os::Windows => host.app_data().join("devin"),
        _ => host.xdg_config().join("devin"),
    };
    add("devin", "Devin", devin.join("mcp_config.json"), vec![devin.clone()], Format::Jsonc, vec!["mcpServers"], Shape::Plain, None);

    // Command Code
    let ccode = h.join(".commandcode");
    add("commandcode", "Command Code", ccode.join("mcp.json"), vec![ccode.clone()], Format::Jsonc, vec!["mcpServers"], Shape::TransportStdio, None);

    // OMP
    let omp = h.join(".omp").join("agent");
    add("omp", "OMP", omp.join("mcp.json"), vec![h.join(".omp")], Format::Jsonc, vec!["mcpServers"], Shape::Stdio, None);

    // Pi (strict JSON loader)
    let pi = host.var("PI_CODING_AGENT_DIR").unwrap_or_else(|| h.join(".pi").join("agent"));
    add("pi", "Pi", pi.join("mcp.json"), vec![pi.clone()], Format::StrictJson, vec!["mcpServers"], Shape::Stdio, None);

    // ZCode (strict JSON, nested table)
    let zc = h.join(".zcode").join("cli");
    add(
        "zcode",
        "ZCode",
        zc.join("config.json"),
        vec![zc.clone()],
        Format::StrictJson,
        vec!["mcp", "servers"],
        Shape::Plain,
        Some(h.join(".zcode").join("skills")),
    );

    // Kimi Code
    let kimi = host.var("KIMI_CODE_HOME").unwrap_or_else(|| h.join(".kimi-code"));
    add("kimi_code", "Kimi Code", kimi.join("mcp.json"), vec![kimi.clone()], Format::Jsonc, vec!["mcpServers"], Shape::Plain, None);

    // Factory Droid (the override replaces the home that holds .factory)
    let factory = host.var("FACTORY_HOME_OVERRIDE").unwrap_or_else(|| h.clone()).join(".factory");
    add(
        "factory_droid",
        "Factory Droid",
        factory.join("mcp.json"),
        vec![factory.clone()],
        Format::Jsonc,
        vec!["mcpServers"],
        Shape::Plain,
        Some(factory.join("skills")),
    );

    // WorkBuddy
    let wb = h.join(".workbuddy");
    add("workbuddy", "WorkBuddy", wb.join("mcp.json"), vec![wb.clone()], Format::Jsonc, vec!["mcpServers"], Shape::Plain, Some(wb.join("skills")));

    // DeepSeek harness: its config is a patch list we don't edit automatically.
    let dsh = host.var("DSH_HOME").unwrap_or_else(|| h.join(".dsh"));
    add("dsh", "DeepSeek harness (DSH)", dsh.join("cordis.patch.yml"), vec![dsh.clone()], Format::Manual, vec![], Shape::Plain, None);

    for c in &mut v {
        if c.id == "pi" {
            c.empty_is_invalid = true;
        }
        if c.id == "dsh" {
            c.manual = Some(
                "Add an MCP client entry for a stdio server named craft-anything whose command is the path of craft-anything-cli with the argument `mcp`, using the harness's own configuration commands.",
            );
        }
    }
    v
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn table_is_complete_and_ids_unique() {
        let host = Host::with_home("/home/u");
        let cs = clients(&host);
        assert!(cs.len() >= 21);
        let mut ids: Vec<_> = cs.iter().map(|c| c.id).collect();
        ids.sort();
        ids.dedup();
        assert_eq!(ids.len(), cs.len());
        assert!(cs.iter().all(|c| c.config.starts_with("/home/u") || c.format == Format::Manual || host.os == Os::Windows));
    }

    #[test]
    fn a_client_is_named_by_id_dashes_or_its_program() {
        let cs = clients(&Host::with_home("/home/u"));
        let named = |n: &str| cs.iter().filter(|c| c.is(n)).map(|c| c.id).collect::<Vec<_>>();
        assert_eq!(named("antigravity"), ["antigravity"]);
        assert_eq!(named("agy"), ["antigravity"]);
        assert_eq!(named("kimi-code"), ["kimi_code"]);
        assert!(named("nope").is_empty());
    }

    #[test]
    fn newer_clients_have_their_config_and_skill_folders() {
        let host = Host::with_home("/home/u");
        let cs = clients(&host);
        let of = |id: &str| cs.iter().find(|c| c.id == id).unwrap();
        assert_eq!(of("kimi_code").config, PathBuf::from("/home/u/.kimi-code/mcp.json"));
        assert_eq!(of("factory_droid").config, PathBuf::from("/home/u/.factory/mcp.json"));
        assert_eq!(of("workbuddy").config, PathBuf::from("/home/u/.workbuddy/mcp.json"));
        let mut moved = Host::with_home("/home/u");
        moved.env.insert("KIMI_CODE_HOME".into(), "/x/kimi".into());
        moved.env.insert("FACTORY_HOME_OVERRIDE".into(), "/x/home".into());
        let cs = clients(&moved);
        let of = |id: &str| cs.iter().find(|c| c.id == id).unwrap();
        assert_eq!(of("kimi_code").config, PathBuf::from("/x/kimi/mcp.json"));
        assert_eq!(of("factory_droid").config, PathBuf::from("/x/home/.factory/mcp.json"));
    }

    #[test]
    fn env_overrides_paths() {
        let mut host = Host::with_home("/home/u");
        host.env.insert("CODEX_HOME".into(), "/x/codex".into());
        host.env.insert("QWEN_HOME".into(), "~/q".into());
        let cs = clients(&host);
        let codex = cs.iter().find(|c| c.id == "codex").unwrap();
        assert_eq!(codex.config, PathBuf::from("/x/codex/config.toml"));
        let qwen = cs.iter().find(|c| c.id == "qwen_code").unwrap();
        assert_eq!(qwen.config, PathBuf::from("/home/u/q/settings.json"));
    }

    #[test]
    fn ownership() {
        assert!(is_owned_entry(&json!({"command": "/opt/bin/craft-anything-cli", "args": ["mcp"]})));
        assert!(is_owned_entry(&json!({"command": "C:\\x\\craft-anything-cli.exe", "args": ["mcp", "--all-tools"]})));
        assert!(is_owned_entry(&json!({"type": "local", "command": ["/b/craft-anything-cli", "mcp"]})));
        assert!(!is_owned_entry(&json!({"command": "npx", "args": ["craft-anything-cli", "mcp"]})));
        assert!(!is_owned_entry(&json!({"command": "/b/craft-anything-cli", "args": ["doctor"]})));
        assert!(!is_owned_entry(&json!({"url": "http://x"})));
    }

    #[test]
    fn shapes() {
        let host = Host::with_home("/h");
        let cs = clients(&host);
        let cmd = vec!["/b/craft-anything-cli".to_string(), "mcp".to_string()];
        let oc = cs.iter().find(|c| c.id == "opencode").unwrap().desired_entry(&cmd);
        assert_eq!(oc, json!({"type": "local", "command": ["/b/craft-anything-cli", "mcp"], "enabled": true}));
        let codex = cs.iter().find(|c| c.id == "codex").unwrap().desired_entry(&cmd);
        assert_eq!(codex["startup_timeout_sec"], 30);
        for c in &cs {
            assert!(is_owned_entry(&c.desired_entry(&cmd)), "{}", c.id);
        }
    }
}
