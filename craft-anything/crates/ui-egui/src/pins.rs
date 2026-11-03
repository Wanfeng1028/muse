//! Pinned builds in the app: the sidebar's Pinned section, "Pin this build" on a project's page,
//! and the dialogs to pin, rename and remove one. Everything goes through the pin tools
//! (`project_pin_*`), as the CLI and MCP clients do; the list is read on a worker, and read again
//! every few seconds while something it started is running, to notice it closing.

use crate::i18n::{tr, trf};
use crate::state::Modal;
use crate::theme::{self, Tokens};
use crate::{CraftApp, icons, widgets};
use craft_anything_engine::evidence::ToolError;
use craft_anything_engine::pins::{Pin, PinMode};
use egui::{RichText, Ui, Vec2};
use serde_json::{Value, json};
use std::path::{Path, PathBuf};
use std::time::Duration;

/// How often the list is read again while a pin is running.
const POLL: Duration = Duration::from_secs(3);
/// Above this, the pin dialog points out that a frozen copy is big.
const BIG_COPY: u64 = 1_000_000_000;

/// One pin as the sidebar shows it.
#[derive(Debug, Clone, PartialEq)]
pub struct PinRow {
    pub project: PathBuf,
    pub project_name: String,
    pub pin: Pin,
    pub running: bool,
}

/// What the pin dialog is choosing.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct PinDraft {
    pub project: PathBuf,
    pub mode: PinMode,
    pub name: String,
    /// What a frozen and a light copy would take: none while it's being worked out.
    pub size: Option<Result<(u64, u64), String>>,
}

impl CraftApp {
    /// Read every project's pins (and what's running) on a worker.
    pub fn refresh_pins(&mut self) {
        self.pins_read_at = Some(std::time::Instant::now());
        self.act("project_pins_list", json!({}), tr("Read pinned builds"));
    }

    /// While a pin is running, read the list again now and then, so it shows when it closes.
    pub(crate) fn poll_pins(&mut self, ctx: &egui::Context) {
        if self.headless || !self.pins.iter().any(|p| p.running) {
            return;
        }
        if self.pins_read_at.is_none_or(|t| t.elapsed() >= POLL) {
            self.refresh_pins();
        }
        ctx.request_repaint_after(POLL);
    }

    pub fn open_pin(&mut self, row: &PinRow, another: bool) {
        self.act("project_pin_open", json!({"project": row.project, "pin": row.pin.id, "another": another}), tr("Open a pinned build"));
    }

    fn stop_pin(&mut self, row: &PinRow) {
        self.act("project_pin_stop", json!({"project": row.project, "pin": row.pin.id}), tr("Close a pinned build"));
    }

    /// Ask how to pin the open project's build (and work out what a frozen copy would take).
    pub fn ask_pin(&mut self, root: &Path) {
        self.state.pin_draft = PinDraft { project: root.to_path_buf(), ..Default::default() };
        self.state.modal = Some(Modal::Pin);
        self.act("project_pin_create", json!({"project": root, "estimate": true}), tr("Work out a copy's size"));
    }

    /// A pin tool finished.
    pub(crate) fn pin_done(&mut self, tool: &str, result: Result<Value, ToolError>) {
        match (tool, result) {
            ("project_pins_list", Ok(v)) => {
                self.pins = v["pins"]
                    .as_array()
                    .into_iter()
                    .flatten()
                    .filter_map(|p| {
                        Some(PinRow {
                            project: PathBuf::from(p["project"].as_str()?),
                            project_name: p["project_name"].as_str().unwrap_or_default().to_string(),
                            pin: serde_json::from_value(p["pin"].clone()).ok()?,
                            running: p["running"].as_bool().unwrap_or(false),
                        })
                    })
                    .collect();
            }
            ("project_pins_list", Err(e)) => log::warn!("pinned builds couldn't be read: {}", e.message),
            ("project_pin_create", Ok(v)) if v.get("estimate").is_some() => {
                let bytes = |k: &str| v["estimate"][k].as_u64().unwrap_or(0);
                self.state.pin_draft.size = Some(Ok((bytes("bytes"), bytes("light_bytes"))));
            }
            ("project_pin_create", Err(e)) if self.state.modal == Some(Modal::Pin) && self.state.pin_draft.size.is_none() => {
                self.state.pin_draft.size = Some(Err(e.for_people()));
            }
            ("project_pin_create", Ok(v)) => {
                let name = v["pin"]["name"].as_str().unwrap_or_default();
                self.toast(trf("Pinned: {name}. Open it from the sidebar any time.", &[("name", name)]), false);
                self.state.pins_collapsed = false;
                self.refresh_pins();
            }
            ("project_pin_open", Ok(v)) => {
                if v["already_running"].as_bool() == Some(true) {
                    self.toast(tr("It's already open. Right-click it to open another copy."), false);
                } else if !v["closed_at_once"].is_null() {
                    self.toast(quit_at_once(&v), true);
                } else {
                    self.toast(tr("Starting… it opens in its own window."), false);
                }
                self.refresh_pins();
            }
            ("project_pin_open", Err(e)) => {
                self.toast(format!("{} {}", tr("Couldn't open it."), e.for_people()), true);
                self.refresh_pins();
            }
            ("project_pin_rename" | "project_pin_stop", Ok(_)) => self.refresh_pins(),
            ("project_pin_delete", Ok(_)) => {
                self.toast(tr("Pin removed."), false);
                self.refresh_pins();
            }
            (_, Err(e)) => self.toast(e.for_people(), true),
            (_, Ok(_)) => {}
        }
    }
}

/// What to say when a program closed straight away without an error code: its last output, if any.
pub(crate) fn quit_at_once(v: &Value) -> String {
    let said = v["last_output"].as_str().and_then(|s| s.lines().rev().find(|l| !l.trim().is_empty())).unwrap_or_default();
    if said.is_empty() { tr("It closed straight away.") } else { format!("{} {said}", tr("It closed straight away. It said:")) }
}

/// The sidebar's Pinned section: nothing until something is pinned.
pub fn section(app: &mut CraftApp, ui: &mut Ui, fold: bool) {
    if app.pins.is_empty() {
        return;
    }
    let t = Tokens::get(ui.ctx());
    let collapsed = app.state.pins_collapsed;
    let arrow = |ui: &mut Ui| {
        let (rect, resp) = ui.allocate_exact_size(Vec2::splat(18.0), egui::Sense::click());
        icons::paint(ui, rect, if collapsed { "chevron-right" } else { "chevron-down" }, 14.0, t.icon);
        resp
    };
    // Folded, the arrow stays where the heading was, so nothing moves.
    let r = if fold {
        crate::sidebar::centred_row(ui, 18.0, arrow)
    } else {
        ui.horizontal(|ui| {
            ui.add_space(12.0);
            widgets::caption(ui, "Pinned");
            arrow(ui)
        })
        .inner
    };
    let r = r.on_hover_text(tr(if collapsed { "Show pinned builds" } else { "Hide pinned builds" }));
    widgets::named(r.clone(), "Pinned builds");
    if r.clicked() {
        app.state.pins_collapsed = !collapsed;
    }
    ui.add_space(4.0);
    if collapsed {
        crate::sidebar::section_gap(ui, fold, 14.0);
        return;
    }
    let mut open = None;
    for row in app.pins.clone() {
        let status = row.running.then_some((t.success, "Running", false));
        let r = crate::sidebar::row(ui, "pin", &row.pin.name, status, false);
        if fold && row.running {
            ui.painter().circle_filled(egui::pos2(r.rect.right() - 10.0, r.rect.top() + 9.0), 4.0, t.success);
        }
        let mode = match row.pin.mode {
            PinMode::Frozen => tr("Frozen copy"),
            PinMode::Light => tr("Light copy: shares big files with the project"),
            PinMode::Live => tr("Live: the project's latest build"),
        };
        let r = r.on_hover_text(format!("{} · {mode}", row.project_name));
        r.context_menu(|ui| menu(app, ui, &row));
        if r.clicked() {
            open = Some(row);
        }
    }
    if let Some(row) = open {
        app.open_pin(&row, false);
    }
    crate::sidebar::section_gap(ui, fold, 14.0);
}

/// The right-click menu on a pin.
fn menu(app: &mut CraftApp, ui: &mut Ui, row: &PinRow) {
    if row.running {
        if ui.button(tr("Open another copy")).on_hover_text(tr("Copies share the files it saves beside itself.")).clicked() {
            app.open_pin(row, true);
            ui.close();
        }
        if ui.button(tr("Close it")).clicked() {
            app.stop_pin(row);
            ui.close();
        }
    } else if ui.button(tr("Open")).clicked() {
        app.open_pin(row, false);
        ui.close();
    }
    if ui.button(tr("Show folder")).clicked() {
        app.act("project_open_folder", json!({"project": row.project, "pin": row.pin.id}), tr("Show the folder"));
        ui.close();
    }
    if ui.button(tr("Go to the project")).clicked() {
        if let Some(ws) = app.projects.iter().find(|w| w.root == row.project).cloned() {
            app.open_workspace(ws);
        }
        ui.close();
    }
    if ui.button(tr("Rename…")).clicked() {
        app.state.rename_input = row.pin.name.clone();
        app.state.modal = Some(Modal::PinRename(row.project.clone(), row.pin.id));
        ui.close();
    }
    ui.separator();
    if ui.add_enabled(!row.running, egui::Button::new(tr("Remove…"))).on_disabled_hover_text(tr("Close it first.")).clicked() {
        app.state.modal = Some(Modal::PinDelete(row.project.clone(), row.pin.id));
        ui.close();
    }
}

fn megabytes(bytes: u64) -> String {
    let mb = bytes.div_ceil(1_000_000).max(1);
    if mb >= 1000 { format!("{:.1} GB", mb as f64 / 1000.0) } else { format!("{mb} MB") }
}

/// Pin this build: a frozen copy (the default) or a light one, and a name.
pub fn pin_modal(app: &mut CraftApp, ui: &mut Ui, close: &mut bool) {
    let t = Tokens::get(ui.ctx());
    ui.set_width(560.0);
    ui.label(theme::heading(tr("Pin this build"), theme::SECTION));
    ui.add_space(4.0);
    ui.add(egui::Label::new(RichText::new(tr("Keep it in the sidebar to open any time, whatever later builds change.")).color(t.text_dim)).wrap());
    ui.add_space(12.0);
    let size = Vec2::new(268.0, 150.0);
    let mode = app.state.pin_draft.mode;
    ui.horizontal(|ui| {
        let frozen = widgets::choice_tile(
            ui,
            size,
            "lock",
            "A frozen copy (recommended)",
            "Keeps this version exactly as it is now. Later builds can't change or break it, and anything it saves stays with the copy.",
            mode == PinMode::Frozen,
        );
        if frozen.clicked() {
            app.state.pin_draft.mode = PinMode::Frozen;
        }
        let light = widgets::choice_tile(
            ui,
            size,
            "layers",
            "A light copy",
            "Saves space: copies the program and code, and shares dependencies and media with the project. A shared file rewritten in place changes here too.",
            mode == PinMode::Light,
        );
        if light.clicked() {
            app.state.pin_draft.mode = PinMode::Light;
        }
    });
    ui.add_space(8.0);
    let (note, color) = match &app.state.pin_draft.size {
        None => (tr("Working out how much space a copy takes…"), t.text_faint),
        Some(Err(e)) => (e.clone(), t.danger),
        Some(Ok((frozen, light))) => {
            let sizes = [("size", megabytes(*frozen)), ("light", megabytes(*light))];
            let sizes = sizes.each_ref().map(|(k, v)| (*k, v.as_str()));
            if *frozen >= BIG_COPY && mode == PinMode::Frozen {
                (trf("A frozen copy takes {size}. That's a lot of space: a light copy takes {light}.", &sizes), t.warning)
            } else {
                (trf("A frozen copy takes {size}; a light copy takes {light}.", &sizes), t.text_dim)
            }
        }
    };
    ui.add(egui::Label::new(RichText::new(note).color(color).size(theme::SMALL)).wrap());
    ui.add_space(10.0);
    widgets::caption(ui, "Name (optional)");
    let r = ui.add(
        egui::TextEdit::singleline(&mut app.state.pin_draft.name)
            .hint_text(tr("The project's name and round"))
            .desired_width(f32::INFINITY)
            .frame(widgets::text_field_frame(&t)),
    );
    widgets::named(r, "Pin name");
    ui.add_space(12.0);
    // A build with nothing to start can't be pinned; the estimate says so first.
    let ok = matches!(app.state.pin_draft.size, Some(Ok(_)));
    ui.horizontal(|ui| {
        if widgets::primary_icon(ui, Some("pin"), "Pin it", ok).clicked() && ok {
            let d = app.state.pin_draft.clone();
            let name = Some(d.name.trim()).filter(|n| !n.is_empty());
            app.act("project_pin_create", json!({"project": d.project, "mode": d.mode, "name": name}), tr("Pin a build"));
            *close = true;
        }
        if widgets::secondary(ui, None, "Cancel").clicked() {
            *close = true;
        }
    });
}

pub fn rename_modal(app: &mut CraftApp, ui: &mut Ui, project: &Path, id: u32, close: &mut bool) {
    let t = Tokens::get(ui.ctx());
    ui.label(theme::heading(tr("Rename the pin"), theme::SECTION));
    ui.add_space(8.0);
    let r = ui.add(egui::TextEdit::singleline(&mut app.state.rename_input).desired_width(f32::INFINITY).frame(widgets::text_field_frame(&t)));
    widgets::named(r.clone(), "Pin name");
    if !r.has_focus() && !r.lost_focus() {
        r.request_focus();
    }
    let ok = !app.state.rename_input.trim().is_empty();
    let enter = r.lost_focus() && ui.input(|i| i.key_pressed(egui::Key::Enter));
    ui.add_space(12.0);
    ui.horizontal(|ui| {
        if (widgets::primary_icon(ui, None, "Rename", ok).clicked() || enter) && ok {
            let name = app.state.rename_input.trim().to_string();
            app.act("project_pin_rename", json!({"project": project, "pin": id, "name": name}), tr("Rename the pin"));
            *close = true;
        }
        if widgets::secondary(ui, None, "Cancel").clicked() {
            *close = true;
        }
    });
}

pub fn delete_modal(app: &mut CraftApp, ui: &mut Ui, project: &Path, id: u32, close: &mut bool) {
    let t = Tokens::get(ui.ctx());
    let Some(row) = app.pins.iter().find(|p| p.project == project && p.pin.id == id).cloned() else {
        *close = true;
        return;
    };
    ui.label(theme::heading(trf("Remove {name}?", &[("name", &row.pin.name)]), theme::SECTION));
    ui.add_space(8.0);
    // A copy may hold what the program saved; say so, since it can't be brought back.
    let what = if row.pin.mode.keeps_copy() {
        tr("Its copy is deleted, with anything it saved there. The project itself stays as it is.")
    } else {
        tr("Only the pin goes; the project and its app stay as they are.")
    };
    ui.add(egui::Label::new(RichText::new(what).color(t.text_dim)).wrap());
    if row.pin.mode.keeps_copy() {
        ui.add_space(4.0);
        ui.label(RichText::new(tr("This can't be undone.")).color(t.danger).size(theme::SMALL));
    }
    ui.add_space(12.0);
    ui.horizontal(|ui| {
        if widgets::secondary(ui, Some("trash-2"), "Remove it").clicked() {
            app.act("project_pin_delete", json!({"project": project, "pin": id, "confirm": true}), tr("Remove a pin"));
            *close = true;
        }
        if widgets::primary(ui, "Keep it").clicked() {
            *close = true;
        }
    });
}
