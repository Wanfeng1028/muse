//! Simple-mode Game files: pick a game's folder, see the archives it packs its art in, look
//! inside one, and save pictures as PNG files, after the person confirms they may unpack the game.
//! Everything runs through the engine's `game_*` tools; this screen only shows and asks.

use crate::i18n::tr;
use crate::state::{GameFiles, Modal, PendingPicture};
use crate::theme::{self, Tokens};
use crate::{CraftApp, Pick, icons, widgets};
use craft_anything_engine::evidence::ToolError;
use egui::{RichText, Sense, Ui, Vec2};
use serde_json::{Value, json};
use std::path::PathBuf;

/// Rows shown at once in an archive (the filter narrows the rest).
const SHOWN: usize = 400;

/// How an archive kind reads, its icon, and whether pictures can be saved from it.
fn kind_label(kind: &str) -> (&'static str, &'static str, bool) {
    match kind {
        "unreal_pak" => ("Unreal pak", "package", true),
        "unreal_iostore" => ("Unreal IoStore", "package", false),
        "unity_assets" => ("Unity assets", "boxes", true),
        "unity_bundle" => ("Unity bundle", "boxes", true),
        _ => ("Archive", "file", false),
    }
}

pub fn show(app: &mut CraftApp, ui: &mut Ui) {
    let t = Tokens::get(ui.ctx());
    egui::ScrollArea::vertical().auto_shrink([false, false]).show(ui, |ui| {
        let full_w = ui.available_width();
        let w = full_w.min(1000.0) - 48.0;
        let pad = ((full_w - w) / 2.0).max(24.0);
        ui.add_space(40.0);
        ui.horizontal(|ui| {
            ui.add_space(pad);
            ui.vertical(|ui| {
                ui.set_width(w);
                ui.label(theme::heading(tr("Game files"), theme::TITLE));
                ui.add_space(4.0);
                ui.label(
                    RichText::new(tr("See what a game packs and save its pictures as PNG files. Only for games you made, or whose owner lets you."))
                        .size(theme::BODY)
                        .color(t.text_dim),
                );
                ui.add_space(18.0);
                // Every look at a game's files reads them, which Clean room never does.
                if !app.settings.deep_mode {
                    crate::engine_ui::deep_needed(app, ui);
                    return;
                }
                ui.horizontal(|ui| {
                    let label = if app.state.game.folder.is_some() { "Pick another game" } else { "Pick a game's folder" };
                    if widgets::primary_icon(ui, Some("folder-open"), label, true).clicked() {
                        app.pick(Pick::GameFolder);
                    }
                    if let Some(folder) = &app.state.game.folder {
                        ui.add_space(8.0);
                        ui.label(RichText::new(folder.display().to_string()).color(t.text_faint).size(theme::CAPTION));
                    }
                });
                ui.add_space(18.0);
                about(app, ui, w);
                archives(app, ui, w);
                contents(app, ui);
                ui.add_space(36.0);
            });
        });
    });
}

/// What the picked game is made of, and the way to ask about it.
fn about(app: &mut CraftApp, ui: &mut Ui, w: f32) {
    let t = Tokens::get(ui.ctx());
    let (Some(folder), Some(v)) = (app.state.game.folder.clone(), app.state.game.profile.as_ref()) else { return };
    let g = &v["game"];
    if g.is_null() {
        return;
    }
    let found = &g["found"];
    let mut ask = false;
    widgets::card(&t).show(ui, |ui| {
        ui.set_width(w - 34.0);
        ui.horizontal(|ui| {
            icons::show(ui, "puzzle", 20.0, t.accent_ink);
            ui.label(theme::heading(g["engine"].as_str().unwrap_or_default(), theme::CARD));
            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                ask = widgets::primary_icon(ui, Some("message-square"), "Ask about this game", true).clicked();
            });
        });
        if let Some(note) = found["note"].as_str() {
            ui.add_space(4.0);
            ui.label(RichText::new(note).color(t.text_dim).size(theme::BODY));
        }
        let stack = g["stack"].as_array().cloned().unwrap_or_default();
        if !stack.is_empty() {
            ui.add_space(10.0);
            widgets::caption(ui, "Built with");
            ui.horizontal_wrapped(|ui| {
                for s in &stack {
                    widgets::pill(ui, s["name"].as_str().unwrap_or_default(), t.text, t.raised).on_hover_text(s["what"].as_str().unwrap_or_default());
                }
            });
        }
        let own = g["other_groups"].as_array().into_iter().flatten().filter_map(Value::as_str).collect::<Vec<_>>();
        if !own.is_empty() {
            ui.add_space(10.0);
            widgets::caption(ui, "Its own code");
            ui.label(RichText::new(own.join(", ")).color(t.text_dim).size(theme::SMALL));
        }
        ui.add_space(10.0);
        let scenes = g["scenes"].as_u64().unwrap_or(0);
        let mut facts =
            vec![format!("{} · {} {}", crate::human_bytes(g["bytes"].as_u64().unwrap_or(0) as usize), g["files"].as_u64().unwrap_or(0), tr("files"))];
        if scenes > 0 {
            facts.push(format!("{scenes} {}", tr(if scenes == 1 { "scene" } else { "scenes" })));
        }
        ui.label(RichText::new(facts.join(" · ")).color(t.text_faint).size(theme::CAPTION));
    });
    ui.add_space(18.0);
    if ask {
        app.open_path(folder);
    }
}

fn archives(app: &mut CraftApp, ui: &mut Ui, w: f32) {
    let t = Tokens::get(ui.ctx());
    let g = &app.state.game;
    if g.looking {
        widgets::working(ui, "Looking for the game's files…", None);
        return;
    }
    if g.folder.is_none() {
        return;
    }
    if g.archives.is_empty() {
        widgets::empty_state(ui, "package", "No game files here", "No Unreal or Unity archives were found. Pick the folder the game is installed in.");
        return;
    }
    widgets::caption(ui, "Archives");
    ui.add_space(6.0);
    let mut open = None;
    for a in &g.archives {
        let (path, kind) = (a["path"].as_str().unwrap_or_default(), a["kind"].as_str().unwrap_or_default());
        let (label, icon, _) = kind_label(kind);
        let selected = g.open.as_deref() == Some(path);
        let (rect, resp) = ui.allocate_exact_size(Vec2::new(w, 44.0), Sense::click());
        let fill = if selected {
            t.accent_soft
        } else if resp.hovered() {
            t.raised
        } else {
            t.card
        };
        ui.painter().rect_filled(rect, t.radius, fill);
        let icon_rect = egui::Rect::from_center_size(egui::pos2(rect.left() + 24.0, rect.center().y), Vec2::splat(20.0));
        icons::paint(ui, icon_rect, icon, 18.0, if selected { t.accent_ink } else { t.text_dim });
        let name = a["name"].as_str().unwrap_or(path);
        ui.painter().text(egui::pos2(rect.left() + 46.0, rect.center().y), egui::Align2::LEFT_CENTER, name, theme::medium(theme::SMALL), t.text);
        let detail = format!("{} · {}", tr(label), crate::human_bytes(a["size"].as_u64().unwrap_or(0) as usize));
        ui.painter().text(
            egui::pos2(rect.right() - 14.0, rect.center().y),
            egui::Align2::RIGHT_CENTER,
            detail,
            egui::FontId::proportional(theme::CAPTION),
            t.text_faint,
        );
        if widgets::named(resp, name).on_hover_cursor(egui::CursorIcon::PointingHand).clicked() {
            open = Some((path.to_string(), kind.to_string()));
        }
        ui.add_space(4.0);
    }
    if let Some((path, kind)) = open {
        open_archive(app, path, kind);
    }
}

fn open_archive(app: &mut CraftApp, path: String, kind: String) {
    let g = &mut app.state.game;
    g.open = Some(path.clone());
    g.open_kind = kind.clone();
    g.rows.clear();
    g.filter.clear();
    g.loading = true;
    // A bundle's pictures are its serialized files' Texture2D objects, listed like an .assets file's.
    let (tool, params) = match kind.as_str() {
        "unreal_pak" => ("game_pak_list", json!({"path": path, "filter": ".uasset", "limit": 20000})),
        "unity_assets" | "unity_bundle" => ("game_unity_list", json!({"path": path, "filter": "texture2d", "limit": 20000})),
        "unreal_iostore" => ("game_iostore_list", json!({"path": path, "limit": 2000})),
        _ => ("game_unity_bundle_list", json!({"path": path, "limit": 2000})),
    };
    app.act(tool, params, tr("Read a game's files"));
}

fn contents(app: &mut CraftApp, ui: &mut Ui) {
    let t = Tokens::get(ui.ctx());
    let g = &app.state.game;
    let Some(open) = g.open.clone() else { return };
    let (_, _, saves) = kind_label(&g.open_kind);
    ui.add_space(18.0);
    let name = std::path::Path::new(&open).file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
    ui.label(theme::heading(format!("{} {name}", tr("Inside")), theme::SECTION));
    ui.add_space(6.0);
    if g.loading {
        widgets::working(ui, "Reading what's inside…", None);
        return;
    }
    if g.open_kind == "unreal_iostore" {
        ui.label(RichText::new(tr("Pictures can't be saved from IoStore containers yet; you can see what's inside.")).color(t.text_faint).size(theme::CAPTION));
        ui.add_space(6.0);
    }
    let r = ui.add(
        egui::TextEdit::singleline(&mut app.state.game.filter)
            .hint_text(tr("Filter by name"))
            .desired_width(320.0)
            .frame(widgets::text_field_frame_compact(&t)),
    );
    widgets::named(r, "Filter the files");
    ui.add_space(8.0);
    let needle = app.state.game.filter.trim().to_lowercase();
    let rows: Vec<Value> =
        app.state.game.rows.iter().filter(|r| needle.is_empty() || row_name(r).to_lowercase().contains(&needle)).take(SHOWN).cloned().collect();
    if rows.is_empty() {
        widgets::empty_state(ui, "search", "Nothing to show", if needle.is_empty() { "" } else { "Nothing matches the filter." });
        return;
    }
    let mut save = None;
    for r in &rows {
        ui.horizontal(|ui| {
            ui.label(RichText::new(row_name(r)).size(theme::SMALL));
            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                if saves && widgets::secondary(ui, Some("download"), "Save picture").clicked() {
                    save = Some(r.clone());
                }
                ui.label(RichText::new(row_detail(r)).color(t.text_faint).size(theme::CAPTION));
            });
        });
        ui.add_space(2.0);
    }
    let total = app.state.game.rows.len();
    if total > rows.len() && needle.is_empty() {
        ui.label(
            RichText::new(format!("{} {} {}", tr("Showing"), rows.len(), tr("— use the filter to find the rest."))).color(t.text_faint).size(theme::CAPTION),
        );
    }
    if let Some(item) = save {
        ask_to_save(app, open, item);
    }
}

/// A row's name: a path in a pak, an object's name in a Unity file.
fn row_name(r: &Value) -> String {
    r["path"].as_str().or_else(|| r["name"].as_str()).map_or_else(|| format!("#{}", r["path_id"]), str::to_string)
}

fn row_detail(r: &Value) -> String {
    let size = r["size"].as_u64().map(|s| crate::human_bytes(s as usize)).unwrap_or_default();
    // A pak's "none" compression says nothing to a person; a class or a method does.
    match r["class"].as_str().or_else(|| r["compression"].as_str().filter(|c| *c != "none")) {
        Some(c) => format!("{c} · {size}"),
        None => size,
    }
}

/// Saving starts with the person's word that they may unpack this game (asked once per folder),
/// then where to save.
fn ask_to_save(app: &mut CraftApp, archive: String, item: Value) {
    let base = row_name(&item);
    let stem = base.rsplit(['/', '\\']).next().unwrap_or(&base).trim_end_matches(".uasset").to_string();
    let g = &mut app.state.game;
    g.pending = Some(PendingPicture { archive, kind: g.open_kind.clone(), item, name: format!("{stem}.png") });
    if g.permitted.is_some() && g.permitted == g.folder {
        app.pick(Pick::SavePicture);
    } else {
        app.state.modal = Some(Modal::GamePermission);
    }
}

/// The question asked before a game's files are unpacked.
pub fn permission_modal(app: &mut CraftApp, ui: &mut Ui, close: &mut bool) {
    let t = Tokens::get(ui.ctx());
    let (rect, _) = ui.allocate_exact_size(Vec2::splat(52.0), Sense::hover());
    ui.painter().rect_filled(rect, t.radius, t.accent_soft);
    icons::paint(ui, rect, "shield-check", 26.0, t.accent_ink);
    ui.add_space(10.0);
    ui.label(theme::heading(tr("Do you have permission?"), theme::SECTION));
    ui.add_space(4.0);
    ui.label(
        RichText::new(tr(
            "Only take pictures out of games you made, or whose owner allows it. A game's art is usually protected by copyright and by the game's licence.",
        ))
        .color(t.text_dim),
    );
    ui.add_space(16.0);
    ui.horizontal(|ui| {
        if widgets::primary_icon(ui, Some("shield-check"), "I have permission", true).clicked() {
            app.state.game.permitted.clone_from(&app.state.game.folder);
            *close = true;
            app.pick(Pick::SavePicture);
        }
        if widgets::secondary(ui, None, "Cancel").clicked() {
            app.state.game.pending = None;
            *close = true;
        }
    });
}

/// The game's folder was picked: look for its archives.
pub fn folder_picked(app: &mut CraftApp, folder: PathBuf) {
    app.state.game = GameFiles { folder: Some(folder.clone()), looking: true, permitted: app.state.game.permitted.clone(), ..Default::default() };
    app.act("game_archives_list", json!({"path": folder.display().to_string()}), tr("Find a game's files"));
    app.act("core_target_triage", json!({"path": folder.display().to_string()}), tr("Look at a game"));
}

/// Where to save the pending picture was picked: save it.
pub fn save_to(app: &mut CraftApp, mut output: PathBuf) {
    let Some(p) = app.state.game.pending.take() else { return };
    if output.extension().is_none() {
        output.set_extension("png");
    }
    let output = output.display().to_string();
    match p.kind.as_str() {
        "unreal_pak" => {
            let params = json!({"path": p.archive, "file": p.item["path"], "output": output, "permission": true});
            app.act("game_unreal_texture_export", params, tr("Save a picture"));
        }
        "unity_assets" | "unity_bundle" => {
            // A bundle's rows say which serialized file inside it holds the object.
            let params = json!({"path": p.archive, "file": p.item["file"], "path_id": p.item["path_id"], "output": output});
            app.act("game_unity_asset_export", params, tr("Save a picture"));
        }
        _ => {}
    }
}

/// The name the save dialog suggests.
pub fn suggested_name(app: &CraftApp) -> String {
    app.state.game.pending.as_ref().map_or_else(|| "picture.png".to_string(), |p| p.name.clone())
}

/// A game tool finished.
pub fn tool_done(app: &mut CraftApp, tool: &str, result: Result<Value, ToolError>) {
    let g = &mut app.state.game;
    match (tool, result) {
        ("game_archives_list", Ok(v)) => {
            g.looking = false;
            g.archives = v["archives"].as_array().cloned().unwrap_or_default();
        }
        ("game_archives_list", Err(e)) => {
            g.looking = false;
            app.toast(format!("{} {}", tr("Couldn't look through that folder."), e.message), true);
        }
        ("core_target_triage", Ok(v)) => g.profile = Some(v),
        // The archives' search says what went wrong with the folder.
        ("core_target_triage", Err(_)) => {}
        ("game_unreal_texture_export" | "game_unity_asset_export", Ok(v)) => {
            let msg = format!("{} {}", tr("Saved"), v["output"].as_str().unwrap_or_default());
            app.toast(msg, false);
        }
        (_, Ok(v)) => {
            g.loading = false;
            g.rows = v["files"].as_array().or_else(|| v["objects"].as_array()).cloned().unwrap_or_default();
        }
        (_, Err(e)) => {
            g.loading = false;
            app.toast(e.for_people(), true);
        }
    }
}
