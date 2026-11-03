//! Context management for long agent conversations (R2.1): old tool results are trimmed, then the
//! oldest part is replaced by a summary when the conversation still doesn't fit, and the whole
//! conversation can be kept on disk (`transcript.json`) so a later message resumes it.
//!
//! Every edit keeps the shape providers require: the first message is the person's, each tool call
//! keeps its result, and the most recent messages are never touched.

use crate::model::{Block, Msg, Speaker};
use craft_anything_evidence::ToolError;
use serde::{Deserialize, Serialize};
use std::path::Path;

/// Messages at the end that trimming leaves alone (the current step and a few before it).
pub const KEEP_RECENT: usize = 12;
/// A trimmed tool result keeps this many characters.
const TRIMMED_KEEP: usize = 400;
/// What a cloud model's conversation may grow to (input tokens) before it is trimmed.
pub const CLOUD_CONTEXT_TOKENS: u64 = 150_000;
/// The same for a local model, whose context is usually small.
pub const LOCAL_CONTEXT_TOKENS: u64 = 24_000;
/// The version of `transcript.json`.
pub const TRANSCRIPT_VERSION: u32 = 1;

/// What the model is asked when the oldest part of a conversation is replaced.
pub const SUMMARY_REQUEST: &str = "The conversation is getting too long to continue. Write a summary of the work so far that you can carry on from without the earlier messages: the task, what has been done (files made or changed, commands that worked), decisions and the reasons for them, what is left to do, and anything the person asked for. Be specific and complete; leave out pleasantries. Don't call any tools.";

/// About how many tokens a conversation takes (4 characters a token), for when no turn has
/// reported its real size yet.
pub fn estimate_tokens(history: &[Msg]) -> u64 {
    let chars: usize = history
        .iter()
        .flat_map(|m| &m.blocks)
        .map(|b| match b {
            Block::Text { text } => text.len(),
            Block::Thinking { thinking, .. } => thinking.len(),
            Block::RedactedThinking { data } => data.len(),
            Block::ToolUse { input, name, .. } => name.len() + input.to_string().len(),
            Block::ToolResult { content, .. } => content.len(),
        })
        .sum();
    (chars / 4) as u64
}

/// Shorten tool results and drop reasoning in all but the last [`KEEP_RECENT`] messages. Returns
/// how many blocks changed.
pub fn trim_old(history: &mut [Msg]) -> usize {
    let end = history.len().saturating_sub(KEEP_RECENT);
    let mut changed = 0;
    for m in history.iter_mut().take(end) {
        let before = m.blocks.len();
        // Earlier turns' reasoning isn't needed again (providers ignore it outside the current step).
        m.blocks.retain(|b| !matches!(b, Block::Thinking { .. } | Block::RedactedThinking { .. }));
        changed += before - m.blocks.len();
        for b in &mut m.blocks {
            if let Block::ToolResult { content, .. } = b
                && content.len() > TRIMMED_KEEP + 100
                && !content.ends_with(TRIMMED_NOTE)
            {
                let mut cut = TRIMMED_KEEP;
                while !content.is_char_boundary(cut) {
                    cut -= 1;
                }
                content.truncate(cut);
                content.push_str(TRIMMED_NOTE);
                changed += 1;
            }
        }
    }
    changed
}

const TRIMMED_NOTE: &str = "… (trimmed to save room; run the tool again if you need the rest)";

/// Where to split a conversation so the part before it can be summarised: an assistant message
/// with about the last third after it. `None` when fewer than three messages would be summarised
/// (one is usually the previous summary, so there's nothing to gain).
pub fn cut_point(history: &[Msg]) -> Option<usize> {
    let start = history.len().saturating_sub(history.len() / 3).max(1);
    (MIN_SUMMARISED..=start.min(history.len().saturating_sub(2))).rev().find(|&i| history[i].role == Speaker::Assistant)
}

/// Fewest messages worth replacing by a summary.
const MIN_SUMMARISED: usize = 3;

/// The conversation with everything before `cut` replaced by `summary`.
pub fn summarised(history: &[Msg], cut: usize, summary: &str) -> Vec<Msg> {
    let mut out =
        vec![Msg::user_text(format!("(Earlier messages were replaced by this summary to save room.)\n\n{}\n\nContinue the task from here.", summary.trim()))];
    out.extend(history.iter().skip(cut).cloned());
    out
}

/// The conversation plus the summary request, appended to the last message when that is the
/// person's (two in a row aren't allowed everywhere).
pub fn with_summary_request(history: &[Msg]) -> Vec<Msg> {
    let mut v = history.to_vec();
    match v.last_mut() {
        Some(m) if m.role == Speaker::User => m.blocks.push(Block::Text { text: SUMMARY_REQUEST.into() }),
        _ => v.push(Msg::user_text(SUMMARY_REQUEST)),
    }
    v
}

/// Add the person's text: appended to the last message when that is already theirs (a resumed
/// conversation can end with tool results).
pub fn push_user_text(history: &mut Vec<Msg>, text: &str) {
    match history.last_mut() {
        Some(m) if m.role == Speaker::User => m.blocks.push(Block::Text { text: text.into() }),
        _ => history.push(Msg::user_text(text)),
    }
}

#[derive(Serialize, Deserialize)]
struct Transcript {
    version: u32,
    history: Vec<Msg>,
}

/// Write the conversation to `path`.
pub fn save(path: &Path, history: &[Msg]) -> Result<(), ToolError> {
    let text = serde_json::to_vec(&Transcript { version: TRANSCRIPT_VERSION, history: history.to_vec() })
        .map_err(|e| ToolError::internal(format!("couldn't write the transcript: {e}")))?;
    craft_anything_engine::project::write_atomic(path, &text)
}

/// A saved conversation, ready to continue: `None` when there is none, it's unreadable or from a
/// newer version. An unfinished step at the end (tool calls without results) is dropped.
pub fn load(path: &Path) -> Option<Vec<Msg>> {
    let t: Transcript = serde_json::from_slice(&std::fs::read(path).ok()?).ok()?;
    if t.version > TRANSCRIPT_VERSION {
        return None;
    }
    let mut h = t.history;
    while h.last().is_some_and(|m| m.role == Speaker::Assistant && !m.tool_uses().is_empty()) {
        h.pop();
    }
    if h.first().is_none_or(|m| m.role != Speaker::User) {
        return None;
    }
    Some(h)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn step(i: usize, result: &str) -> [Msg; 2] {
        let id = format!("t{i}");
        [
            Msg {
                role: Speaker::Assistant,
                blocks: vec![
                    Block::Thinking { thinking: "hmm".into(), signature: "s".into() },
                    Block::ToolUse { id: id.clone(), name: "build_file_read".into(), input: json!({"path": "a"}) },
                ],
            },
            Msg { role: Speaker::User, blocks: vec![Block::ToolResult { tool_use_id: id, content: result.into(), is_error: false }] },
        ]
    }

    fn convo(steps: usize) -> Vec<Msg> {
        let mut h = vec![Msg::user_text("Build it")];
        for i in 0..steps {
            h.extend(step(i, &"x".repeat(5000)));
        }
        h
    }

    /// Every tool call has its result right after it, and the first message is the person's.
    fn well_formed(h: &[Msg]) -> bool {
        h.first().is_some_and(|m| m.role == Speaker::User)
            && h.iter().enumerate().all(|(i, m)| {
                m.tool_uses().iter().all(|(id, _, _)| {
                    h.get(i + 1).is_some_and(|n| n.blocks.iter().any(|b| matches!(b, Block::ToolResult { tool_use_id, .. } if tool_use_id == id)))
                })
            })
    }

    #[test]
    fn trimming_keeps_recent_messages_and_every_pair() {
        let mut h = convo(20);
        let before = estimate_tokens(&h);
        assert!(trim_old(&mut h) > 0);
        assert!(estimate_tokens(&h) < before / 2, "much smaller");
        assert!(well_formed(&h));
        let recent = &h[h.len() - KEEP_RECENT..];
        assert!(recent.iter().any(|m| m.blocks.iter().any(|b| matches!(b, Block::Thinking { .. }))), "recent reasoning stays");
        assert!(recent.iter().all(|m| m.blocks.iter().all(|b| !matches!(b, Block::ToolResult { content, .. } if content.len() < 5000))));
        assert_eq!(trim_old(&mut h), 0, "trimming twice changes nothing");
    }

    #[test]
    fn a_summary_replaces_the_oldest_part() {
        let h = convo(9);
        let cut = cut_point(&h).unwrap();
        assert_eq!(h[cut].role, Speaker::Assistant);
        let s = summarised(&h, cut, "Made index.html.");
        assert!(s.len() < h.len() && s[0].text().contains("Made index.html.") && well_formed(&s));
        assert!(cut_point(&[Msg::user_text("hi")]).is_none());
        assert!(cut_point(&convo(1)).is_none(), "too little to summarise");
        assert!(cut_point(&s).is_none_or(|c| c >= 3), "a summary isn't summarised again on its own");
        // The request joins the last message when that is the person's.
        let r = with_summary_request(&h);
        assert_eq!(r.len(), h.len());
        assert!(r.last().unwrap().text().contains("summary"));
    }

    #[test]
    fn transcripts_resume_without_an_unfinished_step() {
        let d = tempfile::tempdir().unwrap();
        let p = d.path().join("transcript.json");
        assert!(load(&p).is_none());
        let mut h = convo(2);
        h.push(step(9, "")[0].clone());
        save(&p, &h).unwrap();
        let back = load(&p).unwrap();
        assert_eq!(back.len(), h.len() - 1, "the call without a result is dropped");
        assert!(well_formed(&back));
        let mut back = back;
        push_user_text(&mut back, "Make it blue");
        assert_eq!(back.len(), h.len() - 1, "joined to the last tool results");
        std::fs::write(&p, r#"{"version":99,"history":[]}"#).unwrap();
        assert!(load(&p).is_none(), "a newer version is left alone");
    }
}
