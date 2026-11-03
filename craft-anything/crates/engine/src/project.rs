//! Projects (`*.cany` folders): evidence, unknowns, annotations and notes that survive restarts.
//!
//! Layout:
//! ```text
//! name.cany/
//!   project.toml          name, purpose, created, format version
//!   evidence/ab/<id>.json content-addressed evidence records
//!   unknowns/<id>.json
//!   annotations/<sha256>.json
//!   notes.md
//! ```
//! Every write is atomic (temp file + rename). Nothing outside the folder is ever written.

use crate::session::Annotations;
use crate::versioned::{Step, upgrade};
use craft_anything_evidence::{ErrorCode, Evidence, ToolError, Unknown, is_evidence_id};
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

pub const PROJECT_EXTENSION: &str = "cany";
/// The current `project.toml` format version. Bumping it means appending a step to [`FORMAT_STEPS`].
pub const FORMAT_VERSION: u32 = 1;

/// The oldest format a project can be in: projects have carried `format_version` since the start.
const FIRST_FORMAT: u32 = 1;

/// The steps that bring an older `project.toml` forward; step `i` goes from format
/// `FIRST_FORMAT + i` to `FIRST_FORMAT + i + 1`. None yet: format 1 is the only one so far.
const FORMAT_STEPS: &[Step<toml::Table>] = &[];
const _: () = assert!(FIRST_FORMAT as usize + FORMAT_STEPS.len() == FORMAT_VERSION as usize, "one step per project format");

/// Read a `project.toml` of any format this build understands, bringing older ones forward. A
/// newer format is refused: a project's evidence layout may have changed in ways we can't see.
pub fn read_project_meta(text: &str) -> Result<ProjectMeta, ToolError> {
    let bad = |e: String| ToolError::new(ErrorCode::BadSettings, format!("project.toml: {e}"));
    let mut table: toml::Table = toml::from_str(text).map_err(|e| bad(e.to_string()))?;
    let found = match table.get("format_version") {
        None => return Err(bad("missing field `format_version`".into())),
        Some(v) => v.as_integer().and_then(|n| u32::try_from(n).ok()).ok_or_else(|| bad(format!("format_version ({v}) isn't a whole number")))?,
    };
    if found > FORMAT_VERSION {
        return Err(ToolError::unsupported(format!("This project was made by a newer Craft Anything (format {found})."))
            .with_remediation("Update Craft Anything to open it."));
    }
    let reached = upgrade(&mut table, found, FIRST_FORMAT, FORMAT_STEPS).map_err(bad)?;
    table.insert("format_version".into(), toml::Value::Integer(reached.into()));
    table.try_into::<ProjectMeta>().map_err(|e| bad(e.to_string()))
}

/// Why the user is examining software. Asked once, in plain words.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default, schemars::JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Purpose {
    /// My own software, or software I'm allowed to examine.
    #[default]
    OwnOrAuthorized,
    /// Making something work with something else.
    Interoperability,
    /// Security research.
    Security,
    /// Learning how things work.
    Education,
    /// Keeping old software alive.
    Preservation,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ProjectMeta {
    pub name: String,
    #[serde(default)]
    pub purpose: Purpose,
    pub format_version: u32,
    /// Tools the user said may run code or change devices in this project without asking again.
    #[serde(default)]
    pub allowed_tools: Vec<String>,
}

/// One evidence file in a project's store.
#[derive(Debug, Clone)]
pub struct StoredEvidence {
    pub id: String,
    pub modified: Option<std::time::SystemTime>,
    pub bytes: u64,
}

#[derive(Debug, Clone)]
pub struct Project {
    pub root: PathBuf,
    pub meta: ProjectMeta,
}

impl Project {
    /// Create a new project folder (fails if it exists and isn't empty).
    pub fn create(root: &Path, name: &str, purpose: Purpose) -> Result<Project, ToolError> {
        if root.exists() && std::fs::read_dir(root).map(|mut d| d.next().is_some()).unwrap_or(true) {
            return Err(ToolError::invalid(format!("{} already exists", root.display())).with_remediation("Pick a new folder name."));
        }
        for sub in ["evidence", "unknowns", "annotations"] {
            std::fs::create_dir_all(root.join(sub)).map_err(|e| ToolError::io(root.display(), e))?;
        }
        let meta = ProjectMeta { name: name.to_string(), purpose, format_version: FORMAT_VERSION, allowed_tools: Vec::new() };
        let p = Project { root: root.to_path_buf(), meta };
        p.save_meta()?;
        Ok(p)
    }

    pub fn open(root: &Path) -> Result<Project, ToolError> {
        let text = std::fs::read_to_string(root.join("project.toml")).map_err(|e| ToolError::io(root.display(), e))?;
        let meta = read_project_meta(&text)?;
        Ok(Project { root: root.to_path_buf(), meta })
    }

    pub fn save_meta(&self) -> Result<(), ToolError> {
        let text = toml::to_string_pretty(&self.meta).map_err(|e| ToolError::internal(format!("project.toml: {e}")))?;
        write_atomic(&self.root.join("project.toml"), text.as_bytes())
    }

    fn evidence_path(&self, id: &str) -> Result<PathBuf, ToolError> {
        if !is_evidence_id(id) {
            return Err(ToolError::invalid(format!("not an evidence id: {id}")));
        }
        let shard = id.get(3..5).unwrap_or("00");
        Ok(self.root.join("evidence").join(shard).join(format!("{id}.json")))
    }

    pub fn store_evidence(&self, ev: &Evidence) -> Result<(), ToolError> {
        let path = self.evidence_path(&ev.id)?;
        if path.exists() {
            return Ok(());
        }
        let text = serde_json::to_vec_pretty(ev).map_err(|e| ToolError::internal(e.to_string()))?;
        write_atomic(&path, &text)
    }

    pub fn load_evidence(&self, id: &str) -> Result<Evidence, ToolError> {
        let path = self.evidence_path(id)?;
        let bytes = std::fs::read(&path).map_err(|e| ToolError::io(path.display(), e))?;
        let ev: Evidence = serde_json::from_slice(&bytes).map_err(|e| ToolError::new(ErrorCode::EvidenceHashMismatch, format!("{id}: {e}")))?;
        if !ev.verify() || ev.id != id {
            return Err(ToolError::new(ErrorCode::EvidenceHashMismatch, format!("{id} was changed after it was recorded")));
        }
        Ok(ev)
    }

    /// Every stored evidence id.
    pub fn evidence_ids(&self) -> Vec<String> {
        let mut out: Vec<String> = self.evidence_files().into_iter().map(|f| f.id).collect();
        out.sort();
        out
    }

    /// Every stored evidence record's id, write time and size (unordered, contents not read).
    pub fn evidence_files(&self) -> Vec<StoredEvidence> {
        let mut out = Vec::new();
        if let Ok(shards) = std::fs::read_dir(self.root.join("evidence")) {
            for shard in shards.flatten() {
                if let Ok(files) = std::fs::read_dir(shard.path()) {
                    for f in files.flatten() {
                        if let Some(id) = f.path().file_stem().map(|s| s.to_string_lossy().into_owned())
                            && is_evidence_id(&id)
                        {
                            let meta = f.metadata().ok();
                            let modified = meta.as_ref().and_then(|m| m.modified().ok());
                            out.push(StoredEvidence { id, modified, bytes: meta.map(|m| m.len()).unwrap_or(0) });
                        }
                    }
                }
            }
        }
        out
    }

    pub fn store_unknown(&self, u: &Unknown) -> Result<(), ToolError> {
        let safe: String = u.id.chars().filter(|c| c.is_ascii_alphanumeric() || *c == '_').collect();
        let text = serde_json::to_vec_pretty(u).map_err(|e| ToolError::internal(e.to_string()))?;
        write_atomic(&self.root.join("unknowns").join(format!("{safe}.json")), &text)
    }

    pub fn load_unknowns(&self) -> Result<Vec<Unknown>, ToolError> {
        let mut out = Vec::new();
        let dir = self.root.join("unknowns");
        let Ok(entries) = std::fs::read_dir(&dir) else { return Ok(out) };
        for e in entries.flatten() {
            if let Ok(bytes) = std::fs::read(e.path()) {
                match serde_json::from_slice::<Unknown>(&bytes) {
                    Ok(u) => out.push(u),
                    Err(err) => log::warn!("skipping unreadable unknown {}: {err}", e.path().display()),
                }
            }
        }
        Ok(out)
    }

    fn annotations_path(&self, sha256: &str) -> PathBuf {
        let safe: String = sha256.chars().filter(|c| c.is_ascii_hexdigit()).take(64).collect();
        self.root.join("annotations").join(format!("{safe}.json"))
    }

    pub fn load_annotations(&self, sha256: &str) -> Result<Annotations, ToolError> {
        let path = self.annotations_path(sha256);
        let bytes = std::fs::read(&path).map_err(|e| ToolError::io(path.display(), e))?;
        serde_json::from_slice(&bytes).map_err(|e| ToolError::new(ErrorCode::BadSettings, e.to_string()))
    }

    pub fn save_annotations(&self, sha256: &str, a: &Annotations) -> Result<(), ToolError> {
        let text = serde_json::to_vec_pretty(a).map_err(|e| ToolError::internal(e.to_string()))?;
        write_atomic(&self.annotations_path(sha256), &text)
    }

    pub fn is_allowed(&self, tool: &str) -> bool {
        self.meta.allowed_tools.iter().any(|t| t == tool)
    }
}

/// Write `bytes` to `path` atomically: a temp file of its own, fsync, then rename (retried on
/// Windows while another program holds the file for a moment).
pub use craft_anything_platform::fs::write_atomic;

#[cfg(test)]
mod tests {
    use super::*;
    use craft_anything_evidence::{Environment, EvidenceBuilder, Subject};

    /// #273: threads saving one file at once shared a temp file, so saves failed with "not found"
    /// and the file could be left half one version, half another.
    #[test]
    fn saves_from_several_threads_never_mix() {
        let dir = tempfile::tempdir().unwrap();
        let p = dir.path().join("craft.json");
        let versions: Vec<Vec<u8>> = (0..4u8).map(|i| vec![b'a' + i; 4096 * (usize::from(i) + 1)]).collect();
        std::thread::scope(|s| {
            for v in &versions {
                let (p, versions) = (&p, &versions);
                s.spawn(move || {
                    for _ in 0..50 {
                        write_atomic(p, v).unwrap();
                        let now = std::fs::read(p).unwrap();
                        assert!(versions.contains(&now), "a mixed file of {} bytes", now.len());
                    }
                });
            }
        });
        assert_eq!(std::fs::read_dir(dir.path()).unwrap().count(), 1, "temp files left behind");
    }

    /// A file another program holds open for a moment (as a virus scan does) is still replaced.
    #[cfg(windows)]
    #[test]
    fn a_file_held_open_for_a_moment_is_still_replaced() {
        use std::os::windows::fs::OpenOptionsExt;
        let d = tempfile::tempdir().unwrap();
        let p = d.path().join("config.toml");
        std::fs::write(&p, "old").unwrap();
        // Shared for reading only, so replacing the file fails while it's open.
        let held = std::fs::OpenOptions::new().read(true).share_mode(1).open(&p).unwrap();
        std::fs::write(d.path().join("probe"), "x").unwrap();
        assert!(std::fs::rename(d.path().join("probe"), &p).is_err(), "the held file can't be replaced");
        let release = std::thread::spawn(move || {
            std::thread::sleep(std::time::Duration::from_millis(400));
            drop(held);
        });
        write_atomic(&p, b"new").unwrap();
        release.join().unwrap();
        assert_eq!(std::fs::read_to_string(&p).unwrap(), "new");
    }

    #[test]
    fn project_formats_are_brought_forward_and_newer_ones_refused() {
        // project.toml as the first release wrote it.
        let v1 = "name = \"t\"\npurpose = \"education\"\nformat_version = 1\nallowed_tools = [\"run_program\"]\n";
        let meta = read_project_meta(v1).unwrap();
        assert_eq!((meta.format_version, meta.purpose, meta.allowed_tools.len()), (1, Purpose::Education, 1));
        assert_eq!(read_project_meta("name = \"t\"\nformat_version = 1\n").unwrap().purpose, Purpose::OwnOrAuthorized);

        let newer = read_project_meta("name = \"t\"\nformat_version = 2\n").unwrap_err();
        assert_eq!(newer.code, ErrorCode::NotSupported);
        assert!(newer.message.contains("newer") && newer.remediation.is_some());
        for bad in ["name = \"t\"\n", "name = \"t\"\nformat_version = 0\n", "format_version = \"1\"\n", "format_version = -3\n", "[[["] {
            assert_eq!(read_project_meta(bad).unwrap_err().code, ErrorCode::BadSettings, "{bad}");
        }

        // The mechanism a format 2 will use: a step rewrites the raw table before it's read.
        fn rename_tools(t: &mut toml::Table) -> Result<(), String> {
            if let Some(v) = t.remove("allowed") {
                t.insert("allowed_tools".into(), v);
            }
            Ok(())
        }
        let mut t: toml::Table = toml::from_str("name = \"t\"\nformat_version = 1\nallowed = [\"x\"]\n").unwrap();
        assert_eq!(upgrade(&mut t, 1, FIRST_FORMAT, &[rename_tools as Step<toml::Table>]), Ok(2));
        assert_eq!(t.get("allowed_tools").and_then(|v| v.as_array()).map(Vec::len), Some(1));
    }

    #[test]
    fn evidence_round_trips_and_detects_tampering() {
        let dir = tempfile::tempdir().unwrap();
        let p = Project::create(&dir.path().join("t.cany"), "t", Purpose::Education).unwrap();
        let ev = EvidenceBuilder::new("x", Subject::default(), Environment::builtin(true)).result(serde_json::json!(1)).build().unwrap();
        p.store_evidence(&ev).unwrap();
        assert_eq!(p.load_evidence(&ev.id).unwrap(), ev);
        assert_eq!(p.evidence_ids(), vec![ev.id.clone()]);
        let path = p.evidence_path(&ev.id).unwrap();
        let text = std::fs::read_to_string(&path).unwrap().replace("\"result\": 1", "\"result\": 2");
        std::fs::write(&path, text).unwrap();
        assert_eq!(p.load_evidence(&ev.id).unwrap_err().code, ErrorCode::EvidenceHashMismatch);
        let reopened = Project::open(&p.root).unwrap();
        assert_eq!(reopened.meta.purpose, Purpose::Education);
    }
}
