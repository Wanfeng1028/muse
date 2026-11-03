//! Engines and settings as tools, so a computer can be set up without the app: what's installed,
//! installing Ghidra, Godot or a pinned engine, and reading or changing settings. Ids follow
//! docs/tool-ids.md.

use crate::settings::Settings;
use crate::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use craft_anything_engines::game::{self, Builder};
use craft_anything_evidence::{ErrorCode, ToolError};
use schemars::JsonSchema;
use serde::Deserialize;
use serde_json::{Value, json};
use std::sync::Arc;

pub fn specs() -> Vec<ToolSpec> {
    vec![
        ToolSpec {
            id: "engines_list",
            title: "List engines",
            summary: "What's on this computer: each external engine (where it was found, what it's for, whether it can be installed for you), Ghidra for Deep mode, and the game engines that can build games (Unity, Unreal, Godot, Rust) with whether each is ready.",
            beginner: "Shows which helper programs are installed.",
            toolset: Toolset::Setup,
            effects: Effects::READ_ONLY,
            requires: Requires::Nothing,
            input_schema: schema_of::<NoParams>,
            run: engines_list,
        },
        ToolSpec {
            id: "engines_install",
            title: "Install an engine",
            summary: "Download and install an engine into Craft Anything's own folder: `ghidra` (Deep mode, with its Java), `godot`, or any engine with a pinned download (`adb`, `jadx`…). Every download is checked against its published SHA-256. Unity and Unreal need their vendors' installers and accounts: on Windows the installer (Unity Hub, the Epic Games Launcher) is downloaded, its publisher checked, and opened for the person; elsewhere they get the download page.",
            beginner: "Installs a helper program for you.",
            toolset: Toolset::Setup,
            effects: Effects::ACCESSES_NETWORK.union(Effects::WRITES_FILESYSTEM).union(Effects::LAUNCHES_PROCESS),
            requires: Requires::Nothing,
            input_schema: schema_of::<InstallParams>,
            run: engines_install,
        },
        ToolSpec {
            id: "settings_show",
            title: "Show settings",
            summary: "The current settings as JSON (mode, Auto mode, Deep mode/Ghidra, engine paths, projects folder, asset budget and picture model, AI backends). API keys are never in settings.",
            beginner: "Shows your settings.",
            toolset: Toolset::Setup,
            effects: Effects::READ_ONLY,
            requires: Requires::Nothing,
            input_schema: schema_of::<NoParams>,
            run: settings_show,
        },
        ToolSpec {
            id: "settings_set",
            title: "Change a setting",
            summary: "Set one setting by its dotted key from settings_show (`auto_mode`, `deep_mode`, `projects_dir`, `assets.budget_usd`…) to a JSON value, then save. Unknown keys and values of the wrong type are refused, and nothing is written.",
            beginner: "Changes one of your settings.",
            toolset: Toolset::Setup,
            effects: Effects::WRITES_FILESYSTEM.union(Effects::MUTATES_SESSION),
            requires: Requires::Nothing,
            input_schema: schema_of::<SetParams>,
            run: settings_set,
        },
        ToolSpec {
            id: "plugins_list",
            title: "List plugins",
            summary: "The external MCP servers configured as plugins ([[plugins.mcp]] in config.toml): id, command, whether it's on and asks before each call, and the tools cached from its last refresh.",
            beginner: "Shows the add-ons you've set up.",
            toolset: Toolset::Setup,
            effects: Effects::READ_ONLY,
            requires: Requires::Nothing,
            input_schema: schema_of::<NoParams>,
            run: plugins_list,
        },
        ToolSpec {
            id: "plugins_refresh",
            title: "Refresh plugins",
            summary: "Start a plugin's MCP server (or every enabled one), read its tool list and cache it. New or changed tools are offered from the next start of the app or CLI. It runs the plugin's program, so it needs consent.",
            beginner: "Reads which tools an add-on offers.",
            toolset: Toolset::Setup,
            effects: Effects::LAUNCHES_PROCESS.union(Effects::WRITES_FILESYSTEM).union(Effects::EXECUTES_FOREIGN_CODE),
            requires: Requires::Nothing,
            input_schema: schema_of::<RefreshParams>,
            run: plugins_refresh,
        },
        ToolSpec {
            id: "plugins_add",
            title: "Add a plugin",
            summary: "Add an external MCP server as a plugin ([[plugins.mcp]] in config.toml): an id, and either a command (a local server, with args, env and cwd) or a url (a remote https server, with headers). A plugin added here always asks before each call. replace overwrites a plugin with the same id. Run plugins_refresh next to read its tools.",
            beginner: "Adds an add-on: another program or server whose tools Craft Anything can use.",
            toolset: Toolset::Setup,
            effects: Effects::WRITES_FILESYSTEM.union(Effects::MUTATES_SESSION),
            requires: Requires::Nothing,
            input_schema: schema_of::<AddPluginParams>,
            run: plugins_add,
        },
        ToolSpec {
            id: "plugins_remove",
            title: "Remove a plugin",
            summary: "Remove a plugin from config.toml by its id. Its tools stop being offered from the next start.",
            beginner: "Removes an add-on.",
            toolset: Toolset::Setup,
            effects: Effects::WRITES_FILESYSTEM.union(Effects::MUTATES_SESSION),
            requires: Requires::Nothing,
            input_schema: schema_of::<RemovePluginParams>,
            run: plugins_remove,
        },
        ToolSpec {
            id: "engines_app_open",
            title: "Open an engine's app",
            summary: "Open Unity Hub or the Epic Games Launcher (to sign in and install the Unity Editor or Unreal Engine), found on this computer. Only those two; nothing else is started.",
            beginner: "Opens Unity Hub or the Epic Games Launcher.",
            toolset: Toolset::Setup,
            effects: Effects::LAUNCHES_PROCESS,
            requires: Requires::Nothing,
            input_schema: schema_of::<AppOpenParams>,
            run: engines_app_open,
        },
    ]
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct AppOpenParams {
    /// `unity_hub` or `epic_launcher`.
    pub app: String,
}

fn engines_app_open(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: AppOpenParams = parse_params(params)?;
    let inv = game::inventory(&game::Places::here(ctx.session.settings.engine_store_dir()));
    let path = match p.app.as_str() {
        "unity_hub" => inv.unity_hub,
        "epic_launcher" => inv.epic_launcher,
        other => return Err(ToolError::invalid(format!("{other:?} isn't an app this can open.")).with_remediation("Use unity_hub or epic_launcher.")),
    };
    let Some(path) = path else {
        return Err(ToolError::new(ErrorCode::NotFound, format!("{} isn't installed on this computer.", p.app))
            .with_remediation("Install it first (engines_install unity or unreal)."));
    };
    let launch = if path.extension().is_some_and(|e| e == "app") {
        craft_anything_platform::Launch::new("open").arg(&path)
    } else {
        craft_anything_platform::Launch::new(&path)
    };
    launch.label(p.app.clone()).start()?;
    Ok(ToolOutput::Value(json!({"opened": path.display().to_string()})))
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct AddPluginParams {
    /// Toolset id and tool-id prefix: lower-case letters, digits and `_`.
    pub id: String,
    /// The name people see (default: the id).
    #[serde(default)]
    pub name: Option<String>,
    /// The program of a local server.
    #[serde(default)]
    pub command: String,
    #[serde(default)]
    pub args: Vec<String>,
    #[serde(default)]
    pub env: std::collections::BTreeMap<String, String>,
    #[serde(default)]
    pub cwd: Option<std::path::PathBuf>,
    /// A remote server's address: `https://…`, or `http://` to this computer.
    #[serde(default)]
    pub url: Option<String>,
    /// Sent with every request to a remote server (e.g. `Authorization`).
    #[serde(default)]
    pub headers: std::collections::BTreeMap<String, String>,
    /// A WASM component plugin's file (full path to a `.wasm`), instead of a command or url. Its
    /// tools load from the next start, in a build with the `wasm-plugins` feature.
    #[serde(default)]
    pub wasm: Option<std::path::PathBuf>,
    /// Overwrite a plugin with the same id.
    #[serde(default)]
    pub replace: bool,
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct RemovePluginParams {
    pub id: String,
}

fn save_settings(ctx: &mut Ctx<'_>, next: Settings) -> Result<String, ToolError> {
    let path = ctx.session.config_dir().join("config.toml");
    next.save_to(&path)?;
    ctx.session.settings = next;
    Ok(path.display().to_string())
}

/// Whether a plugin of either kind already has this id (ids name toolsets, so they're shared).
fn plugin_id_taken(settings: &crate::Settings, id: &str) -> bool {
    settings.plugins.mcp.iter().any(|x| x.id == id) || settings.plugins.wasm.iter().any(|x| x.id == id)
}

fn add_wasm_plugin(ctx: &mut Ctx<'_>, p: AddPluginParams, path: std::path::PathBuf) -> Result<ToolOutput, ToolError> {
    if !p.command.trim().is_empty() || p.url.as_deref().is_some_and(|u| !u.trim().is_empty()) {
        return Err(ToolError::invalid("A plugin is a .wasm file, a command or a url: give one."));
    }
    let plugin = crate::wasm_plugins::WasmPluginConfig { id: p.id.trim().to_string(), name: p.name.filter(|n| !n.trim().is_empty()), path, enabled: true };
    if let Some(problem) = plugin.problem() {
        return Err(ToolError::invalid(problem));
    }
    let mut next = ctx.session.settings.clone();
    if plugin_id_taken(&next, &plugin.id) && !p.replace {
        return Err(
            ToolError::invalid(format!("There's already a plugin called {}.", plugin.id)).with_remediation("Pick another id, or pass replace to overwrite it.")
        );
    }
    next.plugins.mcp.retain(|x| x.id != plugin.id);
    match next.plugins.wasm.iter_mut().find(|x| x.id == plugin.id) {
        Some(slot) => *slot = plugin.clone(),
        None => next.plugins.wasm.push(plugin.clone()),
    }
    let path = save_settings(ctx, next)?;
    Ok(ToolOutput::Value(json!({
        "added": plugin.id,
        "kind": "wasm",
        "file": plugin.path.display().to_string(),
        "path": path,
        "next": "its tools load from the next start, in a build with the wasm-plugins feature",
    })))
}

fn plugins_add(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let mut p: AddPluginParams = parse_params(params)?;
    if let Some(path) = p.wasm.take() {
        return add_wasm_plugin(ctx, p, path);
    }
    // Added from here, a plugin always asks before each call; only config.toml can turn that off.
    let plugin = crate::plugins::McpPlugin {
        id: p.id.trim().to_string(),
        name: p.name.filter(|n| !n.trim().is_empty()),
        command: p.command.trim().to_string(),
        args: p.args,
        env: p.env,
        cwd: p.cwd,
        url: p.url.map(|u| u.trim().to_string()).filter(|u| !u.is_empty()),
        headers: p.headers,
        enabled: true,
        consent: true,
    };
    if let Some(problem) = plugin.problem() {
        return Err(ToolError::invalid(problem));
    }
    let mut next = ctx.session.settings.clone();
    if next.plugins.wasm.iter().any(|x| x.id == plugin.id) {
        if !p.replace {
            return Err(ToolError::invalid(format!("There's already a plugin called {}.", plugin.id))
                .with_remediation("Pick another id, or pass replace to overwrite it."));
        }
        next.plugins.wasm.retain(|x| x.id != plugin.id);
    }
    match next.plugins.mcp.iter().position(|x| x.id == plugin.id) {
        Some(_) if !p.replace => {
            return Err(ToolError::invalid(format!("There's already a plugin called {}.", plugin.id))
                .with_remediation("Pick another id, or pass replace to overwrite it."));
        }
        Some(i) => {
            if let Some(slot) = next.plugins.mcp.get_mut(i) {
                *slot = plugin.clone();
            }
        }
        None => next.plugins.mcp.push(plugin.clone()),
    }
    let path = save_settings(ctx, next)?;
    Ok(ToolOutput::Value(
        json!({"added": plugin.id, "runs": plugin.place(), "asks_before_each_call": true, "path": path, "next": "plugins_refresh reads its tools"}),
    ))
}

fn plugins_remove(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: RemovePluginParams = parse_params(params)?;
    let mut next = ctx.session.settings.clone();
    let before = next.plugins.mcp.len() + next.plugins.wasm.len();
    next.plugins.mcp.retain(|x| x.id != p.id);
    next.plugins.wasm.retain(|x| x.id != p.id);
    if next.plugins.mcp.len() + next.plugins.wasm.len() == before {
        return Err(ToolError::new(ErrorCode::NotFound, format!("No plugin called {}.", p.id)).with_remediation("See plugins_list for the ids."));
    }
    let path = save_settings(ctx, next)?;
    Ok(ToolOutput::Value(json!({"removed": p.id, "path": path})))
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct RefreshParams {
    /// One plugin's id (default: every enabled plugin).
    #[serde(default)]
    pub id: Option<String>,
}

fn plugins_list(ctx: &mut Ctx<'_>, _params: Value) -> Result<ToolOutput, ToolError> {
    let config = ctx.session.config_dir();
    let list: Vec<Value> = ctx
        .session
        .settings
        .plugins
        .mcp
        .iter()
        .map(|p| {
            let tools: Vec<String> = p.cached_tools(&config).into_iter().map(|t| t.name).collect();
            json!({
                "id": p.id,
                "kind": "mcp",
                "name": p.display_name(),
                "runs": p.place(),
                "remote": p.url.is_some(),
                "env": p.env.keys().collect::<Vec<_>>(),
                "headers": p.headers.keys().collect::<Vec<_>>(),
                "problem": p.problem(),
                "enabled": p.enabled,
                "asks_before_each_call": p.consent,
                "cached_tools": tools,
                "cache": p.cache_path(&config).display().to_string(),
            })
        })
        .chain(ctx.session.settings.plugins.wasm.iter().map(|p| {
            json!({
                "id": p.id,
                "kind": "wasm",
                "name": p.display_name(),
                "file": p.path.display().to_string(),
                "problem": p.problem(),
                "enabled": p.enabled,
                // No files, network or programs, and limited work and memory per call.
                "asks_before_each_call": false,
            })
        }))
        .collect();
    Ok(ToolOutput::Value(json!({"plugins": list})))
}

fn plugins_refresh(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: RefreshParams = parse_params(params)?;
    let chosen: Vec<crate::plugins::McpPlugin> = ctx
        .session
        .settings
        .plugins
        .mcp
        .iter()
        .filter(|x| match &p.id {
            Some(id) => &x.id == id,
            None => x.enabled,
        })
        .cloned()
        .collect();
    if chosen.is_empty() {
        return Err(ToolError::new(ErrorCode::NotFound, "No plugin to refresh.")
            .with_remediation("Add one with plugins_add (or under [[plugins.mcp]] in config.toml), or check its id."));
    }
    let config = ctx.session.config_dir();
    let mut out = Vec::new();
    for plugin in chosen {
        ctx.report(None, format!("Reading the {} plugin's tools…", plugin.display_name()));
        let r = match crate::plugins::refresh(&plugin, &config) {
            Ok(tools) => json!({"id": plugin.id, "tools": tools.iter().map(|t| t.name.clone()).collect::<Vec<_>>()}),
            Err(e) => json!({"id": plugin.id, "error": e.message, "remediation": e.remediation}),
        };
        out.push(r);
    }
    Ok(ToolOutput::Value(json!({"refreshed": out, "note": "New tools are offered from the next start."})))
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct NoParams {}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct InstallParams {
    /// `ghidra`, `godot`, `unity`, `unreal`, or an engine id from engines_list.
    pub engine: String,
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct SetParams {
    /// A dotted key from settings_show, e.g. `deep_mode`.
    pub key: String,
    /// The new value as JSON (`true`, `5`, `"C:/Projects"`, `null`).
    pub value: Value,
}

fn engines_list(ctx: &mut Ctx<'_>, _params: Value) -> Result<ToolOutput, ToolError> {
    let s = &ctx.session.settings;
    let store = s.engine_store_dir();
    let engines: Vec<Value> = craft_anything_engines::ENGINES
        .iter()
        .map(|e| {
            json!({
                "id": e.id,
                "name": e.name,
                "needed_for": e.needed_for,
                "found": s.engine_path(e.id).map(|p| p.display().to_string()),
                "installable_here": e.host_pin().is_some(),
            })
        })
        .collect();
    let inv = game::inventory(&game::Places::here(store.clone()));
    let builders: Vec<Value> = Builder::ALL
        .into_iter()
        .map(|b| {
            json!({
                "id": format!("{b:?}").to_lowercase(),
                "name": b.name(),
                "ready": inv.ready(b),
                "found": inv.best(b).map(|i| json!({"version": i.version, "program": i.program.display().to_string()})),
                "needs": b.needs(),
            })
        })
        .collect();
    Ok(ToolOutput::Value(json!({
        "engine_store": store.display().to_string(),
        "engines": engines,
        "deep_mode": {"enabled": s.deep_mode, "ghidra": s.ghidra_launcher().map(|p| p.display().to_string())},
        "game_engines": builders,
    })))
}

fn engines_install(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: InstallParams = parse_params(params)?;
    let id = p.engine.trim().to_ascii_lowercase();
    let store = ctx.session.settings.engine_store_dir();
    let c = ctx.cancel.clone();
    let cancel: craft_anything_platform::process::Cancel = Arc::new(move || c.is_cancelled());
    let mb = |n: u64| n / (1024 * 1024);
    let path = match id.as_str() {
        "ghidra" => {
            let progress = |what: &str, got: u64, total: Option<u64>| {
                let fraction = total.filter(|t| *t > 0).map(|t| got as f32 / t as f32);
                ctx.report(fraction, format!("{what}: {} of {} MB", mb(got), total.map_or("?".into(), |t| mb(t).to_string())));
            };
            craft_anything_engines::ghidra::get::install(&store, Some(cancel), &progress)?
        }
        "godot" => {
            let progress = |got: u64, total: Option<u64>| {
                let fraction = total.filter(|t| *t > 0).map(|t| got as f32 / t as f32);
                ctx.report(fraction, format!("Godot: {} of {} MB", mb(got), total.map_or("?".into(), |t| mb(t).to_string())));
            };
            game::install_godot(&store, Some(cancel), &progress)?
        }
        "unity" | "unreal" if game::installer(if id == "unity" { Builder::Unity } else { Builder::Unreal }).is_some() => {
            let b = if id == "unity" { Builder::Unity } else { Builder::Unreal };
            let progress = |got: u64, total: Option<u64>| {
                let fraction = total.filter(|t| *t > 0).map(|t| got as f32 / t as f32);
                ctx.report(fraction, format!("{} installer: {} of {} MB", b.name(), mb(got), total.map_or("?".into(), |t| mb(t).to_string())));
            };
            let file = game::download_installer(b, &store.join("installers"), Some(cancel), &progress)?;
            game::run_installer(&file)?;
            return Ok(ToolOutput::Value(json!({"installer_opened": file.display().to_string(), "engine": id})));
        }
        "unity" | "unreal" => {
            let b = if id == "unity" { Builder::Unity } else { Builder::Unreal };
            return Err(ToolError::new(
                ErrorCode::NotSupported,
                format!("{} needs its own installer and account, so it can't be installed for you.", b.name()),
            )
            .with_remediation(format!("Get it from {} ({}), then run engines_list.", game::download_page(b), b.needs())));
        }
        other => {
            let report = |m: &str| ctx.report(None, m.to_string());
            craft_anything_engines::install::install(other, &store, None, Some(cancel), &report)?.install_dir
        }
    };
    Ok(ToolOutput::Value(json!({"installed": id, "path": path.display().to_string()})))
}

fn settings_show(ctx: &mut Ctx<'_>, _params: Value) -> Result<ToolOutput, ToolError> {
    let mut settings = serde_json::to_value(&ctx.session.settings).map_err(|e| ToolError::internal(e.to_string()))?;
    // Plugins' environment and headers may hold keys: their names are shown, never their values.
    for p in settings.pointer_mut("/plugins/mcp").and_then(Value::as_array_mut).into_iter().flatten() {
        for field in ["env", "headers"] {
            for v in p.get_mut(field).and_then(Value::as_object_mut).into_iter().flat_map(|m| m.values_mut()) {
                *v = json!("(hidden)");
            }
        }
    }
    Ok(ToolOutput::Value(json!({"path": ctx.session.config_dir().join("config.toml").display().to_string(), "settings": settings})))
}

/// `settings` with `key` (dotted) set to `value`, checked by reading the result back as
/// settings. Only keys that exist can be set; `version` belongs to the file format.
pub fn with_setting(settings: &Settings, key: &str, value: Value) -> Result<Settings, ToolError> {
    let parts: Vec<&str> = key.split('.').map(str::trim).collect();
    if parts.iter().any(|p| p.is_empty()) || parts.first() == Some(&"version") {
        return Err(ToolError::invalid(format!("{key:?} isn't a setting you can change.")).with_remediation("Use a dotted key from settings_show."));
    }
    let mut doc = serde_json::to_value(settings).map_err(|e| ToolError::internal(e.to_string()))?;
    let mut pointer = String::new();
    for (i, part) in parts.iter().enumerate() {
        let Some(obj) = doc.pointer(&pointer).and_then(Value::as_object) else {
            return Err(ToolError::invalid(format!("{} has no settings inside it.", parts.get(..i).unwrap_or_default().join("."))));
        };
        if !obj.contains_key(*part) {
            let mut keys: Vec<&str> = obj.keys().map(String::as_str).collect();
            keys.sort_unstable();
            return Err(ToolError::invalid(format!("There's no setting {key:?}.")).with_remediation(format!("Keys here: {}.", keys.join(", "))));
        }
        pointer.push('/');
        pointer.push_str(&part.replace('~', "~0").replace('/', "~1"));
    }
    if let Some(slot) = doc.pointer_mut(&pointer) {
        *slot = value;
    }
    let mut next: Settings = serde_json::from_value(doc)
        .map_err(|e| ToolError::invalid(format!("That value doesn't fit {key}: {e}")).with_remediation("Check the type in settings_show."))?;
    // Not part of the saved settings, so the round trip above drops it: keep this session's.
    next.engines.only_configured = settings.engines.only_configured;
    Ok(next)
}

fn settings_set(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: SetParams = parse_params(params)?;
    let next = with_setting(&ctx.session.settings, &p.key, p.value)?;
    let path = ctx.session.config_dir().join("config.toml");
    next.save_to(&path)?;
    ctx.session.settings = next;
    Ok(ToolOutput::Value(json!({"set": p.key, "path": path.display().to_string()})))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{CallOptions, Caller, Engine};

    #[test]
    fn a_setting_is_changed_by_its_dotted_key_and_checked() {
        let s = Settings::default();
        let on = with_setting(&s, "deep_mode", json!(true)).unwrap();
        assert!(on.deep_mode);
        assert!(!with_setting(&s, "auto_mode", json!(false)).unwrap().auto_mode);
        assert!(with_setting(&s, "auto_mode", json!("yes")).is_err(), "wrong type");
        let e = with_setting(&s, "engines.ghidra.memry_gb", json!(8)).unwrap_err();
        assert!(e.remediation.unwrap_or_default().contains("memory_gb"), "unknown keys list what's there");
        assert!(with_setting(&s, "version", json!(9)).is_err());
        assert!(with_setting(&s, "auto_mode.inner", json!(1)).is_err());
        assert!(with_setting(&s, "", json!(1)).is_err());
    }

    #[test]
    fn plugins_are_added_and_removed_through_tools() {
        let s = crate::testing::session();
        let config = s.config_dir().join("config.toml");
        let e = Engine::new(s);
        let call = |id: &str, p: Value| e.call(id, p, CallOptions::new(Caller::Cli)).map(|o| o.to_json()["result"].clone());
        let r = call("plugins_add", json!({"id": "docs", "url": "https://mcp.example.com/mcp", "headers": {"Authorization": "Bearer sk-9"}})).unwrap();
        assert_eq!(r["asks_before_each_call"], true);
        let saved = std::fs::read_to_string(&config).unwrap();
        assert!(saved.contains("docs") && saved.contains("https://mcp.example.com/mcp"), "{saved}");
        let list = call("plugins_list", json!({})).unwrap();
        assert_eq!(list["plugins"][0]["id"], "docs");
        assert!(!list.to_string().contains("sk-9"), "keys are never shown");

        // Same id again needs replace; bad shapes are refused before anything is written.
        assert!(call("plugins_add", json!({"id": "docs", "command": "docs-server"})).unwrap_err().message.contains("already"));
        assert!(call("plugins_add", json!({"id": "docs", "command": "docs-server", "replace": true})).is_ok());
        assert!(call("plugins_add", json!({"id": "Bad-Id", "command": "x"})).is_err());
        assert!(call("plugins_add", json!({"id": "both", "command": "x", "url": "https://a.example.com"})).is_err());
        assert!(call("plugins_add", json!({"id": "plain", "url": "http://example.com/mcp"})).is_err(), "remote needs https");
        assert!(call("plugins_add", json!({"id": "x", "command": "y", "consent": false})).is_err(), "no way to turn asking off here");

        call("plugins_remove", json!({"id": "docs"})).unwrap();
        assert_eq!(call("plugins_list", json!({})).unwrap()["plugins"], json!([]));
        assert!(call("plugins_remove", json!({"id": "docs"})).is_err());
    }

    #[test]
    fn wasm_plugins_are_added_listed_and_removed_through_tools() {
        let dir = tempfile::tempdir().unwrap();
        let file = dir.path().join("words.wasm");
        std::fs::write(&file, b"\0asm").unwrap();
        let s = crate::testing::session();
        let config = s.config_dir().join("config.toml");
        let e = Engine::new(s);
        let call = |id: &str, p: Value| e.call(id, p, CallOptions::new(Caller::Cli)).map(|o| o.to_json()["result"].clone());
        let r = call("plugins_add", json!({"id": "words", "wasm": file})).unwrap();
        assert_eq!(r["kind"], "wasm");
        assert!(std::fs::read_to_string(&config).unwrap().contains("[[plugins.wasm]]"));
        let list = call("plugins_list", json!({})).unwrap();
        assert_eq!((&list["plugins"][0]["kind"], &list["plugins"][0]["problem"]), (&json!("wasm"), &Value::Null));

        // One id across both kinds; a .wasm is a file, not also a command; the file must be there.
        assert!(call("plugins_add", json!({"id": "words", "command": "x"})).unwrap_err().message.contains("already"));
        assert!(call("plugins_add", json!({"id": "other", "wasm": file, "command": "x"})).is_err());
        assert!(call("plugins_add", json!({"id": "gone", "wasm": dir.path().join("gone.wasm")})).unwrap_err().message.contains("isn't there"));
        assert!(call("plugins_add", json!({"id": "rel", "wasm": "words.wasm"})).unwrap_err().message.contains("full path"));

        call("plugins_remove", json!({"id": "words"})).unwrap();
        assert_eq!(call("plugins_list", json!({})).unwrap()["plugins"], json!([]));
    }

    #[test]
    fn plugin_keys_are_never_shown() {
        let mut s = crate::testing::session();
        let toml =
            "[[mcp]]\nid = \"docs\"\nurl = \"https://mcp.example.com/mcp\"\nheaders = { Authorization = \"Bearer sk-1\" }\nenv = { API_KEY = \"sk-2\" }\n";
        s.settings.plugins = toml::from_str(toml).unwrap();
        let e = Engine::new(s);
        for tool in ["settings_show", "plugins_list"] {
            let out = e.call(tool, json!({}), CallOptions::new(Caller::Cli)).unwrap().to_json().to_string();
            assert!(!out.contains("sk-1") && !out.contains("sk-2"), "{tool}: {out}");
            assert!(out.contains("Authorization") && out.contains("API_KEY"), "{tool} still names them");
        }
    }

    #[test]
    fn engines_are_listed_and_vendor_installs_get_their_page() {
        let e = Engine::new(crate::testing::session());
        let out = e.call("engines_list", json!({}), CallOptions::new(Caller::Cli)).unwrap().to_json();
        let ids: Vec<&str> = out["result"]["engines"].as_array().unwrap().iter().filter_map(|v| v["id"].as_str()).collect();
        assert!(ids.contains(&"adb") && ids.contains(&"ghidra"), "{ids:?}");
        assert_eq!(out["result"]["game_engines"].as_array().map(Vec::len), Some(4));
        // Never a real download in tests: an engine nobody knows is refused before any network use.
        // (Unity/Unreal would download and open the vendor's installer on Windows.)
        assert!(e.call("engines_install", json!({"engine": "no-such-engine"}), CallOptions::new(Caller::Cli)).is_err());
    }

    /// A Ghidra chosen through its own folder setting is what Deep mode runs, so the listing says
    /// it's there (it once said "not found" while `native_function_pseudocode` used it).
    #[test]
    fn a_ghidra_folder_setting_shows_in_engines_list() {
        let dir = tempfile::tempdir().unwrap();
        let exe = if cfg!(windows) { "analyzeHeadless.bat" } else { "analyzeHeadless" };
        let launcher = dir.path().join("support").join(exe);
        std::fs::create_dir_all(launcher.parent().unwrap()).unwrap();
        std::fs::write(&launcher, b"x").unwrap();
        let mut s = crate::testing::session();
        s.settings.engines.ghidra.install_dir = Some(dir.path().to_path_buf());
        assert_eq!(s.settings.engine_path("ghidra"), Some(launcher.clone()));
        let e = Engine::new(s);
        let out = e.call("engines_list", json!({}), CallOptions::new(Caller::Cli)).unwrap().to_json();
        let ghidra = out["result"]["engines"].as_array().unwrap().iter().find(|v| v["id"] == "ghidra").unwrap();
        assert_eq!(ghidra["found"].as_str(), Some(launcher.display().to_string().as_str()));
        assert_eq!(out["result"]["deep_mode"]["ghidra"], ghidra["found"]);
    }

    #[test]
    fn an_isolated_session_keeps_settings_in_its_own_folder() {
        let s = crate::testing::session();
        let dir = s.config_dir();
        let e = Engine::new(s);
        let out = e.call("settings_set", json!({"key": "auto_mode", "value": false}), CallOptions::new(Caller::Cli)).unwrap().to_json();
        let path = std::path::PathBuf::from(out["result"]["path"].as_str().unwrap());
        assert!(path.starts_with(&dir), "{} is under {}", path.display(), dir.display());
        assert!(std::fs::read_to_string(&path).unwrap().contains("auto_mode = false"));
        assert_ne!(dir, crate::settings::config_dir(), "never the computer's own folder");
        assert!(e.session().settings.engines.only_configured, "changing a setting keeps the test session from finding this computer's engines");
        assert_eq!(e.session().settings.ghidra_launcher(), None);
    }
}
