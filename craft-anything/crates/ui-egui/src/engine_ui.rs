//! Game engines in the UI: the "Build with" choice on Make, the step-by-step "Get Unity / Unreal /
//! Godot" dialog, the engines list in Settings, and the download progress shown everywhere. Also a
//! game's generated-assets switch and the fal.ai key it needs.
//!
//! Craft Anything downloads only what it can check (Godot against its official checksums; Unity
//! Hub and the Epic Games Launcher against their vendors' signatures). Sign-in, licences and the
//! engines themselves stay in the vendors' own apps, with the person.

use crate::i18n::{tr, trf};
use crate::state::{MakeDraft, Modal, Screen};
use crate::theme::{self, Tokens};
use crate::{CraftApp, Done, icons, widgets};
use craft_anything_ai::rebuild::KindRegistry;
use craft_anything_engine::{CallOptions, Caller};
use craft_anything_engines::assets::{AssetProvider, AssetProviders, fal};
use craft_anything_engines::game::{self, Builder, Inventory};
use craft_anything_engines::ghidra::{self, get};
use egui::{RichText, Ui, Vec2};
use std::collections::BTreeMap;
use std::path::PathBuf;
use std::sync::Arc;
use std::time::{Duration, Instant};

/// Where the person is in getting an engine.
#[derive(Debug, Default)]
pub struct Flow {
    /// The inventory refresh is running.
    pub checking: bool,
    pub checked_at: Option<Instant>,
    /// The download running for an engine, and its job.
    pub job: Option<(Builder, u64)>,
    /// Engines whose vendor installer was opened (waiting for the person to finish it).
    pub installer_opened: Vec<Builder>,
    /// Start the waiting project once the engine is ready.
    pub start_after: bool,
}

impl CraftApp {
    /// Look for game engines again (in the background; skipped while a look is running).
    pub fn refresh_game_engines(&mut self) {
        if self.engine_flow.checking || self.headless {
            return;
        }
        self.engine_flow.checking = true;
        let store = self.settings.engine_store_dir();
        self.jobs.spawn("Look for game engines", false, move |_| Ok(Done::GameEngines(game::inventory(&game::Places::here(store)))));
    }

    pub fn engines_found(&mut self, inv: Inventory) {
        self.game_engines = Some(inv);
        self.engine_flow.checking = false;
        self.engine_flow.checked_at = Some(Instant::now());
    }

    /// Look up which engine made the game the person just picked.
    pub fn detect_game_engine(&mut self, path: PathBuf) {
        self.state.make.found = None;
        self.jobs.spawn("Look at the game", false, move |_| {
            let folder = craft_anything_ai::rebuild::game_folder(&path);
            Ok(Done::GameFound { found: folder.as_deref().and_then(game::detect), path })
        });
    }

    /// Start getting `b`: download what we can check, else open the vendor's page.
    pub fn get_engine(&mut self, b: Builder, ctx: &egui::Context) {
        if self.engine_flow.job.is_some() {
            return;
        }
        // Installs go through the engines_install tool, as they do from the CLI or an agent.
        let install = |engine: &Arc<craft_anything_engine::Engine>, id: &'static str, j: &crate::jobs::JobCtx| {
            let progress = j.reporter();
            let opts = CallOptions::new(Caller::Ui).with_cancel(j.cancel.clone()).with_progress(&progress);
            engine.call("engines_install", serde_json::json!({"engine": id}), opts).map(|_| ()).map_err(|e| e.for_people())
        };
        let engine = self.engine.clone();
        let id = match b {
            Builder::Godot => self.jobs.spawn(tr("Getting Godot"), true, move |j| {
                install(&engine, "godot", j)?;
                Ok(Done::EngineGot { builder: b, installer: false })
            }),
            Builder::Unity | Builder::Unreal if game::installer(b).is_some() => {
                let title = if b == Builder::Unity { tr("Getting Unity Hub") } else { tr("Getting the Epic Games Launcher") };
                let tool_id = if b == Builder::Unity { "unity" } else { "unreal" };
                self.jobs.spawn(title, true, move |j| {
                    install(&engine, tool_id, j)?;
                    Ok(Done::EngineGot { builder: b, installer: true })
                })
            }
            _ => {
                ctx.open_url(egui::OpenUrl::new_tab(game::download_page(b)));
                return;
            }
        };
        self.engine_flow.job = Some((b, id));
    }

    pub fn engine_got(&mut self, b: Builder, installer: bool) {
        self.engine_flow.job = None;
        if installer {
            if !self.engine_flow.installer_opened.contains(&b) {
                self.engine_flow.installer_opened.push(b);
            }
            self.toast(tr("The installer is open. Follow its steps, then come back here."), false);
        } else {
            self.toast(trf("{name} is ready.", &[("name", b.name())]), false);
        }
        self.refresh_game_engines();
    }

    /// The download for `b`, while it runs: (fraction, "120 of 150 MB").
    fn engine_download(&self, b: Builder) -> Option<(Option<f32>, String)> {
        let (jb, id) = self.engine_flow.job?;
        let j = self.jobs.running().find(|j| j.id == id).filter(|_| jb == b)?;
        Some(j.progress().map(|p| (p.fraction, p.message)).unwrap_or((None, tr("Starting…"))))
    }
}

/// Getting Ghidra for Deep mode: asked first, then downloaded, checked and set up in the background.
#[derive(Debug, Default)]
pub struct GhidraFlow {
    /// Whether Ghidra was found; `None` until looked for again (after a settings change or install).
    pub ready: Option<bool>,
    /// The download running, as a job.
    pub job: Option<u64>,
    /// The project to start once Ghidra is ready (or the person goes on without it): the draft
    /// as it was when Start was pressed, so editing the next one meanwhile doesn't change it.
    pub start_after: Option<Box<crate::state::MakeDraft>>,
}

impl CraftApp {
    /// Ghidra is here for Deep mode to use (looked up once, then remembered).
    pub fn ghidra_ready(&mut self) -> bool {
        let settings = &self.settings;
        *self.ghidra.ready.get_or_insert_with(|| settings.ghidra_launcher().is_some())
    }

    /// Deep mode is on, but it can't use Ghidra yet.
    pub fn ghidra_missing(&mut self) -> bool {
        self.settings.deep_mode && !self.ghidra_ready()
    }

    /// Download Ghidra and its Java in the background (the person already agreed).
    pub fn get_ghidra(&mut self) {
        if self.ghidra.job.is_some() {
            return;
        }
        let engine = self.engine.clone();
        let id = self.jobs.spawn(tr("Getting Ghidra"), true, move |j| {
            let progress = j.reporter();
            let opts = CallOptions::new(Caller::Ui).with_cancel(j.cancel.clone()).with_progress(&progress);
            engine.call("engines_install", serde_json::json!({"engine": "ghidra"}), opts).map_err(|e| e.for_people())?;
            Ok(Done::GhidraGot)
        });
        self.ghidra.job = Some(id);
    }

    pub fn ghidra_got(&mut self) {
        let waiting = self.ghidra.start_after.take();
        self.ghidra = GhidraFlow::default();
        if self.ghidra_ready() {
            self.toast(tr("Ghidra is ready. Deep mode uses it from now on."), false);
        }
        if let Some(draft) = waiting {
            self.start_draft(*draft);
        }
    }

    /// The Ghidra download while it runs: (fraction, "Ghidra · 120 of 543 MB").
    fn ghidra_download(&self) -> Option<(Option<f32>, String)> {
        let j = self.jobs.running().find(|j| Some(j.id) == self.ghidra.job)?;
        Some(j.progress().map(|p| (p.fraction, p.message)).unwrap_or((None, tr("Starting…"))))
    }
}

/// Where Clean room can't do what was asked (a look inside the original): why, and the switch.
pub fn deep_needed(app: &mut CraftApp, ui: &mut Ui) {
    widgets::empty_state(
        ui,
        "shield-check",
        "Looking inside needs Deep mode",
        "Clean room never reads the original's code, files or page source. Deep mode reads them with every tool Craft Anything has.",
    );
    ui.vertical_centered(|ui| {
        if widgets::primary_icon(ui, Some("microscope"), "Turn on Deep mode", true).clicked() {
            // Closes the dialog this is in, if it is in one; Deep mode may offer Ghidra next.
            app.state.modal = None;
            app.set_deep(true);
        }
    });
}

/// [`deep_needed`] as a dialog, for a look inside asked for anywhere else.
pub fn deep_modal(app: &mut CraftApp, ui: &mut Ui, close: &mut bool) {
    deep_needed(app, ui);
    ui.add_space(4.0);
    ui.vertical_centered(|ui| {
        if widgets::secondary(ui, None, "Not now").clicked() {
            *close = true;
        }
    });
}

/// Asked when Deep mode could use Ghidra and it isn't here: get it (then use it), or go on without.
pub fn ghidra_modal(app: &mut CraftApp, ui: &mut Ui, close: &mut bool) {
    let t = Tokens::get(ui.ctx());
    ui.set_width(520.0);
    let ready = app.ghidra_ready();
    let downloading = app.ghidra_download();
    ui.horizontal(|ui| {
        let (rect, _) = ui.allocate_exact_size(Vec2::splat(48.0), egui::Sense::hover());
        ui.painter().rect_filled(rect, t.radius, t.accent_soft);
        icons::paint(ui, rect, if ready { "check" } else { "microscope" }, 24.0, t.accent_ink);
        ui.vertical(|ui| {
            let title = if ready {
                "Ghidra is ready"
            } else if downloading.is_some() {
                "Getting Ghidra"
            } else {
                "Get Ghidra for Deep mode"
            };
            ui.label(theme::heading(tr(title), theme::SECTION));
            ui.label(
                RichText::new(tr("Ghidra, a free reverse-engineering tool from the NSA, gives Deep mode richer decompiled code and types.")).color(t.text_dim),
            );
        });
    });
    ui.add_space(12.0);
    let body = |ui: &mut Ui, text: String| ui.add(egui::Label::new(RichText::new(text).size(theme::BODY)).wrap());
    let then = if app.ghidra.start_after.is_some() { tr("Your project starts as soon as it's done.") } else { String::new() };
    if ready {
        body(ui, tr("Deep mode now decompiles with Ghidra. The first look at a large program can take several minutes."));
    } else if let Some((fraction, message)) = &downloading {
        progress_bar(ui, *fraction, message);
        ui.add_space(6.0);
        body(
            ui,
            format!("{} {then}", tr("This keeps going in the background, and each download is checked against its publisher's checksum before it's used.")),
        );
    } else if get::can_install() {
        body(
            ui,
            trf(
                "It isn't on this computer yet. Craft Anything can download Ghidra {version} and the Java runtime it needs (about {mb} MB), check both against their publishers' checksums, and set them up in its own folder. Nothing else on your computer changes.",
                &[("version", get::VERSION), ("mb", &get::DOWNLOAD_MB.to_string())],
            ),
        );
    } else {
        body(ui, trf("It isn't on this computer yet. Install Ghidra {version} from its release page, then choose its folder.", &[("version", get::VERSION)]));
        if widgets::link(ui, "Open Ghidra's release page").clicked() {
            ui.ctx().open_url(egui::OpenUrl::new_tab(get::PAGE));
        }
    }
    if !ready && downloading.is_none() {
        body(ui, tr("Without it, Deep mode uses Craft Anything's own decompiler, which is rougher."));
    }
    ui.add_space(14.0);
    ui.horizontal(|ui| {
        if ready {
            let start = app.ghidra.start_after.is_some();
            if widgets::primary_icon(ui, Some(if start { "sparkles" } else { "check" }), if start { "Start building" } else { "Done" }, true).clicked() {
                *close = true;
                if let Some(draft) = app.ghidra.start_after.take() {
                    app.start_draft(*draft);
                }
            }
        } else if downloading.is_some() {
            if widgets::secondary(ui, None, "Close").on_hover_text(tr("The download keeps going in the background.")).clicked() {
                *close = true;
            }
        } else {
            if get::can_install() && widgets::primary_icon(ui, Some("download"), "Download and use Ghidra", true).clicked() {
                app.get_ghidra();
            }
            if widgets::secondary(ui, Some("folder-open"), "I have Ghidra").on_hover_text(tr("Choose the folder Ghidra is installed in.")).clicked() {
                app.pick(crate::Pick::GhidraDir);
            }
            let without = if app.ghidra.start_after.is_some() { "Build without it" } else { "Not now" };
            if widgets::secondary(ui, None, without).clicked() {
                *close = true;
                if let Some(mut draft) = app.ghidra.start_after.take() {
                    draft.skip_ghidra = true;
                    app.start_draft(*draft);
                }
            }
        }
    });
}

/// The memory the person set for Ghidra (GB), or `None` for the automatic amount.
pub fn ghidra_memory(app: &CraftApp) -> Option<u64> {
    app.settings.engines.ghidra.memory_gb.map(|g| g.clamp(*ghidra::HEAP_GB.start(), *ghidra::HEAP_GB.end()))
}

/// "Ghidra will use …": the automatic amount in words, or the set one.
pub fn ghidra_memory_words(app: &CraftApp) -> String {
    match ghidra_memory(app) {
        Some(gb) => trf("Ghidra will use up to {gb} GB of memory.", &[("gb", &gb.to_string())]),
        None => trf("Ghidra will use half of this computer's memory (up to {gb} GB).", &[("gb", &ghidra::HEAP_GB.end().to_string())]),
    }
}

/// "Rough guide: 4 GB for programs up to 50 MB, 8 GB up to 200 MB, …", from the engine's table.
pub fn ghidra_memory_guide() -> String {
    let size = |mb: u64| if mb >= 1024 { format!("{} GB", mb / 1024) } else { format!("{mb} MB") };
    let mut parts: Vec<String> = ghidra::HEAP_FOR_PROGRAM
        .iter()
        .enumerate()
        .map(|(i, (mb, gb))| {
            let space = size(*mb);
            if i == 0 {
                trf("{gb} GB for programs up to {size}", &[("gb", &gb.to_string()), ("size", &space)])
            } else {
                trf("{gb} GB up to {size}", &[("gb", &gb.to_string()), ("size", &space)])
            }
        })
        .collect();
    parts.push(trf("{gb} GB for bigger ones", &[("gb", &ghidra::BIG_PROGRAM_GB.to_string())]));
    format!("{} {}.", tr("Rough guide:"), parts.join(", "))
}

/// Settings → Engines: Automatic (half this computer's memory) or a set amount for Ghidra.
pub fn ghidra_memory_setting(app: &mut CraftApp, ui: &mut Ui) {
    let t = Tokens::get(ui.ctx());
    let set = ghidra_memory(app);
    ui.vertical(|ui| {
        if let Some(i) = widgets::segmented(ui, &["Automatic", "Custom"], usize::from(set.is_some()), 30.0) {
            // Custom starts from what a program of a few hundred MB wants.
            app.settings.engines.ghidra.memory_gb = (i == 1).then(|| ghidra::suggested_heap_gb(500 << 20));
            app.settings_changed();
        }
        ui.add_space(6.0);
        match set {
            None => {
                let line = trf("Half of this computer's memory, up to {gb} GB.", &[("gb", &ghidra::HEAP_GB.end().to_string())]);
                ui.label(RichText::new(line).color(t.text_faint).size(theme::CAPTION));
            }
            Some(mut gb) => {
                // A visible rail on the card, filled in the app colour up to the knob.
                let r = ui
                    .scope(|ui| {
                        ui.spacing_mut().slider_width = 180.0;
                        ui.visuals_mut().widgets.inactive.bg_fill = t.field_border;
                        ui.visuals_mut().selection.bg_fill = t.accent;
                        ui.add(egui::Slider::new(&mut gb, ghidra::HEAP_GB).suffix(" GB").trailing_fill(true))
                    })
                    .inner;
                let r = widgets::named(r, "Memory for Ghidra");
                if r.changed() {
                    app.settings.engines.ghidra.memory_gb = Some(gb);
                }
                // Saved once the slider is let go, not on every step of a drag.
                if r.drag_stopped() || (r.changed() && !r.dragged()) {
                    app.settings_changed();
                }
                ui.label(RichText::new(tr("Leave a few GB for the rest of your computer.")).color(t.text_faint).size(theme::CAPTION));
            }
        }
    });
}

/// Settings → Engines: whether Deep mode can use Ghidra, and the way to get it.
pub fn ghidra_status(app: &mut CraftApp, ui: &mut Ui) {
    let t = Tokens::get(ui.ctx());
    if let Some((fraction, message)) = app.ghidra_download() {
        progress_bar(ui, fraction, &message);
    } else if app.ghidra_ready() {
        let at = app.settings.ghidra_launcher().map(|p| p.display().to_string()).unwrap_or_default();
        widgets::pill(ui, "Installed", t.success, t.raised).on_hover_text(at);
    } else {
        ui.horizontal(|ui| {
            widgets::pill(ui, "Not installed", t.warning, t.raised);
            if widgets::secondary(ui, Some("download"), "Get Ghidra").clicked() {
                app.state.modal = Some(Modal::Ghidra);
            }
        });
    }
}

/// Which asset providers have a key stored, by id.
fn stored_keys(hub: &craft_anything_ai::AiHub) -> BTreeMap<String, bool> {
    let all = AssetProviders::built_in();
    all.ids().into_iter().map(|id| (id.to_string(), hub.has_asset_key(&all, id))).collect()
}

impl CraftApp {
    /// Find out which asset providers have a key set up (in the background: the keychain can be slow).
    pub fn check_asset_keys(&mut self) {
        if self.headless {
            return;
        }
        let hub = self.hub.clone();
        self.jobs.spawn("Check the asset keys", false, move |_| Ok(Done::AssetKeys(stored_keys(&hub))));
    }

    /// Whether a fal.ai key is set up: it makes the generated pictures and models.
    pub fn fal_key(&self) -> Option<bool> {
        self.asset_keys.as_ref().map(|k| k.get(fal::ID).copied().unwrap_or(false))
    }

    /// Save an asset provider's key in the system keychain.
    pub fn save_asset_key(&mut self, provider: String, key: String) {
        let hub = self.hub.clone();
        self.jobs.spawn(tr("Save the key"), true, move |_| {
            hub.set_asset_key(&provider, &key).map_err(|e| e.message)?;
            Ok(Done::AssetKeys(stored_keys(&hub)))
        });
    }

    pub fn remove_asset_key(&mut self, provider: String) {
        let hub = self.hub.clone();
        self.jobs.spawn(tr("Forget the key"), true, move |_| {
            hub.remove_asset_key(&provider).map_err(|e| e.message)?;
            Ok(Done::AssetKeys(stored_keys(&hub)))
        });
    }

    /// Let the builder generate pictures and 3D models, or not: for the open project on its screen
    /// (through the project_assets_allow tool), else for the game being set up on Make. Turning it
    /// on without a fal.ai key asks for one.
    pub fn set_generate_assets(&mut self, on: bool) {
        let project = self.workspace.as_ref().filter(|_| self.state.screen == Screen::Project).map(|w| w.root.clone());
        match project {
            Some(root) => {
                let title = tr(if on { "Allow generated assets" } else { "Stop generated assets" });
                self.act("project_assets_allow", serde_json::json!({"project": root, "allow": on}), title);
            }
            None => self.state.make.generate_assets = on,
        }
        if on && self.fal_key() == Some(false) {
            self.state.modal = Some(Modal::Assets);
        }
    }
}

/// A provider's key field and its Save button; returns the key when Save is pressed.
fn key_field(app: &mut CraftApp, ui: &mut Ui, provider: &dyn AssetProvider, save: &str) -> Option<String> {
    let t = Tokens::get(ui.ctx());
    let mut out = None;
    ui.horizontal(|ui| {
        let key = app.key_inputs.entry(provider.id().into()).or_default();
        let r = ui.add(
            egui::TextEdit::singleline(key)
                .password(true)
                .hint_text(trf("Paste your {name} key", &[("name", provider.name())]))
                .desired_width(320.0)
                .frame(widgets::text_field_frame_compact(&t)),
        );
        widgets::named(r, &trf("{name} key", &[("name", provider.name())]));
        let k = key.trim().to_string();
        if widgets::primary_icon(ui, None, save, !k.is_empty()).clicked() && !k.is_empty() {
            key.clear();
            out = Some(k);
        }
    });
    out
}

/// The game's "Generate custom pictures and models" switch and what they cost. It works while the
/// project builds: a run keeps the person's choice when it saves, and the asset tools read it each time.
pub fn assets_toggle(app: &mut CraftApp, ui: &mut Ui, mut on: bool) {
    let t = Tokens::get(ui.ctx());
    if widgets::toggle(ui, &mut on, "Generate custom pictures and models").changed() {
        app.set_generate_assets(on);
    }
    let no_key = on && app.fal_key() == Some(false);
    let note = if no_key {
        tr("Needs a fal.ai key. Until then the game is built without them.")
    } else {
        let p = AssetPrices::of(app);
        trf(
            "Made with fal.ai and paid from your account: {model} a 3D model, {picture} a picture. Off, the game is built without them.",
            &[("model", &p.model), ("picture", &p.picture)],
        )
    };
    ui.horizontal_wrapped(|ui| {
        ui.label(RichText::new(note).color(if no_key { t.warning } else { t.text_dim }).size(theme::SMALL));
        if no_key && widgets::link(ui, "Add a fal.ai key").clicked() {
            app.state.modal = Some(Modal::Assets);
        }
    });
}

/// Asks for a fal.ai key when generated assets are turned on without one.
pub fn assets_modal(app: &mut CraftApp, ui: &mut Ui, close: &mut bool) {
    let t = Tokens::get(ui.ctx());
    ui.set_width(520.0);
    ui.horizontal(|ui| {
        let (rect, _) = ui.allocate_exact_size(Vec2::splat(48.0), egui::Sense::hover());
        ui.painter().rect_filled(rect, t.radius, t.accent_soft);
        icons::paint(ui, rect, "boxes", 24.0, t.accent_ink);
        ui.vertical(|ui| {
            ui.label(theme::heading(tr("Your fal.ai key"), theme::SECTION));
            ui.label(RichText::new(tr("Generated pictures and 3D models are made with fal.ai.")).color(t.text_dim));
        });
    });
    ui.add_space(12.0);
    ui.add(
        egui::Label::new(
            RichText::new({
                let p = AssetPrices::of(app);
                trf(
                    "The builder makes the game's 3D models and textures from descriptions of original designs, paid from your fal.ai account. Models are low-poly so the game runs fast. A textured model costs {model} and a picture {picture}. Each project has a {budget} budget, and you're asked before it goes over. The key is kept in your system keychain.",
                    &[("model", &p.model), ("picture", &p.picture), ("budget", &p.budget)],
                )
            })
            .size(theme::BODY),
        )
        .wrap(),
    );
    ui.add_space(10.0);
    let fal = fal::Fal::default();
    keys_link(ui, &fal);
    ui.add_space(8.0);
    if let Some(key) = key_field(app, ui, &fal, "Save") {
        *close = true;
        app.save_asset_key(fal.id().into(), key);
    }
    ui.add_space(14.0);
    if widgets::secondary(ui, None, "Not now").clicked() {
        *close = true;
        app.set_generate_assets(false);
    }
}

/// Prices for the text about generated art, from the asset table and Settings.
struct AssetPrices {
    /// A textured 3D model ("about $0.53").
    model: String,
    /// A square picture with the chosen picture model.
    picture: String,
    /// A new project's budget ("$5.00").
    budget: String,
}

impl AssetPrices {
    fn of(app: &CraftApp) -> AssetPrices {
        use crate::usage::asset_cost_words;
        use craft_anything_engines::assets::{Catalogue, Shape, usd};
        let table = Catalogue::built_in();
        let picture =
            table.image_model(app.settings.assets.image_model.as_deref()).or_else(|_| table.image_model(None)).map(|m| m.cost(Shape::Square)).unwrap_or(0.0);
        let model = table.model_3d(None).map(|m| m.cost(true)).unwrap_or(0.0) + picture;
        AssetPrices { model: asset_cost_words(model), picture: asset_cost_words(picture), budget: tr(&usd(app.settings.assets.budget())) }
    }
}

/// "Get a key at …" for a provider that says where.
fn keys_link(ui: &mut Ui, provider: &dyn AssetProvider) {
    if let Some(page) = provider.keys_page()
        && widgets::link(ui, &trf("Get a key at {name}", &[("name", provider.name())])).clicked()
    {
        ui.ctx().open_url(egui::OpenUrl::new_tab(page));
    }
}

/// Settings → AI: each asset provider's key for game assets.
pub fn assets_settings(app: &mut CraftApp, ui: &mut Ui) {
    let t = Tokens::get(ui.ctx());
    ui.label(RichText::new(tr("Game assets")).font(theme::medium(theme::SMALL)));
    ui.add(
        egui::Label::new(
            RichText::new({
                let p = AssetPrices::of(app);
                trf(
                    "Lets the builder make realistic 3D models and textures for games, {model} a model, with a {budget} budget per project.",
                    &[("model", &p.model), ("budget", &p.budget)],
                )
            })
            .color(t.text_faint)
            .size(theme::CAPTION),
        )
        .wrap(),
    );
    let all = AssetProviders::built_in();
    for provider in all.ids().into_iter().filter_map(|id| all.get(id)) {
        ui.add_space(6.0);
        ui.label(RichText::new(provider.name()).size(theme::SMALL));
        let stored = app.asset_keys.as_ref().and_then(|k| k.get(provider.id()).copied());
        ui.push_id(provider.id(), |ui| {
            if stored == Some(true) {
                ui.horizontal(|ui| {
                    widgets::pill(ui, "Key saved", t.success, t.raised);
                    if widgets::secondary(ui, None, "Remove").clicked() {
                        app.remove_asset_key(provider.id().into());
                    }
                });
            } else {
                if let Some(key) = key_field(app, ui, provider.as_ref(), "Save") {
                    app.save_asset_key(provider.id().into(), key);
                }
                keys_link(ui, provider.as_ref());
            }
        });
    }
}

/// The engine to build this draft with: the person's pick, else the one the request names, else
/// none when the request names another way to build ("…in Electron"), else the original's own
/// or Unity.
pub fn chosen(kinds: &KindRegistry, d: &MakeDraft) -> Option<Builder> {
    if d.builder.is_some() {
        return d.builder;
    }
    match kinds.named(&d.request, &crate::make::resolve_target(d)) {
        Some(stack) => Builder::from_stack(stack),
        None => Some(Builder::for_game(d.found.as_ref().map(|f| f.engine))),
    }
}

/// "Build with" on Make: what made the original, the engine we'll use, and whether it's here.
pub fn build_with(app: &mut CraftApp, ui: &mut Ui) {
    let t = Tokens::get(ui.ctx());
    let b = chosen(&app.kinds, &app.state.make);
    if let Some(f) = app.state.make.found.clone() {
        ui.horizontal_wrapped(|ui| {
            icons::show(ui, "puzzle", 16.0, t.accent_ink);
            ui.label(RichText::new(trf("Made with {engine}", &[("engine", &f.label())])).font(theme::semibold(theme::BODY)));
        });
        if !matches!(f.engine, game::Made::Unity | game::Made::Unreal | game::Made::Godot) {
            ui.label(
                RichText::new(trf("Craft Anything can't build with {engine}, so Unity is the closest match.", &[("engine", f.engine.name())]))
                    .color(t.text_dim)
                    .size(theme::SMALL),
            );
        }
        ui.add_space(8.0);
    }
    ui.horizontal(|ui| {
        ui.label(RichText::new(tr("Build with")).size(theme::BODY).color(t.text_dim));
        let names: Vec<&str> = Builder::ALL.iter().map(|b| b.name()).collect();
        // Nothing is selected while the request names another way to build.
        let sel = b.and_then(|b| Builder::ALL.iter().position(|x| *x == b)).unwrap_or(usize::MAX);
        if let Some(i) = widgets::segmented(ui, &names, sel, 32.0) {
            app.state.make.builder = Builder::ALL.get(i).copied();
        }
    });
    ui.add_space(6.0);
    match b {
        Some(b) => status_line(app, ui, b, true),
        None => {
            let named = app.kinds.named(&app.state.make.request, &crate::make::resolve_target(&app.state.make)).unwrap_or_default();
            ui.horizontal_wrapped(|ui| {
                icons::show(ui, "check", 16.0, t.success);
                ui.label(
                    RichText::new(trf("Built with {stack}, as you asked, so no game engine is needed.", &[("stack", named)]))
                        .color(t.text_dim)
                        .size(theme::SMALL),
                );
            });
        }
    }
}

/// "Ready — Unity 6000.0.23f1" or "Not on this computer yet" with the way to get it.
fn status_line(app: &mut CraftApp, ui: &mut Ui, b: Builder, offer: bool) {
    let t = Tokens::get(ui.ctx());
    let inv = app.game_engines.clone();
    ui.horizontal_wrapped(|ui| match &inv {
        None => {
            ui.add(egui::Spinner::new().size(14.0).color(t.accent));
            ui.label(RichText::new(tr("Looking for game engines on this computer…")).color(t.text_dim).size(theme::SMALL));
        }
        Some(inv) if inv.ready(b) => {
            icons::show(ui, "check", 16.0, t.success);
            let v = inv.best(b).map(|i| i.version.clone()).unwrap_or_default();
            let what = if v.is_empty() { b.name().to_string() } else { format!("{} {v}", b.name()) };
            ui.label(RichText::new(trf("Ready: {what} is on this computer.", &[("what", &what)])).color(t.text_dim).size(theme::SMALL));
        }
        Some(inv) => {
            icons::show(ui, "download", 16.0, t.warning);
            let text = if b == Builder::Unreal && inv.best(b).is_some() {
                tr("Unreal is here, but it also needs Visual Studio's C++ tools.")
            } else {
                format!("{} {}", trf("{name} isn't on this computer yet.", &[("name", b.name())]), tr(b.needs()))
            };
            ui.label(RichText::new(text).color(t.text_dim).size(theme::SMALL));
            if offer && widgets::secondary(ui, Some("download"), &trf("Get {name}", &[("name", b.name())])).clicked() {
                // One dialog at a time: the steps replace Settings when opened from there.
                app.state.settings_open = false;
                app.state.modal = Some(Modal::Engine(b));
            }
        }
    });
}

/// One step of getting an engine.
struct Step {
    title: String,
    detail: String,
    done: bool,
    action: Option<Action>,
}

enum Action {
    Download,
    OpenApp(PathBuf),
    OpenPage(&'static str),
}

fn steps(app: &CraftApp, b: Builder, inv: &Inventory) -> Vec<Step> {
    let opened = app.engine_flow.installer_opened.contains(&b);
    let direct = game::installer(b).is_some();
    let step = |title: &str, detail: &str, done: bool, action: Option<Action>| Step { title: tr(title), detail: tr(detail), done, action };
    match b {
        Builder::Godot => vec![step(
            &trf("Download Godot {v}", &[("v", game::GODOT_VERSION.trim_end_matches("-stable"))]),
            "Checked against Godot's official checksums before it's used.",
            inv.ready(b),
            Some(Action::Download),
        )],
        Builder::Rust => {
            vec![step("Install Rust", "Follow the steps on rustup.rs, then come back here.", inv.ready(b), Some(Action::OpenPage(game::download_page(b))))]
        }
        Builder::Unity => {
            let hub = inv.unity_hub.clone();
            let mut v = Vec::new();
            if direct {
                v.push(step(
                    "Download Unity Hub",
                    "Unity's own installer. It only opens if Unity's signature checks out.",
                    hub.is_some() || opened,
                    Some(Action::Download),
                ));
                v.push(step("Install Unity Hub", "Follow the installer that opened. Come back here when it's done.", hub.is_some(), None));
            } else {
                v.push(step("Get Unity Hub", "Download it from unity.com and install it.", hub.is_some(), Some(Action::OpenPage(game::download_page(b)))));
            }
            v.push(step(
                "Sign in and add the Unity Editor",
                "In Unity Hub: sign in (or make a free account) and accept the free Personal licence. Then open Installs, press Install Editor and choose the recommended version. About 10 GB.",
                inv.best(b).is_some(),
                hub.map(Action::OpenApp),
            ));
            v
        }
        Builder::Unreal => {
            let launcher = inv.epic_launcher.clone();
            let mut v = Vec::new();
            if direct {
                v.push(step(
                    "Download the Epic Games Launcher",
                    "Epic's own installer. It only opens if Epic's signature checks out.",
                    launcher.is_some() || opened,
                    Some(Action::Download),
                ));
                v.push(step("Install the launcher", "Follow the installer that opened. Come back here when it's done.", launcher.is_some(), None));
            } else {
                v.push(step(
                    "Get the Epic Games Launcher",
                    "Download it from unrealengine.com and install it.",
                    launcher.is_some(),
                    Some(Action::OpenPage(game::download_page(b))),
                ));
            }
            v.push(step(
                "Sign in and install Unreal Engine",
                "In the launcher: sign in, open Unreal Engine, then Library, and press + next to Engine Versions to install one. About 60 GB.",
                inv.best(b).is_some(),
                launcher.map(Action::OpenApp),
            ));
            let (title, detail) = if cfg!(target_os = "macos") {
                ("Install Xcode", "Unreal builds games with Apple's Xcode, free in the App Store.")
            } else {
                ("Add Visual Studio's C++ tools", "Install Visual Studio Community (free) and tick \"Game development with C++\".")
            };
            v.push(step(title, detail, inv.cpp_tools, (!cfg!(target_os = "macos")).then_some(Action::OpenPage(game::VISUAL_STUDIO_PAGE))));
            v
        }
    }
}

/// The body of the "Get <engine>" dialog. Sets `close` when the person is done with it.
pub fn modal(app: &mut CraftApp, ui: &mut Ui, b: Builder, close: &mut bool) {
    let t = Tokens::get(ui.ctx());
    ui.set_width(520.0);
    let Some(inv) = app.game_engines.clone() else {
        ui.horizontal(|ui| {
            ui.add(egui::Spinner::new().size(16.0).color(t.accent));
            ui.label(tr("Looking for game engines on this computer…"));
        });
        app.refresh_game_engines();
        return;
    };
    let ready = inv.ready(b);
    // Keep looking while the person installs things in other windows.
    if !ready && !app.engine_flow.checking && app.engine_flow.checked_at.is_none_or(|at| at.elapsed() > Duration::from_secs(3)) {
        app.refresh_game_engines();
    }
    ui.ctx().request_repaint_after(Duration::from_secs(1));

    ui.horizontal(|ui| {
        let (rect, _) = ui.allocate_exact_size(Vec2::splat(48.0), egui::Sense::hover());
        ui.painter().rect_filled(rect, t.radius, t.accent_soft);
        icons::paint(ui, rect, if ready { "check" } else { "download" }, 24.0, t.accent_ink);
        ui.vertical(|ui| {
            let title = if ready { trf("{name} is ready", &[("name", b.name())]) } else { trf("Get {name}", &[("name", b.name())]) };
            ui.label(theme::heading(title, theme::SECTION));
            ui.label(RichText::new(tr(b.needs())).color(t.text_dim));
        });
    });
    ui.add_space(16.0);

    let list = steps(app, b, &inv);
    let current = list.iter().position(|s| !s.done);
    let mut act = None;
    for (i, s) in list.iter().enumerate() {
        let now = Some(i) == current;
        ui.horizontal_top(|ui| {
            let (r, _) = ui.allocate_exact_size(Vec2::splat(28.0), egui::Sense::hover());
            if s.done {
                ui.painter().rect_filled(r, r.width() / 2.0, t.success);
                icons::paint(ui, r, "check", 16.0, t.canvas);
            } else {
                ui.painter().rect_stroke(r, r.width() / 2.0, egui::Stroke::new(1.0, if now { t.accent } else { t.field_border }), egui::StrokeKind::Inside);
                let g = widgets::label_galley(ui, &(i + 1).to_string(), 12.0, t.text);
                ui.painter().galley_with_override_text_color(r.center() - g.size() / 2.0, g, if now { t.text } else { t.text_faint });
            }
            ui.add_space(4.0);
            ui.vertical(|ui| {
                ui.label(RichText::new(&s.title).font(theme::semibold(theme::BODY)).color(if s.done || now { t.text } else { t.text_dim }));
                if now || !s.done {
                    ui.add(egui::Label::new(RichText::new(&s.detail).color(t.text_dim).size(theme::SMALL)).wrap());
                }
                if now {
                    ui.add_space(8.0);
                    if let Some(a) = &s.action {
                        let downloading = app.engine_download(b);
                        match (a, downloading) {
                            (Action::Download, Some((fraction, message))) => progress_bar(ui, fraction, &message),
                            (Action::Download, None) => {
                                if widgets::primary_icon(ui, Some("download"), &tr("Download"), app.engine_flow.job.is_none()).clicked() {
                                    act = Some(Action::Download);
                                }
                            }
                            (Action::OpenApp(p), _) => {
                                let label = if b == Builder::Unity { "Open Unity Hub" } else { "Open the Epic Games Launcher" };
                                if widgets::primary_icon(ui, Some("external-link"), label, true).clicked() {
                                    act = Some(Action::OpenApp(p.clone()));
                                }
                            }
                            (Action::OpenPage(url), _) => {
                                if widgets::primary_icon(ui, Some("external-link"), "Open the download page", true).clicked() {
                                    act = Some(Action::OpenPage(url));
                                }
                            }
                        }
                        ui.add_space(4.0);
                    }
                    if !s.done && current.is_some() && i > 0 {
                        ui.label(RichText::new(tr("This updates by itself when it's done.")).color(t.text_faint).size(theme::SMALL));
                    }
                }
            });
        });
        ui.add_space(12.0);
    }

    match act {
        Some(Action::Download) => app.get_engine(b, ui.ctx()),
        Some(Action::OpenApp(_)) => open_app(app, b),
        Some(Action::OpenPage(url)) => ui.ctx().open_url(egui::OpenUrl::new_tab(url)),
        None => {}
    }

    ui.add_space(4.0);
    ui.horizontal(|ui| {
        if ready {
            let label = if app.engine_flow.start_after { "Start building" } else { "Done" };
            if widgets::primary_icon(ui, Some(if app.engine_flow.start_after { "sparkles" } else { "check" }), label, true).clicked() {
                *close = true;
                app.state.make.builder = Some(b);
                if std::mem::take(&mut app.engine_flow.start_after) {
                    app.start_make();
                }
            }
        } else {
            // Another engine that's ready now, best first.
            if let Some(alt) = Builder::ALL.into_iter().find(|x| *x != b && inv.ready(*x))
                && widgets::secondary(ui, None, &trf("Build with {name} instead", &[("name", alt.name())])).clicked()
            {
                *close = true;
                app.state.make.builder = Some(alt);
                if std::mem::take(&mut app.engine_flow.start_after) {
                    app.start_make();
                }
            }
            if widgets::secondary(ui, None, "Close").on_hover_text(tr("Downloads keep going in the background.")).clicked() {
                *close = true;
                app.engine_flow.start_after = false;
            }
        }
    });
}

/// A labelled progress bar (indeterminate when the size isn't known).
pub fn progress_bar(ui: &mut Ui, fraction: Option<f32>, message: &str) {
    let t = Tokens::get(ui.ctx());
    let w = ui.available_width().min(420.0);
    let (bar, _) = ui.allocate_exact_size(Vec2::new(w, 6.0), egui::Sense::hover());
    ui.painter().rect_filled(bar, 3.0, t.separator);
    let (from, to) = match fraction {
        Some(f) => (0.0, f.clamp(0.0, 1.0)),
        None => {
            let x = (ui.input(|i| i.time) * 0.6).fract() as f32;
            ((x - 0.25).max(0.0), x)
        }
    };
    ui.painter().rect_filled(egui::Rect::from_x_y_ranges(bar.left() + bar.width() * from..=bar.left() + bar.width() * to, bar.y_range()), 3.0, t.accent);
    ui.add_space(4.0);
    let pct = fraction.map(|f| format!("{:.0}%  ·  ", f * 100.0)).unwrap_or_default();
    ui.label(RichText::new(format!("{pct}{message}")).font(theme::mono(12.5)).color(t.text_dim));
    widgets::animate(ui, Duration::from_millis(100));
}

/// Settings → Engines: each game engine, whether it's here, and the way to get it.
pub fn settings_section(app: &mut CraftApp, ui: &mut Ui) {
    let t = Tokens::get(ui.ctx());
    if app.game_engines.is_none() {
        app.refresh_game_engines();
    }
    ui.label(RichText::new(tr("Game engines")).font(theme::medium(theme::SMALL)));
    ui.add(
        egui::Label::new(
            RichText::new(tr(
                "Recreated games are built with the original's own engine when it's here (Unity, Unreal or Godot), else Unity, and Rust as the last resort.",
            ))
            .color(t.text_faint)
            .size(theme::CAPTION),
        )
        .wrap(),
    );
    ui.add_space(8.0);
    for b in Builder::ALL {
        ui.label(RichText::new(b.name()).font(theme::semibold(theme::SMALL)));
        status_line(app, ui, b, true);
        ui.add_space(8.0);
    }
}

/// The download running anywhere in the app, for the title bar: (title, fraction, message).
pub fn global_download(app: &CraftApp) -> Option<(String, Option<f32>, String)> {
    let id = app.engine_flow.job.map(|(_, id)| id).or(app.ghidra.job)?;
    let j = app.jobs.running().find(|j| j.id == id)?;
    let p = j.progress();
    Some((j.title.clone(), p.as_ref().and_then(|p| p.fraction), p.map(|p| p.message).unwrap_or_default()))
}

/// Unity Hub or the Epic Games Launcher, through the engines_app_open tool.
fn open_app(app: &mut CraftApp, b: Builder) {
    let which = if b == Builder::Unity { "unity_hub" } else { "epic_launcher" };
    app.act("engines_app_open", serde_json::json!({"app": which}), tr("Open the installer app"));
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_request_picks_the_engine_or_none() {
        let kinds = KindRegistry::built_in();
        let draft = |r: &str| MakeDraft { request: r.into(), ..Default::default() };
        assert_eq!(chosen(&kinds, &draft("a racing game")), Some(Builder::Unity));
        assert_eq!(chosen(&kinds, &draft("a racing game in Godot")), Some(Builder::Godot));
        assert_eq!(chosen(&kinds, &draft("a racing game in Electron")), None, "built as asked: no engine needed");
        let mut d = draft("a racing game in Electron");
        d.builder = Some(Builder::Unreal);
        assert_eq!(chosen(&kinds, &d), Some(Builder::Unreal), "the person's pick on Make wins");
    }
}
