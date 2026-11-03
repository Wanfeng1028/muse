//! WASM component plugins (R1.8 phase 2): each `[[plugins.wasm]]` entry is a component exporting
//! `craft-anything:plugin/tools` (see `crates/engines/wit/plugin.wit`), whose tools become
//! Craft Anything tools in a toolset of their own.
//!
//! ```toml
//! [[plugins.wasm]]
//! id = "wordtools"             # toolset id; tool ids become wordtools_<tool>
//! path = "C:/plugins/wordtools.wasm"
//! ```
//!
//! A plugin imports nothing, so it can't touch files, the network or other programs, and each call
//! has a work and memory limit: its tools run without asking. Needs a build with the
//! `wasm-plugins` feature; without it, configured plugins are skipped and logged.

use crate::registry::RuntimeTool;
use crate::session::Session;
use serde::{Deserialize, Serialize};
use std::path::PathBuf;

/// One configured WASM component plugin.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct WasmPluginConfig {
    /// Toolset id and tool-id prefix: lower-case letters, digits and `_`.
    pub id: String,
    /// The name people see (default: the id).
    #[serde(default)]
    pub name: Option<String>,
    /// The component file (`.wasm`).
    pub path: PathBuf,
    #[serde(default = "yes")]
    pub enabled: bool,
}

fn yes() -> bool {
    true
}

impl WasmPluginConfig {
    pub fn display_name(&self) -> &str {
        self.name.as_deref().filter(|n| !n.trim().is_empty()).unwrap_or(&self.id)
    }

    /// What's wrong with this entry, in plain words, or `None`.
    pub fn problem(&self) -> Option<String> {
        if !RuntimeTool::valid_id(&self.id) || crate::registry::custom_toolset(&self.id).is_none() {
            return Some(format!("Plugin id {:?} must be lower-case letters, digits and _.", self.id));
        }
        if !self.path.is_absolute() || !self.path.extension().is_some_and(|e| e.eq_ignore_ascii_case("wasm")) {
            return Some(format!("The {} plugin needs the full path of its .wasm file.", self.id));
        }
        if !self.path.is_file() {
            return Some(format!("The {} plugin's file isn't there: {}.", self.id, self.path.display()));
        }
        None
    }
}

/// A check from a WASM plugin (its `checks` interface), run in the rebuild's check rounds.
pub struct PluginCheck {
    /// `<plugin id>_<check name>`, stored in each result.
    pub id: &'static str,
    pub title: String,
    /// Kinds of project it judges; empty means all.
    pub kinds: Vec<String>,
    /// File extensions whose text it wants.
    pub extensions: Vec<String>,
    #[allow(clippy::type_complexity)]
    run: Box<dyn Fn(&serde_json::Value) -> Result<serde_json::Value, craft_anything_evidence::ToolError> + Send + Sync>,
}

impl PluginCheck {
    /// A check served by `run` (a plugin's `run`, or a stand-in in tests).
    pub fn new(
        id: &'static str,
        title: impl Into<String>,
        kinds: Vec<String>,
        extensions: Vec<String>,
        run: impl Fn(&serde_json::Value) -> Result<serde_json::Value, craft_anything_evidence::ToolError> + Send + Sync + 'static,
    ) -> Self {
        PluginCheck { id, title: title.into(), kinds, extensions, run: Box::new(run) }
    }

    /// Judge `build` (the JSON described in plugin.wit); the plugin's answer.
    pub fn run(&self, build: &serde_json::Value) -> Result<serde_json::Value, craft_anything_evidence::ToolError> {
        (self.run)(build)
    }
}

/// The loaded plugins' checks, kept in the session.
#[derive(Default)]
struct PluginChecks(Vec<std::sync::Arc<PluginCheck>>);

/// The checks the session's WASM plugins offer (none without the `wasm-plugins` feature).
pub fn checks(session: &Session) -> Vec<std::sync::Arc<PluginCheck>> {
    session.ext.get::<PluginChecks>().map(|c| c.0.clone()).unwrap_or_default()
}

/// Load the enabled WASM plugins into `session` and add their tools to `tools` (and keep their
/// checks for [`checks`]). A plugin that can't be loaded, or a tool or check whose id is invalid
/// or taken, is skipped and logged.
pub fn install(session: &mut Session, tools: &mut Vec<RuntimeTool>) {
    let configs: Vec<WasmPluginConfig> = session.settings.plugins.wasm.iter().filter(|p| p.enabled).cloned().collect();
    if configs.is_empty() {
        return;
    }
    imp::install(session, configs, tools);
}

#[cfg(not(feature = "wasm-plugins"))]
mod imp {
    use super::*;

    pub fn install(_session: &mut Session, configs: Vec<WasmPluginConfig>, _tools: &mut Vec<RuntimeTool>) {
        for p in configs {
            log::error!("WASM plugin {} skipped: this build has no WASM support (build with --features wasm-plugins)", p.id);
        }
    }
}

#[cfg(feature = "wasm-plugins")]
mod imp {
    use super::*;
    use crate::registry::custom_toolset;
    use crate::tool::{Ctx, Effects, Requires, ToolOutput};
    use craft_anything_engines::wasm_plugin::WasmPlugin;
    use craft_anything_evidence::ToolError;
    use serde_json::{Value, json};
    use std::collections::HashMap;
    use std::sync::Arc;

    /// Most tools one plugin may add.
    const MAX_TOOLS: usize = 500;

    /// Which plugin and tool name serve each tool id.
    #[derive(Default)]
    struct WasmRoutes(HashMap<&'static str, (Arc<WasmPlugin>, String)>);

    pub fn install(session: &mut Session, configs: Vec<WasmPluginConfig>, tools: &mut Vec<RuntimeTool>) {
        let mut routes = WasmRoutes::default();
        let mut checks = PluginChecks::default();
        for p in configs {
            if !RuntimeTool::valid_id(&p.id) {
                log::error!("WASM plugin {:?} skipped: ids are lower-case letters, digits and _", p.id);
                continue;
            }
            let Some(set) = custom_toolset(&p.id) else { continue };
            let loaded = WasmPlugin::load(&p.path).and_then(|w| {
                let (has_tools, has_checks) = w.exports()?;
                if !has_tools && !has_checks {
                    return Err(ToolError::invalid("it exports neither craft-anything:plugin/tools nor craft-anything:plugin/checks"));
                }
                let tools = if has_tools { w.describe()? } else { Vec::new() };
                let found = if has_checks { w.describe_checks()? } else { Vec::new() };
                Ok((w, tools, found))
            });
            let (plugin, described, plugin_checks) = match loaded {
                Ok(x) => x,
                Err(e) => {
                    log::error!("WASM plugin {} skipped: {}", p.id, e.message);
                    continue;
                }
            };
            let plugin = Arc::new(plugin);
            for c in plugin_checks.into_iter().take(MAX_TOOLS) {
                let id = format!("{}_{}", p.id, c.name);
                if !RuntimeTool::valid_id(&id) || checks.0.iter().any(|x| x.id == id) {
                    log::error!("WASM plugin {} check {:?} skipped (its id {id:?} is invalid or taken)", p.id, c.name);
                    continue;
                }
                let (pl, name) = (plugin.clone(), c.name.clone());
                checks.0.push(Arc::new(PluginCheck {
                    id: Box::leak(id.into_boxed_str()),
                    title: c.title.clone().unwrap_or_else(|| format!("{}: {}", p.display_name(), c.name)),
                    kinds: c.kinds,
                    extensions: c.extensions,
                    run: Box::new(move |build| pl.run_check(&name, build)),
                }));
            }
            for t in described.into_iter().take(MAX_TOOLS) {
                let mut id = format!("{}_{}", p.id, t.name);
                id.truncate(64);
                if !RuntimeTool::valid_id(&id) || tools.iter().any(|x| x.id == id) {
                    log::error!("WASM plugin {} tool {:?} skipped (its id {id:?} is invalid or taken)", p.id, t.name);
                    continue;
                }
                let leaked: &'static str = Box::leak(id.clone().into_boxed_str());
                routes.0.insert(leaked, (plugin.clone(), t.name.clone()));
                tools.push(RuntimeTool {
                    id,
                    title: t.title.clone().unwrap_or_else(|| format!("{}: {}", p.display_name(), t.name)),
                    summary: t
                        .description
                        .clone()
                        .filter(|d| !d.trim().is_empty())
                        .unwrap_or_else(|| format!("{} from the {} plugin.", t.name, p.display_name())),
                    beginner: format!("A tool from the {} plugin.", p.display_name()),
                    toolset: set,
                    // Sandboxed: no files, network or programs; bounded work and memory.
                    effects: Effects::IDEMPOTENT,
                    requires: Requires::Nothing,
                    schema: if t.input_schema.is_object() { t.input_schema.clone() } else { json!({"type": "object"}) },
                    run: call_wasm,
                });
            }
        }
        session.ext.insert(Arc::new(routes));
        session.ext.insert(Arc::new(checks));
    }

    fn call_wasm(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
        let routes = ctx.session.ext.get::<WasmRoutes>().ok_or_else(|| ToolError::internal("WASM plugins aren't loaded in this session"))?;
        let (plugin, name) = routes.0.get(ctx.tool).ok_or_else(|| ToolError::internal(format!("no WASM plugin serves {}", ctx.tool)))?;
        let input = if params.is_null() { json!({}) } else { params };
        Ok(ToolOutput::Value(plugin.call(name, &input)?))
    }
}

#[cfg(all(test, feature = "wasm-plugins"))]
mod tests {
    use super::*;
    use crate::tool::ToolOutput;
    use crate::{CallOptions, Caller, Engine};
    use serde_json::json;

    #[test]
    fn a_configured_plugin_adds_tools_that_run_without_asking() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("echo.wat");
        std::fs::write(&path, craft_anything_testkit::wasm_plugin::echo_plugin_wat(false)).unwrap();
        let mut s = crate::testing::session();
        s.settings.plugins.wasm = vec![
            WasmPluginConfig { id: "wordtools".into(), name: None, path, enabled: true },
            WasmPluginConfig { id: "missing".into(), name: None, path: dir.path().join("nope.wasm"), enabled: true },
        ];
        let tools = crate::plugins::install(&mut s);
        assert_eq!(tools.iter().map(|t| t.id.as_str()).collect::<Vec<_>>(), ["wordtools_echo"], "the missing plugin is skipped");
        let e = Engine::shared_with(s, Vec::new(), tools);
        let out = e.call("wordtools_echo", json!({"text": "hi"}), CallOptions::new(Caller::Mcp)).unwrap();
        assert!(matches!(out, ToolOutput::Value(v) if v == json!({"text": "hi"})));
    }

    #[test]
    fn a_plugin_with_checks_offers_them_to_the_rebuild() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("judge.wat");
        std::fs::write(&path, craft_anything_testkit::wasm_plugin::check_plugin_wat(true)).unwrap();
        let mut s = crate::testing::session();
        s.settings.plugins.wasm = vec![WasmPluginConfig { id: "judge".into(), name: None, path, enabled: true }];
        assert!(crate::plugins::install(&mut s).is_empty(), "checks only: no tools");
        let found = checks(&s);
        assert_eq!(found.len(), 1);
        assert_eq!((found[0].id, found[0].kinds.as_slice()), ("judge_looks_fine", &["game".to_string()][..]));
        assert_eq!(found[0].run(&json!({"files": []})).unwrap()["passed"], true);
    }
}
