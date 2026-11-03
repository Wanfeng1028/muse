//! The skill we install into coding-agent apps: our own guide to the investigation method.

use craft_anything_evidence::ToolError;
use serde::Serialize;
use std::path::{Path, PathBuf};

/// Folder name under each skills directory.
pub const SKILL_DIR: &str = "craft-anything";
/// Bumped whenever the skill text changes.
pub const SKILL_VERSION: &str = "1";
/// How an installed SKILL.md identifies itself as ours.
pub const SKILL_PREFIX: &str = "---\nname: craft-anything\n";
const REFERENCE_MARKER: &str = "<!-- craft-anything skill reference -->";

pub const SKILL_MD: &str = include_str!("skill.md");
pub const RECOVERY_MD: &str = include_str!("skill_recovery.md");

/// The managed files, relative to `<skills dir>/craft-anything/`.
pub fn files() -> [(&'static str, &'static str); 2] {
    [("SKILL.md", SKILL_MD), ("references/recovery.md", RECOVERY_MD)]
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum SkillState {
    Missing,
    Current,
    /// Ours, but an older or edited version.
    Outdated,
    /// Something else lives at our path.
    Foreign,
}

/// What's installed in one skills directory.
pub fn inspect(skills_dir: &Path) -> SkillState {
    let path = skills_dir.join(SKILL_DIR).join("SKILL.md");
    match std::fs::read_to_string(&path) {
        Err(_) => SkillState::Missing,
        Ok(t) if !t.replace("\r\n", "\n").starts_with(SKILL_PREFIX) => SkillState::Foreign,
        Ok(_) => {
            let all_current = files().iter().all(|(rel, body)| std::fs::read_to_string(skills_dir.join(SKILL_DIR).join(rel)).is_ok_and(|t| t == *body));
            if all_current { SkillState::Current } else { SkillState::Outdated }
        }
    }
}

/// One file the install would create or update.
#[derive(Debug, Clone, Serialize)]
pub struct SkillFileAction {
    pub path: PathBuf,
    /// `create`, `update` or `already_current`.
    pub action: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub backup: Option<PathBuf>,
}

pub fn backup_path(p: &Path) -> PathBuf {
    let mut s = p.as_os_str().to_os_string();
    s.push(".craft-anything.backup");
    PathBuf::from(s)
}

pub fn plan(skills_dir: &Path) -> Vec<SkillFileAction> {
    files()
        .iter()
        .map(|(rel, body)| {
            let path = skills_dir.join(SKILL_DIR).join(rel);
            match std::fs::read_to_string(&path) {
                Ok(t) if t == *body => SkillFileAction { path, action: "already_current", backup: None },
                Ok(_) => SkillFileAction { backup: Some(backup_path(&path)), path, action: "update" },
                Err(_) => SkillFileAction { path, action: "create", backup: None },
            }
        })
        .collect()
}

/// Install (or refresh) the skill in `skills_dir`. Only changed files are touched; on any failure
/// everything written in this call is put back in reverse order.
pub fn install(skills_dir: &Path) -> Result<Vec<PathBuf>, ToolError> {
    let mut done: Vec<(PathBuf, Option<Vec<u8>>)> = Vec::new();
    let mut written = Vec::new();
    for (rel, body) in files() {
        let path = skills_dir.join(SKILL_DIR).join(rel);
        let old = std::fs::read(&path).ok();
        if old.as_deref() == Some(body.as_bytes()) {
            continue;
        }
        let step = (|| {
            if old.is_some() {
                craft_anything_platform::backup_once(&path, &backup_path(&path))?;
            }
            craft_anything_platform::write_atomic_private(&path, body.as_bytes())?;
            let back = std::fs::read(&path).map_err(|e| ToolError::io(path.display(), e))?;
            if back != body.as_bytes() {
                return Err(ToolError::new(craft_anything_evidence::ErrorCode::FileError, format!("{} did not read back correctly", path.display())));
            }
            Ok(())
        })();
        done.push((path.clone(), old));
        if let Err(e) = step {
            rollback(&done);
            return Err(e);
        }
        written.push(path);
    }
    Ok(written)
}

fn rollback(done: &[(PathBuf, Option<Vec<u8>>)]) {
    for (path, old) in done.iter().rev() {
        let r = match old {
            Some(bytes) => craft_anything_platform::write_atomic(path, bytes).map_err(|e| e.message),
            None => std::fs::remove_file(path).map_err(|e| e.to_string()),
        };
        if let Err(e) = r {
            log::warn!("could not roll back {}: {e}; restore it from its .craft-anything.backup copy", path.display());
        }
    }
}

/// Remove our skill files from `skills_dir` (only files that identify as ours), then any of our
/// folders left empty. Returns removed paths.
pub fn uninstall(skills_dir: &Path) -> Vec<PathBuf> {
    let root = skills_dir.join(SKILL_DIR);
    let mut removed = Vec::new();
    for (rel, _) in files() {
        let path = root.join(rel);
        let Ok(text) = std::fs::read_to_string(&path) else { continue };
        let text = text.replace("\r\n", "\n");
        let ours = if rel == "SKILL.md" { text.starts_with(SKILL_PREFIX) } else { text.starts_with(REFERENCE_MARKER) };
        if ours && std::fs::remove_file(&path).is_ok() {
            removed.push(path);
        }
    }
    for d in [root.join("references"), root] {
        // remove_dir only succeeds on empty folders
        if std::fs::remove_dir(&d).is_ok() {
            removed.push(d);
        }
    }
    removed
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn content_is_ours_and_teaches_the_loop() {
        assert!(SKILL_MD.starts_with(SKILL_PREFIX));
        assert!(RECOVERY_MD.starts_with(REFERENCE_MARKER));
        assert!(SKILL_MD.contains(&format!("version: \"{SKILL_VERSION}\"")));
        for t in [
            "core_investigation_show",
            "core_brief_write",
            "core_plan_update",
            "core_hypothesis_record",
            "core_hypothesis_update",
            "core_finding_record",
            "core_handoff_write",
            "core_journal_read",
            "enable_toolset",
        ] {
            assert!(SKILL_MD.contains(t), "{t}");
        }
    }

    #[test]
    fn install_update_uninstall() {
        let dir = tempfile::tempdir().unwrap();
        assert_eq!(inspect(dir.path()), SkillState::Missing);
        assert_eq!(install(dir.path()).unwrap().len(), 2);
        assert_eq!(inspect(dir.path()), SkillState::Current);
        assert!(install(dir.path()).unwrap().is_empty());
        assert!(plan(dir.path()).iter().all(|a| a.action == "already_current"));
        let skill = dir.path().join(SKILL_DIR).join("SKILL.md");
        std::fs::write(&skill, format!("{SKILL_PREFIX}old\n")).unwrap();
        assert_eq!(inspect(dir.path()), SkillState::Outdated);
        assert_eq!(install(dir.path()).unwrap().len(), 1);
        assert!(backup_path(&skill).exists());
        // a user's own file in our folder survives uninstall, and so does the folder
        std::fs::write(dir.path().join(SKILL_DIR).join("notes.md"), "mine").unwrap();
        let removed = uninstall(dir.path());
        assert!(removed.iter().any(|p| p.ends_with("SKILL.md")));
        assert!(dir.path().join(SKILL_DIR).join("notes.md").exists());
        std::fs::remove_file(dir.path().join(SKILL_DIR).join("notes.md")).unwrap();
        std::fs::remove_file(backup_path(&skill)).unwrap();
        uninstall(dir.path());
        assert!(!dir.path().join(SKILL_DIR).exists());
    }

    #[test]
    fn foreign_skill_is_not_removed() {
        let dir = tempfile::tempdir().unwrap();
        let p = dir.path().join(SKILL_DIR).join("SKILL.md");
        std::fs::create_dir_all(p.parent().unwrap()).unwrap();
        std::fs::write(&p, "---\nname: something-else\n---\n").unwrap();
        assert_eq!(inspect(dir.path()), SkillState::Foreign);
        assert!(uninstall(dir.path()).is_empty());
        assert!(p.exists());
    }
}
