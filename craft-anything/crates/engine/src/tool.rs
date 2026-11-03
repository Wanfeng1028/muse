//! Tool specs: the single contract the UI, CLI, MCP server and built-in agent all dispatch through.

use crate::session::Session;
use bitflags::bitflags;
use craft_anything_evidence::{Evidence, ToolError};
use serde::de::DeserializeOwned;
use serde::{Deserialize, Serialize};
use serde_json::Value;

bitflags! {
    /// Side effects of a tool. Every tool declares them; MCP hints and consent are derived from them.
    #[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
    pub struct Effects: u16 {
        /// Records evidence or changes session state (almost every analysis tool).
        const MUTATES_SESSION = 1 << 0;
        /// Changes the target or its annotations (rename, comment).
        const MUTATES_TARGET = 1 << 1;
        const WRITES_FILESYSTEM = 1 << 2;
        const LAUNCHES_PROCESS = 1 << 3;
        const ACCESSES_NETWORK = 1 << 4;
        const CHANGES_UI_STATE = 1 << 5;
        const MAY_DISCARD_DATA = 1 << 6;
        /// Runs code from the target or a script (process capture, Frida, walkthroughs). Needs consent.
        const EXECUTES_FOREIGN_CODE = 1 << 7;
        /// Changes a connected device (install, push, start). Needs consent.
        const MUTATES_DEVICE = 1 << 8;
        const IDEMPOTENT = 1 << 9;
        /// Its result carries content taken from the target (decompiled text, strings, bytes,
        /// rows, plist values): clients are told to treat it as untrusted data.
        const CARRIES_TARGET_CONTENT = 1 << 10;
    }
}

impl Effects {
    /// Plain evidence-producing analysis.
    pub const EVIDENCE: Effects = Effects::MUTATES_SESSION.union(Effects::IDEMPOTENT);
    /// Evidence that needs an engine process.
    pub const NATIVE_EVIDENCE: Effects = Effects::EVIDENCE.union(Effects::LAUNCHES_PROCESS);
    /// Evidence that talks to a browser or device over the network.
    pub const NETWORK_EVIDENCE: Effects = Effects::EVIDENCE.union(Effects::ACCESSES_NETWORK);
    /// Pure reads with no effect at all.
    pub const READ_ONLY: Effects = Effects::IDEMPOTENT;

    pub fn read_only_hint(self) -> bool {
        (self - Effects::IDEMPOTENT).is_empty()
    }

    pub fn destructive_hint(self) -> bool {
        self.intersects(Effects::MAY_DISCARD_DATA | Effects::EXECUTES_FOREIGN_CODE | Effects::MUTATES_DEVICE)
    }

    pub fn open_world_hint(self) -> bool {
        self.intersects(Effects::LAUNCHES_PROCESS | Effects::ACCESSES_NETWORK)
    }

    pub fn needs_consent(self) -> bool {
        self.intersects(Effects::EXECUTES_FOREIGN_CODE | Effects::MUTATES_DEVICE)
    }
}

/// Groups of tools. Agents see `Core` plus whatever toolsets they enable, which keeps their
/// context small. Every tool is always reachable from the CLI and UI. The built-in groups are
/// listed here; a plugin or a fork adds its own with [`Toolset::Custom`] (see
/// [`crate::registry::RuntimeTool`]), and [`crate::Registry::toolsets`] lists every group in use.
/// Serialized as its id.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub enum Toolset {
    /// Triage, open/close, overview, search, decompile, function dossier, views, evidence, unknowns.
    Core,
    /// Deep native: listings, navigation, annotations, xrefs, bytes, call graphs, value traces.
    Native,
    /// Mach-O, code signing, plists, Swift/ObjC, Interface Builder, asset catalogs, dyld.
    Apple,
    /// Target-free formats and diagnostics: Go, WASM, EVM, PE resources, ELF layout, crashes, firmware.
    Formats,
    /// .NET assemblies.
    Managed,
    /// APK, DEX, resources, Flutter, JEB.
    Android,
    /// Java `.class` files and JAR/WAR archives: constant pool, bytecode, pseudo-Java.
    Java,
    /// A phone or emulator over adb.
    Adb,
    /// Web pages through the browser debugging protocol.
    Browser,
    /// Electron apps, JavaScript bundles and the V8 inspector.
    Javascript,
    /// Running programs: process capture, native calls, native UI.
    Runtime,
    /// Frida instrumentation.
    Frida,
    /// Application graphs, comparisons and rebuild (reconstruction) ledgers.
    Application,
    /// Databases on disk: SQLite file inspection.
    Database,
    /// What the person is making: projects, their conversation and questions.
    Projects,
    /// Setting up this computer: engines and settings.
    Setup,
    /// A builder's own hands: reading, writing and building the project it works in.
    Build,
    /// A group added at run time (its id, lower-case letters, digits and `_`).
    Custom(&'static str),
}

impl Serialize for Toolset {
    fn serialize<S: serde::Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        s.serialize_str(self.id())
    }
}

impl Toolset {
    pub const ALL: [Toolset; 17] = [
        Toolset::Core,
        Toolset::Native,
        Toolset::Apple,
        Toolset::Formats,
        Toolset::Managed,
        Toolset::Android,
        Toolset::Java,
        Toolset::Adb,
        Toolset::Browser,
        Toolset::Javascript,
        Toolset::Runtime,
        Toolset::Frida,
        Toolset::Application,
        Toolset::Database,
        Toolset::Projects,
        Toolset::Setup,
        Toolset::Build,
    ];

    pub fn id(self) -> &'static str {
        match self {
            Toolset::Core => "core",
            Toolset::Native => "native",
            Toolset::Apple => "apple",
            Toolset::Formats => "formats",
            Toolset::Managed => "managed",
            Toolset::Android => "android",
            Toolset::Java => "java",
            Toolset::Adb => "adb",
            Toolset::Browser => "browser",
            Toolset::Javascript => "javascript",
            Toolset::Runtime => "runtime",
            Toolset::Frida => "frida",
            Toolset::Application => "application",
            Toolset::Database => "database",
            Toolset::Projects => "projects",
            Toolset::Setup => "setup",
            Toolset::Build => "build",
            Toolset::Custom(id) => id,
        }
    }

    /// A built-in group by id. Groups added at run time are found with [`crate::Registry::toolset`].
    pub fn from_id(s: &str) -> Option<Toolset> {
        Toolset::ALL.into_iter().find(|t| t.id() == s)
    }

    pub fn title(self) -> &'static str {
        match self {
            Toolset::Core => "Essentials",
            Toolset::Native => "Programs (native code)",
            Toolset::Apple => "Apple apps",
            Toolset::Formats => "File formats",
            Toolset::Managed => ".NET apps",
            Toolset::Android => "Android apps",
            Toolset::Java => "Java programs",
            Toolset::Adb => "Connected phone",
            Toolset::Browser => "Websites",
            Toolset::Javascript => "Electron and JavaScript",
            Toolset::Runtime => "Running programs",
            Toolset::Frida => "Frida instrumentation",
            Toolset::Application => "Comparing and rebuilding",
            Toolset::Database => "Databases",
            Toolset::Projects => "Projects",
            Toolset::Setup => "Engines and settings",
            Toolset::Build => "Building",
            Toolset::Custom(id) => id,
        }
    }
}

/// What a tool needs before it can run.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum Requires {
    #[default]
    Nothing,
    /// An open target.
    Target,
    /// The Deep (Ghidra) engine to be enabled and installed.
    Ghidra,
    /// An external tool, by engine id (`adb`, `jadx`, `chromium`, `frida`, …).
    Engine(&'static str),
    /// One of these hosts, by `std::env::consts::OS` name (`macos`, `windows`, `linux`).
    Os(&'static [&'static str]),
}

/// Who invoked a tool. Programmatic callers never get dialogs.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Caller {
    Ui,
    Cli,
    Mcp,
    Agent,
}

/// Cooperative cancellation, shared with long-running work (it lives in `platform`, so the
/// transports below the engine can take it too).
pub use craft_anything_platform::cancel::CancelToken;

/// Progress reports from a running tool.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Progress {
    /// 0..=1 when known.
    pub fraction: Option<f32>,
    pub message: String,
}

pub type ProgressFn = dyn Fn(Progress) + Send + Sync;

/// Everything a tool run can touch.
pub struct Ctx<'a> {
    /// The id of the tool being run (one function can serve several tools added at run time).
    pub tool: &'static str,
    pub session: &'a mut Session,
    pub cancel: CancelToken,
    pub progress: &'a ProgressFn,
    pub caller: Caller,
}

impl Ctx<'_> {
    pub fn report(&self, fraction: Option<f32>, message: impl Into<String>) {
        (self.progress)(Progress { fraction, message: message.into() });
    }
}

/// What a tool returns.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "kind", content = "value", rename_all = "snake_case")]
pub enum ToolOutput {
    /// An evidence record; the engine stores it in the session ledger.
    Evidence(Box<Evidence>),
    /// A lifecycle or status result that is not itself evidence.
    Value(Value),
}

impl ToolOutput {
    pub fn evidence(e: Evidence) -> Self {
        ToolOutput::Evidence(Box::new(e))
    }

    /// The JSON payload agents see.
    pub fn to_json(&self) -> Value {
        match self {
            ToolOutput::Evidence(e) => serde_json::to_value(e).unwrap_or(Value::Null),
            ToolOutput::Value(v) => serde_json::json!({ "result": v }),
        }
    }
}

pub type ToolFn = fn(&mut Ctx<'_>, Value) -> Result<ToolOutput, ToolError>;

/// A registered tool.
#[derive(Clone, Copy)]
pub struct ToolSpec {
    /// snake_case id; also the MCP tool name. The CLI uses the kebab-case form.
    pub id: &'static str,
    pub title: &'static str,
    /// One or two sentences for agents and experienced users.
    pub summary: &'static str,
    /// Plain-English description for Beginner mode.
    pub beginner: &'static str,
    pub toolset: Toolset,
    pub effects: Effects,
    pub requires: Requires,
    pub input_schema: fn() -> Value,
    pub run: ToolFn,
}

impl std::fmt::Debug for ToolSpec {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("ToolSpec").field("id", &self.id).field("toolset", &self.toolset).finish()
    }
}

impl ToolSpec {
    pub fn cli_name(&self) -> String {
        self.id.replace('_', "-")
    }
}

/// JSON Schema for a params type.
pub fn schema_of<T: schemars::JsonSchema>() -> Value {
    serde_json::to_value(schemars::schema_for!(T)).unwrap_or(Value::Null)
}

/// The schema of a tool that takes no params.
pub fn empty_schema() -> Value {
    serde_json::json!({"type": "object", "properties": {}, "additionalProperties": false})
}

/// Parse tool params; `null` is treated as `{}` so programmatic callers can omit them.
pub fn parse_params<T: DeserializeOwned>(v: Value) -> Result<T, ToolError> {
    let v = if v.is_null() { Value::Object(Default::default()) } else { v };
    serde_json::from_value(v).map_err(|e| ToolError::invalid(format!("invalid params: {e}")))
}
