//! The prompt box used everywhere the person types to the builder or the assistant: it grows
//! with the text (Enter sends, Shift+Enter adds a line), shows attached pictures as chips, and
//! has the attach, stop and send buttons in its bottom row. Up at the start of the box takes back
//! the last message still waiting, to edit it; with none waiting, Up at the very start and Down at
//! the very end go through earlier prompts, and Down past the newest brings back what was being
//! typed. Anywhere else they move the cursor as usual.

use crate::i18n::{tr, trf};
use crate::theme::{self, Tokens};
use crate::{icons, widgets};
use egui::{Margin, RichText, Ui};
use std::path::PathBuf;

/// How one prompt box looks and behaves.
pub struct PromptBox<'a> {
    /// The accessible name, and the id of the text field.
    pub name: &'a str,
    pub hint: String,
    /// Visible text rows: (at least, at most before it scrolls).
    pub rows: (usize, usize),
    /// The paperclip's tooltip; `None` hides it (no attachments here).
    pub attach: Option<&'a str>,
    /// A run or answer is in progress: a stop button beside Send, named this ("Stop", "Pause").
    pub stop_button: Option<&'a str>,
    /// Show the send button (the Make screen has its own big Start button).
    pub send: bool,
    /// A sent message is still waiting and can be taken back: Up at the start of the box asks for it.
    pub recall: bool,
    /// Earlier prompts, oldest first, for Up and Down; read only when a key asks for them.
    pub history: Option<&'a dyn Fn() -> Vec<String>>,
    pub font_size: f32,
}

/// Going through earlier prompts: how far back, and what the box holds for it to still count.
#[derive(Debug, Clone, Default, PartialEq)]
struct Browsing {
    back: usize,
    shown: String,
    /// What was being typed, for Down past the newest.
    draft: String,
}

/// The prompt before the one showing; none when there's no earlier one.
fn older(history: &[String], now: Option<&Browsing>, text: &str) -> Option<Browsing> {
    let back = now.map_or(1, |b| b.back + 1);
    let shown = history.get(history.len().checked_sub(back)?)?.clone();
    Some(Browsing { back, shown, draft: now.map_or_else(|| text.to_string(), |b| b.draft.clone()) })
}

/// The prompt after the one showing, or what was being typed once past the newest.
fn newer(history: &[String], now: &Browsing) -> Result<Browsing, String> {
    let back = now.back.saturating_sub(1);
    match history.len().checked_sub(back).and_then(|i| history.get(i)) {
        Some(shown) if back > 0 => Ok(Browsing { back, shown: shown.clone(), draft: now.draft.clone() }),
        _ => Err(now.draft.clone()),
    }
}

/// Up at the start or Down at the end went through earlier prompts: consumed before the field
/// sees them. Up leaves the cursor at the start and Down at the end, so pressing it again goes on.
fn browse(ui: &mut Ui, id: egui::Id, text: &mut String, history: &dyn Fn() -> Vec<String>) {
    let key = id.with("history");
    // Editing what came back, or sending it, ends going through them.
    let now = ui.data_mut(|d| d.get_temp::<Browsing>(key)).filter(|b| b.shown == *text);
    let list = || {
        let mut list = history();
        list.dedup();
        list
    };
    let plain = egui::Modifiers::NONE;
    let up = at_start(ui.ctx(), id, text) && ui.input_mut(|i| i.consume_key(plain, egui::Key::ArrowUp));
    let next = if up {
        older(&list(), now.as_ref(), text).map(Ok)
    } else {
        now.as_ref().filter(|_| at_end(ui.ctx(), id, text) && ui.input_mut(|i| i.consume_key(plain, egui::Key::ArrowDown))).map(|b| newer(&list(), b))
    };
    match next {
        Some(Ok(b)) => {
            text.clone_from(&b.shown);
            ui.data_mut(|d| d.insert_temp(key, b));
        }
        Some(Err(draft)) => {
            *text = draft;
            ui.data_mut(|d| d.remove_temp::<Browsing>(key));
        }
        None => return,
    }
    if up {
        cursor_to(ui.ctx(), id, 0);
    } else {
        cursor_to_end(ui.ctx(), id, text);
    }
}

/// What the person did with it this frame.
#[derive(Default)]
pub struct PromptOut {
    /// Send was pressed (button or Enter) with something to send.
    pub send: bool,
    pub attach: bool,
    pub stop: bool,
    /// Up was pressed at the start of the box while a message could be taken back.
    pub recall: bool,
    /// The attachment to remove.
    pub remove: Option<usize>,
}

pub fn show(ui: &mut Ui, text: &mut String, attachments: &[PathBuf], b: PromptBox) -> PromptOut {
    let t = Tokens::get(ui.ctx());
    let mut out = PromptOut::default();
    let id = ui.make_persistent_id(("prompt-box", b.name));
    let focused = ui.memory(|m| m.has_focus(id));
    let stroke = egui::Stroke::new(1.0, if focused { t.text_faint } else { t.field_border });
    let frame = egui::Frame::new()
        .fill(t.card)
        .stroke(stroke)
        .corner_radius(t.r_lg())
        .shadow(egui::Shadow { offset: [0, 2], blur: 12, spread: 0, color: t.shadow })
        .inner_margin(Margin { left: 16, right: 10, top: 14, bottom: 10 });
    // Stacked top to bottom whatever the caller's layout (it's often placed in a row).
    frame.show(ui, |ui| {
        ui.with_layout(egui::Layout::top_down(egui::Align::Min), |ui| {
            ui.set_width(ui.available_width());
            if !attachments.is_empty() {
                ui.horizontal_wrapped(|ui| {
                    for (i, p) in attachments.iter().enumerate() {
                        let name = p.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
                        egui::Frame::new()
                            .fill(t.raised)
                            .stroke(egui::Stroke::new(1.0, t.card_border))
                            .corner_radius(t.r_sm())
                            .inner_margin(Margin { left: 8, right: 2, top: 2, bottom: 2 })
                            .show(ui, |ui| {
                                ui.horizontal(|ui| {
                                    icons::show(ui, "paperclip", 13.0, t.icon);
                                    ui.add(egui::Label::new(RichText::new(&name).size(theme::SMALL)).truncate()).on_hover_text(p.display().to_string());
                                    if icons::button(ui, "x", 24.0, false, &trf("Remove {name}", &[("name", &name)])).clicked() {
                                        out.remove = Some(i);
                                    }
                                });
                            });
                    }
                });
                ui.add_space(6.0);
            }
            let line = ui.fonts_mut(|f| f.row_height(&egui::FontId::proportional(b.font_size)));
            // Up at the very start (or in an empty box) takes back the last waiting message; it's
            // consumed before the field sees it, and anywhere else Up moves the cursor as usual.
            // The caller fills the text in after this frame; the cursor goes to its end on the next.
            let to_end = id.with("cursor-to-end");
            if ui.data_mut(|d| d.remove_temp::<bool>(to_end)).is_some() {
                cursor_to_end(ui.ctx(), id, text);
            }
            if b.recall && focused && at_start(ui.ctx(), id, text) && ui.input_mut(|i| i.consume_key(egui::Modifiers::NONE, egui::Key::ArrowUp)) {
                out.recall = true;
                ui.data_mut(|d| d.insert_temp(to_end, true));
            } else if let Some(history) = b.history.filter(|_| focused && !b.recall) {
                browse(ui, id, text, history);
            }
            // What Tab would complete to, when the box starts with a partial command name. egui
            // decides keyboard navigation at the start of the pass, so the field keeps Tab only
            // while there is something to complete; anywhere else Tab moves focus as usual.
            let completing = completed_command(text);
            if focused
                && let Some(completed) = &completing
                && ui.input_mut(|i| i.consume_key(egui::Modifiers::NONE, egui::Key::Tab))
            {
                text.clone_from(completed);
                cursor_to_end(ui.ctx(), id, text);
            }
            // No "more below" fade: the frame after each keystroke the scroll area briefly
            // measures a few points of overflow, and the fade blinked over the line being typed.
            ui.spacing_mut().scroll.fade.strength = 0.0;
            egui::ScrollArea::vertical().id_salt(id.with("scroll")).max_height(line * b.rows.1 as f32 + 4.0).stick_to_bottom(true).show(ui, |ui| {
                let r = ui.add(
                    egui::TextEdit::multiline(text)
                        .id(id)
                        .hint_text(&b.hint)
                        .frame(egui::Frame::NONE)
                        .desired_rows(b.rows.0)
                        .desired_width(f32::INFINITY)
                        .font(egui::FontId::proportional(b.font_size))
                        // Enter sends; Shift+Enter starts a new line.
                        .return_key(Some(egui::KeyboardShortcut::new(egui::Modifiers::SHIFT, egui::Key::Enter)))
                        .event_filter(egui::EventFilter {
                            tab: completing.is_some(),
                            horizontal_arrows: true,
                            vertical_arrows: true,
                            ..egui::EventFilter::default()
                        }),
                );
                widgets::named(r.clone(), b.name);
                if r.has_focus() && ui.input(|i| i.key_pressed(egui::Key::Enter) && !i.modifiers.shift) && !text.trim().is_empty() {
                    out.send = true;
                }
            });
            // Hint: available slash commands when typing one.
            if text.trim_start().starts_with('/') && !text.trim().contains(' ') {
                ui.label(RichText::new(format!("{} {}", tr("Commands:"), crate::slash::names())).size(theme::CAPTION).color(t.text_faint));
            }
            ui.add_space(4.0);
            ui.horizontal(|ui| {
                if let Some(tip) = b.attach
                    && icons::button(ui, "paperclip", 30.0, false, tip).clicked()
                {
                    out.attach = true;
                }
                ui.label(RichText::new(tr("Enter to send · Shift+Enter for a new line")).size(theme::CAPTION).color(t.text_faint));
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    if b.send {
                        let ready = !text.trim().is_empty();
                        if send_button(ui, ready).clicked() && ready {
                            out.send = true;
                        }
                    }
                    if let Some(name) = b.stop_button
                        && icons::button(ui, "circle-stop", 30.0, false, name).clicked()
                    {
                        out.stop = true;
                    }
                });
            });
        })
    });
    out
}

/// What Tab would complete the box to, when it starts with a partial command name. Only the
/// name is replaced, so a question after it is kept; `None` when there is nothing to complete.
fn completed_command(text: &str) -> Option<String> {
    let trimmed = text.trim_start();
    let rest = trimmed.strip_prefix('/')?;
    let name = rest.split_whitespace().next().unwrap_or(rest);
    if name.is_empty() || !name.chars().all(|c| c.is_ascii_alphanumeric() || c == '-') {
        return None;
    }
    let full = crate::slash::complete(name)?;
    if name.eq_ignore_ascii_case(full) {
        return None;
    }
    let leading = text.len() - trimmed.len();
    Some(format!("{}/{full} {}", &text[..leading], rest[name.len()..].trim_start()))
}

/// The cursor is at this character, selecting nothing (or there's no text, or no cursor yet).
fn cursor_at(ctx: &egui::Context, id: egui::Id, text: &str, index: usize) -> bool {
    text.is_empty()
        || egui::TextEdit::load_state(ctx, id).and_then(|s| s.cursor.char_range()).is_none_or(|r| r.primary.index.0 == index && r.secondary.index.0 == index)
}

fn at_start(ctx: &egui::Context, id: egui::Id, text: &str) -> bool {
    cursor_at(ctx, id, text, 0)
}

fn at_end(ctx: &egui::Context, id: egui::Id, text: &str) -> bool {
    cursor_at(ctx, id, text, text.chars().count())
}

fn cursor_to(ctx: &egui::Context, id: egui::Id, index: usize) {
    let mut state = egui::TextEdit::load_state(ctx, id).unwrap_or_default();
    state.cursor.set_char_range(Some(egui::text::CCursorRange::one(egui::text::CCursor::new(index))));
    egui::TextEdit::store_state(ctx, id, state);
}

/// Put the cursor at the end of the text.
fn cursor_to_end(ctx: &egui::Context, id: egui::Id, text: &str) {
    cursor_to(ctx, id, text.chars().count());
}

/// Send: an app-colour square once there's something to send, a quiet one before.
fn send_button(ui: &mut Ui, ready: bool) -> egui::Response {
    let t = Tokens::get(ui.ctx());
    let (rect, resp) = ui.allocate_exact_size(egui::Vec2::splat(32.0), egui::Sense::click());
    let fill = if ready { crate::theme::mix(t.accent, egui::Color32::BLACK, 0.12 * widgets::hover_t(ui, &resp)) } else { t.raised };
    ui.painter().rect_filled(rect, t.radius, fill);
    icons::paint(ui, rect, "send", 16.0, if ready { egui::Color32::WHITE } else { t.text_faint });
    widgets::focus_ring(ui, &resp, rect);
    resp.widget_info(|| egui::WidgetInfo::labeled(egui::WidgetType::Button, true, tr("Send (Enter)")));
    resp.on_hover_cursor(egui::CursorIcon::PointingHand).on_hover_text(tr("Send (Enter)"))
}

/// "2 pictures attached" for the feed, or nothing.
pub fn attached_line(n: usize) -> String {
    match n {
        0 => String::new(),
        1 => tr("(1 picture attached)"),
        n => trf("({n} pictures attached)", &[("n", &n.to_string())]),
    }
}

/// A sent message as it was typed: what the feed shows, without its [`attached_line`].
pub fn as_typed(shown: &str) -> &str {
    let Some((text, last)) = shown.rsplit_once('\n') else { return shown };
    let n: Option<usize> = last.chars().filter(char::is_ascii_digit).collect::<String>().parse().ok();
    if n.is_some_and(|n| attached_line(n) == last) { text } else { shown }
}

/// The text the agent gets: the message, then where its pictures are so it opens them.
pub fn with_attachments(text: &str, files: &[PathBuf], root: &std::path::Path) -> String {
    if files.is_empty() {
        return text.to_string();
    }
    let list = files.iter().map(|p| p.strip_prefix(root).unwrap_or(p).display().to_string().replace('\\', "/")).collect::<Vec<_>>().join(", ");
    format!("{text}\n\nAttached pictures: {list}. Open each one with the Read tool; they show what the person means.")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn up_goes_back_through_prompts_and_down_returns_to_what_was_being_typed() {
        let list = ["one".to_string(), "two".to_string()];
        let first = older(&list, None, "half a thou").unwrap();
        assert_eq!((first.shown.as_str(), first.draft.as_str()), ("two", "half a thou"));
        let second = older(&list, Some(&first), &first.shown).unwrap();
        assert_eq!((second.shown.as_str(), second.draft.as_str()), ("one", "half a thou"));
        assert_eq!(older(&list, Some(&second), &second.shown), None, "the oldest stays");
        assert_eq!(newer(&list, &second).unwrap().shown, "two");
        assert_eq!(newer(&list, &first), Err("half a thou".to_string()));
        assert_eq!(older(&[], None, ""), None);
    }

    #[test]
    fn a_prompt_comes_back_without_its_pictures_line() {
        assert_eq!(as_typed("Add tags\n(2 pictures attached)"), "Add tags");
        assert_eq!(as_typed("Add tags\n(1 picture attached)"), "Add tags");
        assert_eq!(as_typed("First\nsecond line"), "First\nsecond line");
        assert_eq!(as_typed("Use 3\ncolours"), "Use 3\ncolours");
    }
}
