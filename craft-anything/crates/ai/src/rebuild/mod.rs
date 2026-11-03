//! The rebuild workflow: study a target, have a coding agent build it in the workspace's `app/`
//! folder, check the build against the target, and refine — asking the person when needed.
//!
//! ```text
//! Study   website: web_site_open + web_site_capture → capture/   (screenshots, blueprint, HTML)
//!         local:   triage (+ app graph for JS apps)  → capture/README.md
//! Build   the coding agent (an agent CLI such as Claude Code) works in the workspace with our
//!         MCP server; edits outside app/ and unusual commands ask the person (core_action_approve),
//!         questions arrive as cards (core_person_ask). Both go through the workspace inbox.
//! Check   website: serve app/dist on loopback, capture it the same way, compare screenshots
//!         (layout similarity per width). Other stacks: the build must succeed.
//! Refine  measured differences go back to the agent, up to `max_rounds`.
//! ```
//!
//! Everything runs on one worker thread; the UI drains [`RunEvent`]s with [`RebuildRun::poll`].
//!
//! Modules: `kinds` (what is made: [`TargetKind`]s and [`Check`]s), `study`, `brief` (the builder's prompts), `check`,
//! `locate` (what to study in a local target) and `output` (what a build produced).

use crate::cli_agents::{Builder, CliSpec};
use crate::{AgentEvent, AiHub, BackendKind, Conversation, Role};
use craft_anything_engine::inbox::{Answer, Inbox, InboxDir, Request};
use craft_anything_engine::project::{Project, Purpose};
use craft_anything_engine::workspace::{CheckResult, ProjectUsage, Status, TargetRef, Workspace};
use craft_anything_engine::{CallOptions, Caller, CancelToken, Engine, ToolOutput};
use craft_anything_engines::game;
use craft_anything_evidence::{ErrorCode, ToolError};
pub use craft_anything_platform::serve::StaticServer;
use craft_anything_platform::serve::serve_dir;
use craft_anything_platform::sync::Mutex;
use serde_json::{Value, json};
use std::collections::HashSet;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::mpsc::{Receiver, Sender};
use std::sync::{Arc, PoisonError};
use std::time::{Duration, Instant};

pub mod activity;
mod brief;
mod check;
pub mod feed;
pub mod kinds;
mod locate;
pub mod notes;
mod output;
pub mod project;
pub mod question;
pub mod runs;
pub mod self_check;
pub mod stacks;
pub mod stand_in;
mod study;
#[cfg(test)]
mod tests;
pub mod tools;

use brief::*;
pub use kinds::{
    AppKind, BriefCx, BuildCheck, Check, CheckCx, DetectCx, GameKind, KindRegistry, KindWords, MechanicsCheck, TargetKind, WebVisualCheck, WebsiteKind,
};
pub use locate::game_folder;
use locate::*;
use output::*;
pub use output::{built_program, launch, site_dir};
pub use runs::{RunSet, Started, Stopped, keep_queue_moving};
pub use stand_in::StandIns;

pub use craft_anything_engine::workspace::Step;

/// What the UI shows, in order.
#[derive(Debug, Clone, PartialEq)]
pub enum RunEvent {
    /// A stage started (with a plain-words line on what's happening).
    Step { step: Step, text: String },
    /// Something from the coding agent (text, tool calls, errors).
    Agent(AgentEvent),
    /// A note the person added while it worked, now read by the agent (as the feed shows it).
    Note(String),
    /// A question or approval waiting for the person.
    Ask(Request),
    /// A check finished.
    Checked(CheckResult),
    /// The build can be previewed here.
    Preview(String),
    Finished {
        ok: bool,
        message: String,
        /// The person paused it: not a failure.
        paused: bool,
    },
}

/// Called after each event a run sends, so a window draws it at once instead of checking on a
/// timer.
#[derive(Clone, Default)]
pub struct Wake(Option<Arc<dyn Fn() + Send + Sync>>);

impl Wake {
    pub fn new(f: impl Fn() + Send + Sync + 'static) -> Wake {
        Wake(Some(Arc::new(f)))
    }

    fn call(&self) {
        if let Some(f) = &self.0 {
            f();
        }
    }
}

impl std::fmt::Debug for Wake {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(if self.0.is_some() { "Wake(set)" } else { "Wake(none)" })
    }
}

/// Options for one run.
#[derive(Debug, Clone)]
pub struct RunOptions {
    /// The agent backend by name; `None` picks the Builder role, else the first agent app.
    pub backend: Option<String>,
    /// A follow-up request on an existing build (skips Study).
    pub message: Option<String>,
    /// How the person's message is shown in the project's feed (it can differ from `message`,
    /// which carries attachment paths). `None` adds nothing to the feed.
    pub shown: Option<String>,
    /// Pick up a build whose last run stopped part-way (paused, the app closed, the computer
    /// stopped): Study isn't repeated when it was done, and an agent with a saved session is
    /// told to carry on rather than given the brief again. A run with no message on a project
    /// whose builder has already worked does the same, so "Try again" never starts over.
    pub continuing: bool,
    /// Refinement rounds after the first build (each fixes what the last check found).
    pub max_rounds: u32,
    /// Stop refining once the build looks at least this alike (percent).
    pub good_enough: f64,
    pub beginner: bool,
    /// The kinds of thing this run can make (website, app, game, and any a fork registers).
    pub kinds: KindRegistry,
    /// How each coding agent is driven (Claude Code, Codex, Gemini CLI, and any a fork registers).
    pub adapters: crate::cli_agents::AgentAdapters,
    /// Told after each event (the app repaints).
    pub wake: Wake,
}

impl Default for RunOptions {
    fn default() -> Self {
        RunOptions {
            backend: None,
            message: None,
            shown: None,
            continuing: false,
            max_rounds: 6,
            good_enough: 90.0,
            beginner: true,
            kinds: KindRegistry::built_in(),
            adapters: Default::default(),
            wake: Wake::default(),
        }
    }
}

/// Something the person added while a run works, until the agent reads it.
#[derive(Debug, Clone, PartialEq)]
pub struct Note {
    /// Unique in this process, so the app can take a note back.
    pub id: u64,
    /// What the agent reads.
    pub text: String,
    /// How it appears in the project's feed.
    pub shown: String,
}

/// A running (or finished) rebuild.
pub struct RebuildRun {
    rx: Receiver<RunEvent>,
    stop: CancelToken,
    inbox: Inbox,
    running: Arc<AtomicBool>,
    preview: Arc<Mutex<Option<StaticServer>>>,
    /// What the person added while it works; the agent reads them at its next step.
    notes: Arc<Mutex<Vec<Note>>>,
    /// The project's conversation, kept in its folder.
    feed: Arc<Mutex<feed::FeedLog>>,
    pub root: PathBuf,
    started: Instant,
    activity: Arc<activity::Activity>,
}

impl RebuildRun {
    /// Start a run on a worker thread. Fails fast (before any work) when no coding agent is set up.
    pub fn start(hub: &AiHub, ws: Workspace, opts: RunOptions) -> Result<RebuildRun, ToolError> {
        let cfg = hub.config();
        let entry = builder_backend(&cfg, opts.backend.as_deref().or_else(|| project_builder(&cfg, &ws)))?;
        // An API backend builds with our own agent loop and the Build tools; its conversation is
        // kept in the project and continued by follow-ups (a fresh build starts a new one).
        let api = match entry.config.kind {
            BackendKind::AgentCli => None,
            _ => {
                if opts.message.is_none() || !ws.capture_dir().exists() {
                    let _ = std::fs::remove_file(ws.transcript_path());
                }
                Some(hub.start_builder(&entry, opts.beginner, Some(ws.transcript_path()))?)
            }
        };
        // A chosen extractor (an API backend, e.g. Kimi K3) takes a game's files out after a fresh
        // study; the run only uses it in Deep mode on a game (see Worker::extract).
        let fresh = opts.message.is_none() || !ws.capture_dir().exists();
        let extractor = match hub.chosen(Role::Extractor).and_then(|n| hub.config().get(&n).cloned()) {
            Some(e) if fresh && e.config.kind != BackendKind::AgentCli => {
                let _ = std::fs::remove_file(ws.root.join(EXTRACT_TRANSCRIPT));
                Some((e.config.name.clone(), hub.start_extractor(&e, opts.beginner, Some(ws.root.join(EXTRACT_TRANSCRIPT)))?))
            }
            _ => None,
        };
        let (tx, rx) = std::sync::mpsc::channel();
        let stop = CancelToken::default();
        let running = Arc::new(AtomicBool::new(true));
        let preview: Arc<Mutex<Option<StaticServer>>> = Arc::default();
        let notes: Arc<Mutex<Vec<Note>>> = Arc::default();
        let inbox = Inbox::new(ws.inbox_dir());
        // Notes left by an earlier run would be handed over again (ids restart with the process);
        // cleared before the app can add any to this one.
        notes::clear(&notes::notes_dir(&ws.inbox_dir()));
        let root = ws.root.clone();
        // The project's conversation: the run keeps it in the folder as it goes.
        let feed = Arc::new(Mutex::new(feed::FeedLog::open(&ws)));
        if let Some(shown) = opts.shown.clone() {
            feed.lock().unwrap_or_else(PoisonError::into_inner).push(feed::FeedItem::User(shown));
        }
        let ctx = Worker {
            wake: opts.wake.clone(),
            engine: hub.engine.clone(),
            tx,
            stop: stop.clone(),
            preview: preview.clone(),
            seen: HashSet::new(),
            inbox: inbox.clone(),
            editor: None,
            notes: notes.clone(),
            feed: feed.clone(),
            assets: hub.has_asset_keys(),
            decompiled: false,
            usage: Some(UsageClock { root: root.clone(), since: Instant::now() }),
            self_check: None,
        };
        let r2 = running.clone();
        std::thread::Builder::new()
            .name("rebuild".into())
            .spawn(move || {
                let mut ctx = ctx;
                let mut ws = ws;
                // A clone can run for hours: keep the computer from sleeping until it ends.
                let _awake = craft_anything_platform::keep_awake();
                let _here = self_check::BuildingHere::new(&ws.root);
                let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| ctx.run(&mut ws, entry, api, extractor, &opts)));
                let (ok, message, paused) = match result {
                    Ok(Ok(m)) => (true, m, false),
                    Ok(Err(e)) if e.code == ErrorCode::Cancelled => {
                        let _ = ws.set_status(Status::Stopped, "Paused. Send a message to continue.");
                        (false, "Paused.".to_string(), true)
                    }
                    Ok(Err(e)) => {
                        let msg = e.for_people();
                        let _ = ws.set_status(Status::NeedsYou, msg.clone());
                        (false, msg, false)
                    }
                    Err(_) => (false, "The workflow hit a bug and stopped safely. Your files are untouched.".to_string(), false),
                };
                ctx.record_usage(None);
                ctx.emit(RunEvent::Finished { ok, message, paused });
                r2.store(false, Ordering::SeqCst);
            })
            .map_err(|e| ToolError::internal(e.to_string()))?;
        let activity = feed.lock().unwrap_or_else(PoisonError::into_inner).activity();
        Ok(RebuildRun { rx, stop, inbox, running, preview, notes, feed, root, started: Instant::now(), activity })
    }

    /// Add something while it works; the agent reads it at its next step, and only then does it
    /// join the feed (as `shown`). Returns its id, to take it back with `unsend` until then.
    pub fn add_note(&self, text: String, shown: String) -> u64 {
        static NEXT: AtomicU64 = AtomicU64::new(1);
        let id = NEXT.fetch_add(1, Ordering::Relaxed);
        // Also left for an agent that takes notes at its next step; without it, after the turn.
        if let Err(e) = notes::hand_over(&notes::notes_dir(self.inbox.dir()), id, &text) {
            log::warn!("A note waits for the builder's turn to end: {}", e.message);
        }
        self.notes.lock().unwrap_or_else(PoisonError::into_inner).push(Note { id, text, shown });
        id
    }

    /// The notes still waiting for the agent, oldest first.
    pub fn waiting(&self) -> Vec<Note> {
        self.notes.lock().unwrap_or_else(PoisonError::into_inner).clone()
    }

    /// Take back a note the agent hasn't read yet; `None` once it has.
    pub fn unsend(&self, id: u64) -> Option<Note> {
        let mut notes = self.notes.lock().unwrap_or_else(PoisonError::into_inner);
        let i = notes.iter().position(|n| n.id == id)?;
        let dir = notes::notes_dir(self.inbox.dir());
        // Taking its file back first means the agent can't claim it after this.
        if !notes::take_back(&dir, id) && notes::was_read(&dir, id) {
            return None;
        }
        Some(notes.remove(i))
    }

    /// How many notes are still waiting for the agent.
    pub fn queued(&self) -> usize {
        self.notes.lock().unwrap_or_else(PoisonError::into_inner).len()
    }

    /// Notes the agent never got to (the run ended first), to send as the next message.
    pub fn take_notes(&self) -> Vec<Note> {
        std::mem::take(&mut *self.notes.lock().unwrap_or_else(PoisonError::into_inner))
    }

    pub fn poll(&mut self) -> Vec<RunEvent> {
        self.rx.try_iter().collect()
    }

    /// The project's conversation as the run has it now, for showing a project that is already
    /// building. Events not yet polled are in it, so they're dropped from the queue.
    pub fn feed_now(&mut self) -> Vec<feed::FeedItem> {
        let feed = self.feed.lock().unwrap_or_else(PoisonError::into_inner);
        while self.rx.try_recv().is_ok() {}
        feed.items().to_vec()
    }

    /// Answer a question or approval card.
    pub fn answer(&self, id: &str, answer: &Answer) -> Result<(), ToolError> {
        self.answer_as(id, answer, &answer.as_text())
    }

    /// Answer a card; `shown` is how the answer appears in the project's feed.
    pub fn answer_as(&self, id: &str, answer: &Answer, shown: &str) -> Result<(), ToolError> {
        self.inbox.answer(id, answer)?;
        self.feed.lock().unwrap_or_else(PoisonError::into_inner).answered(id, shown);
        Ok(())
    }

    pub fn stop(&self) {
        self.stop.cancel();
    }

    pub fn is_running(&self) -> bool {
        self.running.load(Ordering::SeqCst)
    }

    /// When it began working (a queued run begins when its turn comes).
    pub fn started(&self) -> Instant {
        self.started
    }

    /// How long since the run last had anything to say. Cheap: safe to read while drawing.
    pub fn quiet_for(&self) -> Duration {
        self.activity.quiet_for()
    }

    /// What it's on now. Cheap: safe to read while drawing.
    pub fn activity_now(&self) -> activity::ActivityNow {
        self.activity.now()
    }

    /// How many lines of its activity are at hand for [`RebuildRun::activity_lines`].
    pub fn activity_len(&self) -> usize {
        self.activity.len()
    }

    /// Some of its latest activity. Cheap: safe to read while drawing.
    pub fn activity_lines(&self, range: std::ops::Range<usize>) -> Vec<activity::ActivityLine> {
        self.activity.lines_in(range)
    }

    /// The file with all of it.
    pub fn activity_log(&self) -> PathBuf {
        self.root.join(craft_anything_engine::workspace::ACTIVITY_LOG)
    }

    pub fn preview_url(&self) -> Option<String> {
        self.preview.lock().unwrap_or_else(PoisonError::into_inner).as_ref().map(StaticServer::url)
    }
}

impl Drop for RebuildRun {
    fn drop(&mut self) {
        self.stop.cancel();
    }
}

/// Serve a workspace's built site for previewing (without running the workflow).
pub fn preview(ws: &Workspace) -> Result<StaticServer, ToolError> {
    let site = site_dir(&ws.app_dir()).ok_or_else(|| {
        ToolError::new(ErrorCode::NotFound, "There's no built website to show yet.").with_remediation("Ask for a rebuild, or open the project folder.")
    })?;
    serve_dir(&site).map_err(|e| ToolError::io(site.display(), e))
}

struct Worker {
    /// Told after each event.
    wake: Wake,
    engine: Arc<Engine>,
    tx: Sender<RunEvent>,
    stop: CancelToken,
    preview: Arc<Mutex<Option<StaticServer>>>,
    seen: HashSet<String>,
    inbox: Inbox,
    /// The game engine's editor for this run (Unity, Unreal or Godot stacks).
    editor: Option<PathBuf>,
    notes: Arc<Mutex<Vec<Note>>>,
    feed: Arc<Mutex<feed::FeedLog>>,
    /// An asset provider's key is set up, so the builder can generate pictures and 3D models if the
    /// project allows it.
    assets: bool,
    /// The builder has decompiled something this run (Deep mode requires it).
    decompiled: bool,
    /// Where this run adds its working time, tokens and cost (`None` in tests that don't build).
    usage: Option<UsageClock>,
    /// The kind and bar the builder's own checks (`rebuild_check`) are judged by, once known.
    self_check: Option<(Arc<dyn kinds::TargetKind>, f64)>,
}

/// The project a run records its usage in, and when it last did.
struct UsageClock {
    root: PathBuf,
    since: Instant,
}

/// How often a long agent turn saves the time worked so far, so a crash loses little of it.
const USAGE_FLUSH: Duration = Duration::from_secs(60);

impl Worker {
    /// Add the time worked since the last record (and an agent turn's tokens and reported cost)
    /// to the project's usage.json. The run is its only writer; a failure is logged and the build
    /// carries on.
    fn record_usage(&mut self, turn: Option<(u64, u64, Option<f64>, bool)>) {
        let Some(clock) = self.usage.as_mut() else { return };
        let ms = u64::try_from(clock.since.elapsed().as_millis()).unwrap_or(u64::MAX);
        clock.since = Instant::now();
        let saved = ProjectUsage::update(&clock.root, |u| {
            u.work_ms = u.work_ms.saturating_add(ms);
            if let Some((input, output, cost, estimate)) = turn {
                u.add_turn(input, output, cost, estimate);
            }
        });
        if let Err(e) = saved {
            log::warn!("Couldn't save the project's usage in {}: {}", clock.root.display(), e.message);
        }
    }

    /// Recorded and sent under one lock, so [`RebuildRun::feed_now`] sees each event once.
    fn emit(&self, e: RunEvent) {
        let mut feed = self.feed.lock().unwrap_or_else(PoisonError::into_inner);
        feed.record(&e);
        let _ = self.tx.send(e);
        drop(feed);
        self.wake.call();
    }

    fn step(&self, ws: &mut Workspace, step: Step, status: Status, text: &str) -> Result<(), ToolError> {
        self.stop.check()?;
        ws.set_status(status, text)?;
        self.emit(RunEvent::Step { step, text: text.to_string() });
        Ok(())
    }

    fn call(&self, tool: &str, params: Value) -> Result<ToolOutput, ToolError> {
        self.stop.check()?;
        // The person started this run for this target, which is the consent for opening it.
        let opts = CallOptions::new(Caller::Ui).with_consent(craft_anything_engine::Consent::Granted).with_cancel(self.stop.clone());
        // Said as it happens, so a long step shows what it's doing and the feed counts it.
        let call_id = format!("run-{tool}");
        self.emit(RunEvent::Agent(AgentEvent::ToolStarted { call_id: call_id.clone(), tool: tool.to_string(), input: Value::Null }));
        let result = self.engine.call(tool, params, opts);
        self.emit(RunEvent::Agent(AgentEvent::ToolFinished { call_id, tool: tool.to_string(), ok: result.is_ok(), summary: String::new(), evidence_id: None }));
        result
    }

    /// Point the engine at this workspace: its investigation project and inbox.
    fn attach(&self, ws: &Workspace) -> Result<(), ToolError> {
        let dir = ws.investigation_dir();
        let project = Project::open(&dir).or_else(|_| Project::create(&dir, &ws.manifest.name, Purpose::default()))?;
        let mut s = self.engine.session();
        s.open_project(project)?;
        s.ext.insert(Arc::new(InboxDir(ws.inbox_dir())));
        Ok(())
    }

    /// The prompt for notes the person added while the agent worked, if there are any.
    fn added(&self, ws: &mut Workspace) -> Option<String> {
        let notes = std::mem::take(&mut *self.notes.lock().unwrap_or_else(PoisonError::into_inner));
        if notes.is_empty() {
            return None;
        }
        // They go in this message, so no hook hands them over again.
        let dir = notes::notes_dir(&ws.inbox_dir());
        for n in &notes {
            notes::forget(&dir, n.id);
        }
        for n in &notes {
            self.emit(RunEvent::Note(n.shown.clone()));
        }
        // A cancelled step can't be reported, but the notes go in either way.
        let _ = self.step(ws, Step::Build, Status::Building, "Reading what you added…");
        let texts: Vec<String> = notes.into_iter().map(|n| n.text).collect();
        Some(added_prompt(&texts) + &pictures_reminder(ws))
    }

    /// Decides an ACP builder's permission requests with the same policy Claude Code's approval
    /// tool uses: allowed, refused, or asked of the person through this project's inbox.
    fn approver(&self, ws: &Workspace) -> crate::cli_agents::acp::Approver {
        let inbox = ws.inbox_dir();
        let (auto_mode, clean_room) = {
            let s = self.engine.session();
            (s.settings.auto_mode, s.clean_room())
        };
        let stop = self.stop.clone();
        Arc::new(move |tool: &str, input: &Value| {
            let r = craft_anything_engine::tools::interaction_tools::approve_with(
                Some(Inbox::new(inbox.clone())),
                auto_mode,
                clean_room,
                tool,
                input,
                &|| stop.is_cancelled(),
                &mut || {},
            );
            matches!(r, Ok(Ok(())))
        })
    }

    /// The editor for a game-engine stack. An engine that isn't ready stops the run before any
    /// work, with the way to get it.
    fn find_editor(&self, stack: &str) -> Result<Option<PathBuf>, ToolError> {
        let Some(b) = game::Builder::from_stack(stack).filter(|b| *b != game::Builder::Rust) else { return Ok(None) };
        let store = self.engine.session().settings.engine_store_dir();
        let inv = game::inventory(&game::Places::here(store));
        match inv.best(b) {
            Some(i) if inv.ready(b) => Ok(Some(i.program.clone())),
            _ => Err(ToolError::new(ErrorCode::BadSettings, format!("{} isn't ready on this computer yet.", b.name())).with_remediation(
                "Get it (Settings → Engines in the app), or pick another engine (\"Build with\" in the app, --build-with in the CLI) and start again.",
            )),
        }
    }

    /// How the builder's agent runs. Reads the session once: a lock taken twice in one statement
    /// is held by the first until the statement ends, and the second then waits forever.
    fn agent_spec(&self, ws: &Workspace, entry: &crate::BackendEntry, opts: &RunOptions) -> CliSpec {
        let (deep, config_dir) = {
            let session = self.engine.session();
            (!session.clean_room(), session.config_dir())
        };
        CliSpec {
            builder: Some(Builder { investigation: Some(ws.investigation_dir()), inbox: ws.inbox_dir() }),
            deep,
            logs: Some(crate::failure_log::dir_in(&config_dir)),
            resume: ws.manifest.agent_session.clone(),
            preamble: Some(
                "You work inside Craft Anything for a person who doesn't code. The message below is your task.

"
                .into(),
            ),
            adapters: opts.adapters.clone(),
            ..CliSpec::new(entry.config.clone(), entry.options.clone(), opts.beginner, Some(ws.root.clone()))
        }
    }

    /// The whole run: checks the builder can start, studies a new project, then builds and checks
    /// in rounds until it's good enough or the rounds run out. A coding agent's saved session is
    /// put back from the project first when this computer doesn't have it, and the project keeps
    /// a copy after every turn; when it can't be resumed, a new one starts from the brief and what
    /// the project kept. Returns the summary shown when it's ready.
    fn run(
        &mut self,
        ws: &mut Workspace,
        entry: crate::BackendEntry,
        api: Option<crate::agent::ApiConversation>,
        extractor: Option<(String, crate::agent::ApiConversation)>,
        opts: &RunOptions,
    ) -> Result<String, ToolError> {
        // Fail before any work when the agent's tools are missing or it can't sign in.
        let remote = entry.config.ssh_host.as_deref().is_some_and(|h| !h.trim().is_empty());
        if !remote && api.is_none() {
            let adapter = opts.adapters.for_agent(&entry.config.model);
            crate::cli_agents::check_builder_tools(adapter.as_ref(), &entry.config.model, &entry.options, &self.stop)?;
            let program = entry.options.command.clone().unwrap_or_else(|| crate::cli_agents::program_for(&entry.config.model));
            if adapter.signed_in(&program) == Some(false) {
                let who = crate::cli_agents::display_for(&entry.config.model);
                return Err(ToolError::new(ErrorCode::BadSettings, format!("{who} isn't signed in on this computer."))
                    .with_remediation(adapter.sign_in_fix().unwrap_or_default()));
            }
        }
        self.attach(ws)?;
        std::fs::create_dir_all(ws.app_dir()).map_err(|e| ToolError::io(ws.app_dir().display(), e))?;
        let no_kind = || {
            ToolError::new(ErrorCode::BadSettings, "No kind of project matches this request.")
                .with_remediation("Describe what to make: a website, an app or a game.")
        };
        if ws.manifest.stack.is_empty() {
            let deep = !self.engine.session().clean_room();
            let (_, stack) = opts.kinds.choose(&ws.manifest.request, &ws.manifest.target, deep).ok_or_else(no_kind)?;
            ws.manifest.stack = stack.to_string();
            ws.save()?;
        }
        let kind = opts.kinds.detect(&ws.manifest.request, &ws.manifest.target, &ws.manifest.stack).ok_or_else(no_kind)?;
        self.self_check = Some((kind.clone(), opts.good_enough));
        let kind = kind.as_ref();
        self.editor = self.find_editor(&ws.manifest.stack)?;
        let carrying_on = opts.continuing || (opts.message.is_none() && ws.builder_started());
        let first = (opts.message.is_none() && !carrying_on) || !ws.capture_dir().exists();
        if first {
            self.study(ws, kind)?;
            if let Some((name, ex)) = extractor {
                self.extract(ws, kind, &name, ex)?;
            }
        }
        // A coding agent resumes its own session; our loop resumes its kept transcript.
        let resumable = api.as_ref().is_none_or(crate::agent::ApiConversation::resumed);
        let api_loop = api.is_some();
        // A session another coding agent saved can't be continued by this one (#469).
        if !api_loop && ws.manifest.agent_session_by.as_deref() != Some(entry.config.model.as_str()) {
            ws.manifest.agent_session = ws.manifest.agent_session_for(&entry.config.model).map(str::to_string);
            ws.manifest.agent_session_by = Some(entry.config.model.clone());
            ws.save()?;
        }
        // A coding agent on this computer whose session the project keeps a copy of (#451).
        let keeper = (!api_loop && !remote).then(|| opts.adapters.for_agent(&entry.config.model));
        if let Some(a) = &keeper {
            self.restore_session(ws, a.as_ref());
        }
        // A coding agent that never saved a session starts over, so it needs the brief.
        let has_history = resumable && (api_loop || ws.manifest.agent_session.is_some());
        self.step(ws, Step::Build, Status::Building, "Getting the builder ready…")?;
        let spec = self.agent_spec(ws, &entry, opts);
        let mut agent: Box<dyn Conversation> = match api {
            Some(a) => Box::new(a),
            None => crate::cli_agents::builder_conversation(spec, self.approver(ws)),
        };
        // The builder's tool server is started in this run's mode (`--deep` or `--clean-room`).
        let s = self.engine.session();
        let (deep, ghidra) = (!s.clean_room(), s.settings.ghidra_launcher().is_some());
        let image_model = s.settings.assets.image_model.clone();
        drop(s);
        let cx = BriefCx { ws, deep, ghidra, editor: self.editor.as_deref(), assets: self.assets, image_model: image_model.as_deref() };
        // The project's settings as they are now, for an agent that carries on its session.
        let now = || kind.follow_up_sections(&cx).iter().map(|s| format!("\n\n{s}")).collect::<String>() + &pictures_reminder(ws);
        let mut prompt = match &opts.message {
            // An agent with a saved session gets the follow-up; one without (an API loop) starts
            // from the brief with the request added.
            Some(m) if !first && has_history => follow_up(m, kind) + &now(),
            // Carrying on after a stop: the same, told to finish what it was doing.
            None if carrying_on && !first && has_history => continue_prompt(kind) + &now(),
            _ => {
                let b = brief(kind, &cx, opts.message.as_deref());
                if api_loop { format!("{API_BUILDER}\n\n{b}") } else { b }
            }
        };
        // The extraction step left the original's files in app/Original/: the builder starts from them.
        if first && ws.app_dir().join(ORIGINALS_MANIFEST).is_file() {
            prompt.push_str(ORIGINALS_READY);
        }
        // A saved session may not be on this computer (the project was copied here): then a new
        // one starts from the brief and what the project already has.
        let mut fresh = (!api_loop && ws.manifest.agent_session.is_some()).then(|| {
            let handoff = keeper.as_ref().and_then(|a| a.handoff(&kept_session(ws)?, HANDOFF_CHARS));
            resumed_elsewhere(&brief(kind, &cx, opts.message.as_deref()), &ws.manifest.last_reply, handoff.as_deref())
        });
        let mut round = ws.manifest.checks.iter().map(|c| c.round).max().unwrap_or(0);
        let mut refinements = 0;
        // Deep mode on a program: decompiling is required, so a build turn without any gets one reminder.
        let must_decompile = !self.engine.session().clean_room() && matches!(ws.manifest.target, TargetRef::Local { .. });
        let mut reminded = false;
        // The builder finished and only the check didn't: the build is there to check.
        let mut only_check = carrying_on && !first && opts.message.is_none() && ws.manifest.awaiting_check;
        loop {
            if !std::mem::take(&mut only_check) {
                let doing = match (round, carrying_on) {
                    (0, false) => "Building the first version…",
                    (0, true) => "Carrying on with the build…",
                    _ => "Improving the build…",
                };
                self.step(ws, Step::Build, Status::Building, doing)?;
                ws.manifest.awaiting_check = false;
                let reply = self.turn(ws, agent.as_mut(), &prompt, fresh.take());
                // Kept even when the turn failed: the conversation is still worth carrying.
                if let Some(a) = &keeper {
                    self.keep_session(ws, a.as_ref());
                }
                let reply = reply?;
                if !reply.trim().is_empty() {
                    ws.manifest.last_reply = reply.trim().to_string();
                }
                // The stack is recorded as the one the build uses, once it shows: left to the builder,
                // or another than the default because the request asked for it. A game engine stays
                // (it says the project is a game, and its editor is found for it).
                if game::Builder::from_stack(&ws.manifest.stack).is_none()
                    && let Some(s) = stacks::used_in(&ws.app_dir())
                {
                    ws.manifest.stack = s.name.clone();
                }
                ws.manifest.awaiting_check = true;
                ws.save()?;
                // What the person added while the agent worked goes in before anything else.
                if let Some(p) = self.added(ws) {
                    prompt = p;
                    continue;
                }
                if must_decompile && !self.decompiled && !reminded {
                    reminded = true;
                    prompt = DECOMPILE_FIRST.to_string();
                    continue;
                }
            }
            round += 1;
            self.step(ws, Step::Check, Status::Checking, "Checking the build against the original…")?;
            let checks = self.checks_with_a_retry(ws, kind, round)?;
            ws.manifest.checks.extend(checks.iter().cloned());
            ws.manifest.awaiting_check = false;
            ws.save()?;
            for c in &checks {
                self.emit(RunEvent::Checked(c.clone()));
            }
            let not_good = checks.iter().find(|c| !c.good(opts.good_enough));
            if let Some(p) = self.added(ws) {
                prompt = p;
                continue;
            }
            let Some(check) = not_good else { break };
            if refinements >= opts.max_rounds {
                break;
            }
            refinements += 1;
            prompt = kind.refine(check) + &pictures_reminder(ws);
            if !api_loop {
                prompt.push_str(CHECK_BEFORE_REPLYING);
            }
        }
        if let Some(url) = self.preview.lock().unwrap_or_else(PoisonError::into_inner).as_ref().map(StaticServer::url) {
            self.emit(RunEvent::Preview(url));
        }
        let last = ws.manifest.checks.last().cloned();
        // A site that builds but isn't close enough is still usable; no working build is not.
        let usable = last.as_ref().is_some_and(|c| c.passed);
        if !usable {
            let why = last.map(|c| c.note).unwrap_or_default();
            return Err(ToolError::new(ErrorCode::ProgramFailed, format!("The build isn't working yet. {why}").trim().to_string())
                .with_remediation("Ask for a fix in the box below, or press Try again."));
        }
        let last = ws.manifest.checks.last().cloned();
        // The last round's checks, all of them: the last one alone (say a mechanics sheet) isn't the verdict.
        let last_round: Vec<CheckResult> = last.map(|l| ws.manifest.checks.iter().filter(|c| c.round == l.round).cloned().collect()).unwrap_or_default();
        let mut summary = if last_round.is_empty() { "Ready.".to_string() } else { format!("Ready: {}.", self_check::summary(&last_round, opts.good_enough)) };
        // What the builder couldn't find out is said, not hidden.
        match self_check::open_questions(ws).len() {
            0 => {}
            1 => summary.push_str(" 1 question about the original is still open."),
            n => summary.push_str(&format!(" {n} questions about the original are still open.")),
        }
        ws.set_status(Status::Ready, summary.clone())?;
        self.emit(RunEvent::Step { step: Step::Done, text: summary.clone() });
        Ok(summary)
    }

    /// One builder turn. Its session is kept even when the turn fails, so nothing is lost; a turn
    /// cut short (a time limit, a crash, a dropped connection) is picked up where it stopped, up to
    /// three times. Problems only the person can fix (sign-in, credit, a missing app) end the run.
    /// Deep mode on a game: the chosen extractor takes the game's own files out into app/Original/
    /// before the build (the person owns the game and chose this; nothing is decrypted).
    fn extract(&mut self, ws: &mut Workspace, kind: &dyn kinds::TargetKind, name: &str, mut ex: crate::agent::ApiConversation) -> Result<(), ToolError> {
        let TargetRef::Local { path } = ws.manifest.target.clone() else { return Ok(()) };
        if kind.id() != kinds::GameKind::ID || self.engine.session().clean_room() {
            return Ok(());
        }
        let folder = locate::game_folder(&path).unwrap_or(path);
        self.step(ws, Step::Study, Status::Inspecting, &format!("{name} is taking the game's own files out…"))?;
        std::fs::create_dir_all(ws.app_dir().join("Original")).map_err(|e| ToolError::io(ws.app_dir().display(), e))?;
        // A failed extraction doesn't stop the build: it says why, and the builder uses what's there.
        match self.converse(ws, &mut ex, &extract_brief(&folder)) {
            Err(e) if e.code == ErrorCode::Cancelled => Err(e),
            Err(e) => {
                let why = e.message.chars().take(200).collect::<String>();
                self.step(ws, Step::Study, Status::Inspecting, &format!("{name} couldn't finish taking the files out ({why}). Building with what's there."))
            }
            Ok(_) => Ok(()),
        }
    }

    /// The round's checks. A check that fails says what's wrong with the build; one that returns
    /// an error couldn't look at all (a browser that went away), which says nothing about the
    /// build, so it gets a second go before the run stops, and the run says what is really wrong.
    fn checks_with_a_retry(&self, ws: &Workspace, kind: &dyn kinds::TargetKind, round: u32) -> Result<Vec<CheckResult>, ToolError> {
        let e = match self.run_checks(ws, kind, round) {
            Err(e) if e.code != ErrorCode::Cancelled => e,
            done => return done,
        };
        self.emit(RunEvent::Agent(AgentEvent::Status { text: format!("The check couldn't finish ({}). Trying it once more…", e.message) }));
        self.run_checks(ws, kind, round).map_err(|e| {
            if e.code == ErrorCode::Cancelled {
                return e;
            }
            ToolError::new(e.code, format!("The build is finished, but it couldn't be checked: {}", e.message))
                .with_remediation("Press Try again to check it again. Nothing needs building again.")
        })
    }

    /// A copy of the builder's session in the project, so the conversation travels with the
    /// folder (#451). A copy that can't be made doesn't stop the build, but it's said.
    fn keep_session(&self, ws: &Workspace, adapter: &dyn crate::cli_agents::AgentAdapter) {
        let Some(from) = ws.manifest.agent_session.as_deref().and_then(|id| adapter.session_file(id)) else { return };
        let kept = match std::fs::metadata(&from) {
            Ok(m) if m.len() > MAX_KEPT_SESSION => Err(format!("it's over {} MB", MAX_KEPT_SESSION / 1_000_000)),
            Ok(_) => std::fs::read(&from)
                .map_err(|e| e.to_string())
                .and_then(|b| craft_anything_platform::fs::write_atomic_private(&ws.agent_session_path(), &b).map_err(|e| e.message)),
            Err(e) => Err(e.to_string()),
        };
        if let Err(why) = kept {
            let text =
                format!("Couldn't keep a copy of the builder's conversation in the project ({why}), so it won't go with the folder to another computer.");
            self.emit(RunEvent::Agent(AgentEvent::Status { text }));
        }
    }

    /// The project came from another computer with its builder's session kept in it: put it back
    /// where the agent looks, so the same conversation carries on (#451). If that fails, a new one
    /// starts from what the project has when the turn finds the session missing.
    fn restore_session(&self, ws: &Workspace, adapter: &dyn crate::cli_agents::AgentAdapter) {
        let (Some(id), Some(saved)) = (ws.manifest.agent_session.as_deref(), kept_session_bytes(ws)) else { return };
        let text = match adapter.restore_session(id, &saved, &ws.root) {
            Ok(false) => return,
            Ok(true) => "Brought the builder's earlier conversation over from the project folder.".to_string(),
            Err(e) => format!("Couldn't bring the builder's earlier conversation over from the project folder ({}).", e.message),
        };
        self.emit(RunEvent::Agent(AgentEvent::Status { text }));
    }

    /// `fresh`: what to send instead when the agent's saved session turns out not to be on this
    /// computer.
    fn turn(&mut self, ws: &mut Workspace, agent: &mut dyn Conversation, prompt: &str, mut fresh: Option<String>) -> Result<String, ToolError> {
        let mut prompt = prompt.to_string();
        let mut tries = 0u64;
        loop {
            let result = self.converse(ws, agent, &prompt);
            let lost = result.is_err() && agent.session_lost();
            if lost {
                // The id is for a session this computer doesn't have: never ask for it again.
                ws.manifest.agent_session = None;
                ws.save()?;
            } else if let Some(id) = agent.session_id() {
                ws.manifest.agent_session = Some(id);
                ws.save()?;
            }
            match result {
                Err(_) if lost && let Some(f) = fresh.take() => {
                    self.step(
                        ws,
                        Step::Build,
                        Status::Building,
                        "The builder's earlier conversation isn't on this computer. Starting a new one from what the project already has…",
                    )?;
                    prompt = f;
                }
                Err(e) if e.code != ErrorCode::Cancelled && tries < 3 && agent.session_id().is_some() && worth_retrying(&e.message) => {
                    tries += 1;
                    let why = e.message.chars().take(160).collect::<String>();
                    // A service that says how long to wait is waited for; otherwise a dropped
                    // connection or a busy service gets a moment, longer each time.
                    let wait = match retry_after(&e.message) {
                        Some(secs) => {
                            let note = format!("The AI service is busy or its rate limit was reached, and asked to wait {secs} s. Trying again then…");
                            self.step(ws, Step::Build, Status::Building, &note)?;
                            secs + 1
                        }
                        None => {
                            self.step(ws, Step::Build, Status::Building, &format!("The builder stopped ({why}). Picking up where it left off…"))?;
                            30 * tries
                        }
                    };
                    for _ in 0..wait {
                        self.stop.check()?;
                        std::thread::sleep(Duration::from_secs(1));
                    }
                    prompt = format!(
                        "Your last turn was cut off ({why}). Carry on from where you stopped: look at what's already in app/ and your checklist, then finish the task."
                    );
                }
                r => return r,
            }
        }
    }

    /// Send one message and pump the agent until its turn ends, relaying events and inbox
    /// requests. Returns the agent's reply text.
    fn converse(&mut self, ws: &mut Workspace, agent: &mut dyn Conversation, text: &str) -> Result<String, ToolError> {
        agent.send(text);
        let mut reply = String::new();
        let mut failed = None;
        loop {
            if self.stop.is_cancelled() {
                agent.stop();
            }
            for e in agent.poll() {
                match &e {
                    AgentEvent::TextDelta { text } => reply.push_str(text),
                    // Our own loop asks before tools that need consent. The Build tools are the
                    // builder's job (they apply the approval policy themselves); nothing else runs.
                    AgentEvent::ConsentNeeded { call_id, tool, .. } => {
                        let build = self.engine.registry().get(tool).is_some_and(|s| s.toolset == craft_anything_engine::Toolset::Build);
                        agent.answer_consent(call_id, build);
                    }
                    // Decided on the tool's own id (its CLI and `mcp__…__` names included).
                    AgentEvent::ToolStarted { tool, .. }
                        if self.engine.registry().canonical(tool) == Some(craft_anything_engine::tools::native_function::PSEUDOCODE_TOOL) =>
                    {
                        self.decompiled = true
                    }
                    AgentEvent::Error { message, remediation, .. } => failed = Some((message.clone(), remediation.clone())),
                    _ => {}
                }
                if let AgentEvent::TurnDone { input_tokens, output_tokens, cost_usd, cost_is_estimate, .. } = &e {
                    self.record_usage(Some((*input_tokens, *output_tokens, *cost_usd, *cost_is_estimate)));
                }
                let done = matches!(e, AgentEvent::TurnDone { .. });
                // A saved session that isn't on this computer isn't the build failing: the turn
                // starts a new one (or, with nothing to start it from, the run's error says why).
                if !(matches!(e, AgentEvent::Error { .. }) && agent.session_lost()) {
                    self.emit(RunEvent::Agent(e));
                }
                if done {
                    self.stop.check()?;
                    // An agent-level error (sign-in, crash, limits) ends the run: checking a
                    // build that never happened would only mislead.
                    if let Some((m, r)) = failed {
                        return Err(ToolError::new(ErrorCode::ProgramFailed, m).with_remediation(r.unwrap_or_default()));
                    }
                    return Ok(reply);
                }
            }
            self.relay_inbox();
            self.relay_read_notes(ws);
            self.answer_self_checks(ws)?;
            if self.usage.as_ref().is_some_and(|c| c.since.elapsed() >= USAGE_FLUSH) {
                self.record_usage(None);
            }
            std::thread::sleep(Duration::from_millis(120));
        }
    }

    /// Notes the builder took at a step of this turn (its hook claimed them): they join the feed
    /// now and aren't sent again after the turn.
    fn relay_read_notes(&self, ws: &Workspace) {
        let dir = notes::notes_dir(&ws.inbox_dir());
        let read: Vec<Note> = {
            let mut notes = self.notes.lock().unwrap_or_else(PoisonError::into_inner);
            let (read, waiting) = std::mem::take(&mut *notes).into_iter().partition(|n| notes::was_read(&dir, n.id));
            *notes = waiting;
            read
        };
        for n in read {
            notes::forget(&dir, n.id);
            self.emit(RunEvent::Note(n.shown));
        }
    }

    fn relay_inbox(&mut self) {
        for r in self.inbox.pending() {
            if self.seen.insert(r.id.clone()) {
                self.emit(RunEvent::Ask(r));
            }
        }
    }
}

/// Largest builder session the project keeps a copy of.
const MAX_KEPT_SESSION: u64 = 64_000_000;
/// How much of a kept session a new one is handed when the old one isn't on this computer.
const HANDOFF_CHARS: usize = 16_000;

/// The builder's session as the project kept it, if it did.
fn kept_session_bytes(ws: &Workspace) -> Option<Vec<u8>> {
    let path = ws.agent_session_path();
    if std::fs::metadata(&path).ok()?.len() > MAX_KEPT_SESSION {
        return None;
    }
    std::fs::read(path).ok()
}

/// The kept session as text, for a handoff (a broken byte doesn't lose the rest).
fn kept_session(ws: &Workspace) -> Option<String> {
    kept_session_bytes(ws).map(|b| String::from_utf8_lossy(&b).into_owned())
}

/// What an API-backend builder is told first: its tools differ from an agent app's.
const API_BUILDER: &str = "Your tools: build_files_list, build_file_read, build_file_write and build_file_edit for the project's files (paths relative to the project folder, e.g. app/src/main.rs), and build_command_run for commands, which run in app/ (never start dev servers or watchers). Where the steps below mention Read, Write, Edit or Bash, use these. For the checklist step use build_checklist (the same shape as TodoWrite: todos with content, activeForm and status) and call it again as you go. You can't look at pictures: use capture/README.md, capture/capture.json and the evidence instead. Ask the person with core_person_ask only when a choice really changes the result. Other Craft Anything tools are available too; enable a toolset with enable_toolset when you need it. rebuild_check isn't available in this loop: Craft Anything checks your build after each turn instead.";

/// Added to a refinement for a builder that can check its own work.
const CHECK_BEFORE_REPLYING: &str = " Before you reply, check your build again with rebuild_check and fix what it still lists.";

/// The backend the person chose for this project, while it's still set up and on (else the
/// default builds it).
pub fn project_builder<'a>(cfg: &crate::AiConfig, ws: &'a Workspace) -> Option<&'a str> {
    ws.manifest.builder.as_deref().filter(|n| cfg.get(n).is_some_and(|b| b.config.enabled))
}

/// The backend that builds: the one named, else the Builder role's, else an agent app, else any
/// enabled AI backend (which builds with our own agent loop and the Build tools).
pub fn builder_backend(cfg: &crate::AiConfig, named: Option<&str>) -> Result<crate::BackendEntry, ToolError> {
    let found = match named {
        Some(n) => cfg.get(n).cloned(),
        None => {
            cfg.backend_for(Role::Builder).or_else(|| cfg.enabled().find(|b| b.config.kind == BackendKind::AgentCli)).or_else(|| cfg.enabled().next()).cloned()
        }
    };
    found.ok_or_else(|| {
        ToolError::new(ErrorCode::BadSettings, "Building needs a coding agent (such as Claude Code) or an AI backend with an API key.")
            .with_remediation("Install a coding agent or add an API key in Settings → AI, then try again.")
    })
}

/// Whether a failed builder turn is worth resuming, rather than needing the person (sign-in,
/// credit, a missing, broken or too old install).
fn worth_retrying(message: &str) -> bool {
    let m = message.to_ascii_lowercase();
    !["sign in", "log in", "login", "logged in", "auth", "credit", "billing", "usage limit", "not installed", "install ", crate::cli_agents::TOO_OLD_FOR_MODEL]
        .iter()
        .any(|k| m.contains(k))
}

/// The longest wait a service's "retry in …" is followed for.
const MAX_RETRY_WAIT: u64 = 15 * 60;

/// How long a busy or rate-limited service asked to wait ("Please retry in 19.05s", "retry after
/// 2 minutes"), in whole seconds rounded up and at most [`MAX_RETRY_WAIT`] (#142).
fn retry_after(message: &str) -> Option<u64> {
    let m = message.to_ascii_lowercase();
    let at = ["retry in ", "retry after ", "try again in "].iter().find_map(|p| m.find(p).map(|i| i + p.len()))?;
    let rest = m.get(at..)?;
    let number: String = rest.chars().take_while(|c| c.is_ascii_digit() || *c == '.').collect();
    let value: f64 = number.parse().ok()?;
    let unit = rest.get(number.len()..).unwrap_or_default().trim_start();
    let seconds = if unit.starts_with("ms") || unit.starts_with("millisecond") {
        value / 1000.0
    } else if unit.starts_with("min") || (unit.starts_with('m') && !unit.starts_with("ms")) {
        value * 60.0
    } else if unit.starts_with('h') {
        value * 3600.0
    } else {
        value
    };
    Some((seconds.ceil().max(1.0) as u64).min(MAX_RETRY_WAIT))
}
