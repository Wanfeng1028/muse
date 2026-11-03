//! A workspace is one thing the person is making: a folder under their projects directory that
//! holds what we learned about the target and what we built from it.
//!
//! ```text
//! <projects>/<slug>/
//!   craft.json           the manifest (request, target, status, history)
//!   investigation.cany/  evidence, memory and journal (a regular project)
//!   capture/             what we recorded from the target (screenshots, blueprint)
//!   reference/           pictures of the original the person added (the look to match)
//!   app/                 the generated project (its own git repository)
//!   checks/              comparisons of the build against the target, one folder per round
//!   inbox/               questions and approvals waiting for the person
//!   build-activity.log   what the runs did, line by line (with .old.log, the one before it)
//! ```
//!
//! A project can also start in a folder the person picks ([`Workspace::create_at`]). When it
//! already has their files, they're either the app itself (`app_in_root`: the builder edits them in
//! place and the folders above sit beside them) or material to start from, with the app in app/.

use crate::inbox::now_ms;
use crate::project::write_atomic;
use crate::versioned::{self, upgrade};
use craft_anything_evidence::{ErrorCode, ToolError};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::path::{Path, PathBuf};

pub const MANIFEST: &str = "craft.json";

/// Folders a copy of a project leaves out: what a build makes again, which can be gigabytes.
const REBUILT: &[&str] = &["node_modules", "target", ".godot", "Library", "Temp", ".venv", "__pycache__", ".next", ".turbo"];
/// An `obj` directory is ambiguous: these neighbouring project files identify managed build output.
const MANAGED_PROJECTS: &[&str] = &["csproj", "fsproj", "vbproj"];
/// How deep a copy of a project's folders goes.
const COPY_DEPTH: usize = 64;

pub(crate) fn rebuilt(p: &Path) -> bool {
    let Some(name) = p.file_name().and_then(|n| n.to_str()) else { return false };
    if name != "obj" {
        return REBUILT.contains(&name) && p.is_dir();
    }
    if !p.is_dir() {
        return false;
    }
    // Runtime models commonly live in assets/obj. Without evidence that a folder is compiler
    // output, keep it; an unreadable or unusually large parent must not cause data to be omitted.
    p.parent().and_then(|parent| std::fs::read_dir(parent).ok()).is_some_and(|entries| {
        entries.take(4096).flatten().any(|entry| {
            entry.path().extension().and_then(|e| e.to_str()).is_some_and(|ext| MANAGED_PROJECTS.iter().any(|project| ext.eq_ignore_ascii_case(project)))
                && entry.file_type().is_ok_and(|kind| kind.is_file())
        })
    })
}

/// Copy a folder's files and folders (links are skipped), leaving out what `skip` says.
fn copy_tree(from: &Path, to: &Path, skip: &dyn Fn(&Path) -> bool, depth: usize) -> Result<(), ToolError> {
    if depth > COPY_DEPTH {
        return Err(ToolError::new(ErrorCode::OverLimit, format!("{} is nested more than {COPY_DEPTH} folders deep.", from.display())));
    }
    std::fs::create_dir_all(to).map_err(|e| ToolError::io(to.display(), e))?;
    for entry in std::fs::read_dir(from).map_err(|e| ToolError::io(from.display(), e))? {
        let entry = entry.map_err(|e| ToolError::io(from.display(), e))?;
        let (path, kind) = (entry.path(), entry.file_type().map_err(|e| ToolError::io(entry.path().display(), e))?);
        if skip(&path) || kind.is_symlink() {
            continue;
        }
        let dest = to.join(entry.file_name());
        if kind.is_dir() {
            copy_tree(&path, &dest, skip, depth + 1)?;
        } else if kind.is_file() {
            std::fs::copy(&path, &dest).map_err(|e| ToolError::io(path.display(), e))?;
        }
    }
    Ok(())
}

/// The current `craft.json` format version. Bumping it means appending a step to [`MANIFEST_STEPS`].
pub const MANIFEST_VERSION: u32 = 2;

/// The steps that bring an older `craft.json` forward; step `i` goes from version `i` to `i + 1`.
const MANIFEST_STEPS: &[versioned::Step<Value>] = &[manifest_v0_to_v1, manifest_v1_to_v2];
const _: () = assert!(MANIFEST_STEPS.len() == MANIFEST_VERSION as usize, "one step per craft.json version");

/// Version 0 (no `version` field) has the same shape as version 1; only the number is new.
fn manifest_v0_to_v1(doc: &mut Value) -> Result<(), String> {
    if doc.is_object() { Ok(()) } else { Err("the manifest isn't a JSON object".into()) }
}

/// Version 2 adds where the app is (`app_in_root`) and the files a picked folder started with;
/// both default to a project made the usual way. The number is new so an older build, which would
/// look for the app in app/, opens such a project read-only instead of saving over it.
fn manifest_v1_to_v2(doc: &mut Value) -> Result<(), String> {
    if doc.is_object() { Ok(()) } else { Err("the manifest isn't a JSON object".into()) }
}

/// Read a `craft.json` document of any version this build understands. A newer manifest is read
/// as far as its fields are known and keeps its version, so [`Workspace::save`] refuses to write it.
pub fn read_manifest(bytes: &[u8]) -> Result<Manifest, ToolError> {
    let mut doc: Value = serde_json::from_slice(bytes).map_err(|e| ToolError::invalid(format!("it isn't valid JSON: {e}")))?;
    let found = match doc.get("version") {
        None | Some(Value::Null) => 0,
        Some(v) => v.as_u64().and_then(|n| u32::try_from(n).ok()).ok_or_else(|| ToolError::invalid(format!("its version ({v}) isn't a whole number")))?,
    };
    if found > MANIFEST_VERSION {
        return serde_json::from_value(doc).map_err(|e| {
            ToolError::unsupported(format!(
                "This project was made by a newer Craft Anything (craft.json version {found}; this one reads up to {MANIFEST_VERSION}) and can't be read: {e}"
            ))
            .with_remediation("Update Craft Anything to open it.")
        });
    }
    let reached = upgrade(&mut doc, found, 0, MANIFEST_STEPS).map_err(|e| ToolError::invalid(format!("it couldn't be brought up to date: {e}")))?;
    if let Some(obj) = doc.as_object_mut() {
        obj.insert("version".into(), Value::from(reached));
    }
    serde_json::from_value(doc).map_err(|e| ToolError::invalid(e.to_string()))
}

/// The JSON Schema of `craft.json` as published in `docs/schemas/craft.schema.json`.
pub fn manifest_schema() -> String {
    let schema = schemars::generate::SchemaSettings::draft2020_12().into_generator().into_root_schema_for::<Manifest>();
    serde_json::to_string_pretty(&schema).map(|s| s + "\n").unwrap_or_default()
}

/// What is being rebuilt.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, JsonSchema)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum TargetRef {
    Website {
        url: String,
    },
    /// An app, game, executable, archive or folder on this computer.
    Local {
        path: PathBuf,
    },
    /// Only a description.
    None,
}

impl TargetRef {
    /// A URL becomes a website; an existing path a local target; anything else nothing.
    pub fn parse(s: &str) -> TargetRef {
        let t = s.trim().trim_matches('"');
        if t.starts_with("http://") || t.starts_with("https://") {
            return TargetRef::Website { url: t.to_string() };
        }
        let p = PathBuf::from(t);
        if !t.is_empty() && p.is_absolute() && p.exists() { TargetRef::Local { path: p } } else { TargetRef::None }
    }

    pub fn label(&self) -> String {
        match self {
            TargetRef::Website { url } => url.clone(),
            TargetRef::Local { path } => path.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_else(|| path.display().to_string()),
            TargetRef::None => String::new(),
        }
    }
}

/// Where a workspace is in its life.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Status {
    #[default]
    New,
    Inspecting,
    Building,
    Checking,
    /// Waiting for the person (a question, an approval, or after an error).
    NeedsYou,
    Ready,
    Stopped,
}

impl Status {
    pub fn label(self) -> &'static str {
        match self {
            Status::New => "New",
            Status::Inspecting => "Studying",
            Status::Building => "Building",
            Status::Checking => "Checking",
            Status::NeedsYou => "Needs you",
            Status::Ready => "Ready",
            Status::Stopped => "Paused",
        }
    }
}

/// The four stages the person sees.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Step {
    Study,
    Build,
    Check,
    Done,
}

impl Step {
    pub const ALL: [Step; 4] = [Step::Study, Step::Build, Step::Check, Step::Done];

    pub fn label(self) -> &'static str {
        match self {
            Step::Study => "Study",
            Step::Build => "Build",
            Step::Check => "Check",
            Step::Done => "Ready",
        }
    }
}

/// One check of the build: whether it works and, when it could be compared with the original,
/// how alike it is. Decisions read `passed` and `similarity`, never `note` (which is for people).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
#[serde(from = "CheckRecord")]
pub struct CheckResult {
    pub round: u32,
    /// Which check ran: [`CheckResult::BUILD`], [`CheckResult::WEB_VISUAL`], or another check's id.
    pub check: String,
    /// The build works: it built, or it was served and compared.
    pub passed: bool,
    /// 0..=100, higher is closer. `None` when the build wasn't compared.
    pub similarity: Option<f64>,
    pub note: String,
    /// Files the check made, relative to the project folder (screenshots…).
    pub artifacts: Vec<PathBuf>,
    pub at_ms: u64,
    /// This check's own bar for `similarity` (e.g. likeness to the person's pictures), instead of
    /// the run's.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub good_enough: Option<f64>,
    /// Each page compared, for a website with several (`similarity` is their mean).
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub pages: Vec<PageLikeness>,
    /// What the check meant to compare but couldn't ("/about at 768 px couldn't be pictured").
    /// Missing evidence never counts as alike, so a check with any isn't good enough.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub unknowns: Vec<String>,
    /// The things the build must do, each judged on its own; one that fails keeps the check from
    /// being good enough, however alike the rest looks.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub claims: Vec<Claim>,
}

/// One thing a build must do, checked on its own ("The start page doesn't scroll sideways at
/// 390 px").
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
pub struct Claim {
    pub title: String,
    pub passed: bool,
    /// Why it failed, in plain words (empty when it passed).
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub detail: String,
}

impl Claim {
    pub fn new(title: impl Into<String>, passed: bool, detail: impl Into<String>) -> Claim {
        Claim { title: title.into(), passed, detail: if passed { String::new() } else { detail.into() } }
    }
}

/// How alike one page of a website and its rebuild are.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
pub struct PageLikeness {
    /// What people see: "start page" or the page's path ("/about").
    pub name: String,
    /// Its screenshots' folder inside `capture/` and `checks/round-N/`: "" for the start page,
    /// `routes/<slug>` for another.
    pub dir: String,
    /// 0..=100, as [`CheckResult::similarity`].
    pub similarity: f64,
}

impl CheckResult {
    /// The project's own build ran (cargo, npm, or the game engine's).
    pub const BUILD: &'static str = "build";
    /// The built site was served and its screenshots compared with the original's.
    pub const WEB_VISUAL: &'static str = "web-visual";

    pub fn new(check: &str, round: u32, passed: bool, note: impl Into<String>) -> CheckResult {
        CheckResult {
            round,
            check: check.into(),
            passed,
            similarity: None,
            note: note.into(),
            artifacts: Vec::new(),
            at_ms: crate::inbox::now_ms(),
            good_enough: None,
            pages: Vec::new(),
            unknowns: Vec::new(),
            claims: Vec::new(),
        }
    }

    /// Passed with nothing left unknown and every claim holding, and (when compared) at least as
    /// alike as its own bar, else `good_enough`.
    pub fn good(&self, good_enough: f64) -> bool {
        self.passed
            && self.unknowns.is_empty()
            && self.claims.iter().all(|c| c.passed)
            && self.similarity.is_none_or(|s| s >= self.good_enough.unwrap_or(good_enough))
    }

    /// The claims that don't hold yet.
    pub fn failed_claims(&self) -> impl Iterator<Item = &Claim> {
        self.claims.iter().filter(|c| !c.passed)
    }
}

/// A check as stored. Projects from before `check` and `passed` existed are read the way their
/// results were judged then: compared means it worked, else the note said "Build succeeded".
#[derive(Deserialize, JsonSchema)]
struct CheckRecord {
    round: u32,
    #[serde(default)]
    check: Option<String>,
    #[serde(default)]
    passed: Option<bool>,
    similarity: Option<f64>,
    note: String,
    #[serde(default)]
    artifacts: Vec<PathBuf>,
    at_ms: u64,
    #[serde(default)]
    good_enough: Option<f64>,
    #[serde(default)]
    pages: Vec<PageLikeness>,
    #[serde(default)]
    unknowns: Vec<String>,
    #[serde(default)]
    claims: Vec<Claim>,
}

impl From<CheckRecord> for CheckResult {
    fn from(r: CheckRecord) -> CheckResult {
        let compared = r.similarity.is_some();
        CheckResult {
            round: r.round,
            check: r.check.unwrap_or_else(|| (if compared { CheckResult::WEB_VISUAL } else { CheckResult::BUILD }).into()),
            passed: r.passed.unwrap_or(compared || r.note.starts_with("Build succeeded")),
            similarity: r.similarity,
            note: r.note,
            artifacts: r.artifacts,
            at_ms: r.at_ms,
            good_enough: r.good_enough,
            pages: r.pages,
            unknowns: r.unknowns,
            claims: r.claims,
        }
    }
}

/// A workspace's manifest (`craft.json`): what the person asked for, the target, status and history.
/// Its schema is published in `docs/schemas/craft.schema.json` (`cargo xtask schemas`).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
pub struct Manifest {
    /// The craft.json format version. Missing means 0: written before files had versions.
    #[serde(default)]
    pub version: u32,
    pub name: String,
    /// What the person asked for, in their words.
    pub request: String,
    pub target: TargetRef,
    /// The stack chosen for the build ("React + TypeScript (Vite)", "Rust + Bevy"…).
    #[serde(default)]
    pub stack: String,
    #[serde(default)]
    pub status: Status,
    /// One line on what's happening or what went wrong.
    #[serde(default)]
    pub note: String,
    pub created_ms: u64,
    pub updated_ms: u64,
    #[serde(default)]
    pub checks: Vec<CheckResult>,
    /// The coding agent's session, so a later request continues the same conversation.
    #[serde(default)]
    pub agent_session: Option<String>,
    /// The coding agent that saved `agent_session` (`claude-code`, `codex`…); none: saved before
    /// this was kept.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub agent_session_by: Option<String>,
    /// Kinds of agent action the person allowed for this workspace ("bash:npm", "web_fetch"…).
    #[serde(default)]
    pub allowed_actions: Vec<String>,
    /// The agent's last plain-words summary, shown when the project is reopened.
    #[serde(default)]
    pub last_reply: String,
    /// What generated pictures and 3D models may cost before the person is asked (US dollars).
    #[serde(default = "default_asset_budget")]
    pub asset_budget_usd: f64,
    /// The person lets the builder generate pictures and 3D models (paid, so off until they turn
    /// it on; it also needs a key for an asset provider).
    #[serde(default)]
    pub generate_assets: bool,
    /// The app is the project folder itself: the person's own files, which the builder edits in
    /// place, instead of app/.
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub app_in_root: bool,
    /// The names in the person's folder when the project started there (at most
    /// [`START_FILES_SHOWN`]), so the builder knows what to start from.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub start_files: Vec<String>,
    /// The AI the person chose to build this project (a backend's name); none: the default
    /// builder. The person's, like the budget.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub builder: Option<String>,
    /// What the builder's questions get in this project; none: the app's default
    /// (`Settings::questions`). The person's, like the budget.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub questions: Option<Questions>,
    /// The builder finished its turn and the run's checks haven't reported on it yet, so a run
    /// that picks this up only needs to check: nothing is left to build.
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub awaiting_check: bool,
}

impl Manifest {
    fn new(name: &str, request: &str, target: TargetRef) -> Manifest {
        let now = now_ms();
        Manifest {
            version: MANIFEST_VERSION,
            name: name.trim().to_string(),
            request: request.trim().to_string(),
            target,
            stack: String::new(),
            status: Status::New,
            note: String::new(),
            created_ms: now,
            updated_ms: now,
            checks: Vec::new(),
            agent_session: None,
            agent_session_by: None,
            allowed_actions: Vec::new(),
            last_reply: String::new(),
            asset_budget_usd: ASSET_BUDGET_USD,
            generate_assets: false,
            app_in_root: false,
            start_files: Vec::new(),
            builder: None,
            questions: None,
            awaiting_check: false,
        }
    }

    /// The saved session, if `agent` (`claude-code`, `codex`…) saved it: another agent can't
    /// continue it (#469). One saved before the agent was kept counts.
    pub fn agent_session_for(&self, agent: &str) -> Option<&str> {
        self.agent_session.as_deref().filter(|_| self.agent_session_by.as_deref().is_none_or(|a| a == agent))
    }

    /// Take the fields the person owns from `other` (what's on disk).
    fn take_person_fields(&mut self, other: &Manifest) {
        self.asset_budget_usd = other.asset_budget_usd;
        self.generate_assets = other.generate_assets;
        self.allowed_actions = other.allowed_actions.clone();
        self.builder.clone_from(&other.builder);
        self.questions = other.questions;
        self.name.clone_from(&other.name);
    }
}

/// The starting budget for generated assets.
pub const ASSET_BUDGET_USD: f64 = 5.0;

fn default_asset_budget() -> f64 {
    ASSET_BUDGET_USD
}

/// One generated asset (a picture or a 3D model) and what it cost.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct AssetRecord {
    /// Where it was saved, relative to app/.
    pub file: String,
    /// "image" or "model".
    pub kind: String,
    /// What it was made from (the description, or the picture it was made from).
    pub prompt: String,
    pub cost_usd: f64,
    pub at_ms: u64,
}

/// The list of generated assets, in the workspace folder.
const ASSETS: &str = "assets.json";

/// What a project's builds have taken and used, every run together (`usage.json`). The rebuild
/// run is its only writer; everything else reads it.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
#[serde(default)]
pub struct ProjectUsage {
    /// The usage.json format version ([`USAGE_VERSION`]).
    pub version: u32,
    /// How long the builds have worked, in milliseconds.
    pub work_ms: u64,
    pub input_tokens: u64,
    pub output_tokens: u64,
    /// Everything reported, in US dollars: what API keys were charged plus coding agents' own
    /// estimates at API prices.
    pub cost_usd: f64,
    /// The part of `cost_usd` charged to an API key. The rest is an estimate, which is all files
    /// from before this field held.
    pub api_billed_usd: f64,
    /// Some of it came with a price; agents that report none leave tokens only.
    pub priced: bool,
}

/// What a project's runs did, line by line; the run is its only writer.
pub const ACTIVITY_LOG: &str = "build-activity.log";
/// The log before it, set aside when it grew long.
pub const ACTIVITY_LOG_OLD: &str = "build-activity.old.log";

/// Where [`ProjectUsage`] is kept in the project folder.
pub const USAGE_FILE: &str = "usage.json";
pub const USAGE_VERSION: u32 = 1;

impl ProjectUsage {
    /// The saved usage of the project at `root`; nothing yet (or unreadable) is all zeros.
    pub fn load(root: &Path) -> ProjectUsage {
        std::fs::read(root.join(USAGE_FILE)).ok().and_then(|b| serde_json::from_slice(&b).ok()).unwrap_or_default()
    }

    /// Change the saved usage (the run's job). A file from a newer Craft Anything is left alone.
    pub fn update(root: &Path, f: impl FnOnce(&mut ProjectUsage)) -> Result<(), ToolError> {
        let mut u = ProjectUsage::load(root);
        if u.version > USAGE_VERSION {
            return Err(ToolError::unsupported(format!("{USAGE_FILE} was written by a newer Craft Anything, so it isn't changed.")));
        }
        f(&mut u);
        u.version = USAGE_VERSION;
        let json = serde_json::to_vec_pretty(&u).map_err(|e| ToolError::internal(e.to_string()))?;
        write_atomic(&root.join(USAGE_FILE), &json)
    }

    /// One agent turn's tokens and reported cost (a price that isn't a sensible number is skipped).
    /// `estimate`: the cost is the agent's own guess at API prices, not a key's charge.
    pub fn add_turn(&mut self, input: u64, output: u64, cost_usd: Option<f64>, estimate: bool) {
        self.input_tokens = self.input_tokens.saturating_add(input);
        self.output_tokens = self.output_tokens.saturating_add(output);
        if let Some(c) = cost_usd.filter(|c| c.is_finite() && *c >= 0.0) {
            self.cost_usd += c;
            if !estimate {
                self.api_billed_usd += c;
            }
            self.priced = true;
        }
    }

    /// The part of the cost that is a coding agent's estimate rather than a key's charge.
    pub fn estimated_usd(&self) -> f64 {
        (self.cost_usd - self.api_billed_usd).max(0.0)
    }

    pub fn tokens(&self) -> u64 {
        self.input_tokens.saturating_add(self.output_tokens)
    }

    pub fn used_anything(&self) -> bool {
        self.tokens() > 0 || self.priced
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct Workspace {
    pub root: PathBuf,
    pub manifest: Manifest,
}

/// A folder-name slug: lower-case words joined by dashes, at most 40 characters.
pub fn slug(s: &str) -> String {
    let mut out = String::new();
    for c in s.chars() {
        if c.is_ascii_alphanumeric() {
            out.push(c.to_ascii_lowercase());
        } else if !out.ends_with('-') && !out.is_empty() {
            out.push('-');
        }
        if out.len() >= 40 {
            break;
        }
    }
    let out = out.trim_matches('-').to_string();
    if out.is_empty() { "project".into() } else { out }
}

/// A short name from a request and target: the site's host, the file's stem, or the first words.
pub fn suggest_name(request: &str, target: &TargetRef) -> String {
    match target {
        TargetRef::Website { url } => {
            let host = url.split("://").nth(1).unwrap_or(url).split(['/', '?', '#', ':']).next().unwrap_or_default();
            host.trim_start_matches("www.").to_string()
        }
        TargetRef::Local { path } => path.file_stem().map(|s| s.to_string_lossy().into_owned()).unwrap_or_default(),
        TargetRef::None => request.split_whitespace().take(5).collect::<Vec<_>>().join(" "),
    }
}

impl Workspace {
    /// Create a new workspace folder under `projects_dir` (a fresh, unique folder).
    pub fn create(projects_dir: &Path, name: &str, request: &str, target: TargetRef) -> Result<Workspace, ToolError> {
        std::fs::create_dir_all(projects_dir).map_err(|e| ToolError::io(projects_dir.display(), e))?;
        let base = slug(name);
        let mut root = projects_dir.join(&base);
        let mut n = 2;
        // create_dir (not _all) fails if the folder exists, so two creators never share one.
        while let Err(e) = std::fs::create_dir(&root) {
            if e.kind() != std::io::ErrorKind::AlreadyExists || n > 999 {
                return Err(ToolError::io(root.display(), e));
            }
            root = projects_dir.join(format!("{base}-{n}"));
            n += 1;
        }
        let ws = Workspace { root, manifest: Manifest::new(name, request, target) };
        ws.save()?;
        Ok(ws)
    }

    /// Rename the project (its name, not its folder). The name is the person's: a run saving the
    /// project meanwhile keeps it.
    pub fn rename(&mut self, name: &str) -> Result<(), ToolError> {
        let name = name.trim().to_string();
        if name.is_empty() {
            return Err(ToolError::invalid("A project needs a name."));
        }
        self.set_person(|m| m.name = name)
    }

    /// A copy of the project beside it, named `name`, to try something else from where this one
    /// is: what was built, the pictures of the original and the study, not the conversation,
    /// questions or usage. An app edited in place is copied into the copy's app/. What a build
    /// makes again (dependencies, compiler output) is left out.
    pub fn duplicate(&self, name: &str) -> Result<Workspace, ToolError> {
        let parent = self.root.parent().ok_or_else(|| ToolError::invalid(format!("{} has no parent folder to copy it into.", self.root.display())))?;
        let m = &self.manifest;
        let mut copy = Workspace::create(parent, name, &m.request, m.target.clone())?;
        let in_place = m.app_in_root;
        let app = self.app_dir();
        if app.is_dir() {
            copy_tree(&app, &copy.app_dir(), &|p| rebuilt(p) || (in_place && self.is_own_record(p)), 0)?;
        }
        for dir in ["reference", "capture"] {
            let from = self.root.join(dir);
            if from.is_dir() {
                copy_tree(&from, &copy.root.join(dir), &rebuilt, 0)?;
            }
        }
        copy.manifest.stack.clone_from(&m.stack);
        copy.manifest.checks.clone_from(&m.checks);
        copy.manifest.last_reply.clone_from(&m.last_reply);
        // Ready stays ready; anything else can carry on (with a new conversation).
        copy.manifest.status = if m.status == Status::Ready { Status::Ready } else { Status::Stopped };
        copy.save()?;
        let (budget, generate, builder, allowed, questions) =
            (m.asset_budget_usd, m.generate_assets, m.builder.clone(), m.allowed_actions.clone(), m.questions);
        copy.set_person(|c| {
            c.asset_budget_usd = budget;
            c.generate_assets = generate;
            c.builder = builder;
            c.allowed_actions = allowed;
            c.questions = questions;
        })?;
        Ok(copy)
    }

    /// Delete the project: everything Craft Anything made in its folder (its records, checks and
    /// what was built in app/). The person's own files stay: an app edited in place, and the
    /// files a project started from. A folder left empty is removed. This can't be undone.
    pub fn delete(self) -> Result<(), ToolError> {
        if !self.root.join(MANIFEST).is_file() {
            return Err(ToolError::invalid(format!("{} isn't a project folder.", self.root.display())));
        }
        let gone = |p: &Path| -> Result<(), ToolError> {
            let r = if p.is_dir() { std::fs::remove_dir_all(p) } else { std::fs::remove_file(p) };
            match r {
                Err(e) if e.kind() != std::io::ErrorKind::NotFound => Err(ToolError::io(p.display(), e)),
                _ => Ok(()),
            }
        };
        if !self.manifest.app_in_root {
            gone(&self.app_dir())?;
        }
        // craft.json last: a delete that stops part-way leaves a project that can be deleted again.
        for name in OWN_NAMES.iter().filter(|n| **n != MANIFEST) {
            gone(&self.root.join(name))?;
        }
        gone(&self.root.join(MANIFEST))?;
        if std::fs::read_dir(&self.root).is_ok_and(|mut d| d.next().is_none()) {
            let _ = std::fs::remove_dir(&self.root);
        }
        Ok(())
    }

    /// Start a project in `folder` itself, a folder the person picked. A missing or empty folder
    /// is used as it is. One that has their files needs `existing` to say what those files are:
    /// the app, edited in place, or material to start from, with the app built in app/ beside
    /// them. A folder that's already a project, or that has something named like a file Craft
    /// Anything keeps there, is refused, so nothing of theirs is ever replaced.
    pub fn create_at(folder: &Path, name: &str, request: &str, target: TargetRef, existing: Option<ExistingFiles>) -> Result<Workspace, ToolError> {
        let mut manifest = Manifest::new(name, request, target);
        match folder_state(folder)? {
            FolderState::Empty => std::fs::create_dir_all(folder).map_err(|e| ToolError::io(folder.display(), e))?,
            FolderState::Project => {
                return Err(ToolError::invalid(format!("{} is already a project.", folder.display()))
                    .with_remediation("Open it to keep working on it, or pick another folder for a new one."));
            }
            FolderState::HasFiles { names, .. } => {
                let Some(existing) = existing else {
                    return Err(ToolError::invalid(format!("{} already has files.", folder.display())).with_remediation(
                        "Say what they are: the app itself, to edit in place (existing: edit), or material to start from, with the app built in app/ beside them (existing: start_from).",
                    ));
                };
                let clash = clashes(folder, existing);
                if !clash.is_empty() {
                    return Err(ToolError::invalid(format!(
                        "{} already has {}, which Craft Anything would keep its own files in.",
                        folder.display(),
                        clash.join(", ")
                    ))
                    .with_remediation("Pick another folder, or move those out of it first; Craft Anything never replaces your files."));
                }
                manifest.app_in_root = existing == ExistingFiles::Edit;
                manifest.start_files = names;
            }
        }
        let ws = Workspace { root: folder.to_path_buf(), manifest };
        ws.save()?;
        Ok(ws)
    }

    pub fn open(root: &Path) -> Result<Workspace, ToolError> {
        let path = root.join(MANIFEST);
        let bytes = std::fs::read(&path).map_err(|e| ToolError::io(path.display(), e))?;
        let manifest = read_manifest(&bytes)
            .map_err(|e| if e.code == ErrorCode::NotSupported { e } else { ToolError::invalid(format!("{} is unreadable: {}", path.display(), e.message)) })?;
        Ok(Workspace { root: root.to_path_buf(), manifest })
    }

    /// Made by a newer Craft Anything: it can be looked at but not changed (saving is refused, so
    /// fields this build doesn't know are never lost).
    pub fn is_read_only(&self) -> bool {
        self.manifest.version > MANIFEST_VERSION
    }

    /// Re-read the manifest from disk (another process may have changed it).
    pub fn reload(&mut self) -> Result<(), ToolError> {
        *self = Workspace::open(&self.root)?;
        Ok(())
    }

    /// Save the manifest. The fields the person owns (see [`Workspace::set_person`]) are kept as
    /// they are on disk, so a writer holding an older copy (a run that started before the person
    /// raised the budget) can't undo their change.
    pub fn save(&self) -> Result<(), ToolError> {
        let mut m = self.manifest.clone();
        if let Ok(disk) = Workspace::open(&self.root) {
            m.take_person_fields(&disk.manifest);
        }
        self.write_manifest(&m)
    }

    /// Change the fields the person owns (the asset budget, whether assets are generated, the
    /// actions always allowed): start from what's on disk, apply `f` and save. This is the only
    /// way they change.
    pub fn set_person(&mut self, f: impl FnOnce(&mut Manifest)) -> Result<(), ToolError> {
        if let Ok(disk) = Workspace::open(&self.root) {
            self.manifest.take_person_fields(&disk.manifest);
        }
        f(&mut self.manifest);
        self.write_manifest(&self.manifest)
    }

    fn write_manifest(&self, m: &Manifest) -> Result<(), ToolError> {
        if self.is_read_only() {
            return Err(ToolError::unsupported(format!(
                "{} was made by a newer Craft Anything (craft.json version {}), so this one doesn't change it.",
                self.manifest.name, self.manifest.version
            ))
            .with_remediation("Update Craft Anything to keep working on this project. Nothing was written."));
        }
        let bytes = serde_json::to_vec_pretty(m).map_err(|e| ToolError::internal(e.to_string()))?;
        write_atomic(&self.root.join(MANIFEST), &bytes)
    }

    /// Set the status and note, and save.
    pub fn set_status(&mut self, status: Status, note: impl Into<String>) -> Result<(), ToolError> {
        self.manifest.status = status;
        self.manifest.note = note.into();
        self.manifest.updated_ms = now_ms();
        self.save()
    }

    pub fn investigation_dir(&self) -> PathBuf {
        self.root.join("investigation.cany")
    }
    pub fn capture_dir(&self) -> PathBuf {
        self.root.join("capture")
    }
    /// The app: app/, or the project folder itself when the person's files are edited in place.
    pub fn app_dir(&self) -> PathBuf {
        if self.manifest.app_in_root { self.root.clone() } else { self.root.join("app") }
    }
    /// Where the app is, in words for messages: "app/", or "the project folder" (#174).
    pub fn app_place(&self) -> &'static str {
        if self.manifest.app_in_root { "the project folder" } else { "app/" }
    }

    /// One of Craft Anything's own records in this project (the manifest, the feed, the inbox,
    /// the person's pictures…), which the builder never changes, even when the app is the
    /// project folder itself. checks/ isn't one: the builder keeps its notes there.
    pub fn is_own_record(&self, p: &Path) -> bool {
        OWN_NAMES.iter().filter(|n| **n != "checks").any(|n| inside(&self.root.join(n), p))
    }
    /// Separate from capture/, which a website study replaces.
    pub fn reference_dir(&self) -> PathBuf {
        self.root.join("reference")
    }

    /// The person's pictures of the original, in the order they were added.
    pub fn references(&self) -> Vec<PathBuf> {
        pictures_in(&self.reference_dir())
    }

    /// Copy pictures of the original into reference/ as picture-N.ext. Returns how many were
    /// added; files that aren't PNG, JPEG, WebP or GIF, or are over 20 MB, are skipped.
    pub fn add_references(&self, files: &[PathBuf]) -> Result<usize, ToolError> {
        copy_pictures(&self.reference_dir(), files).map(|v| v.len())
    }

    /// Every generated asset so far, oldest first.
    pub fn assets(&self) -> Vec<AssetRecord> {
        std::fs::read(self.root.join(ASSETS)).ok().and_then(|b| serde_json::from_slice(&b).ok()).unwrap_or_default()
    }

    /// What the builds have taken and used so far.
    pub fn usage(&self) -> ProjectUsage {
        ProjectUsage::load(&self.root)
    }

    /// What generated assets have cost so far.
    pub fn assets_spent(&self) -> f64 {
        // A fold from 0.0: an empty `sum()` of floats is -0.0, which prints as "$-0.00".
        self.assets().iter().fold(0.0, |spent, a| spent + a.cost_usd)
    }

    /// Add a generated asset to the list.
    pub fn record_asset(&self, rec: AssetRecord) -> Result<(), ToolError> {
        let mut all = self.assets();
        all.push(rec);
        let json = serde_json::to_vec_pretty(&all).map_err(|e| ToolError::internal(e.to_string()))?;
        write_atomic(&self.root.join(ASSETS), &json)
    }

    /// Pictures attached to messages (what the person wants changed), kept apart from the
    /// pictures of the original.
    pub fn attachments_dir(&self) -> PathBuf {
        self.root.join("attachments")
    }

    /// Copy a message's pictures into attachments/. Returns where each one went.
    pub fn add_attachments(&self, files: &[PathBuf]) -> Result<Vec<PathBuf>, ToolError> {
        copy_pictures(&self.attachments_dir(), files)
    }
    pub fn checks_dir(&self) -> PathBuf {
        self.root.join("checks")
    }
    /// The builder's sheet of how the rebuild plays (`crate::mechanics`).
    pub fn mechanics_path(&self) -> PathBuf {
        self.app_dir().join(crate::mechanics::MECHANICS)
    }
    pub fn inbox_dir(&self) -> PathBuf {
        self.root.join("inbox")
    }
    /// A builder has worked on this project and its conversation was kept, so a later run carries
    /// it on instead of starting over.
    pub fn builder_started(&self) -> bool {
        self.manifest.agent_session.is_some() || self.transcript_path().is_file()
    }

    /// The API builder's conversation, kept so a follow-up continues it (`ai::context`).
    pub fn transcript_path(&self) -> PathBuf {
        self.root.join("transcript.json")
    }

    /// A copy of the coding agent's own session (Claude Code's), kept after every turn so the
    /// conversation travels with the project folder to another computer.
    pub fn agent_session_path(&self) -> PathBuf {
        self.root.join(AGENT_SESSION_FILE)
    }

    /// Every workspace under `projects_dir`, most recently updated first. Folders without a
    /// readable manifest are skipped.
    pub fn list(projects_dir: &Path) -> Vec<Workspace> {
        Workspace::list_in(&[projects_dir.to_path_buf()])
    }

    /// Every workspace in `locations`, most recently updated first, each once. A location is a
    /// folder of projects or a project itself (one started in a folder the person picked).
    pub fn list_in(locations: &[PathBuf]) -> Vec<Workspace> {
        let mut roots: Vec<PathBuf> = Vec::new();
        for loc in locations {
            if loc.join(MANIFEST).is_file() {
                roots.push(loc.clone());
            } else if let Ok(rd) = std::fs::read_dir(loc) {
                roots.extend(rd.flatten().map(|e| e.path()).filter(|p| p.join(MANIFEST).is_file()));
            }
        }
        // The same project reached twice (a project listed, and its parent folder listed too).
        let mut seen = std::collections::HashSet::new();
        roots.retain(|r| seen.insert(std::fs::canonicalize(r).unwrap_or_else(|_| r.clone())));
        let mut v: Vec<Workspace> = roots.iter().filter_map(|r| Workspace::open(r).ok()).collect();
        v.sort_by_key(|w| std::cmp::Reverse(w.manifest.updated_ms));
        v
    }
}

/// The coding agent's session, copied into the project ([`Workspace::agent_session_path`]).
pub const AGENT_SESSION_FILE: &str = "agent-session.jsonl";

/// The names Craft Anything keeps in a project folder beside app/. A folder the person picks
/// mustn't already have any of them.
pub const OWN_NAMES: &[&str] = &[
    MANIFEST,
    crate::feed::FEED_FILE,
    crate::questions::QUESTIONS_FILE,
    USAGE_FILE,
    ACTIVITY_LOG,
    ACTIVITY_LOG_OLD,
    ASSETS,
    "transcript.json",
    "extract-transcript.json",
    AGENT_SESSION_FILE,
    "inbox",
    "checks",
    "capture",
    "reference",
    "attachments",
    "investigation.cany",
    crate::pins::PINNED,
];

/// `p` is `dir` or inside it (case-insensitive on Windows, where paths are).
pub fn inside(dir: &Path, p: &Path) -> bool {
    if cfg!(windows) {
        let (d, p) = (dir.to_string_lossy().to_lowercase().replace('\\', "/"), p.to_string_lossy().to_lowercase().replace('\\', "/"));
        p == d || p.starts_with(&format!("{}/", d.trim_end_matches('/')))
    } else {
        p.starts_with(dir)
    }
}

/// How many of a picked folder's names are kept for the builder.
pub const START_FILES_SHOWN: usize = 40;

/// What a folder picked for a new project already holds.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, JsonSchema)]
#[serde(rename_all = "snake_case", tag = "state")]
pub enum FolderState {
    /// Missing or empty: the project starts there as usual.
    Empty,
    /// Already a Craft Anything project.
    Project,
    /// The person's files: the first names (sorted, at most [`START_FILES_SHOWN`]) and how many.
    HasFiles { names: Vec<String>, count: usize },
}

/// What the builder's questions (`core_person_ask`) get.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum Questions {
    /// Shown to the person as a card; the builder waits for the answer.
    Ask,
    /// Answered at once with "decide yourself and say what you chose".
    Decide,
}

/// What the files already in a picked folder are to a new project.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum ExistingFiles {
    /// The app itself: the builder edits them in place.
    Edit,
    /// Material to start from: the builder reads them and builds the app in app/ beside them.
    StartFrom,
}

/// What's already in `folder` under a name Craft Anything would keep its own files in (app/ too
/// when the app goes beside the person's files). A project can start there only when it's empty.
pub fn clashes(folder: &Path, existing: ExistingFiles) -> Vec<&'static str> {
    OWN_NAMES.iter().copied().chain((existing == ExistingFiles::StartFrom).then_some("app")).filter(|n| folder.join(n).exists()).collect()
}

/// What `folder` holds, for starting a project there.
pub fn folder_state(folder: &Path) -> Result<FolderState, ToolError> {
    if folder.join(MANIFEST).is_file() {
        return Ok(FolderState::Project);
    }
    let rd = match std::fs::read_dir(folder) {
        Ok(rd) => rd,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(FolderState::Empty),
        Err(e) => return Err(ToolError::io(folder.display(), e)),
    };
    let mut names: Vec<String> = rd.flatten().map(|e| e.file_name().to_string_lossy().into_owned()).collect();
    if names.is_empty() {
        return Ok(FolderState::Empty);
    }
    names.sort();
    let count = names.len();
    names.truncate(START_FILES_SHOWN);
    Ok(FolderState::HasFiles { names, count })
}

/// Picture types the builder agent can open and look at.
pub fn is_picture(p: &Path) -> bool {
    p.extension().and_then(|e| e.to_str()).is_some_and(|e| ["png", "jpg", "jpeg", "webp", "gif"].contains(&e.to_ascii_lowercase().as_str()))
}

/// The pictures in `dir`, in the order they were added.
fn pictures_in(dir: &Path) -> Vec<PathBuf> {
    let mut v: Vec<PathBuf> = std::fs::read_dir(dir).into_iter().flatten().flatten().map(|e| e.path()).filter(|p| p.is_file() && is_picture(p)).collect();
    v.sort_by_key(|p| picture_number(p));
    v
}

/// Copy pictures into `dir` as picture-N.ext, numbering on from what's there. Files that aren't
/// PNG, JPEG, WebP or GIF, or are over 20 MB, are skipped.
fn copy_pictures(dir: &Path, files: &[PathBuf]) -> Result<Vec<PathBuf>, ToolError> {
    const MAX: u64 = 20 * 1024 * 1024;
    std::fs::create_dir_all(dir).map_err(|e| ToolError::io(dir.display(), e))?;
    let mut next = pictures_in(dir).iter().map(|p| picture_number(p)).max().unwrap_or(0);
    let mut added = Vec::new();
    for f in files {
        if !is_picture(f) || f.metadata().map_or(true, |m| m.len() > MAX) {
            continue;
        }
        next += 1;
        let ext = f.extension().and_then(|e| e.to_str()).unwrap_or("png").to_ascii_lowercase();
        let to = dir.join(format!("picture-{next}.{ext}"));
        std::fs::copy(f, &to).map_err(|e| ToolError::io(to.display(), e))?;
        added.push(to);
    }
    Ok(added)
}

/// N in `picture-N.ext` (0 for anything else), for ordering and numbering.
fn picture_number(p: &Path) -> u32 {
    p.file_stem().and_then(|s| s.to_str()).and_then(|s| s.strip_prefix("picture-")).and_then(|n| n.parse().ok()).unwrap_or(0)
}

/// The default projects folder: `Documents/Craft Anything`, else `~/Craft Anything`.
pub fn default_projects_dir() -> PathBuf {
    dirs::document_dir().or_else(dirs::home_dir).unwrap_or_else(|| PathBuf::from(".")).join("Craft Anything")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_projects_usage_adds_up_across_runs_and_a_newer_file_is_left_alone() {
        let dir = tempfile::tempdir().unwrap();
        assert_eq!(ProjectUsage::load(dir.path()), ProjectUsage::default(), "nothing yet");
        for cost in [Some(1.25), None, Some(f64::NAN), Some(2.0)] {
            ProjectUsage::update(dir.path(), |u| {
                u.work_ms += 1_000;
                u.add_turn(100, 10, cost, true);
            })
            .unwrap();
        }
        let u = ProjectUsage::load(dir.path());
        assert_eq!((u.version, u.work_ms, u.tokens(), u.cost_usd, u.priced), (USAGE_VERSION, 4_000, 440, 3.25, true));
        std::fs::write(dir.path().join(USAGE_FILE), r#"{"version": 99, "work_ms": 5}"#).unwrap();
        assert!(ProjectUsage::update(dir.path(), |u| u.work_ms = 0).is_err());
        assert_eq!(ProjectUsage::load(dir.path()).work_ms, 5, "read as far as it's known, never written over");
    }

    #[test]
    fn a_run_holding_an_old_copy_keeps_the_persons_changes() {
        let dir = tempfile::tempdir().unwrap();
        let mut run = Workspace::create(dir.path(), "game", "A snake game", TargetRef::None).unwrap();
        // While the run works, the person raises the budget, turns assets on and always allows npm.
        let mut person = Workspace::open(&run.root).unwrap();
        person
            .set_person(|m| {
                m.asset_budget_usd = 20.0;
                m.generate_assets = true;
                m.allowed_actions.push("bash:npm".into());
            })
            .unwrap();
        // The run saves its own progress from the copy it started with.
        run.manifest.status = Status::Building;
        run.manifest.note = "Building".into();
        run.save().unwrap();
        let disk = Workspace::open(&run.root).unwrap().manifest;
        assert_eq!((disk.asset_budget_usd, disk.generate_assets), (20.0, true));
        assert_eq!(disk.allowed_actions, ["bash:npm"]);
        assert_eq!((disk.status, disk.note.as_str()), (Status::Building, "Building"), "the run's own fields are saved");
        // A setter on the old copy starts from what's on disk too.
        run.set_person(|m| m.asset_budget_usd = 25.0).unwrap();
        let disk = Workspace::open(&run.root).unwrap().manifest;
        assert_eq!((disk.asset_budget_usd, disk.generate_assets), (25.0, true));
    }

    #[test]
    fn slugs_and_names() {
        assert_eq!(slug("  My Cool Site!! "), "my-cool-site");
        assert_eq!(slug("***"), "project");
        assert!(slug(&"a".repeat(100)).len() <= 40);
        assert_eq!(suggest_name("x", &TargetRef::Website { url: "https://www.example.com/a?b".into() }), "example.com");
        assert_eq!(suggest_name("Make a snake game in Rust please", &TargetRef::None), "Make a snake game in");
    }

    #[test]
    fn targets_parse() {
        assert_eq!(TargetRef::parse(" https://a.com "), TargetRef::Website { url: "https://a.com".into() });
        assert_eq!(TargetRef::parse("just words"), TargetRef::None);
        let dir = tempfile::tempdir().unwrap();
        assert_eq!(TargetRef::parse(&dir.path().display().to_string()), TargetRef::Local { path: dir.path().to_path_buf() });
    }

    #[test]
    fn pictures_of_the_original_are_copied_numbered_and_kept_in_order() {
        let dir = tempfile::tempdir().unwrap();
        let ws = Workspace::create(dir.path(), "Game", "Copy it", TargetRef::None).unwrap();
        let src = dir.path().join("src");
        std::fs::create_dir_all(&src).unwrap();
        for f in ["a.webp", "b.PNG", "notes.txt"] {
            std::fs::write(src.join(f), "x").unwrap();
        }
        assert_eq!(ws.add_references(&[src.join("a.webp"), src.join("notes.txt"), src.join("missing.png")]).unwrap(), 1);
        assert_eq!(ws.add_references(&[src.join("b.PNG")]).unwrap(), 1);
        let names: Vec<_> = ws.references().iter().map(|p| p.file_name().unwrap().to_string_lossy().into_owned()).collect();
        assert_eq!(names, ["picture-1.webp", "picture-2.png"]);
        // A message's pictures go to attachments/, numbered on their own.
        let got = ws.add_attachments(&[src.join("b.PNG"), src.join("notes.txt")]).unwrap();
        assert_eq!(got, vec![ws.attachments_dir().join("picture-1.png")]);
        assert_eq!(ws.references().len(), 2, "attachments aren't pictures of the original");
    }

    #[test]
    fn create_list_reload() {
        let dir = tempfile::tempdir().unwrap();
        let a = Workspace::create(dir.path(), "Example", "Clone it", TargetRef::Website { url: "https://example.com".into() }).unwrap();
        let mut b = Workspace::create(dir.path(), "Example", "Again", TargetRef::None).unwrap();
        assert_ne!(a.root, b.root, "same name gets a fresh folder");
        assert!(b.root.ends_with("example-2"));
        std::thread::sleep(std::time::Duration::from_millis(5));
        b.set_status(Status::Building, "Writing the page").unwrap();
        let all = Workspace::list(dir.path());
        assert_eq!(all.len(), 2);
        assert_eq!(all[0].root, b.root, "most recently updated first");
        let mut a2 = a.clone();
        a2.reload().unwrap();
        assert_eq!(a2.manifest.request, "Clone it");
        std::fs::create_dir(dir.path().join("junk")).unwrap();
        assert_eq!(Workspace::list(dir.path()).len(), 2, "folders without a manifest are skipped");
    }

    #[test]
    fn project_copies_keep_runtime_obj_folders() {
        let dir = tempfile::tempdir().unwrap();
        let ws = Workspace::create(dir.path(), "Models", "a model viewer", TargetRef::None).unwrap();
        let app = ws.app_dir();
        std::fs::create_dir_all(app.join("assets/obj")).unwrap();
        std::fs::write(app.join("assets/obj/hero.obj"), "v 0 0 0\n").unwrap();
        std::fs::create_dir_all(app.join("managed/obj")).unwrap();
        std::fs::write(app.join("managed/Viewer.csproj"), "<Project />").unwrap();
        std::fs::write(app.join("managed/obj/intermediate.bin"), [7; 256]).unwrap();
        let copy = ws.duplicate("Models copy").unwrap().app_dir();
        assert!(copy.join("assets/obj/hero.obj").is_file(), "a project copy keeps its runtime model");
        assert_eq!(std::fs::read_to_string(copy.join("assets/obj/hero.obj")).unwrap(), "v 0 0 0\n");
        assert!(copy.join("managed/Viewer.csproj").is_file());
        assert!(!copy.join("managed/obj").exists());
    }

    #[test]
    fn checks_from_older_projects_are_judged_as_they_were() {
        let old = |json: &str| serde_json::from_str::<CheckResult>(json).unwrap();
        let built = old(r#"{"round":1,"similarity":null,"note":"Build succeeded.","at_ms":5}"#);
        assert!(built.passed && built.check == CheckResult::BUILD && built.artifacts.is_empty());
        let failed = old(r#"{"round":2,"similarity":null,"note":"Build failed: error[E0308]","at_ms":5}"#);
        assert!(!failed.passed);
        let compared = old(r#"{"round":1,"similarity":71.0,"note":"1440 px: 71% alike","at_ms":5}"#);
        assert!(compared.passed && compared.check == CheckResult::WEB_VISUAL);
        // Written back with every field, and read the same.
        let again: CheckResult = serde_json::from_str(&serde_json::to_string(&compared).unwrap()).unwrap();
        assert_eq!(again, compared);
        assert!(compared.pages.is_empty() && !serde_json::to_string(&compared).unwrap().contains("pages"));
        let page = PageLikeness { name: "/about".into(), dir: "routes/about".into(), similarity: 80.0 };
        let multi = CheckResult { pages: vec![page], ..compared };
        let again: CheckResult = serde_json::from_str(&serde_json::to_string(&multi).unwrap()).unwrap();
        assert_eq!(again, multi, "each page's likeness is kept");
    }

    /// A craft.json as written before versions existed (and before checks were structured).
    const MANIFEST_V0: &str = r#"{
  "name": "Example",
  "request": "Clone it",
  "target": { "kind": "website", "url": "https://example.com" },
  "stack": "React + TypeScript (Vite)",
  "status": "ready",
  "note": "",
  "created_ms": 1700000000000,
  "updated_ms": 1700000005000,
  "checks": [ { "round": 1, "similarity": 71.0, "note": "1440 px: 71% alike", "at_ms": 1700000004000 } ],
  "agent_session": "abc",
  "allowed_actions": ["bash:npm"],
  "last_reply": "Done."
}"#;

    #[test]
    fn manifests_from_before_versions_open_and_are_saved_as_current() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(dir.path().join(MANIFEST), MANIFEST_V0).unwrap();
        let ws = Workspace::open(dir.path()).unwrap();
        assert_eq!(ws.manifest.version, MANIFEST_VERSION);
        assert_eq!(ws.manifest.status, Status::Ready);
        assert_eq!(ws.manifest.asset_budget_usd, ASSET_BUDGET_USD);
        assert!(!ws.manifest.generate_assets, "assets are generated only once the person turns it on");
        assert!(ws.manifest.checks[0].passed && !ws.is_read_only());
        ws.save().unwrap();
        let saved: Value = serde_json::from_slice(&std::fs::read(dir.path().join(MANIFEST)).unwrap()).unwrap();
        assert_eq!(saved["version"], MANIFEST_VERSION);
        assert_eq!(Workspace::open(dir.path()).unwrap().manifest, ws.manifest);
    }

    #[test]
    fn newer_manifests_open_read_only_and_are_never_overwritten() {
        let dir = tempfile::tempdir().unwrap();
        let newer = MANIFEST_V0.replacen('{', r#"{ "version": 99, "a_field_from_the_future": [1, 2],"#, 1);
        std::fs::write(dir.path().join(MANIFEST), &newer).unwrap();
        let mut ws = Workspace::open(dir.path()).unwrap();
        assert!(ws.is_read_only());
        assert_eq!(ws.manifest.name, "Example");
        let err = ws.set_status(Status::Building, "x").unwrap_err();
        assert_eq!(err.code, ErrorCode::NotSupported);
        assert!(err.message.contains("newer") && err.remediation.is_some());
        assert_eq!(std::fs::read_to_string(dir.path().join(MANIFEST)).unwrap(), newer, "the file is untouched");
        assert_eq!(Workspace::list(dir.path().parent().unwrap()).iter().filter(|w| w.root == dir.path()).count(), 1, "still listed");

        // A newer manifest whose shape this build can't read at all is refused, in plain words.
        std::fs::write(dir.path().join(MANIFEST), r#"{"version": 7, "name": {"parts": []}}"#).unwrap();
        let err = Workspace::open(dir.path()).unwrap_err();
        assert_eq!(err.code, ErrorCode::NotSupported);
        assert!(err.message.contains("newer Craft Anything") && err.remediation.is_some());
    }

    #[test]
    fn broken_versions_are_unreadable_not_crashes() {
        for bad in [r#"{"version": "one"}"#, r#"{"version": -1}"#, r#"{"version": 5000000000}"#, "[1, 2]", "", "{"] {
            assert!(read_manifest(bad.as_bytes()).is_err(), "{bad}");
        }
    }

    #[test]
    fn the_published_schema_is_current() {
        let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../docs/schemas/craft.schema.json");
        let published = std::fs::read_to_string(path).unwrap_or_default().replace("\r\n", "\n");
        assert!(published == manifest_schema(), "docs/schemas/craft.schema.json is stale: run `cargo xtask schemas`");
        let schema: Value = serde_json::from_str(&published).unwrap();
        assert!(schema["properties"]["version"].is_object() && schema["properties"]["checks"].is_object());
    }

    #[test]
    fn good_means_working_and_alike_enough() {
        let web = |s: f64| CheckResult { similarity: Some(s), ..CheckResult::new(CheckResult::WEB_VISUAL, 1, true, "") };
        assert!(web(92.0).good(90.0));
        assert!(!web(80.0).good(90.0));
        assert!(CheckResult::new(CheckResult::BUILD, 1, true, "Build succeeded.").good(90.0), "nothing to compare: working is enough");
        assert!(!CheckResult::new(CheckResult::BUILD, 1, false, "Build failed").good(0.0));
        // A check with its own bar (likeness to the person's pictures) uses it instead.
        let pics = CheckResult { similarity: Some(70.0), good_enough: Some(60.0), ..CheckResult::new("app-screenshot", 1, true, "") };
        assert!(pics.good(90.0), "70% clears its own 60% bar");
        assert!(!CheckResult { good_enough: Some(80.0), ..pics.clone() }.good(0.0));
        assert!(!CheckResult { unknowns: vec!["/about couldn't be pictured".into()], ..pics.clone() }.good(0.0), "missing evidence is never good enough");
        let held = Claim::new("No sideways scroll at 390 px", true, "it's 512 px wide");
        assert!(held.detail.is_empty(), "a claim that holds has nothing to explain");
        let broken = Claim::new("Every file loads", false, "/logo.png (404)");
        assert!(CheckResult { claims: vec![held.clone()], ..pics.clone() }.good(0.0));
        let c = CheckResult { claims: vec![held, broken], ..pics };
        assert!(!c.good(0.0), "a failed claim never rolls up into a pass");
        assert_eq!(c.failed_claims().map(|c| c.detail.as_str()).collect::<Vec<_>>(), ["/logo.png (404)"]);
    }

    #[test]
    fn a_project_starts_in_a_picked_folder_that_is_missing_or_empty() {
        let d = tempfile::tempdir().unwrap();
        for folder in [d.path().join("new"), d.path().join("empty")] {
            if folder.ends_with("empty") {
                std::fs::create_dir(&folder).unwrap();
            }
            assert_eq!(folder_state(&folder).unwrap(), FolderState::Empty);
            let ws = Workspace::create_at(&folder, "Notes", "A notes app", TargetRef::None, None).unwrap();
            assert_eq!(ws.root, folder, "the folder itself, not a new one inside it");
            assert_eq!(ws.app_dir(), folder.join("app"));
            assert!(ws.manifest.start_files.is_empty() && !ws.manifest.app_in_root);
            assert_eq!(folder_state(&folder).unwrap(), FolderState::Project);
            let again = Workspace::create_at(&folder, "Notes", "x", TargetRef::None, None).unwrap_err();
            assert!(again.message.contains("already a project"), "{}", again.message);
        }
    }

    #[test]
    fn a_folder_with_files_says_what_they_are_and_keeps_them() {
        let d = tempfile::tempdir().unwrap();
        let mine = |name: &str| {
            let f = d.path().join(name);
            std::fs::create_dir_all(f.join("src")).unwrap();
            std::fs::write(f.join("Cargo.toml"), "[package]").unwrap();
            std::fs::write(f.join("src/main.rs"), "fn main() {}").unwrap();
            f
        };
        let edit = mine("edit");
        assert_eq!(folder_state(&edit).unwrap(), FolderState::HasFiles { names: vec!["Cargo.toml".into(), "src".into()], count: 2 });
        let e = Workspace::create_at(&edit, "Mine", "Add tabs", TargetRef::None, None).unwrap_err();
        assert!(e.remediation.unwrap_or_default().contains("existing: edit"), "it says how to answer");
        assert!(!edit.join(MANIFEST).exists(), "nothing written until it's answered");

        let ws = Workspace::create_at(&edit, "Mine", "Add tabs", TargetRef::None, Some(ExistingFiles::Edit)).unwrap();
        assert!(ws.manifest.app_in_root);
        assert_eq!(ws.app_dir(), edit, "their files are the app");
        assert_eq!(ws.manifest.start_files, ["Cargo.toml", "src"]);
        assert_eq!(std::fs::read_to_string(edit.join("src/main.rs")).unwrap(), "fn main() {}", "their files are left as they were");
        let reopened = Workspace::open(&edit).unwrap();
        assert_eq!(reopened.app_dir(), edit, "it's saved");

        let start = mine("start");
        let ws = Workspace::create_at(&start, "Mine", "Add tabs", TargetRef::None, Some(ExistingFiles::StartFrom)).unwrap();
        assert!(!ws.manifest.app_in_root);
        assert_eq!(ws.app_dir(), start.join("app"), "the app goes beside them");
        assert_eq!(ws.manifest.start_files, ["Cargo.toml", "src"]);
    }

    #[test]
    fn a_folder_with_names_craft_anything_uses_is_refused() {
        let d = tempfile::tempdir().unwrap();
        let checks = d.path().join("checks-here");
        std::fs::create_dir_all(checks.join("checks")).unwrap();
        for how in [ExistingFiles::Edit, ExistingFiles::StartFrom] {
            assert_eq!(clashes(&checks, how), ["checks"]);
            let e = Workspace::create_at(&checks, "x", "x", TargetRef::None, Some(how)).unwrap_err();
            assert!(e.message.contains("checks"), "{}", e.message);
        }
        // Their own app/ is only in the way when the app would be built in app/.
        let app = d.path().join("app-here");
        std::fs::create_dir_all(app.join("app")).unwrap();
        assert_eq!(clashes(&app, ExistingFiles::StartFrom), ["app"]);
        assert!(clashes(&app, ExistingFiles::Edit).is_empty());
        assert!(Workspace::create_at(&app, "x", "x", TargetRef::None, Some(ExistingFiles::Edit)).is_ok());
        assert!(!checks.join(MANIFEST).exists());
    }

    #[test]
    fn projects_are_listed_from_every_location_once() {
        let d = tempfile::tempdir().unwrap();
        let (many, own) = (d.path().join("many"), d.path().join("elsewhere").join("mine"));
        let a = Workspace::create(&many, "Alpha", "x", TargetRef::None).unwrap();
        let b = Workspace::create(&many, "Beta", "x", TargetRef::None).unwrap();
        let c = Workspace::create_at(&own, "Mine", "x", TargetRef::None, None).unwrap();
        let roots = |locs: &[PathBuf]| {
            let mut v: Vec<PathBuf> = Workspace::list_in(locs).into_iter().map(|w| w.root).collect();
            v.sort();
            v
        };
        let mut all = vec![a.root.clone(), b.root.clone(), c.root.clone()];
        all.sort();
        // A folder of projects, a project itself, the same project again and a folder that's gone.
        assert_eq!(roots(&[many.clone(), own.clone(), a.root.clone(), d.path().join("gone")]), all);
        assert_eq!(roots(std::slice::from_ref(&many)), [a.root.clone(), b.root.clone()]);
        assert_eq!(Workspace::list(&many).len(), 2);
    }

    #[test]
    fn a_version_1_manifest_reads_as_a_usual_project_and_new_fields_are_saved_only_when_set() {
        let v1 = br#"{"version":1,"name":"Old","request":"x","target":{"kind":"none"},"created_ms":1,"updated_ms":1}"#;
        let m = read_manifest(v1).unwrap();
        assert_eq!(m.version, MANIFEST_VERSION, "brought forward");
        assert!(!m.app_in_root && m.start_files.is_empty());
        let d = tempfile::tempdir().unwrap();
        let ws = Workspace::create(d.path(), "New", "x", TargetRef::None).unwrap();
        let saved: Value = serde_json::from_slice(&std::fs::read(ws.root.join(MANIFEST)).unwrap()).unwrap();
        assert!(saved.get("app_in_root").is_none() && saved.get("start_files").is_none(), "a usual project's craft.json is unchanged");
    }

    #[test]
    fn craft_anythings_records_are_its_own_even_when_the_app_is_the_folder() {
        let d = tempfile::tempdir().unwrap();
        std::fs::write(d.path().join("index.html"), "<p>hi</p>").unwrap();
        let ws = Workspace::create_at(d.path(), "Site", "x", TargetRef::None, Some(ExistingFiles::Edit)).unwrap();
        for own in ["craft.json", "feed.json", "inbox/a.json", "reference/picture-1.png", "investigation.cany/x"] {
            assert!(ws.is_own_record(&ws.root.join(own)), "{own}");
        }
        for theirs in ["index.html", "src/main.rs", "checks/round-1/notes.md", "craft.json.bak"] {
            assert!(!ws.is_own_record(&ws.root.join(theirs)), "{theirs}");
        }
        if cfg!(windows) {
            assert!(ws.is_own_record(&ws.root.join("CRAFT.JSON")), "paths on Windows ignore case");
        }
    }

    /// #469: a saved session is only for the agent that saved it.
    #[test]
    fn a_session_is_only_for_the_agent_that_saved_it() {
        let mut m = Manifest::new("x", "A thing", TargetRef::None);
        assert_eq!(m.agent_session_for("codex"), None);
        m.agent_session = Some("s1".into());
        assert_eq!(m.agent_session_for("codex"), Some("s1"), "one saved before the agent was kept counts");
        m.agent_session_by = Some("claude-code".into());
        assert_eq!(m.agent_session_for("claude-code"), Some("s1"));
        assert_eq!(m.agent_session_for("codex"), None);
        let text = serde_json::to_string(&m).unwrap();
        assert_eq!(serde_json::from_str::<Manifest>(&text).unwrap().agent_session_by.as_deref(), Some("claude-code"));
    }

    /// A rename survives a stale save, a copy takes the build but not the conversation (nor its
    /// kept session), and a delete leaves the person's own files.
    #[test]
    fn a_project_is_renamed_duplicated_and_deleted_without_touching_the_persons_files() {
        let d = tempfile::tempdir().unwrap();
        let mut ws = Workspace::create(d.path(), "Snake", "A snake game", TargetRef::None).unwrap();
        std::fs::create_dir_all(ws.app_dir().join("src")).unwrap();
        std::fs::write(ws.app_dir().join("src/main.rs"), "fn main() {}").unwrap();
        std::fs::create_dir_all(ws.app_dir().join("target/debug")).unwrap();
        std::fs::write(ws.app_dir().join("target/debug/big.bin"), "x").unwrap();
        std::fs::create_dir_all(ws.reference_dir()).unwrap();
        std::fs::write(ws.reference_dir().join("picture-1.png"), "x").unwrap();
        ws.manifest.agent_session = Some("old".into());
        ws.save().unwrap();
        std::fs::write(ws.agent_session_path(), "{}\n").unwrap();

        ws.rename("  Snake II ").unwrap();
        assert_eq!(Workspace::open(&ws.root).unwrap().manifest.name, "Snake II");
        assert!(ws.rename(" ").is_err());
        // A run saving its own copy keeps the person's new name.
        let mut stale = ws.clone();
        stale.manifest.name = "Snake".into();
        stale.save().unwrap();
        assert_eq!(Workspace::open(&ws.root).unwrap().manifest.name, "Snake II");

        let copy = ws.duplicate("Snake III").unwrap();
        assert_ne!(copy.root, ws.root);
        assert_eq!(std::fs::read_to_string(copy.app_dir().join("src/main.rs")).unwrap(), "fn main() {}");
        assert!(copy.reference_dir().join("picture-1.png").is_file());
        assert!(!copy.app_dir().join("target").exists(), "compiler output is made again, not copied");
        assert!(copy.manifest.agent_session.is_none(), "a copy has its own conversation");
        assert!(!copy.agent_session_path().exists(), "and doesn't carry the original's");

        ws.delete().unwrap();
        assert!(!d.path().join("snake").exists(), "a project of its own goes with its folder");

        // An app edited in place: Craft Anything's records go, the person's files stay.
        let mine = d.path().join("mine");
        std::fs::create_dir_all(&mine).unwrap();
        std::fs::write(mine.join("index.html"), "<p>hi</p>").unwrap();
        let ws = Workspace::create_at(&mine, "Site", "x", TargetRef::None, Some(ExistingFiles::Edit)).unwrap();
        std::fs::create_dir_all(ws.inbox_dir()).unwrap();
        std::fs::write(ws.agent_session_path(), "{}\n").unwrap();
        let copy = ws.duplicate("Site copy").unwrap();
        assert!(copy.app_dir().join("index.html").is_file() && !copy.manifest.app_in_root, "the copy's app is in its app/");
        assert!(!copy.app_dir().join(MANIFEST).exists(), "without the original's records");
        ws.delete().unwrap();
        assert_eq!(std::fs::read_to_string(mine.join("index.html")).unwrap(), "<p>hi</p>");
        assert!(!mine.join(MANIFEST).exists() && !mine.join("inbox").exists() && !mine.join(AGENT_SESSION_FILE).exists());
    }
}
