//! Small shared widgets drawn from theme tokens: cards, buttons, pills, badges, empty states.

use crate::i18n::tr;
use crate::icons;
use crate::theme::{self, Tokens, confidence_color, confidence_label};
use craft_anything_engine::evidence::Confidence;
use egui::{Color32, Frame, Margin, Response, RichText, Sense, Stroke, Ui, Vec2};

/// Lay out `text` in the label style ([`theme::label_text`]) for painting.
pub fn label_galley(ui: &Ui, text: &str, size: f32, color: Color32) -> std::sync::Arc<egui::Galley> {
    egui::WidgetText::from(theme::label_text(text, size).color(color)).into_galley(
        ui,
        Some(egui::TextWrapMode::Extend),
        f32::INFINITY,
        egui::FontSelection::Default,
    )
}

/// 0..1 as the pointer rests on `resp` (a short ease, so hover states don't snap).
pub fn hover_t(ui: &Ui, resp: &Response) -> f32 {
    ui.ctx().animate_bool_with_time(resp.id.with("hover-t"), resp.hovered() || resp.has_focus(), 0.12)
}

/// The frame every text field uses: a field-coloured box with a 3:1 border and roomy padding.
pub fn text_field_frame(t: &Tokens) -> Frame {
    Frame::new().fill(t.field).stroke(Stroke::new(1.0, t.field_border)).corner_radius(t.r()).inner_margin(Margin::symmetric(12, 10))
}

/// The text-field frame for dense panels (filters, offsets, forms).
pub fn text_field_frame_compact(t: &Tokens) -> Frame {
    text_field_frame(t).inner_margin(Margin::symmetric(8, 6))
}

/// A switch with a label, in place of a checkbox. Flips `on` when clicked.
pub fn toggle(ui: &mut Ui, on: &mut bool, label: &str) -> Response {
    let t = Tokens::get(ui.ctx());
    // The label wraps to the room left, so a long one can't push a narrow panel wider.
    let wrap = (ui.available_width() - 42.0).max(80.0);
    let g = (!label.is_empty()).then(|| ui.painter().layout(tr(label), egui::FontId::proportional(theme::SMALL), t.text, wrap));
    let w = 32.0 + g.as_ref().map_or(0.0, |g| g.size().x + 10.0);
    let h = g.as_ref().map_or(24.0, |g| g.size().y.max(24.0));
    let (rect, mut resp) = ui.allocate_exact_size(Vec2::new(w, h), Sense::click());
    if resp.clicked() {
        *on = !*on;
        resp.mark_changed();
    }
    let how = ui.ctx().animate_bool_with_time(resp.id, *on, 0.12);
    let sw = egui::Rect::from_min_size(egui::pos2(rect.left(), rect.top() + 3.0), Vec2::new(32.0, 18.0));
    ui.painter().rect(sw, 9.0, theme::mix(t.field, t.accent, how), Stroke::new(1.0, theme::mix(t.field_border, t.accent, how)), egui::StrokeKind::Inside);
    let knob = egui::pos2(egui::lerp(sw.left() + 9.0..=sw.right() - 9.0, how), sw.center().y);
    ui.painter().circle_filled(knob, 6.0, theme::mix(t.text_dim, Color32::WHITE, how));
    if let Some(g) = g {
        ui.painter().galley(egui::pos2(sw.right() + 10.0, rect.center().y - g.size().y / 2.0), g, t.text);
    }
    focus_ring(ui, &resp, sw);
    let state = *on;
    resp.widget_info(|| egui::WidgetInfo::selected(egui::WidgetType::Checkbox, true, state, tr(label)));
    resp.on_hover_cursor(egui::CursorIcon::PointingHand)
}

/// The dropdown arrow for every combo box: a Lucide chevron instead of egui's filled triangle.
pub fn combo_icon(ui: &Ui, rect: egui::Rect, _visuals: &egui::style::WidgetVisuals, _open: bool) {
    icons::paint(ui, rect.expand(2.0), "chevron-down", 14.0, Tokens::get(ui.ctx()).icon);
}

/// The disclosure arrow for every collapsing section: a Lucide chevron.
pub fn disclosure_icon(ui: &mut Ui, openness: f32, resp: &Response) {
    let t = Tokens::get(ui.ctx());
    let r = egui::Rect::from_center_size(resp.rect.center(), Vec2::splat(12.0));
    icons::paint(ui, r, if openness > 0.5 { "chevron-down" } else { "chevron-right" }, 12.0, t.text_faint);
}

/// Give a field without a visible label a name for screen readers (WCAG 4.1.2); egui doesn't
/// use the hint text for that.
pub fn named(resp: Response, name: &str) -> Response {
    resp.ctx.accesskit_node_builder(resp.id, |b| b.set_label(tr(name)));
    resp
}

/// A suggestion: a sentence in a hairline box that fills in a field when clicked. Wraps when
/// it's wider than the space it has; fills the width in a justified layout (a tidy list).
pub fn suggestion(ui: &mut Ui, text: &str) -> Response {
    let t = Tokens::get(ui.ctx());
    let max_w = ui.available_width().max(60.0);
    let g = ui.painter().layout(tr(text), egui::FontId::proportional(theme::SMALL), t.text, max_w - 26.0);
    let w = if ui.layout().horizontal_justify() { max_w } else { (g.size().x + 26.0).min(max_w) };
    let (rect, resp) = ui.allocate_exact_size(Vec2::new(w, (g.size().y + 14.0).max(32.0)), Sense::click());
    let h = hover_t(ui, &resp);
    ui.painter().rect(
        rect,
        t.radius,
        theme::mix(Color32::TRANSPARENT, t.hover, h),
        Stroke::new(1.0, theme::mix(t.card_border, t.field_border, h)),
        egui::StrokeKind::Inside,
    );
    let pos = egui::pos2(rect.left() + 13.0, rect.center().y - g.size().y / 2.0);
    ui.painter().galley_with_override_text_color(pos, g, theme::mix(t.text_dim, t.text, h));
    focus_ring(ui, &resp, rect);
    resp.widget_info(|| egui::WidgetInfo::labeled(egui::WidgetType::Button, true, tr(text)));
    resp.on_hover_cursor(egui::CursorIcon::PointingHand)
}

/// A big, radio-like choice with an icon and plain words (and an optional line under them,
/// empty for none); the chosen one is in the app colour with a tick (so it doesn't rely on
/// colour alone). It grows taller when the words need it.
pub fn choice_tile(ui: &mut Ui, size: Vec2, icon: &str, label: &str, blurb: &str, on: bool) -> Response {
    let t = Tokens::get(ui.ctx());
    let wrap = size.x - 84.0;
    let g = ui.painter().layout(tr(label), theme::medium(theme::BODY), t.text, wrap);
    let sub = (!blurb.is_empty()).then(|| ui.painter().layout(tr(blurb), egui::FontId::proportional(theme::SMALL), t.text_dim, wrap));
    let text_h = g.size().y + sub.as_ref().map_or(0.0, |s| s.size().y + 3.0);
    let (rect, resp) = ui.allocate_exact_size(Vec2::new(size.x, size.y.max(text_h + 24.0)), Sense::click());
    let h = hover_t(ui, &resp);
    let (fill, stroke) = if on {
        (t.accent_soft, Stroke::new(2.0, t.accent))
    } else {
        (theme::mix(Color32::TRANSPARENT, t.hover, h), Stroke::new(1.0, theme::mix(t.field_border, t.text_faint, h)))
    };
    ui.painter().rect(rect, t.radius, fill, stroke, egui::StrokeKind::Inside);
    let icon_rect = egui::Rect::from_center_size(egui::pos2(rect.left() + 28.0, rect.center().y), Vec2::splat(24.0));
    icons::paint(ui, icon_rect, icon, 22.0, if on { t.accent_ink } else { t.icon });
    let top = egui::pos2(icon_rect.right() + 12.0, rect.center().y - text_h / 2.0);
    let title_h = g.size().y;
    ui.painter().galley(top, g, t.text);
    if let Some(s) = sub {
        ui.painter().galley(top + Vec2::new(0.0, title_h + 3.0), s, t.text_dim);
    }
    if on {
        icons::paint(ui, egui::Rect::from_center_size(egui::pos2(rect.right() - 20.0, rect.center().y), Vec2::splat(18.0)), "check", 18.0, t.accent_ink);
    }
    focus_ring(ui, &resp, rect);
    resp.widget_info(|| egui::WidgetInfo::selected(egui::WidgetType::RadioButton, true, on, tr(label)));
    resp.on_hover_cursor(egui::CursorIcon::PointingHand)
}

/// A visible keyboard-focus ring around `rect` when `resp` has focus (2 px accent, outside).
pub fn focus_ring(ui: &Ui, resp: &Response, rect: egui::Rect) {
    if resp.has_focus() {
        let t = Tokens::get(ui.ctx());
        ui.painter().rect_stroke(rect.expand(2.0), t.radius + 2.0, Stroke::new(2.0, t.accent), egui::StrokeKind::Outside);
    }
}

/// A card frame: a soft rounded box with a hairline edge.
pub fn card(t: &Tokens) -> Frame {
    Frame::new().fill(t.card).stroke(Stroke::new(1.0, t.card_border)).corner_radius(t.r_lg()).inner_margin(Margin::same(16))
}

/// A quieter, denser panel frame for the workbench.
pub fn panel(t: &Tokens) -> Frame {
    Frame::new().fill(t.card).stroke(Stroke::new(1.0, t.card_border)).corner_radius(t.r()).inner_margin(Margin::same(10))
}

/// The main action: an ink-filled button (light on dark in the dark theme).
pub fn primary(ui: &mut Ui, label: &str) -> Response {
    primary_icon(ui, None, label, true)
}

pub fn primary_icon(ui: &mut Ui, icon: Option<&str>, label: &str, enabled: bool) -> Response {
    primary_sized(ui, icon, label, enabled, 32.0, 12.5)
}

/// The main button at a given height and label size (Simple mode's Start is a big one).
pub fn primary_sized(ui: &mut Ui, icon: Option<&str>, label: &str, enabled: bool, height: f32, text: f32) -> Response {
    let t = Tokens::get(ui.ctx());
    let galley = label_galley(ui, &tr(label), text, t.canvas);
    let icon_w = if icon.is_some() { BUTTON_ICON_W } else { 0.0 };
    let pad = ui.spacing().button_padding;
    let size = Vec2::new(galley.size().x + icon_w + pad.x * 2.0 + 8.0 + (height - 32.0).max(0.0), (galley.size().y + pad.y * 2.0 + 8.0).max(height));
    let sense = if enabled { Sense::click() } else { Sense::hover() };
    let (rect, resp) = ui.allocate_exact_size(size, sense);
    let fill = if !enabled {
        t.pressed
    } else if resp.is_pointer_button_down_on() {
        theme::mix(t.text, t.canvas, 0.25)
    } else {
        theme::mix(t.text, t.canvas, 0.14 * hover_t(ui, &resp))
    };
    ui.painter().rect_filled(rect, t.radius, fill);
    let fg = if enabled { t.canvas } else { t.text_faint };
    button_content(ui, rect, icon, galley, fg, fg);
    focus_ring(ui, &resp, rect);
    resp.widget_info(|| egui::WidgetInfo::labeled(egui::WidgetType::Button, enabled, tr(label)));
    if enabled { resp.on_hover_cursor(egui::CursorIcon::PointingHand) } else { resp }
}

/// Secondary button: a card-coloured box with a soft edge and an optional icon.
pub fn secondary(ui: &mut Ui, icon: Option<&str>, label: &str) -> Response {
    let t = Tokens::get(ui.ctx());
    let galley = label_galley(ui, &tr(label), 12.0, t.text);
    let icon_w = if icon.is_some() { BUTTON_ICON_W } else { 0.0 };
    let pad = ui.spacing().button_padding;
    let size = Vec2::new(galley.size().x + icon_w + pad.x * 2.0 + 6.0, (galley.size().y + pad.y * 2.0 + 6.0).max(30.0));
    let (rect, resp) = ui.allocate_exact_size(size, Sense::click());
    let h = hover_t(ui, &resp);
    let fill = if resp.is_pointer_button_down_on() { t.pressed } else { theme::mix(t.card, t.hover, h) };
    let stroke = theme::mix(t.card_border, t.field_border, h);
    ui.painter().rect(rect, t.radius, fill, Stroke::new(1.0, stroke), egui::StrokeKind::Inside);
    button_content(ui, rect, icon, galley, t.text, t.icon);
    focus_ring(ui, &resp, rect);
    resp.widget_info(|| egui::WidgetInfo::labeled(egui::WidgetType::Button, true, tr(label)));
    resp.on_hover_cursor(egui::CursorIcon::PointingHand)
}

/// A button's icon and label, centred together in `rect`.
fn button_content(ui: &Ui, rect: egui::Rect, icon: Option<&str>, galley: std::sync::Arc<egui::Galley>, fg: Color32, icon_tint: Color32) {
    let icon_w = if icon.is_some() { BUTTON_ICON_W } else { 0.0 };
    let mut x = (rect.center().x - (icon_w + galley.size().x) / 2.0).round();
    if let Some(i) = icon {
        icons::paint(ui, egui::Rect::from_min_size(egui::pos2(x, rect.center().y - 8.0), Vec2::splat(16.0)), i, 15.0, icon_tint);
        x += icon_w;
    }
    ui.painter().galley_with_override_text_color(egui::pos2(x, rect.center().y - galley.size().y / 2.0), galley, fg);
}

/// A button icon (16 px) and the gap after it.
const BUTTON_ICON_W: f32 = 22.0;

/// A borderless text button in the accent colour.
pub fn link(ui: &mut Ui, label: &str) -> Response {
    let t = Tokens::get(ui.ctx());
    let r = ui.add(egui::Label::new(RichText::new(tr(label)).color(t.accent_ink)).sense(Sense::click()));
    let r = r.on_hover_cursor(egui::CursorIcon::PointingHand);
    if r.hovered() {
        let y = r.rect.bottom();
        ui.painter().hline(r.rect.x_range(), y, Stroke::new(1.0, t.accent_ink));
    }
    r
}

/// A segmented switch; the selected segment is a raised card on a sunken track. Returns the newly
/// picked index when it changes.
pub fn segmented(ui: &mut Ui, options: &[&str], selected: usize, height: f32) -> Option<usize> {
    segmented_sized(ui, options, selected, height, 12.0)
}

/// [`segmented`] with a given label size (in the [`label_galley`] style), for a bigger switch.
pub fn segmented_sized(ui: &mut Ui, options: &[&str], selected: usize, height: f32, text: f32) -> Option<usize> {
    let t = Tokens::get(ui.ctx());
    let galleys: Vec<_> = options.iter().map(|o| label_galley(ui, &tr(o), text, t.text)).collect();
    let widths: Vec<f32> = galleys.iter().map(|g| g.size().x + text * 2.0 + 2.0).collect();
    let total: f32 = widths.iter().sum::<f32>() + 4.0;
    let (rect, _) = ui.allocate_exact_size(Vec2::new(total, height), Sense::hover());
    ui.painter().rect(rect, t.radius, t.raised, Stroke::new(1.0, t.card_border), egui::StrokeKind::Inside);
    let mut x = rect.left() + 2.0;
    let mut picked = None;
    for (i, (g, w)) in galleys.into_iter().zip(widths).enumerate() {
        let seg = egui::Rect::from_min_size(egui::pos2(x, rect.top() + 2.0), Vec2::new(w, height - 4.0));
        let resp = ui.interact(seg, ui.id().with(("seg", options.get(i).copied().unwrap_or_default())), Sense::click());
        let on = i == selected;
        resp.widget_info(|| egui::WidgetInfo::selected(egui::WidgetType::SelectableLabel, true, on, tr(options.get(i).copied().unwrap_or_default())));
        if on {
            ui.painter().rect(seg, t.radius_sm, t.card, Stroke::new(1.0, t.card_border), egui::StrokeKind::Inside);
        } else {
            ui.painter().rect_filled(seg, t.radius_sm, theme::mix(Color32::TRANSPARENT, t.hover, hover_t(ui, &resp)));
        }
        let color = if on { t.text } else { t.text_dim };
        ui.painter().galley_with_override_text_color(seg.center() - g.size() / 2.0, g, color);
        focus_ring(ui, &resp, seg);
        let resp = if on { resp } else { resp.on_hover_cursor(egui::CursorIcon::PointingHand) };
        if resp.clicked() && !on {
            picked = Some(i);
        }
        x += w;
    }
    picked
}

/// A small status label on a tint.
pub fn pill(ui: &mut Ui, text: &str, fg: Color32, bg: Color32) -> Response {
    let t = Tokens::get(ui.ctx());
    let label = tr(text);
    let g = label_galley(ui, &label, 11.0, fg);
    let size = Vec2::new(g.size().x + 14.0, g.size().y + 8.0);
    let (rect, resp) = ui.allocate_exact_size(size, Sense::hover());
    ui.painter().rect_filled(rect, t.r_sm(), bg);
    ui.painter().galley_with_override_text_color(rect.center() - g.size() / 2.0, g, fg);
    // Painted text: say it to screen readers too.
    resp.widget_info(|| egui::WidgetInfo::labeled(egui::WidgetType::Label, true, &label));
    resp
}

/// The "how sure are we" badge: a coloured dot and the plain label.
pub fn confidence_badge(ui: &mut Ui, c: Option<Confidence>) -> Response {
    let t = Tokens::get(ui.ctx());
    let col = confidence_color(c);
    let font = theme::medium(theme::CAPTION);
    let g = ui.painter().layout_no_wrap(tr(confidence_label(c)), font, col);
    let size = Vec2::new(g.size().x + 26.0, g.size().y + 7.0);
    let (rect, resp) = ui.allocate_exact_size(size, Sense::hover());
    let bg = Color32::from_rgba_unmultiplied(col.r(), col.g(), col.b(), 34);
    ui.painter().rect(rect, t.r_sm(), bg, Stroke::new(1.0, col.gamma_multiply(0.45)), egui::StrokeKind::Inside);
    ui.painter().circle_filled(egui::pos2(rect.left() + 10.0, rect.center().y), 3.5, col);
    ui.painter().galley_with_override_text_color(egui::pos2(rect.left() + 18.0, rect.center().y - g.size().y / 2.0), g, col);
    let tip = match c {
        Some(Confidence::Observed) => "Seen it: read directly from the file, page or capture.",
        Some(Confidence::Derived) => "Worked it out: computed step by step from things we saw.",
        Some(Confidence::Inferred) => "Best guess: a reasonable reading, but not proven.",
        None => "Unknown: we couldn't establish this yet.",
    };
    resp.on_hover_text(tr(tip))
}

/// A section caption in the label style, faint.
pub fn caption(ui: &mut Ui, text: &str) {
    let t = Tokens::get(ui.ctx());
    ui.label(theme::label_text(&tr(text), 12.0).color(t.text_faint));
}

/// A centred, calm empty state.
pub fn empty_state(ui: &mut Ui, icon: &str, title: &str, body: &str) {
    let t = Tokens::get(ui.ctx());
    ui.vertical_centered(|ui| {
        ui.add_space(18.0);
        let (rect, _) = ui.allocate_exact_size(Vec2::splat(44.0), Sense::hover());
        ui.painter().circle_filled(rect.center(), 22.0, t.raised);
        icons::paint(ui, rect, icon, 22.0, t.text_faint);
        ui.add_space(6.0);
        ui.label(RichText::new(tr(title)).font(theme::medium(theme::SMALL)).color(t.text_dim));
        if !body.is_empty() {
            ui.label(RichText::new(tr(body)).color(t.text_faint).size(theme::CAPTION));
        }
        ui.add_space(12.0);
    });
}

/// A big clickable card with an icon, title and blurb (Beginner Home).
pub fn big_card(ui: &mut Ui, size: Vec2, icon: &str, title: &str, blurb: &str, badge: Option<&str>) -> Response {
    let t = Tokens::get(ui.ctx());
    let (rect, resp) = ui.allocate_exact_size(size, Sense::click());
    let hovered = resp.hovered();
    let fill = t.card;
    let stroke = Stroke::new(1.0, if hovered { t.field_border } else { t.card_border });
    if hovered {
        ui.painter().add(egui::Shadow { offset: [0, 8], blur: 24, spread: 0, color: t.shadow }.as_shape(rect, t.r_lg()));
    }
    ui.painter().rect(rect, t.radius_lg, fill, stroke, egui::StrokeKind::Inside);
    let icon_rect = egui::Rect::from_min_size(rect.min + Vec2::new(22.0, 22.0), Vec2::splat(52.0));
    ui.painter().rect_filled(icon_rect, t.radius, t.accent_soft);
    icons::paint(ui, icon_rect, icon, 28.0, t.accent_ink);
    if let Some(b) = badge {
        let g = ui.painter().layout_no_wrap(tr(b), theme::medium(theme::TINY), t.text_dim);
        let br = egui::Rect::from_min_size(egui::pos2(rect.right() - g.size().x - 34.0, rect.top() + 22.0), g.size() + Vec2::new(16.0, 8.0));
        ui.painter().rect_filled(br, t.r_sm(), t.hover);
        ui.painter().galley_with_override_text_color(br.center() - g.size() / 2.0, g, t.text_dim);
    }
    let title_pos = egui::pos2(rect.left() + 22.0, icon_rect.bottom() + 18.0);
    // Titles wrap: the display face is wide, and translations are longer.
    let title_g = theme::heading_galley(ui.painter(), tr(title), theme::CARD, t.text, rect.width() - 44.0);
    let title_h = title_g.size().y;
    ui.painter().galley(title_pos, title_g, t.text);
    let wrap = ui.painter().layout(tr(blurb), egui::FontId::proportional(theme::SMALL), t.text_dim, rect.width() - 44.0);
    ui.painter().galley(title_pos + Vec2::new(0.0, title_h + 8.0), wrap, t.text_dim);
    focus_ring(ui, &resp, rect);
    resp.widget_info(|| egui::WidgetInfo::labeled(egui::WidgetType::Button, true, tr(title)));
    resp.on_hover_cursor(egui::CursorIcon::PointingHand)
}

/// A dotted underline under a hoverable glossary word.
pub fn glossary_word(ui: &mut Ui, word: &str, meaning: &str, font: egui::FontId) -> Response {
    let t = Tokens::get(ui.ctx());
    let resp = ui.add(egui::Label::new(RichText::new(word).font(font).color(t.text)).sense(Sense::hover()));
    let y = resp.rect.bottom() - 1.0;
    let mut x = resp.rect.left();
    let trimmed_right = resp.rect.right() - if word.ends_with(' ') { 4.0 } else { 0.0 };
    while x < trimmed_right {
        ui.painter().hline(x..=(x + 2.0).min(trimmed_right), y, Stroke::new(1.0, t.accent));
        x += 4.0;
    }
    resp.on_hover_ui(|ui| {
        ui.label(RichText::new(word.trim()).font(theme::semibold(theme::SMALL)));
        ui.label(tr(meaning));
    })
}

/// Draw an animation's next frame in `every` (about 15 a second is smooth enough for a spinner),
/// or once a second while the window is in the background: a build can run for an hour, and
/// redrawing the whole window 30 times a second for it costs the battery.
pub fn animate(ui: &Ui, every: std::time::Duration) {
    let focused = ui.input(|i| i.viewport().focused.unwrap_or(true));
    ui.ctx().request_repaint_after(if focused { every } else { std::time::Duration::from_secs(1) });
}

/// One frame of an animation at the usual pace.
pub const FRAME: std::time::Duration = std::time::Duration::from_millis(66);

/// A spinner-ish dot row for "thinking".
pub fn thinking(ui: &mut Ui) {
    let t = Tokens::get(ui.ctx());
    let time = ui.input(|i| i.time);
    let (rect, _) = ui.allocate_exact_size(Vec2::new(36.0, 14.0), Sense::hover());
    for i in 0..3 {
        let phase = ((time * 3.0 - i as f64 * 0.5).sin() * 0.5 + 0.5) as f32;
        let c = t.accent.gamma_multiply(0.35 + 0.65 * phase);
        ui.painter().circle_filled(egui::pos2(rect.left() + 6.0 + i as f32 * 12.0, rect.center().y), 3.5, c);
    }
    animate(ui, FRAME);
}

/// How long a run may say nothing before the note points it out.
const QUIET_NOTE_AFTER: std::time::Duration = std::time::Duration::from_secs(60);

fn wait_note(secs: u64, quiet: Option<std::time::Duration>) -> Option<String> {
    match quiet {
        Some(q) if q >= QUIET_NOTE_AFTER => Some(crate::i18n::trf(
            "Nothing new for {time}. Long steps can be quiet; if it stays like this, press Pause.",
            &[("time", &crate::usage::duration_words(q))],
        )),
        Some(_) => None,
        None => match secs {
            0..20 => None,
            20..90 => Some(tr("Still working. Bigger jobs can take a few minutes.")),
            _ => Some(tr("This is a big one. You can leave this open and come back later.")),
        },
    }
}

/// "Still working" for waits longer than a moment: a spinning arc, what's happening, how long
/// it has taken, and a calm note once it runs long (so a quiet wait never looks stuck).
/// `title` is translated here; `detail` arrives already in the user's words.
pub fn working(ui: &mut Ui, title: &str, detail: Option<&str>) {
    working_since(ui, title, detail, None, None);
}

/// [`working`] with its clock from `began` (a build's start), so it doesn't restart each time the
/// row comes back; without it, from when the row was last shown.
///
/// `quiet` is how long since the work last had anything to say, when that's known: then the note
/// says so plainly, because a calm note can't tell a long step from one that has stopped.
pub fn working_since(ui: &mut Ui, title: &str, detail: Option<&str>, began: Option<std::time::Instant>, quiet: Option<std::time::Duration>) {
    let t = Tokens::get(ui.ctx());
    let now = ui.input(|i| i.time);
    // The clock restarts when the row wasn't on screen a moment ago.
    let id = ui.id().with("working-since");
    let (since, seen) = ui.data(|d| d.get_temp::<(f64, f64)>(id)).unwrap_or((now, now));
    let since = if now - seen > 1.0 { now } else { since };
    ui.data_mut(|d| d.insert_temp(id, (since, now)));
    let secs = began.map_or((now - since) as u64, |b| b.elapsed().as_secs());
    let note = wait_note(secs, quiet);
    let sub = [detail.map(str::to_string), note].into_iter().flatten().collect::<Vec<_>>().join("  ·  ");
    card(&t).inner_margin(Margin::symmetric(16, 12)).show(ui, |ui| {
        ui.set_width(ui.available_width());
        ui.horizontal(|ui| {
            let (r, _) = ui.allocate_exact_size(Vec2::splat(24.0), Sense::hover());
            let (c, radius) = (r.center(), 9.0);
            ui.painter().circle_stroke(c, radius, Stroke::new(2.5, t.separator));
            let start = (now * 4.0) as f32;
            let sweep = std::f32::consts::PI * (0.9 + 0.5 * (now * 1.7).sin() as f32);
            let arc = (0..=20).map(|i| c + radius * Vec2::angled(start + sweep * i as f32 / 20.0)).collect();
            ui.painter().add(egui::Shape::line(arc, Stroke::new(2.5, t.accent)));
            ui.add_space(4.0);
            ui.vertical(|ui| {
                ui.label(RichText::new(tr(title)).font(theme::semibold(theme::BODY)).color(t.text));
                if !sub.is_empty() {
                    ui.add(egui::Label::new(RichText::new(sub).color(t.text_dim).size(theme::SMALL)).wrap());
                }
            });
            ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                let clock = crate::usage::duration_words(std::time::Duration::from_secs(secs));
                ui.label(RichText::new(clock).font(theme::mono(12.5)).color(t.text_faint));
            });
        });
        // An indeterminate sweep along the bottom: movement even when nothing new has arrived.
        ui.add_space(10.0);
        let (bar, _) = ui.allocate_exact_size(Vec2::new(ui.available_width(), 2.0), Sense::hover());
        ui.painter().rect_filled(bar, 1.0, t.separator);
        let seg = bar.width() * 0.25;
        let x = bar.left() - seg + (bar.width() + seg) * ((now * 0.6).fract() as f32);
        let lit = egui::Rect::from_x_y_ranges(x.max(bar.left())..=(x + seg).min(bar.right()), bar.y_range());
        ui.painter().rect_filled(lit, 1.0, t.accent);
    });
    animate(ui, FRAME);
}

/// The button that opens a failure's log; hovering shows where the log is. True when clicked.
pub fn open_log_button(ui: &mut Ui, path: &std::path::Path) -> bool {
    ui.add_space(6.0);
    secondary(ui, None, "Open log").on_hover_text(path.display().to_string()).clicked()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Duration;

    #[test]
    fn the_wait_note_says_when_nothing_is_happening() {
        let quiet = wait_note(4000, Some(Duration::from_secs(150))).unwrap();
        assert!(quiet.contains("Nothing new for") && !quiet.contains("big one"), "{quiet}");
        assert_eq!(wait_note(4000, Some(Duration::from_secs(5))), None, "it's visibly moving: nothing to add");
        assert!(wait_note(4000, None).unwrap().contains("big one"), "without news to go on, the old note");
    }
}
