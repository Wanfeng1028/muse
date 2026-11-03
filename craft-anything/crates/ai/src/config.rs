//! The `[ai]` table of `config.toml`: backends, roles, the fallback chain and price overrides.
//!
//! ```toml
//! [ai]
//! fallback_chain = ["Claude", "OpenRouter", "Local Llama"]
//!
//! [[ai.backends]]
//! name = "Claude"
//! kind = "anthropic"
//! model = "claude-opus-5-5"
//! effort = "high"
//!
//! [ai.roles]
//! lead = "Claude"
//! worker = "Local Llama"
//!
//! [ai.prices."my-model"]
//! input_per_mtok = 1.0
//! output_per_mtok = 2.0
//! ```

use crate::model::Effort;
use crate::{BackendConfig, BackendKind, Role};
use craft_anything_engine::Settings;
use craft_anything_evidence::{ErrorCode, ToolError};
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

/// Per-backend options beyond [`BackendConfig`].
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct BackendOptions {
    /// Thinking depth (`low`/`medium`/`high`/`xhigh`/`max`) for the Claude API and Claude Code;
    /// `high` unless set. A model without the level gets the nearest one below it.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub effort: Option<Effort>,
    /// Anthropic server-side fallbacks (default on).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub fallbacks_enabled: Option<bool>,
    /// Force the ReAct text protocol (models without tool calling).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub react_fallback: Option<bool>,
    /// Most model turns per user message.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub max_turns: Option<u32>,
    /// Agent CLIs: the program to run instead of the default for `model`.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub command: Option<String>,
    /// Agent CLIs: extra arguments placed before the prompt.
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub args: Vec<String>,
    /// Agent CLIs: the model to ask the CLI for (passed with its model flag when it has one).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub cli_model: Option<String>,
    /// Wall-clock limit in seconds for one agent CLI turn (default: 24 hours for a builder, which may
    /// analyse and build a big game; 30 minutes for questions).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub timeout_secs: Option<u64>,
    /// Agent CLIs that speak ACP (`cli_agents::acp::ACP_AGENTS`): chat over it, one agent process
    /// per conversation (off unless set).
    #[serde(skip_serializing_if = "Option::is_none")]
    pub acp: Option<bool>,
}

/// One configured backend.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct BackendEntry {
    #[serde(flatten)]
    pub config: BackendConfig,
    #[serde(flatten)]
    pub options: BackendOptions,
}

impl BackendEntry {
    /// An agent CLI's `model` names the agent (`opencode`), and the model it should use goes in
    /// `cli_model`. People also write the agent's program in `command` and the model in `model`
    /// (`command = "opencode"`, `model = "deepseek/deepseek-flash"`); that ran the plain adapter
    /// with the agent's own default model (#34). Read that way, it's the agent the command names,
    /// asked for that model.
    fn model_from_command(&mut self) {
        let known = crate::cli_agents::KNOWN;
        let model = self.config.model.trim();
        let names_an_agent = known.iter().any(|(id, prog, display)| model == *id || model == *prog || model.eq_ignore_ascii_case(display));
        if self.config.kind != BackendKind::AgentCli || model.is_empty() || names_an_agent {
            return;
        }
        // The file name without `.exe`, whichever system's separators the path uses.
        let program = self.options.command.as_deref().and_then(|c| c.trim().rsplit(['/', '\\']).next()).map(|f| f.strip_suffix(".exe").unwrap_or(f));
        let Some((id, _, _)) = program.and_then(|p| known.iter().find(|(_, prog, _)| prog.eq_ignore_ascii_case(p))) else { return };
        if self.options.cli_model.is_none() {
            self.options.cli_model = Some(model.to_string());
        }
        self.config.model = id.to_string();
    }
}

/// USD per million tokens.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct Price {
    pub input_per_mtok: f64,
    pub output_per_mtok: f64,
    /// Cache reads; defaults to 10% of input.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub cache_read_per_mtok: Option<f64>,
    /// Cache writes; defaults to 125% of input.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub cache_write_per_mtok: Option<f64>,
}

/// The whole AI configuration.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct AiConfig {
    pub backends: Vec<BackendEntry>,
    /// Role (`lead`, `worker`, `reviewer`, `builder`) → backend name.
    pub roles: BTreeMap<String, String>,
    /// Backends to try in order when one fails before answering.
    pub fallback_chain: Vec<String>,
    /// Price overrides by model id.
    pub prices: BTreeMap<String, Price>,
}

pub fn role_key(r: Role) -> &'static str {
    match r {
        Role::Lead => "lead",
        Role::Worker => "worker",
        Role::Reviewer => "reviewer",
        Role::Builder => "builder",
        Role::Extractor => "extractor",
    }
}

impl AiConfig {
    /// Parse `settings.ai`. A malformed table gives an error the UI can show (never a panic).
    pub fn from_table(t: &toml::Table) -> Result<AiConfig, ToolError> {
        let mut c: AiConfig = toml::Value::Table(t.clone()).try_into().map_err(|e: toml::de::Error| {
            ToolError::new(ErrorCode::BadSettings, format!("The [ai] settings couldn't be read: {e}"))
                .with_remediation("Fix or remove the [ai] section in config.toml.")
        })?;
        c.backends.iter_mut().for_each(BackendEntry::model_from_command);
        Ok(c)
    }

    /// Parse from settings; unreadable config is logged and treated as empty.
    pub fn from_settings(s: &Settings) -> AiConfig {
        AiConfig::from_table(&s.ai).unwrap_or_else(|e| {
            log::warn!("{}", e.message);
            AiConfig::default()
        })
    }

    pub fn to_table(&self) -> Result<toml::Table, ToolError> {
        toml::Table::try_from(self).map_err(|e| ToolError::internal(format!("saving AI settings: {e}")))
    }

    pub fn get(&self, name: &str) -> Option<&BackendEntry> {
        self.backends.iter().find(|b| b.config.name == name)
    }

    pub fn enabled(&self) -> impl Iterator<Item = &BackendEntry> {
        self.backends.iter().filter(|b| b.config.enabled)
    }

    /// Add or replace a backend by name.
    pub fn upsert(&mut self, e: BackendEntry) {
        match self.backends.iter_mut().find(|b| b.config.name == e.config.name) {
            Some(slot) => *slot = e,
            None => self.backends.push(e),
        }
    }

    pub fn remove(&mut self, name: &str) -> bool {
        let before = self.backends.len();
        self.backends.retain(|b| b.config.name != name);
        self.roles.retain(|_, v| v != name);
        self.fallback_chain.retain(|v| v != name);
        before != self.backends.len()
    }

    /// The backend for a role, with the plan's defaults: lead = first enabled backend; worker =
    /// a local model if present, else lead; reviewer and extractor = only when set; builder = an
    /// agent CLI if present, else lead.
    pub fn backend_for(&self, role: Role) -> Option<&BackendEntry> {
        if let Some(b) = self.roles.get(role_key(role)).and_then(|n| self.get(n)).filter(|b| b.config.enabled) {
            return Some(b);
        }
        let lead = || self.enabled().find(|b| b.config.kind != BackendKind::AgentCli).or_else(|| self.enabled().next());
        match role {
            Role::Lead => lead(),
            Role::Worker => self.enabled().find(|b| b.config.kind == BackendKind::OpenaiCompatible).or_else(lead),
            Role::Reviewer | Role::Extractor => None,
            Role::Builder => self.enabled().find(|b| b.config.kind == BackendKind::AgentCli).or_else(lead),
        }
    }

    /// The chain to try for a conversation started on `first`: `first`, then the configured
    /// fallback chain (skipping duplicates and disabled backends).
    pub fn chain_from(&self, first: &str) -> Vec<String> {
        let mut out = vec![first.to_string()];
        for n in &self.fallback_chain {
            if !out.contains(n) && self.get(n).is_some_and(|b| b.config.enabled) {
                out.push(n.clone());
            }
        }
        out
    }
}

#[cfg(test)]
mod tests {
    #[test]
    fn the_default_builder_is_the_same_from_the_list_as_from_the_config() {
        use crate::{BackendConfig, BackendKind, Role, default_builder};
        let b = |name: &str, kind, enabled| BackendConfig { name: name.into(), kind, model: String::new(), base_url: None, ssh_host: None, enabled };
        let cases: Vec<(Vec<BackendConfig>, Option<&str>)> = vec![
            (vec![], None),
            (vec![b("Key", BackendKind::Anthropic, true), b("Claude Code", BackendKind::AgentCli, true)], None),
            (vec![b("Key", BackendKind::Anthropic, true), b("Claude Code", BackendKind::AgentCli, false)], None),
            (vec![b("Key", BackendKind::Anthropic, true), b("Claude Code", BackendKind::AgentCli, true)], Some("Key")),
            (vec![b("Key", BackendKind::Anthropic, false), b("Claude Code", BackendKind::AgentCli, true)], Some("Key")),
            (vec![b("Local", BackendKind::OpenaiCompatible, true), b("Key", BackendKind::Anthropic, true)], None),
        ];
        for (list, chosen) in cases {
            let mut cfg = AiConfig::default();
            for c in &list {
                cfg.upsert(crate::BackendEntry { config: c.clone(), options: Default::default() });
            }
            if let Some(n) = chosen {
                cfg.roles.insert(role_key(Role::Builder).into(), n.into());
            }
            let from_cfg = cfg.backend_for(Role::Builder).map(|e| e.config.name.clone());
            assert_eq!(default_builder(&list, chosen).map(|c| c.name.clone()), from_cfg, "{list:?} {chosen:?}");
        }
    }

    use super::*;

    fn entry(name: &str, kind: BackendKind) -> BackendEntry {
        BackendEntry {
            config: BackendConfig { name: name.into(), kind, model: String::new(), base_url: None, ssh_host: None, enabled: true },
            options: BackendOptions::default(),
        }
    }

    #[test]
    fn round_trip_through_settings_toml() {
        let mut c = AiConfig::default();
        let mut a = entry("Claude", BackendKind::Anthropic);
        a.options.effort = Some(Effort::High);
        a.options.fallbacks_enabled = Some(false);
        c.upsert(a);
        c.upsert(entry("Local", BackendKind::OpenaiCompatible));
        c.roles.insert("reviewer".into(), "Local".into());
        c.fallback_chain = vec!["Local".into()];
        c.prices.insert("m".into(), Price { input_per_mtok: 1.0, output_per_mtok: 2.0, cache_read_per_mtok: None, cache_write_per_mtok: None });
        let mut s = Settings { ai: c.to_table().unwrap(), ..Default::default() };
        let text = toml::to_string_pretty(&s).unwrap();
        s = toml::from_str(&text).unwrap();
        let back = AiConfig::from_settings(&s);
        assert_eq!(back, c);
        assert!(text.contains("[[ai.backends]]"), "{text}");
        assert!(text.contains("effort = \"high\""), "{text}");
    }

    #[test]
    fn roles_and_chains() {
        let mut c = AiConfig::default();
        c.upsert(entry("Codex", BackendKind::AgentCli));
        c.upsert(entry("Claude", BackendKind::Anthropic));
        c.upsert(entry("Local", BackendKind::OpenaiCompatible));
        assert_eq!(c.backend_for(Role::Lead).unwrap().config.name, "Claude");
        assert_eq!(c.backend_for(Role::Worker).unwrap().config.name, "Local");
        assert_eq!(c.backend_for(Role::Builder).unwrap().config.name, "Codex");
        assert!(c.backend_for(Role::Reviewer).is_none());
        assert!(c.backend_for(Role::Extractor).is_none(), "the extractor only runs when chosen");
        c.roles.insert("lead".into(), "Local".into());
        assert_eq!(c.backend_for(Role::Lead).unwrap().config.name, "Local");
        c.fallback_chain = vec!["Claude".into(), "Local".into(), "Gone".into()];
        assert_eq!(c.chain_from("Local"), vec!["Local".to_string(), "Claude".to_string()]);
        assert!(c.remove("Local"));
        assert!(c.roles.is_empty());
        assert!(!c.remove("Local"));
    }

    #[test]
    fn malformed_table_is_an_error_not_a_panic() {
        let t: toml::Table = toml::from_str("backends = 3").unwrap();
        assert_eq!(AiConfig::from_table(&t).unwrap_err().code, ErrorCode::BadSettings);
        let s = Settings { ai: t, ..Default::default() };
        assert!(AiConfig::from_settings(&s).backends.is_empty());
    }

    /// #34: the agent's program in `command` and the model in `model` runs that agent with it.
    #[test]
    fn an_agent_named_by_its_command_gets_the_model() {
        let one = |toml: &str| {
            let t: toml::Table = toml::from_str(&format!("[[backends]]\nname = \"A\"\nkind = \"agent_cli\"\n{toml}")).unwrap();
            let b = AiConfig::from_table(&t).unwrap().backends.remove(0);
            (b.config.model, b.options.cli_model)
        };
        let reported = "model = \"deepseek/deepseek-flash\"\ncommand = \"opencode\"\nargs = [\"run\", \"--auto\"]";
        assert_eq!(one(reported), ("opencode".into(), Some("deepseek/deepseek-flash".into())));
        assert_eq!(one("model = \"sonnet\"\ncommand = 'C:\\Users\\u\\.bun\\bin\\opencode.exe'").0, "opencode", "a full path names it too");
        // Left as they are: a model that names the agent, a cli_model already set, an unknown program.
        assert_eq!(one("model = \"opencode\"\ncommand = \"opencode\""), ("opencode".into(), None));
        assert_eq!(one("model = \"gemini\"\ncommand = \"gemini\""), ("gemini".into(), None));
        assert_eq!(one("model = \"x/y\"\ncommand = \"opencode\"\ncli_model = \"z\""), ("opencode".into(), Some("z".into())));
        assert_eq!(one("model = \"my-agent\"\ncommand = \"my-agent-cli\""), ("my-agent".into(), None));
        assert_eq!(one("model = \"claude-code\""), ("claude-code".into(), None));
        // Maki named by its program runs Maki's own adapter, not `maki <prompt>` (its terminal interface).
        assert_eq!(one("model = \"anthropic/claude-sonnet-4-6\"\ncommand = \"maki\""), ("maki".into(), Some("anthropic/claude-sonnet-4-6".into())));
    }
}
