//! Where a new project goes: the projects folder from Settings, or a folder the person picks,
//! which may already have their files. Then they're asked (unless they said not to) whether those
//! files are the app to edit in place or material to start from.

use crate::i18n::{tr, trf};
use crate::state::Modal;
use crate::theme::{self, Tokens};
use crate::{CraftApp, Pick, widgets};
use craft_anything_engine::workspace::{self, ExistingFiles, FolderState, Workspace};
use egui::{RichText, Ui, Vec2};
use std::path::PathBuf;

/// The Make screen's "Saved in" line: the folder the project will be in, and a way to pick another.
pub fn make_line(app: &mut CraftApp, ui: &mut Ui) {
    let t = Tokens::get(ui.ctx());
    let d = &app.state.make;
    let (place, how) = match &d.folder {
        Some(f) => (
            f.display().to_string(),
            match (d.folder_files.is_some(), d.existing) {
                (false, _) => None,
                (true, Some(ExistingFiles::Edit)) => Some(tr("your files there are the app, edited in place")),
                (true, Some(ExistingFiles::StartFrom)) => Some(tr("the app is built beside your files, starting from them")),
                (true, None) => Some(tr("say how to use the files there")),
            },
        ),
        None => (trf("a new folder in {dir}", &[("dir", &app.settings.projects_dir().display().to_string())]), None),
    };
    let picked = d.folder.is_some();
    // Where it goes (and what the files there are), then what can be changed, each on its own line.
    ui.horizontal(|ui| {
        crate::icons::show(ui, "folder", 14.0, t.text_faint);
        ui.label(RichText::new(tr("Saved in")).size(theme::SMALL).color(t.text_dim));
        ui.add(egui::Label::new(RichText::new(&place).size(theme::SMALL).color(t.text)).truncate()).on_hover_text(&place);
    });
    ui.horizontal_wrapped(|ui| {
        ui.add_space(22.0);
        if let Some(how) = how {
            ui.label(RichText::new(how).size(theme::SMALL).color(t.text_dim));
            if widgets::link(ui, "Change").clicked() {
                app.state.modal = Some(Modal::ExistingFiles);
            }
            ui.label(RichText::new("·").size(theme::SMALL).color(t.text_faint));
        }
        if widgets::link(ui, if picked { "Pick another folder…" } else { "Choose a folder…" }).clicked() {
            app.pick(Pick::ProjectFolder);
        }
        if picked {
            ui.label(RichText::new("·").size(theme::SMALL).color(t.text_faint));
            if widgets::link(ui, "Use the projects folder").clicked() {
                clear(app);
            }
        }
    });
}

fn clear(app: &mut CraftApp) {
    let d = &mut app.state.make;
    d.folder = None;
    d.folder_files = None;
    d.existing = None;
}

/// A folder was picked for the new project: an existing project opens; one with files asks what
/// they are (or uses the answer from Settings).
pub fn picked(app: &mut CraftApp, folder: PathBuf) {
    match workspace::folder_state(&folder) {
        Ok(FolderState::Project) => match Workspace::open(&folder) {
            Ok(ws) => {
                app.toast(tr("That folder is already a project, so it's open now."), false);
                app.open_workspace(ws);
                app.remember_project(&folder);
            }
            Err(e) => app.toast(e.for_people(), true),
        },
        Ok(FolderState::Empty) => {
            clear(app);
            app.state.make.folder = Some(folder);
        }
        Ok(FolderState::HasFiles { names, count }) => {
            clear(app);
            let d = &mut app.state.make;
            d.folder = Some(folder);
            d.folder_files = Some((names, count));
            match app.settings.existing_files {
                Some(choice) => choose(app, choice),
                None => app.state.modal = Some(Modal::ExistingFiles),
            }
        }
        Err(e) => app.toast(e.for_people(), true),
    }
}

/// Use the picked folder's files this way, unless something there is named like Craft Anything's
/// own files: then the folder isn't used (nothing of theirs is ever replaced).
fn choose(app: &mut CraftApp, choice: ExistingFiles) {
    let Some(folder) = app.state.make.folder.clone() else { return };
    let clash = workspace::clashes(&folder, choice);
    if clash.is_empty() {
        app.state.make.existing = Some(choice);
    } else {
        clear(app);
        let names = clash.join(", ");
        app.toast(
            trf(
                "That folder already has {names}, where Craft Anything keeps its own files. Pick another folder, or move those out first.",
                &[("names", &names)],
            ),
            true,
        );
    }
}

/// "This folder already has files": the app itself, or material to start from.
pub fn existing_modal(app: &mut CraftApp, ui: &mut Ui, close: &mut bool) {
    let t = Tokens::get(ui.ctx());
    ui.set_width(560.0);
    let Some(folder) = app.state.make.folder.clone() else {
        *close = true;
        return;
    };
    let (names, count) = app.state.make.folder_files.clone().unwrap_or_default();
    ui.label(theme::heading(tr("This folder already has files"), theme::SECTION));
    ui.add_space(4.0);
    let some = names.iter().take(4).cloned().collect::<Vec<_>>().join(", ");
    let more = if count > 4 { trf(" and {n} more", &[("n", &(count - 4).to_string())]) } else { String::new() };
    ui.add(egui::Label::new(RichText::new(format!("{}: {some}{more}.", folder.display())).color(t.text_dim)).wrap());
    ui.add_space(4.0);
    ui.label(RichText::new(tr("How should the builder use them?")).color(t.text));
    ui.add_space(12.0);
    let current = app.state.make.existing;
    let size = Vec2::new(268.0, 168.0);
    let mut chosen = None;
    ui.horizontal(|ui| {
        let edit = widgets::choice_tile(
            ui,
            size,
            "code",
            "They're my app: edit them in place",
            "The builder works on these files directly and keeps what works. Craft Anything adds a few records of its own beside them.",
            current == Some(ExistingFiles::Edit),
        );
        if edit.clicked() {
            chosen = Some(ExistingFiles::Edit);
        }
        let start = widgets::choice_tile(
            ui,
            size,
            "layers",
            "Start from them",
            "The builder reads them (code, notes, pictures) and builds the app in a new app folder beside them. Your files stay as they are.",
            current == Some(ExistingFiles::StartFrom),
        );
        if start.clicked() {
            chosen = Some(ExistingFiles::StartFrom);
        }
    });
    ui.add_space(12.0);
    let mut remember = app.state.make.remember_existing;
    if widgets::toggle(ui, &mut remember, "Don't ask again (you can change this in Settings)").changed() {
        app.state.make.remember_existing = remember;
    }
    ui.add_space(12.0);
    if widgets::secondary(ui, None, "Cancel: don't use this folder").clicked() {
        clear(app);
        *close = true;
    }
    if let Some(choice) = chosen {
        if app.state.make.remember_existing {
            app.settings.existing_files = Some(choice);
            app.settings_changed();
        }
        choose(app, choice);
        *close = true;
    }
}

/// Settings: the answer used when a picked folder has files.
pub const EXISTING_CHOICES: [(&str, Option<ExistingFiles>); 3] =
    [("Ask each time", None), ("Edit them in place", Some(ExistingFiles::Edit)), ("Start from them", Some(ExistingFiles::StartFrom))];

impl CraftApp {
    /// Keep a project that lives outside the project folders in the list.
    pub fn remember_project(&mut self, root: &std::path::Path) {
        if self.settings.remember_project(root) {
            self.settings_changed();
            self.refresh_projects();
        }
    }

    /// Settings: list projects from another folder too.
    pub fn add_project_folder(&mut self, folder: PathBuf) {
        if !self.settings.project_locations().contains(&folder) {
            self.settings.project_folders.push(folder);
            self.settings_changed();
            self.refresh_projects();
        }
    }

    /// Settings: stop listing a folder's projects (nothing is deleted).
    pub fn remove_project_folder(&mut self, folder: &std::path::Path) {
        self.settings.project_folders.retain(|f| f != folder);
        self.settings_changed();
        self.refresh_projects();
    }
}
