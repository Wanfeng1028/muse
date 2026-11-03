//! Notes the person adds while the builder works, handed over at the builder's next step instead
//! of after its whole turn. The run writes each one to `inbox/notes/<id>.json`; a coding agent
//! that runs a command after every tool call (Claude Code's PostToolUse hook, running
//! `craft-anything-cli builder-notes <dir>`) claims what's there by renaming it to
//! `<id>.read.json` and gives the text to the model; the run sees the rename and shows the note as
//! read. The rename is the one moment a note changes hands, so "take back" works until then.
//! Notes nobody claimed still go in after the turn, as before.

use std::path::{Path, PathBuf};

/// Where a project's notes wait for the builder.
pub fn notes_dir(inbox: &Path) -> PathBuf {
    inbox.join("notes")
}

fn pending(dir: &Path, id: u64) -> PathBuf {
    dir.join(format!("{id}.json"))
}

fn read(dir: &Path, id: u64) -> PathBuf {
    dir.join(format!("{id}.read.json"))
}

/// Leave a note for the builder's next step.
pub fn hand_over(dir: &Path, id: u64, text: &str) -> Result<(), craft_anything_evidence::ToolError> {
    std::fs::create_dir_all(dir).map_err(|e| craft_anything_evidence::ToolError::io(dir.display(), e))?;
    let bytes = serde_json::to_vec(&serde_json::json!({"id": id, "text": text})).map_err(|e| craft_anything_evidence::ToolError::internal(e.to_string()))?;
    craft_anything_engine::project::write_atomic(&pending(dir, id), &bytes)
}

/// Take a note back before the builder read it: true when it was still waiting.
pub fn take_back(dir: &Path, id: u64) -> bool {
    std::fs::remove_file(pending(dir, id)).is_ok()
}

/// The builder has read the note (it was claimed).
pub fn was_read(dir: &Path, id: u64) -> bool {
    read(dir, id).is_file()
}

/// Done with a note: its files go.
pub fn forget(dir: &Path, id: u64) {
    let _ = std::fs::remove_file(pending(dir, id));
    let _ = std::fs::remove_file(read(dir, id));
}

/// Start a run with no notes left over from an earlier one (ids restart with the process).
pub fn clear(dir: &Path) {
    let _ = std::fs::remove_dir_all(dir);
}

/// For the agent's hook: claim every waiting note, oldest first, and return their texts. A note
/// another claimer (or "take back") got first is skipped.
pub fn claim(dir: &Path) -> Vec<String> {
    let Ok(entries) = std::fs::read_dir(dir) else { return Vec::new() };
    let mut ids: Vec<u64> =
        entries.flatten().filter_map(|e| e.file_name().to_str().and_then(|n| n.strip_suffix(".json")).and_then(|n| n.parse::<u64>().ok())).collect();
    ids.sort_unstable();
    ids.into_iter()
        .filter_map(|id| {
            let text = std::fs::read(pending(dir, id)).ok().and_then(|b| serde_json::from_slice::<serde_json::Value>(&b).ok())?;
            std::fs::rename(pending(dir, id), read(dir, id)).ok()?;
            text.get("text").and_then(serde_json::Value::as_str).map(String::from)
        })
        .collect()
}

/// What the hook prints for the agent: the notes as context for its next step, or nothing.
pub fn hook_output(texts: &[String]) -> Option<String> {
    if texts.is_empty() {
        return None;
    }
    let list = texts.iter().map(|t| format!("- {t}")).collect::<Vec<_>>().join("\n");
    // Stated as facts: the agent reads it as context, not as an order from the tool.
    let context = format!(
        "The person added this while you were working:\n{list}\nIt applies to the work from here on, and your reply can say how you took it into account."
    );
    Some(serde_json::json!({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": context}}).to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_note_changes_hands_once_and_can_be_taken_back_until_then() {
        let d = tempfile::tempdir().unwrap();
        let dir = notes_dir(d.path());
        assert!(claim(&dir).is_empty(), "no folder, nothing to claim");
        hand_over(&dir, 2, "make the header blue").unwrap();
        hand_over(&dir, 10, "add a contact form").unwrap();
        hand_over(&dir, 3, "never mind the footer").unwrap();
        assert!(take_back(&dir, 3), "still waiting: it can be taken back");
        assert_eq!(claim(&dir), ["make the header blue", "add a contact form"], "oldest first, by number");
        assert!(was_read(&dir, 2) && was_read(&dir, 10) && !was_read(&dir, 3));
        assert!(!take_back(&dir, 2), "read notes can't be taken back");
        assert!(claim(&dir).is_empty(), "each note is handed over once");
        forget(&dir, 2);
        assert!(!was_read(&dir, 2));
        clear(&dir);
        assert!(!dir.exists());
    }

    #[test]
    fn the_hook_hands_the_notes_to_the_model_as_context() {
        assert!(hook_output(&[]).is_none(), "nothing printed when nothing waits");
        let out: serde_json::Value = serde_json::from_str(&hook_output(&["make it blue".into()]).unwrap()).unwrap();
        assert_eq!(out["hookSpecificOutput"]["hookEventName"], "PostToolUse");
        let context = out["hookSpecificOutput"]["additionalContext"].as_str().unwrap();
        assert!(context.contains("- make it blue") && context.contains("applies to the work from here on"), "{context}");
    }
}
