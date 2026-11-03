//! UI state. Plain serde data: everything the screens show is derived from this plus the engine.

use craft_anything_engine::TargetKind;
use craft_anything_engine::evidence::Evidence;
use craft_anything_engine::project::Purpose;
use craft_anything_engine::workspace::TargetRef;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::BTreeMap;
use std::path::PathBuf;

/// Simple-mode screens (Advanced mode is one workbench).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
pub enum Screen {
    #[default]
    Home,
    /// Questions about one opened target.
    Ask,
    /// One thing being made: progress, questions, checks, preview.
    Project,
    /// A game's archives, and saving its pictures.
    GameFiles,
    /// Advanced mode's workbench: every tool on the open target. Projects and their builds keep
    /// their own screens beside it, so nothing being built goes out of sight.
    Workbench,
}

/// What the person is about to make (the Home prompt).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct MakeDraft {
    pub target: TargetRef,
    /// The address being typed for a website target.
    pub url: String,
    pub request: String,
    /// The website field is open.
    pub editing_url: bool,
    /// Pictures of the original to match (copied into the project when it starts).
    #[serde(default)]
    pub pictures: Vec<PathBuf>,
    /// The engine the chosen game was made with (looked up when it's picked).
    #[serde(default)]
    pub found: Option<craft_anything_engines::game::Found>,
    /// The engine the person picked to build with (else the original's own, or Unity).
    #[serde(default)]
    pub builder: Option<craft_anything_engines::game::Builder>,
    /// The builder may generate pictures and 3D models for this game (saved with the project).
    #[serde(default)]
    pub generate_assets: bool,
    /// The person chose to build without Ghidra (Deep mode with the built-in decompiler) this time.
    #[serde(default)]
    pub skip_ghidra: bool,
    /// The front door is on "Just look inside" rather than "Make my own version".
    #[serde(default)]
    pub look: bool,
    /// The folder the person picked for the project (else a new one in the projects folder).
    #[serde(default)]
    pub folder: Option<PathBuf>,
    /// What's already in that folder: the first names and how many.
    #[serde(default)]
    pub folder_files: Option<(Vec<String>, usize)>,
    /// What those files are to the project.
    #[serde(default)]
    pub existing: Option<craft_anything_engine::workspace::ExistingFiles>,
    /// "Don't ask again" is ticked in the question about them.
    #[serde(default)]
    pub remember_existing: bool,
    /// The AI the person picked to build it ("Built by"); none: the default.
    #[serde(default)]
    pub ai: Option<String>,
    /// The original picked is a game ("A game"), not an app: decided by the tile, not by
    /// whether the path is a folder (an app can be a folder too).
    #[serde(default)]
    pub game: bool,
}

impl Default for MakeDraft {
    fn default() -> Self {
        MakeDraft {
            target: TargetRef::None,
            url: String::new(),
            request: String::new(),
            editing_url: false,
            pictures: Vec::new(),
            found: None,
            builder: None,
            generate_assets: false,
            skip_ghidra: false,
            look: false,
            folder: None,
            folder_files: None,
            existing: None,
            remember_existing: false,
            ai: None,
            game: false,
        }
    }
}

pub use craft_anything_ai::rebuild::feed::{FeedItem, PlanStatus, PlanStep};

/// The first-run steps. Never more than four.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
pub enum FirstRunStep {
    #[default]
    Welcome,
    Brain,
    Purpose,
    Done,
}

impl FirstRunStep {
    pub fn index(self) -> usize {
        match self {
            FirstRunStep::Welcome => 0,
            FirstRunStep::Brain => 1,
            FirstRunStep::Purpose => 2,
            FirstRunStep::Done => 3,
        }
    }
}

/// How the user answered a consent request.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ConsentAnswer {
    Once,
    AlwaysForProject,
    Deny,
}

/// One entry in the conversation.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum ChatItem {
    User(String),
    Assistant {
        text: String,
        backend: Option<String>,
        streaming: bool,
    },
    Status(String),
    Tool {
        call_id: String,
        tool: String,
        /// `None` while running.
        ok: Option<bool>,
        summary: String,
        evidence_id: Option<String>,
        /// The evidence record, once resolved from the session.
        evidence: Option<Box<Evidence>>,
    },
    /// A proof card on its own (no-AI mode, or shared from the workbench).
    Proof {
        intro: String,
        evidence: Box<Evidence>,
    },
    Consent {
        call_id: String,
        tool: String,
        title: String,
        explanation: String,
        answer: Option<ConsentAnswer>,
    },
    Error {
        message: String,
        remediation: Option<String>,
        /// A log with everything known about the failure, to open and inspect.
        #[serde(default, skip_serializing_if = "Option::is_none")]
        log: Option<std::path::PathBuf>,
    },
    /// "Add a brain" and similar calls to action.
    AddBrain,
}

/// Left-rail sections in Experienced mode.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Default, Serialize, Deserialize)]
pub enum RailKind {
    #[default]
    Targets,
    Functions,
    Strings,
    Imports,
    Sections,
    Classes,
    Modules,
    Resources,
}

impl RailKind {
    pub const ALL: [RailKind; 8] = [
        RailKind::Targets,
        RailKind::Functions,
        RailKind::Strings,
        RailKind::Imports,
        RailKind::Sections,
        RailKind::Classes,
        RailKind::Modules,
        RailKind::Resources,
    ];

    pub fn title(self) -> &'static str {
        match self {
            RailKind::Targets => "Targets",
            RailKind::Functions => "Functions",
            RailKind::Strings => "Strings",
            RailKind::Imports => "Imports / Exports",
            RailKind::Sections => "Sections",
            RailKind::Classes => "Classes",
            RailKind::Modules => "Modules",
            RailKind::Resources => "Resources",
        }
    }

    pub fn icon(self) -> &'static str {
        match self {
            RailKind::Targets => "layers",
            RailKind::Functions => "braces",
            RailKind::Strings => "file-code",
            RailKind::Imports => "link",
            RailKind::Sections => "list-tree",
            RailKind::Classes => "boxes",
            RailKind::Modules => "package",
            RailKind::Resources => "folder-open",
        }
    }

    /// Registry tools that can fill this list for a target of `kind`, best first. The first
    /// registered one is used.
    pub fn tools(self, kind: Option<TargetKind>) -> &'static [&'static str] {
        match self {
            RailKind::Targets => &[],
            RailKind::Functions => &["native_functions_list"],
            RailKind::Strings => &["native_strings_browse"],
            RailKind::Imports => &["native_named_addresses_list"],
            RailKind::Sections => &["native_sections_list"],
            RailKind::Classes => match kind {
                Some(TargetKind::Managed) => &["managed_members_list"],
                Some(TargetKind::Jar | TargetKind::JavaClass) => &["java_classes_find"],
                Some(TargetKind::Apk | TargetKind::Dex) => &["android_classes_find"],
                _ => &["apple_objc_classes_list"],
            },
            RailKind::Modules => &["js_app_map"],
            RailKind::Resources => &["native_pe_resources_list"],
        }
    }
}

/// Centre tabs in Experienced mode.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Default, Serialize, Deserialize)]
pub enum CenterTab {
    #[default]
    PseudoC,
    Disassembly,
    Hex,
    Graph,
    Source,
    Network,
    Result,
}

impl CenterTab {
    pub const ALL: [CenterTab; 7] =
        [CenterTab::PseudoC, CenterTab::Disassembly, CenterTab::Hex, CenterTab::Graph, CenterTab::Source, CenterTab::Network, CenterTab::Result];

    pub fn title(self) -> &'static str {
        match self {
            CenterTab::PseudoC => "Pseudo-C",
            CenterTab::Disassembly => "Disassembly",
            CenterTab::Hex => "Hex",
            CenterTab::Graph => "Graph",
            CenterTab::Source => "Source",
            CenterTab::Network => "Network",
            CenterTab::Result => "Result",
        }
    }

    pub fn icon(self) -> &'static str {
        match self {
            CenterTab::PseudoC => "code",
            CenterTab::Disassembly => "cpu",
            CenterTab::Hex => "binary",
            CenterTab::Graph => "workflow",
            CenterTab::Source => "file-code",
            CenterTab::Network => "network",
            CenterTab::Result => "clipboard-list",
        }
    }

    /// Tools that produce this view for the selected item, best first.
    pub fn tools(self) -> &'static [&'static str] {
        match self {
            CenterTab::PseudoC => &["native_function_pseudocode"],
            CenterTab::Disassembly => &["native_function_disassemble"],
            CenterTab::Hex => &["native_bytes_show"],
            CenterTab::Graph => &["native_call_graph_show"],
            CenterTab::Source => &["js_sources_restore"],
            CenterTab::Network => &["web_page_watch"],
            CenterTab::Result => &[],
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
pub enum RightTab {
    #[default]
    Inspector,
    Evidence,
    Unknowns,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
pub enum BottomTab {
    #[default]
    Agent,
    Jobs,
    Log,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize)]
pub enum SettingsTab {
    #[default]
    General,
    Engines,
    Ai,
    Builds,
    Plugins,
    Safety,
}

/// A list or view that a tool fills.
#[derive(Debug, Clone, PartialEq, Default, Serialize, Deserialize)]
pub enum Fill {
    /// Not asked for yet.
    #[default]
    Idle,
    Loading,
    /// No registered tool can produce it (yet).
    Unavailable(String),
    /// The tool exists but can't run now (reason, remediation).
    Blocked(String, Option<String>),
    /// The tool looks inside the original, which Clean room never does.
    DeepNeeded,
    Error(String, Option<String>),
    Ready(Box<Evidence>),
    /// A non-evidence tool result.
    Value(Value),
}

/// A friendly modal.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum Modal {
    ComingSoon {
        title: String,
        body: String,
        icon: String,
    },
    Website,
    Tutorial(usize),
    About,
    /// Getting a game engine (Unity, Unreal, Godot, Rust), step by step.
    Engine(craft_anything_engines::game::Builder),
    /// Asking for a fal.ai key when generated assets are turned on without one.
    Assets,
    /// Getting Ghidra for Deep mode.
    Ghidra,
    /// "Do you have permission?" before a game's files are unpacked.
    GamePermission,
    /// Clean room refused a look inside: turn on Deep mode?
    DeepMode,
    /// The folder picked for a new project has files: the app itself, or material to start from?
    ExistingFiles,
    /// Nothing can build yet: set something up (`start`: then start the project on Make).
    NeedBuilder {
        start: bool,
    },
    /// A new name for the project in this folder.
    Rename(PathBuf),
    /// Delete the project in this folder? (Asked, since it can't be undone.)
    Delete(PathBuf),
    /// Pin the open project's build: frozen or light (`UiState::pin_draft`).
    Pin,
    /// A new name for a pin (project folder, pin id).
    PinRename(PathBuf, u32),
    /// Remove a pin? (Its copy can't be brought back.)
    PinDelete(PathBuf, u32),
}

/// The command palette.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct PaletteState {
    pub open: bool,
    pub query: String,
    pub selected: usize,
    /// The tool whose params form is open.
    pub form_tool: Option<String>,
    pub form: BTreeMap<String, String>,
    pub form_error: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct UiState {
    pub screen: Screen,
    pub first_run: FirstRunStep,
    pub purpose: Purpose,
    /// Chosen AI backend name; `None` = no AI.
    pub backend: Option<String>,
    pub explain_new: bool,
    pub chat: Vec<ChatItem>,
    pub input: String,
    pub rail: RailKind,
    pub rail_filter: String,
    pub lists: BTreeMap<RailKind, Fill>,
    pub center: CenterTab,
    pub views: BTreeMap<CenterTab, Fill>,
    pub right: RightTab,
    pub bottom: BottomTab,
    pub bottom_open: bool,
    /// The row picked in a rail list (JSON of the row).
    pub selection: Option<Value>,
    pub selected_evidence: Option<String>,
    pub palette: PaletteState,
    pub settings_open: bool,
    pub settings_tab: SettingsTab,
    pub modal: Option<Modal>,
    pub url_input: String,
    /// One-line message at the bottom of the window (errors and confirmations).
    /// Newest last: (text, is an error). Confirmations go after a few seconds; errors stay until
    /// dismissed, so a later message never hides one.
    pub toasts: Vec<(String, bool)>,
    pub make: MakeDraft,
    /// The open project's activity.
    pub feed: Vec<FeedItem>,
    /// The follow-up box on the project screen.
    pub project_input: String,
    /// Pictures attached to the next follow-up message.
    #[serde(default)]
    pub project_attachments: Vec<PathBuf>,
    /// The person folded the sidebar to icons (it also folds by itself in a narrow window).
    #[serde(default)]
    pub sidebar_folded: bool,
    /// The sidebar's Pinned section is folded away.
    #[serde(default)]
    pub pins_collapsed: bool,
    /// The project's prompt box asks questions about the build instead of asking for changes.
    #[serde(default)]
    pub just_ask: bool,
    /// What the Pin dialog is choosing.
    #[serde(skip)]
    pub pin_draft: crate::pins::PinDraft,
    /// The name being typed in the Rename dialog.
    #[serde(default)]
    pub rename_input: String,
    /// What was typed (and attached) in other projects' boxes and not sent yet, by project folder:
    /// each project keeps its own until it's opened again.
    #[serde(default)]
    pub unsent: BTreeMap<PathBuf, (String, Vec<PathBuf>)>,
    /// Typed answers to open questions, by request id.
    pub answers: BTreeMap<String, String>,
    /// Settings → Plugins: the plugin being added.
    #[serde(default)]
    pub plugin_form: PluginForm,
    /// The Game files screen.
    #[serde(default)]
    pub game: GameFiles,
}

/// The Game files screen: a game's folder, its archives, the one open and its rows.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct GameFiles {
    pub folder: Option<PathBuf>,
    /// game_archives_list's rows.
    pub archives: Vec<Value>,
    pub looking: bool,
    /// The archive shown (its path) and its kind.
    pub open: Option<String>,
    pub open_kind: String,
    /// Its files (a pak) or objects (a Unity file).
    pub rows: Vec<Value>,
    pub loading: bool,
    pub filter: String,
    /// The game folder the person said they may unpack.
    pub permitted: Option<PathBuf>,
    /// The picture to save once a place is picked.
    pub pending: Option<PendingPicture>,
    /// What the game is made of (triage's result for its folder).
    #[serde(default)]
    pub profile: Option<Value>,
}

/// A picture waiting for where to be saved.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct PendingPicture {
    pub archive: String,
    pub kind: String,
    /// Its row (a pak file's `path`, a Unity object's `path_id`).
    pub item: Value,
    /// The file name to suggest.
    pub name: String,
}

/// What the person typed to add a plugin: an id, and a command or an https address.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct PluginForm {
    pub id: String,
    /// A command (a local server), an https:// address (a remote one) or a `.wasm` file.
    pub place: String,
    /// Arguments for a command, separated by spaces.
    pub args: String,
}

impl PluginForm {
    /// The plugins_add params, or None while it's incomplete.
    pub fn params(&self) -> Option<serde_json::Value> {
        let (id, place) = (self.id.trim(), self.place.trim());
        if id.is_empty() || place.is_empty() {
            return None;
        }
        Some(if place.starts_with("https://") || place.starts_with("http://") {
            serde_json::json!({"id": id, "url": place})
        } else if place.to_ascii_lowercase().ends_with(".wasm") {
            serde_json::json!({"id": id, "wasm": place})
        } else {
            serde_json::json!({"id": id, "command": place, "args": self.args.split_whitespace().collect::<Vec<_>>()})
        })
    }
}

impl Default for UiState {
    fn default() -> Self {
        UiState {
            screen: Screen::Home,
            first_run: FirstRunStep::Welcome,
            purpose: Purpose::OwnOrAuthorized,
            backend: None,
            explain_new: true,
            chat: Vec::new(),
            input: String::new(),
            rail: RailKind::Functions,
            rail_filter: String::new(),
            lists: BTreeMap::new(),
            center: CenterTab::PseudoC,
            views: BTreeMap::new(),
            right: RightTab::Inspector,
            bottom: BottomTab::Agent,
            bottom_open: true,
            selection: None,
            selected_evidence: None,
            palette: PaletteState::default(),
            settings_open: false,
            settings_tab: SettingsTab::General,
            modal: None,
            url_input: String::new(),
            toasts: Vec::new(),
            make: MakeDraft::default(),
            feed: Vec::new(),
            project_input: String::new(),
            project_attachments: Vec::new(),
            unsent: BTreeMap::new(),
            rename_input: String::new(),
            sidebar_folded: false,
            pins_collapsed: false,
            just_ask: false,
            pin_draft: Default::default(),
            answers: BTreeMap::new(),
            plugin_form: PluginForm::default(),
            game: GameFiles::default(),
        }
    }
}

/// Plain-words purposes for the first-run picker.
pub fn purposes() -> [(Purpose, &'static str, &'static str); 5] {
    [
        (Purpose::OwnOrAuthorized, "It's mine, or I'm allowed to look", "Software I made, bought, or have permission to examine."),
        (Purpose::Education, "I'm learning how things work", "Studying software to understand it."),
        (Purpose::Interoperability, "I want to make things work together", "Making my own thing talk to something else."),
        (Purpose::Security, "I'm checking whether it's safe", "Security research on software I'm allowed to examine."),
        (Purpose::Preservation, "I'm keeping old software alive", "Preserving software that's no longer supported."),
    ]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_plugin_form_turns_into_plugins_add_params() {
        let f = |id: &str, place: &str, args: &str| PluginForm { id: id.into(), place: place.into(), args: args.into() }.params();
        assert_eq!(f("docs", " https://mcp.example.com/mcp ", "ignored"), Some(serde_json::json!({"id": "docs", "url": "https://mcp.example.com/mcp"})));
        assert_eq!(f("fs", "npx", "-y  @scope/server  /tmp"), Some(serde_json::json!({"id": "fs", "command": "npx", "args": ["-y", "@scope/server", "/tmp"]})));
        assert_eq!(f("words", r"C:\plugins\Words.WASM", "ignored"), Some(serde_json::json!({"id": "words", "wasm": r"C:\plugins\Words.WASM"})));
        assert_eq!(f("", "npx", ""), None);
        assert_eq!(f("x", "  ", ""), None);
    }

    #[test]
    fn ui_state_round_trips_as_json() {
        let mut s = UiState::default();
        s.chat.push(ChatItem::User("hi".into()));
        s.chat.push(ChatItem::Consent {
            call_id: "1".into(),
            tool: "run".into(),
            title: "Run".into(),
            explanation: "x".into(),
            answer: Some(ConsentAnswer::Once),
        });
        s.lists.insert(RailKind::Strings, Fill::Unavailable("not yet".into()));
        let j = serde_json::to_string(&s).unwrap();
        let back: UiState = serde_json::from_str(&j).unwrap();
        assert_eq!(back, s);
    }
}
