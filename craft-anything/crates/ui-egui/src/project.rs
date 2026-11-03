//! The Project screen: one thing being made. Left: what it is, the four steps, checks and
//! actions (preview, folder, details). Right: a plain-words activity feed with question and
//! approval cards, and a box to ask for changes. Technical detail (each tool the agent used)
//! stays folded away in Simple mode.

use crate::i18n::{tr, trf};
use crate::make::{self, resolve_target};
use crate::state::{FeedItem, MakeDraft, Modal, PlanStatus, PlanStep, Screen};
use crate::theme::{self, Tokens};
use crate::{CraftApp, Done, chat, icons, prompt_box, widgets};
use craft_anything_ai::AgentEvent;
use craft_anything_ai::rebuild::activity::{Action, ActivityNow, LineKind};
use craft_anything_ai::rebuild::feed::{self, apply};
use craft_anything_ai::rebuild::{self, AppKind, KindRegistry, KindWords, Note, RebuildRun, RunEvent, RunOptions, Started, Step, Stopped, TargetKind};
use craft_anything_engine::inbox::{Answer, Inbox, Request, RequestKind};
use craft_anything_engine::workspace::{CheckResult, Status, TargetRef, Workspace, suggest_name};
use egui::{Color32, Margin, RichText, Ui, Vec2};
use std::path::{Path, PathBuf};

// ---- controller -------------------------------------------------------------------------------

impl CraftApp {
    pub fn refresh_projects(&mut self) {
        let locations = self.settings.project_locations();
        self.jobs.spawn("Read projects", false, move |_| Ok(Done::Projects(Workspace::list_in(&locations))));
    }

    /// The open project is building or waiting its turn.
    fn running(&self) -> bool {
        self.workspace.as_ref().is_some_and(|ws| self.runs.is_busy(&ws.root))
    }

    /// The open project's run, working or finished.
    fn open_run(&self) -> Option<&RebuildRun> {
        self.workspace.as_ref().and_then(|ws| self.runs.get(&ws.root))
    }

    /// The open project's place in the queue (1 starts next).
    pub fn queue_position(&self) -> Option<usize> {
        self.workspace.as_ref().and_then(|ws| self.runs.position(&ws.root))
    }

    /// Start a new project from the Home prompt.
    pub fn start_make(&mut self) {
        self.start_draft(self.state.make.clone());
    }

    /// Start a new project from `draft` (Make's, or one that waited for Ghidra).
    pub(crate) fn start_draft(&mut self, draft: MakeDraft) {
        let request = draft.request.trim().to_string();
        if request.is_empty() {
            return;
        }
        let Some(backend) = self.builder_backend(draft.ai.as_deref()) else { return self.need_builder(true) };
        // Games are built with an engine, unless the request names another way to build; one that
        // isn't here yet is got first, then this starts.
        let game = make::is_game(&self.kinds, &draft);
        let engine = if game { crate::engine_ui::chosen(&self.kinds, &draft) } else { None };
        if let Some(b) = engine
            && !self.game_engines.as_ref().is_some_and(|i| i.ready(b))
        {
            self.engine_flow.start_after = true;
            self.state.modal = Some(Modal::Engine(b));
            return;
        }
        let target = resolve_target(&draft);
        // Deep mode reads a program's code with Ghidra: got first when it isn't here (asked once).
        if matches!(target, TargetRef::Local { .. }) && !draft.skip_ghidra && self.ghidra_missing() {
            self.ghidra.start_after = Some(Box::new(draft));
            self.state.modal = Some(Modal::Ghidra);
            return;
        }
        if self.creating.is_some() {
            return;
        }
        let name = suggest_name(&request, &target);
        let (projects_dir, budget, generate) = (self.settings.projects_dir(), self.settings.assets.budget(), game && draft.generate_assets);
        // The folder, its records and copies of the pictures are written on a worker (a slow or
        // network drive must not freeze the window); `created` starts the build.
        self.creating = Some(self.jobs.spawn(tr("Create the project"), false, move |_| {
            let created = match &draft.folder {
                Some(folder) => Workspace::create_at(folder, &name, &request, target, draft.existing),
                None => Workspace::create(&projects_dir, &name, &request, target),
            };
            let mut ws = created.map_err(|e| e.for_people())?;
            // A new project starts with the asset budget from Settings and the person's choice of
            // generated assets.
            if let Some(b) = engine {
                ws.manifest.stack = b.stack().to_string();
            }
            ws.set_person(|m| {
                m.asset_budget_usd = budget;
                m.generate_assets = generate;
                // Picked on Make: its later changes are built by it too.
                m.builder = draft.ai;
            })
            .map_err(|e| e.for_people())?;
            let pictures = ws.add_references(&draft.pictures).err().map(|e| e.message);
            Ok(Done::Created { ws: Box::new(ws), request, backend, pictures })
        }));
    }

    /// A project from [`Self::start_make`] was made: its build starts.
    pub(crate) fn created(&mut self, ws: Workspace, request: String, backend: String, pictures: Option<String>) {
        if let Some(e) = pictures {
            self.toast(format!("{} {}", tr("Couldn't add the pictures:"), e), true);
        }
        // A project in a folder of its own stays in the list.
        self.remember_project(&ws.root);
        // Make is cleared for the next one, unless the person has started on it meanwhile (a
        // project that waited for Ghidra).
        if self.state.make.request.trim() == request {
            self.state.make = MakeDraft::default();
        }
        self.state.feed = vec![FeedItem::User(request)];
        self.start_run(ws, Some(backend), None, None);
    }

    fn run_options(&self, backend: Option<String>, message: Option<String>, shown: Option<String>) -> RunOptions {
        let build = &self.settings.build;
        // Each event repaints the window, so a build needs no timer to show its progress.
        let wake = self.jobs.repaint_ctx().cloned().map_or_else(Default::default, |ctx| rebuild::Wake::new(move || ctx.request_repaint()));
        RunOptions {
            wake,
            backend,
            message,
            shown,
            beginner: self.beginner(),
            kinds: self.kinds.clone(),
            max_rounds: build.max_rounds,
            good_enough: build.good_enough,
            ..RunOptions::default()
        }
    }

    /// Start a run, or queue it when as many as Settings allows are already building.
    fn launch(&mut self, ws: Workspace, opts: RunOptions) -> Result<Started, craft_anything_engine::evidence::ToolError> {
        self.runs.set_limit(self.settings.build.parallel);
        self.runs.start(&self.hub, ws, opts)
    }

    /// `shown`: the person's message as the feed shows it (already in the app's feed).
    fn start_run(&mut self, ws: Workspace, backend: Option<String>, message: Option<String>, shown: Option<String>) {
        let opts = self.run_options(backend, message, shown);
        self.start_run_with(ws, opts);
    }

    fn start_run_with(&mut self, ws: Workspace, opts: RunOptions) {
        self.preview = None;
        self.state.screen = Screen::Project;
        match self.launch(ws.clone(), opts) {
            Ok(Started::Running) => {}
            Ok(Started::Queued { .. }) => self.toast(tr("Another build is working, so this one waits its turn."), false),
            Err(e) => self.state.feed.push(FeedItem::Error { message: e.message, remediation: e.remediation, log: None }),
        }
        self.workspace = Some(ws);
        self.refresh_projects();
    }

    /// Show a project: a building one's conversation comes from its run, any other's from what
    /// was saved. Other projects keep building meanwhile.
    pub fn open_workspace(&mut self, ws: Workspace) {
        let same = self.workspace.as_ref().is_some_and(|w| w.root == ws.root);
        if !same {
            // What was typed here stays with this project; the next one's comes back.
            let typed = (std::mem::take(&mut self.state.project_input), std::mem::take(&mut self.state.project_attachments));
            if let Some(old) = &self.workspace
                && (!typed.0.trim().is_empty() || !typed.1.is_empty())
            {
                self.state.unsent.insert(old.root.clone(), typed);
            }
            (self.state.project_input, self.state.project_attachments) = self.state.unsent.remove(&ws.root).unwrap_or_default();
            // Events so far go to the project they belong to before the screen changes.
            self.poll_run();
            self.preview = None;
            self.state.feed = match self.runs.get_mut(&ws.root).filter(|r| r.is_running()) {
                Some(run) => run.feed_now(),
                None => feed::load(&ws),
            };
            self.load_asked(&ws);
        }
        self.workspace = Some(ws);
        self.refresh_side_panel();
        self.state.screen = Screen::Project;
    }

    /// Ask for a change (or continue after a pause or error).
    pub fn follow_up(&mut self, text: Option<String>) {
        if self.running() {
            return;
        }
        if let Some(t) = &text {
            self.state.feed.push(FeedItem::User(t.clone()));
        }
        let shown = text.clone();
        self.resume(text, shown);
    }

    /// Carry on where the open project's last run stopped (paused, or the app or the computer
    /// closed): the builder picks up its own session instead of starting over.
    pub fn continue_build(&mut self) {
        if self.running() {
            return;
        }
        let Some(ws) = self.workspace.clone() else { return };
        let Some(backend) = self.builder_backend(ws.manifest.builder.as_deref()) else { return self.need_builder(false) };
        let ws = Workspace::open(&ws.root).unwrap_or(ws);
        let opts = RunOptions { continuing: true, ..self.run_options(Some(backend), None, None) };
        self.start_run_with(ws, opts);
    }

    pub fn pause(&mut self) {
        let Some(root) = self.workspace.as_ref().map(|w| w.root.clone()) else { return };
        if self.runs.stop(&root) == Stopped::Unqueued {
            apply(&mut self.state.feed, &RunEvent::Finished { ok: false, message: "Paused.".into(), paused: true });
        }
    }

    /// Answer a question or approval card. `shown` is what the feed says was answered.
    pub fn answer_request(&mut self, id: &str, answer: Answer, shown: String) {
        let r = match (self.open_run(), &self.workspace) {
            (Some(run), _) => run.answer_as(id, &answer, &shown),
            (None, Some(ws)) => {
                // The question, taken before it's answered: whoever asked may remove it right after.
                let inbox = Inbox::new(ws.inbox_dir());
                let question = inbox.pending().into_iter().find(|r| r.id == id);
                inbox.answer(id, &answer).and_then(|()| question.map_or(Ok(()), |q| feed::record_answer(ws, &q, &shown)))
            }
            _ => return,
        };
        if let Err(e) = r {
            self.toast(e.message, true);
            return;
        }
        feed::answered(&mut self.state.feed, id, &shown);
        self.state.answers.remove(id);
        if !self.state.feed.iter().any(|f| matches!(f, FeedItem::Ask { answer: None, .. }))
            && let Some(ws) = &self.workspace
        {
            self.asking.remove(&ws.root);
        }
    }

    /// Every run's events: the open project's go to the screen (each run keeps its own
    /// project's feed). Queued runs start as others finish.
    pub fn poll_run(&mut self) {
        self.runs.set_limit(self.settings.build.parallel);
        let events = self.runs.poll(&self.hub);
        if events.is_empty() {
            return;
        }
        let open = self.workspace.as_ref().map(|w| w.root.clone());
        let mut finished = Vec::new();
        for (root, e) in &events {
            if open.as_ref() == Some(root) {
                apply(&mut self.state.feed, e);
            }
            // The run saves its usage at each agent turn and when it ends; read it again then.
            if matches!(e, RunEvent::Ask(_)) {
                self.asking.insert(root.clone());
                self.attention = true;
            }
            let clock = self.usage.entry(root.clone()).or_default();
            match e {
                RunEvent::Finished { .. } => {
                    self.asking.remove(root);
                    clock.saved_again(root, false);
                    finished.push(root.clone());
                }
                RunEvent::Agent(AgentEvent::TurnDone { input_tokens, output_tokens, cost_usd, cost_is_estimate, .. }) => {
                    clock.saved_again(root, true);
                    self.session_usage.add_turn(*input_tokens, *output_tokens, *cost_usd, *cost_is_estimate);
                }
                // A run's first event is its first step: the clock starts there.
                _ if !clock.working() => clock.saved_again(root, true),
                _ => {}
            }
        }
        if events.iter().any(|(root, _)| open.as_ref() == Some(root)) {
            self.refresh_side_panel();
        }
        if finished.is_empty() {
            return;
        }
        self.refresh_projects();
        for root in finished {
            // Every note of a finished run was read or goes next: none can be taken back now.
            self.drafts.retain(|_, d| d.root != root);
            // Notes the builder didn't get to (it finished, or "Send now" stopped it) go next.
            let left = self.runs.get(&root).map(RebuildRun::take_notes).unwrap_or_default();
            let join = |part: fn(&Note) -> &str| left.iter().map(part).collect::<Vec<_>>().join("\n\n");
            let (message, shown) = (join(|n| &n.text), join(|n| &n.shown));
            if open.as_ref() == Some(&root) {
                if let Some(ws) = self.workspace.as_mut() {
                    let _ = ws.reload();
                }
                if !left.is_empty() {
                    if matches!(self.state.feed.last(), Some(FeedItem::Paused)) {
                        self.state.feed.pop();
                    }
                    self.state.feed.push(FeedItem::User(shown.clone()));
                    self.resume(Some(message), Some(shown));
                }
            } else if !left.is_empty() {
                // Another project's notes start its next run in the background.
                let Ok(ws) = Workspace::open(&root) else { continue };
                let Some(backend) = self.builder_backend(ws.manifest.builder.as_deref()) else { continue };
                let opts = self.run_options(Some(backend), Some(message), Some(shown));
                if let Err(e) = self.launch(ws, opts) {
                    self.toast(e.message, true);
                }
            }
        }
    }

    pub fn preview_url(&self) -> Option<String> {
        self.open_run().and_then(RebuildRun::preview_url).or_else(|| self.preview.clone())
    }

    /// Open the built website in the browser (starting a local preview with project_preview if
    /// needed).
    pub fn open_preview(&mut self, ctx: &egui::Context) {
        if let Some(url) = self.preview_url() {
            ctx.open_url(egui::OpenUrl::new_tab(url));
        } else if let Some(ws) = &self.workspace {
            let root = ws.root.clone();
            self.act("project_preview", serde_json::json!({"project": root}), tr("Preview the website"));
        }
    }

    /// Pictures of the original: straight into the open project, else kept with the draft until
    /// Start.
    pub fn add_pictures(&mut self, files: Vec<PathBuf>) {
        if files.is_empty() {
            return;
        }
        if self.state.screen == Screen::Project
            && let Some(ws) = self.workspace.clone()
        {
            // Copied on a worker; `pictures_added` says how it went.
            self.jobs.spawn(tr("Add pictures"), false, move |_| Ok(Done::PicturesAdded(ws.add_references(&files).map_err(|e| e.message))));
            return;
        }
        let d = &mut self.state.make.pictures;
        for f in files {
            if craft_anything_engine::workspace::is_picture(&f) && !d.contains(&f) {
                d.push(f);
            }
        }
    }

    pub(crate) fn pictures_added(&mut self, added: Result<usize, String>) {
        match added {
            Ok(0) => self.toast(tr("Those aren't pictures we can use (PNG, JPEG, WebP or GIF, up to 20 MB)."), true),
            Ok(n) => self.toast(trf("Added {n} picture(s). The builder uses them from your next change.", &[("n", &n.to_string())]), false),
            Err(e) => self.toast(format!("{} {}", tr("Couldn't add the pictures:"), e), true),
        }
        self.refresh_side_panel();
    }

    /// Start a program this project built, in its own window (only ever on the person's click).
    /// Choose what the builder's questions get in this project. Shown at once; saved by the tool.
    pub fn set_questions(&mut self, root: &Path, mode: craft_anything_engine::workspace::Questions) {
        if let Some(ws) = self.workspace.as_mut().filter(|w| w.root == root) {
            ws.manifest.questions = Some(mode);
        }
        self.act("project_questions_set", serde_json::json!({"project": root, "mode": mode}), tr("Choose what the builder's questions get"));
    }

    /// Start the finished game or app (project_play: its own window, no console behind it).
    pub fn play(&mut self, ws: &Workspace) {
        self.act("project_play", serde_json::json!({"project": ws.root}), tr("Start it"));
    }

    pub fn thumb_ready(&mut self, path: PathBuf, image: Option<egui::TextureHandle>) {
        self.thumbs.insert(path, image.map_or(Thumb::Missing, Thumb::Ready));
    }

    /// A screenshot thumbnail (the top of the page), read and decoded on a worker the first time.
    /// Kept for the open project only (see `tick`).
    fn thumb(&mut self, ctx: &egui::Context, path: &Path) -> Thumb {
        if let Some(t) = self.thumbs.get(path) {
            return t.clone();
        }
        self.thumbs.insert(path.to_path_buf(), Thumb::Loading);
        let (p, ctx) = (path.to_path_buf(), ctx.clone());
        self.jobs.spawn("Load a screenshot", false, move |_| {
            use craft_anything_engine::tools::web_common::{crop, decode_png, resize};
            let image = std::fs::read(&p).ok().and_then(|b| decode_png(&b).ok()).map(|img| {
                let top = crop(&img, img.width, img.height.min(THUMB_TOP));
                // Shown at most half the feed wide: twice that is sharp on a high-density screen.
                let top = if top.width > THUMB_WIDTH { resize(&top, THUMB_WIDTH, (top.height * THUMB_WIDTH / top.width).max(1)) } else { top };
                let ci = egui::ColorImage::from_rgba_unmultiplied([top.width as usize, top.height as usize], &top.rgba);
                ctx.load_texture(p.display().to_string(), ci, egui::TextureOptions::LINEAR)
            });
            Ok(Done::Thumb { path: p, image })
        });
        Thumb::Loading
    }
}

/// How much of a page's screenshot a thumbnail shows (from the top), and its widest, in pixels.
const THUMB_TOP: u32 = 1800;
const THUMB_WIDTH: u32 = 720;

/// A screenshot thumbnail: being read, ready, or not there (no file, or not a PNG we can read).
#[derive(Clone)]
pub enum Thumb {
    Loading,
    Ready(egui::TextureHandle),
    Missing,
}

/// The open project's checklist, if the builder made one.
fn plan(feed: &[FeedItem]) -> Option<&[PlanStep]> {
    feed.iter().find_map(|i| if let FeedItem::Plan(p) = i { Some(p.as_slice()) } else { None })
}

/// The builder's checklist, pinned above the prompt box: what's done, what it's on now, what's
/// next, and while it works how long it has been at it. Shown while it works, and afterwards only
/// if something was left undone.
fn checklist(ui: &mut Ui, steps: &[PlanStep], t: &Tokens, began: Option<std::time::Instant>) {
    let done = steps.iter().filter(|s| s.status == PlanStatus::Done).count();
    widgets::card(t).inner_margin(Margin::symmetric(16, 12)).show(ui, |ui| {
        ui.set_width(ui.available_width());
        ui.horizontal(|ui| {
            widgets::caption(ui, "Plan");
            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                if let Some(b) = began {
                    ui.label(RichText::new(crate::usage::duration_words(b.elapsed())).font(theme::mono(12.0)).color(t.text_faint));
                    ui.add(egui::Spinner::new().size(12.0).color(t.accent));
                    ui.ctx().request_repaint_after(std::time::Duration::from_secs(1));
                }
                ui.label(
                    RichText::new(trf("{done} of {all} done", &[("done", &done.to_string()), ("all", &steps.len().to_string())]))
                        .font(theme::mono(12.0))
                        .color(t.text_faint),
                );
            });
        });
        ui.add_space(6.0);
        for s in steps {
            ui.horizontal(|ui| {
                let (r, _) = ui.allocate_exact_size(Vec2::splat(18.0), egui::Sense::hover());
                match s.status {
                    PlanStatus::Done => {
                        ui.painter().circle_filled(r.center(), 7.0, t.success);
                        icons::paint(ui, r.shrink(4.0), "check", 10.0, t.canvas);
                    }
                    PlanStatus::Doing => {
                        ui.painter().circle_stroke(r.center(), 6.5, egui::Stroke::new(1.5, t.accent));
                        ui.painter().circle_filled(r.center(), 3.0, t.accent);
                    }
                    PlanStatus::Todo => {
                        ui.painter().circle_stroke(r.center(), 6.5, egui::Stroke::new(1.0, t.field_border));
                    }
                }
                let text = RichText::new(&s.text).size(theme::BODY);
                let text = match s.status {
                    PlanStatus::Done => text.color(t.text_faint).strikethrough(),
                    PlanStatus::Doing => text.color(t.text).strong(),
                    PlanStatus::Todo => text.color(t.text_dim),
                };
                ui.add(egui::Label::new(text).wrap());
            });
        }
    });
}

/// What the Project screen shows from the project's files, read on a worker when the project
/// opens and as its run reports (at most once a second), never while drawing: a slow or offline
/// drive must not freeze the window.
#[derive(Debug, Clone, Default)]
pub struct Facts {
    pub root: PathBuf,
    /// A built website to open.
    pub site: bool,
    /// A built program to start.
    pub program: bool,
    /// Pictures of the original to match.
    pub references: usize,
    /// Generated assets: how many, what they cost.
    pub assets: (usize, f64),
    /// The builder's open questions, most important first.
    pub open_questions: Vec<String>,
}

impl Facts {
    pub fn read(ws: &Workspace, godot: Option<&Path>) -> Facts {
        let dir = ws.app_dir();
        let a = ws.assets();
        Facts {
            root: ws.root.clone(),
            site: rebuild::site_dir(&dir).is_some(),
            program: rebuild::launch(&dir, godot).is_some(),
            references: ws.references().len(),
            // Summed from +0.0: an empty f64 `sum()` is -0.0, shown as "$-0.00".
            assets: (a.len(), a.iter().fold(0.0, |s, x| s + x.cost_usd)),
            open_questions: craft_anything_ai::rebuild::self_check::open_questions(ws).into_iter().map(|u| u.question).collect(),
        }
    }
}

/// Reading [`Facts`]: whether it's wanted again, the read under way, and when the last began.
#[derive(Debug, Default)]
pub struct FactsReader {
    wanted: bool,
    job: Option<u64>,
    at: Option<std::time::Instant>,
}

impl CraftApp {
    /// Read the open project's [`Facts`] again soon (on a worker).
    pub fn refresh_side_panel(&mut self) {
        self.facts_reader.wanted = true;
    }

    /// Start a wanted read when none is under way and the last began a second ago or more.
    pub(crate) fn read_facts(&mut self, ctx: &egui::Context) {
        const EVERY: std::time::Duration = std::time::Duration::from_secs(1);
        let r = &mut self.facts_reader;
        let Some(ws) = self.workspace.clone().filter(|_| r.wanted && r.job.is_none()) else { return };
        if let Some(wait) = r.at.map(|at| EVERY.saturating_sub(at.elapsed())).filter(|w| !w.is_zero()) {
            ctx.request_repaint_after(wait);
            return;
        }
        let godot = self.game_engines.as_ref().and_then(|i| i.best(craft_anything_engines::game::Builder::Godot)).map(|i| i.program.clone());
        r.wanted = false;
        r.at = Some(std::time::Instant::now());
        r.job = Some(self.jobs.spawn("Read the project", false, move |_| Ok(Done::Facts(Facts::read(&ws, godot.as_deref())))));
    }

    pub(crate) fn facts_read(&mut self, job: u64, facts: Option<Facts>) {
        if self.facts_reader.job == Some(job) {
            self.facts_reader.job = None;
        }
        if let Some(f) = facts.filter(|f| self.workspace.as_ref().is_some_and(|w| w.root == f.root)) {
            self.facts = f;
        }
    }

    /// What "Raise the budget" adds: the default budget from Settings (or $5 when that is 0).
    pub(crate) fn asset_budget_step(&self) -> f64 {
        let b = self.settings.assets.budget();
        if b > 0.0 { b } else { craft_anything_engine::workspace::ASSET_BUDGET_USD }
    }

    /// Give the open project another [`Self::asset_budget_step`] for generated assets, through
    /// the project_assets_budget tool.
    fn raise_asset_budget(&mut self) {
        let step = self.asset_budget_step();
        let Some(ws) = self.workspace.as_mut() else { return };
        // The builder's tools may have changed the manifest; start from what's on disk.
        let _ = ws.reload();
        let params = serde_json::json!({"project": ws.root, "budget_usd": (ws.manifest.asset_budget_usd + step).min(10_000.0)});
        self.act("project_assets_budget", params, tr("Raise the asset budget"));
    }

    /// After project_assets_budget or project_assets_allow: show the project's new settings.
    pub(crate) fn assets_changed(&mut self) {
        if let Some(ws) = self.workspace.as_mut() {
            let _ = ws.reload();
        }
        self.refresh_side_panel();
    }
}

/// A game project's generated-assets switch, and "7 · $2.10 of $5.00" once it's on or assets were made.
fn asset_line(app: &mut CraftApp, ui: &mut Ui, ws: &Workspace) {
    let t = Tokens::get(ui.ctx());
    if craft_anything_engines::game::Builder::from_stack(&ws.manifest.stack).is_none() {
        return;
    }
    widgets::caption(ui, "Generated assets");
    ui.add_space(4.0);
    crate::engine_ui::assets_toggle(app, ui, ws.manifest.generate_assets);
    let (n, spent) = app.facts.assets;
    if !ws.manifest.generate_assets && n == 0 {
        ui.add_space(12.0);
        return;
    }
    ui.add_space(6.0);
    let budget = ws.manifest.asset_budget_usd;
    let amount = trf("{n} · ${spent} of ${budget}", &[("n", &n.to_string()), ("spent", &format!("{spent:.2}")), ("budget", &format!("{budget:.2}"))]);
    ui.label(RichText::new(amount).font(theme::mono(12.5)).color(if spent >= budget { t.warning } else { t.text_dim }));
    let step = craft_anything_engines::assets::usd(app.asset_budget_step());
    if widgets::link(ui, &trf("Raise the budget by {amount}", &[("amount", &step)])).clicked() {
        app.raise_asset_budget();
    }
    ui.add_space(12.0);
}

/// Which step is current, from the feed and the project's status, and whether it's being worked
/// on now (a paused or interrupted build shows where it stopped, not nothing).
fn current_step(app: &CraftApp, ws: &Workspace) -> Option<(Step, bool)> {
    if ws.manifest.status == Status::Ready {
        return Some((Step::Done, false));
    }
    let last = app.state.feed.iter().rev().find_map(|i| if let FeedItem::Step { step, .. } = i { Some(*step) } else { None })?;
    Some((last, app.running()))
}

// ---- screen -----------------------------------------------------------------------------------

/// The side panel's width, and the room the screen needs to keep it beside the feed.
const SIDE_W: f32 = 300.0;
const SIDE_BESIDE: f32 = 860.0;

pub fn show(app: &mut CraftApp, ui: &mut Ui) {
    let Some(ws) = app.workspace.clone() else {
        app.state.screen = Screen::Home;
        return;
    };
    // What its builds took and used, saved in the project: read once when it's first shown.
    app.usage.entry(ws.root.clone()).or_insert_with(|| crate::usage::ProjectClock::load(&ws.root));
    let t = Tokens::get(ui.ctx());
    // The project's details sit on the right, where there's room for them beside a readable
    // feed; in a narrow window they fold into the top of the feed instead.
    let beside = ui.available_width() >= SIDE_BESIDE;
    if beside {
        egui::Panel::right("project-side")
            .exact_size(SIDE_W)
            .resizable(false)
            .frame(egui::Frame::new().fill(t.canvas).inner_margin(Margin::same(20)))
            .show(ui, |ui| egui::ScrollArea::vertical().show(ui, |ui| side(app, ui, &ws)));
    }
    egui::CentralPanel::default().frame(egui::Frame::new().fill(t.canvas).inner_margin(chat::PANE_MARGIN)).show(ui, |ui| {
        let width = ui.available_width();
        let max_w = width.min(720.0);
        let pad = ((width - max_w) / 2.0).max(0.0);
        // The feed gets what the prompt box leaves; the box grows with its text, so its height
        // is measured each frame and used on the next.
        let comp_id = ui.id().with("project-composer-h");
        let comp_h = ui.data(|d| d.get_temp::<f32>(comp_id)).unwrap_or(110.0);
        let rest = Vec2::new(width, (ui.available_height() - comp_h - chat::COMPOSER_GAP).max(40.0));
        ui.allocate_ui_with_layout(rest, egui::Layout::top_down(egui::Align::Min), |ui| {
            ui.set_min_height(rest.y);
            egui::ScrollArea::vertical().auto_shrink([false, false]).stick_to_bottom(true).show(ui, |ui| {
                ui.horizontal(|ui| {
                    ui.add_space(pad);
                    ui.vertical(|ui| {
                        ui.set_width(max_w);
                        if !beside {
                            egui::CollapsingHeader::new(RichText::new(tr("Project details")).font(theme::semibold(theme::BODY)))
                                .id_salt("project-details")
                                .icon(widgets::disclosure_icon)
                                .show(ui, |ui| side(app, ui, &ws));
                            ui.add_space(chat::MESSAGE_GAP);
                        }
                        feed(app, ui, &ws);
                    });
                });
            });
        });
        ui.add_space(chat::COMPOSER_GAP);
        let r = ui.horizontal(|ui| {
            ui.add_space(pad);
            ui.vertical(|ui| composer(app, ui, max_w, &t));
        });
        chat::remember_composer_height(ui, comp_id, comp_h, r.response.rect.height());
    });
}

fn side(app: &mut CraftApp, ui: &mut Ui, ws: &Workspace) {
    let t = Tokens::get(ui.ctx());
    ui.add_space(10.0);
    let m = &ws.manifest;
    widgets::card(&t).show(ui, |ui| {
        ui.set_width(ui.available_width());
        ui.horizontal(|ui| {
            let (rect, _) = ui.allocate_exact_size(Vec2::splat(48.0), egui::Sense::hover());
            ui.painter().rect_filled(rect, t.radius, t.accent_soft);
            icons::paint(ui, rect, make::project_icon(m), 24.0, t.accent_ink);
            ui.vertical(|ui| {
                ui.add(egui::Label::new(theme::heading(&m.name, theme::CARD)).truncate());
                let (label, fg, bg) = make::status_shown(app, ws, &t);
                widgets::pill(ui, label, fg, bg);
            });
        });
        ui.add_space(10.0);
        if !matches!(m.target, TargetRef::None) {
            widgets::caption(ui, "From");
            ui.add(egui::Label::new(RichText::new(m.target.label()).color(t.text_dim)).truncate());
            ui.add_space(6.0);
        }
        if !m.stack.is_empty() && !app.beginner() {
            widgets::caption(ui, "Built with");
            ui.label(RichText::new(&m.stack).color(t.text_dim));
        }
    });
    ui.add_space(14.0);
    steps(app, ui, ws);
    ui.add_space(14.0);
    open_questions(app, ui);
    asset_line(app, ui, ws);
    if outcome(app).is_some() {
        outcome_button(app, ui, ws, 32.0, 12.5);
        ui.add_space(6.0);
    }
    // Pictures of the original: the look the builder matches (websites are photographed for it).
    if !matches!(m.target, TargetRef::Website { .. }) {
        let n = app.facts.references;
        if widgets::secondary(ui, Some("paperclip"), "Add pictures of the original")
            .on_hover_text(tr("Screenshots of how it should look. The builder opens each one and matches it."))
            .clicked()
        {
            app.pick(crate::Pick::Pictures);
        }
        let note = if n == 0 { tr("None yet. Screenshots help it look right.") } else { trf("{n} picture(s) to match.", &[("n", &n.to_string())]) };
        ui.label(RichText::new(note).color(Tokens::get(ui.ctx()).text_dim).size(theme::SMALL));
        ui.add_space(8.0);
    }
    ui.horizontal_wrapped(|ui| {
        if widgets::secondary(ui, Some("folder-open"), "Open folder").clicked() {
            open_folder(app, ws);
        }
        if matches!(outcome(app), Some(Outcome::Program))
            && widgets::secondary(ui, Some("pin"), "Pin this build").on_hover_text(tr("Keep this version in the sidebar to open any time.")).clicked()
        {
            app.ask_pin(&ws.root);
        }
        crate::manage::buttons(app, ui, ws);
        if !app.beginner()
            && widgets::secondary(ui, Some("microscope"), "Open in the workbench").on_hover_text(tr("The full toolset, evidence and logs.")).clicked()
        {
            app.state.screen = Screen::Workbench;
        }
    });
}

/// How to see what was made: open the built site, or start the built program.
enum Outcome {
    Site,
    /// A program to start (a Godot project opens in Godot).
    Program,
}

fn outcome(app: &CraftApp) -> Option<Outcome> {
    if app.preview_url().is_some() || app.facts.site {
        return Some(Outcome::Site);
    }
    // Not mid-build: a running program locks its file, so the next build couldn't replace it.
    (!app.running() && app.facts.program).then_some(Outcome::Program)
}

/// The words for what was made, from its kind, so a game never gets website examples.
fn outcome_words(kinds: &KindRegistry, ws: &Workspace) -> KindWords {
    let m = &ws.manifest;
    kinds.detect(&m.request, &m.target, &m.stack).map_or_else(|| AppKind.words(), |k| k.words())
}

/// The button that shows the result ("Play the game"); a program starts only on this click.
fn outcome_button(app: &mut CraftApp, ui: &mut Ui, ws: &Workspace, height: f32, text: f32) {
    let Some(o) = outcome(app) else { return };
    let w = outcome_words(&app.kinds, ws);
    if widgets::primary_sized(ui, Some(w.icon), w.button, true, height, text).clicked() {
        match o {
            Outcome::Site => app.open_preview(&ui.ctx().clone()),
            Outcome::Program => app.play(ws),
        }
    }
}

/// Show a folder in the system file manager (a `file://` URL would open the browser instead).
fn open_folder(app: &mut CraftApp, ws: &Workspace) {
    app.act("project_open_folder", serde_json::json!({"project": ws.root}), tr("Open the folder"));
}

/// What the builder couldn't find out about the original, so the person can answer it in a
/// follow-up; nothing when it has no open questions.
fn open_questions(app: &CraftApp, ui: &mut Ui) {
    if app.facts.open_questions.is_empty() {
        return;
    }
    let t = Tokens::get(ui.ctx());
    widgets::card(&t).inner_margin(Margin::symmetric(16, 14)).show(ui, |ui| {
        ui.set_width(ui.available_width());
        widgets::caption(ui, "Open questions");
        ui.add_space(6.0);
        const SHOWN: usize = 5;
        for q in app.facts.open_questions.iter().take(SHOWN) {
            ui.horizontal_wrapped(|ui| {
                icons::show(ui, "info", 14.0, t.text_dim);
                ui.add(egui::Label::new(RichText::new(q).size(theme::SMALL).color(t.text)).wrap());
            });
        }
        if app.facts.open_questions.len() > SHOWN {
            let more = trf("and {n} more", &[("n", &(app.facts.open_questions.len() - SHOWN).to_string())]);
            ui.label(RichText::new(more).size(theme::SMALL).color(t.text_dim));
        }
        ui.add_space(4.0);
        ui.label(RichText::new(tr("Answer any of them in a message below.")).size(theme::SMALL).color(t.text_dim));
    });
    ui.add_space(14.0);
}

fn steps(app: &CraftApp, ui: &mut Ui, ws: &Workspace) {
    let t = Tokens::get(ui.ctx());
    let current = current_step(app, ws);
    let live = current.is_some_and(|(_, live)| live);
    let idx = current.and_then(|(c, _)| Step::ALL.iter().position(|s| *s == c));
    widgets::card(&t).inner_margin(Margin::symmetric(16, 14)).show(ui, |ui| {
        ui.set_width(ui.available_width());
        widgets::caption(ui, "Progress");
        ui.add_space(8.0);
        let row_h = 38.0;
        for (i, s) in Step::ALL.iter().enumerate() {
            // `here`: where a paused or interrupted build stopped.
            let (done, now, here) = match idx {
                Some(c) if *s == Step::Done && c == i => (true, false, false),
                Some(c) => (i < c, i == c && live, i == c && !live),
                None => (false, false, false),
            };
            let (row, resp) = ui.allocate_exact_size(Vec2::new(ui.available_width(), row_h), egui::Sense::hover());
            let marker = egui::Rect::from_min_size(egui::pos2(row.left(), row.center().y - 12.0), Vec2::splat(24.0));
            // The line to the next step: ink once this step is done, a hairline before that.
            if i + 1 < Step::ALL.len() {
                let x = marker.center().x;
                let col = if done { t.text_dim } else { t.separator };
                ui.painter().vline(x, marker.bottom()..=row.bottom() + 12.0, egui::Stroke::new(1.0, col));
            }
            let number = format!("{:02}", i + 1);
            let round = marker.width() / 2.0;
            if done {
                ui.painter().rect_filled(marker, round, t.text);
                icons::paint(ui, marker.shrink(5.0), "check", 14.0, t.canvas);
            } else if now {
                ui.painter().rect_filled(marker, round, t.accent);
                let g = widgets::label_galley(ui, &number, 11.0, t.on_accent);
                ui.painter().galley_with_override_text_color(marker.center() - g.size() / 2.0, g, t.on_accent);
                let pulse = (ui.input(|i| i.time) as f32 * 2.5).sin().abs();
                ui.painter().rect_stroke(
                    marker.expand(2.0 + pulse * 3.0),
                    round + 2.0 + pulse * 3.0,
                    egui::Stroke::new(1.0, t.accent.gamma_multiply(0.6 - pulse * 0.4)),
                    egui::StrokeKind::Outside,
                );
                widgets::animate(ui, widgets::FRAME);
            } else if here {
                ui.painter().rect(marker, round, t.card, egui::Stroke::new(1.5, t.accent), egui::StrokeKind::Inside);
                let g = widgets::label_galley(ui, &number, 11.0, t.accent_ink);
                ui.painter().galley_with_override_text_color(marker.center() - g.size() / 2.0, g, t.accent_ink);
            } else {
                ui.painter().rect(marker, round, t.card, egui::Stroke::new(1.0, t.field_border), egui::StrokeKind::Inside);
                let g = widgets::label_galley(ui, &number, 11.0, t.text_faint);
                ui.painter().galley_with_override_text_color(marker.center() - g.size() / 2.0, g, t.text_faint);
            }
            let x = marker.right() + 12.0;
            let (font, col) = if now || here {
                (theme::semibold(theme::SMALL), t.text)
            } else if done {
                (theme::medium(theme::SMALL), t.text)
            } else {
                (theme::medium(theme::SMALL), t.text_faint)
            };
            ui.painter().text(egui::pos2(x, row.center().y), egui::Align2::LEFT_CENTER, tr(s.label()), font, col);
            // State in words too, so it doesn't rely on colour.
            let state = if now {
                tr("Now")
            } else if here {
                tr("Stopped here")
            } else if done {
                tr("Done")
            } else {
                String::new()
            };
            // Painted, so named for screen readers: "Build: Now".
            let name = if state.is_empty() { tr(s.label()) } else { format!("{}: {state}", tr(s.label())) };
            resp.widget_info(|| egui::WidgetInfo::labeled(egui::WidgetType::Label, true, &name));
            if !state.is_empty() {
                let ink = if now || here { t.accent_ink } else { t.text_faint };
                let g = widgets::label_galley(ui, &state, theme::CAPTION, ink);
                let pos = egui::pos2(row.right() - g.size().x, row.center().y - g.size().y / 2.0);
                ui.painter().galley_with_override_text_color(pos, g, ink);
            }
        }
        // How long it has worked and what the AI has used, live while it builds.
        if let Some(u) = app.usage.get(&ws.root).filter(|u| u.working() || !u.elapsed().is_zero()) {
            ui.add_space(14.0);
            let tip = || crate::usage::explain(&u.saved, "Every build of this project.");
            stat_row(ui, "Time spent", &crate::usage::duration_words(u.elapsed()));
            if u.saved.priced {
                let cost = crate::usage::cost_stat(&u.saved);
                stat_row(ui, cost.label, &cost.value).on_hover_text(tip());
                // Said outright, not only on hover: on a subscription this isn't what they pay.
                if let Some(note) = cost.note {
                    ui.add(egui::Label::new(RichText::new(tr(note)).color(Tokens::get(ui.ctx()).text_faint).size(theme::CAPTION)).wrap());
                }
            }
            if u.saved.tokens() > 0 {
                stat_row(ui, "Tokens", &crate::usage::tokens_short(u.saved.tokens())).on_hover_text(tip());
            }
            if u.working() {
                ui.ctx().request_repaint_after(std::time::Duration::from_secs(1));
            }
        }
        if let Some(sim) = ws.manifest.checks.last().and_then(|c| c.similarity) {
            ui.add_space(14.0);
            stat_row(ui, "Likeness", &format!("{sim:.0}%"));
            let (bar, _) = ui.allocate_exact_size(Vec2::new(ui.available_width(), 4.0), egui::Sense::hover());
            ui.painter().rect_filled(bar, 2.0, t.separator);
            let filled = egui::Rect::from_min_size(bar.min, Vec2::new(bar.width() * (sim / 100.0).clamp(0.0, 1.0) as f32, bar.height()));
            ui.painter().rect_filled(filled, 2.0, t.accent);
        }
    });
}

/// A caption on the left and its value on the right.
fn stat_row(ui: &mut Ui, label: &str, value: &str) -> egui::Response {
    let t = Tokens::get(ui.ctx());
    ui.horizontal(|ui| {
        widgets::caption(ui, label);
        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
            ui.label(RichText::new(value).font(theme::mono(13.0)).color(t.text));
        });
    })
    .response
}

fn feed(app: &mut CraftApp, ui: &mut Ui, ws: &Workspace) {
    let t = Tokens::get(ui.ctx());
    let ctx = ui.ctx().clone();
    let mut answers: Vec<(String, Answer, String)> = Vec::new();
    let mut retry = false;
    // Lent out while it's drawn (the cards need the app), not copied every frame; a part that
    // fails to draw still gives it back.
    let items = std::mem::take(&mut app.state.feed);
    let drawn = crate::guard("feed", || draw_items(app, ui, ws, &items, &ctx, &mut answers, &mut retry));
    app.state.feed = items;
    if drawn.is_none() {
        ui.colored_label(t.danger, tr("Part of this screen hit a bug and was skipped. Your work is safe."));
    }
    if can_continue(app, ws) {
        continue_card(app, ui, ws);
    }
    // The finish line: a big, plain prompt to try what was made.
    if !app.running() && matches!(ws.manifest.status, Status::Ready) && outcome(app).is_some() {
        let w = outcome_words(&app.kinds, ws);
        widgets::card(&t).inner_margin(Margin::same(18)).show(ui, |ui| {
            ui.set_width(ui.available_width());
            ui.horizontal(|ui| {
                let (rect, _) = ui.allocate_exact_size(Vec2::splat(44.0), egui::Sense::hover());
                ui.painter().rect_filled(rect, t.radius, t.accent_soft);
                icons::paint(ui, rect, w.icon, 22.0, t.accent_ink);
                ui.vertical(|ui| {
                    ui.label(theme::heading(tr(w.ready), theme::CARD));
                    ui.label(RichText::new(tr("Try it out, then ask below for any changes.")).color(t.text_dim));
                });
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| outcome_button(app, ui, ws, 44.0, 13.0));
            });
        });
        ui.add_space(10.0);
    }
    let items = &app.state.feed;
    // With a plan pinned below, it shows the work and the clock; one progress display, not two.
    let pinned = plan(items).is_some();
    let status_row =
        app.running() && !pinned && !matches!(items.last(), Some(FeedItem::Agent { streaming: true, .. }) | Some(FeedItem::Ask { answer: None, .. }));
    if status_row {
        // What it's on (the latest step) and how much it has done since, so progress is visible
        // even in Simple mode where the tool-by-tool work is hidden.
        let step = items.iter().rposition(|i| matches!(i, FeedItem::Step { .. }));
        // The builder's own words for the step it's on, else the workflow's stage.
        let doing = plan(items).and_then(|p| p.iter().find(|s| s.status == PlanStatus::Doing)).map(|s| s.doing.as_str());
        let title = doing.or_else(|| {
            step.and_then(|s| match &items[s] {
                FeedItem::Step { text, .. } => Some(text.as_str()),
                _ => None,
            })
        });
        let done: usize = items[step.map_or(0, |s| s + 1)..]
            .iter()
            .map(|i| match i {
                FeedItem::Work { tools, .. } => tools.iter().filter(|(_, d)| d.is_some()).count(),
                _ => 0,
            })
            .sum();
        // The action under way: the command or file it's on, not only how many went before.
        let now = app.open_run().map(RebuildRun::activity_now);
        let detail =
            [now.as_ref().and_then(|n| now_words(app, n)), (done > 0).then(|| crate::i18n::trf("{n} actions done so far", &[("n", &done.to_string())]))]
                .into_iter()
                .flatten()
                .collect::<Vec<_>>()
                .join("  ·  ");
        let (began, quiet) = app.open_run().map_or((None, None), |r| (Some(r.started()), Some(r.quiet_for())));
        widgets::working_since(ui, title.unwrap_or("Working on it"), (!detail.is_empty()).then_some(detail.as_str()), began, quiet);
    }
    run_details(app, ui, status_row);
    for (id, a, shown) in answers {
        app.answer_request(&id, a, shown);
    }
    if retry {
        app.follow_up(None);
    }
}

/// How much of a command or a path fits on the status line; the details have the rest.
const NOW_LENGTH: usize = 90;

/// "Now: Running cargo test (42s)", or what finished last between actions.
fn now_words(app: &CraftApp, now: &ActivityNow) -> Option<String> {
    let words = |a: &Action| {
        let registry = app.engine.registry();
        let w = a.words_with(|tool| registry.canonical(tool).and_then(|id| registry.get(id)).map(|s| s.title.to_string()));
        match w.char_indices().nth(NOW_LENGTH) {
            Some((end, _)) => format!("{}…", w.get(..end).unwrap_or_default()),
            None => w,
        }
    };
    match (&now.current, &now.last) {
        (Some((a, took)), _) => {
            let line = trf("Now: {what} ({time})", &[("what", &words(a)), ("time", &crate::usage::duration_words(*took))]);
            Some(if now.others > 0 { trf("{line}, and {n} more", &[("line", &line), ("n", &now.others.to_string())]) } else { line })
        }
        (None, Some(a)) => Some(trf("Last: {what}", &[("what", &words(a))])),
        (None, None) => None,
    }
}

/// The run's activity, folded away until it's wanted: its latest lines as they arrive, and the
/// whole log to open. Inside the feed's scroll area, so it can never push the prompt box away.
/// `status_row`: the row above already says what it's on.
fn run_details(app: &mut CraftApp, ui: &mut Ui, status_row: bool) {
    const LINE: f32 = 18.0;
    const MOST_SHOWN: f32 = 260.0;
    let t = Tokens::get(ui.ctx());
    let running = app.running();
    let Some(run) = app.open_run() else { return };
    let count = run.activity_len();
    if count == 0 {
        return;
    }
    let title = if !running {
        tr("What happened in this build")
    } else if status_row {
        tr("More detail")
    } else {
        now_words(app, &run.activity_now()).unwrap_or_else(|| tr("More detail"))
    };
    let log = run.activity_log();
    let mut open_log = false;
    egui::CollapsingHeader::new(RichText::new(title).color(t.text_dim).size(theme::CAPTION)).id_salt("run_details").icon(widgets::disclosure_icon).show(
        ui,
        |ui| {
            widgets::card(&t).inner_margin(Margin::symmetric(10, 8)).show(ui, |ui| {
                ui.set_width(ui.available_width());
                // The rows are exactly this tall, or the scroll area miscounts them.
                ui.spacing_mut().item_spacing.y = 0.0;
                ui.spacing_mut().interact_size.y = LINE;
                egui::ScrollArea::vertical().id_salt("run_details_lines").max_height(MOST_SHOWN).auto_shrink([false, true]).stick_to_bottom(true).show_rows(
                    ui,
                    LINE,
                    count,
                    |ui, range| {
                        for line in run.activity_lines(range) {
                            let (colour, words) = match line.kind {
                                LineKind::Failed | LineKind::Problem => (t.warning, t.text),
                                LineKind::Done => (t.success, t.text_dim),
                                LineKind::Stage => (t.accent_ink, t.text),
                                LineKind::Started | LineKind::Said => (t.text_dim, t.text),
                                LineKind::Note | LineKind::Output => (t.text_faint, t.text_dim),
                            };
                            ui.horizontal(|ui| {
                                ui.set_height(LINE);
                                ui.label(RichText::new(crate::usage::duration_words(line.at)).font(theme::mono(theme::CAPTION)).color(t.text_faint));
                                ui.label(RichText::new(line.kind.tag()).font(theme::mono(theme::CAPTION)).color(colour));
                                ui.add(egui::Label::new(RichText::new(&line.text).font(theme::mono(theme::CAPTION)).color(words)).truncate())
                                    .on_hover_text(&line.text);
                            });
                        }
                    },
                );
            });
            ui.horizontal(|ui| {
                ui.label(RichText::new(tr("A command's output shows here when it finishes.")).color(t.text_faint).size(theme::CAPTION));
                open_log = widgets::open_log_button(ui, &log);
            });
        },
    );
    if running {
        ui.ctx().request_repaint_after(std::time::Duration::from_secs(1));
    }
    if open_log {
        app.open_log(&log);
    }
}

/// Each item of the feed, in order. Answers and "Try again" are collected, to act on afterwards.
fn draw_items(
    app: &mut CraftApp,
    ui: &mut Ui,
    ws: &Workspace,
    items: &[FeedItem],
    ctx: &egui::Context,
    answers: &mut Vec<(String, Answer, String)>,
    retry: &mut bool,
) {
    let t = Tokens::get(ui.ctx());
    let advanced = !app.beginner();
    // Questions about the build, among the items they were asked after.
    let mut next_asked = 0;
    let mut questions_up_to = |app: &mut CraftApp, ui: &mut Ui, end: usize| {
        while let Some(a) = app.asked.get_mut(&ws.root).and_then(|l| l.get_mut(next_asked)).filter(|a| a.after <= end) {
            ui.push_id(("asked", next_asked), |ui| crate::just_ask::card(ui, a, !advanced));
            next_asked += 1;
        }
    };
    for (i, item) in items.iter().enumerate() {
        questions_up_to(app, ui, i);
        ui.push_id(i, |ui| match item {
            FeedItem::User(text) => chat::user_bubble(ui, text, false),
            FeedItem::Step { text, .. } => chat::activity_row(ui, RichText::new(text).color(t.text_dim).size(theme::SMALL)),
            FeedItem::Paused => chat::activity_row(ui, RichText::new(tr("Paused.")).color(t.text_dim).size(theme::SMALL)),
            FeedItem::Agent { text, streaming } => {
                chat::bubble(&t, false, false).show(ui, |ui| {
                    ui.set_width(ui.available_width());
                    chat::rich_text(ui, text.trim(), !advanced);
                    if *streaming {
                        widgets::thinking(ui);
                    }
                });
            }
            // Tool-by-tool work is for Advanced mode; Simple mode shows the plain-words story.
            FeedItem::Work { tools, notes } if advanced => work(ui, tools, notes, advanced, &t),
            FeedItem::Work { .. } => {}
            // Pinned above the prompt box instead (see `checklist`).
            FeedItem::Plan(_) => {}
            FeedItem::Ask { request, answer } => {
                if let Some(a) = ask_card(app, ui, request, answer.as_deref()) {
                    answers.push(a);
                }
            }
            FeedItem::Check(c) => check_card(app, ui, ctx, ws, c),
            FeedItem::Error { message, remediation, log } => {
                egui::Frame::new()
                    .fill(t.card)
                    .stroke(egui::Stroke::new(1.0, t.danger.gamma_multiply(0.6)))
                    .corner_radius(t.r_lg())
                    .inner_margin(Margin::same(14))
                    .show(ui, |ui| {
                        ui.set_width(ui.available_width());
                        ui.horizontal(|ui| {
                            icons::show(ui, "triangle-alert", 16.0, t.danger);
                            ui.add(egui::Label::new(RichText::new(message).color(t.text)).wrap());
                        });
                        if let Some(r) = remediation {
                            ui.add(egui::Label::new(RichText::new(r).color(t.text_dim)).wrap());
                        }
                        if let Some(l) = log
                            && widgets::open_log_button(ui, l)
                        {
                            app.open_log(l);
                        }
                        let last = i + 1 == items.len();
                        // A pause or a stop part-way gets the Continue card below instead.
                        if last && !app.running() && !can_continue(app, ws) {
                            ui.add_space(6.0);
                            ui.horizontal(|ui| {
                                if widgets::primary_icon(ui, Some("refresh-cw"), "Try again", true).clicked() {
                                    *retry = true;
                                }
                                done_button(app, ui, ws);
                                // A fix that names a command to run (sign in, install…) offers to copy it.
                                if let Some(cmd) = remediation.as_deref().and_then(command_in)
                                    && widgets::secondary(ui, Some("copy"), "Copy the command").on_hover_text(cmd).clicked()
                                {
                                    ui.ctx().copy_text(cmd.to_string());
                                }
                            });
                        }
                    });
            }
        });
        ui.add_space(chat::MESSAGE_GAP);
    }
    questions_up_to(app, ui, usize::MAX);
}

fn work(ui: &mut Ui, tools: &[(String, Option<bool>)], notes: &[String], advanced: bool, t: &Tokens) {
    let running = tools.iter().any(|(_, d)| d.is_none());
    let failed = tools.iter().filter(|(_, d)| *d == Some(false)).count();
    let title = if tools.is_empty() {
        notes.last().cloned().unwrap_or_default()
    } else {
        let n = tools.len().to_string();
        if running { trf("Working… ({n} steps so far)", &[("n", &n)]) } else { trf("Worked through {n} steps", &[("n", &n)]) }
    };
    egui::CollapsingHeader::new(RichText::new(title).color(t.text_dim).size(theme::CAPTION)).default_open(advanced).icon(widgets::disclosure_icon).show(
        ui,
        |ui| {
            for (tool, done) in tools {
                ui.horizontal(|ui| {
                    let (icon, col) = match done {
                        None => ("loader", t.text_faint),
                        Some(true) => ("check", t.success),
                        Some(false) => ("triangle-alert", t.warning),
                    };
                    icons::show(ui, icon, 12.0, col);
                    ui.label(RichText::new(tool.replace('_', " ")).font(theme::mono(12.5)).color(t.text_dim));
                });
            }
            for n in notes {
                ui.label(RichText::new(n).italics().color(t.text_faint).size(theme::CAPTION));
            }
            if failed > 0 {
                ui.label(
                    RichText::new(trf("{n} step(s) didn't work and were retried or skipped.", &[("n", &failed.to_string())]))
                        .color(t.text_faint)
                        .size(theme::CAPTION),
                );
            }
        },
    );
}

/// A question or approval card. Returns the person's answer when they give one.
/// The project's last run stopped part-way without pausing (the app or the computer closed while
/// it worked): its saved status still says it's working, but nothing is.
pub fn interrupted(app: &CraftApp, ws: &Workspace) -> bool {
    !app.runs.is_busy(&ws.root) && matches!(ws.manifest.status, Status::Inspecting | Status::Building | Status::Checking)
}

/// The build can carry on where it stopped: it was paused, or interrupted.
pub fn can_continue(app: &CraftApp, ws: &Workspace) -> bool {
    interrupted(app, ws) || (!app.runs.is_busy(&ws.root) && ws.manifest.status == Status::Stopped)
}

/// "Paused" or "This build stopped part-way", with one Continue button: like a question card,
/// at the end of the feed.
fn continue_card(app: &mut CraftApp, ui: &mut Ui, ws: &Workspace) {
    let t = Tokens::get(ui.ctx());
    let (title, body) = if interrupted(app, ws) {
        (
            "This build stopped part-way",
            "Craft Anything or the computer closed while it was working. Everything so far is kept; Continue picks up where it stopped.",
        )
    } else {
        ("Paused", "Everything so far is kept. Continue picks up where it stopped.")
    };
    let mut go = false;
    egui::Frame::new().fill(t.card).stroke(egui::Stroke::new(1.5, t.accent)).corner_radius(t.r_lg()).inner_margin(Margin::same(14)).show(ui, |ui| {
        ui.set_width(ui.available_width());
        ui.horizontal(|ui| {
            icons::show(ui, "history", 18.0, t.accent);
            ui.add(egui::Label::new(RichText::new(tr(title)).font(theme::semibold(theme::BODY))).wrap());
        });
        ui.add(egui::Label::new(RichText::new(tr(body)).color(t.text_dim)).wrap());
        ui.add_space(6.0);
        ui.horizontal(|ui| {
            go = widgets::primary_icon(ui, Some("play"), "Continue", true).clicked();
            done_button(app, ui, ws);
        });
    });
    ui.add_space(chat::MESSAGE_GAP);
    if go {
        app.continue_build();
    }
}

/// "It's done": the person is happy with the build as it is, so it stops offering to carry on
/// (#210). Shown only when nothing is running.
fn done_button(app: &mut CraftApp, ui: &mut Ui, ws: &Workspace) {
    if widgets::secondary(ui, Some("check"), "It's done").on_hover_text(tr("Keep the build as it is and stop offering to carry on.")).clicked() {
        app.act("project_build_finish", serde_json::json!({"project": ws.root}), tr("Call the build done"));
    }
}

fn ask_card(app: &mut CraftApp, ui: &mut Ui, r: &Request, answered: Option<&str>) -> Option<(String, Answer, String)> {
    let t = Tokens::get(ui.ctx());
    let approval = r.kind == RequestKind::Approval;
    let border = if approval { t.warning } else { t.accent };
    let mut out = None;
    egui::Frame::new().fill(t.card).stroke(egui::Stroke::new(1.5, border)).corner_radius(t.r_lg()).inner_margin(Margin::same(14)).show(ui, |ui| {
        ui.set_width(ui.available_width());
        ui.horizontal(|ui| {
            icons::show(ui, if approval { "shield" } else { "circle-help" }, 18.0, border);
            let title = if approval { trf("May I {action}?", &[("action", &lower_first(&r.title))]) } else { r.title.clone() };
            ui.add(egui::Label::new(RichText::new(title).font(theme::semibold(theme::BODY))).wrap());
        });
        if !r.detail.is_empty() {
            if approval {
                egui::CollapsingHeader::new(RichText::new(tr("Details")).color(t.text_faint).size(theme::CAPTION))
                    .id_salt(("detail", &r.id))
                    .icon(widgets::disclosure_icon)
                    .show(ui, |ui| {
                        ui.label(RichText::new(&r.detail).font(theme::mono(12.5)).color(t.text_dim));
                    });
            } else {
                ui.add(egui::Label::new(RichText::new(&r.detail).color(t.text_dim)).wrap());
            }
        }
        ui.add_space(6.0);
        if let Some(a) = answered {
            ui.label(RichText::new(trf("You answered: {a}", &[("a", a)])).color(t.text_faint));
            return;
        }
        if approval {
            ui.label(
                RichText::new(tr("This is outside what the builder may do on its own. Nothing happens until you say so."))
                    .color(t.text_faint)
                    .size(theme::CAPTION),
            );
            ui.add_space(4.0);
            ui.horizontal(|ui| {
                if widgets::primary(ui, "Allow once").clicked() {
                    out = Some((r.id.clone(), Answer { allow: Some(true), ..Default::default() }, tr("Allowed once")));
                }
                if widgets::secondary(ui, None, "Always for this project").clicked() {
                    out = Some((r.id.clone(), Answer { allow: Some(true), always: true, ..Default::default() }, tr("Allowed for this project")));
                }
                if widgets::secondary(ui, None, "Don't allow").clicked() {
                    out = Some((r.id.clone(), Answer { allow: Some(false), ..Default::default() }, tr("Not allowed")));
                }
            });
            return;
        }
        ui.horizontal_wrapped(|ui| {
            for c in &r.choices {
                if widgets::secondary(ui, None, c).clicked() {
                    out = Some((r.id.clone(), Answer { choice: Some(c.clone()), ..Default::default() }, c.clone()));
                }
            }
        });
        if r.allow_text {
            ui.add_space(4.0);
            ui.horizontal(|ui| {
                let text = app.state.answers.entry(r.id.clone()).or_default();
                let resp = ui.add(
                    egui::TextEdit::singleline(text)
                        .hint_text(tr("Or type your answer…"))
                        .desired_width(ui.available_width() - 120.0)
                        .frame(widgets::text_field_frame(&t)),
                );
                let enter = resp.lost_focus() && ui.input(|i| i.key_pressed(egui::Key::Enter));
                let ready = !text.trim().is_empty();
                if (widgets::primary_icon(ui, Some("send"), "Send", ready).clicked() || enter) && ready {
                    let v = text.trim().to_string();
                    out = Some((r.id.clone(), Answer { text: Some(v.clone()), ..Default::default() }, v));
                }
            });
        }
    });
    out
}

/// The command a fix tells the person to run: the first `quoted` span that reads like one
/// (fixes quote commands, in any language they're written in).
pub fn command_in(remediation: &str) -> Option<&str> {
    let mut parts = remediation.split('`');
    parts.next()?;
    let cmd = parts.next()?.trim();
    // An unclosed quote isn't one, nor is a single word like `app/`.
    (parts.next().is_some() && cmd.contains(' ') && !cmd.contains('\n')).then_some(cmd)
}

fn lower_first(s: &str) -> String {
    let mut c = s.chars();
    c.next().map(|f| f.to_lowercase().chain(c).collect()).unwrap_or_default()
}

/// What the build must do, each on its own: how many hold, every one that doesn't (with why), what
/// couldn't be compared, and the ones that hold behind "Show the ones that are met".
fn claims_list(ui: &mut Ui, c: &CheckResult, t: &Tokens) {
    if c.claims.is_empty() && c.unknowns.is_empty() {
        return;
    }
    ui.add_space(6.0);
    if !c.claims.is_empty() {
        let held = c.claims.iter().filter(|x| x.passed).count();
        let line = trf("{held} of {n} requirements met", &[("held", &held.to_string()), ("n", &c.claims.len().to_string())]);
        ui.label(RichText::new(line).color(t.text_dim).size(theme::SMALL));
    }
    let row = |ui: &mut Ui, icon: &str, colour: Color32, text: String| {
        ui.horizontal_wrapped(|ui| {
            icons::show(ui, icon, 14.0, colour);
            ui.add(egui::Label::new(RichText::new(text).size(theme::SMALL).color(colour)).wrap());
        });
    };
    for claim in c.claims.iter().filter(|x| !x.passed) {
        let text = if claim.detail.is_empty() { claim.title.clone() } else { format!("{} — {}", claim.title, claim.detail) };
        row(ui, "triangle-alert", t.warning, text);
    }
    for u in &c.unknowns {
        row(ui, "info", t.text_dim, trf("Not compared yet: {what}", &[("what", u)]));
    }
    if c.claims.iter().any(|x| x.passed) {
        egui::CollapsingHeader::new(RichText::new(tr("Show the ones that are met")).size(theme::SMALL)).id_salt(("claims", c.round)).show(ui, |ui| {
            for claim in c.claims.iter().filter(|x| x.passed) {
                row(ui, "check", t.text_dim, claim.title.clone());
            }
        });
    }
}

fn check_card(app: &mut CraftApp, ui: &mut Ui, ctx: &egui::Context, ws: &Workspace, c: &CheckResult) {
    let t = Tokens::get(ui.ctx());
    widgets::card(&t).show(ui, |ui| {
        ui.set_width(ui.available_width());
        ui.horizontal(|ui| {
            icons::show(ui, "scan-search", 18.0, t.accent_ink);
            let title = match c.similarity {
                Some(s) => trf("Check {n}: about {s}% like the original", &[("n", &c.round.to_string()), ("s", &format!("{s:.0}"))]),
                None => trf("Check {n}", &[("n", &c.round.to_string())]),
            };
            ui.label(RichText::new(title).font(theme::semibold(theme::BODY)));
        });
        // The per-width measurements are for Advanced mode; a failed check's reason always shows.
        if !app.beginner() || c.similarity.is_none() {
            ui.add(egui::Label::new(RichText::new(&c.note).color(t.text_dim).size(theme::CAPTION)).wrap());
        }
        claims_list(ui, c, &t);
        // Several pages: each one's likeness; clicking one shows its pictures below.
        let picked_id = egui::Id::new(("check-page", c.round));
        let mut picked: usize = ui.data(|d| d.get_temp(picked_id)).unwrap_or(0);
        if c.pages.len() > 1 {
            picked = picked.min(c.pages.len() - 1);
            ui.add_space(6.0);
            for (i, p) in c.pages.iter().enumerate() {
                let text = format!("{}  {:.0}%", if p.dir.is_empty() { tr("start page") } else { p.name.clone() }, p.similarity);
                let colour = if p.similarity >= app.settings.build.good_enough { t.text_dim } else { t.warning };
                if ui.selectable_label(i == picked, RichText::new(text).font(theme::mono(12.5)).color(colour)).clicked() {
                    picked = i;
                    ui.data_mut(|d| d.insert_temp(picked_id, i));
                }
            }
        }
        let dir = c.pages.get(picked).map(|p| p.dir.as_str()).unwrap_or("");
        let shot = format!("screenshot-{}.png", app.settings.build.widths().first().copied().unwrap_or(1440));
        let (orig, built) = (ws.capture_dir().join(dir).join(&shot), ws.checks_dir().join(format!("round-{}", c.round)).join(dir).join(&shot));
        // Both pictures, read on a worker; nothing when either isn't there.
        let shots = c.similarity.map(|_| [("Original", app.thumb(ctx, &orig)), ("Your version", app.thumb(ctx, &built))]);
        if let Some(shots) = shots.filter(|s| !s.iter().any(|(_, t)| matches!(t, Thumb::Missing))) {
            ui.add_space(8.0);
            let w = (ui.available_width() - 12.0) / 2.0;
            ui.horizontal(|ui| {
                for (label, thumb) in shots {
                    ui.vertical(|ui| {
                        ui.set_width(w);
                        widgets::caption(ui, label);
                        match thumb {
                            Thumb::Ready(tex) => {
                                let size = tex.size_vec2();
                                let h = (w * size.y / size.x.max(1.0)).min(320.0);
                                let uv = egui::Rect::from_min_max(egui::pos2(0.0, 0.0), egui::pos2(1.0, (h / (w * size.y / size.x.max(1.0))).min(1.0)));
                                ui.add(egui::Image::new(&tex).uv(uv).fit_to_exact_size(Vec2::new(w, h)).corner_radius(t.r()));
                            }
                            Thumb::Loading | Thumb::Missing => {
                                ui.allocate_exact_size(Vec2::new(w, 120.0), egui::Sense::hover());
                            }
                        }
                    });
                }
            });
        }
    });
}

fn composer(app: &mut CraftApp, ui: &mut Ui, width: f32, t: &Tokens) {
    let running = app.running();
    if let Some(steps) = plan(&app.state.feed).filter(|p| running || p.iter().any(|s| s.status != PlanStatus::Done)) {
        let began = app.open_run().filter(|_| running).map(RebuildRun::started);
        ui.allocate_ui(Vec2::new(width, 0.0), |ui| checklist(ui, steps, t, began));
        ui.add_space(8.0);
    }
    if let Some(n) = app.queue_position() {
        ui.horizontal(|ui| {
            icons::show(ui, "history", 15.0, t.accent_ink);
            let line = if n == 1 {
                tr("Waiting for another build to finish: this one starts next.")
            } else {
                trf("Waiting for other builds to finish: {n} in line.", &[("n", &n.to_string())])
            };
            ui.label(RichText::new(line).color(t.text_dim).size(theme::SMALL));
        });
        ui.add_space(4.0);
    }
    // Notes waiting for the builder's next step: each can be taken back, or all sent now.
    let waiting = app.open_run().filter(|r| r.is_running()).map(RebuildRun::waiting).unwrap_or_default();
    let mut take_back = None;
    // As wide as the prompt box below, so they line up with it.
    ui.allocate_ui(Vec2::new(width, 0.0), |ui| {
        for (i, note) in waiting.iter().enumerate() {
            chat::user_bubble(ui, &note.shown, false);
            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                if icons::button(ui, "x", 22.0, false, "Take back: puts it in the box again").clicked() {
                    take_back = Some(note.id);
                }
                // Said once, under the last note.
                if i + 1 == waiting.len() {
                    if widgets::link(ui, "Send now").on_hover_text(tr("Stops the current step and sends your notes straight away.")).clicked() {
                        app.pause();
                    }
                    let line = if waiting.len() == 1 {
                        tr("Waiting: the builder reads it at its next step. Up arrow to edit.")
                    } else {
                        tr("Waiting: the builder reads these at its next step. Up arrow to edit the last.")
                    };
                    ui.label(RichText::new(line).color(t.text_dim).size(theme::SMALL));
                }
            });
            ui.add_space(4.0);
        }
    });
    if let Some(id) = take_back {
        app.unsend(id);
    }
    let hint = if app.state.just_ask {
        tr("Ask about the build, e.g. \"where are the latest files?\" Nothing changes and no build starts.")
    } else if running {
        tr("Add more info. The builder reads it at its next step.")
    } else {
        tr(app
            .workspace
            .as_ref()
            .map(|ws| outcome_words(&app.kinds, ws).change_hint)
            .unwrap_or("Ask for a change, e.g. \"make the header blue\" or \"add a contact form\""))
    };
    ui.allocate_ui(Vec2::new(width, 0.0), |ui| {
        let history = || {
            let asked = app.workspace.as_ref().and_then(|w| app.asked.get(&w.root)).map_or(&[][..], Vec::as_slice);
            crate::just_ask::prompts(&app.state.feed, asked)
        };
        let out = prompt_box::show(
            ui,
            &mut app.state.project_input,
            &app.state.project_attachments,
            prompt_box::PromptBox {
                name: "Ask for a change",
                hint,
                rows: (1, 8),
                attach: Some("Attach pictures (or drop them here)"),
                // The one way to pause (Continue picks up where it stopped).
                stop_button: running.then_some("Pause"),
                send: true,
                recall: !waiting.is_empty(),
                history: Some(&history),
                font_size: theme::BODY,
            },
        );
        // Like the x on a note: the last one waiting comes back into the box to be edited.
        if out.recall
            && let Some(note) = waiting.last()
        {
            app.unsend(note.id);
        }
        if let Some(i) = out.remove {
            app.state.project_attachments.remove(i);
        }
        if out.attach {
            app.pick(crate::Pick::Attach);
        }
        if out.stop {
            app.pause();
        }
        if out.send {
            // A question (the switch, or /btw) is answered without building.
            match crate::just_ask::question_in(&app.state.project_input, app.state.just_ask) {
                Ok(Some(q)) => {
                    app.state.project_input.clear();
                    app.ask_about_build(q);
                }
                Ok(None) => app.send_message(),
                // It stays in the box to be fixed.
                Err(why) => app.toast(why, true),
            }
        }
        questions_switch(app, ui);
    });
}

/// Under the prompt box: what sending does (ask for a change, or just ask about the build), and
/// whether the builder's questions come to the person or it decides by itself, for this project
/// (`project_questions_set`; it applies from its next question).
fn questions_switch(app: &mut CraftApp, ui: &mut Ui) {
    let Some(ws) = &app.workspace else { return };
    let now = app.settings.questions_in(Some(&ws.manifest));
    let root = ws.root.clone();
    let t = Tokens::get(ui.ctx());
    ui.add_space(4.0);
    ui.horizontal(|ui| {
        // What sending does: ask for a change, or just ask about the build.
        if let Some(i) = widgets::segmented(ui, &["Change it", "Just ask"], usize::from(app.state.just_ask), 24.0) {
            app.state.just_ask = i == 1;
        }
        ui.label(RichText::new(tr("or start with /btw to just ask")).color(t.text_faint).size(theme::SMALL));
        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| questions_controls(app, ui, now, &root, &t));
    });
}

fn questions_controls(app: &mut CraftApp, ui: &mut Ui, now: craft_anything_engine::workspace::Questions, root: &Path, t: &Tokens) {
    use craft_anything_engine::workspace::Questions;
    {
        let sel = usize::from(now == Questions::Decide);
        if let Some(i) = widgets::segmented(ui, &["Ask me", "Decide yourself"], sel, 24.0) {
            let mode = if i == 0 { Questions::Ask } else { Questions::Decide };
            app.set_questions(root, mode);
        }
        let tip = if now == Questions::Ask {
            tr("The builder's questions come to you as cards, and it waits for your answer.")
        } else {
            tr("The builder answers its own questions and says what it chose (\"I decided: …\"), so you can change it.")
        };
        ui.label(RichText::new(tr("Builder's questions:")).color(t.text_dim).size(theme::SMALL)).on_hover_text(tip);
    }
}

/// What was typed for a note while its project's builder worked.
pub struct Draft {
    pub root: PathBuf,
    pub text: String,
    pub attachments: Vec<PathBuf>,
}

impl CraftApp {
    /// Pictures for the next message on the open project (pictures only, once each).
    pub fn attach(&mut self, files: Vec<PathBuf>) {
        let list = &mut self.state.project_attachments;
        for f in files {
            if craft_anything_engine::workspace::is_picture(&f) && !list.contains(&f) {
                list.push(f);
            }
        }
    }

    /// Send what's in the project's prompt box: a follow-up, or a note while it's working.
    pub fn send_message(&mut self) {
        let Some(ws) = self.workspace.clone() else { return };
        let text = self.state.project_input.trim().to_string();
        if text.is_empty() {
            return;
        }
        // Before anything is taken from the box: a project waiting its turn keeps what was typed.
        if self.queue_position().is_some() {
            return self.toast(tr("This project is waiting its turn. Send your message once it starts."), true);
        }
        self.state.project_input.clear();
        let attachments = std::mem::take(&mut self.state.project_attachments);
        if attachments.is_empty() {
            return self.deliver(ws.root, text, attachments, Ok(Vec::new()));
        }
        // Pictures are copied into the project on a worker, then the message goes.
        self.jobs.spawn(tr("Attach pictures"), false, move |_| {
            let files = ws.add_attachments(&attachments).map_err(|e| e.message);
            Ok(Done::Attached { root: ws.root, text, attachments, files })
        });
    }

    /// Send a message once its pictures are in the project (`files`: their copies there); if they
    /// couldn't be copied, it goes back in the box.
    pub(crate) fn deliver(&mut self, root: PathBuf, text: String, attachments: Vec<PathBuf>, files: Result<Vec<PathBuf>, String>) {
        let Some(ws) = self.workspace.clone().filter(|w| w.root == root) else {
            return self.toast(tr("Your message wasn't sent: another project was opened while its pictures were copied."), true);
        };
        let files = match files {
            Ok(f) => f,
            Err(e) => {
                self.state.project_input = text;
                self.state.project_attachments = attachments;
                return self.toast(format!("{} {}", tr("Couldn't attach the pictures:"), e), true);
            }
        };
        let message = prompt_box::with_attachments(&text, &files, &ws.root);
        let shown = [text.clone(), prompt_box::attached_line(files.len())].into_iter().filter(|s| !s.is_empty()).collect::<Vec<_>>().join("\n");
        match self.open_run() {
            Some(run) if run.is_running() => {
                // It joins the feed when the builder reads it; until then it can be taken back.
                let id = run.add_note(message, shown);
                self.drafts.insert(id, Draft { root: ws.root.clone(), text, attachments });
            }
            _ => {
                self.state.feed.push(FeedItem::User(shown.clone()));
                self.resume(Some(message), Some(shown));
            }
        }
    }

    /// Take back a note the builder hasn't read yet: what was typed (and its pictures) goes back
    /// in the prompt box, before anything typed since.
    pub fn unsend(&mut self, id: u64) {
        let Some(note) = self.open_run().and_then(|r| r.unsend(id)) else { return };
        let (text, attachments) = self.drafts.remove(&id).map_or((note.shown, Vec::new()), |d| (d.text, d.attachments));
        let input = &mut self.state.project_input;
        *input = if input.trim().is_empty() { text } else { format!("{text}\n{input}") };
        self.attach(attachments);
    }

    /// Start another run on the open project: with a message (already shown in the app's feed;
    /// `shown` puts it in the saved one), or none to try again.
    fn resume(&mut self, message: Option<String>, shown: Option<String>) {
        let Some(ws) = self.workspace.clone() else { return };
        let ws = Workspace::open(&ws.root).unwrap_or(ws);
        let Some(backend) = self.builder_backend(ws.manifest.builder.as_deref()) else { return self.need_builder(false) };
        self.start_run(ws, Some(backend), message, shown);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use craft_anything_ai::AgentEvent;

    #[test]
    fn the_app_starts_with_the_persons_settings_while_the_engine_is_busy() {
        let engine = crate::demo::engine(craft_anything_engine::Mode::Beginner, true);
        engine.session().settings.deep_mode = true;
        let (held, release) = (std::sync::mpsc::channel(), std::sync::mpsc::channel::<()>());
        let busy = {
            let engine = engine.clone();
            std::thread::spawn(move || {
                let _lock = engine.session();
                let _ = held.0.send(());
                let _ = release.1.recv_timeout(std::time::Duration::from_millis(300));
            })
        };
        held.1.recv().unwrap();
        let app = crate::demo::app(engine);
        busy.join().unwrap();
        assert!(app.settings.deep_mode, "a busy engine at startup must not mean default settings");
        drop(release.0);
    }

    #[test]
    fn a_fix_that_names_a_command_offers_it() {
        let hint = craft_anything_ai::cli_agents::sign_in_hint("Not logged in").unwrap();
        assert_eq!(command_in(&hint), Some("claude auth login"));
        assert_eq!(command_in("Run `codex login` in a terminal."), Some("codex login"));
        for none in ["Try again later.", "Files go in `app/`.", "An `unclosed quote"] {
            assert_eq!(command_in(none), None, "{none}");
        }
    }

    #[test]
    fn events_fold_into_a_readable_feed() {
        let mut feed = Vec::new();
        let ev = |e| RunEvent::Agent(e);
        for e in [
            RunEvent::Step { step: Step::Build, text: "Building".into() },
            ev(AgentEvent::TextDelta { text: "Looking at ".into() }),
            ev(AgentEvent::TextDelta { text: "the page.".into() }),
            ev(AgentEvent::ToolStarted { call_id: "1".into(), tool: "Write".into(), input: serde_json::json!({}) }),
            ev(AgentEvent::ToolStarted { call_id: "2".into(), tool: "Bash".into(), input: serde_json::json!({}) }),
            ev(AgentEvent::ToolFinished { call_id: "1".into(), tool: "Write".into(), ok: true, summary: String::new(), evidence_id: None }),
            ev(AgentEvent::TextDelta { text: "Done.".into() }),
            RunEvent::Checked(CheckResult { similarity: Some(88.0), ..CheckResult::new(CheckResult::WEB_VISUAL, 1, true, "n") }),
            RunEvent::Finished { ok: true, message: "Ready".into(), paused: false },
        ] {
            apply(&mut feed, &e);
        }
        assert!(matches!(&feed[1], FeedItem::Agent { text, streaming: false } if text == "Looking at the page."));
        assert!(matches!(&feed[2], FeedItem::Work { tools, .. } if tools.len() == 2 && tools[0].1 == Some(true) && tools[1].1.is_none()));
        assert!(matches!(&feed[3], FeedItem::Agent { text, .. } if text == "Done."));
        assert!(matches!(&feed[4], FeedItem::Check(_)));
        assert_eq!(feed.len(), 5, "a successful finish adds nothing");
        apply(&mut feed, &ev(AgentEvent::Error { message: "x".into(), remediation: None, log: None }));
        apply(&mut feed, &RunEvent::Finished { ok: false, message: "x".into(), paused: false });
        assert_eq!(feed.iter().filter(|f| matches!(f, FeedItem::Error { .. })).count(), 1, "an explained failure isn't repeated");
        // A pause isn't a failure: a calm line, not an error card.
        apply(&mut feed, &RunEvent::Finished { ok: false, message: "Paused.".into(), paused: true });
        assert!(matches!(feed.last(), Some(FeedItem::Paused)));
        assert_eq!(feed.iter().filter(|f| matches!(f, FeedItem::Error { .. })).count(), 1, "a pause adds no error");
    }
}
