//! A readable Markdown report of the conversation and the evidence behind it.

use crate::TargetInfo;
use crate::state::{ChatItem, ConsentAnswer};
use craft_anything_engine::evidence::Evidence;
use std::fmt::Write as _;

fn evidence_md(out: &mut String, e: &Evidence) {
    let _ = writeln!(out, "> **{}** · {} · `{}`", e.confidence.plain_label(), e.operation, e.id);
    if !e.summary.is_empty() {
        let _ = writeln!(out, ">\n> {}", e.summary.replace('\n', "\n> "));
    }
    if !e.locations.is_empty() {
        let locs: Vec<String> = e.locations.iter().take(20).map(|l| format!("`{}`", l.value)).collect();
        let _ = writeln!(out, ">\n> Where: {}", locs.join(", "));
    }
    for l in &e.limitations {
        let _ = writeln!(out, ">\n> Limitation: {}", l.message);
    }
    let _ = writeln!(out, ">\n> Engine: {}{}", e.environment.engine, if e.environment.clean_room { " (clean room)" } else { "" });
    out.push('\n');
}

/// Build the report.
pub fn markdown(chat: &[ChatItem], target: Option<&TargetInfo>, clean_room: bool) -> String {
    let mut out = String::new();
    let title = target.map(|t| t.name.as_str()).unwrap_or("Investigation");
    let _ = writeln!(out, "# {title}\n");
    if let Some(t) = target {
        let _ = writeln!(out, "- **What it is:** {}", t.kind.plain());
        let _ = writeln!(out, "- **SHA-256:** `{}`", t.sha256);
        let _ = writeln!(out, "- **Size:** {}", crate::human_bytes(t.bytes.len()));
    }
    let _ = writeln!(out, "- **Mode:** {}", craft_anything_engine::clean_room::mode_words(clean_room));
    let _ = writeln!(
        out,
        "\nConfidence: *Seen it* = read directly; *Worked it out* = computed from what we saw; *Best guess* = a reasonable reading, not proven.\n"
    );
    let mut evidence: Vec<&Evidence> = Vec::new();
    for item in chat {
        match item {
            ChatItem::User(q) => {
                let _ = writeln!(out, "## {q}\n");
            }
            ChatItem::Assistant { text, backend, .. } => {
                let _ = writeln!(out, "{text}\n");
                if let Some(b) = backend {
                    let _ = writeln!(out, "*Answered by {b}.*\n");
                }
            }
            ChatItem::Tool { tool, summary, evidence: ev, ok, .. } => {
                let mark = match ok {
                    Some(true) => "ran",
                    Some(false) => "failed",
                    None => "running",
                };
                let _ = writeln!(out, "- `{tool}` {mark}{}", if summary.is_empty() { String::new() } else { format!(": {summary}") });
                if let Some(e) = ev {
                    evidence.push(e);
                }
            }
            ChatItem::Proof { intro, evidence: e } => {
                if !intro.is_empty() {
                    let _ = writeln!(out, "{intro}\n");
                }
                evidence_md(&mut out, e);
                evidence.push(e);
            }
            ChatItem::Consent { title, answer, .. } => {
                let a = match answer {
                    Some(ConsentAnswer::Once) => "allowed once",
                    Some(ConsentAnswer::AlwaysForProject) => "allowed for this project",
                    Some(ConsentAnswer::Deny) => "not allowed",
                    None => "not answered",
                };
                let _ = writeln!(out, "- Permission to run *{title}*: {a}\n");
            }
            ChatItem::Error { message, remediation, .. } => {
                let _ = writeln!(out, "> ⚠ {message}{}\n", remediation.as_ref().map(|r| format!(" {r}")).unwrap_or_default());
            }
            ChatItem::Status(_) | ChatItem::AddBrain => {}
        }
    }
    if !evidence.is_empty() {
        let _ = writeln!(out, "\n## Evidence\n");
        for e in evidence {
            let _ = writeln!(out, "### {}\n", e.operation);
            evidence_md(&mut out, e);
        }
    }
    let _ = writeln!(out, "\n---\nMade with Craft Anything {}.", env!("CARGO_PKG_VERSION"));
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn report_has_questions_answers_and_permissions() {
        let chat = vec![
            ChatItem::User("What does it do?".into()),
            ChatItem::Assistant { text: "It adds numbers.".into(), backend: Some("Claude".into()), streaming: false },
            ChatItem::Consent {
                call_id: "1".into(),
                tool: "run".into(),
                title: "Run it".into(),
                explanation: String::new(),
                answer: Some(ConsentAnswer::Deny),
            },
        ];
        let md = markdown(&chat, None, true);
        assert!(md.contains("## What does it do?"));
        assert!(md.contains("It adds numbers."));
        assert!(md.contains("not allowed"));
        assert!(md.contains("Clean room"));
    }
}
