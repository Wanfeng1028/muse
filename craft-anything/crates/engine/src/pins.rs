//! Pinned builds: a build of a project kept at hand, to open whatever the builder does next.
//!
//! ```text
//! <project>/pinned/
//!   <n>/pin.json       the pin (name, frozen or light, the round it was pinned at)
//!   <n>/app/           a pin's copy of the app: its files and the program, without what a
//!                      build makes again
//!   <n>/last-run.log   what it printed the last time it was opened
//!   play.log           the same for Play
//! ```
//!
//! A **frozen** pin (the default) runs its own copy, so a rebuild can't change or break it, and a
//! running copy never locks the files the builder replaces. A **light** pin copies the program
//! and the app's code the same way but hard-links its dependencies and media to the project's, so
//! those take no more space. A rebuild replaces or deletes files, which leaves the pin's as they
//! were; only a file rewritten in place changes in both. Programs a pin or Play started are kept
//! in [`Runs`], one at a time per folder unless another is asked for.

use crate::inbox::now_ms;
use crate::versioned;
use crate::workspace::{self, Workspace};
use craft_anything_evidence::{ErrorCode, ToolError};
use craft_anything_platform::sync::Mutex;
use craft_anything_platform::{Ended, Launch, Launched};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::PoisonError;
use std::time::Duration;

/// The folder in a project that holds its pins.
pub const PINNED: &str = "pinned";
pub const PIN_FILE: &str = "pin.json";
/// The current `pin.json` format version.
pub const PIN_VERSION: u32 = 2;
/// Version 2 remembers the program selected for an argument-free launch inside the copied app.
const PIN_STEPS: &[versioned::Step<Value>] = &[pin_v1_to_v2];

fn pin_v1_to_v2(doc: &mut Value) -> Result<(), String> {
    let object = doc.as_object_mut().ok_or_else(|| "a pin must be an object".to_string())?;
    object.insert("program".into(), Value::Null);
    Ok(())
}
const _: () = assert!(PIN_STEPS.len() as u32 + 1 == PIN_VERSION, "one step per pin.json version after the first");
/// A start that ends within this long is reported as having quit straight away.
pub const QUICK_EXIT: Duration = Duration::from_secs(2);
/// Most pins one project keeps.
const MAX_PINS: u32 = 999;
/// How much of the end of a run's log is read back.
const TAIL_BYTES: u64 = 8 * 1024;
const TAIL_LINES: usize = 20;
/// Inside a folder a copy leaves out, the folders where a start needs only the files beside its
/// program (a Rust build's `target/release/`); in any other (`node_modules` for Electron) it needs
/// the whole folder.
const PROGRAM_FILES_ONLY: &[&str] = &["target"];
/// Never copied into a pin.
const NEVER_COPIED: &[&str] = &[".git"];
/// What a compiler leaves beside a program that nothing needs to run it. Debug symbols alone were
/// 85% of a typical Rust pin (a 242 MB `.pdb` beside a 49 MB program).
const NOT_NEEDED_TO_RUN: &[&str] = &["pdb", "ilk", "exp", "lib", "d", "rlib", "rmeta"];
/// File kinds a program only reads, which a light pin shares with the project. What a program may
/// write to (a save, a database) isn't here: a pin writing to a shared file would change the
/// project's.
const SHARED_KINDS: &[&str] = &[
    "png", "jpg", "jpeg", "webp", "gif", "tga", "dds", "ktx", "ktx2", "exr", "hdr", "mp3", "ogg", "wav", "flac", "mp4", "webm", "mov", "glb", "gltf", "fbx",
    "obj", "ttf", "otf", "woff", "woff2", "pak", "pck",
];

/// How a pin keeps its build.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize, Deserialize, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub enum PinMode {
    /// Its own copy of the build, which nothing else changes (the default).
    #[default]
    Frozen,
    /// Its own program and code, sharing dependencies and media with the project.
    Light,
    /// The project's app where it is, as the latest build left it. No longer made (it only
    /// opened what Play opens); pins already saved this way still work.
    Live,
}

impl PinMode {
    /// Has a folder of its own to run from.
    pub fn keeps_copy(self) -> bool {
        self != PinMode::Live
    }
}

/// One pin (`pinned/<id>/pin.json`).
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, JsonSchema)]
pub struct Pin {
    pub version: u32,
    pub id: u32,
    pub name: String,
    pub mode: PinMode,
    pub created_ms: u64,
    /// The build round it was pinned at, when the project had checked one.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub round: Option<u32>,
    /// What its copy takes on disk.
    #[serde(default)]
    pub bytes: u64,
    /// What a light pin shares with the project.
    #[serde(default)]
    pub shared_bytes: u64,
    /// The selected program relative to the copied app, for a launch without arguments.
    /// Older pins and launches through an external runtime keep the existing discovery path.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub program: Option<PathBuf>,
}

impl Pin {
    pub fn dir(&self, ws: &Workspace) -> PathBuf {
        pin_dir(ws, self.id)
    }

    /// The folder its program runs from: its copy, or the project's app for a live pin.
    pub fn app_dir(&self, ws: &Workspace) -> PathBuf {
        match self.mode {
            PinMode::Frozen | PinMode::Light => self.dir(ws).join("app"),
            PinMode::Live => ws.app_dir(),
        }
    }

    pub fn log_path(&self, ws: &Workspace) -> PathBuf {
        self.dir(ws).join("last-run.log")
    }

    /// Resolve the recorded program within the copy; old pins retain their discovery behavior.
    pub(crate) fn launch(&self, ws: &Workspace, godot: Option<&Path>) -> Result<(PathBuf, Vec<String>), ToolError> {
        let app = self.app_dir(ws);
        if self.mode.keeps_copy()
            && let Some(relative) = &self.program
        {
            if relative.as_os_str().is_empty() || !relative.components().all(|part| matches!(part, std::path::Component::Normal(_))) {
                return Err(ToolError::invalid("The pin's recorded program must be a relative path inside its app."));
            }
            let program = app.join(relative);
            if !program.is_file() || !crate::outputs::is_program(&program) {
                return Err(ToolError::new(ErrorCode::NotFound, "The program recorded by this pin is missing or cannot be started.")
                    .with_remediation("Restore the pin's program or pin a working build again."));
            }
            let resolved = program.canonicalize().map_err(|e| ToolError::io(program.display(), e))?;
            let root = app.canonicalize().map_err(|e| ToolError::io(app.display(), e))?;
            if !resolved.starts_with(root) {
                return Err(ToolError::invalid("The pin's recorded program points outside its app."));
            }
            return Ok((program, Vec::new()));
        }
        crate::outputs::launch(&app, godot).ok_or_else(|| {
            ToolError::new(ErrorCode::NotFound, "There's nothing to start: no built program in this pin.")
                .with_remediation("Pin a working build or open the folder to look.")
        })
    }
}

fn pin_dir(ws: &Workspace, id: u32) -> PathBuf {
    ws.root.join(PINNED).join(id.to_string())
}

/// Where Play's output goes.
pub fn play_log(ws: &Workspace) -> PathBuf {
    ws.root.join(PINNED).join("play.log")
}

/// Read a `pin.json` of any version this build understands; a newer one is read as far as its
/// fields are known.
pub fn read_pin(bytes: &[u8]) -> Result<Pin, ToolError> {
    let mut doc: Value = serde_json::from_slice(bytes).map_err(|e| ToolError::invalid(format!("it isn't valid JSON: {e}")))?;
    let found = doc.get("version").and_then(Value::as_u64).and_then(|n| u32::try_from(n).ok()).unwrap_or(1);
    if found <= PIN_VERSION {
        let reached = versioned::upgrade(&mut doc, found, 1, PIN_STEPS).map_err(|e| ToolError::invalid(format!("it couldn't be brought up to date: {e}")))?;
        if let Some(obj) = doc.as_object_mut() {
            obj.insert("version".into(), Value::from(reached));
        }
    }
    serde_json::from_value(doc).map_err(|e| ToolError::invalid(e.to_string()))
}

fn save(ws: &Workspace, pin: &Pin) -> Result<(), ToolError> {
    let json = serde_json::to_vec_pretty(pin).map_err(|e| ToolError::internal(e.to_string()))?;
    crate::project::write_atomic(&pin.dir(ws).join(PIN_FILE), &json)
}

/// A project's pins, oldest first. Folders without a readable pin.json (a copy still being made,
/// or one that stopped part-way) are skipped.
pub fn list(ws: &Workspace) -> Vec<Pin> {
    let mut pins: Vec<Pin> = std::fs::read_dir(ws.root.join(PINNED))
        .into_iter()
        .flatten()
        .flatten()
        .filter(|e| e.file_name().to_str().is_some_and(|n| n.parse::<u32>().is_ok()))
        .filter_map(|e| std::fs::read(e.path().join(PIN_FILE)).ok())
        .filter_map(|b| read_pin(&b).ok())
        .collect();
    pins.sort_by_key(|p| p.id);
    pins
}

pub fn get(ws: &Workspace, id: u32) -> Result<Pin, ToolError> {
    list(ws)
        .into_iter()
        .find(|p| p.id == id)
        .ok_or_else(|| ToolError::new(ErrorCode::NotFound, format!("This project has no pin {id}.")).with_remediation("Use project_pins_list to see its pins."))
}

/// What a pin of the project's build would take.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default, Serialize)]
pub struct Size {
    /// A frozen copy.
    pub bytes: u64,
    pub files: u64,
    /// A light copy.
    pub light_bytes: u64,
}

/// One file of a pin's copy.
struct Planned {
    from: PathBuf,
    to: PathBuf,
    len: u64,
    /// A light pin may share it with the project.
    shared: bool,
}

/// What a copy of `app` keeps of the folders a copy normally leaves out, for its start.
enum Keep {
    Whole(PathBuf),
    FilesIn(PathBuf),
}

/// What a pin copies: the app without what a build makes again, the project's own records (an app
/// edited in place) or `.git`; plus what starting it needs from those folders.
struct Plan {
    app: PathBuf,
    keep: Vec<Keep>,
    /// The program's folder: what's in it is always copied, since a running program locks it.
    program_dir: Option<PathBuf>,
}

impl Plan {
    fn new(ws: &Workspace, program: &Path) -> Plan {
        let app = ws.app_dir();
        let mut keep = Vec::new();
        if let Ok(rel) = program.strip_prefix(&app)
            && let Some(first) = rel.components().next()
        {
            let top = app.join(first);
            let only_files = first.as_os_str().to_str().is_some_and(|n| PROGRAM_FILES_ONLY.contains(&n));
            match program.parent() {
                Some(dir) if only_files => keep.push(Keep::FilesIn(dir.to_path_buf())),
                _ if workspace::rebuilt(&top) => keep.push(Keep::Whole(top)),
                _ => {}
            }
        }
        // A Godot project runs from its imported resources.
        let imported = app.join(".godot");
        if app.join("project.godot").is_file() && imported.is_dir() {
            keep.push(Keep::Whole(imported));
        }
        Plan { app, keep, program_dir: program.parent().map(Path::to_path_buf) }
    }

    /// Every (file, where it goes under `to`) the copy makes, in order.
    fn files(&self, ws: &Workspace, to: &Path) -> Result<Vec<Planned>, ToolError> {
        let (mut own, mut dependencies) = (Vec::new(), Vec::new());
        let skip = |p: &Path| {
            workspace::rebuilt(p) || ws.is_own_record(p) || p.file_name().and_then(|n| n.to_str()).is_some_and(|n| NEVER_COPIED.contains(&n)) || stray_copy(p)
        };
        walk(&self.app, to, &skip, 0, &mut own)?;
        for k in &self.keep {
            let (from, whole) = match k {
                Keep::Whole(d) => (d, true),
                Keep::FilesIn(d) => (d, false),
            };
            let rel = from.strip_prefix(&self.app).map_err(|_| ToolError::internal("a kept folder isn't inside the app"))?;
            if whole {
                walk(
                    from,
                    &to.join(rel),
                    &|p| p.file_name().and_then(|n| n.to_str()).is_some_and(|n| NEVER_COPIED.contains(&n)) || stray_copy(p),
                    0,
                    &mut dependencies,
                )?;
            } else {
                for e in std::fs::read_dir(from).map_err(|e| ToolError::io(from.display(), e))?.flatten() {
                    if let Ok(m) = e.metadata()
                        && m.is_file()
                        && !compiler_leftover(&e.path())
                        && !stray_copy(&e.path())
                    {
                        own.push((e.path(), to.join(rel).join(e.file_name()), m.len()));
                    }
                }
            }
        }
        let beside_program = |p: &Path| p.parent() == self.program_dir.as_deref();
        let media = |p: &Path| p.extension().and_then(|e| e.to_str()).is_some_and(|e| SHARED_KINDS.contains(&e.to_ascii_lowercase().as_str()));
        let own = own.into_iter().map(|f| (f, true));
        let dependencies = dependencies.into_iter().map(|f| (f, false));
        Ok(own
            .chain(dependencies)
            .map(|((from, to, len), is_own)| {
                let shared = !beside_program(&from) && (!is_own || media(&from));
                Planned { from, to, len, shared }
            })
            .collect())
    }
}

fn compiler_leftover(p: &Path) -> bool {
    let kind = p.extension().and_then(|e| e.to_str()).is_some_and(|e| NOT_NEEDED_TO_RUN.contains(&e.to_ascii_lowercase().as_str()));
    kind || p.file_name().and_then(|n| n.to_str()).is_some_and(|n| n.starts_with(".cargo-"))
}

/// An old copy of a program, left behind when a build replaced one that was running
/// (`snake.running-144900.exe`): a pin copies the program, not each copy of it. It only counts as
/// one when the program it copies is still beside it, so a helper that happens to be named like
/// one stays.
fn stray_copy(p: &Path) -> bool {
    let Some(name) = p.file_name().and_then(|n| n.to_str()) else { return false };
    let Some((base, rest)) = name.rsplit_once(".running-") else { return false };
    let (digits, ext) = rest.split_once('.').map_or((rest, None), |(d, e)| (d, Some(e)));
    if base.is_empty() || digits.is_empty() || !digits.bytes().all(|b| b.is_ascii_digit()) {
        return false;
    }
    let original = match ext {
        Some(e) => format!("{base}.{e}"),
        None => base.to_string(),
    };
    let original = p.with_file_name(original);
    original.is_file() && crate::outputs::is_program(&original)
}

/// How deep a copy goes.
const WALK_DEPTH: usize = 64;

fn walk(from: &Path, to: &Path, skip: &dyn Fn(&Path) -> bool, depth: usize, out: &mut Vec<(PathBuf, PathBuf, u64)>) -> Result<(), ToolError> {
    if depth > WALK_DEPTH {
        return Err(ToolError::new(ErrorCode::OverLimit, format!("{} is nested more than {WALK_DEPTH} folders deep.", from.display())));
    }
    for entry in std::fs::read_dir(from).map_err(|e| ToolError::io(from.display(), e))? {
        let entry = entry.map_err(|e| ToolError::io(from.display(), e))?;
        let (path, kind) = (entry.path(), entry.file_type().map_err(|e| ToolError::io(entry.path().display(), e))?);
        if skip(&path) || kind.is_symlink() {
            continue;
        }
        let dest = to.join(entry.file_name());
        if kind.is_dir() {
            walk(&path, &dest, skip, depth + 1, out)?;
        } else if kind.is_file() {
            out.push((path, dest, entry.metadata().map(|m| m.len()).unwrap_or(0)));
        }
    }
    Ok(())
}

/// What there is to start in `app`: the program and its arguments (see `outputs::launch`). A
/// website isn't pinned yet.
fn start_of(app: &Path, godot: Option<&Path>) -> Result<(PathBuf, Vec<String>), ToolError> {
    if crate::outputs::site_dir(app).is_some() {
        return Err(ToolError::unsupported("This project made a website, and websites can't be pinned yet.").with_remediation("Use project_preview to see it."));
    }
    crate::outputs::launch(app, godot).ok_or_else(|| {
        ToolError::new(ErrorCode::NotFound, "There's nothing to pin yet: no built program in this project.")
            .with_remediation("Finish a build first (rebuild), then pin it.")
    })
}

/// What a pin of the project's current build would take on disk.
pub fn estimate(ws: &Workspace, godot: Option<&Path>) -> Result<Size, ToolError> {
    let (program, _) = start_of(&ws.app_dir(), godot)?;
    let files = Plan::new(ws, &program).files(ws, Path::new(""))?;
    let bytes = |only_copied: bool| files.iter().filter(|f| !(only_copied && f.shared)).fold(0u64, |n, f| n.saturating_add(f.len));
    Ok(Size { bytes: bytes(false), files: files.len() as u64, light_bytes: bytes(true) })
}

/// Pin the project's current build. `progress(done, total)` hears how far the copy is (bytes) and
/// stops it by returning false, which removes what was copied.
pub fn create(ws: &Workspace, mode: PinMode, name: Option<&str>, godot: Option<&Path>, progress: &mut dyn FnMut(u64, u64) -> bool) -> Result<Pin, ToolError> {
    if !mode.keeps_copy() {
        return Err(ToolError::invalid("Live pins aren't made any more: one only opened the latest build, as Play does.")
            .with_remediation("Pin it as frozen or light."));
    }
    let (program, args) = start_of(&ws.app_dir(), godot)?;
    let recorded_program = if args.is_empty() { program.strip_prefix(ws.app_dir()).ok().map(Path::to_path_buf) } else { None };
    let parent = ws.root.join(PINNED);
    std::fs::create_dir_all(&parent).map_err(|e| ToolError::io(parent.display(), e))?;
    let mut id = list(ws).iter().map(|p| p.id).max().unwrap_or(0).saturating_add(1);
    // create_dir (not _all) fails if the folder exists, so two pins never share one.
    let dir = loop {
        let d = parent.join(id.to_string());
        match std::fs::create_dir(&d) {
            Ok(()) => break d,
            Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists && id < MAX_PINS => id += 1,
            Err(e) => return Err(ToolError::io(d.display(), e)),
        }
    };
    let round = ws.manifest.checks.iter().map(|c| c.round).max();
    let project = ws.manifest.name.as_str();
    let name = match (name.map(str::trim).filter(|n| !n.is_empty()), round) {
        (Some(n), _) => n.to_string(),
        (None, Some(r)) => format!("{project} · round {r}"),
        (None, None) => format!("{project} · pin {id}"),
    };
    let mut pin = Pin { version: PIN_VERSION, id, name, mode, created_ms: now_ms(), round, bytes: 0, shared_bytes: 0, program: recorded_program };
    let made = (|| {
        (pin.bytes, pin.shared_bytes) = copy(ws, &program, &pin.app_dir(ws), mode, progress)?;
        pin.launch(ws, godot)?;
        save(ws, &pin)
    })();
    if let Err(e) = made {
        // Nothing half-made stays behind: no pin.json means no pin, and the copy goes.
        if let Err(rm) = std::fs::remove_dir_all(&dir) {
            log::warn!("a pin that wasn't finished couldn't be removed from {}: {rm}", dir.display());
        }
        return Err(e);
    }
    Ok(pin)
}

/// Make a pin's copy; what it took and what it shares. A file that can't be linked (a drive
/// without hard links, a file with as many as it can have) is copied.
fn copy(ws: &Workspace, program: &Path, to: &Path, mode: PinMode, progress: &mut dyn FnMut(u64, u64) -> bool) -> Result<(u64, u64), ToolError> {
    let files = Plan::new(ws, program).files(ws, to)?;
    let total = files.iter().fold(0u64, |n, f| n.saturating_add(f.len));
    let (mut done, mut shared) = (0u64, 0u64);
    for f in &files {
        if !progress(done, total) {
            return Err(ToolError::new(ErrorCode::Cancelled, "Pinning was stopped; nothing was kept."));
        }
        if let Some(d) = f.to.parent() {
            std::fs::create_dir_all(d).map_err(|e| ToolError::io(d.display(), e))?;
        }
        if mode == PinMode::Light && f.shared && std::fs::hard_link(&f.from, &f.to).is_ok() {
            shared = shared.saturating_add(f.len);
        } else {
            std::fs::copy(&f.from, &f.to).map_err(|e| {
                ToolError::io(f.from.display(), e)
                    .with_remediation("Check there's room on the drive for the copy, or pin it as a light copy, which takes less.")
            })?;
        }
        done = done.saturating_add(f.len);
    }
    progress(total, total);
    Ok((total.saturating_sub(shared), shared))
}

/// Give a pin a new name.
pub fn rename(ws: &Workspace, id: u32, name: &str) -> Result<Pin, ToolError> {
    let name = name.trim();
    if name.is_empty() {
        return Err(ToolError::invalid("A pin needs a name."));
    }
    let mut pin = get(ws, id)?;
    pin.name = name.to_string();
    save(ws, &pin)?;
    Ok(pin)
}

/// Remove a pin and its copy, with anything it saved there; what it shared stays with the project.
pub fn delete(ws: &Workspace, id: u32) -> Result<(), ToolError> {
    let pin = get(ws, id)?;
    let dir = pin.dir(ws);
    // pin.json first: a delete that stops part-way leaves no half-pin in the list.
    let file = dir.join(PIN_FILE);
    std::fs::remove_file(&file).map_err(|e| ToolError::io(file.display(), e))?;
    std::fs::remove_dir_all(&dir).map_err(|e| ToolError::io(dir.display(), e).with_remediation("Close what it opened, then remove it again."))
}

/// The last lines a run printed.
pub fn tail(log: &Path) -> String {
    use std::io::{Read, Seek, SeekFrom};
    let Ok(mut f) = std::fs::File::open(log) else { return String::new() };
    let len = f.metadata().map(|m| m.len()).unwrap_or(0);
    if f.seek(SeekFrom::Start(len.saturating_sub(TAIL_BYTES))).is_err() {
        return String::new();
    }
    let mut buf = Vec::new();
    if f.take(TAIL_BYTES).read_to_end(&mut buf).is_err() {
        return String::new();
    }
    let text = String::from_utf8_lossy(&buf);
    let lines: Vec<&str> = text.lines().filter(|l| !l.trim().is_empty()).collect();
    lines.iter().skip(lines.len().saturating_sub(TAIL_LINES)).copied().collect::<Vec<_>>().join("\n")
}

/// What opening something did.
#[derive(Debug, Clone)]
pub enum Opened {
    /// It was already running, and no other copy was asked for.
    AlreadyRunning(Launched),
    /// Started; `quit` when it ended within [`QUICK_EXIT`].
    Started { launched: Launched, quit: Option<Ended> },
}

/// Programs started from pins and Play in this session, by the folder they run from. Starts
/// after a restart aren't known (a pin then shows as not running).
#[derive(Debug, Default)]
pub struct Runs(Mutex<HashMap<String, Vec<Launched>>>);

/// One key per folder (case and slashes don't matter on Windows).
fn key(dir: &Path) -> String {
    let s = dir.to_string_lossy();
    if cfg!(windows) { s.to_lowercase().replace('\\', "/").trim_end_matches('/').to_string() } else { s.trim_end_matches('/').to_string() }
}

impl Runs {
    /// What's still running from `dir`.
    pub fn running(&self, dir: &Path) -> Vec<Launched> {
        let mut map = self.0.lock().unwrap_or_else(PoisonError::into_inner);
        let k = key(dir);
        let alive: Vec<Launched> = map.get(&k).into_iter().flatten().filter(|l| l.is_running()).cloned().collect();
        if alive.is_empty() {
            map.remove(&k);
        } else {
            map.insert(k, alive.clone());
        }
        alive
    }

    /// Start `launch` from `dir`, unless something already runs from there and `another` isn't
    /// asked for. Waits up to [`QUICK_EXIT`] to see whether it quits straight away.
    pub fn open(&self, dir: &Path, launch: Launch, another: bool) -> Result<Opened, ToolError> {
        let launched = {
            let mut map = self.0.lock().unwrap_or_else(PoisonError::into_inner);
            let list = map.entry(key(dir)).or_default();
            list.retain(Launched::is_running);
            if !another && let Some(first) = list.first() {
                return Ok(Opened::AlreadyRunning(first.clone()));
            }
            let launched = launch.start_watched()?;
            list.push(launched.clone());
            launched
        };
        let quit = launched.wait_timeout(QUICK_EXIT);
        Ok(Opened::Started { launched, quit })
    }

    /// Stop everything running from `dir`; how many were stopped.
    pub fn stop(&self, dir: &Path) -> usize {
        let list = self.0.lock().unwrap_or_else(PoisonError::into_inner).remove(&key(dir)).unwrap_or_default();
        list.iter().filter(|l| l.is_running()).filter(|l| l.stop()).count()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::workspace::{CheckResult, TargetRef};

    /// A project whose app is a Rust workspace with a built program, a dependency folder and a
    /// file the app keeps beside itself.
    fn built(dir: &Path) -> Workspace {
        let mut ws = Workspace::create(dir, "Snake", "a snake game", TargetRef::None).unwrap();
        ws.manifest.checks.push(CheckResult::new("build", 3, true, "Build succeeded."));
        ws.save().unwrap();
        let app = ws.app_dir();
        std::fs::create_dir_all(app.join("src")).unwrap();
        std::fs::write(app.join("Cargo.toml"), "[package]\nname = \"snake\"\n[dependencies]\neframe = \"0.1\"\n").unwrap();
        std::fs::write(app.join("src/main.rs"), "fn main() {}").unwrap();
        std::fs::create_dir_all(app.join("assets")).unwrap();
        std::fs::write(app.join("assets/level.txt"), "####").unwrap();
        let release = app.join("target/release");
        std::fs::create_dir_all(release.join("deps")).unwrap();
        std::fs::write(release.join(exe("snake")), b"program").unwrap();
        std::fs::write(release.join("deps/big.rlib"), vec![0u8; 4096]).unwrap();
        std::fs::write(release.join("snake.pdb"), vec![0u8; 4096]).unwrap();
        std::fs::write(release.join(".cargo-lock"), "").unwrap();
        std::fs::create_dir_all(app.join(".git")).unwrap();
        std::fs::write(app.join(".git/HEAD"), "ref").unwrap();
        mark_program(&release.join(exe("snake")));
        ws
    }

    fn exe(name: &str) -> String {
        if cfg!(windows) { format!("{name}.exe") } else { name.to_string() }
    }

    #[cfg(unix)]
    fn mark_program(p: &Path) {
        use std::os::unix::fs::PermissionsExt;
        std::fs::set_permissions(p, std::fs::Permissions::from_mode(0o755)).unwrap();
    }
    #[cfg(not(unix))]
    fn mark_program(_: &Path) {}

    #[test]
    fn recorded_program_paths_cannot_escape_the_pin() {
        let d = tempfile::tempdir().unwrap();
        let ws = built(d.path());
        let mut pin = create(&ws, PinMode::Frozen, None, None, &mut |_, _| true).unwrap();
        assert_eq!(pin.program, Some(PathBuf::from("target/release").join(exe("snake"))));
        for relative in [PathBuf::new(), PathBuf::from("../other"), d.path().join("outside")] {
            pin.program = Some(relative);
            assert_eq!(pin.launch(&ws, None).unwrap_err().code, ErrorCode::BadInput);
        }
    }

    #[test]
    fn a_frozen_pin_copies_the_app_and_its_program_but_not_what_a_build_makes() {
        let d = tempfile::tempdir().unwrap();
        let ws = built(d.path());
        let size = estimate(&ws, None).unwrap();
        let pin = create(&ws, PinMode::Frozen, None, None, &mut |_, _| true).unwrap();
        assert_eq!(pin.name, "Snake · round 3");
        assert_eq!(pin.bytes, size.bytes);
        let copy = pin.app_dir(&ws);
        assert!(copy.join("assets/level.txt").is_file());
        assert!(copy.join("target/release").join(exe("snake")).is_file(), "the program comes along");
        assert!(!copy.join("target/release/deps").exists(), "compiler output stays behind");
        assert!(!copy.join("target/release/snake.pdb").exists() && !copy.join("target/release/.cargo-lock").exists(), "and so do debug symbols");
        assert!(!copy.join(".git").exists());
        assert_eq!(crate::outputs::built_program(&copy), Some(copy.join("target/release").join(exe("snake"))));
        assert_eq!(list(&ws), vec![pin.clone()]);

        // The project's build changes; the pin doesn't.
        std::fs::write(ws.app_dir().join("assets/level.txt"), "....").unwrap();
        assert_eq!(std::fs::read_to_string(copy.join("assets/level.txt")).unwrap(), "####");

        // It isn't copied with the project, and goes with it.
        let dup = ws.duplicate("Snake 2").unwrap();
        assert!(!dup.root.join(PINNED).exists() && !dup.app_dir().join(PINNED).exists());
        ws.clone().delete().unwrap();
        assert!(!ws.root.join(PINNED).exists());
    }

    #[test]
    fn pins_keep_obj_models_and_leave_out_managed_compiler_intermediates() {
        const MODEL: &str = "o triangle\nv 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n";
        for mode in [PinMode::Frozen, PinMode::Light] {
            let d = tempfile::tempdir().unwrap();
            let ws = built(d.path());
            let app = ws.app_dir();
            for folder in ["assets/obj", "assets/models"] {
                std::fs::create_dir_all(app.join(folder)).unwrap();
                std::fs::write(app.join(folder).join("hero.obj"), MODEL).unwrap();
            }
            for extension in ["csproj", "fsproj", "vbproj"] {
                let project = app.join(extension);
                std::fs::create_dir_all(project.join("obj")).unwrap();
                std::fs::write(project.join(format!("Game.{extension}")), "<Project />").unwrap();
                std::fs::write(project.join("obj/intermediate.bin"), [7; 256]).unwrap();
            }
            let size = estimate(&ws, None).unwrap();
            let pin = create(&ws, mode, None, None, &mut |_, _| true).unwrap();
            let copy = pin.app_dir(&ws);
            for folder in ["assets/obj", "assets/models"] {
                assert!(copy.join(folder).join("hero.obj").is_file(), "{mode:?}: {folder} keeps its runtime model");
                assert_eq!(std::fs::read_to_string(copy.join(folder).join("hero.obj")).unwrap(), MODEL, "{mode:?}: {folder}");
            }
            for extension in ["csproj", "fsproj", "vbproj"] {
                assert!(copy.join(extension).join(format!("Game.{extension}")).is_file(), "the project source stays");
                assert!(!copy.join(extension).join("obj").exists(), "compiler intermediates stay behind");
            }
            assert!(!copy.join("target/release/deps").exists());
            assert_eq!(pin.bytes + pin.shared_bytes, size.bytes, "the estimate includes both models");
            if mode == PinMode::Light {
                assert_eq!(pin.shared_bytes, (2 * MODEL.len()) as u64, "both runtime models can be shared");
            } else {
                assert_eq!(pin.shared_bytes, 0);
            }
            std::fs::remove_file(app.join("assets/obj/hero.obj")).unwrap();
            assert_eq!(std::fs::read_to_string(copy.join("assets/obj/hero.obj")).unwrap(), MODEL, "the pin survives removal from the project");
        }
    }

    #[test]
    fn a_pin_leaves_out_old_copies_of_its_program_but_keeps_helpers() {
        let d = tempfile::tempdir().unwrap();
        let ws = built(d.path());
        let release = ws.app_dir().join("target/release");
        let before = estimate(&ws, None).unwrap();
        let program = |name: &str, body: &[u8]| {
            let p = release.join(exe(name));
            std::fs::write(&p, body).unwrap();
            mark_program(&p);
        };
        // What a build leaves when it replaces a program that was running, and two files that only
        // look like one: a helper with nothing beside it, and a copy whose program is gone.
        program("snake.running-144900", &[0u8; 4096]);
        program("snake-tool.running-1", b"helper");
        program("ghost.running-7", b"gone");
        let after = estimate(&ws, None).unwrap();
        assert_eq!(after.files, before.files + 2, "the old copy isn't counted, the two others are");
        assert_eq!(after.bytes, before.bytes + 6 + 4, "and its size isn't either");
        let pin = create(&ws, PinMode::Frozen, None, None, &mut |_, _| true).unwrap();
        assert_eq!(pin.bytes, after.bytes);
        let copy = pin.app_dir(&ws).join("target/release");
        assert!(copy.join(exe("snake")).is_file());
        assert!(!copy.join(exe("snake.running-144900")).exists(), "the old copy of the program is left out");
        assert!(copy.join(exe("snake-tool.running-1")).is_file(), "a helper with nothing it copies beside it stays");
        assert!(copy.join(exe("ghost.running-7")).is_file(), "a copy whose program is gone is all there is to run");
    }

    #[test]
    fn a_light_pin_shares_media_and_survives_a_rebuild_replacing_or_deleting_them() {
        let d = tempfile::tempdir().unwrap();
        let ws = built(d.path());
        let app = ws.app_dir();
        std::fs::write(app.join("assets/sky.PNG"), "old sky").unwrap();
        std::fs::write(app.join("assets/song.ogg"), "old song").unwrap();
        std::fs::write(app.join("assets/save.db"), "a save").unwrap();
        std::fs::write(app.join("target/release/icon.png"), "beside the program").unwrap();
        let size = estimate(&ws, None).unwrap();
        assert_eq!(size.bytes - size.light_bytes, 15, "the two media files, not the save or what's beside the program");
        let pin = create(&ws, PinMode::Light, Some("  Playable  "), None, &mut |_, _| true).unwrap();
        assert_eq!((pin.name.as_str(), pin.bytes, pin.shared_bytes), ("Playable", size.light_bytes, 15));
        let copy = pin.app_dir(&ws);
        assert_eq!(crate::outputs::built_program(&copy), Some(copy.join("target/release").join(exe("snake"))));
        assert_eq!(list(&ws), vec![pin.clone()]);

        // What a program can write to, its program and its code are its own.
        std::fs::write(app.join("assets/save.db"), "changed").unwrap();
        std::fs::write(app.join("assets/level.txt"), "....").unwrap();
        std::fs::write(app.join("target/release/icon.png"), "changed").unwrap();
        assert_eq!(std::fs::read_to_string(copy.join("assets/save.db")).unwrap(), "a save");
        assert_eq!(std::fs::read_to_string(copy.join("assets/level.txt")).unwrap(), "####");
        assert_eq!(std::fs::read_to_string(copy.join("target/release/icon.png")).unwrap(), "beside the program");

        // A rebuild replaces a file (writing beside it, then renaming) or deletes it.
        std::fs::write(app.join("assets/sky.new"), "new sky").unwrap();
        std::fs::rename(app.join("assets/sky.new"), app.join("assets/sky.PNG")).unwrap();
        std::fs::remove_file(app.join("assets/song.ogg")).unwrap();
        assert_eq!(std::fs::read_to_string(copy.join("assets/sky.PNG")).unwrap(), "old sky");
        assert_eq!(std::fs::read_to_string(copy.join("assets/song.ogg")).unwrap(), "old song");

        delete(&ws, pin.id).unwrap();
        assert!(!pin.dir(&ws).exists());
        assert_eq!(std::fs::read_to_string(app.join("assets/save.db")).unwrap(), "changed", "removing a pin leaves the project alone");
    }

    #[test]
    fn a_light_pin_shares_an_engines_imports_and_electrons_packages_but_copies_its_program() {
        let d = tempfile::tempdir().unwrap();
        let ws = Workspace::create(d.path(), "Hop", "a game", TargetRef::None).unwrap();
        let app = ws.app_dir();
        std::fs::create_dir_all(&app).unwrap();
        std::fs::write(app.join("project.godot"), "config").unwrap();
        std::fs::create_dir_all(app.join(".godot/imported")).unwrap();
        std::fs::write(app.join(".godot/imported/sky.ctex"), "imported").unwrap();
        let godot = d.path().join("godot.exe");
        let pin = create(&ws, PinMode::Light, None, Some(&godot), &mut |_, _| true).unwrap();
        assert_eq!((pin.bytes, pin.shared_bytes), (6, 8), "project.godot copied, the import shared");

        let ws = Workspace::create(d.path(), "Notes", "an app", TargetRef::None).unwrap();
        let app = ws.app_dir();
        std::fs::create_dir_all(&app).unwrap();
        std::fs::write(app.join("package.json"), r#"{"dependencies":{"electron":"1"}}"#).unwrap();
        let dist = app.join("node_modules/electron/dist");
        std::fs::create_dir_all(dist.join("resources")).unwrap();
        std::fs::create_dir_all(app.join("node_modules/lib")).unwrap();
        std::fs::write(app.join("node_modules/lib/index.js"), "12345").unwrap();
        std::fs::write(dist.join("resources/default.asar"), "123").unwrap();
        let program = if cfg!(target_os = "macos") { dist.join("Electron.app/Contents/MacOS/Electron") } else { dist.join(exe("electron")) };
        std::fs::create_dir_all(program.parent().unwrap()).unwrap();
        std::fs::write(&program, b"electron").unwrap();
        mark_program(&program);
        let pin = create(&ws, PinMode::Light, None, None, &mut |_, _| true).unwrap();
        assert_eq!(pin.shared_bytes, 8, "the packages, not the program");
        assert!(pin.bytes >= 8);
    }

    #[test]
    fn a_live_pin_is_no_longer_made_and_an_old_one_still_opens_the_projects_app() {
        let d = tempfile::tempdir().unwrap();
        let ws = built(d.path());
        assert_eq!(create(&ws, PinMode::Live, None, None, &mut |_, _| true).unwrap_err().code, ErrorCode::BadInput);
        let old = read_pin(br#"{"id":2,"name":"A","mode":"live","created_ms":5}"#).unwrap();
        assert_eq!(old.app_dir(&ws), ws.app_dir());
    }

    #[test]
    fn a_pin_of_an_app_edited_in_place_leaves_the_projects_records_out() {
        let d = tempfile::tempdir().unwrap();
        let folder = d.path().join("mine");
        std::fs::create_dir_all(&folder).unwrap();
        std::fs::write(folder.join("notes.txt"), "mine").unwrap();
        let ws = Workspace::create_at(&folder, "Mine", "edit it", TargetRef::None, Some(crate::workspace::ExistingFiles::Edit)).unwrap();
        std::fs::write(folder.join("Cargo.toml"), "[package]\nname = \"mine\"\n").unwrap();
        std::fs::create_dir_all(folder.join("src")).unwrap();
        std::fs::write(folder.join("src/main.rs"), "fn main() {}").unwrap();
        std::fs::create_dir_all(folder.join("target/debug")).unwrap();
        std::fs::write(folder.join("target/debug").join(exe("mine")), b"program").unwrap();
        mark_program(&folder.join("target/debug").join(exe("mine")));
        let first = create(&ws, PinMode::Frozen, None, None, &mut |_, _| true).unwrap();
        let second = create(&ws, PinMode::Frozen, None, None, &mut |_, _| true).unwrap();
        assert_eq!((first.id, second.id), (1, 2));
        let copy = second.app_dir(&ws);
        assert!(copy.join("notes.txt").is_file());
        assert!(!copy.join(crate::workspace::MANIFEST).exists(), "the project's records aren't part of the app");
        assert!(!copy.join(PINNED).exists(), "a pin never copies other pins");
    }

    #[test]
    fn a_stopped_copy_leaves_nothing_behind_and_nothing_to_pin_is_refused() {
        let d = tempfile::tempdir().unwrap();
        let ws = built(d.path());
        let e = create(&ws, PinMode::Frozen, None, None, &mut |_, _| false).unwrap_err();
        assert_eq!(e.code, ErrorCode::Cancelled);
        assert!(list(&ws).is_empty());
        assert_eq!(std::fs::read_dir(ws.root.join(PINNED)).unwrap().count(), 0, "the half-made copy is gone");

        let empty = Workspace::create(d.path(), "Empty", "nothing yet", TargetRef::None).unwrap();
        assert_eq!(create(&empty, PinMode::Frozen, None, None, &mut |_, _| true).unwrap_err().code, ErrorCode::NotFound);
    }

    #[test]
    fn pins_are_renamed_and_removed_and_unreadable_ones_skipped() {
        let d = tempfile::tempdir().unwrap();
        let ws = built(d.path());
        let pin = create(&ws, PinMode::Frozen, None, None, &mut |_, _| true).unwrap();
        assert_eq!(rename(&ws, pin.id, "Best one").unwrap().name, "Best one");
        assert!(rename(&ws, pin.id, " ").is_err());
        std::fs::create_dir_all(ws.root.join(PINNED).join("7")).unwrap();
        std::fs::write(ws.root.join(PINNED).join("7").join(PIN_FILE), "{").unwrap();
        assert_eq!(list(&ws).len(), 1);
        delete(&ws, pin.id).unwrap();
        assert!(list(&ws).is_empty() && !pin.dir(&ws).exists());
        assert_eq!(delete(&ws, pin.id).unwrap_err().code, ErrorCode::NotFound);
    }

    #[test]
    fn an_older_or_newer_pin_file_is_read() {
        let old = read_pin(br#"{"id":2,"name":"A","mode":"live","created_ms":5}"#).unwrap();
        assert_eq!((old.version, old.mode, old.bytes), (PIN_VERSION, PinMode::Live, 0));
        assert_eq!(old.program, None);
        let frozen = read_pin(br#"{"version":1,"id":3,"name":"Old copy","mode":"frozen","created_ms":5,"program":"formerly-unknown"}"#).unwrap();
        assert_eq!(frozen.version, PIN_VERSION);
        assert_eq!(frozen.program, None, "the migration cannot invent the old pin's selected program");
        let newer = read_pin(br#"{"version":9,"id":2,"name":"A","mode":"frozen","created_ms":5,"colour":"red"}"#).unwrap();
        assert_eq!(newer.version, 9, "a newer pin keeps its version");
        assert!(read_pin(b"[]").is_err());
    }

    #[test]
    fn the_end_of_a_log_is_its_last_lines() {
        let d = tempfile::tempdir().unwrap();
        let log = d.path().join("run.log");
        let text: String = (0..100).map(|i| format!("line {i}\n")).collect();
        std::fs::write(&log, text).unwrap();
        let t = tail(&log);
        assert!(t.starts_with("line 80") && t.ends_with("line 99"), "{t}");
        assert_eq!(tail(&d.path().join("none.log")), "");
    }

    fn shell(script: &str) -> Launch {
        if cfg!(windows) { Launch::new("cmd").args(["/C", script]).hide_console() } else { Launch::new("sh").args(["-c", script]) }
    }

    #[test]
    fn one_copy_runs_per_folder_unless_another_is_asked_for() {
        let d = tempfile::tempdir().unwrap();
        let runs = Runs::default();
        let long = if cfg!(windows) { "ping -n 30 127.0.0.1 > NUL" } else { "sleep 30" };
        let Opened::Started { quit: None, .. } = runs.open(d.path(), shell(long), false).unwrap() else { panic!("it should be running") };
        assert!(matches!(runs.open(d.path(), shell(long), false).unwrap(), Opened::AlreadyRunning(_)));
        assert!(matches!(runs.open(d.path(), shell(long), true).unwrap(), Opened::Started { quit: None, .. }));
        assert_eq!(runs.running(d.path()).len(), 2);
        assert_eq!(runs.stop(d.path()), 2);
        assert!(runs.running(d.path()).is_empty());

        // A start that quits at once says so, and doesn't count as running.
        let log = d.path().join("run.log");
        let Opened::Started { quit: Some(ended), .. } = runs.open(d.path(), shell("echo no window here && exit 4").log_to(&log), false).unwrap() else {
            panic!("it should have quit")
        };
        assert_eq!(ended.code, Some(4));
        assert!(tail(&log).contains("no window here"));
        assert!(runs.running(d.path()).is_empty());
    }
}
