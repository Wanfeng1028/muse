//! Plan what setup would change, apply it transactionally, and uninstall what we own.

use crate::clients::{Client, Format, Host, SERVER_NAME, clients, is_owned_entry};
use crate::config;
use crate::skill;
use craft_anything_evidence::{ErrorCode, ToolError};
use serde::Serialize;
use serde_json::Value;
use std::path::{Path, PathBuf};

/// What to set up.
#[derive(Debug, Clone, Default)]
pub struct PlanRequest {
    /// Client ids. Empty (and not `all_detected`) means "refresh the clients that already have our entry".
    pub clients: Vec<String>,
    pub all_detected: bool,
    /// Program and args to register, e.g. `["/usr/local/bin/craft-anything-cli", "mcp"]`.
    pub command: Vec<String>,
    /// Also install the skill into each selected client's skills folder.
    pub include_skill: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ActionKind {
    Create,
    Update,
    AlreadyCurrent,
    Invalid,
    Manual,
}

/// One config file and what will happen to it.
#[derive(Debug, Clone, Serialize)]
pub struct Action {
    pub client: String,
    pub display: String,
    pub path: PathBuf,
    pub action: ActionKind,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub backup: Option<PathBuf>,
    /// The lines that change (`-` old, `+` new), short.
    #[serde(skip_serializing_if = "String::is_empty")]
    pub preview: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub reason: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub remediation: Option<String>,
    /// File text when planned (to detect changes before apply) and the text to write.
    #[serde(skip)]
    pub(crate) old_text: Option<String>,
    #[serde(skip)]
    pub(crate) new_text: Option<String>,
    #[serde(skip)]
    pub(crate) client_def: Option<Client>,
}

/// Skill files for one skills folder.
#[derive(Debug, Clone, Serialize)]
pub struct SkillPlan {
    pub dir: PathBuf,
    pub for_clients: Vec<String>,
    pub files: Vec<skill::SkillFileAction>,
}

#[derive(Debug, Clone, Serialize)]
pub struct Plan {
    pub command: Vec<String>,
    pub actions: Vec<Action>,
    pub skills: Vec<SkillPlan>,
    /// True when any selected client's config is invalid: nothing will be written.
    pub blocked: bool,
    pub notes: Vec<String>,
}

impl Plan {
    /// Number of file writes this plan would make.
    pub fn change_count(&self) -> usize {
        self.actions.iter().filter(|a| matches!(a.action, ActionKind::Create | ActionKind::Update)).count()
            + self.skills.iter().flat_map(|s| &s.files).filter(|f| f.action != "already_current").count()
    }
}

pub fn backup_path(p: &Path) -> PathBuf {
    skill::backup_path(p)
}

/// The default registration: this machine's `craft-anything-cli` plus `mcp`.
pub fn default_command() -> Result<Vec<String>, ToolError> {
    let p = craft_anything_platform::self_cli_path().ok_or_else(|| {
        ToolError::new(ErrorCode::EngineMissing, "Couldn't find craft-anything-cli.")
            .with_remediation("Install Craft Anything (the CLI ships next to the app), or pass its path explicitly.")
    })?;
    Ok(vec![p.display().to_string(), "mcp".into()])
}

fn read_text(path: &Path) -> Result<Option<String>, String> {
    match std::fs::read(path) {
        Ok(b) => String::from_utf8(b).map(Some).map_err(|_| "the file is not valid UTF-8".to_string()),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(e) => Err(e.to_string()),
    }
}

fn preview(old: &str, new: &str) -> String {
    let o: Vec<&str> = old.lines().collect();
    let n: Vec<&str> = new.lines().collect();
    let prefix = o.iter().zip(&n).take_while(|(a, b)| a == b).count();
    let suffix = o.iter().rev().zip(n.iter().rev()).take_while(|(a, b)| a == b).count().min(o.len().saturating_sub(prefix)).min(n.len().saturating_sub(prefix));
    let mut out = String::new();
    for l in o.iter().skip(prefix).take(o.len().saturating_sub(prefix + suffix)).take(40) {
        out.push_str(&format!("- {l}\n"));
    }
    for l in n.iter().skip(prefix).take(n.len().saturating_sub(prefix + suffix)).take(40) {
        out.push_str(&format!("+ {l}\n"));
    }
    out
}

/// Inspect one client and decide what to do.
pub fn inspect_client(c: &Client, command: &[String]) -> Action {
    let mut a = Action {
        client: c.id.into(),
        display: c.display.into(),
        path: c.config.clone(),
        action: ActionKind::AlreadyCurrent,
        backup: None,
        preview: String::new(),
        reason: None,
        remediation: None,
        old_text: None,
        new_text: None,
        client_def: Some(c.clone()),
    };
    if c.format == Format::Manual {
        a.action = ActionKind::Manual;
        a.reason = Some("This app's configuration isn't edited automatically.".into());
        a.remediation = c.manual.map(str::to_string);
        return a;
    }
    let desired = c.desired_entry(command);
    let text = match read_text(&c.config) {
        Ok(t) => t,
        Err(e) => {
            a.action = ActionKind::Invalid;
            a.reason = Some(format!("Can't read {}: {e}", c.config.display()));
            a.remediation = Some("Check the file's permissions.".into());
            return a;
        }
    };
    // A missing file is created; only an existing empty one is invalid where empty is (#238).
    let base = text.clone().unwrap_or_else(|| if c.empty_is_invalid { "{}".into() } else { String::new() });
    let existing = match config::read_entry(c, &base) {
        Ok(e) => e,
        Err(e) => {
            a.action = ActionKind::Invalid;
            a.reason = Some(format!("{} can't be read as {:?}: {e}", c.config.display(), c.format));
            a.remediation = Some(format!("Fix or move {} (it was left untouched), then run setup again.", c.config.display()));
            return a;
        }
    };
    if existing.as_ref() == Some(&desired) && !config::is_disabled(c, &base) {
        a.old_text = text;
        return a;
    }
    if let Some(e) = &existing
        && !is_owned_entry(e)
    {
        a.reason = Some(format!("A different \"{SERVER_NAME}\" entry exists and will be replaced."));
    }
    match config::set_entry(c, &base, &desired) {
        Ok(new) => {
            a.preview = preview(text.as_deref().unwrap_or_default(), &new);
            a.action = if text.is_some() { ActionKind::Update } else { ActionKind::Create };
            a.backup = text.as_ref().map(|_| backup_path(&c.config));
            a.old_text = text;
            a.new_text = Some(new);
        }
        Err(e) => {
            a.action = ActionKind::Invalid;
            a.reason = Some(format!("Can't add our entry to {}: {e}", c.config.display()));
            a.remediation = Some("Add it by hand, or fix the file and run setup again.".into());
        }
    }
    a
}

/// Work out what setup would change. Nothing is written.
pub fn plan(host: &Host, req: &PlanRequest) -> Result<Plan, ToolError> {
    if req.command.is_empty() {
        return Err(ToolError::invalid("No command to register."));
    }
    let all = clients(host);
    let mut notes = Vec::new();
    let selected: Vec<&Client> = if !req.clients.is_empty() {
        let mut v = Vec::new();
        for id in &req.clients {
            match all.iter().find(|c| c.is(id)) {
                Some(c) => v.push(c),
                None => {
                    let ids: Vec<&str> = all.iter().map(|c| c.id).collect();
                    return Err(ToolError::invalid(format!("Unknown client {id}")).with_remediation(format!("Use one of: {}", ids.join(", "))));
                }
            }
        }
        v
    } else if req.all_detected {
        all.iter().filter(|c| c.detected()).collect()
    } else {
        let owned: Vec<&Client> = all
            .iter()
            .filter(|c| {
                c.format != Format::Manual
                    && read_text(&c.config).ok().flatten().and_then(|t| config::read_entry(c, &t).ok().flatten()).is_some_and(|e| is_owned_entry(&e))
            })
            .collect();
        if owned.is_empty() {
            notes.push("No app is connected yet. Choose apps with --client <id> or --all-detected.".into());
        }
        owned
    };
    let actions: Vec<Action> = selected.iter().map(|c| inspect_client(c, &req.command)).collect();
    let blocked = actions.iter().any(|a| a.action == ActionKind::Invalid);
    if blocked {
        notes.push("Some configuration files can't be read safely, so nothing will be changed. Fix them and run setup again.".into());
    }
    let mut skills: Vec<SkillPlan> = Vec::new();
    if req.include_skill {
        for c in selected.iter().filter(|c| c.format != Format::Manual) {
            match skills.iter_mut().find(|s| s.dir == c.skills_dir) {
                Some(s) => s.for_clients.push(c.id.into()),
                None => skills.push(SkillPlan { dir: c.skills_dir.clone(), for_clients: vec![c.id.into()], files: skill::plan(&c.skills_dir) }),
            }
        }
    }
    Ok(Plan { command: req.command.clone(), actions, skills, blocked, notes })
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Outcome {
    Configured,
    Removed,
    Unchanged,
    Skipped,
    Failed,
    RolledBack,
}

#[derive(Debug, Clone, Serialize)]
pub struct FileResult {
    pub client: String,
    pub path: PathBuf,
    pub outcome: Outcome,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub backup: Option<PathBuf>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ApplyReport {
    /// `configured`, `unchanged`, `blocked` or `failed`.
    pub status: &'static str,
    pub results: Vec<FileResult>,
    pub skill_files: Vec<PathBuf>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub skill_error: Option<String>,
    /// Apps to restart so they pick up the change.
    pub restart: Vec<String>,
}

type Writer<'a> = &'a dyn Fn(&Path, &[u8]) -> Result<(), ToolError>;

fn real_write(p: &Path, b: &[u8]) -> Result<(), ToolError> {
    craft_anything_platform::write_atomic_private(p, b)
}

/// Apply a plan. Config files are written one by one with a first-time backup, an atomic write and
/// a read-back check; if any step fails, every file changed by this call is put back.
pub fn apply(plan: &Plan) -> ApplyReport {
    apply_with(plan, &real_write)
}

pub(crate) fn apply_with(plan: &Plan, write: Writer<'_>) -> ApplyReport {
    let mut results = Vec::new();
    if plan.blocked {
        for a in &plan.actions {
            results.push(FileResult { client: a.client.clone(), path: a.path.clone(), outcome: Outcome::Skipped, backup: None, error: a.reason.clone() });
        }
        return ApplyReport { status: "blocked", results, skill_files: Vec::new(), skill_error: None, restart: Vec::new() };
    }
    let mut done: Vec<(usize, PathBuf, Option<String>)> = Vec::new();
    let mut failed = false;
    for a in &plan.actions {
        let (Some(new), Some(c)) = (&a.new_text, &a.client_def) else {
            let outcome = if a.action == ActionKind::AlreadyCurrent { Outcome::Unchanged } else { Outcome::Skipped };
            results.push(FileResult { client: a.client.clone(), path: a.path.clone(), outcome, backup: None, error: a.remediation.clone() });
            continue;
        };
        let r = write_one(a, c, new, write);
        if r.as_ref().err().is_none_or(|(_, written)| *written) {
            done.push((results.len(), a.path.clone(), a.old_text.clone()));
        }
        match r.map_err(|(e, _)| e) {
            Ok(()) => {
                results.push(FileResult { client: a.client.clone(), path: a.path.clone(), outcome: Outcome::Configured, backup: a.backup.clone(), error: None })
            }
            Err(e) => {
                results.push(FileResult {
                    client: a.client.clone(),
                    path: a.path.clone(),
                    outcome: Outcome::Failed,
                    backup: a.backup.clone(),
                    error: Some(e.message),
                });
                failed = true;
                break;
            }
        }
    }
    if failed {
        for (idx, path, old) in done.iter().rev() {
            let r = match old {
                Some(t) => craft_anything_platform::write_atomic(path, t.as_bytes()).map_err(|e| e.message),
                None => match std::fs::remove_file(path) {
                    Err(e) if e.kind() != std::io::ErrorKind::NotFound => Err(e.to_string()),
                    _ => Ok(()),
                },
            };
            if let Some(res) = results.get_mut(*idx) {
                match r {
                    Ok(()) => {
                        if res.outcome == Outcome::Configured {
                            res.outcome = Outcome::RolledBack;
                        }
                    }
                    Err(e) => {
                        res.error = Some(format!(
                            "{} Restoring it failed ({e}); restore it from {} by hand.",
                            res.error.clone().unwrap_or_default(),
                            backup_path(path).display()
                        ));
                    }
                }
            }
        }
        return ApplyReport { status: "failed", results, skill_files: Vec::new(), skill_error: None, restart: Vec::new() };
    }
    let mut skill_files = Vec::new();
    let mut skill_error = None;
    for s in &plan.skills {
        match skill::install(&s.dir) {
            Ok(mut w) => skill_files.append(&mut w),
            Err(e) => {
                skill_error = Some(e.message);
                break;
            }
        }
    }
    let restart: Vec<String> = results
        .iter()
        .filter(|r| r.outcome == Outcome::Configured)
        .map(|r| plan.actions.iter().find(|a| a.client == r.client).map(|a| a.display.clone()).unwrap_or_default())
        .collect();
    let status = if skill_error.is_some() {
        "failed"
    } else if restart.is_empty() && skill_files.is_empty() {
        "unchanged"
    } else {
        "configured"
    };
    ApplyReport { status, results, skill_files, skill_error, restart }
}

/// Write one file. On error, the flag says whether the file may have been changed.
fn write_one(a: &Action, c: &Client, new: &str, write: Writer<'_>) -> Result<(), (ToolError, bool)> {
    // The file must not have changed since the plan was made.
    let now = read_text(&a.path).map_err(|e| (ToolError::new(ErrorCode::FileError, e), false))?;
    if now != a.old_text {
        return Err((
            ToolError::new(ErrorCode::FileChanged, format!("{} changed after the plan was made.", a.path.display())).with_remediation("Run setup again."),
            false,
        ));
    }
    if now.is_some() {
        craft_anything_platform::backup_once(&a.path, &backup_path(&a.path)).map_err(|e| (e, false))?;
    }
    write(&a.path, new.as_bytes()).map_err(|e| (e, true))?;
    verify(c, &a.path, &a.client_desired()).map_err(|e| (e, true))
}

impl Action {
    fn client_desired(&self) -> Value {
        match (&self.client_def, &self.new_text) {
            (Some(c), Some(t)) => config::read_entry(c, t).ok().flatten().unwrap_or(Value::Null),
            _ => Value::Null,
        }
    }
}

/// Re-read `path` and check our entry equals `desired` and isn't disabled.
pub fn verify(c: &Client, path: &Path, desired: &Value) -> Result<(), ToolError> {
    let text = std::fs::read_to_string(path).map_err(|e| ToolError::io(path.display(), e))?;
    let got = config::read_entry(c, &text).map_err(|e| ToolError::new(ErrorCode::FileError, format!("{} no longer parses: {e}", path.display())))?;
    if got.as_ref() != Some(desired) || desired.is_null() || config::is_disabled(c, &text) {
        return Err(ToolError::new(ErrorCode::FileError, format!("{} did not read back with the expected entry.", path.display())));
    }
    Ok(())
}

#[derive(Debug, Clone, Serialize)]
pub struct UninstallReport {
    /// `removed`, `nothing_to_remove`, `blocked` or `partial`.
    pub status: &'static str,
    pub removed_entries: Vec<FileResult>,
    pub removed_skill_files: Vec<PathBuf>,
    /// Configs that stopped the uninstall (malformed or unreadable).
    pub blocking: Vec<Action>,
    pub kept: Vec<String>,
}

/// Remove our registrations and skill files, and nothing else. If any config can't be read
/// safely, nothing at all is removed.
pub fn uninstall(host: &Host) -> UninstallReport {
    let all = clients(host);
    let mut blocking = Vec::new();
    let mut targets: Vec<(&Client, String, String)> = Vec::new();
    for c in all.iter().filter(|c| c.format != Format::Manual) {
        let text = match read_text(&c.config) {
            Ok(Some(t)) => t,
            Ok(None) => continue,
            Err(e) => {
                let mut a = inspect_client(c, &[]);
                a.action = ActionKind::Invalid;
                a.reason = Some(e);
                blocking.push(a);
                continue;
            }
        };
        match config::read_entry(c, &text) {
            Err(_) => blocking.push(inspect_client(c, &[])),
            Ok(Some(e)) if is_owned_entry(&e) => match config::remove_entry(c, &text) {
                Ok(Some(new)) => targets.push((c, text, new)),
                _ => blocking.push(inspect_client(c, &[])),
            },
            Ok(_) => {}
        }
    }
    let kept = vec!["Projects, evidence and settings".into(), "Other MCP servers and unrelated skills".into(), "Analysis engines".into()];
    if !blocking.is_empty() {
        return UninstallReport { status: "blocked", removed_entries: Vec::new(), removed_skill_files: Vec::new(), blocking, kept };
    }
    let mut removed_entries = Vec::new();
    let mut partial = false;
    for (c, old, new) in targets {
        let backup = backup_path(&c.config);
        let r = craft_anything_platform::backup_once(&c.config, &backup)
            .and_then(|_| craft_anything_platform::write_atomic_private(&c.config, new.as_bytes()))
            .and_then(|_| {
                let t = std::fs::read_to_string(&c.config).map_err(|e| ToolError::io(c.config.display(), e))?;
                match config::read_entry(c, &t) {
                    Ok(None) => Ok(()),
                    _ => Err(ToolError::new(ErrorCode::FileError, "the entry is still there after removal")),
                }
            });
        let (outcome, error) = match r {
            Ok(()) => (Outcome::Removed, None),
            Err(e) => {
                partial = true;
                let restored = craft_anything_platform::write_atomic(&c.config, old.as_bytes()).is_ok();
                (Outcome::Failed, Some(if restored { e.message } else { format!("{} Restore {} by hand.", e.message, backup.display()) }))
            }
        };
        removed_entries.push(FileResult { client: c.id.into(), path: c.config.clone(), outcome, backup: Some(backup), error });
    }
    let mut dirs: Vec<PathBuf> = all.iter().map(|c| c.skills_dir.clone()).collect();
    dirs.push(host.shared_skills());
    dirs.sort();
    dirs.dedup();
    let removed_skill_files: Vec<PathBuf> = dirs.iter().flat_map(|d| skill::uninstall(d)).collect();
    let status = if partial {
        "partial"
    } else if removed_entries.is_empty() && removed_skill_files.is_empty() {
        "nothing_to_remove"
    } else {
        "removed"
    };
    UninstallReport { status, removed_entries, removed_skill_files, blocking, kept }
}
