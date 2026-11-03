//! Rename, duplicate and delete a project, from its row in the sidebar (right-click) or its page.
//! Each goes through its tool (project_rename, project_duplicate, project_delete), as the CLI and
//! MCP clients do; deleting asks first and says what stays.

use crate::i18n::{tr, trf};
use crate::state::{Modal, Screen};
use crate::theme::{self, Tokens};
use crate::{CraftApp, icons, widgets};
use craft_anything_engine::evidence::ToolError;
use craft_anything_engine::workspace::Workspace;
use egui::{RichText, Ui, Vec2};
use serde_json::{Value, json};
use std::path::Path;

impl CraftApp {
    pub fn rename_project(&mut self, root: &Path, name: &str) {
        self.act("project_rename", json!({"project": root, "name": name}), tr("Rename the project"));
    }

    pub fn duplicate_project(&mut self, root: &Path) {
        self.act("project_duplicate", json!({"project": root}), tr("Duplicate the project"));
    }

    /// Delete a project (after the person confirmed). Never one that's building.
    pub fn delete_project(&mut self, root: &Path) {
        if self.runs.is_busy(root) {
            return self.toast(tr("Pause the build first, then delete the project."), true);
        }
        self.act("project_delete", json!({"project": root, "confirm": true}), tr("Delete the project"));
    }

    /// A rename, duplicate or delete finished.
    pub(crate) fn managed(&mut self, tool: &str, result: Result<Value, ToolError>) {
        let v = match result {
            Ok(v) => v,
            Err(e) => return self.toast(e.for_people(), true),
        };
        let root = v.get("project").or_else(|| v.get("deleted")).and_then(Value::as_str).map(std::path::PathBuf::from);
        match tool {
            "project_rename" => {
                if let Some(ws) = self.workspace.as_mut().filter(|w| Some(&w.root) == root.as_ref()) {
                    let _ = ws.reload();
                }
            }
            "project_duplicate" => {
                let name = v.get("name").and_then(Value::as_str).unwrap_or_default();
                self.toast(trf("Made a copy: {name}", &[("name", name)]), false);
            }
            _ => {
                if self.workspace.as_ref().is_some_and(|w| Some(&w.root) == root.as_ref()) {
                    self.workspace = None;
                    self.state.feed.clear();
                    self.state.screen = Screen::Home;
                }
                if let Some(r) = &root {
                    self.usage.remove(r);
                    self.state.unsent.remove(r);
                }
                let kept = v.get("your_files_kept").and_then(Value::as_bool).unwrap_or(false);
                self.toast(tr(if kept { "Deleted. Your own files are still in the folder." } else { "Deleted." }), false);
            }
        }
        self.refresh_projects();
    }
}

/// The right-click menu on a project in the sidebar.
pub fn menu(app: &mut CraftApp, ui: &mut Ui, ws: &Workspace) {
    if ui.button(tr("Rename…")).clicked() {
        ask_rename(app, ws);
        ui.close();
    }
    if ui.button(tr("Duplicate")).clicked() {
        app.duplicate_project(&ws.root);
        ui.close();
    }
    ui.separator();
    if ui.add_enabled(!app.runs.is_busy(&ws.root), egui::Button::new(tr("Delete…"))).on_disabled_hover_text(tr("Pause the build first.")).clicked() {
        app.state.modal = Some(Modal::Delete(ws.root.clone()));
        ui.close();
    }
}

/// The same, as quiet links on the project's page.
pub fn buttons(app: &mut CraftApp, ui: &mut Ui, ws: &Workspace) {
    if widgets::secondary(ui, None, "Rename").clicked() {
        ask_rename(app, ws);
    }
    if widgets::secondary(ui, Some("copy"), "Duplicate").on_hover_text(tr("A copy to try something else from here.")).clicked() {
        app.duplicate_project(&ws.root);
    }
    if !app.runs.is_busy(&ws.root) && icons::button(ui, "trash-2", 30.0, false, "Delete the project").clicked() {
        app.state.modal = Some(Modal::Delete(ws.root.clone()));
    }
}

fn ask_rename(app: &mut CraftApp, ws: &Workspace) {
    app.state.rename_input = ws.manifest.name.clone();
    app.state.modal = Some(Modal::Rename(ws.root.clone()));
}

fn project<'a>(app: &'a CraftApp, root: &Path) -> Option<&'a Workspace> {
    app.workspace.iter().chain(&app.projects).find(|w| w.root == root)
}

pub fn rename_modal(app: &mut CraftApp, ui: &mut Ui, root: &Path, close: &mut bool) {
    let t = Tokens::get(ui.ctx());
    ui.label(theme::heading(tr("Rename the project"), theme::SECTION));
    ui.add_space(8.0);
    let r = ui.add(egui::TextEdit::singleline(&mut app.state.rename_input).desired_width(f32::INFINITY).frame(widgets::text_field_frame(&t)));
    widgets::named(r.clone(), "Project name");
    if !r.has_focus() && !r.lost_focus() {
        r.request_focus();
    }
    let ok = !app.state.rename_input.trim().is_empty();
    let enter = r.lost_focus() && ui.input(|i| i.key_pressed(egui::Key::Enter));
    ui.add(egui::Label::new(RichText::new(tr("Only its name changes; its folder stays where it is.")).color(t.text_faint).size(theme::SMALL)).wrap());
    ui.add_space(12.0);
    ui.horizontal(|ui| {
        if (widgets::primary_icon(ui, None, "Rename", ok).clicked() || enter) && ok {
            let name = app.state.rename_input.trim().to_string();
            app.rename_project(root, &name);
            *close = true;
        }
        if widgets::secondary(ui, None, "Cancel").clicked() {
            *close = true;
        }
    });
}

pub fn delete_modal(app: &mut CraftApp, ui: &mut Ui, root: &Path, close: &mut bool) {
    let t = Tokens::get(ui.ctx());
    let Some(ws) = project(app, root).cloned() else {
        *close = true;
        return;
    };
    ui.horizontal(|ui| {
        let (rect, _) = ui.allocate_exact_size(Vec2::splat(40.0), egui::Sense::hover());
        ui.painter().rect_filled(rect, t.radius, t.raised);
        icons::paint(ui, rect, "trash-2", 20.0, t.danger);
        ui.label(theme::heading(trf("Delete {name}?", &[("name", &ws.manifest.name)]), theme::SECTION));
    });
    ui.add_space(8.0);
    // What goes and what stays, in so many words: it can't be undone.
    let m = &ws.manifest;
    let what = if m.app_in_root || !m.start_files.is_empty() {
        tr("Craft Anything's records, checks and anything it built in app/ are deleted. Your own files in the folder stay as they are.")
    } else {
        tr("Its folder is deleted with everything in it: what was built, the checks and the conversation.")
    };
    ui.add(egui::Label::new(RichText::new(what).color(t.text_dim)).wrap());
    ui.add(egui::Label::new(RichText::new(crate::short_path(&ws.root)).font(theme::mono(12.0)).color(t.text_faint)).truncate());
    ui.add_space(4.0);
    ui.label(RichText::new(tr("This can't be undone.")).color(t.danger).size(theme::SMALL));
    ui.add_space(12.0);
    ui.horizontal(|ui| {
        if widgets::secondary(ui, Some("trash-2"), "Delete it").clicked() {
            app.delete_project(root);
            *close = true;
        }
        if widgets::primary(ui, "Keep it").clicked() {
            *close = true;
        }
    });
}
