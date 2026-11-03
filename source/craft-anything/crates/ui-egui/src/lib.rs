//! The Craft Anything egui interface: Simple mode (make something from a prompt, or ask about a
//! target) and Advanced mode (the full workbench). Both drive the same engine.
//!
//! Threading: the UI thread never waits. Engine tools, AI detection, file dialogs and file writes
//! run on worker threads ([`jobs`]) and come back through a channel that is drained once per
//! frame. The session lock is only ever taken with `Engine::try_session` from here, so a long tool
//! holding it never freezes a frame; the last snapshot ([`SessionView`]) is shown meanwhile.
#![deny(clippy::unwrap_used, clippy::expect_used, clippy::panic, clippy::unimplemented, clippy::todo, clippy::unreachable)]

pub mod builders;
pub mod chat;
pub mod demo;
pub mod engine_ui;
pub mod evidence_ui;
pub mod first_run;
pub mod folders;
pub mod game_files;
pub mod glossary;
pub mod home;
pub mod i18n;
mod icon_data;
pub mod icons;
pub mod jobs;
pub mod just_ask;
pub mod make;
pub mod manage;
pub mod palette;
pub mod pins;
pub mod project;
pub mod prompt_box;
pub mod report;
pub mod schema_form;
pub mod settings_ui;
pub mod sidebar;
pub mod slash;
pub mod state;
pub mod theme;
pub mod titlebar;
pub mod usage;
pub mod widgets;
pub mod workbench;

use craft_anything_ai::{AgentEvent, AiHub, BackendConfig, Conversation, Detected};
use craft_anything_engine::evidence::{ErrorCode, Evidence, ToolError, Unknown};
use craft_anything_engine::{CallOptions, Caller, Consent, Engine, Mode, Settings, TargetKind, ToolOutput, clean_room};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use state::{CenterTab, ChatItem, ConsentAnswer, Fill, RailKind, Screen, UiState};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::{Duration, Instant};
use theme::ThemeKind;

pub use i18n::tr;

/// Every icon name the UI uses (checked against the embedded set by a test).
pub const USED_ICONS: &[&str] = &[
    "activity",
    "app-window",
    "binary",
    "book-open",
    "bot",
    "boxes",
    "braces",
    "check",
    "chevron-down",
    "chevron-right",
    "circle-help",
    "circle-stop",
    "clipboard-list",
    "code",
    "copy",
    "cpu",
    "database",
    "download",
    "external-link",
    "file",
    "file-code",
    "fingerprint",
    "flask-conical",
    "folder",
    "folder-open",
    "gauge",
    "globe",
    "graduation-cap",
    "hammer",
    "history",
    "house",
    "info",
    "key-round",
    "layers",
    "link",
    "list-tree",
    "lock",
    "message-square",
    "microscope",
    "network",
    "package",
    "play",
    "plus",
    "puzzle",
    "radar",
    "refresh-cw",
    "rocket",
    "scan-search",
    "search",
    "send",
    "server",
    "settings",
    "shield",
    "shield-check",
    "smartphone",
    "sparkles",
    "terminal",
    "trash-2",
    "triangle-alert",
    "upload",
    "user",
    "wand-sparkles",
    "workflow",
    "wrench",
    "x",
    "zap",
];

/// Where a tool result goes.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum Route {
    /// Into the conversation as a proof card. `cta` adds an "add a brain" card after it.
    Chat {
        intro: String,
        cta: bool,
    },
    Rail(RailKind),
    View(CenterTab),
    /// From the command palette: the Result tab.
    Palette,
    Silent,
}

/// What a worker hands back to the UI thread.
pub enum Done {
    Tool {
        tool: String,
        params: Value,
        route: Route,
        result: Result<ToolOutput, ToolError>,
    },
    Opened {
        path: PathBuf,
        result: Result<Value, ToolError>,
    },
    Detected(Vec<Detected>),
    /// The configured backends, the ones chosen to build with and to extract with, and each one's
    /// options.
    Backends(Vec<BackendConfig>, Option<String>, Option<String>, std::collections::BTreeMap<String, craft_anything_ai::BackendOptions>),
    /// The models an AI can be set to (Settings → AI's model picker).
    ModelChoices {
        name: String,
        result: Result<Vec<String>, ToolError>,
    },
    Picked {
        pick: Pick,
        path: Option<PathBuf>,
    },
    /// Pictures of the original were chosen (empty when the dialog was cancelled).
    Pictures(Vec<PathBuf>),
    /// Pictures for the next message were chosen.
    ToAttach(Vec<PathBuf>),
    /// The game engines on this computer were listed.
    GameEngines(craft_anything_engines::game::Inventory),
    /// What engine made the game at `path`.
    GameFound {
        path: PathBuf,
        found: Option<craft_anything_engines::game::Found>,
    },
    /// An engine download finished: ready, or its vendor installer was opened.
    EngineGot {
        builder: craft_anything_engines::game::Builder,
        installer: bool,
    },
    /// Ghidra and its Java were downloaded and set up for Deep mode.
    GhidraGot,
    /// A tool started by a button finished (see `CraftApp::act`).
    Acted {
        tool: &'static str,
        result: Result<Value, ToolError>,
    },
    /// Which asset providers have a key set up (provider id → stored).
    AssetKeys(std::collections::BTreeMap<String, bool>),
    Wrote {
        what: String,
        path: Option<PathBuf>,
    },
    BackendAdded {
        name: String,
        result: Result<(), ToolError>,
    },
    /// The projects folder was listed.
    Projects(Vec<craft_anything_engine::workspace::Workspace>),
    /// A new project's folder was made (see `CraftApp::start_make`).
    Created {
        ws: Box<craft_anything_engine::workspace::Workspace>,
        request: String,
        backend: String,
        /// Why the pictures couldn't be copied, if they couldn't.
        pictures: Option<String>,
    },
    /// A message's pictures were copied into its project (see `CraftApp::deliver`).
    Attached {
        root: PathBuf,
        text: String,
        attachments: Vec<PathBuf>,
        files: Result<Vec<PathBuf>, String>,
    },
    /// Pictures of the original were copied into the open project (how many were).
    PicturesAdded(Result<usize, String>),
    /// The open project's files were read for the Project screen.
    Facts(project::Facts),
    /// A screenshot thumbnail was decoded (`None` when it couldn't be).
    Thumb {
        path: PathBuf,
        image: Option<egui::TextureHandle>,
    },
    Nothing,
}

/// An AI server added by its address (Settings → AI): another computer's Ollama or LM Studio, or a
/// service that speaks the OpenAI API.
#[derive(Debug, Clone, Default)]
pub struct ServerForm {
    pub name: String,
    pub address: String,
    /// Empty: the first model it lists that can chat.
    pub model: String,
    pub key: String,
}

/// What a file dialog was for.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Pick {
    OpenFile,
    OpenFolder,
    GhidraDir,
    /// The app, game or file to rebuild.
    TargetFile,
    TargetFolder,
    ProjectsDir,
    /// The folder a new project starts in (it may already have the person's files).
    ProjectFolder,
    /// Another folder whose projects are listed (Settings).
    ExtraProjectsDir,
    /// Pictures of the original to match (several at once).
    Pictures,
    /// Pictures for the next message on a project (several at once).
    Attach,
    /// The game folder for Game files.
    GameFolder,
    /// Where to save a picture from a game.
    SavePicture,
    /// The program an agent app runs ([`CraftApp::picking_program_for`] says which).
    AgentProgram,
}

/// One open target, as the UI shows it.
#[derive(Debug, Clone)]
pub struct TargetInfo {
    pub id: String,
    pub name: String,
    pub kind: TargetKind,
    pub path: PathBuf,
    pub sha256: String,
    pub bytes: Arc<[u8]>,
}

/// The last snapshot of the session, refreshed whenever the lock is free and something changed.
#[derive(Debug, Clone, Default)]
pub struct SessionView {
    pub targets: Vec<TargetInfo>,
    pub active: Option<String>,
    pub clean_room: bool,
    /// Newest first, capped.
    pub ledger: Vec<Evidence>,
    pub ledger_len: usize,
    pub unknowns: Vec<Unknown>,
    pub project: Option<String>,
    pub project_allows: Vec<String>,
}

impl SessionView {
    pub fn active_target(&self) -> Option<&TargetInfo> {
        self.active.as_ref().and_then(|id| self.targets.iter().find(|t| &t.id == id))
    }
}

/// One line in the Log panel.
#[derive(Debug, Clone)]
pub struct LogLine {
    pub at: Instant,
    pub error: bool,
    pub text: String,
}

/// UI preferences remembered between launches (through eframe's storage).
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(default)]
pub struct Prefs {
    pub purpose: craft_anything_engine::project::Purpose,
    pub backend: Option<String>,
    pub explain_new: Option<bool>,
    pub rail: Option<RailKind>,
    pub center: Option<CenterTab>,
    pub bottom_open: Option<bool>,
    /// The sidebar was folded to icons.
    #[serde(default)]
    pub sidebar_folded: bool,
    /// The sidebar's Pinned section was folded away.
    #[serde(default)]
    pub pins_collapsed: bool,
    /// The project that was open, reopened on the next start.
    #[serde(default)]
    pub last_project: Option<PathBuf>,
    /// What was typed on Make and not started yet.
    #[serde(default)]
    pub make: Option<state::MakeDraft>,
    /// What was typed in each project's box and not sent yet, by project folder.
    #[serde(default)]
    pub unsent: std::collections::BTreeMap<PathBuf, String>,
}

pub const PREFS_KEY: &str = "craft-anything-ui";
const LEDGER_VIEW_CAP: usize = 300;

pub struct CraftApp {
    pub engine: Arc<Engine>,
    pub hub: Arc<AiHub>,
    pub state: UiState,
    /// The UI's copy of the settings; pushed into the session (and saved) when changed.
    pub settings: Settings,
    /// Write settings to disk (off in tests and snapshots).
    pub persist: bool,
    /// Never open native dialogs (tests and snapshots).
    pub headless: bool,
    pub view: SessionView,
    pub jobs: jobs::Jobs<Done>,
    pub conversation: Option<Box<dyn Conversation>>,
    pub backends: Vec<BackendConfig>,
    /// Each backend's options (an agent app's program and model), by name (Settings → AI).
    pub backend_options: std::collections::BTreeMap<String, craft_anything_ai::BackendOptions>,
    /// The AI whose model is being chosen in Settings → AI, and the models it offers once they've
    /// come (`None`: still asking).
    pub model_picker: Option<(String, Option<Vec<String>>)>,
    /// The agent app whose program the file dialog is choosing.
    pub picking_program_for: Option<String>,
    /// The backend the person chose to build with (Settings → AI), if any.
    pub builder: Option<String>,
    /// The backend chosen to take a game's files out in Deep mode, if any.
    pub extractor: Option<String>,
    pub detected: Option<Vec<Detected>>,
    pub detecting: bool,
    pub log: Vec<LogLine>,
    pub key_inputs: std::collections::BTreeMap<String, String>,
    /// Settings → AI's "Add an AI by its address" form. Not kept with the UI state: its key goes
    /// only to the keychain.
    pub server_form: ServerForm,
    /// Every project's rebuild in this window: working, waiting their turn, or finished.
    pub runs: craft_anything_ai::rebuild::RunSet,
    /// What was typed for each note still waiting for a builder, by note id, to put back in the
    /// prompt box when the note is taken back.
    pub drafts: std::collections::HashMap<u64, project::Draft>,
    /// Each project's building time and AI use, every build together (read from its usage.json).
    pub usage: std::collections::HashMap<PathBuf, usage::ProjectClock>,
    /// All AI use since the app opened: builds and chat.
    pub session_usage: craft_anything_engine::workspace::ProjectUsage,
    /// The project shown on the Project screen.
    pub workspace: Option<craft_anything_engine::workspace::Workspace>,
    /// Every project in the projects folder, newest first.
    pub projects: Vec<craft_anything_engine::workspace::Workspace>,
    /// A preview server for a project opened without a run.
    pub preview: Option<String>,
    /// Questions asked about each project's build this session, and their answers (`just_ask`).
    pub asked: std::collections::HashMap<PathBuf, Vec<just_ask::Asked>>,
    /// Every project's pinned builds, and whether they're running (read by `refresh_pins`).
    pub pins: Vec<pins::PinRow>,
    pub pins_read_at: Option<Instant>,
    /// An address to open in the browser on the next frame (set from a worker's result).
    open_url: Option<String>,
    /// The open project's screenshot thumbnails (dropped when another project opens).
    pub thumbs: std::collections::HashMap<PathBuf, project::Thumb>,
    /// The kinds of thing this app can make; a fork registers its own here.
    pub kinds: craft_anything_ai::rebuild::KindRegistry,
    /// Game engines on this computer (`None` until the first look finishes).
    pub game_engines: Option<craft_anything_engines::game::Inventory>,
    /// Which asset providers have a key set up, by provider id (`None` until checked; the keys
    /// themselves never come into the app).
    pub asset_keys: Option<std::collections::BTreeMap<String, bool>>,
    /// What the open project's files say (built result, pictures, assets, open questions), read
    /// on a worker.
    pub facts: project::Facts,
    facts_reader: project::FactsReader,
    /// Getting a game engine: downloads, installers opened, a project waiting to start.
    pub engine_flow: engine_ui::Flow,
    /// Getting Ghidra for Deep mode.
    pub ghidra: engine_ui::GhidraFlow,
    /// When each toast appeared, in the same order (confirmations hide after a few seconds).
    toast_at: Vec<Instant>,
    settings_dirty: bool,
    /// When to write the settings to disk: a moment after the last change, so typing a path
    /// saves once, not once per letter.
    save_due: Option<Instant>,
    /// The save being written (one at a time; a change meanwhile saves again after it).
    saving: Option<u64>,
    /// A new project being made (Start waits for it).
    pub creating: Option<u64>,
    /// Tools the UI started that wait for the person's consent, by the id on their card.
    pending_consent: std::collections::HashMap<u64, (String, Value, Route)>,
    next_consent: u64,
    /// Projects whose build is waiting for the person's answer (a question or approval).
    pub asking: std::collections::HashSet<PathBuf>,
    /// A build asked something since the last frame: the taskbar flashes if the window is behind.
    attention: bool,
    /// Jobs whose result goes into the conversation (a first look, an answer without an AI):
    /// what the Ask screen waits on and its Stop cancels.
    chat_jobs: Vec<u64>,
    view_dirty: bool,
    last_view: Option<Instant>,
    applied_theme: Option<(ThemeKind, bool)>,
    started: bool,
}

impl CraftApp {
    pub fn new(engine: Arc<Engine>, hub: Arc<AiHub>) -> Self {
        // Wait for the engine if it's busy: defaults here would show Clean room and no AI, and the
        // next settings change would save them over the person's own.
        let settings = engine.session().settings.clone();
        i18n::set_language(&settings.language);
        CraftApp {
            engine,
            hub,
            state: UiState::default(),
            settings,
            persist: true,
            headless: false,
            view: SessionView::default(),
            jobs: jobs::Jobs::default(),
            conversation: None,
            backends: Vec::new(),
            backend_options: Default::default(),
            model_picker: None,
            picking_program_for: None,
            builder: None,
            extractor: None,
            detected: None,
            detecting: false,
            log: Vec::new(),
            key_inputs: Default::default(),
            server_form: ServerForm::default(),
            runs: craft_anything_ai::rebuild::RunSet::new(craft_anything_engine::settings::BuildSettings::default().parallel),
            drafts: Default::default(),
            usage: Default::default(),
            session_usage: Default::default(),
            workspace: None,
            projects: Vec::new(),
            preview: None,
            pins: Vec::new(),
            asked: Default::default(),
            pins_read_at: None,
            open_url: None,
            thumbs: Default::default(),
            kinds: craft_anything_ai::rebuild::KindRegistry::built_in(),
            game_engines: None,
            asset_keys: None,
            facts: Default::default(),
            facts_reader: Default::default(),
            engine_flow: Default::default(),
            ghidra: Default::default(),
            toast_at: Vec::new(),
            settings_dirty: false,
            save_due: None,
            saving: None,
            creating: None,
            chat_jobs: Vec::new(),
            asking: Default::default(),
            pending_consent: Default::default(),
            next_consent: 1,
            attention: false,
            view_dirty: true,
            last_view: None,
            applied_theme: None,
            started: false,
        }
    }

    /// Fonts and image loaders; call once with the egui context.
    pub fn setup_context(ctx: &egui::Context) {
        theme::install_fonts(ctx);
        egui_extras::install_image_loaders(ctx);
    }

    /// Restore remembered preferences.
    pub fn load_prefs(&mut self, storage: Option<&dyn eframe::Storage>) {
        let Some(text) = storage.and_then(|s| s.get_string(PREFS_KEY)) else { return };
        let Ok(p) = serde_json::from_str::<Prefs>(&text) else { return };
        self.state.purpose = p.purpose;
        self.state.backend = p.backend;
        if let Some(v) = p.explain_new {
            self.state.explain_new = v;
        }
        if let Some(v) = p.rail {
            self.state.rail = v;
        }
        if let Some(v) = p.center {
            self.state.center = v;
        }
        if let Some(v) = p.bottom_open {
            self.state.bottom_open = v;
        }
        self.state.sidebar_folded = p.sidebar_folded;
        self.state.pins_collapsed = p.pins_collapsed;
        // Typed drafts come back, so a restart doesn't lose them.
        if let Some(d) = p.make {
            self.state.make = d;
        }
        self.state.unsent = p.unsent.into_iter().map(|(root, text)| (root, (text, Vec::new()))).collect();
        // Back to the project that was open, with its conversation, if it's still there.
        if let Some(ws) = p.last_project.and_then(|root| craft_anything_engine::workspace::Workspace::open(&root).ok()) {
            self.open_workspace(ws);
        }
    }

    pub fn prefs(&self) -> Prefs {
        let mut unsent: std::collections::BTreeMap<PathBuf, String> =
            self.state.unsent.iter().filter(|(_, (t, _))| !t.trim().is_empty()).map(|(r, (t, _))| (r.clone(), t.clone())).collect();
        if let Some(ws) = &self.workspace
            && !self.state.project_input.trim().is_empty()
        {
            unsent.insert(ws.root.clone(), self.state.project_input.clone());
        }
        let m = &self.state.make;
        let make = (!m.request.trim().is_empty() || !m.url.trim().is_empty() || !m.pictures.is_empty()).then(|| m.clone());
        Prefs {
            make,
            unsent,
            sidebar_folded: self.state.sidebar_folded,
            pins_collapsed: self.state.pins_collapsed,
            purpose: self.state.purpose,
            backend: self.state.backend.clone(),
            explain_new: Some(self.state.explain_new),
            rail: Some(self.state.rail),
            center: Some(self.state.center),
            bottom_open: Some(self.state.bottom_open),
            last_project: (self.state.screen == Screen::Project).then(|| self.workspace.as_ref().map(|w| w.root.clone())).flatten(),
        }
    }

    pub fn mode(&self) -> Mode {
        self.settings.mode
    }

    pub fn beginner(&self) -> bool {
        self.settings.mode == Mode::Beginner
    }

    pub fn theme_kind(&self) -> ThemeKind {
        ThemeKind::from_id(&self.settings.theme)
    }

    pub fn log(&mut self, error: bool, text: impl Into<String>) {
        let text = text.into();
        if error {
            log::warn!("{text}");
        } else {
            log::info!("{text}");
        }
        self.log.push(LogLine { at: Instant::now(), error, text });
        if self.log.len() > 500 {
            self.log.drain(..100);
        }
    }

    pub fn toast(&mut self, text: impl Into<String>, error: bool) {
        const KEPT: usize = 4;
        let text = text.into();
        // The same message again moves to the front instead of stacking up.
        if let Some(i) = self.state.toasts.iter().position(|(t, _)| *t == text) {
            self.state.toasts.remove(i);
            if i < self.toast_at.len() {
                self.toast_at.remove(i);
            }
        }
        self.state.toasts.push((text, error));
        self.toast_at.push(Instant::now());
        // The oldest confirmations go first when there are too many; errors are kept longest.
        while self.state.toasts.len() > KEPT {
            let i = self.state.toasts.iter().position(|(_, e)| !e).unwrap_or(0);
            self.state.toasts.remove(i);
            if i < self.toast_at.len() {
                self.toast_at.remove(i);
            }
        }
    }

    pub fn has_tool(&self, id: &str) -> bool {
        self.engine.registry().get(id).is_some()
    }

    /// The first registered tool among `ids`.
    pub fn first_tool(&self, ids: &[&'static str]) -> Option<&'static str> {
        ids.iter().copied().find(|id| self.has_tool(id))
    }

    // ---- settings -------------------------------------------------------------------------------

    /// Mark settings changed: they are pushed into the session and saved on a worker.
    pub fn settings_changed(&mut self) {
        self.settings_dirty = true;
    }

    /// Changed settings go into the session at once, and to disk a moment after the last change.
    fn flush_settings(&mut self, ctx: &egui::Context) {
        const QUIET: Duration = Duration::from_millis(600);
        if self.settings_dirty
            && let Some(mut s) = self.engine.try_session()
        {
            // The Ghidra folder changed: look for it again.
            if s.settings.engines.ghidra.install_dir != self.settings.engines.ghidra.install_dir {
                self.ghidra.ready = None;
            }
            // The `ai` table belongs to the ai crate (it edits it in the session); keep its copy.
            self.settings.ai = s.settings.ai.clone();
            s.settings = self.settings.clone();
            drop(s);
            self.settings_dirty = false;
            self.view_dirty = true;
            if self.persist {
                self.save_due = Some(Instant::now() + QUIET);
            }
        }
        let Some(due) = self.save_due.filter(|_| self.saving.is_none()) else { return };
        let wait = due.saturating_duration_since(Instant::now());
        if !wait.is_zero() {
            ctx.request_repaint_after(wait);
            return;
        }
        self.save_due = None;
        let engine = self.engine.clone();
        // What's in the session when it runs, so the newest settings are the ones written.
        self.saving = Some(self.jobs.spawn("Save settings", false, move |_| {
            let settings = engine.session().settings.clone();
            settings.save().map_err(|e| e.message)?;
            Ok(Done::Nothing)
        }));
    }

    pub fn set_mode(&mut self, mode: Mode) {
        if self.settings.mode != mode {
            self.settings.mode = mode;
            self.settings_changed();
            if mode == Mode::Experienced {
                self.state.screen = Screen::Workbench;
                self.ensure_rail_loaded();
            } else if self.state.screen == Screen::Workbench {
                self.state.screen = Screen::Home;
            }
        }
    }

    pub fn set_deep(&mut self, on: bool) {
        if self.settings.deep_mode != on {
            self.settings.deep_mode = on;
            self.settings_changed();
            self.log(false, if on { "Deep mode on" } else { "Clean room on" });
            // Deep mode wants Ghidra: offer to get it now rather than quietly going without.
            if on && self.ghidra_missing() && self.ghidra.job.is_none() {
                self.state.modal = Some(state::Modal::Ghidra);
            }
        }
    }

    pub fn finish_first_run(&mut self) {
        self.settings.first_run_done = true;
        self.settings_changed();
        self.state.screen = Screen::Home;
    }

    // ---- session snapshot -------------------------------------------------------------------

    fn refresh_view(&mut self) {
        let stale = self.last_view.is_none_or(|t| t.elapsed() > Duration::from_millis(1500));
        if !self.view_dirty && !stale {
            return;
        }
        let Some(s) = self.engine.try_session() else { return };
        let targets = s
            .targets()
            .map(|t| TargetInfo {
                id: t.target.id.clone(),
                name: t.target.name.clone(),
                kind: t.target.kind,
                path: t.target.path.clone(),
                sha256: t.target.sha256.clone(),
                bytes: t.target.bytes.clone(),
            })
            .collect();
        let view = SessionView {
            targets,
            active: s.active_id().cloned(),
            clean_room: s.clean_room(),
            ledger: if self.view_dirty || self.view.ledger_len != s.ledger_len() {
                s.ledger().take(LEDGER_VIEW_CAP).cloned().collect()
            } else {
                std::mem::take(&mut self.view.ledger)
            },
            ledger_len: s.ledger_len(),
            unknowns: s.unknowns().take(500).cloned().collect(),
            project: s.project.as_ref().map(|p| p.meta.name.clone()),
            project_allows: s.project.as_ref().map(|p| p.meta.allowed_tools.clone()).unwrap_or_default(),
        };
        drop(s);
        self.view = view;
        self.view_dirty = false;
        self.last_view = Some(Instant::now());
        self.resolve_chat_evidence();
    }

    /// Fill in proof cards for agent tool calls once their evidence is in the ledger.
    fn resolve_chat_evidence(&mut self) {
        for item in &mut self.state.chat {
            if let ChatItem::Tool { evidence_id: Some(id), evidence: ev @ None, .. } = item
                && let Some(e) = self.view.ledger.iter().find(|e| &e.id == id)
            {
                *ev = Some(Box::new(e.clone()));
            }
        }
    }

    pub fn mark_dirty(&mut self) {
        self.view_dirty = true;
    }

    // ---- tools ------------------------------------------------------------------------------

    /// Build params for a tool from what its schema accepts (so `deny_unknown_fields` tools never
    /// get a field they don't know).
    pub fn params_for(&self, tool: &str, wanted: &[(&str, Value)]) -> Value {
        let mut out = serde_json::Map::new();
        let Some(spec) = self.engine.registry().get(tool) else { return Value::Object(out) };
        let schema = self.engine.registry().input_schema(spec);
        let props = schema.get("properties").and_then(Value::as_object);
        for (k, v) in wanted {
            if props.is_some_and(|p| p.contains_key(*k)) {
                out.insert((*k).to_string(), v.clone());
            }
        }
        Value::Object(out)
    }

    /// Run a tool on a worker; the result goes to `route`.
    pub fn run_tool(&mut self, tool: &str, params: Value, route: Route, consent: Consent) {
        let Some(spec) = self.engine.registry().get(tool).copied() else {
            self.log(true, format!("No tool named {tool}"));
            return;
        };
        match &route {
            Route::Rail(k) => {
                self.state.lists.insert(*k, Fill::Loading);
            }
            Route::View(t) => {
                self.state.views.insert(*t, Fill::Loading);
            }
            Route::Palette => {
                self.state.views.insert(CenterTab::Result, Fill::Loading);
                self.state.center = CenterTab::Result;
            }
            _ => {}
        }
        let engine = self.engine.clone();
        let id = spec.id.to_string();
        let title = spec.title.to_string();
        self.log(false, format!("Running {id}"));
        let chat = matches!(route, Route::Chat { .. });
        let job = self.jobs.spawn(title, true, move |j| {
            let progress = j.reporter();
            let opts = CallOptions::new(Caller::Ui).with_consent(consent).with_cancel(j.cancel.clone()).with_progress(&progress);
            let result = engine.call(&id, params.clone(), opts);
            Ok(Done::Tool { tool: id, params, route, result })
        });
        if chat {
            self.chat_jobs.push(job);
        }
    }

    /// Run a tool for a button on a worker (play, preview, open a folder…); the result comes back
    /// as `Done::Acted` and is shown by `acted`. A click is the person's consent.
    pub fn act(&mut self, tool: &'static str, params: Value, title: String) {
        let engine = self.engine.clone();
        self.jobs.spawn(title, false, move |j| {
            let progress = j.reporter();
            let opts = CallOptions::new(Caller::Ui).with_consent(Consent::Granted).with_cancel(j.cancel.clone()).with_progress(&progress);
            let result = engine.call(tool, params, opts).map(|o| o.to_json().get("result").cloned().unwrap_or(Value::Null));
            Ok(Done::Acted { tool, result })
        });
    }

    fn acted(&mut self, tool: &str, result: Result<Value, ToolError>) {
        match (tool, result) {
            ("project_preview", Ok(v)) => {
                let url = v.get("url").and_then(Value::as_str).map(str::to_string);
                self.preview.clone_from(&url);
                self.open_url = url;
            }
            ("project_play", Ok(v)) if v["already_running"].as_bool() == Some(true) => self.toast(tr("It's already open."), false),
            ("project_play", Ok(v)) if !v["closed_at_once"].is_null() => self.toast(pins::quit_at_once(&v), true),
            ("project_play", Ok(_)) => self.toast(tr("Starting… it opens in its own window."), false),
            ("project_play", Err(e)) => self.toast(format!("{} {}", tr("Couldn't start it."), e.for_people()), true),
            ("project_assets_budget" | "project_assets_allow", Ok(_)) => self.assets_changed(),
            ("rebuild_question_ask", r) => self.question_done(r),
            ("project_build_finish", Ok(v)) => {
                if let Some(ws) = self.workspace.as_mut().filter(|w| v["project"].as_str().is_some_and(|p| w.root == std::path::Path::new(p))) {
                    let _ = ws.reload();
                    // What the tool added to the saved conversation.
                    let text = craft_anything_engine::tools::project_tools::CALLED_DONE.to_string();
                    self.state.feed.push(craft_anything_engine::feed::FeedItem::Step { step: craft_anything_engine::workspace::Step::Done, text });
                }
                self.toast(tr("Called done. A new message carries on from here."), false);
            }
            ("project_questions_set", Ok(v)) => {
                // What was saved (the person's other changes on disk come along).
                if let Some(ws) = self.workspace.as_mut().filter(|w| v["project"].as_str().is_some_and(|p| w.root == std::path::Path::new(p))) {
                    let _ = ws.reload();
                }
                let decide = v["questions"].as_str() == Some("decide");
                self.toast(
                    tr(if decide { "The builder will decide its questions and tell you what it chose." } else { "The builder's questions will come to you." }),
                    false,
                );
            }
            ("project_pins_list" | "project_pin_create" | "project_pin_open" | "project_pin_stop" | "project_pin_rename" | "project_pin_delete", r) => {
                self.pin_done(tool, r)
            }
            ("project_rename" | "project_duplicate" | "project_delete", r) => self.managed(tool, r),
            // The tool changed the session's plugin list; take it, so saving settings keeps it.
            ("plugins_add" | "plugins_remove", Ok(_)) => {
                if let Some(s) = self.engine.try_session() {
                    self.settings.plugins = s.settings.plugins.clone();
                }
                self.toast(tr(if tool == "plugins_add" { "Plugin added. Read its tools to start using them." } else { "Plugin removed." }), false);
            }
            ("plugins_refresh", Ok(v)) => {
                let failed: Vec<String> = v["refreshed"]
                    .as_array()
                    .into_iter()
                    .flatten()
                    .filter_map(|r| r.get("error").and_then(Value::as_str).map(|e| format!("{}: {e}", r["id"].as_str().unwrap_or("?"))))
                    .collect();
                if failed.is_empty() {
                    self.toast(tr("Plugins read. Their new tools are offered from the next start."), false);
                } else {
                    self.toast(format!("{} {}", tr("Some plugins couldn't be read:"), failed.join("; ")), true);
                }
            }
            ("project_open_folder", Err(e)) => self.toast(format!("{} {}", tr("Couldn't open the folder."), e.message), true),
            (
                "game_archives_list"
                | "game_pak_list"
                | "game_unity_list"
                | "game_iostore_list"
                | "game_unity_bundle_list"
                | "game_unreal_texture_export"
                | "game_unity_asset_export",
                r,
            ) => game_files::tool_done(self, tool, r),
            // The Game files screen's look at a picked game.
            ("core_target_triage", r) => game_files::tool_done(self, tool, r),
            (_, Ok(_)) => {}
            (_, Err(e)) if clean_room::is_refusal(&e) => self.state.modal = Some(state::Modal::DeepMode),
            (_, Err(e)) => self.toast(e.for_people(), true),
        }
    }

    /// Says when a lock got stuck (crates/platform/src/sync.rs), with a way out.
    fn stuck_banner(&mut self, ui: &mut egui::Ui, ctx: &egui::Context) {
        use craft_anything_platform::sync::{self, ProblemKind};
        let Some(problem) = sync::problems().into_iter().find(|p| p.kind != ProblemKind::SlowJob) else { return };
        let t = theme::Tokens::get(ctx);
        let text = match problem.kind {
            ProblemKind::Broken => "Part of the app got stuck, so it was stopped and the rest carried on. Your work is kept.",
            _ => "Part of the app is stuck. Restarting clears it, and your work is kept.",
        };
        egui::Panel::top("stuck-banner").frame(egui::Frame::new().fill(t.card).inner_margin(egui::Margin::symmetric(14, 8))).show(ui, |ui| {
            ui.horizontal_wrapped(|ui| {
                icons::show(ui, "triangle-alert", 16.0, t.danger);
                ui.label(egui::RichText::new(i18n::tr(text)).color(t.text)).on_hover_text(problem.summary.clone());
                if let Some(path) = &problem.log
                    && widgets::secondary(ui, None, "Open log").on_hover_text(path.display().to_string()).clicked()
                {
                    self.open_log(path);
                }
                if widgets::secondary(ui, None, "Restart").clicked() {
                    match craft_anything_platform::process::start_another_copy() {
                        Ok(_) => ctx.send_viewport_cmd(egui::ViewportCommand::Close),
                        Err(e) => self.toast(e.message, true),
                    }
                }
                if widgets::secondary(ui, None, "Dismiss").clicked() {
                    sync::dismiss(&problem.summary);
                }
            });
        });
    }

    /// Show a failure log in the system's viewer for text files.
    pub(crate) fn open_log(&mut self, path: &std::path::Path) {
        if let Err(e) = craft_anything_platform::open_path(path) {
            self.toast(format!("{}: {}", e.message, path.display()), true);
        }
    }

    /// Open a file or folder as the active target.
    pub fn open_path(&mut self, path: PathBuf) {
        let path = if path.is_absolute() { path } else { std::env::current_dir().map(|d| d.join(&path)).unwrap_or(path) };
        let engine = self.engine.clone();
        let name = path.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_else(|| path.display().to_string());
        self.toast(i18n::trf("Opening {name}…", &[("name", &name)]), false);
        self.jobs.spawn(i18n::trf("Open {name}", &[("name", &name)]), true, move |j| {
            let params = json!({"path": path.to_string_lossy()});
            let result = engine.call("core_target_open", params, CallOptions::new(Caller::Ui).with_cancel(j.cancel.clone())).map(|o| match o {
                ToolOutput::Value(v) => v,
                ToolOutput::Evidence(e) => serde_json::to_value(*e).unwrap_or(Value::Null),
            });
            Ok(Done::Opened { path, result })
        });
    }

    /// Show a native file dialog on a worker thread.
    pub fn pick(&mut self, pick: Pick) {
        if self.headless {
            return;
        }
        #[cfg(not(target_arch = "wasm32"))]
        let suggested = game_files::suggested_name(self);
        #[cfg(not(target_arch = "wasm32"))]
        self.jobs.spawn("Choose a file", false, move |_| {
            let d = rfd::AsyncFileDialog::new();
            if matches!(pick, Pick::Pictures | Pick::Attach) {
                let title = if pick == Pick::Pictures { tr("Pictures of the original") } else { tr("Attach pictures") };
                let files = pollster::block_on(d.set_title(title).add_filter(tr("Pictures"), &["png", "jpg", "jpeg", "webp", "gif"]).pick_files());
                let files: Vec<PathBuf> = files.unwrap_or_default().iter().map(|h| h.path().to_path_buf()).collect();
                return Ok(if pick == Pick::Pictures { Done::Pictures(files) } else { Done::ToAttach(files) });
            }
            let handle = match pick {
                Pick::OpenFile => pollster::block_on(d.set_title(tr("Open an app or file")).pick_file()),
                Pick::OpenFolder => pollster::block_on(d.set_title(tr("Open a folder or app bundle")).pick_folder()),
                Pick::GhidraDir => pollster::block_on(d.set_title(tr("Where is Ghidra installed?")).pick_folder()),
                Pick::TargetFile => pollster::block_on(d.set_title(tr("Pick the app, game or file to rebuild")).pick_file()),
                Pick::TargetFolder => pollster::block_on(d.set_title(tr("Pick the app or game folder")).pick_folder()),
                Pick::ProjectsDir => pollster::block_on(d.set_title(tr("Where should new projects go?")).pick_folder()),
                Pick::ProjectFolder => pollster::block_on(d.set_title(tr("Pick the folder for this project")).pick_folder()),
                Pick::ExtraProjectsDir => pollster::block_on(d.set_title(tr("Pick a folder with projects in it")).pick_folder()),
                Pick::GameFolder => pollster::block_on(d.set_title(tr("Pick the game's folder")).pick_folder()),
                Pick::SavePicture => pollster::block_on(d.set_title(tr("Save the picture")).add_filter("PNG", &["png"]).set_file_name(&suggested).save_file()),
                Pick::AgentProgram => pollster::block_on(d.set_title(tr("Where is the program?")).pick_file()),
                Pick::Pictures | Pick::Attach => None,
            };
            Ok(Done::Picked { pick, path: handle.map(|h| h.path().to_path_buf()) })
        });
    }

    /// The overview tool used for a "first look" and for answering without an AI.
    pub fn first_look_tool(&self) -> Option<&'static str> {
        self.first_tool(&["core_target_triage", "core_overview_show", "native_overview", "core_session_show"])
    }

    pub fn first_look(&mut self, intro: &str, cta: bool) {
        if let Some(tool) = self.first_look_tool() {
            self.run_tool(tool, json!({}), Route::Chat { intro: intro.to_string(), cta }, Consent::NotAsked);
        }
    }

    /// Load the current rail list if it hasn't been.
    pub fn ensure_rail_loaded(&mut self) {
        let kind = self.state.rail;
        if kind == RailKind::Targets || self.view.active.is_none() {
            return;
        }
        if matches!(self.state.lists.get(&kind), None | Some(Fill::Idle)) {
            self.load_rail(kind);
        }
    }

    pub fn load_rail(&mut self, kind: RailKind) {
        let target = self.view.active_target().map(|t| (t.kind, t.path.display().to_string()));
        let Some(tool) = self.first_tool(kind.tools(target.as_ref().map(|t| t.0))) else {
            self.state.lists.insert(kind, Fill::Unavailable(i18n::trf("{name} isn't available yet in this build.", &[("name", &tr(kind.title()))])));
            return;
        };
        if let Some(blocked) = self.blocked(tool) {
            self.state.lists.insert(kind, blocked);
            return;
        }
        let path = target.map(|t| t.1).unwrap_or_default();
        let params = self.params_for(tool, &[("offset", json!(0)), ("limit", json!(2000)), ("input_path", json!(path))]);
        self.run_tool(tool, params, Route::Rail(kind), Consent::NotAsked);
    }

    /// `Some(Fill::Blocked)` when a tool can't run right now (checked without waiting).
    pub fn blocked(&self, tool: &str) -> Option<Fill> {
        let spec = self.engine.registry().get(tool)?;
        let s = self.engine.try_session()?;
        let a = self.engine.availability(spec, &s);
        let deep_needed = s.clean_room() && !clean_room::allows(tool);
        (!a.available).then(|| if deep_needed { Fill::DeepNeeded } else { Fill::Blocked(a.reason.unwrap_or_default(), a.remediation) })
    }

    /// Fill a centre view for the current selection.
    pub fn load_view(&mut self, tab: CenterTab) {
        let Some(tool) = self.first_tool(tab.tools()) else {
            self.state.views.insert(tab, Fill::Unavailable(i18n::trf("The {name} view isn't available yet in this build.", &[("name", &tr(tab.title()))])));
            return;
        };
        let sel = self.state.selection.clone().unwrap_or(Value::Null);
        let address = workbench::row_address(&sel);
        let name = workbench::row_name(&sel);
        let mut wanted: Vec<(&str, Value)> = vec![("offset", json!(0)), ("limit", json!(4096))];
        if let Some(a) = address.as_ref().or(name.as_ref()) {
            wanted.extend([("address", json!(a)), ("function", json!(a))]);
        }
        if let Some(n) = &name {
            wanted.extend([("name", json!(n)), ("module", json!(n)), ("path", json!(n))]);
        }
        let params = self.params_for(tool, &wanted);
        self.run_tool(tool, params, Route::View(tab), Consent::NotAsked);
    }

    // ---- AI ---------------------------------------------------------------------------------

    pub fn refresh_backends(&mut self) {
        let hub = self.hub.clone();
        self.jobs.spawn("Read AI settings", false, move |_| Ok(backends(&hub)));
    }

    /// Choose the backend that builds or extracts (`None`: its default).
    pub fn set_role(&mut self, role: craft_anything_ai::Role, name: Option<String>) {
        let hub = self.hub.clone();
        self.jobs.spawn(tr("Choose an AI's job"), true, move |_| {
            hub.set_role(role, name.as_deref()).map_err(|e| e.message)?;
            Ok(backends(&hub))
        });
    }

    pub fn detect_backends(&mut self) {
        if self.detecting {
            return;
        }
        self.detecting = true;
        let hub = self.hub.clone();
        self.jobs.spawn("Look for AI on this computer", true, move |_| Ok(Done::Detected(hub.detect())));
    }

    pub fn add_backend(&mut self, config: BackendConfig, key: Option<String>) {
        let hub = self.hub.clone();
        let name = config.name.clone();
        self.jobs.spawn(i18n::trf("Connect {name}", &[("name", &name)]), true, move |_| {
            let result = hub.add_backend(config, key);
            Ok(Done::BackendAdded { name, result })
        });
    }

    pub fn choose_backend(&mut self, name: Option<String>) {
        if self.state.backend != name {
            self.state.backend = name;
            if let Some(mut c) = self.conversation.take() {
                c.stop();
            }
        }
    }

    /// Send a question: to the AI when one is set up, otherwise answered by the built-in engines.
    pub fn send(&mut self, text: &str) {
        let text = text.trim().to_string();
        if text.is_empty() {
            return;
        }
        self.state.chat.push(ChatItem::User(text.clone()));
        if self.state.backend.is_some() && self.conversation.is_none() {
            match self.hub.start(self.state.backend.as_deref(), self.beginner()) {
                Ok(c) => self.conversation = Some(c),
                Err(e) => self.state.chat.push(ChatItem::Error { message: e.message, remediation: e.remediation, log: None }),
            }
        }
        if let Some(c) = self.conversation.as_mut() {
            let sent = if self.settings.mode == Mode::Beginner && self.state.explain_new {
                format!("{text}\n\n(Explain like I'm new to this: plain words, short sentences, no jargon.)")
            } else {
                text
            };
            c.send(&sent);
            return;
        }
        if self.view.active.is_none() {
            self.state.chat.push(ChatItem::Assistant {
                text: tr("Open something first: drop a file or app here, or choose \"Just look inside\" on New project. Then I can look inside it."),
                backend: None,
                streaming: false,
            });
            return;
        }
        self.first_look(&tr("There's no AI brain set up yet, so here's what the built-in engines found:"), true);
    }

    /// Stop the answer being worked on: the AI's, and tools working for the conversation. Builds,
    /// downloads and other jobs carry on.
    pub fn stop(&mut self) {
        if let Some(c) = self.conversation.as_mut() {
            c.stop();
        }
        for id in &self.chat_jobs {
            self.jobs.cancel(*id);
        }
    }

    /// An answer is being worked on (the Ask screen's "Working on your answer" and Stop).
    pub fn answering(&self) -> bool {
        self.conversation.as_ref().is_some_and(|c| c.is_busy()) || self.jobs.running().any(|j| self.chat_jobs.contains(&j.id))
    }

    pub fn busy(&self) -> bool {
        self.conversation.as_ref().is_some_and(|c| c.is_busy()) || self.jobs.busy() || self.runs.any_busy()
    }

    fn poll_conversation(&mut self) {
        let Some(c) = self.conversation.as_mut() else { return };
        let events = c.poll();
        if events.is_empty() {
            return;
        }
        for e in events {
            chat::apply_event(&mut self.state.chat, e.clone());
            match e {
                AgentEvent::ToolFinished { .. } => self.view_dirty = true,
                AgentEvent::TurnDone { backend, input_tokens, output_tokens, cost_usd, cost_is_estimate } => {
                    self.session_usage.add_turn(input_tokens, output_tokens, cost_usd, cost_is_estimate);
                    let cost = cost_usd.map(|c| format!(", ${c:.4}")).unwrap_or_default();
                    self.log(false, format!("{backend}: {input_tokens} in / {output_tokens} out{cost}"));
                }
                AgentEvent::Error { message, .. } => self.log(true, message),
                _ => {}
            }
        }
    }

    /// Answer a consent card (from the agent or from a UI-started tool).
    pub fn answer_consent(&mut self, call_id: &str, answer: ConsentAnswer) {
        let mut tool = None;
        for item in &mut self.state.chat {
            if let ChatItem::Consent { call_id: id, answer: a @ None, tool: t, .. } = item
                && id == call_id
            {
                *a = Some(answer);
                tool = Some(t.clone());
            }
        }
        let allow = answer != ConsentAnswer::Deny;
        if answer == ConsentAnswer::AlwaysForProject
            && let Some(t) = &tool
        {
            self.allow_for_project(t.clone());
        }
        if let Some(rest) = call_id.strip_prefix("ui:") {
            // A tool the UI started: run it again with consent.
            let call = rest.parse().ok().and_then(|id| self.pending_consent.remove(&id));
            if allow && let Some((tool, params, route)) = call {
                self.run_tool(&tool, params, route, Consent::Granted);
            }
        } else if let Some(c) = self.conversation.as_mut() {
            c.answer_consent(call_id, allow);
        }
    }

    fn allow_for_project(&mut self, tool: String) {
        let engine = self.engine.clone();
        self.jobs.spawn("Remember permission", false, move |_| {
            let mut s = engine.session();
            if let Some(p) = s.project.as_mut() {
                if !p.meta.allowed_tools.contains(&tool) {
                    p.meta.allowed_tools.push(tool);
                }
                p.save_meta().map_err(|e| e.message)?;
            }
            Ok(Done::Nothing)
        });
    }

    // ---- report -----------------------------------------------------------------------------

    pub fn export_report(&mut self) {
        let md = report::markdown(&self.state.chat, self.view.active_target(), self.view.clean_room);
        if self.headless {
            return;
        }
        let name = self.view.active_target().map(|t| format!("{} report.md", t.name)).unwrap_or_else(|| "Craft Anything report.md".into());
        let engine = self.engine.clone();
        #[cfg(not(target_arch = "wasm32"))]
        self.jobs.spawn("Export report", true, move |_| {
            let picked = pollster::block_on(
                rfd::AsyncFileDialog::new().set_title(tr("Save the report")).set_file_name(&name).add_filter("Markdown", &["md"]).save_file(),
            );
            let Some(h) = picked else { return Ok(Done::Wrote { what: "report".into(), path: None }) };
            let path = h.path().to_path_buf();
            // Written by the core_report_save tool, as any other client would.
            let params = json!({"path": path.display().to_string(), "text": md});
            engine.call("core_report_save", params, CallOptions::new(Caller::Ui)).map_err(|e| e.message)?;
            Ok(Done::Wrote { what: "report".into(), path: Some(path) })
        });
    }

    // ---- results ----------------------------------------------------------------------------

    fn handle_done(&mut self, done: jobs::Finished<Done>) {
        let job = done.job;
        if self.saving == Some(job) {
            self.saving = None;
        }
        if self.creating == Some(job) {
            self.creating = None;
        }
        self.chat_jobs.retain(|id| *id != job);
        let done = match done.result {
            Ok(d) => d,
            Err(e) => {
                self.detecting = false;
                self.facts_read(job, None);
                // A failed or cancelled engine download frees the button to try again.
                if self.engine_flow.job.is_some_and(|(_, id)| id == job) {
                    self.engine_flow.job = None;
                }
                if self.ghidra.job == Some(job) {
                    self.ghidra.job = None;
                }
                self.log(true, e.clone());
                self.toast(e, true);
                return;
            }
        };
        match done {
            Done::Nothing => {}
            Done::Projects(p) => {
                self.projects = p;
                self.refresh_pins();
            }
            Done::Facts(f) => self.facts_read(job, Some(f)),
            Done::PicturesAdded(added) => self.pictures_added(added),
            Done::Created { ws, request, backend, pictures } => self.created(*ws, request, backend, pictures),
            Done::Thumb { path, image } => self.thumb_ready(path, image),
            Done::Tool { tool, params, route, result } => self.tool_done(tool, params, route, result),
            Done::Acted { tool, result } => self.acted(tool, result),
            Done::Opened { path, result } => match result {
                Ok(v) => {
                    // Another target: a new conversation, so answers about two things don't mix.
                    if self.view.active_target().is_some_and(|t| t.path != path) {
                        self.state.chat.clear();
                        if let Some(mut c) = self.conversation.take() {
                            c.stop();
                        }
                    }
                    self.settings.recent.retain(|p| p != &path);
                    self.settings.recent.insert(0, path.clone());
                    self.settings.recent.truncate(12);
                    self.settings_changed();
                    self.state.lists.clear();
                    self.state.views.clear();
                    self.state.selection = None;
                    self.view_dirty = true;
                    let name = v.get("name").and_then(Value::as_str).unwrap_or("it").to_string();
                    self.toast(i18n::trf("Opened {name}", &[("name", &name)]), false);
                    self.log(false, format!("Opened {}", path.display()));
                    if self.beginner() {
                        self.state.screen = Screen::Ask;
                        self.state.chat.push(ChatItem::Status(i18n::trf("Opened {name}. Taking a first look…", &[("name", &name)])));
                        self.first_look(&tr("Here's a first look:"), false);
                    } else {
                        self.state.screen = Screen::Workbench;
                        self.state.rail = if self.state.rail == RailKind::Targets { RailKind::Functions } else { self.state.rail };
                        self.load_rail(self.state.rail);
                    }
                }
                Err(e) if clean_room::is_refusal(&e) => self.state.modal = Some(state::Modal::DeepMode),
                Err(e) => {
                    self.log(true, format!("Couldn't open {}: {}", path.display(), e.message));
                    self.toast(e.for_people(), true);
                }
            },
            Done::Detected(d) => {
                self.detecting = false;
                self.log(false, format!("Found {} AI option(s) on this computer", d.len()));
                self.detected = Some(d);
            }
            Done::Backends(b, builder, extractor, options) => {
                if self.state.backend.as_ref().is_some_and(|n| !b.iter().any(|c| &c.name == n)) {
                    self.state.backend = None;
                }
                self.backends = b;
                self.builder = builder;
                self.extractor = extractor;
                self.backend_options = options;
            }
            Done::ModelChoices { name, result } => match result {
                // Kept only while the picker is still open for that AI.
                Ok(models) if self.model_picker.as_ref().is_some_and(|(n, _)| *n == name) => self.model_picker = Some((name, Some(models))),
                Ok(_) => {}
                Err(e) => {
                    self.model_picker = None;
                    self.toast(e.for_people(), true);
                }
            },
            Done::BackendAdded { name, result } => match result {
                Ok(()) => {
                    if self.server_form.name.trim() == name {
                        self.server_form = ServerForm::default();
                    }
                    self.toast(i18n::trf("{name} is ready", &[("name", &name)]), false);
                    self.choose_backend(Some(name));
                    self.refresh_backends();
                }
                Err(e) => self.toast(e.for_people(), true),
            },
            Done::Picked { pick, path } => {
                if let Some(path) = path {
                    match pick {
                        Pick::OpenFile | Pick::OpenFolder => self.open_path(path),
                        Pick::GhidraDir => {
                            self.settings.engines.ghidra.install_dir = Some(path);
                            self.settings_changed();
                        }
                        Pick::TargetFile | Pick::TargetFolder => {
                            self.state.make.target = craft_anything_engine::workspace::TargetRef::Local { path: path.clone() };
                            self.state.make.game = pick == Pick::TargetFolder;
                            self.state.make.editing_url = false;
                            self.state.make.builder = None;
                            self.detect_game_engine(path);
                        }
                        Pick::ProjectsDir => {
                            self.settings.projects_dir = Some(path);
                            self.settings_changed();
                            self.refresh_projects();
                        }
                        Pick::ProjectFolder => folders::picked(self, path),
                        Pick::ExtraProjectsDir => self.add_project_folder(path),
                        Pick::GameFolder => game_files::folder_picked(self, path),
                        Pick::SavePicture => game_files::save_to(self, path),
                        Pick::AgentProgram => {
                            if let Some(name) = self.picking_program_for.take() {
                                self.set_agent_program(&name, Some(path.display().to_string()));
                            }
                        }
                        // Several files: these come back as Done::Pictures / Done::ToAttach.
                        Pick::Pictures | Pick::Attach => {}
                    }
                }
            }
            Done::Pictures(files) => self.add_pictures(files),
            Done::ToAttach(files) => self.attach(files),
            Done::Attached { root, text, attachments, files } => self.deliver(root, text, attachments, files),
            Done::GameEngines(inv) => self.engines_found(inv),
            Done::GameFound { path, found } => {
                // Only if that game is still the one picked.
                if self.state.make.target == (craft_anything_engine::workspace::TargetRef::Local { path }) {
                    self.state.make.found = found;
                }
            }
            Done::EngineGot { builder, installer } => self.engine_got(builder, installer),
            Done::GhidraGot => self.ghidra_got(),
            Done::AssetKeys(keys) => self.asset_keys = Some(keys),
            Done::Wrote { what, path } => {
                if let Some(p) = path {
                    self.toast(format!("{} {}", tr("Saved"), p.display()), false);
                    self.log(false, format!("Wrote {what} to {}", p.display()));
                }
            }
        }
    }

    fn tool_done(&mut self, tool: String, params: Value, route: Route, result: Result<ToolOutput, ToolError>) {
        self.view_dirty = true;
        let fill = match &result {
            Ok(ToolOutput::Evidence(e)) => Fill::Ready(e.clone()),
            Ok(ToolOutput::Value(v)) => Fill::Value(v.clone()),
            Err(e) if e.code == ErrorCode::ConsentRequired => Fill::Blocked(e.message.clone(), e.remediation.clone()),
            Err(e) if clean_room::is_refusal(e) => Fill::DeepNeeded,
            Err(e) => Fill::Error(e.message.clone(), e.remediation.clone()),
        };
        match &result {
            Ok(_) => self.log(false, format!("{tool} finished")),
            Err(e) => self.log(true, format!("{tool}: {}", e.message)),
        }
        match route {
            Route::Rail(k) => {
                self.state.lists.insert(k, fill);
            }
            Route::View(t) => {
                self.state.views.insert(t, fill);
            }
            Route::Palette => {
                if let Fill::Ready(e) = &fill {
                    self.state.selected_evidence = Some(e.id.clone());
                }
                self.state.views.insert(CenterTab::Result, fill);
                self.state.center = CenterTab::Result;
            }
            Route::Silent => {}
            Route::Chat { intro, cta } => {
                match result {
                    Ok(ToolOutput::Evidence(e)) => self.state.chat.push(ChatItem::Proof { intro, evidence: e }),
                    Ok(ToolOutput::Value(v)) => {
                        self.state.chat.push(ChatItem::Assistant { text: format!("{intro}\n\n{}", chat::describe_value(&v)), backend: None, streaming: false })
                    }
                    Err(e) if e.code == ErrorCode::ConsentRequired => {
                        let title = self.engine.registry().get(&tool).map(|s| s.title.to_string()).unwrap_or_else(|| tool.clone());
                        // The card carries a short id; the call it stands for waits here.
                        let id = self.next_consent;
                        self.next_consent += 1;
                        self.pending_consent.insert(id, (tool.clone(), params, Route::Chat { intro, cta }));
                        self.state.chat.push(ChatItem::Consent { call_id: format!("ui:{id}"), tool, title, explanation: e.message, answer: None });
                        return;
                    }
                    Err(e) if clean_room::is_refusal(&e) => {
                        self.state.modal = Some(state::Modal::DeepMode);
                        return;
                    }
                    Err(e) => self.state.chat.push(ChatItem::Error { message: e.message, remediation: e.remediation, log: None }),
                }
                if cta {
                    self.state.chat.push(ChatItem::AddBrain);
                }
            }
        }
    }

    // ---- frame ------------------------------------------------------------------------------

    /// Per-frame housekeeping: results, events, snapshot, theme. Never blocks.
    pub fn tick(&mut self, ctx: &egui::Context) {
        if !self.started {
            self.started = true;
            // Advanced mode opens on the workbench, unless a project was open.
            if !self.beginner() && self.state.screen == Screen::Home {
                self.state.screen = Screen::Workbench;
            }
            self.jobs.set_repaint(ctx);
            if !self.headless {
                self.refresh_backends();
                self.refresh_projects();
                self.refresh_game_engines();
                self.check_asset_keys();
                if !self.settings.first_run_done {
                    self.detect_backends();
                }
            }
        }
        let want = (self.theme_kind(), self.beginner());
        if self.applied_theme != Some(want) {
            theme::apply(ctx, want.0, want.1);
            self.applied_theme = Some(want);
        }
        for f in self.jobs.poll() {
            guard("job result", || self.handle_done(f));
        }
        if let Some(url) = self.open_url.take() {
            ctx.open_url(egui::OpenUrl::new_tab(url));
        }
        guard("conversation", || self.poll_conversation());
        guard("rebuild", || self.poll_run());
        guard("pins", || self.poll_pins(ctx));
        // Back from another window: projects may have been added, moved or removed meanwhile.
        if !self.headless && ctx.input(|i| i.events.iter().any(|e| matches!(e, egui::Event::WindowFocused(true)))) {
            self.refresh_projects();
            self.refresh_side_panel();
        }
        // Another project shown (or none read yet): read its files.
        if let Some(root) = self.workspace.as_ref().map(|w| &w.root).filter(|r| **r != self.facts.root) {
            self.facts = project::Facts { root: root.clone(), ..Default::default() };
            self.thumbs.clear();
            self.refresh_side_panel();
        }
        self.read_facts(ctx);
        self.flush_settings(ctx);
        // A build asked something while the window is behind others: flash it in the taskbar.
        if std::mem::take(&mut self.attention) && !ctx.input(|i| i.viewport().focused.unwrap_or(true)) {
            ctx.send_viewport_cmd(egui::ViewportCommand::RequestUserAttention(egui::UserAttentionType::Informational));
        }
        self.refresh_view();
        // A conversation and jobs are checked on a timer; runs repaint the window themselves
        // (`RunOptions::wake`), so only a slow check covers them.
        if self.conversation.as_ref().is_some_and(|c| c.is_busy()) || self.jobs.busy() {
            ctx.request_repaint_after(Duration::from_millis(100));
        } else if self.runs.any_busy() {
            ctx.request_repaint_after(Duration::from_secs(1));
        }
        // Dropped pictures go to the prompt box on Make or a project; anything else opens.
        let dropped: Vec<PathBuf> = ctx.input(|i| i.raw.dropped_files.iter().map(|f| f.path().to_path_buf()).filter(|p| !p.as_os_str().is_empty()).collect());
        let pictures = !dropped.is_empty() && dropped.iter().all(|p| craft_anything_engine::workspace::is_picture(p));
        match self.state.screen {
            Screen::Project if pictures => self.attach(dropped),
            Screen::Home if pictures => self.add_pictures(dropped),
            _ => {
                if let Some(p) = dropped.into_iter().next() {
                    self.open_path(p);
                }
            }
        }
    }

    /// Draw the whole interface.
    pub fn show(&mut self, ui: &mut egui::Ui) {
        let ctx = ui.ctx().clone();
        self.tick(&ctx);
        self.shortcuts(&ctx);
        let t = theme::Tokens::get(&ctx);
        // The title bar is on every screen: it is how the window moves, resizes and closes.
        egui::Panel::top("titlebar").exact_size(titlebar::HEIGHT).frame(egui::Frame::new().fill(t.chrome)).show(ui, |ui| {
            guard_ui(ui, "title bar", |ui| titlebar::show(self, ui));
        });
        self.stuck_banner(ui, &ctx);
        if !self.settings.first_run_done {
            egui::CentralPanel::default().frame(egui::Frame::new().fill(t.canvas)).show(ui, |ui| guard_ui(ui, "first run", |ui| first_run::show(self, ui)));
            titlebar::window_edge(&ctx);
            titlebar::resize_edges(&ctx);
            return;
        }

        if self.beginner() || self.state.screen != Screen::Workbench {
            egui::Panel::left("app-sidebar")
                .exact_size(sidebar::width(self, &ctx))
                .resizable(false)
                .frame(egui::Frame::new().fill(t.chrome).inner_margin(egui::Margin::symmetric(8, 0)))
                .show(ui, |ui| guard_ui(ui, "sidebar", |ui| sidebar::show(self, ui)));
            egui::CentralPanel::default().frame(egui::Frame::new().fill(t.canvas)).show(ui, |ui| {
                guard_ui(ui, "simple", |ui| match self.state.screen {
                    Screen::Home | Screen::Workbench => home::show(self, ui),
                    Screen::Ask => chat::ask_screen(self, ui),
                    Screen::Project => project::show(self, ui),
                    Screen::GameFiles => game_files::show(self, ui),
                })
            });
        } else {
            guard_ui(ui, "workbench", |ui| workbench::show(self, ui));
        }
        palette::show(self, &ctx);
        settings_ui::show(self, &ctx);
        home::modals(self, &ctx);
        self.toasts(&ctx);
        self.drop_overlay(&ctx);
        titlebar::window_edge(&ctx);
        titlebar::resize_edges(&ctx);
    }

    /// Messages float over the bottom of the window, newest at the bottom: the screen under them
    /// doesn't move when one comes or goes.
    fn toasts(&mut self, ctx: &egui::Context) {
        const CONFIRMATION: Duration = Duration::from_secs(4);
        // Times and messages stay in step even if something cleared the messages directly.
        self.toast_at.resize(self.state.toasts.len(), Instant::now());
        let mut i = 0;
        while i < self.state.toasts.len() {
            let gone = !self.state.toasts[i].1 && self.toast_at.get(i).is_some_and(|t| t.elapsed() >= CONFIRMATION);
            if gone {
                self.state.toasts.remove(i);
                self.toast_at.remove(i);
            } else {
                i += 1;
            }
        }
        if let Some(next) = self.state.toasts.iter().zip(&self.toast_at).filter(|((_, e), _)| !e).map(|(_, t)| CONFIRMATION.saturating_sub(t.elapsed())).min() {
            ctx.request_repaint_after(next);
        }
        if self.state.toasts.is_empty() {
            return;
        }
        let t = theme::Tokens::get(ctx);
        let width = (ctx.content_rect().width() - 32.0).clamp(200.0, 640.0);
        let mut dismiss = None;
        egui::Area::new(egui::Id::new("toasts")).order(egui::Order::Foreground).anchor(egui::Align2::CENTER_BOTTOM, egui::vec2(0.0, -16.0)).show(ctx, |ui| {
            ui.set_width(width);
            for (i, (text, error)) in self.state.toasts.iter().enumerate() {
                egui::Frame::new()
                    .fill(t.raised)
                    .stroke(egui::Stroke::new(1.0, if *error { t.danger.gamma_multiply(0.6) } else { t.card_border }))
                    .corner_radius(t.r_lg())
                    .shadow(egui::Shadow { offset: [0, 4], blur: 16, spread: 0, color: t.shadow })
                    .inner_margin(egui::Margin::symmetric(14, 8))
                    .show(ui, |ui| {
                        ui.set_width(width - 28.0);
                        ui.horizontal(|ui| {
                            let (icon, col) = if *error { ("triangle-alert", t.danger) } else { ("check", t.success) };
                            icons::show(ui, icon, 15.0, col);
                            ui.add(egui::Label::new(egui::RichText::new(text).color(if *error { t.text } else { t.text_dim })).wrap());
                            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                                if icons::button(ui, "x", 28.0, false, "Dismiss").clicked() {
                                    dismiss = Some(i);
                                }
                            });
                        });
                    });
                ui.add_space(6.0);
            }
        });
        if let Some(i) = dismiss {
            self.state.toasts.remove(i);
            if i < self.toast_at.len() {
                self.toast_at.remove(i);
            }
        }
    }

    fn drop_overlay(&self, ctx: &egui::Context) {
        if !ctx.input(|i| !i.raw.hovered_files.is_empty()) {
            return;
        }
        let t = theme::Tokens::get(ctx);
        let rect = ctx.content_rect();
        let painter = ctx.layer_painter(egui::LayerId::new(egui::Order::Foreground, egui::Id::new("drop")));
        painter.rect_filled(rect, 0.0, t.shadow);
        let inner = rect.shrink(40.0);
        painter.rect_stroke(inner, t.radius_lg, egui::Stroke::new(2.0, t.accent), egui::StrokeKind::Inside);
        // Pictures dropped on Make or a project are attached; anything else opens.
        let pictures = ctx.input(|i| i.raw.hovered_files.iter().all(|f| f.path.as_deref().is_some_and(craft_anything_engine::workspace::is_picture)));
        let attach = pictures && matches!(self.state.screen, Screen::Home | Screen::Project);
        let g = theme::heading_galley(&painter, tr(if attach { "Drop to attach" } else { "Drop to open it" }), theme::TITLE, t.text, f32::INFINITY);
        painter.galley(inner.center() - g.size() / 2.0, g, t.text);
    }

    fn shortcuts(&mut self, ctx: &egui::Context) {
        let (palette, esc) = ctx.input_mut(|i| (i.consume_key(egui::Modifiers::COMMAND, egui::Key::K), i.key_pressed(egui::Key::Escape)));
        if palette && self.settings.first_run_done {
            self.state.palette.open = !self.state.palette.open;
            self.state.palette.query.clear();
            self.state.palette.selected = 0;
            self.state.palette.form_tool = None;
        }
        if esc {
            if self.state.palette.open {
                self.state.palette.open = false;
            } else if self.state.modal.is_some() {
                home::dismiss(self);
            } else if self.state.settings_open {
                self.state.settings_open = false;
            } else if !matches!(self.state.screen, Screen::Home | Screen::Workbench) && ctx.memory(|m| m.focused().is_none()) {
                // Back to Home, unless Esc was meant for a text field.
                self.state.screen = Screen::Home;
            }
        }
    }
}

/// The 256 px app icon.
pub static APP_ICON_PNG: &[u8] = include_bytes!("../../../assets/app-icon/hicolor/256x256/apps/ai.storyteller.craft-anything.png");
/// The app icon's master SVG, drawn at the exact pixel size wherever the app shows its icon.
pub static APP_ICON_SVG: &[u8] = include_bytes!("../../../assets/app-icon/craft-anything.svg");

/// The app icon at `size` points.
pub fn app_icon(size: f32) -> egui::Image<'static> {
    egui::Image::from_bytes("bytes://app-icon.svg", APP_ICON_SVG).fit_to_exact_size(egui::Vec2::splat(size))
}

/// Run an action; a panic is logged and swallowed so one bad action never takes the app down.
/// The configured backends and the ones chosen to build and to extract (read off the UI thread).
pub(crate) fn backends(hub: &AiHub) -> Done {
    Done::Backends(hub.backends(), hub.chosen(craft_anything_ai::Role::Builder), hub.chosen(craft_anything_ai::Role::Extractor), hub.options())
}

pub fn guard<R>(what: &str, f: impl FnOnce() -> R) -> Option<R> {
    match std::panic::catch_unwind(std::panic::AssertUnwindSafe(f)) {
        Ok(r) => Some(r),
        Err(p) => {
            let msg = p.downcast_ref::<&str>().map(|s| s.to_string()).or_else(|| p.downcast_ref::<String>().cloned()).unwrap_or_default();
            log::error!("{what} panicked: {msg}");
            None
        }
    }
}

/// Draw part of the UI; a panic shows a calm notice in its place instead of crashing.
pub fn guard_ui(ui: &mut egui::Ui, what: &str, f: impl FnOnce(&mut egui::Ui)) {
    let ok = guard(what, || f(ui)).is_some();
    if !ok {
        let t = theme::Tokens::get(ui.ctx());
        ui.colored_label(t.danger, tr("Part of this screen hit a bug and was skipped. Your work is safe."));
    }
}

impl eframe::App for CraftApp {
    fn ui(&mut self, ui: &mut egui::Ui, _frame: &mut eframe::Frame) {
        self.show(ui);
    }

    fn save(&mut self, storage: &mut dyn eframe::Storage) {
        if let Ok(s) = serde_json::to_string(&self.prefs()) {
            storage.set_string(PREFS_KEY, s);
        }
    }

    fn on_exit(&mut self) {
        // A running build saves the project's conversation itself (rebuild::feed).
        if let Some(c) = self.conversation.as_mut() {
            c.stop();
        }
        self.runs.stop_all();
        for j in self.jobs.running() {
            j.cancel.cancel();
        }
        // A change not written yet (or one being written as the window closed) is written now.
        if self.persist && (self.settings_dirty || self.save_due.is_some() || self.saving.is_some()) {
            let _ = self.settings.save();
        }
    }
}

/// Short display of a path for recents.
pub fn short_path(p: &Path) -> String {
    let s = p.display().to_string();
    // Windows keeps the home folder in USERPROFILE.
    if let Some(home) = std::env::var_os("HOME").or_else(|| std::env::var_os("USERPROFILE")).map(PathBuf::from)
        && let Ok(rest) = p.strip_prefix(&home)
    {
        return format!("~{}{}", std::path::MAIN_SEPARATOR, rest.display());
    }
    s
}

/// Human byte size.
pub fn human_bytes(n: usize) -> String {
    craft_anything_engine::evidence::human_bytes(n as u64)
}

/// Icon for a target kind.
pub fn kind_icon(k: TargetKind) -> &'static str {
    match k {
        TargetKind::Elf | TargetKind::Pe | TargetKind::MachO | TargetKind::MachOFat | TargetKind::DosCom | TargetKind::RawBinary => "cpu",
        TargetKind::Managed | TargetKind::Jar | TargetKind::JavaClass => "boxes",
        TargetKind::Wasm => "binary",
        TargetKind::Apk | TargetKind::Dex => "smartphone",
        TargetKind::Zip | TargetKind::Asar => "package",
        TargetKind::Directory => "folder",
        TargetKind::Script => "file-code",
        TargetKind::NetworkCapture => "network",
        TargetKind::Plist => "list-tree",
        TargetKind::Evm => "zap",
        TargetKind::Sqlite => "database",
        TargetKind::Unknown => "file",
    }
}
