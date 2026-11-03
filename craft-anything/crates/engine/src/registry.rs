//! The tool registry.

use crate::tool::{Effects, Requires, ToolFn, ToolSpec, Toolset};
use serde_json::{Value, json};
use std::collections::BTreeMap;

/// The first word of a tool id (docs/tool-ids.md).
pub const AREAS: &[&str] = &[
    "core", "native", "managed", "java", "android", "apple", "harmony", "js", "web", "app", "firmware", "formats", "radio", "packets", "db", "assets", "game",
    "project", "rebuild", "build", "runtime", "adb", "frida", "engines", "settings", "plugins", "setup",
];

/// A tool defined at run time rather than in code: a plugin's, or one proxied from an external
/// MCP server. Its names are owned and its input schema is plain JSON; `run` can serve many such
/// tools, telling them apart by [`crate::Ctx::tool`]. Registering one keeps its strings for the
/// rest of the process (they're registered once, at startup).
#[derive(Clone)]
pub struct RuntimeTool {
    pub id: String,
    pub title: String,
    pub summary: String,
    pub beginner: String,
    pub toolset: Toolset,
    pub effects: Effects,
    pub requires: Requires,
    pub schema: Value,
    pub run: ToolFn,
}

impl RuntimeTool {
    /// Ids (and custom toolset ids) are lower-case letters, digits and `_`, 1-64 characters.
    pub fn valid_id(id: &str) -> bool {
        (1..=64).contains(&id.len()) && id.chars().all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_')
    }
}

/// A run-time group's id kept for the process, once per distinct id.
pub fn custom_toolset(id: &str) -> Option<Toolset> {
    use craft_anything_platform::sync::Mutex;
    use std::sync::{OnceLock, PoisonError};
    static SEEN: OnceLock<Mutex<Vec<&'static str>>> = OnceLock::new();
    if let Some(t) = Toolset::from_id(id) {
        return Some(t);
    }
    if !RuntimeTool::valid_id(id) {
        return None;
    }
    let mut seen = SEEN.get_or_init(Mutex::default).lock().unwrap_or_else(PoisonError::into_inner);
    let kept = match seen.iter().find(|s| **s == id) {
        Some(s) => *s,
        None => {
            let s: &'static str = Box::leak(id.to_string().into_boxed_str());
            seen.push(s);
            s
        }
    };
    Some(Toolset::Custom(kept))
}

#[derive(Debug, Clone)]
pub struct Registry {
    specs: Vec<ToolSpec>,
    index: BTreeMap<&'static str, usize>,
    /// Input schemas of tools defined at run time.
    schemas: BTreeMap<&'static str, Value>,
}

impl Registry {
    pub fn new(specs: Vec<ToolSpec>) -> Self {
        let mut index = BTreeMap::new();
        let mut kept = Vec::with_capacity(specs.len());
        for s in specs {
            if index.contains_key(s.id) {
                log::error!("duplicate tool id {} ignored", s.id);
                continue;
            }
            index.insert(s.id, kept.len());
            kept.push(s);
        }
        Registry { specs: kept, index, schemas: BTreeMap::new() }
    }

    pub fn with_all_tools() -> Self {
        Registry::new(crate::tools::all())
    }

    /// Add tools defined at run time. One with an invalid id, a custom toolset with an invalid
    /// id, a schema that isn't an object, or an id already taken is skipped (and logged).
    pub fn with_runtime(mut self, tools: Vec<RuntimeTool>) -> Self {
        for t in tools {
            let set_ok = !matches!(t.toolset, Toolset::Custom(id) if !RuntimeTool::valid_id(id));
            if !RuntimeTool::valid_id(&t.id) || !set_ok || !t.schema.is_object() || self.index.contains_key(t.id.as_str()) {
                log::error!("run-time tool {:?} skipped (invalid or duplicate)", t.id);
                continue;
            }
            let leak = |s: String| -> &'static str { Box::leak(s.into_boxed_str()) };
            let spec = ToolSpec {
                id: leak(t.id),
                title: leak(t.title),
                summary: leak(t.summary),
                beginner: leak(t.beginner),
                toolset: t.toolset,
                effects: t.effects,
                requires: t.requires,
                input_schema: crate::tool::empty_schema,
                run: t.run,
            };
            self.schemas.insert(spec.id, t.schema);
            self.index.insert(spec.id, self.specs.len());
            self.specs.push(spec);
        }
        self
    }

    /// A tool's input schema (its own type's, or the JSON a run-time tool brought).
    pub fn input_schema(&self, spec: &ToolSpec) -> Value {
        self.schemas.get(spec.id).cloned().unwrap_or_else(|| (spec.input_schema)())
    }

    /// Every group in use: the built-in ones, then those added at run time.
    pub fn toolsets(&self) -> Vec<Toolset> {
        let mut out = Toolset::ALL.to_vec();
        for s in &self.specs {
            if !out.contains(&s.toolset) {
                out.push(s.toolset);
            }
        }
        out
    }

    /// A group by id, built-in or added at run time.
    pub fn toolset(&self, id: &str) -> Option<Toolset> {
        self.toolsets().into_iter().find(|t| t.id() == id)
    }

    /// The tool's own id for any name a client may use: its id, its CLI name (kebab-case), or
    /// either as an MCP client reports it (`mcp__<server>__<name>`). Code that decides
    /// on which tool ran compares this, never the raw name.
    pub fn canonical(&self, name: &str) -> Option<&'static str> {
        let bare = name.strip_prefix("mcp__").and_then(|rest| rest.split_once("__").map(|(_, tool)| tool)).unwrap_or(name);
        self.get(bare).map(|s| s.id)
    }

    /// A tool by its id or its CLI name (kebab-case).
    pub fn get(&self, id: &str) -> Option<&ToolSpec> {
        self.index.get(id.replace('-', "_").as_str()).and_then(|i| self.specs.get(*i))
    }

    pub fn all(&self) -> &[ToolSpec] {
        &self.specs
    }

    pub fn in_toolset(&self, t: Toolset) -> impl Iterator<Item = &ToolSpec> {
        self.specs.iter().filter(move |s| s.toolset == t)
    }

    pub fn len(&self) -> usize {
        self.specs.len()
    }

    pub fn is_empty(&self) -> bool {
        self.specs.is_empty()
    }

    /// The MCP `tools/list` entry for one tool.
    pub fn mcp_descriptor(&self, spec: &ToolSpec) -> Value {
        json!({
            "name": spec.id,
            "title": spec.title,
            "description": spec.summary,
            "inputSchema": self.input_schema(spec),
            "annotations": {
                "title": spec.title,
                "readOnlyHint": spec.effects.read_only_hint(),
                "destructiveHint": spec.effects.destructive_hint(),
                "idempotentHint": spec.effects.contains(crate::Effects::IDEMPOTENT),
                "openWorldHint": spec.effects.open_world_hint(),
            },
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_tool_is_well_formed() {
        let r = Registry::with_all_tools();
        assert!(!r.is_empty());
        for s in r.all() {
            assert!(s.id.chars().all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_'), "{}", s.id);
            assert!(!s.title.is_empty() && !s.summary.is_empty() && !s.beginner.is_empty(), "{}", s.id);
            let schema = r.input_schema(s);
            assert!(schema.is_object(), "{} schema", s.id);
            assert!(r.get(&s.cli_name()).is_some());
        }
    }

    #[test]
    fn every_mcp_input_property_has_an_object_schema() {
        let r = Registry::with_all_tools();
        for spec in r.all() {
            let schema = &r.mcp_descriptor(spec)["inputSchema"];
            for (property, value) in schema["properties"].as_object().into_iter().flatten() {
                assert!(value.is_object(), "{}.{property} schema must be an object, got {value}", spec.id);
            }
        }
    }

    #[test]
    fn any_name_a_client_uses_resolves_to_the_tool_id() {
        let r = Registry::with_all_tools();
        assert_eq!(r.canonical("core_session_show"), Some("core_session_show"));
        assert_eq!(r.canonical("core-session-show"), Some("core_session_show"));
        assert_eq!(r.canonical("mcp__craft-anything__core_session_show"), Some("core_session_show"));
        assert_eq!(r.canonical("mcp__other__nope"), None);
        assert_eq!(r.canonical("Read"), None, "an agent's own tool isn't ours");
    }

    /// Every tool's id is `<area>_<object…>_<action>` (or `<area>_<action>` where the area is the
    /// object, like `project_list`).
    #[test]
    fn every_tool_id_follows_the_scheme() {
        let bad: Vec<&str> = Registry::with_all_tools()
            .all()
            .iter()
            .map(|s| s.id)
            .filter(|id| {
                let mut words = id.split('_');
                !(words.next().is_some_and(|a| AREAS.contains(&a)) && words.count() >= 1)
            })
            .collect();
        assert!(bad.is_empty(), "ids outside the scheme (docs/tool-ids.md): {bad:?}");
    }
}
