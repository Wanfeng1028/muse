//! The left sidebar on the Simple screens: New project (make something, or just look inside
//! something), pinned builds (`crate::pins`), your projects, and Settings. Chrome background, quiet section captions, rounded rows with a soft
//! fill on the one that's open.

use crate::i18n::tr;
use crate::make::{ago, status_shown};
use crate::state::Screen;
use crate::theme::{self, Tokens};
use crate::{CraftApp, icons, widgets};
use egui::{RichText, Sense, Ui, Vec2};

pub const WIDTH: f32 = 248.0;
/// Folded to icons.
pub const FOLDED: f32 = 56.0;
/// Below this window width the sidebar folds by itself, leaving the room to the screen.
const FOLD_BELOW: f32 = 900.0;

/// Folded: by the person, or because the window is narrow.
pub fn folded(app: &CraftApp, ctx: &egui::Context) -> bool {
    app.state.sidebar_folded || ctx.content_rect().width() < FOLD_BELOW
}

pub fn width(app: &CraftApp, ctx: &egui::Context) -> f32 {
    if folded(app, ctx) { FOLDED } else { WIDTH }
}
const ROW_H: f32 = 34.0;
/// Room above the first row and below Settings.
const EDGE: f32 = 14.0;

pub fn show(app: &mut CraftApp, ui: &mut Ui) {
    let t = Tokens::get(ui.ctx());
    let fold = folded(app, ui.ctx());
    ui.data_mut(|d| d.insert_temp(egui::Id::new("sidebar-folded"), fold));
    let w = ui.available_width();
    // Settings sits at the bottom under a rule, as far from the window's edge as New project is
    // from the title bar; everything else scrolls above it.
    let gap = ui.spacing().item_spacing.y;
    let top_h = (ui.available_height() - (gap + 10.0 + ROW_H + EDGE)).max(120.0);
    ui.allocate_ui_with_layout(Vec2::new(w, top_h), egui::Layout::top_down(egui::Align::Min), |ui| {
        ui.set_min_height(top_h);
        ui.add_space(EDGE);
        // Fold to icons, or open again (a narrow window keeps it folded).
        let narrow = ui.ctx().content_rect().width() < FOLD_BELOW;
        if !narrow {
            let (icon, tip) = if fold { ("chevron-right", "Show the sidebar") } else { ("chevron-left", "Fold the sidebar") };
            // Over the row icons when folded, in the corner when open.
            let layout = if fold { egui::Layout::top_down(egui::Align::Center) } else { egui::Layout::right_to_left(egui::Align::Min) };
            ui.with_layout(layout, |ui| {
                if icons::button(ui, icon, 24.0, false, tip).clicked() {
                    app.state.sidebar_folded = !fold;
                }
            });
        }
        let home = app.state.screen == Screen::Home;
        if row(ui, "plus", "New project", None, home).clicked() {
            app.state.screen = Screen::Home;
        }
        // Advanced mode's workbench sits beside the projects, so builds stay in sight.
        if !app.beginner() && row(ui, "microscope", "Workbench", None, false).clicked() {
            app.state.screen = Screen::Workbench;
            app.ensure_rail_loaded();
        }
        section_gap(ui, fold, 18.0);
        // Pinned builds, between the screens and the projects, to open in one click.
        crate::pins::section(app, ui, fold);
        // Folded, the heading's words don't fit: the rule and the icon stay, on the same line, so
        // nothing moves when the sidebar folds.
        let refresh = |ui: &mut Ui| icons::button(ui, "refresh-cw", 22.0, false, "Look for projects again").clicked();
        let again = if fold {
            centred_row(ui, 22.0, refresh)
        } else {
            ui.horizontal(|ui| {
                ui.add_space(12.0);
                widgets::caption(ui, "Projects");
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), refresh).inner
            })
            .inner
        };
        if again {
            app.refresh_projects();
        }
        ui.add_space(4.0);
        egui::ScrollArea::vertical().auto_shrink([false, false]).show(ui, |ui| {
            if app.projects.is_empty() && !fold {
                egui::Frame::new().inner_margin(egui::Margin { left: 12, right: 8, top: 2, bottom: 2 }).show(ui, |ui| {
                    ui.label(RichText::new(tr("Nothing made yet. What you make shows up here.")).color(t.text_faint).size(theme::SMALL));
                });
                return;
            }
            let open_root = (app.state.screen == Screen::Project).then(|| app.workspace.as_ref().map(|w| w.root.clone())).flatten();
            let mut open = None;
            for ws in app.projects.clone().iter() {
                let m = &ws.manifest;
                let (label, fg, _) = status_shown(app, ws, &t);
                // What needs the person is said in words, not only a dot.
                let urgent = matches!(label, "Needs you" | "Interrupted");
                let r = row(ui, crate::make::project_icon(m), &m.name, Some((fg, label, urgent)), open_root.as_ref() == Some(&ws.root)).on_hover_text(format!(
                    "{} · {}",
                    m.request,
                    ago(m.updated_ms)
                ));
                // Right-click: rename, duplicate or delete it.
                r.context_menu(|ui| crate::manage::menu(app, ui, ws));
                if r.clicked() {
                    open = Some(ws.clone());
                }
            }
            if let Some(ws) = open {
                app.open_workspace(ws);
            }
        });
    });
    ui.painter().hline(ui.max_rect().x_range(), ui.cursor().top() + 1.0, egui::Stroke::new(1.0, t.separator));
    ui.add_space(10.0);
    if row(ui, "settings", "Settings", None, app.state.settings_open).clicked() {
        app.state.settings_open = !app.state.settings_open;
    }
}

/// A folded section's heading: a row as tall as the open one, with something `width` wide centred.
pub(crate) fn centred_row<R>(ui: &mut Ui, width: f32, add: impl FnOnce(&mut Ui) -> R) -> R {
    ui.horizontal(|ui| {
        ui.add_space(((ui.available_width() - width) / 2.0).max(0.0));
        add(ui)
    })
    .inner
}

/// The space before a section. Folded, a rule across it takes the place of the section's name.
pub(crate) fn section_gap(ui: &mut Ui, fold: bool, height: f32) {
    let y = ui.cursor().top() + height / 2.0;
    ui.add_space(height);
    if fold {
        let t = Tokens::get(ui.ctx());
        ui.painter().hline(ui.max_rect().shrink2(Vec2::new(12.0, 0.0)).x_range(), y, egui::Stroke::new(1.0, t.separator));
    }
}

/// One sidebar row: icon, label, and for projects a status dot, or the status in words when it
/// needs the person (`urgent`). `on` = the open one.
pub(crate) fn row(ui: &mut Ui, icon: &str, label: &str, status: Option<(egui::Color32, &str, bool)>, on: bool) -> egui::Response {
    let t = Tokens::get(ui.ctx());
    let fold = ui.data(|d| d.get_temp::<bool>(egui::Id::new("sidebar-folded")).unwrap_or(false));
    let (rect, resp) = ui.allocate_exact_size(Vec2::new(ui.available_width(), ROW_H), Sense::click());
    let h = widgets::hover_t(ui, &resp);
    let fill = if on { t.pressed } else { theme::mix(egui::Color32::TRANSPARENT, t.hover, h) };
    ui.painter().rect_filled(rect, t.radius, fill);
    let ink = if on { t.text } else { theme::mix(t.text_dim, t.text, h) };
    // Project names are shown as written; the app's own rows are translated.
    let text = if status.is_some() { label.to_string() } else { tr(label) };
    let icon_x = if fold { rect.center().x } else { rect.left() + 22.0 };
    icons::paint(ui, egui::Rect::from_center_size(egui::pos2(icon_x, rect.center().y), Vec2::splat(16.0)), icon, 16.0, if on { t.text } else { t.icon });
    let name = match status {
        Some((_, s, _)) => format!("{text}, {}", tr(s)),
        None => text.clone(),
    };
    // Folded: the icon, a dot for a project that needs the person, and the name on hover.
    if fold {
        if let Some((color, _, urgent)) = status
            && urgent
        {
            ui.painter().circle_filled(egui::pos2(rect.right() - 10.0, rect.top() + 9.0), 4.0, color);
        }
        widgets::focus_ring(ui, &resp, rect);
        resp.widget_info(|| egui::WidgetInfo::selected(egui::WidgetType::Button, true, on, &name));
        return resp.on_hover_text(name).on_hover_cursor(egui::CursorIcon::PointingHand);
    }
    // An urgent status is a small pill on the right; the name gives way to it.
    let pill = status.filter(|s| s.2).map(|(color, s, _)| (color, ui.painter().layout_no_wrap(tr(s), theme::semibold(theme::CAPTION), color)));
    let right = match (&pill, status) {
        (Some((_, g)), _) => g.size().x + 26.0,
        (None, Some(_)) => 26.0,
        (None, None) => 10.0,
    };
    let max_w = (rect.width() - 40.0 - right).max(20.0);
    let mut job = egui::text::LayoutJob::simple_singleline(text.clone(), egui::FontId::proportional(theme::SMALL), ink);
    job.wrap = egui::text::TextWrapping::truncate_at_width(max_w);
    let g = ui.painter().layout_job(job);
    ui.painter().galley(egui::pos2(rect.left() + 38.0, rect.center().y - g.size().y / 2.0), g, ink);
    match (pill, status) {
        (Some((color, g)), _) => {
            let r = egui::Rect::from_min_size(egui::pos2(rect.right() - 10.0 - g.size().x - 12.0, rect.center().y - 10.0), Vec2::new(g.size().x + 12.0, 20.0));
            ui.painter().rect_filled(r, 10.0, color.gamma_multiply(0.16));
            ui.painter().galley(r.center() - g.size() / 2.0, g, color);
        }
        (None, Some((color, _, _))) => {
            ui.painter().circle_filled(egui::pos2(rect.right() - 16.0, rect.center().y), 3.5, color);
        }
        (None, None) => {}
    }
    widgets::focus_ring(ui, &resp, rect);
    resp.widget_info(|| egui::WidgetInfo::selected(egui::WidgetType::Button, true, on, &name));
    resp.on_hover_cursor(egui::CursorIcon::PointingHand)
}
