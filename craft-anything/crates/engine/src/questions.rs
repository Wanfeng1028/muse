//! Questions asked about a project's build and their answers, kept in the project folder
//! (`questions.json`) to read again later. They stay apart from `feed.json`: they aren't part of
//! the build's conversation, and a run owns that file. `rebuild_question_ask` is what writes here.

use crate::inbox::now_ms;
use crate::workspace::Workspace;
use craft_anything_evidence::ToolError;
use craft_anything_platform::sync::Mutex;
use serde::{Deserialize, Serialize};
use std::sync::PoisonError;

/// Where they're kept in the project folder.
pub const QUESTIONS_FILE: &str = "questions.json";
/// The format written today.
pub const QUESTIONS_VERSION: u32 = 1;
/// How many a project keeps; the oldest go first.
const KEPT: usize = 200;

/// One question and its answer.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct AskedQuestion {
    pub question: String,
    pub answer: String,
    /// From a copy of the builder's own session (it remembers the build).
    pub from_session: bool,
    pub backend: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub cost_usd: Option<f64>,
    /// How many items the project's feed held when it was asked: where it shows in the conversation.
    pub after: usize,
    pub at_ms: u64,
}

impl AskedQuestion {
    pub fn new(question: String, answer: String, from_session: bool, backend: String, cost_usd: Option<f64>, after: usize) -> Self {
        Self { question, answer, from_session, backend, cost_usd, after, at_ms: now_ms() }
    }
}

#[derive(Serialize, Deserialize)]
struct File {
    #[serde(default)]
    version: u32,
    items: Vec<AskedQuestion>,
}

/// A project's questions, oldest first; none when there are none or the file can't be read.
pub fn load(ws: &Workspace) -> Vec<AskedQuestion> {
    let Ok(bytes) = std::fs::read(ws.root.join(QUESTIONS_FILE)) else { return Vec::new() };
    match serde_json::from_slice::<File>(&bytes) {
        Ok(f) => f.items,
        Err(e) => {
            log::warn!("the questions of {} couldn't be read: {e}", ws.root.display());
            Vec::new()
        }
    }
}

/// Keep one more. Questions can finish at once, so each read and write happens alone.
pub fn add(ws: &Workspace, asked: AskedQuestion) -> Result<(), ToolError> {
    static WRITING: Mutex<()> = Mutex::new(());
    let _alone = WRITING.lock().unwrap_or_else(PoisonError::into_inner);
    let mut items = load(ws);
    items.push(asked);
    let extra = items.len().saturating_sub(KEPT);
    items.drain(..extra);
    let json = serde_json::to_vec_pretty(&File { version: QUESTIONS_VERSION, items }).map_err(|e| ToolError::internal(e.to_string()))?;
    crate::project::write_atomic(&ws.root.join(QUESTIONS_FILE), &json)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::workspace::TargetRef;

    fn asked(q: &str, after: usize) -> AskedQuestion {
        AskedQuestion::new(q.into(), "in src".into(), true, "Claude".into(), None, after)
    }

    #[test]
    fn questions_are_kept_in_order_and_the_oldest_go_first() {
        let d = tempfile::tempdir().unwrap();
        let ws = Workspace::create(d.path(), "Snake", "a snake game", TargetRef::None).unwrap();
        assert!(load(&ws).is_empty());
        for n in 0..KEPT + 2 {
            add(&ws, asked(&format!("q{n}"), n)).unwrap();
        }
        let items = load(&ws);
        assert_eq!((items.len(), items[0].question.as_str(), items[KEPT - 1].after), (KEPT, "q2", KEPT + 1));
    }

    #[test]
    fn an_unreadable_file_is_no_questions_and_they_go_with_the_project() {
        let d = tempfile::tempdir().unwrap();
        let ws = Workspace::create(d.path(), "Snake", "a snake game", TargetRef::None).unwrap();
        std::fs::write(ws.root.join(QUESTIONS_FILE), "{").unwrap();
        assert!(load(&ws).is_empty());
        add(&ws, asked("where", 0)).unwrap();
        assert_eq!(load(&ws).len(), 1);
        let root = ws.root.clone();
        ws.delete().unwrap();
        assert!(!root.join(QUESTIONS_FILE).exists());
    }
}
