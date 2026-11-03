//! The session: open targets, the evidence ledger, unknowns, annotations and caches.

use crate::project::Project;
use crate::settings::Settings;
use crate::target::{Target, TargetId};
use craft_anything_evidence::{ErrorCode, Evidence, ToolError, Unknown};
use std::any::{Any, TypeId};
use std::collections::{BTreeMap, HashMap};
use std::sync::Arc;

/// Per-target annotations made by people or agents (names, comments, bookmarks).
#[derive(Debug, Clone, Default, serde::Serialize, serde::Deserialize)]
pub struct Annotations {
    pub names: BTreeMap<u64, String>,
    pub comments: BTreeMap<u64, String>,
    pub inline_comments: BTreeMap<u64, String>,
    pub bookmarks: BTreeMap<u64, String>,
}

/// Where the user (or agent) is looking in a target.
#[derive(Debug, Clone, Default, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub struct Cursor {
    pub address: Option<u64>,
}

/// Type-keyed cache slots that analysis layers attach to a target (disassembly, module graphs…).
#[derive(Default)]
pub struct Extensions(HashMap<TypeId, Arc<dyn Any + Send + Sync>>);

impl Extensions {
    pub fn get<T: Any + Send + Sync>(&self) -> Option<Arc<T>> {
        self.0.get(&TypeId::of::<T>()).and_then(|a| a.clone().downcast::<T>().ok())
    }

    pub fn insert<T: Any + Send + Sync>(&mut self, value: Arc<T>) {
        self.0.insert(TypeId::of::<T>(), value);
    }

    pub fn remove<T: Any + Send + Sync>(&mut self) -> Option<Arc<T>> {
        self.0.remove(&TypeId::of::<T>()).and_then(|a| a.downcast::<T>().ok())
    }

    pub fn clear(&mut self) {
        self.0.clear();
    }
}

impl std::fmt::Debug for Extensions {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "Extensions({} slots)", self.0.len())
    }
}

/// One open target with its annotations and caches.
#[derive(Debug)]
pub struct OpenTarget {
    pub target: Target,
    pub annotations: Annotations,
    pub cursor: Cursor,
    pub ext: Extensions,
}

/// How many project evidence records a session keeps in memory (newest first). Older ones stay on
/// disk and still resolve by id.
pub const MAX_LOADED_EVIDENCE: usize = 5_000;
/// Total bytes of project evidence a session loads into memory before leaving the rest on disk.
const MAX_LOADED_EVIDENCE_BYTES: u64 = 64 * 1024 * 1024;

/// All state a tool can touch.
#[derive(Debug, Default)]
pub struct Session {
    pub settings: Settings,
    pub project: Option<Project>,
    targets: BTreeMap<TargetId, OpenTarget>,
    active: Option<TargetId>,
    ledger: BTreeMap<String, Evidence>,
    /// Insertion order of the ledger, for "latest first" views.
    order: Vec<String>,
    unknowns: BTreeMap<String, Unknown>,
    /// Project records left on disk because the project holds more than [`MAX_LOADED_EVIDENCE`].
    /// They still resolve by id through [`Session::resolve_evidence`].
    unloaded_evidence: usize,
    /// Session-wide caches not tied to a target (device lists, browser connections…).
    pub ext: Extensions,
    /// Where this session keeps config.toml and plugin caches, when not the usual folder
    /// ([`crate::settings::config_dir`]); see [`Session::isolated`].
    config_dir: Option<std::path::PathBuf>,
    /// Deep mode (`true`) or Clean room (`false`) for this process only, over
    /// `settings.deep_mode` and never saved: the CLI's `--deep` and `--clean-room`.
    pub deep_for_run: Option<bool>,
}

impl Session {
    pub fn new(settings: Settings) -> Self {
        Session { settings, ..Default::default() }
    }

    /// A session that keeps everything under `dir` (config.toml, plugin caches, the engine store,
    /// new projects) instead of this computer's own folders: for tests, and anything that must not
    /// touch the person's setup.
    pub fn isolated(dir: &std::path::Path) -> Self {
        let mut settings = Settings::default();
        settings.engines.store_dir = Some(dir.join("engines"));
        settings.projects_dir = Some(dir.join("projects"));
        Session { settings, config_dir: Some(dir.to_path_buf()), ..Default::default() }
    }

    /// Keep a project started in a folder the person picked in the project list
    /// ([`Settings::remember_project`]), saving settings when that changed them.
    pub fn remember_project(&mut self, root: &std::path::Path) -> Result<(), craft_anything_evidence::ToolError> {
        let mut next = self.settings.clone();
        if next.remember_project(root) {
            next.save_to(&self.config_dir().join("config.toml"))?;
            self.settings = next;
        }
        Ok(())
    }

    /// Where this session's config.toml and plugin caches live.
    pub fn config_dir(&self) -> std::path::PathBuf {
        self.config_dir.clone().unwrap_or_else(crate::settings::config_dir)
    }

    /// True in Clean room: nothing inside a target is read ([`crate::clean_room`]).
    pub fn clean_room(&self) -> bool {
        !self.deep_for_run.unwrap_or(self.settings.deep_mode)
    }

    // ---- targets ----

    pub fn add_target(&mut self, target: Target) -> TargetId {
        let id = target.id.clone();
        let annotations = self.project.as_ref().and_then(|p| p.load_annotations(&target.sha256).ok()).unwrap_or_default();
        self.targets.insert(id.clone(), OpenTarget { target, annotations, cursor: Cursor::default(), ext: Extensions::default() });
        self.active = Some(id.clone());
        id
    }

    pub fn close_target(&mut self, id: &TargetId) -> Option<OpenTarget> {
        let removed = self.targets.remove(id);
        if self.active.as_ref() == Some(id) {
            self.active = self.targets.keys().next_back().cloned();
        }
        removed
    }

    pub fn targets(&self) -> impl Iterator<Item = &OpenTarget> {
        self.targets.values()
    }

    pub fn target(&self, id: &TargetId) -> Option<&OpenTarget> {
        self.targets.get(id)
    }

    pub fn target_mut(&mut self, id: &TargetId) -> Option<&mut OpenTarget> {
        self.targets.get_mut(id)
    }

    pub fn active_id(&self) -> Option<&TargetId> {
        self.active.as_ref()
    }

    pub fn set_active(&mut self, id: &TargetId) -> Result<(), ToolError> {
        if self.targets.contains_key(id) {
            self.active = Some(id.clone());
            Ok(())
        } else {
            Err(ToolError::new(ErrorCode::NotFound, format!("No open target {id}")))
        }
    }

    /// The active target, or a `not_found` error that tells the caller what to do.
    pub fn active(&self) -> Result<&OpenTarget, ToolError> {
        self.active.as_ref().and_then(|id| self.targets.get(id)).ok_or_else(ToolError::target_required)
    }

    pub fn active_mut(&mut self) -> Result<&mut OpenTarget, ToolError> {
        match self.active.clone() {
            Some(id) => self.targets.get_mut(&id).ok_or_else(ToolError::target_required),
            None => Err(ToolError::target_required()),
        }
    }

    /// Persist the active target's annotations to the project, if one is open.
    pub fn save_annotations(&self) -> Result<(), ToolError> {
        if let (Some(project), Ok(t)) = (&self.project, self.active()) {
            project.save_annotations(&t.target.sha256, &t.annotations)?;
        }
        Ok(())
    }

    // ---- evidence ----

    /// Record evidence in the ledger (and the project store, when a project is open).
    pub fn record(&mut self, ev: Evidence) -> Result<(), ToolError> {
        if let Some(project) = &self.project {
            project.store_evidence(&ev)?;
        }
        if !self.ledger.contains_key(&ev.id) {
            self.order.push(ev.id.clone());
        }
        self.ledger.insert(ev.id.clone(), ev);
        Ok(())
    }

    pub fn evidence(&self, id: &str) -> Option<&Evidence> {
        self.ledger.get(id).or(None)
    }

    /// Look up evidence in memory, then in the project store.
    pub fn resolve_evidence(&self, id: &str) -> Result<Evidence, ToolError> {
        if let Some(e) = self.ledger.get(id) {
            return Ok(e.clone());
        }
        if let Some(project) = &self.project
            && let Ok(e) = project.load_evidence(id)
        {
            return Ok(e);
        }
        Err(ToolError::invalid(format!("Unknown evidence id {id}")).with_details(serde_json::json!({"reason": "missing", "evidence_id": id})))
    }

    /// Evidence, newest first.
    pub fn ledger(&self) -> impl Iterator<Item = &Evidence> {
        self.order.iter().rev().filter_map(|id| self.ledger.get(id))
    }

    pub fn ledger_len(&self) -> usize {
        self.ledger.len()
    }

    /// Project records not loaded into the ledger because the project is larger than the in-memory cap.
    pub fn unloaded_evidence(&self) -> usize {
        self.unloaded_evidence
    }

    pub fn clear_ledger(&mut self) {
        self.ledger.clear();
        self.order.clear();
        self.unknowns.clear();
        self.unloaded_evidence = 0;
    }

    // ---- unknowns ----

    pub fn unknowns(&self) -> impl Iterator<Item = &Unknown> {
        self.unknowns.values()
    }

    pub fn unknown(&self, id: &str) -> Option<&Unknown> {
        self.unknowns.get(id)
    }

    pub fn put_unknown(&mut self, u: Unknown) -> Result<(), ToolError> {
        if let Some(project) = &self.project {
            project.store_unknown(&u)?;
        }
        self.unknowns.insert(u.id.clone(), u);
        Ok(())
    }

    pub fn unknown_mut(&mut self, id: &str) -> Option<&mut Unknown> {
        self.unknowns.get_mut(id)
    }

    /// Open a project: its evidence and unknowns become available.
    ///
    /// The newest stored records (by write time) are loaded into the ledger, up to
    /// [`MAX_LOADED_EVIDENCE`] records and a byte budget; the rest stay on disk and resolve by id.
    /// Every loaded record passes its integrity check; tampered or unreadable ones are skipped.
    pub fn open_project(&mut self, project: Project) -> Result<(), ToolError> {
        for u in project.load_unknowns()? {
            self.unknowns.insert(u.id.clone(), u);
        }
        let mut stored = project.evidence_files();
        // Newest first, so the budget keeps the most recent work.
        stored.sort_by(|a, b| b.modified.cmp(&a.modified).then_with(|| a.id.cmp(&b.id)));
        let mut loaded = Vec::new();
        let mut bytes = 0u64;
        for (i, f) in stored.iter().enumerate() {
            if loaded.len() >= MAX_LOADED_EVIDENCE || bytes.saturating_add(f.bytes) > MAX_LOADED_EVIDENCE_BYTES {
                self.unloaded_evidence = stored.len().saturating_sub(i);
                break;
            }
            match project.load_evidence(&f.id) {
                Ok(ev) => {
                    bytes = bytes.saturating_add(f.bytes);
                    loaded.push(ev);
                }
                Err(e) => log::warn!("skipping project evidence {}: {}", f.id, e.message),
            }
        }
        // Oldest first into the ledger so `ledger()` (newest first) matches write order.
        for ev in loaded.into_iter().rev() {
            if !self.ledger.contains_key(&ev.id) {
                self.order.push(ev.id.clone());
            }
            self.ledger.insert(ev.id.clone(), ev);
        }
        self.project = Some(project);
        Ok(())
    }
}
