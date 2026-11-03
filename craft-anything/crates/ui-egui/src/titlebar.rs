//! The custom title bar (the native frame is off): app mark, what's open, Clean room / Deep, AI
//! backend, Simple · Advanced, settings and the window buttons. Empty parts drag the window; the
//! window edges resize it.

use crate::i18n::tr;
use crate::state::Screen;
use crate::theme::{self, Tokens};
use crate::{CraftApp, icons, widgets};
use craft_anything_engine::Mode;
use egui::viewport::ResizeDirection;
use egui::{RichText, Ui, Vec2};

/// Height of the custom title bar.
pub const HEIGHT: f32 = 40.0;
/// How close to the window edge the pointer must be to resize.
const EDGE: f32 = 5.0;

fn maximized(ctx: &egui::Context) -> bool {
    ctx.input(|i| i.viewport().maximized.unwrap_or(false) || i.viewport().fullscreen.unwrap_or(false))
}

/// The window edge (or corner) under the pointer, when the window can be resized from there.
pub fn edge_at(ctx: &egui::Context) -> Option<ResizeDirection> {
    if maximized(ctx) {
        return None;
    }
    let pos = ctx.input(|i| i.pointer.hover_pos())?;
    let r = ctx.content_rect();
    let (w, e, n, s) = (pos.x - r.left() < EDGE, r.right() - pos.x < EDGE, pos.y - r.top() < EDGE, r.bottom() - pos.y < EDGE);
    Some(match (w, e, n, s) {
        (true, _, true, _) => ResizeDirection::NorthWest,
        (_, true, true, _) => ResizeDirection::NorthEast,
        (true, _, _, true) => ResizeDirection::SouthWest,
        (_, true, _, true) => ResizeDirection::SouthEast,
        (true, ..) => ResizeDirection::West,
        (_, true, ..) => ResizeDirection::East,
        (_, _, true, _) => ResizeDirection::North,
        (_, _, _, true) => ResizeDirection::South,
        _ => return None,
    })
}

/// A 1 px edge around the window (the native frame is off), so it doesn't melt into the desktop.
pub fn window_edge(ctx: &egui::Context) {
    if maximized(ctx) {
        return;
    }
    let t = Tokens::get(ctx);
    ctx.layer_painter(egui::LayerId::new(egui::Order::Foreground, egui::Id::new("window-edge"))).rect_stroke(
        ctx.content_rect(),
        0.0,
        egui::Stroke::new(1.0, t.field_border),
        egui::StrokeKind::Inside,
    );
}

/// Resizing from the window edges (the native frame is off, so we provide it).
pub fn resize_edges(ctx: &egui::Context) {
    let Some(dir) = edge_at(ctx) else { return };
    ctx.set_cursor_icon(match dir {
        ResizeDirection::North => egui::CursorIcon::ResizeNorth,
        ResizeDirection::South => egui::CursorIcon::ResizeSouth,
        ResizeDirection::East => egui::CursorIcon::ResizeEast,
        ResizeDirection::West => egui::CursorIcon::ResizeWest,
        ResizeDirection::NorthEast => egui::CursorIcon::ResizeNorthEast,
        ResizeDirection::NorthWest => egui::CursorIcon::ResizeNorthWest,
        ResizeDirection::SouthEast => egui::CursorIcon::ResizeSouthEast,
        ResizeDirection::SouthWest => egui::CursorIcon::ResizeSouthWest,
    });
    if ctx.input(|i| i.pointer.primary_pressed()) {
        ctx.send_viewport_cmd(egui::ViewportCommand::BeginResize(dir));
    }
}

/// A thin vertical rule between title bar cells.
fn rule(ui: &mut Ui) {
    let t = Tokens::get(ui.ctx());
    let (r, _) = ui.allocate_exact_size(Vec2::new(1.0, HEIGHT), egui::Sense::hover());
    ui.painter().vline(r.center().x, r.y_range(), egui::Stroke::new(1.0, t.separator));
}

/// One of the window buttons (minimise, maximise, close): a full-height cell.
fn window_button(ui: &mut Ui, icon: &str, tip: &str, close: bool) -> egui::Response {
    let t = Tokens::get(ui.ctx());
    let (rect, resp) = ui.allocate_exact_size(Vec2::new(46.0, HEIGHT), egui::Sense::click());
    let hot = resp.hovered();
    if hot {
        ui.painter().rect_filled(rect, 0.0, if close { t.danger } else { t.hover });
    }
    let col = if hot && close { egui::Color32::WHITE } else { t.icon };
    icons::paint(ui, egui::Rect::from_center_size(rect.center(), Vec2::splat(14.0)), icon, 14.0, col);
    widgets::focus_ring(ui, &resp, rect.shrink(3.0));
    resp.widget_info(|| egui::WidgetInfo::labeled(egui::WidgetType::Button, true, tr(tip)));
    resp.on_hover_text(tr(tip))
}

pub fn show(app: &mut CraftApp, ui: &mut Ui) {
    let t = Tokens::get(ui.ctx());
    let ctx = ui.ctx().clone();
    let bar = ui.max_rect();
    // Empty parts of the bar move the window and double-click maximises. This is registered
    // before the controls, so they get their own clicks.
    let drag = ui.interact(bar, ui.id().with("titlebar-drag"), egui::Sense::click_and_drag());
    if edge_at(&ctx).is_none() && drag.drag_started_by(egui::PointerButton::Primary) {
        ctx.send_viewport_cmd(egui::ViewportCommand::StartDrag);
    }
    if drag.double_clicked() {
        ctx.send_viewport_cmd(egui::ViewportCommand::Maximized(!maximized(&ctx)));
    }
    ui.painter().hline(bar.x_range(), bar.bottom() - 0.5, egui::Stroke::new(1.0, t.separator));
    // A download anywhere in the app fills the bottom edge of the bar, on every screen.
    let download = crate::engine_ui::global_download(app);
    if let Some((_, Some(f), _)) = &download {
        let x = bar.left() + bar.width() * f.clamp(0.0, 1.0);
        ui.painter().line_segment([egui::pos2(bar.left(), bar.bottom() - 1.0), egui::pos2(x, bar.bottom() - 1.0)], egui::Stroke::new(2.0, t.accent));
    }
    ui.horizontal_centered(|ui| {
        ui.spacing_mut().item_spacing.x = 10.0;
        ui.add_space(12.0);
        if ui.add(crate::app_icon(22.0).sense(egui::Sense::click())).on_hover_text(tr("Home")).clicked() {
            app.state.screen = Screen::Home;
        }
        ui.label(theme::label_text("Craft Anything", 12.0).color(t.text).strong());
        let in_project = app.state.screen == Screen::Project;
        let project = if in_project { app.workspace.as_ref().map(|w| w.manifest.name.clone()) } else { app.view.project.clone() };
        let target = if in_project { None } else { app.view.active_target().map(|t| (t.name.clone(), t.kind)) };
        if project.is_some() || target.is_some() {
            rule(ui);
        }
        if let Some(p) = project {
            ui.label(theme::label_text(&p, 12.0).color(t.text_dim));
            if target.is_some() {
                ui.label(RichText::new("/").color(t.text_faint));
            }
        }
        if let Some((name, kind)) = target {
            icons::show(ui, crate::kind_icon(kind), 14.0, t.icon);
            ui.add(egui::Label::new(RichText::new(name).font(theme::mono(theme::CAPTION)).color(t.text)).truncate()).on_hover_text(tr(kind.plain()));
        }
        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
            ui.spacing_mut().item_spacing.x = 0.0;
            if window_button(ui, "x", "Close", true).clicked() {
                ctx.send_viewport_cmd(egui::ViewportCommand::Close);
            }
            let max = maximized(&ctx);
            if window_button(ui, if max { "layers" } else { "square" }, if max { "Restore" } else { "Maximise" }, false).clicked() {
                ctx.send_viewport_cmd(egui::ViewportCommand::Maximized(!max));
            }
            if window_button(ui, "minus", "Minimise", false).clicked() {
                ctx.send_viewport_cmd(egui::ViewportCommand::Minimized(true));
            }
            rule(ui);
            ui.spacing_mut().item_spacing.x = 10.0;
            ui.add_space(4.0);
            if let Some((title, fraction, message)) = download {
                if download_pill(ui, &title, fraction).on_hover_text(message).clicked() {
                    app.state.modal = Some(match app.engine_flow.job {
                        Some((b, _)) => crate::state::Modal::Engine(b),
                        None => crate::state::Modal::Ghidra,
                    });
                }
                rule(ui);
            }
            // During first run there is nothing to switch or set yet.
            if !app.settings.first_run_done {
                return;
            }
            // Simple mode keeps the bar to the essentials: Settings is in the sidebar, the mode
            // switch and AI picker are in Settings, and the Clean room switch stays in view.
            if app.beginner() {
                deep_toggle(app, ui);
                usage_pill(app, ui);
                return;
            }
            if icons::button(ui, "settings", 30.0, app.state.settings_open, "Settings").clicked() {
                app.state.settings_open = !app.state.settings_open;
            }
            rule(ui);
            let sel = usize::from(app.mode() == Mode::Experienced);
            if let Some(i) = widgets::segmented(ui, &["Simple", "Advanced"], sel, 28.0) {
                app.set_mode(if i == 0 { Mode::Beginner } else { Mode::Experienced });
            }
            rule(ui);
            backend_picker(app, ui);
            deep_toggle(app, ui);
            usage_pill(app, ui);
            if app.jobs.busy() {
                let n = app.jobs.running().filter(|j| j.visible).count();
                ui.add(egui::Spinner::new().size(14.0).color(t.accent)).on_hover_text(crate::i18n::trf("{n} job(s) running", &[("n", &n.to_string())]));
            }
        });
    });
}

/// What the AI has used since the app opened ("about $3.20", or tokens without a price), once
/// it has used anything; the details are in its tooltip.
fn usage_pill(app: &CraftApp, ui: &mut Ui) {
    let u = &app.session_usage;
    if !u.used_anything() {
        return;
    }
    let t = Tokens::get(ui.ctx());
    let text = if u.priced { crate::usage::cost_short(u) } else { crate::usage::tokens_words(u.tokens()) };
    let r = widgets::pill(ui, &text, t.text_dim, t.raised);
    r.widget_info(|| egui::WidgetInfo::labeled(egui::WidgetType::Label, true, &text));
    r.on_hover_ui(|ui| {
        ui.label(RichText::new(tr("AI use this session")).font(theme::semibold(theme::SMALL)));
        ui.label(crate::usage::explain(u, "Since Craft Anything opened."));
    });
}

/// "Getting Godot · 42%" with a small bar; opens the engine's steps when clicked.
fn download_pill(ui: &mut Ui, title: &str, fraction: Option<f32>) -> egui::Response {
    let t = Tokens::get(ui.ctx());
    let text = match fraction {
        Some(f) => format!("{title} · {:.0}%", f * 100.0),
        None => title.to_string(),
    };
    let g = widgets::label_galley(ui, &text, 12.0, t.text);
    let size = Vec2::new(g.size().x + 26.0 + 52.0, 26.0);
    let (rect, resp) = ui.allocate_exact_size(size, egui::Sense::click());
    let h = widgets::hover_t(ui, &resp);
    ui.painter().rect(rect, t.radius, crate::theme::mix(t.raised, t.hover, h), egui::Stroke::new(1.0, t.card_border), egui::StrokeKind::Inside);
    icons::paint(ui, egui::Rect::from_center_size(egui::pos2(rect.left() + 14.0, rect.center().y), Vec2::splat(14.0)), "download", 14.0, t.accent);
    ui.painter().galley_with_override_text_color(egui::pos2(rect.left() + 26.0, rect.center().y - g.size().y / 2.0), g, t.text);
    let track = egui::Rect::from_min_size(egui::pos2(rect.right() - 48.0, rect.center().y - 1.5), Vec2::new(38.0, 3.0));
    ui.painter().rect_filled(track, 1.5, t.separator);
    let f = fraction.unwrap_or_else(|| (ui.input(|i| i.time) * 0.6).fract() as f32).clamp(0.0, 1.0);
    ui.painter().rect_filled(egui::Rect::from_min_size(track.min, Vec2::new(track.width() * f, track.height())), 1.5, t.accent);
    widgets::focus_ring(ui, &resp, rect);
    widgets::animate(ui, std::time::Duration::from_millis(250));
    resp.widget_info(|| egui::WidgetInfo::labeled(egui::WidgetType::Button, true, text.clone()));
    resp.on_hover_cursor(egui::CursorIcon::PointingHand)
}

/// Clean room / Deep switch.
fn deep_toggle(app: &mut CraftApp, ui: &mut Ui) {
    let t = Tokens::get(ui.ctx());
    let deep = app.settings.deep_mode;
    let missing = app.ghidra_missing();
    let label = tr(if deep { "Deep" } else { "Clean room" });
    let g = widgets::label_galley(ui, &label, 12.0, t.text);
    let size = Vec2::new(g.size().x + 64.0, 30.0);
    let (rect, resp) = ui.allocate_exact_size(size, egui::Sense::click());
    let fill = if resp.hovered() { t.hover } else { egui::Color32::TRANSPARENT };
    ui.painter().rect(rect, t.radius, fill, egui::Stroke::new(1.0, t.card_border), egui::StrokeKind::Inside);
    let icon_rect = egui::Rect::from_center_size(egui::pos2(rect.left() + 16.0, rect.center().y), Vec2::splat(16.0));
    let (icon, col) = if deep { ("microscope", t.accent) } else { ("shield-check", t.success) };
    icons::paint(ui, icon_rect, icon, 15.0, col);
    ui.painter().galley_with_override_text_color(egui::pos2(rect.left() + 30.0, rect.center().y - g.size().y / 2.0), g, t.text);
    // The little switch.
    let sw = egui::Rect::from_center_size(egui::pos2(rect.right() - 18.0, rect.center().y), Vec2::new(22.0, 12.0));
    let how = ui.ctx().animate_bool(resp.id, deep);
    ui.painter().rect_filled(sw, 6.0, if deep { t.accent } else { t.pressed });
    let knob_x = egui::lerp(sw.left() + 6.0..=sw.right() - 6.0, how);
    ui.painter().circle_filled(egui::pos2(knob_x, sw.center().y), 4.5, egui::Color32::WHITE);
    widgets::focus_ring(ui, &resp, rect);
    resp.widget_info(|| egui::WidgetInfo::selected(egui::WidgetType::Checkbox, true, !deep, tr("Clean room")));
    let resp = resp.on_hover_ui(|ui| {
        ui.label(RichText::new(tr("Clean room or Deep")).font(theme::semibold(theme::SMALL)));
        ui.label(tr(
            "Clean room: nothing inside the original is read. We work from what you can see: pictures, the page as a visitor sees it, and watching it run.",
        ));
        ui.label(tr("Deep: we read its code, files and page source with every tool we have, and with Ghidra when it's installed. Click to switch."));
        if missing {
            ui.label(RichText::new(tr("Ghidra isn't installed, so the built-in decompiler stands in. Get it in Settings → Engines.")).color(t.warning));
        }
    });
    if resp.clicked() {
        app.set_deep(!deep);
    }
}

/// AI backend picker: configured brains, "No AI", "Set up…".
fn backend_picker(app: &mut CraftApp, ui: &mut Ui) {
    let t = Tokens::get(ui.ctx());
    let current = format!("{} · {}", tr("AI"), app.state.backend.clone().unwrap_or_else(|| tr("None")));
    let mut choice: Option<Option<String>> = None;
    let mut setup = false;
    ui.scope(|ui| {
        ui.spacing_mut().interact_size.y = 30.0;
        egui::ComboBox::from_id_salt("backend-picker")
            .selected_text(theme::label_text(&current, 12.0).color(if app.state.backend.is_some() { t.text } else { t.text_dim }))
            .icon(widgets::combo_icon)
            .width(190.0)
            .show_ui(ui, |ui| {
                for b in &app.backends {
                    let on = app.state.backend.as_ref() == Some(&b.name);
                    if ui.selectable_label(on, &b.name).on_hover_text(format!("{:?} · {}", b.kind, b.model)).clicked() {
                        choice = Some(Some(b.name.clone()));
                    }
                }
                if ui.selectable_label(app.state.backend.is_none(), tr("No AI (built-in engines only)")).clicked() {
                    choice = Some(None);
                }
                ui.separator();
                if ui.selectable_label(false, tr("Set up a brain…")).clicked() {
                    setup = true;
                }
            })
            .response
            .on_hover_text(tr("Which AI answers your questions"));
    });
    if let Some(c) = choice {
        app.choose_backend(c);
    }
    if setup {
        app.state.settings_open = true;
        app.state.settings_tab = crate::state::SettingsTab::Ai;
        app.detect_backends();
    }
}
