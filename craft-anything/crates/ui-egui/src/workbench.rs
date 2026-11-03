//! Experienced mode: a dense workbench. Left rail lists, centre tabbed views, right inspector /
//! evidence / unknowns, bottom agent console / jobs / log.

use crate::evidence_ui::{self, json_tree, truncate};
use crate::i18n::tr;
use crate::state::{BottomTab, CenterTab, Fill, RailKind, RightTab};
use crate::theme::{self, Tokens};
use crate::{CraftApp, Pick, Route, chat, icons, widgets};
use craft_anything_engine::Consent;
use egui::{Margin, RichText, Ui, Vec2};
use serde_json::{Value, json};

/// Keys that usually hold a row's address.
const ADDRESS_KEYS: &[&str] = &["address", "addr", "start", "entry", "va", "rva", "offset"];
/// Keys that usually hold a row's display name.
const NAME_KEYS: &[&str] = &["name", "symbol", "label", "value", "text", "string", "module", "path", "class", "id"];
/// Keys that usually hold the list in a result object, best first.
const LIST_KEYS: &[&str] = &[
    "items",
    "functions",
    "functions",
    "strings",
    "imports",
    "exports",
    "segments",
    "sections",
    "classes",
    "modules",
    "resources",
    "entries",
    "results",
    "instructions",
    "lines",
    "requests",
    "targets",
];
const MAX_ROWS: usize = 50_000;

/// The rows of a list result.
pub fn rows(v: &Value) -> &[Value] {
    match v {
        Value::Array(a) => a.as_slice(),
        Value::Object(m) => {
            for k in LIST_KEYS {
                if let Some(Value::Array(a)) = m.get(*k) {
                    return a.as_slice();
                }
            }
            m.values().find_map(|v| v.as_array().filter(|a| !a.is_empty())).map(Vec::as_slice).unwrap_or(&[])
        }
        _ => &[],
    }
}

fn scalar(v: &Value) -> Option<String> {
    match v {
        Value::String(s) => Some(s.clone()),
        Value::Number(n) => Some(n.to_string()),
        Value::Bool(b) => Some(b.to_string()),
        _ => None,
    }
}

/// A row's address as `0x…` text.
pub fn row_address(v: &Value) -> Option<String> {
    let m = v.as_object()?;
    ADDRESS_KEYS.iter().find_map(|k| match m.get(*k)? {
        Value::Number(n) => n.as_u64().map(|a| format!("0x{a:x}")),
        Value::String(s) => Some(s.clone()),
        _ => None,
    })
}

pub fn row_name(v: &Value) -> Option<String> {
    match v {
        Value::Object(m) => NAME_KEYS.iter().find_map(|k| m.get(*k).and_then(scalar)),
        other => scalar(other),
    }
}

/// A short secondary text for a row (kind, size, library…).
fn row_detail(v: &Value) -> Option<String> {
    let m = v.as_object()?;
    ["kind", "type", "library", "dll", "section", "size", "permissions", "flags"].iter().find_map(|k| m.get(*k).and_then(scalar).map(|s| format!("{k}: {s}")))
}

fn row_text(v: &Value) -> String {
    let mut s = row_name(v).unwrap_or_default();
    if let Some(a) = row_address(v) {
        s.push(' ');
        s.push_str(&a);
    }
    s.to_lowercase()
}

pub fn show(app: &mut CraftApp, ui: &mut Ui) {
    let t = Tokens::get(ui.ctx());
    egui::Panel::left("wb-rail-icons")
        .exact_size(48.0)
        .resizable(false)
        .frame(egui::Frame::new().fill(t.chrome).inner_margin(Margin::symmetric(6, 10)))
        .show(ui, |ui| rail_icons(app, ui));
    egui::Panel::left("wb-rail")
        .default_size(290.0)
        .size_range(200.0..=520.0)
        .frame(egui::Frame::new().fill(t.chrome).inner_margin(Margin { left: 4, right: 8, top: 10, bottom: 8 }))
        .show(ui, |ui| crate::guard_ui(ui, "rail", |ui| rail(app, ui)));
    egui::Panel::right("wb-right")
        .default_size(330.0)
        .size_range(240.0..=560.0)
        .frame(egui::Frame::new().fill(t.chrome).inner_margin(Margin { left: 8, right: 10, top: 10, bottom: 8 }))
        .show(ui, |ui| crate::guard_ui(ui, "inspector", |ui| right(app, ui)));
    let mut open = app.state.bottom_open;
    egui::Panel::bottom("wb-bottom")
        .default_size(240.0)
        .size_range(120.0..=600.0)
        .frame(egui::Frame::new().fill(t.chrome).inner_margin(Margin { left: 8, right: 10, top: 4, bottom: 8 }))
        .show_collapsible(ui, &mut open, |ui| crate::guard_ui(ui, "bottom", |ui| bottom(app, ui)));
    app.state.bottom_open = open;
    if !app.state.bottom_open {
        egui::Panel::bottom("wb-bottom-closed").exact_size(30.0).frame(egui::Frame::new().fill(t.chrome).inner_margin(Margin::symmetric(10, 4))).show(
            ui,
            |ui| {
                ui.horizontal(|ui| {
                    if icons::button(ui, "chevron-up", 22.0, false, "Show the console").clicked() {
                        app.state.bottom_open = true;
                    }
                    status_line(app, ui);
                });
            },
        );
    }
    egui::CentralPanel::default()
        .frame(egui::Frame::new().fill(t.canvas).inner_margin(Margin::same(0)))
        .show(ui, |ui| crate::guard_ui(ui, "centre", |ui| center(app, ui)));
}

fn rail_icons(app: &mut CraftApp, ui: &mut Ui) {
    ui.vertical_centered(|ui| {
        for k in RailKind::ALL {
            let on = app.state.rail == k;
            if icons::button(ui, k.icon(), 34.0, on, k.title()).clicked() && !on {
                app.state.rail = k;
                app.state.rail_filter.clear();
                app.ensure_rail_loaded();
            }
            ui.add_space(2.0);
        }
        ui.with_layout(egui::Layout::bottom_up(egui::Align::Center), |ui| {
            if icons::button(ui, "search", 34.0, app.state.palette.open, "Command palette (Ctrl/⌘ K)").clicked() {
                app.state.palette.open = true;
            }
            // Projects and their builds; a dot when one needs an answer.
            let r = icons::button(ui, "hammer", 34.0, false, "Projects and builds");
            if !app.asking.is_empty() {
                let t = Tokens::get(ui.ctx());
                ui.painter().circle_filled(r.rect.right_top() + egui::vec2(-7.0, 7.0), 4.5, t.warning);
            }
            if r.clicked() {
                app.state.screen = if app.workspace.is_some() { crate::state::Screen::Project } else { crate::state::Screen::Home };
            }
        });
    });
}

fn panel_title(ui: &mut Ui, title: &str, count: Option<usize>) {
    let t = Tokens::get(ui.ctx());
    ui.horizontal(|ui| {
        ui.label(theme::label_text(&tr(title), 11.5).color(t.text));
        if let Some(n) = count {
            widgets::pill(ui, &n.to_string(), t.text_dim, t.raised);
        }
    });
}

fn rail(app: &mut CraftApp, ui: &mut Ui) {
    let kind = app.state.rail;
    if kind == RailKind::Targets {
        targets_list(app, ui);
        return;
    }
    // Lent out while it's drawn, not copied every frame (a list can hold thousands of rows); a
    // reload started meanwhile (it puts Loading in its place) wins.
    let fill = app.state.lists.remove(&kind).unwrap_or_default();
    rail_list(app, ui, kind, &fill);
    app.state.lists.entry(kind).or_insert(fill);
}

fn rail_list(app: &mut CraftApp, ui: &mut Ui, kind: RailKind, fill: &Fill) {
    let t = Tokens::get(ui.ctx());
    let all: Vec<&Value> = match fill {
        Fill::Ready(e) => rows(&e.result).iter().take(MAX_ROWS).collect(),
        Fill::Value(v) => rows(v).iter().take(MAX_ROWS).collect(),
        _ => Vec::new(),
    };
    ui.horizontal(|ui| {
        panel_title(ui, kind.title(), matches!(fill, Fill::Ready(_) | Fill::Value(_)).then_some(all.len()));
        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
            if icons::button(ui, "refresh-cw", 24.0, false, "Reload").clicked() {
                app.load_rail(kind);
            }
        });
    });
    ui.add_space(4.0);
    widgets::named(
        ui.add(
            egui::TextEdit::singleline(&mut app.state.rail_filter)
                .hint_text(tr("Filter…"))
                .desired_width(f32::INFINITY)
                .frame(widgets::text_field_frame_compact(&t)),
        ),
        "Filter",
    );
    ui.add_space(6.0);
    if app.view.active.is_none() {
        widgets::empty_state(ui, "folder-open", "Nothing open", "Open a file or drop one here.");
        ui.vertical_centered(|ui| {
            if widgets::primary_icon(ui, Some("folder-open"), "Open…", true).clicked() {
                app.pick(Pick::OpenFile);
            }
        });
        return;
    }
    match fill {
        Fill::Idle => {
            app.ensure_rail_loaded();
            ui.add(egui::Spinner::new().color(t.accent));
        }
        Fill::Loading => {
            ui.horizontal(|ui| {
                ui.add(egui::Spinner::new().color(t.accent));
                ui.label(RichText::new(tr("Loading…")).color(t.text_dim));
            });
        }
        Fill::Unavailable(reason) => {
            widgets::empty_state(ui, "hammer", "Not available yet", reason);
        }
        Fill::Blocked(reason, rem) => {
            widgets::empty_state(ui, "lock", reason, rem.as_deref().unwrap_or(""));
        }
        Fill::DeepNeeded => crate::engine_ui::deep_needed(app, ui),
        Fill::Error(msg, rem) => {
            widgets::empty_state(ui, "triangle-alert", msg, rem.as_deref().unwrap_or(""));
        }
        Fill::Ready(_) | Fill::Value(_) => {
            let filter = app.state.rail_filter.trim().to_lowercase();
            let idx: Vec<usize> = all.iter().enumerate().filter(|(_, r)| filter.is_empty() || row_text(r).contains(&filter)).map(|(i, _)| i).collect();
            if idx.is_empty() {
                widgets::empty_state(ui, "search", if all.is_empty() { "Nothing found" } else { "No matches" }, "");
                return;
            }
            let row_h = 34.0;
            let mut clicked = None;
            egui::ScrollArea::vertical().auto_shrink([false, false]).show_rows(ui, row_h, idx.len(), |ui, range| {
                for i in range {
                    let Some(r) = idx.get(i).and_then(|i| all.get(*i)).copied() else { continue };
                    let selected = app.state.selection.as_ref() == Some(r);
                    if list_row(ui, r, selected, row_h) {
                        clicked = Some(r.clone());
                    }
                }
            });
            if let Some(r) = clicked {
                select_row(app, r);
            }
        }
    }
}

fn list_row(ui: &mut Ui, r: &Value, selected: bool, h: f32) -> bool {
    let t = Tokens::get(ui.ctx());
    let (rect, resp) = ui.allocate_exact_size(Vec2::new(ui.available_width(), h), egui::Sense::click());
    if selected {
        ui.painter().rect_filled(rect, t.radius_sm, t.accent_soft);
    } else if resp.hovered() {
        ui.painter().rect_filled(rect, t.radius_sm, t.hover);
    }
    let name = row_name(r).unwrap_or_else(|| truncate(&r.to_string(), 80));
    let addr = row_address(r);
    resp.widget_info(|| egui::WidgetInfo::selected(egui::WidgetType::SelectableLabel, true, selected, &name));
    let x = rect.left() + 8.0;
    if let Some(a) = &addr {
        let g = ui.painter().layout_no_wrap(a.clone(), theme::mono(11.0), if selected { t.accent_ink } else { t.text_faint });
        ui.painter().galley(egui::pos2(x, rect.top() + 3.0), g, t.text_faint);
    }
    let name_y = if addr.is_some() { rect.top() + 17.0 } else { rect.center().y - 8.0 };
    let name_g = ui.painter().layout_no_wrap(truncate(&name, 120), theme::mono(12.5), t.text);
    let clip = rect.shrink2(Vec2::new(6.0, 0.0));
    ui.painter().with_clip_rect(clip).galley(egui::pos2(x, name_y), name_g, t.text);
    if let Some(d) = row_detail(r) {
        let g = ui.painter().layout_no_wrap(d, egui::FontId::proportional(theme::TINY), t.text_faint);
        let pos = egui::pos2(rect.right() - g.size().x - 8.0, rect.top() + 4.0);
        ui.painter().with_clip_rect(clip).galley(pos, g, t.text_faint);
    }
    resp.clicked()
}

fn select_row(app: &mut CraftApp, r: Value) {
    app.state.selection = Some(r);
    app.state.right = RightTab::Inspector;
    app.state.views.retain(|k, _| *k == CenterTab::Result);
    let tab = app.state.center;
    if !tab.tools().is_empty() && app.first_tool(tab.tools()).is_some() {
        app.load_view(tab);
    }
}

fn targets_list(app: &mut CraftApp, ui: &mut Ui) {
    let t = Tokens::get(ui.ctx());
    ui.horizontal(|ui| {
        panel_title(ui, "Targets", Some(app.view.targets.len()));
        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
            if icons::button(ui, "plus", 24.0, false, "Open another target").clicked() {
                app.pick(Pick::OpenFile);
            }
        });
    });
    ui.add_space(6.0);
    if app.view.targets.is_empty() {
        widgets::empty_state(ui, "layers", "No targets", "Open files, folders or apps; you can have several open at once.");
        return;
    }
    let mut pick = None;
    for tgt in &app.view.targets {
        let active = app.view.active.as_ref() == Some(&tgt.id);
        let (rect, resp) = ui.allocate_exact_size(Vec2::new(ui.available_width(), 50.0), egui::Sense::click());
        if active {
            ui.painter().rect_filled(rect, t.radius, t.accent_soft);
        } else if resp.hovered() {
            ui.painter().rect_filled(rect, t.radius, t.hover);
        }
        let ir = egui::Rect::from_min_size(rect.min + Vec2::new(8.0, 10.0), Vec2::splat(30.0));
        ui.painter().rect_filled(ir, t.radius_sm, t.raised);
        icons::paint(ui, ir, crate::kind_icon(tgt.kind), 16.0, if active { t.accent_ink } else { t.icon });
        ui.painter().text(egui::pos2(ir.right() + 10.0, rect.top() + 8.0), egui::Align2::LEFT_TOP, &tgt.name, theme::medium(theme::SMALL), t.text);
        ui.painter().text(
            egui::pos2(ir.right() + 10.0, rect.top() + 27.0),
            egui::Align2::LEFT_TOP,
            format!("{} · {}", tgt.kind.id(), crate::human_bytes(tgt.bytes.len())),
            egui::FontId::proportional(theme::TINY),
            t.text_faint,
        );
        if resp.on_hover_text(tgt.path.display().to_string()).clicked() && !active {
            pick = Some(tgt.id.clone());
        }
    }
    if let Some(id) = pick {
        app.run_tool("core_target_select", json!({"target_id": id}), Route::Silent, Consent::NotAsked);
        app.state.lists.clear();
        app.state.views.clear();
        app.state.selection = None;
    }
}

/// A tab strip; returns the clicked tab index.
fn tab_strip(ui: &mut Ui, tabs: &[(&str, &str)], selected: usize) -> Option<usize> {
    let t = Tokens::get(ui.ctx());
    let mut picked = None;
    ui.horizontal(|ui| {
        ui.spacing_mut().item_spacing.x = 2.0;
        for (i, (icon, title)) in tabs.iter().enumerate() {
            let on = i == selected;
            let g = widgets::label_galley(ui, &tr(title), 11.0, t.text);
            let w = g.size().x + if icon.is_empty() { 22.0 } else { 42.0 };
            let (rect, resp) = ui.allocate_exact_size(Vec2::new(w, 32.0), egui::Sense::click());
            resp.widget_info(|| egui::WidgetInfo::selected(egui::WidgetType::SelectableLabel, true, on, tr(title)));
            if !on {
                let h = widgets::hover_t(ui, &resp);
                ui.painter().rect_filled(rect.shrink2(Vec2::new(0.0, 3.0)), t.radius_sm, theme::mix(egui::Color32::TRANSPARENT, t.hover, h));
            }
            widgets::focus_ring(ui, &resp, rect.shrink2(Vec2::new(0.0, 3.0)));
            let col = if on { t.text } else { t.text_dim };
            let mut x = rect.left() + 10.0;
            if !icon.is_empty() {
                icons::paint(
                    ui,
                    egui::Rect::from_min_size(egui::pos2(x, rect.center().y - 7.0), Vec2::splat(14.0)),
                    icon,
                    14.0,
                    if on { t.accent } else { t.text_faint },
                );
                x += 20.0;
            }
            ui.painter().galley_with_override_text_color(egui::pos2(x, rect.center().y - g.size().y / 2.0), g, col);
            if on {
                ui.painter().hline(rect.x_range().shrink(6.0), rect.bottom() - 1.0, egui::Stroke::new(2.0, t.accent));
            }
            if resp.clicked() && !on {
                picked = Some(i);
            }
        }
    });
    picked
}

fn center(app: &mut CraftApp, ui: &mut Ui) {
    let t = Tokens::get(ui.ctx());
    egui::Frame::new().fill(t.chrome).inner_margin(Margin::symmetric(8, 0)).show(ui, |ui| {
        ui.set_width(ui.available_width());
        let tabs: Vec<(&str, &str)> = CenterTab::ALL.iter().map(|c| (c.icon(), c.title())).collect();
        let sel = CenterTab::ALL.iter().position(|c| *c == app.state.center).unwrap_or(0);
        if let Some(i) = tab_strip(ui, &tabs, sel)
            && let Some(tab) = CenterTab::ALL.get(i).copied()
        {
            app.state.center = tab;
            if app.state.selection.is_some() && matches!(app.state.views.get(&tab), None | Some(Fill::Idle)) && app.first_tool(tab.tools()).is_some() {
                app.load_view(tab);
            }
        }
    });
    ui.painter().hline(ui.max_rect().x_range(), ui.cursor().top(), egui::Stroke::new(1.0, t.separator));
    egui::Frame::new().inner_margin(Margin::same(14)).show(ui, |ui| {
        ui.set_width(ui.available_width());
        if app.view.active.is_none() && app.state.center != CenterTab::Result {
            no_target(app, ui);
            return;
        }
        let tab = app.state.center;
        match tab {
            CenterTab::Result => result_view(app, ui),
            CenterTab::Hex if !matches!(app.state.views.get(&tab), Some(Fill::Ready(_) | Fill::Value(_) | Fill::Loading)) => hex_view(app, ui),
            _ => tool_view(app, ui, tab),
        }
    });
}

fn no_target(app: &mut CraftApp, ui: &mut Ui) {
    ui.add_space(ui.available_height() * 0.2);
    widgets::empty_state(
        ui,
        "scan-search",
        "Open something to start",
        "A program, an app bundle, an APK, a JavaScript bundle, a folder… or drop it on the window.",
    );
    ui.vertical_centered(|ui| {
        ui.horizontal(|ui| {
            ui.add_space((ui.available_width() - 300.0).max(0.0) / 2.0);
            if widgets::primary_icon(ui, Some("folder-open"), "Open a file…", true).clicked() {
                app.pick(Pick::OpenFile);
            }
            if widgets::secondary(ui, Some("folder"), "Open a folder…").clicked() {
                app.pick(Pick::OpenFolder);
            }
        });
        ui.add_space(10.0);
        let t = Tokens::get(ui.ctx());
        ui.label(RichText::new(tr("Tip: press Ctrl/⌘ K to run any tool.")).color(t.text_faint));
    });
}

fn tool_view(app: &mut CraftApp, ui: &mut Ui, tab: CenterTab) {
    let fill = app.state.views.get(&tab).cloned().unwrap_or_default();
    match fill {
        Fill::Idle => {
            if app.first_tool(tab.tools()).is_none() {
                widgets::empty_state(
                    ui,
                    tab.icon(),
                    &format!("{} {}", tr(tab.title()), tr("isn't available yet")),
                    "This view arrives with the next engines. The Hex and Result views work today.",
                );
            } else if app.state.selection.is_none() {
                widgets::empty_state(ui, tab.icon(), "Pick something on the left", "Choose a function, string or section to see it here.");
            } else {
                app.load_view(tab);
            }
        }
        Fill::Loading => {
            ui.horizontal(|ui| {
                ui.add(egui::Spinner::new().color(Tokens::get(ui.ctx()).accent));
                ui.label(tr("Working…"));
            });
        }
        Fill::Unavailable(reason) => widgets::empty_state(ui, tab.icon(), "Not available yet", &reason),
        Fill::Blocked(reason, rem) => widgets::empty_state(ui, "lock", &reason, rem.as_deref().unwrap_or("")),
        Fill::DeepNeeded => crate::engine_ui::deep_needed(app, ui),
        Fill::Error(msg, rem) => widgets::empty_state(ui, "triangle-alert", &msg, rem.as_deref().unwrap_or("")),
        Fill::Ready(e) => {
            ui.horizontal(|ui| {
                widgets::confidence_badge(ui, Some(e.confidence));
                ui.label(RichText::new(&e.summary).color(Tokens::get(ui.ctx()).text_dim));
            });
            ui.add_space(6.0);
            render_result(ui, &e.result, tab);
        }
        Fill::Value(v) => render_result(ui, &v, tab),
    }
}

/// Code-like text in a result, if any.
pub fn code_text(v: &Value) -> Option<&str> {
    match v {
        Value::String(s) => Some(s),
        Value::Object(m) => ["pseudo_c", "pseudocode", "code", "source", "text", "listing", "disassembly", "dot", "mermaid"]
            .iter()
            .find_map(|k| m.get(*k).and_then(Value::as_str)),
        _ => None,
    }
}

fn render_result(ui: &mut Ui, v: &Value, tab: CenterTab) {
    let t = Tokens::get(ui.ctx());
    if let Some(code) = code_text(v) {
        code_view(ui, code, &t);
        return;
    }
    let r = rows(v);
    if !r.is_empty() && matches!(tab, CenterTab::Disassembly | CenterTab::Network | CenterTab::Hex) {
        table(ui, r, &t);
        return;
    }
    egui::ScrollArea::both().auto_shrink([false, false]).show(ui, |ui| json_tree(ui, "result", v, 0));
}

/// Monospace code with line numbers and light keyword colouring.
fn code_view(ui: &mut Ui, code: &str, t: &Tokens) {
    let lines: Vec<&str> = code.lines().collect();
    let row_h = 18.0;
    egui::Frame::new().fill(t.code_bg).corner_radius(t.r()).inner_margin(Margin::same(8)).show(ui, |ui| {
        egui::ScrollArea::both().auto_shrink([false, false]).show_rows(ui, row_h, lines.len(), |ui, range| {
            for i in range {
                let Some(line) = lines.get(i) else { continue };
                ui.horizontal(|ui| {
                    ui.spacing_mut().item_spacing.x = 12.0;
                    ui.add_sized(Vec2::new(38.0, row_h), egui::Label::new(RichText::new(format!("{:>4}", i + 1)).font(theme::mono(12.0)).color(t.text_faint)));
                    ui.label(highlight(line, t));
                });
            }
        });
    });
}

const KEYWORDS: &[&str] = &[
    "if", "else", "while", "for", "return", "do", "switch", "case", "break", "goto", "int", "void", "char", "long", "unsigned", "struct", "const", "function",
    "var", "let", "call", "jmp", "ret", "push", "pop", "mov",
];

fn highlight(line: &str, t: &Tokens) -> egui::text::LayoutJob {
    let mut job = egui::text::LayoutJob::default();
    let font = theme::mono(12.5);
    let comment = line.find("//").or_else(|| line.find(';').filter(|_| !line.trim_end().ends_with(';')));
    let (code, rest) = match comment {
        Some(i) => (line.get(..i).unwrap_or(line), line.get(i..).unwrap_or("")),
        None => (line, ""),
    };
    let mut word = String::new();
    let flush = |job: &mut egui::text::LayoutJob, word: &mut String| {
        if word.is_empty() {
            return;
        }
        let col = if KEYWORDS.contains(&word.as_str()) {
            t.accent_ink
        } else if word.starts_with("0x") || word.chars().all(|c| c.is_ascii_digit()) {
            theme::SEEN_IT
        } else {
            t.text
        };
        job.append(word, 0.0, egui::TextFormat { font_id: font.clone(), color: col, ..Default::default() });
        word.clear();
    };
    let mut in_str = false;
    let mut s = String::new();
    for c in code.chars() {
        if in_str {
            s.push(c);
            if c == '"' {
                job.append(&s, 0.0, egui::TextFormat { font_id: font.clone(), color: theme::BEST_GUESS, ..Default::default() });
                s.clear();
                in_str = false;
            }
            continue;
        }
        if c == '"' {
            flush(&mut job, &mut word);
            in_str = true;
            s.push(c);
        } else if c.is_alphanumeric() || c == '_' {
            word.push(c);
        } else {
            flush(&mut job, &mut word);
            job.append(&c.to_string(), 0.0, egui::TextFormat { font_id: font.clone(), color: t.text_dim, ..Default::default() });
        }
    }
    flush(&mut job, &mut word);
    if !s.is_empty() {
        job.append(&s, 0.0, egui::TextFormat { font_id: font.clone(), color: theme::BEST_GUESS, ..Default::default() });
    }
    if !rest.is_empty() {
        job.append(rest, 0.0, egui::TextFormat { font_id: font.clone(), color: t.text_faint, italics: true, ..Default::default() });
    }
    job
}

/// A generic table: columns from the first row's keys (up to 6).
fn table(ui: &mut Ui, rows: &[Value], t: &Tokens) {
    let cols: Vec<String> = rows.first().and_then(Value::as_object).map(|m| m.keys().take(6).cloned().collect()).unwrap_or_else(|| vec!["value".into()]);
    let row_h = 20.0;
    ui.horizontal(|ui| {
        for c in &cols {
            ui.add_sized(Vec2::new(150.0, 18.0), egui::Label::new(theme::label_text(c, 11.0).color(t.text_faint)));
        }
    });
    egui::ScrollArea::both().auto_shrink([false, false]).show_rows(ui, row_h, rows.len().min(MAX_ROWS), |ui, range| {
        for i in range {
            let Some(r) = rows.get(i) else { continue };
            ui.horizontal(|ui| {
                for c in &cols {
                    let v = match r {
                        Value::Object(m) => m.get(c).map(|v| scalar(v).unwrap_or_else(|| v.to_string())).unwrap_or_default(),
                        other => scalar(other).unwrap_or_default(),
                    };
                    ui.add_sized(Vec2::new(150.0, row_h), egui::Label::new(RichText::new(truncate(&v, 40)).font(theme::mono(12.0))).truncate());
                }
            });
        }
    });
}

/// The built-in hex view of the active target's bytes (works with no tools at all).
fn hex_view(app: &mut CraftApp, ui: &mut Ui) {
    let t = Tokens::get(ui.ctx());
    let Some(target) = app.view.active_target().cloned() else { return };
    let bytes = target.bytes.clone();
    if bytes.is_empty() {
        widgets::empty_state(ui, "folder", "A folder has no bytes of its own", "Open one of the files inside it to see its bytes.");
        return;
    }
    let goto_id = ui.id().with("hex-goto");
    let mut goto: String = ui.data_mut(|d| d.get_temp::<String>(goto_id).unwrap_or_default());
    let mut scroll_to: Option<usize> = None;
    ui.horizontal(|ui| {
        ui.label(RichText::new(format!("{} · {}", target.name, crate::human_bytes(bytes.len()))).font(theme::medium(theme::CAPTION)));
        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
            let r = ui.add(
                egui::TextEdit::singleline(&mut goto)
                    .hint_text(tr("Go to offset (0x…)"))
                    .desired_width(150.0)
                    .font(theme::mono(12.0))
                    .frame(widgets::text_field_frame_compact(&t)),
            );
            if r.lost_focus() && ui.input(|i| i.key_pressed(egui::Key::Enter)) {
                let s = goto.trim().trim_start_matches("0x").trim_start_matches("0X");
                if let Ok(off) = usize::from_str_radix(s, 16) {
                    scroll_to = Some(off / 16);
                }
            }
        });
    });
    ui.data_mut(|d| d.insert_temp(goto_id, goto));
    ui.add_space(6.0);
    let rows = bytes.len().div_ceil(16);
    let row_h = 18.0;
    egui::Frame::new().fill(t.code_bg).corner_radius(t.r()).inner_margin(Margin::same(8)).show(ui, |ui| {
        let mut area = egui::ScrollArea::both().auto_shrink([false, false]);
        if let Some(r) = scroll_to {
            area = area.vertical_scroll_offset(r as f32 * (row_h + ui.spacing().item_spacing.y));
        }
        area.show_rows(ui, row_h, rows, |ui, range| {
            for row in range {
                let start = row * 16;
                let Some(chunk) = bytes.get(start..(start + 16).min(bytes.len())) else { continue };
                let mut job = egui::text::LayoutJob::default();
                let f = theme::mono(12.5);
                job.append(&format!("{start:08x}  "), 0.0, egui::TextFormat { font_id: f.clone(), color: t.text_faint, ..Default::default() });
                for (i, b) in chunk.iter().enumerate() {
                    let col = if *b == 0 {
                        t.text_faint
                    } else if b.is_ascii_graphic() {
                        t.text
                    } else {
                        t.accent_ink
                    };
                    let sep = if i == 7 { "  " } else { " " };
                    job.append(&format!("{b:02x}{sep}"), 0.0, egui::TextFormat { font_id: f.clone(), color: col, ..Default::default() });
                }
                for i in chunk.len()..16 {
                    job.append(if i == 7 { "    " } else { "   " }, 0.0, egui::TextFormat { font_id: f.clone(), color: t.text, ..Default::default() });
                }
                let ascii: String = chunk.iter().map(|b| if b.is_ascii_graphic() || *b == b' ' { *b as char } else { '·' }).collect();
                job.append(&format!(" {ascii}"), 0.0, egui::TextFormat { font_id: f.clone(), color: t.text_dim, ..Default::default() });
                ui.label(job);
            }
        });
    });
}

fn result_view(app: &mut CraftApp, ui: &mut Ui) {
    let t = Tokens::get(ui.ctx());
    let fill = app.state.views.get(&CenterTab::Result).cloned();
    let selected = app.state.selected_evidence.as_ref().and_then(|id| app.view.ledger.iter().find(|e| &e.id == id)).cloned();
    match (fill, selected) {
        (Some(Fill::Loading), _) => {
            ui.horizontal(|ui| {
                ui.add(egui::Spinner::new().color(t.accent));
                ui.label(tr("Working…"));
            });
        }
        (Some(Fill::Error(m, r)), _) => widgets::empty_state(ui, "triangle-alert", &m, r.as_deref().unwrap_or("")),
        (Some(Fill::Blocked(m, r)), _) => widgets::empty_state(ui, "lock", &m, r.as_deref().unwrap_or("")),
        (Some(Fill::DeepNeeded), _) => crate::engine_ui::deep_needed(app, ui),
        (Some(Fill::Value(v)), None) => {
            egui::ScrollArea::both().auto_shrink([false, false]).show(ui, |ui| json_tree(ui, "result", &v, 0));
        }
        (_, Some(e)) => evidence_view(ui, &e, &t),
        (Some(Fill::Ready(e)), None) => evidence_view(ui, &e, &t),
        _ => widgets::empty_state(
            ui,
            "clipboard-list",
            "No result yet",
            "Run a tool from the command palette (Ctrl/⌘ K), or pick a finding in the Evidence panel.",
        ),
    }
}

fn evidence_view(ui: &mut Ui, e: &craft_anything_engine::evidence::Evidence, t: &Tokens) {
    egui::ScrollArea::vertical().auto_shrink([false, false]).show(ui, |ui| {
        evidence_ui::proof_card(ui, e, true, false);
        ui.add_space(10.0);
        if let Some(code) = code_text(&e.result) {
            code_view(ui, code, t);
        } else {
            json_tree(ui, "result", &e.result, 0);
        }
    });
}

fn right(app: &mut CraftApp, ui: &mut Ui) {
    let tabs = [("search", "Inspector"), ("shield-check", "Evidence"), ("circle-help", "Unknowns")];
    let sel = match app.state.right {
        RightTab::Inspector => 0,
        RightTab::Evidence => 1,
        RightTab::Unknowns => 2,
    };
    if let Some(i) = tab_strip(ui, &tabs, sel) {
        app.state.right = [RightTab::Inspector, RightTab::Evidence, RightTab::Unknowns].get(i).copied().unwrap_or_default();
    }
    ui.add_space(6.0);
    match app.state.right {
        RightTab::Inspector => inspector(app, ui),
        RightTab::Evidence => ledger(app, ui),
        RightTab::Unknowns => unknowns(app, ui),
    }
}

fn kv(ui: &mut Ui, k: &str, v: &str, t: &Tokens) {
    ui.label(RichText::new(tr(k)).color(t.text_faint).size(theme::CAPTION));
    ui.add(egui::Label::new(RichText::new(v).font(theme::mono(12.0))).wrap());
    ui.end_row();
}

fn inspector(app: &mut CraftApp, ui: &mut Ui) {
    let t = Tokens::get(ui.ctx());
    egui::ScrollArea::vertical().auto_shrink([false, false]).show(ui, |ui| {
        if let Some(sel) = app.state.selection.clone() {
            widgets::panel(&t).show(ui, |ui| {
                ui.set_width(ui.available_width());
                widgets::caption(ui, "Selection");
                ui.label(RichText::new(row_name(&sel).unwrap_or_else(|| "—".into())).font(theme::semibold(theme::BODY)));
                ui.add_space(4.0);
                egui::Grid::new("sel-grid").num_columns(2).spacing([10.0, 4.0]).show(ui, |ui| {
                    if let Value::Object(m) = &sel {
                        for (k, v) in m.iter().take(30) {
                            kv(ui, k, &scalar(v).unwrap_or_else(|| truncate(&v.to_string(), 200)), &t);
                        }
                    }
                });
                ui.add_space(6.0);
                if widgets::secondary(ui, Some("message-square"), "Ask the agent about this").clicked() {
                    let what = row_name(&sel).or_else(|| row_address(&sel)).unwrap_or_default();
                    app.state.input = crate::i18n::trf("What does {what} do?", &[("what", &what)]);
                    app.state.bottom = BottomTab::Agent;
                    app.state.bottom_open = true;
                }
            });
            ui.add_space(8.0);
        }
        match app.view.active_target().cloned() {
            Some(tgt) => {
                widgets::panel(&t).show(ui, |ui| {
                    ui.set_width(ui.available_width());
                    widgets::caption(ui, "Target");
                    ui.horizontal(|ui| {
                        icons::show(ui, crate::kind_icon(tgt.kind), 16.0, t.accent);
                        ui.label(RichText::new(&tgt.name).font(theme::semibold(theme::SMALL)));
                    });
                    ui.label(RichText::new(tr(tgt.kind.plain())).color(t.text_dim));
                    ui.add_space(4.0);
                    egui::Grid::new("tgt-grid").num_columns(2).spacing([10.0, 4.0]).show(ui, |ui| {
                        kv(ui, "Kind", &tgt.kind.id(), &t);
                        kv(ui, "Size", &crate::human_bytes(tgt.bytes.len()), &t);
                        kv(ui, "SHA-256", tgt.sha256.get(..16).unwrap_or(&tgt.sha256), &t);
                        kv(ui, "Path", &tgt.path.display().to_string(), &t);
                        kv(ui, "Mode", if app.view.clean_room { "Clean room" } else { "Deep" }, &t);
                    });
                });
            }
            None => widgets::empty_state(ui, "search", "Nothing selected", "Details about the selected item appear here."),
        }
    });
}

fn ledger(app: &mut CraftApp, ui: &mut Ui) {
    let t = Tokens::get(ui.ctx());
    ui.horizontal(|ui| {
        panel_title(ui, "Evidence ledger", Some(app.view.ledger_len));
    });
    ui.add_space(4.0);
    if app.view.ledger.is_empty() {
        widgets::empty_state(ui, "shield-check", "No evidence yet", "Every finding is saved here with how sure we are.");
        return;
    }
    let mut pick = None;
    egui::ScrollArea::vertical().auto_shrink([false, false]).show(ui, |ui| {
        for e in &app.view.ledger {
            let selected = app.state.selected_evidence.as_ref() == Some(&e.id);
            if evidence_ui::ledger_row(ui, e, selected) {
                pick = Some(e.id.clone());
            }
            ui.add_space(3.0);
        }
        if app.view.ledger_len > app.view.ledger.len() {
            ui.label(RichText::new(crate::i18n::trf("… {n} older", &[("n", &(app.view.ledger_len - app.view.ledger.len()).to_string())])).color(t.text_faint));
        }
    });
    if let Some(id) = pick {
        app.state.selected_evidence = Some(id);
        app.state.views.remove(&CenterTab::Result);
        app.state.center = CenterTab::Result;
    }
}

fn unknowns(app: &mut CraftApp, ui: &mut Ui) {
    let t = Tokens::get(ui.ctx());
    panel_title(ui, "Open questions", Some(app.view.unknowns.len()));
    ui.add_space(4.0);
    if app.view.unknowns.is_empty() {
        widgets::empty_state(ui, "circle-help", "No open questions", "Things we couldn't establish yet are listed here, with what would settle them.");
        return;
    }
    egui::ScrollArea::vertical().auto_shrink([false, false]).show(ui, |ui| {
        for u in &app.view.unknowns {
            widgets::panel(&t).show(ui, |ui| {
                ui.set_width(ui.available_width());
                ui.horizontal(|ui| {
                    let sev = format!("{:?}", u.severity);
                    let col = match u.severity {
                        craft_anything_engine::evidence::Severity::Critical | craft_anything_engine::evidence::Severity::High => t.danger,
                        craft_anything_engine::evidence::Severity::Medium => t.warning,
                        craft_anything_engine::evidence::Severity::Low => t.text_dim,
                    };
                    widgets::pill(ui, &sev, col, t.raised);
                    widgets::pill(ui, &format!("{:?}", u.status), t.text_dim, t.raised);
                    ui.label(RichText::new(&u.domain).color(t.text_faint).size(theme::TINY));
                });
                ui.add(egui::Label::new(RichText::new(&u.question)).wrap());
                if let Some(r) = &u.resolution {
                    ui.label(RichText::new(r).color(t.success).size(theme::CAPTION));
                }
            });
            ui.add_space(4.0);
        }
    });
}

fn status_line(app: &CraftApp, ui: &mut Ui) {
    let t = Tokens::get(ui.ctx());
    let n = app.jobs.running().filter(|j| j.visible).count();
    let text = if n > 0 { crate::i18n::trf("{n} job(s) running", &[("n", &n.to_string())]) } else { tr("Ready") };
    ui.label(RichText::new(text).color(t.text_faint).size(theme::CAPTION));
    ui.label(RichText::new(format!("· {} {}", app.view.ledger_len, tr("findings"))).color(t.text_faint).size(theme::CAPTION));
}

fn bottom(app: &mut CraftApp, ui: &mut Ui) {
    let t = Tokens::get(ui.ctx());
    ui.horizontal(|ui| {
        let n_jobs = app.jobs.running().filter(|j| j.visible).count();
        let jobs_title = if n_jobs > 0 { crate::i18n::trf("Jobs ({n})", &[("n", &n_jobs.to_string())]) } else { tr("Jobs") };
        let tabs = [("bot", "Agent"), ("activity", jobs_title.as_str()), ("terminal", "Log")];
        let sel = match app.state.bottom {
            BottomTab::Agent => 0,
            BottomTab::Jobs => 1,
            BottomTab::Log => 2,
        };
        if let Some(i) = tab_strip(ui, &tabs, sel) {
            app.state.bottom = [BottomTab::Agent, BottomTab::Jobs, BottomTab::Log].get(i).copied().unwrap_or_default();
        }
        ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
            if icons::button(ui, "chevron-down", 24.0, false, "Hide the console").clicked() {
                app.state.bottom_open = false;
            }
            status_line(app, ui);
        });
    });
    ui.painter().hline(ui.max_rect().x_range(), ui.cursor().top(), egui::Stroke::new(1.0, t.separator));
    ui.add_space(6.0);
    match app.state.bottom {
        BottomTab::Agent => chat::conversation(app, ui, true),
        BottomTab::Jobs => jobs(app, ui),
        BottomTab::Log => log_view(app, ui),
    }
}

fn jobs(app: &mut CraftApp, ui: &mut Ui) {
    let t = Tokens::get(ui.ctx());
    let visible: Vec<_> = app.jobs.list.iter().filter(|j| j.visible).collect();
    if visible.is_empty() {
        ui.label(RichText::new(tr("No jobs yet. Long tasks show their progress here, and you can cancel them.")).color(t.text_faint));
        return;
    }
    let mut cancel = None;
    let mut clear = false;
    egui::ScrollArea::vertical().auto_shrink([false, false]).show(ui, |ui| {
        for j in visible.iter().rev() {
            ui.horizontal(|ui| {
                let (icon, col) = match &j.outcome {
                    None => ("loader", t.accent),
                    Some(Ok(())) => ("check", t.success),
                    Some(Err(_)) => ("triangle-alert", t.danger),
                };
                icons::show(ui, icon, 14.0, col);
                ui.add_sized(Vec2::new(220.0, 18.0), egui::Label::new(RichText::new(tr(&j.title)).font(theme::medium(theme::CAPTION))).truncate());
                let secs = j.finished_at.unwrap_or_else(std::time::Instant::now).duration_since(j.started).as_secs_f32();
                ui.label(RichText::new(format!("{secs:.1}s")).font(theme::mono(11.5)).color(t.text_faint));
                match &j.outcome {
                    None => {
                        let p = j.progress();
                        let frac = p.as_ref().and_then(|p| p.fraction).unwrap_or(0.0);
                        let bar = egui::ProgressBar::new(frac).desired_width(160.0).desired_height(8.0).fill(t.accent);
                        ui.add(if p.as_ref().and_then(|p| p.fraction).is_none() { bar.animate(true) } else { bar });
                        if let Some(p) = p {
                            ui.label(RichText::new(p.message).color(t.text_dim).size(theme::CAPTION));
                        }
                        if icons::button(ui, "x", 24.0, false, "Cancel").clicked() {
                            cancel = Some(j.id);
                        }
                    }
                    Some(Err(e)) => {
                        ui.add(egui::Label::new(RichText::new(e).color(t.danger).size(theme::CAPTION)).truncate());
                    }
                    Some(Ok(())) => {}
                }
            });
        }
        ui.add_space(4.0);
        if widgets::link(ui, "Clear finished").clicked() {
            clear = true;
        }
    });
    if let Some(id) = cancel {
        app.jobs.cancel(id);
    }
    if clear {
        app.jobs.clear_finished();
    }
}

fn log_view(app: &CraftApp, ui: &mut Ui) {
    let t = Tokens::get(ui.ctx());
    let start = app.log.first().map(|l| l.at);
    egui::ScrollArea::vertical().auto_shrink([false, false]).stick_to_bottom(true).show(ui, |ui| {
        for l in &app.log {
            let secs = start.map(|s| l.at.duration_since(s).as_secs_f32()).unwrap_or(0.0);
            ui.horizontal(|ui| {
                ui.label(RichText::new(format!("{secs:>8.2}")).font(theme::mono(11.5)).color(t.text_faint));
                ui.label(RichText::new(&l.text).font(theme::mono(11.5)).color(if l.error { t.danger } else { t.text_dim }));
            });
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rows_are_found_in_common_shapes() {
        assert_eq!(rows(&json!([1, 2])).len(), 2);
        assert_eq!(rows(&json!({"total": 3, "functions": [{"name": "main", "address": 4096}]})).len(), 1);
        assert_eq!(rows(&json!({"weird": [1, 2, 3]})).len(), 3);
        assert!(rows(&json!("x")).is_empty());
        let r = json!({"name": "main", "address": 4096});
        assert_eq!(row_address(&r).as_deref(), Some("0x1000"));
        assert_eq!(row_name(&r).as_deref(), Some("main"));
        assert!(row_text(&r).contains("main"));
    }

    #[test]
    fn highlighting_never_panics_on_odd_lines() {
        let t = Tokens::for_kind(crate::theme::ThemeKind::Studio);
        for l in ["", "\"unterminated", "if (x) { return 0x10; } // done", "mov eax, 1 ; comment", "日本語 \"文字\""] {
            let _ = highlight(l, &t);
        }
    }
}
