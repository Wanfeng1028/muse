//! The inbox: how an agent working on a project asks the person something — a question with
//! choices, or approval for an action — and waits for the answer the app writes back.
//!
//! It is a folder, so it works across processes (the app, our MCP server started by a coding
//! agent, the in-process agent loop): `<id>.request.json` is written by the asker and
//! `<id>.answer.json` by the app. Both are written atomically; the asker removes both once it has
//! read the answer. Ids are generated here and validated on every path join.

use crate::project::write_atomic;
use craft_anything_evidence::ToolError;
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

/// The session's inbox folder (kept in `Session::ext`). Set by `mcp --inbox <dir>` or by the
/// workflow that runs the in-process agent.
#[derive(Debug, Clone)]
pub struct InboxDir(pub PathBuf);

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum RequestKind {
    /// A question; the answer is a choice and/or free text.
    Question,
    /// Permission for an action; the answer is allow/deny.
    Approval,
}

/// Something waiting for the person.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Request {
    pub id: String,
    pub kind: RequestKind,
    /// The question, or a one-line description of the action ("Run `npm install`").
    pub title: String,
    /// Optional context in plain words.
    #[serde(default)]
    pub detail: String,
    /// Suggested answers, shown as buttons.
    #[serde(default)]
    pub choices: Vec<String>,
    /// Whether a typed answer is accepted too.
    #[serde(default)]
    pub allow_text: bool,
    /// For approvals: the action's kind, so "always allow" can be remembered per kind.
    #[serde(default)]
    pub action: Option<String>,
    pub created_ms: u64,
}

/// The person's answer.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Answer {
    #[serde(default)]
    pub choice: Option<String>,
    #[serde(default)]
    pub text: Option<String>,
    /// Approvals: true to allow.
    #[serde(default)]
    pub allow: Option<bool>,
    /// Approvals: allow this kind of action for the rest of the project.
    #[serde(default)]
    pub always: bool,
}

impl Answer {
    /// The answer as one line of text for an agent.
    pub fn as_text(&self) -> String {
        match (&self.choice, self.text.as_deref().map(str::trim).filter(|t| !t.is_empty())) {
            (Some(c), Some(t)) => format!("{c} — {t}"),
            (Some(c), None) => c.clone(),
            (None, Some(t)) => t.to_string(),
            (None, None) => String::new(),
        }
    }
}

#[derive(Debug, Clone)]
pub struct Inbox {
    dir: PathBuf,
}

static COUNTER: AtomicU64 = AtomicU64::new(0);

pub fn now_ms() -> u64 {
    SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_millis() as u64).unwrap_or(0)
}

/// Ids are `[0-9a-z-]` only, so they are always safe as file names.
fn valid_id(id: &str) -> bool {
    !id.is_empty() && id.len() <= 64 && id.bytes().all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'-')
}

impl Inbox {
    pub fn new(dir: impl Into<PathBuf>) -> Inbox {
        Inbox { dir: dir.into() }
    }

    pub fn dir(&self) -> &Path {
        &self.dir
    }

    fn path(&self, id: &str, suffix: &str) -> Result<PathBuf, ToolError> {
        if !valid_id(id) {
            return Err(ToolError::invalid(format!("{id:?} is not an inbox id")));
        }
        Ok(self.dir.join(format!("{id}.{suffix}.json")))
    }

    /// Post a request; returns its id.
    pub fn post(
        &self,
        kind: RequestKind,
        title: &str,
        detail: &str,
        choices: Vec<String>,
        allow_text: bool,
        action: Option<String>,
    ) -> Result<String, ToolError> {
        std::fs::create_dir_all(&self.dir).map_err(|e| ToolError::io(self.dir.display(), e))?;
        let n = COUNTER.fetch_add(1, Ordering::SeqCst);
        let id = format!("{}-{}-{n}", now_ms(), std::process::id());
        let req = Request { id: id.clone(), kind, title: title.to_string(), detail: detail.to_string(), choices, allow_text, action, created_ms: now_ms() };
        let bytes = serde_json::to_vec_pretty(&req).map_err(|e| ToolError::internal(e.to_string()))?;
        write_atomic(&self.path(&id, "request")?, &bytes)?;
        Ok(id)
    }

    /// Requests without an answer yet, oldest first. Unreadable files are skipped.
    pub fn pending(&self) -> Vec<Request> {
        let Ok(rd) = std::fs::read_dir(&self.dir) else { return Vec::new() };
        let mut out: Vec<Request> = rd
            .flatten()
            .filter_map(|e| e.file_name().to_str().and_then(|n| n.strip_suffix(".request.json")).map(str::to_string))
            .filter(|id| valid_id(id) && !self.dir.join(format!("{id}.answer.json")).exists())
            .filter_map(|id| std::fs::read(self.dir.join(format!("{id}.request.json"))).ok())
            .filter_map(|b| serde_json::from_slice::<Request>(&b).ok())
            .collect();
        out.sort_by_key(|r| r.created_ms);
        out
    }

    /// Write the person's answer.
    pub fn answer(&self, id: &str, answer: &Answer) -> Result<(), ToolError> {
        let bytes = serde_json::to_vec(answer).map_err(|e| ToolError::internal(e.to_string()))?;
        write_atomic(&self.path(id, "answer")?, &bytes)
    }

    /// Wait for the answer to `id` (polling), until `timeout` or `cancelled()`. The request and
    /// answer files are removed once read; on timeout or cancel the request is withdrawn.
    pub fn wait(&self, id: &str, timeout: Duration, cancelled: &dyn Fn() -> bool) -> Option<Answer> {
        let (req, ans) = (self.path(id, "request").ok()?, self.path(id, "answer").ok()?);
        let start = Instant::now();
        loop {
            if let Ok(bytes) = std::fs::read(&ans)
                && let Ok(a) = serde_json::from_slice::<Answer>(&bytes)
            {
                let _ = std::fs::remove_file(&ans);
                let _ = std::fs::remove_file(&req);
                return Some(a);
            }
            if cancelled() || start.elapsed() >= timeout {
                let _ = std::fs::remove_file(&req);
                return None;
            }
            std::thread::sleep(Duration::from_millis(200));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn question_round_trip_across_handles() {
        let dir = tempfile::tempdir().unwrap();
        let asker = Inbox::new(dir.path().join("inbox"));
        let app = Inbox::new(dir.path().join("inbox"));
        let id = asker.post(RequestKind::Question, "Which colour?", "", vec!["Blue".into(), "Red".into()], true, None).unwrap();
        let pending = app.pending();
        assert_eq!(pending.len(), 1);
        assert_eq!(pending[0].choices, vec!["Blue", "Red"]);
        app.answer(&id, &Answer { choice: Some("Red".into()), text: Some(" darker ".into()), ..Default::default() }).unwrap();
        assert!(app.pending().is_empty(), "answered requests are no longer pending");
        let a = asker.wait(&id, Duration::from_secs(2), &|| false).unwrap();
        assert_eq!(a.as_text(), "Red — darker");
        assert_eq!(std::fs::read_dir(dir.path().join("inbox")).unwrap().count(), 0, "both files are cleaned up");
    }

    #[test]
    fn timeout_withdraws_and_bad_ids_are_refused() {
        let dir = tempfile::tempdir().unwrap();
        let inbox = Inbox::new(dir.path());
        let id = inbox.post(RequestKind::Approval, "Run npm install", "", vec![], false, Some("bash".into())).unwrap();
        assert!(inbox.wait(&id, Duration::from_millis(50), &|| false).is_none());
        assert!(inbox.pending().is_empty());
        assert!(inbox.answer("../escape", &Answer::default()).is_err());
        assert!(inbox.answer("A", &Answer::default()).is_err());
    }
}
