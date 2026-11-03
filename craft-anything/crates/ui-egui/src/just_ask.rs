//! "Just ask": questions about a project's build from its prompt box ("where are the latest
//! files?"), answered without starting a build or a round and without changing anything
//! (`rebuild_question_ask`). The switch under the box picks it, or a message starting with `/btw`.
//! Answers show in the conversation, where they were asked, each folding away to one line; they're
//! kept in the project (`engine::questions`).

use crate::i18n::{tr, trf};
use crate::slash::{self, Command, Typed};
use crate::state::FeedItem;
use crate::theme::{self, Tokens};
use crate::{CraftApp, chat, icons, prompt_box, widgets};
use craft_anything_engine::evidence::ToolError;
use craft_anything_engine::questions::{self, AskedQuestion};
use craft_anything_engine::workspace::Workspace;
use egui::{RichText, Ui};
use serde_json::{Value, json};
use std::path::{Path, PathBuf};

/// A question and, once it's come, its answer (or why there isn't one).
#[derive(Debug, Clone, PartialEq)]
pub struct Asked {
    pub question: String,
    pub answer: Option<Result<Answer, String>>,
    /// How many feed items came before it: where it shows in the conversation.
    pub after: usize,
    /// Folded to one line.
    pub collapsed: bool,
    /// Scroll to it on the next frame: it was just asked, or its answer just came.
    reveal: bool,
}

impl From<AskedQuestion> for Asked {
    /// One kept from before, folded away.
    fn from(a: AskedQuestion) -> Self {
        let answer = Answer { text: a.answer, from_session: a.from_session, backend: a.backend, cost_usd: a.cost_usd };
        Asked { question: a.question, answer: Some(Ok(answer)), after: a.after, collapsed: true, reveal: false }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct Answer {
    pub text: String,
    /// From a copy of the builder's own session (it remembers the build).
    pub from_session: bool,
    pub backend: String,
    pub cost_usd: Option<f64>,
}

/// The question in `text` when it's one: the switch is on "Just ask", or it starts with `/btw`.
/// An error says why it shouldn't be sent as it is.
pub fn question_in(text: &str, just_ask: bool) -> Result<Option<String>, String> {
    match slash::read(text) {
        Typed::Command(Command::Btw, "") => Err(tr("Type your question after /btw.")),
        Typed::Command(Command::Btw, question) => Ok(Some(question.to_string())),
        Typed::Unknown(name) => Err(trf("There's no /{name} command. You can use {commands}.", &[("name", name), ("commands", &slash::names())])),
        Typed::Message => Ok(Some(text.trim()).filter(|t| just_ask && !t.is_empty()).map(str::to_string)),
    }
}

/// Everything sent in a project, oldest first: its messages as they were typed, and its questions
/// where they were asked, as `/btw` so they stay questions when sent again.
pub fn prompts(feed: &[FeedItem], asked: &[Asked]) -> Vec<String> {
    let mut out = Vec::new();
    let mut asked = asked.iter().peekable();
    for (i, item) in feed.iter().enumerate() {
        while let Some(a) = asked.next_if(|a| a.after <= i) {
            out.push(format!("/btw {}", a.question));
        }
        if let FeedItem::User(shown) = item {
            out.push(prompt_box::as_typed(shown).to_string());
        }
    }
    out.extend(asked.map(|a| format!("/btw {}", a.question)));
    out
}

impl CraftApp {
    /// Read a project's kept questions, the first time it's opened.
    pub(crate) fn load_asked(&mut self, ws: &Workspace) {
        self.asked.entry(ws.root.clone()).or_insert_with(|| questions::load(ws).into_iter().map(Asked::from).collect());
    }

    /// Ask about the open project's build; the answer comes back in the conversation.
    pub fn ask_about_build(&mut self, question: String) {
        let Some(ws) = self.workspace.clone() else { return };
        self.load_asked(&ws);
        let root = ws.root;
        let after = self.state.feed.len();
        self.asked.entry(root.clone()).or_default().push(Asked { question: question.clone(), answer: None, after, collapsed: false, reveal: true });
        self.act("rebuild_question_ask", json!({"project": root, "question": question}), tr("Ask about the build"));
    }

    /// A question's answer came (or it failed).
    pub(crate) fn question_done(&mut self, result: Result<Value, ToolError>) {
        match result {
            Ok(v) => {
                let (Some(root), Some(q)) = (v["project"].as_str().map(PathBuf::from), v["question"].as_str()) else { return };
                let a = &v["answered"];
                let answer = Answer {
                    text: a["answer"].as_str().unwrap_or_default().to_string(),
                    from_session: a["from"].as_str() == Some("builders_session"),
                    backend: a["backend"].as_str().unwrap_or_default().to_string(),
                    cost_usd: a["cost_usd"].as_f64(),
                };
                if let Some(slot) = self.waiting_question(&root, Some(q)) {
                    slot.answer = Some(Ok(answer));
                    slot.reveal = true;
                }
                if let Some(why) = v["not_kept"].as_str() {
                    self.toast(format!("{} {why}", tr("This answer won't be there after a restart:")), true);
                }
            }
            // The error doesn't say which question it was for: the oldest one still waiting.
            Err(e) => {
                let why = e.for_people();
                let roots: Vec<PathBuf> = self.asked.keys().cloned().collect();
                if let Some(slot) = roots.iter().find_map(|r| self.asked.get(r).and_then(|l| l.iter().position(|a| a.answer.is_none())).map(|i| (r.clone(), i)))
                    && let Some(a) = self.asked.get_mut(&slot.0).and_then(|l| l.get_mut(slot.1))
                {
                    a.answer = Some(Err(why));
                    a.reveal = true;
                } else {
                    self.toast(why, true);
                }
            }
        }
    }

    fn waiting_question(&mut self, root: &Path, question: Option<&str>) -> Option<&mut Asked> {
        self.asked.get_mut(root)?.iter_mut().find(|a| a.answer.is_none() && question.is_none_or(|q| a.question == q))
    }
}

/// One question in the conversation: a line that folds its answer away. A long answer is read by
/// scrolling the conversation, so it never pushes the prompt box off the screen.
pub fn card(ui: &mut Ui, a: &mut Asked, glossary: bool) {
    let t = Tokens::get(ui.ctx());
    let shown = widgets::card(&t).show(ui, |ui| {
        ui.set_width(ui.available_width());
        let mut toggle = false;
        ui.horizontal(|ui| {
            let name = if a.collapsed { "Show the answer" } else { "Hide the answer" };
            toggle |= icons::button(ui, if a.collapsed { "chevron-right" } else { "chevron-down" }, 22.0, false, name).clicked();
            let (icon, _) = ui.allocate_exact_size(egui::vec2(16.0, 16.0), egui::Sense::hover());
            icons::paint(ui, icon, "circle-help", 16.0, t.icon);
            let line = egui::Label::new(RichText::new(&a.question).strong()).sense(egui::Sense::click()).selectable(false);
            let line = if a.collapsed { line.truncate() } else { line.wrap() };
            toggle |= ui.add(line).on_hover_cursor(egui::CursorIcon::PointingHand).clicked();
        });
        if toggle {
            a.collapsed = !a.collapsed;
        }
        if a.collapsed {
            return;
        }
        ui.add_space(4.0);
        match &a.answer {
            None => widgets::thinking(ui),
            Some(Ok(ans)) => {
                chat::rich_text(ui, &ans.text, glossary);
                ui.add_space(4.0);
                let from = if ans.from_session { tr("from the builder's own memory of the build") } else { tr("from the project's files") };
                let cost = ans.cost_usd.map(|c| format!(" · ${c:.2}")).unwrap_or_default();
                ui.label(
                    RichText::new(format!("{} {} · {}{cost}", tr("Just a question: nothing was changed. Answered by"), ans.backend, from))
                        .color(t.text_faint)
                        .size(theme::SMALL),
                );
            }
            Some(Err(why)) => {
                ui.add(egui::Label::new(RichText::new(format!("{} {why}", tr("Couldn't answer:"))).color(t.danger)).wrap());
            }
        }
    });
    if std::mem::take(&mut a.reveal) {
        // Its start, not the end of a long answer.
        ui.scroll_to_rect(shown.response.rect, Some(egui::Align::Min));
    }
    ui.add_space(chat::MESSAGE_GAP);
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn prompts_keep_questions_where_they_were_asked() {
        let asked = |q: &str, after| Asked { question: q.into(), answer: None, after, collapsed: false, reveal: false };
        let user = |t: &str| FeedItem::User(t.into());
        let feed = [user("A notes app"), FeedItem::Paused, user("Make it blue\n(1 picture attached)")];
        let list = [asked("why Rust", 1), asked("where are the files", 3)];
        assert_eq!(prompts(&feed, &list), ["A notes app", "/btw why Rust", "Make it blue", "/btw where are the files"]);
    }

    #[test]
    fn a_question_is_marked_by_the_switch_or_btw() {
        let question = |t: &str, just_ask| question_in(t, just_ask).unwrap();
        assert_eq!(question("/btw where are the files", false).as_deref(), Some("where are the files"));
        assert_eq!(question("where are the files", true).as_deref(), Some("where are the files"));
        assert_eq!(question("make it blue", false), None);
        assert_eq!(question("? is a plain message now", false), None);
        assert_eq!(question("  ", true), None);
        assert!(question_in("/btw", false).unwrap_err().contains("after /btw"));
        assert!(question_in("/bwt where", true).unwrap_err().contains("/bwt"), "a typo isn't sent, whatever the switch says");
    }
}
