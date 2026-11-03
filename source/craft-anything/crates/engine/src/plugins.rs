//! Plugins: external MCP servers whose tools become Craft Anything tools, each server its own
//! toolset. A server is listed in `config.toml`:
//!
//! ```toml
//! [[plugins.mcp]]
//! id = "notes"                 # toolset id; tool ids become notes_<tool>
//! command = "notes-mcp"
//! args = ["--stdio"]
//! consent = true               # ask before each call (default): it runs someone else's code
//!
//! [[plugins.mcp]]
//! id = "docs"                  # a remote server (Streamable HTTP)
//! url = "https://mcp.example.com/mcp"
//! headers = { Authorization = "Bearer …" }
//! ```
//!
//! Its tool list is cached (`plugins_refresh`), so starting the app or a CLI command never starts
//! every server; a server starts on its first call and stays up for the session. Results are
//! recorded as evidence from an external service. Effects come from the server's own tool
//! annotations, plus launching a process (local) or using the network (remote); `consent` adds
//! "runs foreign code", which asks first. `env` and `headers` values are never shown by
//! `settings_show` or `plugins_list`.

use crate::registry::{RuntimeTool, custom_toolset};
use crate::session::Session;
use crate::tool::{Ctx, Effects, Requires, ToolOutput};
use craft_anything_engines::mcp_client::{McpClient, RemoteTool, Server, ServerCommand, ServerUrl, content_text, url_allowed};
use craft_anything_evidence::{Authority, Confidence, Environment, ErrorCode, EvidenceBuilder, Subject, ToolError};
use craft_anything_platform::sync::Mutex;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::{BTreeMap, HashMap};
use std::path::PathBuf;
use std::sync::{Arc, PoisonError};
use std::time::Duration;

/// How long a server may take to start and answer the handshake or its tool list.
pub const START_TIMEOUT: Duration = Duration::from_secs(60);
/// How long one call may take.
pub const CALL_TIMEOUT: Duration = Duration::from_secs(15 * 60);
/// Most tools one server may add.
const MAX_TOOLS: usize = 500;

/// One configured MCP server.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct McpPlugin {
    /// Toolset id and tool-id prefix: lower-case letters, digits and `_`.
    pub id: String,
    /// The name people see (default: the id).
    #[serde(default)]
    pub name: Option<String>,
    /// The program of a local server (or `url` for a remote one).
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub command: String,
    #[serde(default)]
    pub args: Vec<String>,
    #[serde(default)]
    pub env: BTreeMap<String, String>,
    #[serde(default)]
    pub cwd: Option<PathBuf>,
    /// A remote server's address: `https://…`, or `http://` to this computer.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub url: Option<String>,
    /// Sent with every request to a remote server (e.g. `Authorization`).
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub headers: BTreeMap<String, String>,
    #[serde(default = "yes")]
    pub enabled: bool,
    /// Ask before each call (it runs someone else's code). Default true.
    #[serde(default = "yes")]
    pub consent: bool,
}

fn yes() -> bool {
    true
}

impl McpPlugin {
    pub fn display_name(&self) -> &str {
        self.name.as_deref().unwrap_or(&self.id)
    }

    /// How to reach it: a remote `url`, else the local `command`.
    pub fn server(&self) -> Server {
        match self.remote_url() {
            Some(url) => Server::Url(ServerUrl { url: url.to_string(), headers: self.headers.clone() }),
            None => Server::Command(ServerCommand { command: self.command.clone(), args: self.args.clone(), env: self.env.clone(), cwd: self.cwd.clone() }),
        }
    }

    fn remote_url(&self) -> Option<&str> {
        self.url.as_deref().map(str::trim).filter(|u| !u.is_empty())
    }

    /// What's wrong with it, if anything: its id, or not exactly one of `command` and `url`.
    pub fn problem(&self) -> Option<String> {
        if !RuntimeTool::valid_id(&self.id) || custom_toolset(&self.id).is_none() {
            return Some(format!("Plugin id {:?} must be lower-case letters, digits and _.", self.id));
        }
        match (self.command.trim().is_empty(), self.remote_url()) {
            (true, None) => Some(format!("The {} plugin needs a command (a local server) or a url (a remote one).", self.id)),
            (false, Some(_)) => Some(format!("The {} plugin has both a command and a url; keep one.", self.id)),
            (true, Some(u)) if !url_allowed(u) => Some(format!("The {} plugin's url must start with https:// (or http:// to this computer).", self.id)),
            _ => None,
        }
    }

    /// Where it runs, for people: the url, or the command line.
    pub fn place(&self) -> String {
        match self.remote_url() {
            Some(u) => u.to_string(),
            None => std::iter::once(self.command.as_str()).chain(self.args.iter().map(String::as_str)).collect::<Vec<_>>().join(" "),
        }
    }

    /// Where its tool list is cached, under a config folder ([`Session::config_dir`]).
    pub fn cache_path(&self, config: &std::path::Path) -> PathBuf {
        config.join("plugins").join(format!("{}.tools.json", self.id))
    }

    /// The tools cached by the last refresh (none before the first).
    pub fn cached_tools(&self, config: &std::path::Path) -> Vec<RemoteTool> {
        std::fs::read(self.cache_path(config)).ok().and_then(|b| serde_json::from_slice(&b).ok()).unwrap_or_default()
    }
}

/// `[plugins]` in config.toml.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct PluginSettings {
    pub mcp: Vec<McpPlugin>,
    /// WASM component plugins (`crate::wasm_plugins`).
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub wasm: Vec<crate::wasm_plugins::WasmPluginConfig>,
}

/// One proxied tool: which server, and the tool's name there.
struct Route {
    server: String,
    remote: String,
}

/// The session's plugins: their settings, running clients and the tool routes.
#[derive(Default)]
pub struct Plugins {
    servers: HashMap<String, (McpPlugin, Mutex<Option<McpClient>>)>,
    routes: HashMap<&'static str, Route>,
}

/// A remote tool name as part of our id: lower case, `_` for anything else, no repeats.
fn id_part(name: &str) -> String {
    let mut out = String::new();
    for c in name.chars() {
        let c = if c.is_ascii_alphanumeric() { c.to_ascii_lowercase() } else { '_' };
        if !(c == '_' && out.ends_with('_')) {
            out.push(c);
        }
    }
    out.trim_matches('_').to_string()
}

/// What a remote tool may do, from its annotations (MCP's hints), plus starting a local server
/// or reaching a remote one.
fn effects_of(t: &RemoteTool, consent: bool, remote: bool) -> Effects {
    let hint = |k: &str| t.annotations.get(k).and_then(Value::as_bool);
    let mut e = Effects::MUTATES_SESSION | if remote { Effects::ACCESSES_NETWORK } else { Effects::LAUNCHES_PROCESS };
    if hint("readOnlyHint") != Some(true) {
        e |= Effects::WRITES_FILESYSTEM;
    }
    if hint("destructiveHint") == Some(true) {
        e |= Effects::MAY_DISCARD_DATA;
    }
    if hint("openWorldHint") != Some(false) || remote {
        e |= Effects::ACCESSES_NETWORK;
    }
    if hint("idempotentHint") == Some(true) {
        e |= Effects::IDEMPOTENT;
    }
    if consent {
        e |= Effects::EXECUTES_FOREIGN_CODE;
    }
    e
}

/// Read the configured plugins into `session` and return their (cached) tools for
/// [`crate::Engine::shared_with`]. A plugin with an invalid id, or a tool whose id clashes, is
/// skipped and logged.
pub fn install(session: &mut Session) -> Vec<RuntimeTool> {
    let mut plugins = Plugins::default();
    let mut tools = Vec::new();
    let config = session.config_dir();
    for p in session.settings.plugins.mcp.iter().filter(|p| p.enabled) {
        if let Some(problem) = p.problem() {
            log::error!("plugin skipped: {problem}");
            continue;
        }
        let Some(set) = custom_toolset(&p.id) else { continue };
        let remote = matches!(p.server(), Server::Url(_));
        for t in p.cached_tools(&config).into_iter().take(MAX_TOOLS) {
            let mut id = format!("{}_{}", p.id, id_part(&t.name));
            id.truncate(64);
            if !RuntimeTool::valid_id(&id) || tools.iter().any(|x: &RuntimeTool| x.id == id) {
                log::error!("plugin {} tool {:?} skipped (its id {id:?} is invalid or taken)", p.id, t.name);
                continue;
            }
            let schema = if t.input_schema.is_object() { t.input_schema.clone() } else { json!({"type": "object"}) };
            let leaked: &'static str = Box::leak(id.clone().into_boxed_str());
            plugins.routes.insert(leaked, Route { server: p.id.clone(), remote: t.name.clone() });
            tools.push(RuntimeTool {
                id,
                title: t.title.clone().unwrap_or_else(|| format!("{}: {}", p.display_name(), t.name)),
                summary: t.description.clone().filter(|d| !d.trim().is_empty()).unwrap_or_else(|| format!("{} from the {} plugin.", t.name, p.display_name())),
                beginner: format!("A tool from the {} plugin.", p.display_name()),
                toolset: set,
                effects: effects_of(&t, p.consent, remote),
                requires: Requires::Nothing,
                schema,
                run: call_plugin,
            });
        }
        plugins.servers.insert(p.id.clone(), (p.clone(), Mutex::new(None)));
    }
    session.ext.insert(Arc::new(plugins));
    crate::wasm_plugins::install(session, &mut tools);
    tools
}

/// Start a server, list its tools and cache them. New tools are offered from the next start.
pub fn refresh(p: &McpPlugin, config: &std::path::Path) -> Result<Vec<RemoteTool>, ToolError> {
    if let Some(problem) = p.problem() {
        return Err(ToolError::invalid(problem).with_remediation("Fix it in config.toml ([[plugins.mcp]])."));
    }
    let mut client = McpClient::connect(p.display_name(), &p.server(), START_TIMEOUT)?;
    let tools = client.list_tools(START_TIMEOUT)?;
    let path = p.cache_path(config);
    if let Some(dir) = path.parent() {
        std::fs::create_dir_all(dir).map_err(|e| ToolError::io(dir.display(), e))?;
    }
    let json = serde_json::to_vec_pretty(&tools).map_err(|e| ToolError::internal(e.to_string()))?;
    crate::project::write_atomic(&path, &json)?;
    Ok(tools)
}

/// The function behind every proxied tool: route by [`Ctx::tool`], start the server if needed,
/// call it, and record the result as evidence.
fn call_plugin(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let plugins = ctx.session.ext.get::<Plugins>().ok_or_else(|| ToolError::internal("plugins aren't loaded in this session"))?;
    let route = plugins.routes.get(ctx.tool).ok_or_else(|| ToolError::internal(format!("no plugin serves {}", ctx.tool)))?;
    let (plugin, client) = plugins.servers.get(&route.server).ok_or_else(|| ToolError::internal(format!("plugin {} isn't loaded", route.server)))?;
    let mut slot = client.lock().unwrap_or_else(PoisonError::into_inner);
    if slot.is_none() {
        ctx.report(None, format!("Starting the {} plugin…", plugin.display_name()));
        *slot = Some(McpClient::connect(plugin.display_name(), &plugin.server(), START_TIMEOUT)?);
    }
    let Some(c) = slot.as_mut() else { return Err(ToolError::internal("plugin client missing")) };
    let cancel = ctx.cancel.clone();
    let args = if params.is_null() { json!({}) } else { params.clone() };
    let result = match c.call_tool(&route.remote, args, CALL_TIMEOUT, &move || cancel.is_cancelled()) {
        Ok(r) => r,
        Err(e) => {
            // A server that died is started again on the next call.
            if e.code == ErrorCode::EngineMissing {
                *slot = None;
            }
            return Err(e);
        }
    };
    let text = content_text(&result);
    let summary: String = if text.is_empty() { format!("{} answered.", plugin.display_name()) } else { text.chars().take(300).collect() };
    let env = Environment {
        clean_room: ctx.session.clean_room(),
        engine: format!("plugin:{}", plugin.id),
        engine_version: None,
        host: craft_anything_evidence::host_triple(),
        language_id: None,
    };
    let e = EvidenceBuilder::new(ctx.tool, Subject { kind: "plugin".into(), sha256: None, name: Some(plugin.display_name().to_string()) }, env)
        .params(params)
        .authority(Authority::OutsideService)
        .confidence(Confidence::Observed)
        .result(result)
        .summary(summary)
        .build()?;
    Ok(ToolOutput::evidence(e))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn remote_names_become_our_ids_and_annotations_our_effects() {
        assert_eq!(id_part("Search Notes!"), "search_notes");
        assert_eq!(id_part("get-page__v2"), "get_page_v2");
        let t = |ann: Value| RemoteTool { name: "x".into(), title: None, description: None, input_schema: json!({}), annotations: ann };
        let read = effects_of(&t(json!({"readOnlyHint": true, "openWorldHint": false})), false, false);
        assert!(!read.contains(Effects::WRITES_FILESYSTEM) && !read.contains(Effects::ACCESSES_NETWORK) && !read.needs_consent());
        let risky = effects_of(&t(json!({"destructiveHint": true})), true, false);
        assert!(risky.contains(Effects::MAY_DISCARD_DATA) && risky.needs_consent(), "consent plugins ask first");
        assert!(effects_of(&t(Value::Null), false, false).contains(Effects::WRITES_FILESYSTEM), "no hints: assume it may write");
        let remote = effects_of(&t(json!({"readOnlyHint": true, "openWorldHint": false})), false, true);
        assert!(remote.contains(Effects::ACCESSES_NETWORK) && !remote.contains(Effects::LAUNCHES_PROCESS), "a remote server uses the network");
    }

    #[test]
    fn plugins_without_a_cache_add_no_tools_and_bad_ids_are_skipped() {
        let mut s = crate::testing::session();
        s.settings.plugins.mcp =
            vec![McpPlugin { id: "Bad Id".into(), ..plugin("x") }, McpPlugin { id: "never_refreshed_plugin_for_tests".into(), ..plugin("x") }];
        assert!(install(&mut s).is_empty());
        assert!(s.ext.get::<Plugins>().is_some());
        let parsed: PluginSettings = toml::from_str("[[mcp]]\nid = \"notes\"\ncommand = \"notes-mcp\"\n").unwrap();
        assert!(parsed.mcp[0].enabled && parsed.mcp[0].consent, "on and asking by default");
    }

    fn plugin(command: &str) -> McpPlugin {
        McpPlugin {
            id: "notes".into(),
            name: None,
            command: command.into(),
            args: vec![],
            env: BTreeMap::new(),
            cwd: None,
            url: None,
            headers: BTreeMap::new(),
            enabled: true,
            consent: true,
        }
    }

    #[test]
    fn a_plugin_is_local_or_remote_never_both() {
        assert!(plugin("notes-mcp").problem().is_none());
        assert!(matches!(plugin("notes-mcp").server(), Server::Command(_)));
        let remote = McpPlugin { url: Some("https://mcp.example.com/mcp".into()), ..plugin("") };
        assert!(remote.problem().is_none() && matches!(remote.server(), Server::Url(_)));
        assert_eq!(remote.place(), "https://mcp.example.com/mcp");
        assert!(plugin("").problem().unwrap().contains("command"));
        assert!(McpPlugin { url: Some("https://x".into()), ..plugin("notes-mcp") }.problem().unwrap().contains("both"));
        assert!(McpPlugin { url: Some("http://example.com/mcp".into()), ..plugin("") }.problem().unwrap().contains("https://"));
        let parsed: PluginSettings =
            toml::from_str("[[mcp]]\nid = \"docs\"\nurl = \"https://mcp.example.com/mcp\"\nheaders = { Authorization = \"Bearer t\" }\n").unwrap();
        assert!(parsed.mcp[0].problem().is_none() && parsed.mcp[0].headers.contains_key("Authorization"));
        assert!(!toml::to_string(&parsed).unwrap().contains("command"), "a remote plugin is saved without an empty command");
    }
}
