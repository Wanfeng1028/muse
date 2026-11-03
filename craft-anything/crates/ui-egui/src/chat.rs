//! The conversation: turning agent events into chat items, and drawing them (Beginner Ask screen
//! and the Experienced agent console share the renderer).

use crate::i18n::tr;
use crate::state::{ChatItem, ConsentAnswer};
use crate::theme::{self, Tokens};
use crate::{CraftApp, evidence_ui, glossary, icons, widgets};
use craft_anything_ai::AgentEvent;
use craft_anything_engine::TargetKind;
use egui::{Margin, RichText, Ui, Vec2};
use serde_json::Value;

/// Fold one agent event into the conversation.
pub fn apply_event(chat: &mut Vec<ChatItem>, e: AgentEvent) {
    match e {
        AgentEvent::TextDelta { text } => {
            if let Some(ChatItem::Assistant { text: t, streaming: true, .. }) = chat.last_mut() {
                t.push_str(&text);
            } else {
                // Status lines from this turn are superseded once the answer starts.
                if matches!(chat.last(), Some(ChatItem::Status(_))) {
                    chat.pop();
                }
                chat.push(ChatItem::Assistant { text, backend: None, streaming: true });
            }
        }
        // For logs, not the conversation.
        AgentEvent::Output { .. } => {}
        AgentEvent::Status { text } => {
            if let Some(ChatItem::Status(s)) = chat.last_mut() {
                *s = text;
            } else {
                chat.push(ChatItem::Status(text));
            }
        }
        AgentEvent::ToolStarted { call_id, tool, .. } => {
            end_streaming(chat);
            chat.push(ChatItem::Tool { call_id, tool, ok: None, summary: String::new(), evidence_id: None, evidence: None });
        }
        AgentEvent::ToolFinished { call_id, tool, ok, summary, evidence_id } => {
            let found = chat.iter_mut().rev().find_map(|i| match i {
                ChatItem::Tool { call_id: c, ok: o, summary: s, evidence_id: e, .. } if *c == call_id => Some((o, s, e)),
                _ => None,
            });
            match found {
                Some((o, s, e)) => {
                    *o = Some(ok);
                    *s = summary;
                    *e = evidence_id;
                }
                None => chat.push(ChatItem::Tool { call_id, tool, ok: Some(ok), summary, evidence_id, evidence: None }),
            }
        }
        AgentEvent::ConsentNeeded { call_id, tool, title, explanation } => {
            end_streaming(chat);
            chat.push(ChatItem::Consent { call_id, tool, title, explanation, answer: None });
        }
        AgentEvent::TurnDone { backend, .. } => {
            if matches!(chat.last(), Some(ChatItem::Status(_))) {
                chat.pop();
            }
            for item in chat.iter_mut().rev() {
                if let ChatItem::Assistant { streaming, backend: b, .. } = item {
                    *streaming = false;
                    if b.is_none() {
                        *b = Some(backend.clone());
                    }
                    break;
                }
                if matches!(item, ChatItem::User(_)) {
                    break;
                }
            }
        }
        AgentEvent::Error { message, remediation, log } => {
            end_streaming(chat);
            if matches!(chat.last(), Some(ChatItem::Status(_))) {
                chat.pop();
            }
            chat.push(ChatItem::Error { message, remediation, log });
        }
    }
}

fn end_streaming(chat: &mut [ChatItem]) {
    if let Some(ChatItem::Assistant { streaming, .. }) = chat.last_mut() {
        *streaming = false;
    }
}

/// Plain-words rendering of a non-evidence tool result (status values).
pub fn describe_value(v: &Value) -> String {
    match v {
        Value::Object(m) => m
            .iter()
            .take(24)
            .map(|(k, v)| {
                let val = match v {
                    Value::String(s) => s.clone(),
                    Value::Null => "none".into(),
                    Value::Array(a) => crate::i18n::trf("{n} item(s)", &[("n", &a.len().to_string())]),
                    Value::Object(_) => "…".into(),
                    other => other.to_string(),
                };
                format!("- **{}**: {}", k.replace('_', " "), val)
            })
            .collect::<Vec<_>>()
            .join("\n"),
        other => other.to_string(),
    }
}

/// Questions to suggest for a kind of target.
pub fn suggestions(kind: Option<TargetKind>) -> Vec<&'static str> {
    use TargetKind::*;
    match kind {
        None => vec!["What can Craft Anything do?", "How do I open an app?", "Is it safe to look inside programs?"],
        Some(Elf | Pe | MachO | MachOFat | DosCom | RawBinary) => {
            vec!["What does this program do?", "What does it send over the internet?", "Is it safe to run?", "Which files does it read or write?"]
        }
        Some(Managed | Jar | JavaClass) => vec!["What does this program do?", "What are its main parts?", "Does it talk to the internet?"],
        Some(Sqlite) => vec!["What does this app store?", "What tables are in here?", "Is anything sensitive saved in plain text?"],
        Some(Apk | Dex) => vec!["What does this app do?", "What permissions does it ask for?", "Which servers does it talk to?", "Does it track me?"],
        Some(Asar | Script) => vec!["How is this app built?", "Which websites does it load?", "How do the window and the page talk to each other?"],
        Some(Wasm) => vec!["What does this module do?", "What does it need from the page?"],
        Some(Directory) => vec!["What's in this folder?", "Which file is the main program?", "How is this app put together?"],
        Some(Zip) => vec!["What's inside this archive?", "Is anything in here a program?"],
        Some(NetworkCapture) => vec!["Which servers were contacted?", "What data was sent?"],
        Some(Plist) => vec!["What settings are in here?"],
        Some(Evm) => vec!["What does this contract do?", "Who can move funds?"],
        Some(Unknown) => vec!["What kind of file is this?", "Is there any readable text inside?"],
    }
}

/// Beginner Ask screen: target card on the left, conversation in the centre.
pub fn ask_screen(app: &mut CraftApp, ui: &mut Ui) {
    let t = Tokens::get(ui.ctx());
    let side_w = 300.0_f32.min(ui.available_width() * 0.3);
    // What's open sits on the right; the app's sidebar is on the left.
    egui::Panel::right("ask-side").exact_size(side_w).resizable(false).frame(egui::Frame::new().fill(t.canvas).inner_margin(Margin::same(20))).show(ui, |ui| {
        target_card(app, ui);
    });
    egui::CentralPanel::default().frame(egui::Frame::new().fill(t.canvas).inner_margin(PANE_MARGIN)).show(ui, |ui| {
        conversation(app, ui, false);
    });
}

fn target_card(app: &mut CraftApp, ui: &mut Ui) {
    let t = Tokens::get(ui.ctx());
    widgets::card(&t).show(ui, |ui| {
        ui.set_width(ui.available_width());
        match app.view.active_target().cloned() {
            Some(target) => {
                ui.horizontal(|ui| {
                    let (rect, _) = ui.allocate_exact_size(Vec2::splat(48.0), egui::Sense::hover());
                    ui.painter().rect_filled(rect, t.radius, t.accent_soft);
                    icons::paint(ui, rect, crate::kind_icon(target.kind), 26.0, t.accent_ink);
                    ui.vertical(|ui| {
                        ui.add(egui::Label::new(theme::heading(&target.name, theme::CARD)).truncate());
                        ui.label(RichText::new(crate::human_bytes(target.bytes.len())).color(t.text_faint).size(theme::CAPTION));
                    });
                });
                ui.add_space(10.0);
                widgets::caption(ui, "What is it");
                ui.label(RichText::new(tr(target.kind.plain())).size(theme::BODY));
                ui.add_space(10.0);
                ui.horizontal_wrapped(|ui| {
                    if app.view.clean_room {
                        widgets::pill(ui, "Clean room", t.success, t.raised).on_hover_text(tr("Nothing inside it is read."));
                    } else {
                        widgets::pill(ui, "Deep", t.accent_ink, t.accent_soft);
                    }
                    widgets::pill(ui, &format!("{} {}", app.view.ledger_len, tr("findings")), t.text_dim, t.raised);
                });
            }
            None => {
                widgets::empty_state(ui, "folder-open", "Nothing open yet", "Drop a file or app anywhere in this window.");
                ui.vertical_centered(|ui| {
                    if widgets::primary_icon(ui, Some("folder-open"), "Open an app or file", true).clicked() {
                        app.pick(crate::Pick::OpenFile);
                    }
                });
            }
        }
    });
    ui.add_space(14.0);
    widgets::card(&t).show(ui, |ui| {
        ui.set_width(ui.available_width());
        widgets::caption(ui, "Try asking");
        ui.add_space(4.0);
        let kind = app.view.active_target().map(|t| t.kind);
        ui.spacing_mut().item_spacing.y = 6.0;
        ui.with_layout(egui::Layout::top_down_justified(egui::Align::Min), |ui| {
            for q in suggestions(kind) {
                if widgets::suggestion(ui, q).clicked() {
                    app.send(&tr(q));
                }
            }
        });
    });
    ui.add_space(14.0);
    ui.horizontal(|ui| {
        widgets::toggle(ui, &mut app.state.explain_new, "Explain like I'm new")
            .on_hover_text(tr("Plain words, short sentences, and every technical word explained."));
    });
    ui.add_space(10.0);
    if widgets::secondary(ui, Some("download"), "Export a report").on_hover_text(tr("Everything found so far, as a Markdown file.")).clicked() {
        app.export_report();
    }
}

/// The chat panes' margins: a little more air under the prompt box than at the top.
pub const PANE_MARGIN: Margin = Margin { left: 12, right: 20, top: 12, bottom: 24 };
/// Between the last message and the prompt box.
pub const COMPOSER_GAP: f32 = 16.0;
/// Between messages (on top of the item spacing).
pub const MESSAGE_GAP: f32 = 6.0;

/// The conversation with its composer. `dense` = Experienced agent console.
pub fn conversation(app: &mut CraftApp, ui: &mut Ui, dense: bool) {
    let width = ui.available_width();
    let max_w = if dense { width } else { width.min(720.0) };
    let pad = ((width - max_w) / 2.0).max(0.0);
    // The history gets exactly what the composer leaves (its height is measured last frame), so
    // a panel never grows to fit us.
    let comp_id = ui.id().with(("composer-h", dense));
    let comp_h = ui.data(|d| d.get_temp::<f32>(comp_id)).unwrap_or(if dense { 48.0 } else { 70.0 });
    // The item spacing after the history counts too. Anything here that comes out taller than the
    // space given makes the agent console's panel grow by that much every frame, until it reaches
    // its maximum and the top of its tab strip is cut off.
    let rest = Vec2::new(width, (ui.available_height() - comp_h - COMPOSER_GAP - ui.spacing().item_spacing.y).max(40.0));
    ui.allocate_ui_with_layout(rest, egui::Layout::top_down(egui::Align::Min), |ui| {
        ui.set_min_height(rest.y);
        history(app, ui, dense, pad, max_w)
    });
    ui.add_space(COMPOSER_GAP);
    // Top-aligned: `horizontal` centres in its row, which put the box 12 points below the gap.
    let r = ui.horizontal_top(|ui| {
        ui.add_space(pad);
        composer(app, ui, max_w, dense);
    });
    remember_composer_height(ui, comp_id, comp_h, r.response.rect.height());
}

/// Keep the prompt box's height for the next frame's layout. When it changed (a line added or
/// removed, a note appeared), this frame was laid out with the old height, so it's thrown away
/// and laid out again before it's shown: otherwise the box and the feed jump while typing.
pub fn remember_composer_height(ui: &mut Ui, id: egui::Id, used: f32, measured: f32) {
    ui.data_mut(|d| d.insert_temp(id, measured));
    if (measured - used).abs() > 0.5 {
        ui.ctx().request_discard("the prompt box changed height");
    }
}

fn history(app: &mut CraftApp, ui: &mut Ui, dense: bool, pad: f32, max_w: f32) {
    egui::ScrollArea::vertical().auto_shrink([false, false]).stick_to_bottom(true).show(ui, |ui| {
        ui.horizontal(|ui| {
            ui.add_space(pad);
            ui.vertical(|ui| {
                ui.set_width(max_w);
                if app.state.chat.is_empty() {
                    greeting(app, ui, dense);
                }
                let mut actions = Vec::new();
                let beginner = app.beginner();
                let last_proof = app.state.chat.iter().rposition(|i| matches!(i, ChatItem::Proof { .. }));
                for (i, item) in app.state.chat.iter().enumerate() {
                    let open = !dense && Some(i) == last_proof;
                    ui.push_id(i, |ui| item_ui(ui, item, beginner, dense, open, &mut actions));
                    ui.add_space(if dense { 4.0 } else { MESSAGE_GAP });
                }
                // Only for this conversation: a build or a download elsewhere isn't an answer.
                if app.answering() && !matches!(app.state.chat.last(), Some(ChatItem::Assistant { streaming: true, .. })) {
                    if dense {
                        widgets::thinking(ui);
                    } else {
                        widgets::working(ui, "Working on your answer", None);
                    }
                }
                for a in actions {
                    match a {
                        ChatAction::Consent(id, ans) => app.answer_consent(&id, ans),
                        ChatAction::OpenLog(path) => app.open_log(&path),
                        ChatAction::AddBrain => {
                            app.state.settings_open = true;
                            app.state.settings_tab = crate::state::SettingsTab::Ai;
                            app.detect_backends();
                        }
                    }
                }
            });
        });
    });
}

fn greeting(app: &CraftApp, ui: &mut Ui, dense: bool) {
    let t = Tokens::get(ui.ctx());
    if dense {
        ui.label(RichText::new(tr("Ask the agent about this target. It cites evidence for every claim.")).color(t.text_faint));
        return;
    }
    ui.add_space(24.0);
    let name = app.view.active_target().map(|t| t.name.clone());
    let title = match &name {
        Some(n) => crate::i18n::trf("What would you like to know about {name}?", &[("name", n)]),
        None => tr("What would you like to find out?"),
    };
    ui.label(theme::heading(title, theme::TITLE));
    ui.add_space(4.0);
    let sub = if app.state.backend.is_some() {
        "Ask in your own words. Every answer shows how sure we are, and the proof."
    } else {
        "No AI brain is set up, so answers come straight from the built-in engines. Add one any time for plain-words explanations."
    };
    ui.label(RichText::new(tr(sub)).color(t.text_dim));
    ui.add_space(16.0);
}

fn composer(app: &mut CraftApp, ui: &mut Ui, width: f32, dense: bool) {
    let answering = app.answering();
    let hint = if dense { tr("Ask the agent…") } else { tr("Ask anything, e.g. \"What does this program do?\"") };
    ui.allocate_ui(Vec2::new(width, 0.0), |ui| {
        let history = || app.state.chat.iter().filter_map(|i| if let ChatItem::User(text) = i { Some(text.clone()) } else { None }).collect();
        let out = crate::prompt_box::show(
            ui,
            &mut app.state.input,
            &[],
            crate::prompt_box::PromptBox {
                name: "Ask a question",
                hint,
                rows: (1, if dense { 4 } else { 8 }),
                attach: None,
                stop_button: answering.then_some("Stop"),
                send: !answering,
                recall: false,
                history: Some(&history),
                font_size: if dense { 14.0 } else { 16.0 },
            },
        );
        if out.stop {
            app.stop();
        }
        // One answer at a time; what's typed meanwhile stays in the box.
        if out.send && !answering {
            let text = std::mem::take(&mut app.state.input);
            app.send(&text);
        }
    });
}

enum ChatAction {
    Consent(String, ConsentAnswer),
    AddBrain,
    OpenLog(std::path::PathBuf),
}

pub(crate) fn bubble(t: &Tokens, user: bool, dense: bool) -> egui::Frame {
    let fill = if user { t.accent_soft } else { t.card };
    let stroke = if user { egui::Stroke::NONE } else { egui::Stroke::new(1.0, t.card_border) };
    let m = if dense { Margin::symmetric(10, 6) } else { Margin::symmetric(16, 12) };
    egui::Frame::new().fill(fill).stroke(stroke).corner_radius(t.r_lg()).inner_margin(m)
}

/// The person's message on the right. Labels in a right-to-left row don't wrap by themselves,
/// so a long prompt would run off the side: wrap it inside the bubble.
pub(crate) fn user_bubble(ui: &mut Ui, text: &str, dense: bool) {
    let t = Tokens::get(ui.ctx());
    ui.with_layout(egui::Layout::right_to_left(egui::Align::Min), |ui| {
        bubble(&t, true, dense).show(ui, |ui| {
            ui.set_max_width(ui.available_width().min(560.0));
            // The bubble sits on the right; its lines still read from the left.
            ui.with_layout(egui::Layout::top_down(egui::Align::Min), |ui| {
                ui.add(egui::Label::new(RichText::new(text).color(t.text)).wrap());
            });
        });
    });
}

/// A one-line activity row (icon and text) that wraps instead of running off the side.
pub(crate) fn activity_row(ui: &mut Ui, text: RichText) {
    let t = Tokens::get(ui.ctx());
    ui.horizontal_top(|ui| {
        icons::show(ui, "activity", 14.0, t.accent);
        ui.add(egui::Label::new(text).wrap());
    });
}

fn item_ui(ui: &mut Ui, item: &ChatItem, beginner: bool, dense: bool, open: bool, actions: &mut Vec<ChatAction>) {
    let t = Tokens::get(ui.ctx());
    match item {
        ChatItem::User(text) => user_bubble(ui, text, dense),
        ChatItem::Assistant { text, backend, streaming } => {
            bubble(&t, false, dense).show(ui, |ui| {
                ui.set_width(ui.available_width());
                rich_text(ui, text, beginner && !dense);
                if *streaming {
                    widgets::thinking(ui);
                }
                if let Some(b) = backend {
                    ui.add_space(4.0);
                    ui.label(RichText::new(crate::i18n::trf("Answered by {name}", &[("name", b)])).color(t.text_faint).size(theme::CAPTION));
                }
            });
        }
        ChatItem::Status(text) => {
            activity_row(ui, RichText::new(text).italics().color(t.text_dim).size(theme::CAPTION));
        }
        ChatItem::Tool { tool, ok, summary, evidence, .. } => {
            ui.horizontal_wrapped(|ui| {
                let (icon, col) = match ok {
                    None => ("loader", t.text_faint),
                    Some(true) => ("check", t.success),
                    Some(false) => ("triangle-alert", t.danger),
                };
                egui::Frame::new().fill(t.raised).corner_radius(t.r_sm()).inner_margin(Margin::symmetric(10, 3)).show(ui, |ui| {
                    ui.horizontal(|ui| {
                        icons::show(ui, icon, 13.0, col);
                        ui.label(RichText::new(tool.replace('_', " ")).font(theme::mono(12.5)).color(t.text_dim));
                    });
                });
                if !summary.is_empty() {
                    ui.label(RichText::new(summary).color(t.text_dim).size(theme::CAPTION));
                }
            });
            if let Some(e) = evidence {
                ui.add_space(4.0);
                evidence_ui::proof_card(ui, e, dense, false);
            }
        }
        ChatItem::Proof { intro, evidence } => {
            if !intro.is_empty() {
                ui.label(RichText::new(intro).color(t.text_dim));
                ui.add_space(4.0);
            }
            evidence_ui::proof_card(ui, evidence, dense, open);
        }
        ChatItem::Consent { call_id, title, explanation, answer, .. } => {
            egui::Frame::new().fill(t.card).stroke(egui::Stroke::new(1.5, t.warning)).corner_radius(t.r_lg()).inner_margin(Margin::same(14)).show(ui, |ui| {
                ui.set_width(ui.available_width());
                ui.horizontal(|ui| {
                    icons::show(ui, "shield", 18.0, t.warning);
                    ui.label(RichText::new(crate::i18n::trf("May I run \"{title}\"?", &[("title", title)])).font(theme::semibold(theme::BODY)));
                });
                ui.label(RichText::new(explanation).color(t.text_dim));
                ui.label(
                    RichText::new(tr("This runs code from the target or changes a device. Nothing runs until you say so."))
                        .color(t.text_faint)
                        .size(theme::CAPTION),
                );
                ui.add_space(6.0);
                match answer {
                    None => {
                        ui.horizontal(|ui| {
                            if widgets::primary(ui, "Allow once").clicked() {
                                actions.push(ChatAction::Consent(call_id.clone(), ConsentAnswer::Once));
                            }
                            if widgets::secondary(ui, None, "Always for this project").clicked() {
                                actions.push(ChatAction::Consent(call_id.clone(), ConsentAnswer::AlwaysForProject));
                            }
                            if widgets::secondary(ui, None, "Don't allow").clicked() {
                                actions.push(ChatAction::Consent(call_id.clone(), ConsentAnswer::Deny));
                            }
                        });
                    }
                    Some(a) => {
                        let text = match a {
                            ConsentAnswer::Once => "Allowed once.",
                            ConsentAnswer::AlwaysForProject => "Allowed for this project.",
                            ConsentAnswer::Deny => "Not allowed.",
                        };
                        ui.label(RichText::new(tr(text)).color(t.text_faint));
                    }
                }
            });
        }
        ChatItem::Error { message, remediation, log } => {
            egui::Frame::new()
                .fill(t.card)
                .stroke(egui::Stroke::new(1.0, t.danger.gamma_multiply(0.6)))
                .corner_radius(t.r_lg())
                .inner_margin(Margin::same(12))
                .show(ui, |ui| {
                    ui.set_width(ui.available_width());
                    ui.horizontal(|ui| {
                        icons::show(ui, "triangle-alert", 16.0, t.danger);
                        ui.add(egui::Label::new(RichText::new(message).color(t.text)).wrap());
                    });
                    if let Some(r) = remediation {
                        ui.add(egui::Label::new(RichText::new(r).color(t.text_dim)).wrap());
                    }
                    if let Some(l) = log
                        && widgets::open_log_button(ui, l)
                    {
                        actions.push(ChatAction::OpenLog(l.clone()));
                    }
                });
        }
        ChatItem::AddBrain => {
            egui::Frame::new().fill(t.accent_soft).corner_radius(t.r_lg()).inner_margin(Margin::same(14)).show(ui, |ui| {
                ui.set_width(ui.available_width());
                ui.horizontal(|ui| {
                    icons::show(ui, "sparkles", 20.0, t.accent_ink);
                    ui.vertical(|ui| {
                        ui.label(RichText::new(tr("Want answers in plain words?")).font(theme::semibold(theme::BODY)));
                        ui.label(
                            RichText::new(tr("Add an AI brain and I'll read this evidence for you, answer follow-up questions and point at the proof."))
                                .color(t.text_dim),
                        );
                        ui.add_space(4.0);
                        if widgets::primary_icon(ui, Some("plus"), "Add a brain", true).clicked() {
                            actions.push(ChatAction::AddBrain);
                        }
                    });
                });
            });
        }
    }
}

/// Light Markdown (headings, bullets, code fences, **bold**) with glossary hovers when `glossary`.
pub fn rich_text(ui: &mut Ui, text: &str, with_glossary: bool) {
    let t = Tokens::get(ui.ctx());
    let body = ui.style().text_styles.get(&egui::TextStyle::Body).cloned().unwrap_or_else(|| egui::FontId::proportional(theme::SMALL));
    let mut in_code = false;
    let mut code = String::new();
    for line in text.lines() {
        if line.trim_start().starts_with("```") {
            if in_code {
                code_block(ui, &code, &t);
                code.clear();
            }
            in_code = !in_code;
            continue;
        }
        if in_code {
            code.push_str(line);
            code.push('\n');
            continue;
        }
        let trimmed = line.trim_start();
        if trimmed.is_empty() {
            ui.add_space(4.0);
            continue;
        }
        if let Some(h) = trimmed.strip_prefix("### ").or_else(|| trimmed.strip_prefix("## ")).or_else(|| trimmed.strip_prefix("# ")) {
            ui.label(RichText::new(h).font(theme::semibold(body.size + 2.0)));
            continue;
        }
        let (bullet, rest) = match trimmed.strip_prefix("- ").or_else(|| trimmed.strip_prefix("* ")) {
            Some(r) => (true, r),
            None => (false, trimmed),
        };
        ui.horizontal_wrapped(|ui| {
            ui.spacing_mut().item_spacing.x = 0.0;
            if bullet {
                ui.label(RichText::new("  •  ").color(t.accent));
            }
            inline(ui, rest, with_glossary, &body, &t);
        });
    }
    if in_code && !code.is_empty() {
        code_block(ui, &code, &t);
    }
}

fn inline(ui: &mut Ui, text: &str, with_glossary: bool, body: &egui::FontId, t: &Tokens) {
    // Split on ** and ` markers; alternate plain/bold and plain/code.
    let mut bold = false;
    for (bi, part) in text.split("**").enumerate() {
        if bi > 0 {
            bold = !bold;
        }
        for (ci, piece) in part.split('`').enumerate() {
            let code = ci % 2 == 1;
            if piece.is_empty() {
                continue;
            }
            if code {
                ui.label(RichText::new(piece).font(theme::mono(body.size - 1.0)).color(t.accent_ink).background_color(t.code_bg));
                continue;
            }
            let font = if bold { theme::semibold(body.size) } else { body.clone() };
            if with_glossary {
                for (run, meaning) in glossary::segments(piece) {
                    match meaning {
                        Some(m) => {
                            widgets::glossary_word(ui, &run, m, font.clone());
                        }
                        None => words(ui, &run, &font, t),
                    }
                }
            } else {
                words(ui, piece, &font, t);
            }
        }
    }
}

/// A run of text as one label: in a wrapping row egui starts it where the last one ended and
/// breaks it between words, so a paragraph isn't one widget per word.
fn words(ui: &mut Ui, text: &str, font: &egui::FontId, t: &Tokens) {
    if !text.is_empty() {
        ui.add(egui::Label::new(RichText::new(text).font(font.clone()).color(t.text)).wrap());
    }
}

fn code_block(ui: &mut Ui, code: &str, t: &Tokens) {
    egui::Frame::new().fill(t.code_bg).corner_radius(t.r()).inner_margin(Margin::same(10)).show(ui, |ui| {
        ui.set_width(ui.available_width());
        ui.label(RichText::new(code.trim_end()).font(theme::mono(12.5)).color(t.text));
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn events_fold_into_a_tidy_conversation() {
        let mut chat = vec![ChatItem::User("hi".into())];
        apply_event(&mut chat, AgentEvent::Status { text: "Looking…".into() });
        apply_event(&mut chat, AgentEvent::Status { text: "Still looking…".into() });
        assert_eq!(chat.len(), 2);
        apply_event(&mut chat, AgentEvent::TextDelta { text: "Hel".into() });
        apply_event(&mut chat, AgentEvent::TextDelta { text: "lo".into() });
        assert_eq!(chat.len(), 2, "status replaced by the answer");
        apply_event(&mut chat, AgentEvent::ToolStarted { call_id: "c1".into(), tool: "core_target_triage".into(), input: Value::Null });
        apply_event(
            &mut chat,
            AgentEvent::ToolFinished {
                call_id: "c1".into(),
                tool: "core_target_triage".into(),
                ok: true,
                summary: "done".into(),
                evidence_id: Some("ev".into()),
            },
        );
        apply_event(&mut chat, AgentEvent::ConsentNeeded { call_id: "c2".into(), tool: "run".into(), title: "Run it".into(), explanation: "runs".into() });
        apply_event(&mut chat, AgentEvent::TurnDone { backend: "Claude".into(), input_tokens: 1, output_tokens: 2, cost_usd: None, cost_is_estimate: false });
        match &chat[1] {
            ChatItem::Assistant { text, streaming, backend } => {
                assert_eq!(text, "Hello");
                assert!(!streaming);
                assert_eq!(backend.as_deref(), Some("Claude"));
            }
            other => panic!("{other:?}"),
        }
        assert!(matches!(&chat[2], ChatItem::Tool { ok: Some(true), evidence_id: Some(_), .. }));
        assert!(matches!(&chat[3], ChatItem::Consent { answer: None, .. }));
    }

    #[test]
    fn every_kind_has_suggestions() {
        for k in [TargetKind::Elf, TargetKind::Apk, TargetKind::Asar, TargetKind::Unknown, TargetKind::Directory] {
            assert!(suggestions(Some(k)).len() >= 2);
        }
        assert!(!suggestions(None).is_empty());
        assert!(describe_value(&serde_json::json!({"a_b": 1})).contains("a b"));
    }
}
