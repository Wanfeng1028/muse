//! WASM component plugins (R1.8), with the `wasm-plugins` feature: a component that exports the
//! `craft-anything:plugin/tools` interface (`wit/plugin.wit`) adds tools. It imports nothing, so
//! it can't reach files, the network, the environment or other programs: its only way out is the
//! JSON it returns. Each call runs in a fresh instance with a fuel budget (bounded work) and a
//! memory cap, so a plugin can't hang or exhaust the app, and nothing carries over between calls.

use craft_anything_evidence::{ErrorCode, ToolError};
use serde::Deserialize;
use serde_json::Value;
use std::path::Path;
use wasmtime::component::{Component, Instance, Linker};
use wasmtime::{Config, Engine, Store, StoreLimits, StoreLimitsBuilder};

/// The plugin API version this host speaks (`package craft-anything:plugin@…` in plugin.wit).
pub const API_VERSION: &str = "0.1.0";
/// The interface a plugin exports to add tools, at [`API_VERSION`].
pub const INTERFACE: &str = "craft-anything:plugin/tools@0.1.0";
/// The interface a plugin exports to add checks, at [`API_VERSION`].
pub const CHECKS_INTERFACE: &str = "craft-anything:plugin/checks@0.1.0";
const TOOLS_BASE: &str = "craft-anything:plugin/tools";
const CHECKS_BASE: &str = "craft-anything:plugin/checks";

/// Whether a plugin built against API `found` works with this host (`ours`): semver, so the same
/// major version, and for 0.x the same minor too. Patch versions only add optional JSON fields.
pub fn compatible(found: &str, ours: &str) -> bool {
    let parse = |v: &str| -> Option<(u64, u64)> {
        let mut parts = v.split('.');
        let major = parts.next()?.parse().ok()?;
        let minor = parts.next()?.parse().ok()?;
        parts.next()?.split(['-', '+']).next()?.parse::<u64>().ok()?;
        Some((major, minor))
    };
    match (parse(found), parse(ours)) {
        (Some((0, a)), Some((0, b))) => a == b,
        (Some((a, _)), Some((b, _))) => a == b,
        _ => false,
    }
}

/// The export of `base` (`craft-anything:plugin/tools`) among `exports` that this host can use:
/// `Ok(None)` when there's none, an error when there's one built for an incompatible version.
fn resolve<'a>(exports: impl Iterator<Item = &'a str>, base: &str) -> Result<Option<String>, ToolError> {
    let mut incompatible = None;
    for name in exports {
        let Some(version) = name.strip_prefix(base).and_then(|r| r.strip_prefix('@')) else { continue };
        if compatible(version, API_VERSION) {
            return Ok(Some(name.to_string()));
        }
        incompatible = Some(version.to_string());
    }
    match incompatible {
        Some(v) => Err(ToolError::new(ErrorCode::NotSupported, format!("The plugin exports {base} for API {v}; this Craft Anything speaks {API_VERSION}."))
            .with_remediation("Rebuild the plugin against this version's plugin.wit, or use a Craft Anything that matches it.")),
        None => Ok(None),
    }
}
/// The WIT text of the interface, for plugin authors.
pub const WIT: &str = include_str!("../wit/plugin.wit");
/// Work allowed per call (roughly instructions); a plugin that runs past it is stopped.
pub const FUEL_PER_CALL: u64 = 2_000_000_000;
/// Memory a plugin may grow to.
pub const MAX_MEMORY: usize = 256 << 20;
/// Largest component file read.
const MAX_FILE: u64 = 64 << 20;
/// Largest JSON a plugin may return.
const MAX_OUTPUT: usize = 16 << 20;

/// One tool a plugin offers (from its `describe`).
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct PluginTool {
    pub name: String,
    #[serde(default)]
    pub title: Option<String>,
    #[serde(default)]
    pub description: Option<String>,
    #[serde(default)]
    pub input_schema: Value,
}

/// One check a plugin offers (from its checks `describe`).
#[derive(Debug, Clone, PartialEq, Deserialize)]
pub struct PluginCheckInfo {
    pub name: String,
    #[serde(default)]
    pub title: Option<String>,
    #[serde(default)]
    pub description: Option<String>,
    /// Kinds of project it judges; empty means all.
    #[serde(default)]
    pub kinds: Vec<String>,
    /// File extensions whose text it wants (without the dot).
    #[serde(default)]
    pub extensions: Vec<String>,
}

/// A compiled plugin, ready to call.
pub struct WasmPlugin {
    engine: Engine,
    component: Component,
    linker: Linker<StoreLimits>,
    /// The exported tools and checks interfaces it uses (with their versions), if any.
    tools: Option<String>,
    checks: Option<String>,
}

fn plugin_error(what: &str, e: impl std::fmt::Display) -> ToolError {
    ToolError::new(ErrorCode::ProgramFailed, format!("The plugin {what}: {e}"))
}

impl WasmPlugin {
    /// Compile the component in `path` (a `.wasm` component, or its text form).
    pub fn load(path: &Path) -> Result<Self, ToolError> {
        let meta = std::fs::metadata(path).map_err(|e| ToolError::io(path.display(), e))?;
        if meta.len() > MAX_FILE {
            return Err(ToolError::new(ErrorCode::OverLimit, format!("{} is larger than 64 MiB", path.display())));
        }
        let bytes = std::fs::read(path).map_err(|e| ToolError::io(path.display(), e))?;
        Self::from_bytes(&bytes)
    }

    /// Compile a component from its bytes (binary or text).
    pub fn from_bytes(bytes: &[u8]) -> Result<Self, ToolError> {
        let mut config = Config::new();
        config.wasm_component_model(true).consume_fuel(true);
        let engine = Engine::new(&config).map_err(|e| ToolError::internal(format!("WASM runtime: {e}")))?;
        let component = Component::new(&engine, bytes).map_err(|e| {
            ToolError::invalid(format!("not a usable WASM component: {e}"))
                .with_remediation(format!("Build the plugin as a component exporting {INTERFACE} (see wit/plugin.wit) that imports nothing."))
        })?;
        // Nothing is linked in: a plugin that imports anything fails to instantiate.
        let linker = Linker::new(&engine);
        let ty = component.component_type();
        let names: Vec<&str> = ty.exports(&engine).map(|(n, _)| n).collect();
        let tools = resolve(names.iter().copied(), TOOLS_BASE)?;
        let checks = resolve(names.iter().copied(), CHECKS_BASE)?;
        Ok(WasmPlugin { engine, component, linker, tools, checks })
    }

    /// The interfaces it exports and their versions, e.g. `craft-anything:plugin/tools@0.1.0`.
    pub fn interfaces(&self) -> Vec<&str> {
        self.tools.iter().chain(self.checks.iter()).map(String::as_str).collect()
    }

    /// A fresh, limited instance.
    fn instance(&self) -> Result<(Store<StoreLimits>, Instance), ToolError> {
        let mut store = Store::new(&self.engine, StoreLimitsBuilder::new().memory_size(MAX_MEMORY).instances(16).build());
        store.limiter(|l| l);
        store.set_fuel(FUEL_PER_CALL).map_err(|e| ToolError::internal(format!("WASM fuel: {e}")))?;
        let instance = self.linker.instantiate(&mut store, &self.component).map_err(|e| {
            plugin_error("couldn't start", e).with_remediation("Plugins may import nothing (no WASI): they get no files, network or environment.")
        })?;
        Ok((store, instance))
    }

    /// Which of the interfaces it exports: (tools, checks).
    pub fn exports(&self) -> Result<(bool, bool), ToolError> {
        Ok((self.tools.is_some(), self.checks.is_some()))
    }

    fn tools_name(&self) -> Result<&str, ToolError> {
        self.tools.as_deref().ok_or_else(|| ToolError::invalid(format!("the plugin doesn't export {TOOLS_BASE} (API {API_VERSION})")))
    }

    fn checks_name(&self) -> Result<&str, ToolError> {
        self.checks.as_deref().ok_or_else(|| ToolError::invalid(format!("the plugin doesn't export {CHECKS_BASE} (API {API_VERSION})")))
    }

    /// Call one function of an exported interface that returns a string.
    fn call_export<P>(&self, interface: &str, name: &str, params: P) -> Result<String, ToolError>
    where
        P: wasmtime::component::ComponentNamedList + wasmtime::component::Lower + Send + Sync,
    {
        let (mut store, instance) = self.instance()?;
        let iface =
            instance.get_export_index(&mut store, None, interface).ok_or_else(|| ToolError::invalid(format!("the plugin doesn't export {interface}")))?;
        let idx =
            instance.get_export_index(&mut store, Some(&iface), name).ok_or_else(|| ToolError::invalid(format!("the plugin's {interface} has no {name}")))?;
        let f = instance.get_typed_func::<P, (String,)>(&mut store, &idx).map_err(|e| plugin_error(&format!("has a {name} of the wrong type"), e))?;
        let (out,) = f.call(&mut store, params).map_err(|e| {
            let out_of_fuel = store.get_fuel().is_ok_and(|f| f == 0);
            if out_of_fuel {
                ToolError::new(ErrorCode::OverLimit, format!("The plugin's {name} ran past its work limit and was stopped"))
            } else {
                plugin_error(&format!("failed in {name}"), e)
            }
        })?;
        if out.len() > MAX_OUTPUT {
            return Err(ToolError::new(ErrorCode::OverLimit, format!("The plugin's {name} returned more than 16 MiB")));
        }
        Ok(out)
    }

    /// The tools the plugin offers.
    pub fn describe(&self) -> Result<Vec<PluginTool>, ToolError> {
        let text = self.call_export(self.tools_name()?, "describe", ())?;
        serde_json::from_str(&text).map_err(|e| plugin_error("described its tools in JSON we couldn't read", e))
    }

    /// Run one of its tools. The plugin answers `{"ok": …}` or `{"error": "…"}`.
    pub fn call(&self, tool: &str, input: &Value) -> Result<Value, ToolError> {
        let text = self.call_export(self.tools_name()?, "call", (tool.to_string(), input.to_string()))?;
        let v: Value = serde_json::from_str(&text).map_err(|e| plugin_error("answered with JSON we couldn't read", e))?;
        if let Some(err) = v.get("error") {
            let msg = err.as_str().map(str::to_string).unwrap_or_else(|| err.to_string());
            return Err(ToolError::new(ErrorCode::ProgramFailed, format!("The plugin's {tool} failed: {msg}")));
        }
        v.get("ok").cloned().ok_or_else(|| ToolError::new(ErrorCode::GarbledOutput, format!("The plugin's {tool} answered without ok or error")))
    }

    /// The checks the plugin offers.
    pub fn describe_checks(&self) -> Result<Vec<PluginCheckInfo>, ToolError> {
        let text = self.call_export(self.checks_name()?, "describe", ())?;
        serde_json::from_str(&text).map_err(|e| plugin_error("described its checks in JSON we couldn't read", e))
    }

    /// Run one of its checks on `build`; its answer (`passed`, `similarity`, `summary`).
    pub fn run_check(&self, check: &str, build: &Value) -> Result<Value, ToolError> {
        let text = self.call_export(self.checks_name()?, "run", (check.to_string(), build.to_string()))?;
        let v: Value = serde_json::from_str(&text).map_err(|e| plugin_error("answered with JSON we couldn't read", e))?;
        if let Some(err) = v.get("error") {
            let msg = err.as_str().map(str::to_string).unwrap_or_else(|| err.to_string());
            return Err(ToolError::new(ErrorCode::ProgramFailed, format!("The plugin's {check} check failed to run: {msg}")));
        }
        if !v.get("passed").is_some_and(Value::is_boolean) {
            return Err(ToolError::new(ErrorCode::GarbledOutput, format!("The plugin's {check} check answered without passed")));
        }
        Ok(v)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn a_plugin_describes_its_tools_and_answers_calls() {
        let p = WasmPlugin::from_bytes(craft_anything_testkit::wasm_plugin::echo_plugin_wat(false).as_bytes()).unwrap();
        let tools = p.describe().unwrap();
        assert_eq!(tools.len(), 1);
        assert_eq!((tools[0].name.as_str(), tools[0].title.as_deref()), ("echo", Some("Echo")));
        assert_eq!(p.call("echo", &json!({"x": [1, 2]})).unwrap(), json!({"x": [1, 2]}));
        // A fresh instance per call: the second answer is the same.
        assert_eq!(p.call("echo", &json!("again")).unwrap(), json!("again"));
    }

    #[test]
    fn a_plugin_that_loops_is_stopped() {
        let p = WasmPlugin::from_bytes(craft_anything_testkit::wasm_plugin::echo_plugin_wat(true).as_bytes()).unwrap();
        let e = p.call("spin", &json!({})).unwrap_err();
        assert_eq!(e.code, ErrorCode::OverLimit, "{e:?}");
    }

    /// The example plugin built for real, only where `CRAFT_ANYTHING_TEST_WASM_PLUGIN` names its
    /// component (see examples/wasm-plugin-wordcount/README.md).
    #[test]
    fn the_example_plugin_counts_words() {
        let Some(path) = std::env::var_os("CRAFT_ANYTHING_TEST_WASM_PLUGIN") else { return };
        let p = WasmPlugin::load(Path::new(&path)).unwrap();
        assert_eq!(p.describe().unwrap()[0].name, "count_words");
        assert_eq!(p.call("count_words", &json!({"text": "one two\nthree"})).unwrap(), json!({"words": 3, "lines": 2, "characters": 13}));
        assert!(p.call("count_words", &json!({})).unwrap_err().message.contains("text"));
        assert!(p.call("nope", &json!({})).is_err());
    }

    /// The example check plugin built for real, only where `CRAFT_ANYTHING_TEST_WASM_CHECK` names
    /// its component (see examples/wasm-plugin-readme-check/README.md).
    #[test]
    fn the_example_check_reads_the_readme() {
        let Some(path) = std::env::var_os("CRAFT_ANYTHING_TEST_WASM_CHECK") else { return };
        let p = WasmPlugin::load(Path::new(&path)).unwrap();
        assert_eq!(p.exports().unwrap(), (false, true));
        let info = p.describe_checks().unwrap();
        assert_eq!((info[0].name.as_str(), info[0].extensions.as_slice()), ("readme_says_how_to_run", &["md".to_string()][..]));
        let build = |files: Value| json!({"request": "A snake game", "kind": "game", "stack": "Rust", "round": 1, "files": files, "truncated": false});
        let good = build(json!([{"path": "README.md", "size": 60, "text": "# Snake\n\nA small snake game.\n\nRun it with `cargo run --release`."}]));
        assert_eq!(p.run_check("readme_says_how_to_run", &good).unwrap()["passed"], true);
        let vague = build(json!([{"path": "README.md", "size": 60, "text": "# Snake\n\nA small snake game made for fun, with apples."}]));
        let v = p.run_check("readme_says_how_to_run", &vague).unwrap();
        assert!(v["passed"] == false && v["summary"].as_str().unwrap().contains("how to start"), "{v}");
        let none = build(json!([{"path": "src/main.rs", "size": 12}]));
        assert_eq!(p.run_check("readme_says_how_to_run", &none).unwrap()["passed"], false);
        assert!(p.run_check("nope", &none).is_err());
    }

    #[test]
    fn a_plugin_can_offer_checks_instead_of_tools() {
        let p = WasmPlugin::from_bytes(craft_anything_testkit::wasm_plugin::check_plugin_wat(false).as_bytes()).unwrap();
        assert_eq!(p.exports().unwrap(), (false, true));
        let checks = p.describe_checks().unwrap();
        assert_eq!(
            (checks[0].name.as_str(), checks[0].kinds.as_slice(), checks[0].extensions.as_slice()),
            ("looks_fine", &["game".to_string()][..], &["md".to_string()][..])
        );
        let build = json!({"kind": "game", "files": [{"path": "README.md", "size": 3, "text": "hi"}]});
        let v = p.run_check("looks_fine", &build).unwrap();
        assert_eq!((v["passed"].clone(), v["similarity"].clone(), v["seen"].clone()), (json!(false), json!(70), build));
        assert!(p.describe().is_err(), "no tools interface");
        let tools = WasmPlugin::from_bytes(craft_anything_testkit::wasm_plugin::echo_plugin_wat(false).as_bytes()).unwrap();
        assert_eq!(tools.exports().unwrap(), (true, false));
    }

    #[test]
    fn imports_and_garbage_are_refused() {
        assert!(WasmPlugin::from_bytes(b"not wasm").is_err());
        let wants_host = r#"(component (import "wasi:cli/environment@0.2.0" (instance)) )"#;
        let p = WasmPlugin::from_bytes(wants_host.as_bytes()).unwrap();
        assert!(p.describe().is_err(), "nothing is linked, so it can't start");
        let empty = WasmPlugin::from_bytes(b"(component)").unwrap();
        assert!(empty.describe().unwrap_err().message.contains(TOOLS_BASE));
    }

    #[test]
    fn plugins_built_for_a_compatible_api_version_load_and_others_are_refused() {
        assert!(compatible("0.1.0", "0.1.0") && compatible("0.1.7", "0.1.0") && compatible("0.1.0", "0.1.3"));
        assert!(!compatible("0.2.0", "0.1.0") && !compatible("1.0.0", "0.1.0"), "0.x: the minor version is the breaking one");
        assert!(compatible("1.4.0", "1.0.0") && !compatible("2.0.0", "1.0.0"));
        assert!(!compatible("0.1", "0.1.0") && !compatible("x.y.z", "0.1.0"));
        let wat = craft_anything_testkit::wasm_plugin::echo_plugin_wat(false);
        let newer_patch = WasmPlugin::from_bytes(wat.replace("tools@0.1.0", "tools@0.1.7").as_bytes()).unwrap();
        assert_eq!(newer_patch.interfaces(), ["craft-anything:plugin/tools@0.1.7"]);
        assert_eq!(newer_patch.call("echo", &json!(1)).unwrap(), json!(1));
        let Err(e) = WasmPlugin::from_bytes(wat.replace("tools@0.1.0", "tools@0.2.0").as_bytes()) else { panic!("a 0.2 plugin loaded") };
        assert!(e.message.contains("0.2.0") && e.message.contains(API_VERSION), "{}", e.message);
    }

    #[test]
    fn the_host_and_the_wit_agree_on_the_version() {
        assert!(WIT.contains(&format!("package craft-anything:plugin@{API_VERSION};")));
        assert_eq!(INTERFACE, format!("{TOOLS_BASE}@{API_VERSION}"));
        assert_eq!(CHECKS_INTERFACE, format!("{CHECKS_BASE}@{API_VERSION}"));
    }
}
