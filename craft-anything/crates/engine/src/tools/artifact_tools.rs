//! Artifacts: content-addressed inventories of archives and app bundles, safe extraction, and
//! comparison. Also hosts the filesystem and evidence-input helpers the JavaScript, web and
//! application tool modules share.

use crate::tool::{CancelToken, Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use craft_anything_analysis::js_inventory::{InvLimits, Inventorier, Inventory, compare_inventories};
use craft_anything_evidence::{
    Authority, Confidence, Coverage, Environment, ErrorCode, Evidence, EvidenceBuilder, Limitation, Location, Subject, ToolError, sha256_hex,
};
use craft_anything_formats::{asar, zip};
use schemars::JsonSchema;
use serde::Deserialize;
use serde_json::{Value, json};
use std::io::Write as _;
use std::path::{Component, Path, PathBuf};

pub fn specs() -> Vec<ToolSpec> {
    vec![
        ToolSpec {
            id: "core_archive_show",
            title: "Inventory an archive or app bundle",
            summary: "Content-addressed inventory of a ZIP/APK/IPA/JAR, Electron ASAR, app bundle or folder: every file with size, kind, role and sha256; nested archives opened to a bounded depth; ASAR integrity hashes and ZIP CRCs checked. Paged (offset/limit).",
            beginner: "List everything packed inside an app or archive, with a fingerprint for each file.",
            toolset: Toolset::Core,
            effects: Effects::EVIDENCE,
            requires: Requires::Nothing,
            input_schema: schema_of::<InspectArtifactParams>,
            run: core_archive_show,
        },
        ToolSpec {
            id: "core_archive_extract",
            title: "Extract an archive",
            summary: "Extract every regular file of a ZIP/APK/IPA/JAR or ASAR (plus its .asar.unpacked files) into a fresh private temporary folder chosen by Craft Anything, and return its path. Bounded size and count; entries that would escape the folder are refused.",
            beginner: "Unpack an app or archive into a new folder so you can look at the files.",
            toolset: Toolset::Core,
            effects: Effects::MUTATES_SESSION.union(Effects::WRITES_FILESYSTEM),
            requires: Requires::Nothing,
            input_schema: schema_of::<ExtractArtifactParams>,
            run: core_archive_extract,
        },
        ToolSpec {
            id: "core_archives_compare",
            title: "Compare two artifacts",
            summary: "Compare two archives, app bundles or folders file by file: added, removed, changed (by sha256) and moved files. Inputs are absolute paths or core_archive_show evidence.",
            beginner: "See which files differ between two versions of an app or archive.",
            toolset: Toolset::Core,
            effects: Effects::EVIDENCE,
            requires: Requires::Nothing,
            input_schema: schema_of::<CompareArtifactsParams>,
            run: core_archives_compare,
        },
    ]
}

// ---------------------------------------------------------------------------------------------
// Shared helpers

/// `p` relative to `root` with `/` separators on every platform (bundle and archive paths are POSIX);
/// `p` as-is when it is not under `root`.
pub(crate) fn rel_to(root: &Path, p: &Path) -> String {
    p.strip_prefix(root).map(|r| r.to_string_lossy().replace('\\', "/")).unwrap_or_else(|_| p.display().to_string())
}

/// Require an absolute path.
pub(crate) fn abs_path(p: &str, what: &str) -> Result<PathBuf, ToolError> {
    let path = PathBuf::from(p);
    if !path.is_absolute() {
        return Err(ToolError::invalid(format!("{what} must be an absolute path, got {p:?}"))
            .with_remediation("Pass the full path, for example /Users/me/Downloads/app.asar."));
    }
    Ok(path)
}

/// Read a whole file, refusing ones larger than `max`.
pub(crate) fn read_capped(path: &Path, max: u64) -> Result<Vec<u8>, ToolError> {
    let meta = std::fs::metadata(path).map_err(|e| ToolError::io(path.display(), e))?;
    if !meta.is_file() {
        return Err(ToolError::invalid(format!("{} is not a regular file", path.display())));
    }
    if meta.len() > max {
        return Err(ToolError::new(ErrorCode::OverLimit, format!("{} is {} bytes; the limit is {max}", path.display(), meta.len()))
            .with_remediation("Raise the size limit parameter if you really want to read it."));
    }
    std::fs::read(path).map_err(|e| ToolError::io(path.display(), e))
}

/// One file found by [`walk_dir`].
#[derive(Debug, Clone)]
pub(crate) struct WalkedFile {
    /// Relative path with `/` separators.
    pub rel: String,
    pub abs: PathBuf,
    pub size: u64,
}

#[derive(Debug, Default)]
pub(crate) struct Walked {
    pub files: Vec<WalkedFile>,
    pub dirs: Vec<String>,
    pub links: Vec<String>,
    pub ignored: usize,
    pub truncated: bool,
    /// Folders below the root that couldn't be listed, as (relative path, reason) (#294).
    pub unlisted: Vec<(String, String)>,
}

/// A limitation naming the folders that couldn't be listed, as (path, reason), if any (#294).
pub(crate) fn unlisted_limitation(unlisted: &[(String, String)]) -> Option<Limitation> {
    if unlisted.is_empty() {
        return None;
    }
    let first = unlisted.iter().take(5).map(|(rel, e)| format!("{rel} ({e})")).collect::<Vec<_>>().join(", ");
    let more = unlisted.len().saturating_sub(5);
    Some(Limitation::new(
        "unlisted_folders",
        format!(
            "{} folder(s) couldn't be listed, so what they hold is missing: {first}{}",
            unlisted.len(),
            if more > 0 { format!(" and {more} more") } else { String::new() }
        ),
    ))
}

pub(crate) struct WalkOptions<'a> {
    pub max_files: usize,
    pub max_depth: usize,
    /// Skip a directory (relative path) entirely.
    pub skip_dir: &'a dyn Fn(&str) -> bool,
    /// Honour `.gitignore` files found on the way.
    pub gitignore: bool,
    pub include_hidden: bool,
}

/// Walk a folder without following symbolic links. Bounded by file count and depth.
/// A root that can't be listed is an error; a folder below it that can't be is in `unlisted`.
pub(crate) fn walk_dir(root: &Path, opts: &WalkOptions<'_>, cancel: &CancelToken) -> Result<Walked, ToolError> {
    let mut out = Walked::default();
    let mut ignore = craft_anything_analysis::js_source::Ignore::default();
    let mut stack: Vec<(PathBuf, String, usize)> = vec![(root.to_path_buf(), String::new(), 0)];
    let mut visited = 0usize;
    while let Some((dir, rel, depth)) = stack.pop() {
        cancel.check()?;
        if opts.gitignore
            && let Ok(text) = std::fs::read_to_string(dir.join(".gitignore"))
        {
            ignore.add_file(&rel, &text);
        }
        let entries = match std::fs::read_dir(&dir) {
            Ok(e) => e,
            Err(e) if rel.is_empty() => return Err(ToolError::io(dir.display(), e)),
            Err(e) => {
                out.unlisted.push((rel, e.to_string()));
                continue;
            }
        };
        let mut names: Vec<(String, PathBuf)> = entries.flatten().map(|e| (e.file_name().to_string_lossy().into_owned(), e.path())).collect();
        names.sort();
        for (name, path) in names {
            visited += 1;
            if visited.is_multiple_of(256) {
                cancel.check()?;
            }
            let child_rel = if rel.is_empty() { name.clone() } else { format!("{rel}/{name}") };
            if !opts.include_hidden && name.starts_with('.') && name != ".gitignore" {
                out.ignored += 1;
                continue;
            }
            let Ok(meta) = std::fs::symlink_metadata(&path) else { continue };
            let ft = meta.file_type();
            if ft.is_symlink() {
                out.links.push(child_rel);
                continue;
            }
            if ft.is_dir() {
                if name == ".git" || (opts.skip_dir)(&child_rel) || (opts.gitignore && ignore.is_ignored(&child_rel, true)) {
                    out.ignored += 1;
                    continue;
                }
                if depth + 1 > opts.max_depth {
                    out.truncated = true;
                    continue;
                }
                out.dirs.push(child_rel.clone());
                stack.push((path, child_rel, depth + 1));
            } else if ft.is_file() {
                if opts.gitignore && ignore.is_ignored(&child_rel, false) {
                    out.ignored += 1;
                    continue;
                }
                if out.files.len() >= opts.max_files {
                    out.truncated = true;
                    continue;
                }
                out.files.push(WalkedFile { rel: child_rel, abs: path, size: meta.len() });
            }
        }
    }
    out.files.sort_by(|a, b| a.rel.cmp(&b.rel));
    Ok(out)
}

/// Evidence passed inline, as `{"kind":"saved","evidence_id":…}`, or as a bare id.
pub(crate) fn resolve_evidence_input(ctx: &Ctx<'_>, v: &Value, expected: &[&str]) -> Result<Evidence, ToolError> {
    let ev = if let Some(id) = v.as_str() {
        ctx.session.resolve_evidence(id)?
    } else if v.get("kind").and_then(Value::as_str) == Some("saved") {
        let id = v.get("evidence_id").and_then(Value::as_str).ok_or_else(|| ToolError::invalid("saved needs evidence_id"))?;
        ctx.session.resolve_evidence(id)?
    } else {
        let e: Evidence = serde_json::from_value(v.clone()).map_err(|e| {
            ToolError::invalid(format!("not an evidence record: {e}"))
                .with_remediation("Pass the evidence object a tool returned, or {\"kind\":\"saved\",\"evidence_id\":\"ev_…\"}.")
        })?;
        if !e.verify() {
            return Err(ToolError::new(ErrorCode::EvidenceHashMismatch, format!("evidence {} does not match its content", e.id))
                .with_remediation("Pass the record exactly as it was returned, or reference it by evidence_id."));
        }
        e
    };
    if !expected.is_empty() && !expected.contains(&ev.operation.as_str()) {
        return Err(ToolError::invalid(format!("evidence {} came from {}, but this needs {}", ev.id, ev.operation, expected.join(" or "))));
    }
    Ok(ev)
}

/// True when a value names a path rather than evidence.
pub(crate) fn is_path_input(v: &Value) -> Option<&str> {
    v.as_str().filter(|s| !craft_anything_evidence::is_evidence_id(s))
}

/// A unique id for a fresh folder name.
pub(crate) fn unique_suffix(seed: &str, attempt: u32) -> String {
    let nanos = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_nanos()).unwrap_or(0);
    let h = sha256_hex(format!("{seed}|{}|{nanos}|{attempt}", std::process::id()).as_bytes());
    h.get(..16).unwrap_or(&h).to_string()
}

/// Create a new private directory in the system temp folder.
pub(crate) fn fresh_temp_dir(prefix: &str) -> Result<PathBuf, ToolError> {
    let base = std::env::temp_dir();
    for attempt in 0..16 {
        let p = base.join(format!("{prefix}-{}", unique_suffix(prefix, attempt)));
        #[cfg(unix)]
        let b = {
            use std::os::unix::fs::DirBuilderExt as _;
            let mut b = std::fs::DirBuilder::new();
            b.mode(0o700);
            b
        };
        #[cfg(not(unix))]
        let b = std::fs::DirBuilder::new();
        match b.create(&p) {
            Ok(()) => return Ok(p),
            Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(e) => return Err(ToolError::io(p.display(), e)),
        }
    }
    Err(ToolError::new(ErrorCode::FileError, "could not create a fresh temporary folder"))
}

/// Create an output directory that must not exist yet (its parent must).
pub(crate) fn create_absent_dir(p: &str) -> Result<PathBuf, ToolError> {
    let path = abs_path(p, "output_directory")?;
    if std::fs::symlink_metadata(&path).is_ok() {
        return Err(
            ToolError::invalid(format!("{} already exists", path.display())).with_remediation("Choose a folder that does not exist yet; it will be created.")
        );
    }
    let parent = path.parent().ok_or_else(|| ToolError::invalid("output_directory has no parent folder"))?;
    if !parent.is_dir() {
        return Err(ToolError::invalid(format!("{} does not exist", parent.display())));
    }
    std::fs::create_dir(&path).map_err(|e| ToolError::io(path.display(), e))?;
    Ok(path)
}

/// Removes a folder from [`create_absent_dir`] when the tool stops before writing anything into
/// it, so the same call can be retried (#234). Call `keep` once the tool has succeeded.
pub(crate) struct UnlessWritten<'a> {
    dir: &'a Path,
    keep: bool,
}

impl<'a> UnlessWritten<'a> {
    pub(crate) fn new(dir: &'a Path) -> Self {
        UnlessWritten { dir, keep: false }
    }

    pub(crate) fn keep(mut self) {
        self.keep = true;
    }
}

impl Drop for UnlessWritten<'_> {
    fn drop(&mut self) {
        if !self.keep {
            // remove_dir only removes an empty folder, so anything written stays.
            let _ = std::fs::remove_dir(self.dir);
        }
    }
}

/// Turn an archive member name into safe relative components, or explain why not.
pub(crate) fn safe_components(name: &str) -> Result<Vec<String>, &'static str> {
    if name.contains('\0') {
        return Err("name contains a NUL byte");
    }
    let norm = name.replace('\\', "/");
    if norm.starts_with('/') {
        return Err("absolute path");
    }
    let mut out = Vec::new();
    for c in norm.split('/') {
        match c {
            "" | "." => {}
            ".." => return Err("path climbs out of the folder (..)"),
            c if c.len() == 2 && c.ends_with(':') => return Err("drive-letter path"),
            c => out.push(c.to_string()),
        }
    }
    if out.is_empty() {
        return Err("empty name");
    }
    Ok(out)
}

/// Write a file under `root`, never overwriting and never leaving `root`.
pub(crate) fn write_new_file(root: &Path, rel: &[String], bytes: &[u8]) -> Result<PathBuf, String> {
    let mut path = root.to_path_buf();
    for c in rel {
        if matches!(Path::new(c).components().next(), Some(Component::Normal(_))) && Path::new(c).components().count() == 1 {
            path.push(c);
        } else {
            return Err(format!("unsafe path component {c:?}"));
        }
    }
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;
        // A component that already exists as a symlink would let a write escape.
        let mut cur = root.to_path_buf();
        for c in rel.iter().take(rel.len().saturating_sub(1)) {
            cur.push(c);
            if std::fs::symlink_metadata(&cur).is_ok_and(|m| m.file_type().is_symlink()) {
                return Err("a parent folder is a symbolic link".into());
            }
        }
    }
    let mut f = std::fs::OpenOptions::new().write(true).create_new(true).open(&path).map_err(|e| e.to_string())?;
    f.write_all(bytes).map_err(|e| e.to_string())?;
    Ok(path)
}

/// The evidence environment for built-in engines.
pub(crate) fn env(ctx: &Ctx<'_>) -> Environment {
    Environment::builtin(ctx.session.clean_room())
}

// ---------------------------------------------------------------------------------------------
// Inventory

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Deserialize, JsonSchema)]
#[serde(rename_all = "kebab-case")]
pub enum IntegrityPolicy {
    /// Stop with an error when a recorded hash or checksum does not match the content.
    #[default]
    Fail,
    /// Record mismatches as contradictions and keep going.
    Continue,
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct InspectArtifactParams {
    /// Absolute path of the archive, app bundle or folder. Defaults to the active target.
    #[serde(default)]
    pub path: Option<String>,
    /// What to do when an ASAR integrity hash or ZIP CRC does not match.
    #[serde(default)]
    pub if_tampered: IntegrityPolicy,
    /// First entry of the page.
    #[serde(default)]
    pub offset: usize,
    /// Entries per page (1–20000).
    #[serde(default = "default_inv_limit")]
    pub limit: usize,
    /// How deep nested archives are opened (0–6).
    #[serde(default = "default_depth")]
    pub max_depth: u32,
    /// Most entries listed in total.
    #[serde(default = "default_max_entries")]
    pub max_entries: usize,
    /// Most bytes read and hashed in total.
    #[serde(default = "default_max_total")]
    pub max_total_bytes: u64,
}

fn default_inv_limit() -> usize {
    500
}
fn default_depth() -> u32 {
    3
}
fn default_max_entries() -> usize {
    200_000
}
fn default_max_total() -> u64 {
    4 * 1024 * 1024 * 1024
}

/// Build an inventory of a path (file or folder).
pub(crate) fn inventory_path(path: &Path, limits: InvLimits, cancel: &CancelToken) -> Result<(Inventory, Subject), ToolError> {
    inventory_path_unlisted(path, limits, cancel).map(|(inv, subject, _)| (inv, subject))
}

/// [`inventory_path`], also returning the folders that couldn't be listed, as (path, reason).
#[allow(clippy::type_complexity)]
fn inventory_path_unlisted(path: &Path, limits: InvLimits, cancel: &CancelToken) -> Result<(Inventory, Subject, Vec<(String, String)>), ToolError> {
    let meta = std::fs::metadata(path).map_err(|e| ToolError::io(path.display(), e))?;
    let name = path.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_else(|| path.display().to_string());
    let check = || cancel.is_cancelled();
    if meta.is_dir() {
        let skip = |_: &str| false;
        let walked =
            walk_dir(path, &WalkOptions { max_files: limits.max_entries, max_depth: 64, skip_dir: &skip, gitignore: false, include_hidden: true }, cancel)?;
        let mut inv = Inventorier::new(&name, "directory", limits, &check);
        for d in &walked.dirs {
            let failed = walked.unlisted.iter().find(|(rel, _)| rel == d);
            inv.add_marker(d, "directory", 0, failed.map(|(_, e)| format!("couldn't be listed: {e}")));
        }
        for l in &walked.links {
            inv.add_marker(l, "link", 0, Some("symbolic link (not followed)".into()));
        }
        let mut total = 0u64;
        for f in &walked.files {
            cancel.check()?;
            if total.saturating_add(f.size) > limits.max_total_bytes || f.size > limits.max_entry_bytes {
                inv.add_marker(&f.rel, "unread", 0, Some("size budget reached".into()));
                inv.inv.truncated = true;
                continue;
            }
            match std::fs::read(&f.abs) {
                Ok(b) => {
                    total += b.len() as u64;
                    inv.add_file(&f.rel, &b, 0).map_err(|_| ToolError::cancelled())?;
                }
                Err(e) => inv.add_marker(&f.rel, "unread", 0, Some(e.to_string())),
            }
        }
        let mut out = inv.finish();
        out.truncated |= walked.truncated;
        let id = out.content_id();
        let subject = Subject { kind: "directory".into(), sha256: Some(id.trim_start_matches("inv_").to_string()), name: Some(name) };
        return Ok((out, subject, walked.unlisted));
    }
    let bytes = read_capped(path, limits.max_total_bytes.min(crate::target::MAX_TARGET_BYTES))?;
    let kind = craft_anything_analysis::js_inventory::sniff_kind(&bytes, &name);
    let mut inv = Inventorier::new(&name, kind, limits, &check);
    let mut unlisted = Vec::new();
    match kind {
        "zip" | "apk" | "ipa" | "jar" | "hap" | "msix" | "asar" => {
            inv.add_archive("", &bytes, kind, 0).map_err(|_| ToolError::cancelled())?;
            // Electron keeps some files next to the archive.
            if kind == "asar" {
                let unpacked = PathBuf::from(format!("{}.unpacked", path.display()));
                if unpacked.is_dir() {
                    let skip = |_: &str| false;
                    let walked = walk_dir(
                        &unpacked,
                        &WalkOptions { max_files: limits.max_entries, max_depth: 64, skip_dir: &skip, gitignore: false, include_hidden: true },
                        cancel,
                    )?;
                    unlisted.extend(walked.unlisted.into_iter().map(|(rel, e)| (format!("{name}.unpacked/{rel}"), e)));
                    for f in walked.files.iter().take(limits.max_entries) {
                        if let Ok(b) = std::fs::read(&f.abs) {
                            inv.add_file(&format!("{name}.unpacked/{}", f.rel), &b, 0).map_err(|_| ToolError::cancelled())?;
                        }
                    }
                }
            }
        }
        _ => inv.add_file(&name, &bytes, 0).map_err(|_| ToolError::cancelled())?,
    }
    Ok((inv.finish(), Subject { kind: kind.into(), sha256: Some(sha256_hex(&bytes)), name: Some(name) }, unlisted))
}

fn target_path(ctx: &Ctx<'_>, p: Option<&str>) -> Result<PathBuf, ToolError> {
    match p {
        Some(p) => abs_path(p, "path"),
        None => Ok(ctx.session.active()?.target.path.clone()),
    }
}

fn integrity_error(inv: &Inventory) -> ToolError {
    ToolError::new(
        ErrorCode::FileHashMismatch,
        format!("{} integrity contradiction(s), first: {}", inv.contradictions.len(), inv.contradictions.first().map(Value::to_string).unwrap_or_default()),
    )
    .with_remediation("Pass if_tampered=continue to inventory it anyway and see every mismatch.")
    .with_details(json!({"contradictions": inv.contradictions.iter().take(50).collect::<Vec<_>>()}))
}

fn show_limits(max_depth: u32, max_entries: usize, max_total_bytes: u64) -> InvLimits {
    InvLimits { max_entries: max_entries.clamp(1, 1_000_000), max_depth: max_depth.min(6), max_total_bytes, ..InvLimits::default() }
}

/// Re-read the path a core_archive_show record names and check it is unchanged, then return its inventory at `limits`.
/// The check uses the scope the record was made with, since a folder's id covers only the entries that scope lists.
pub(crate) fn recorded_inventory(ev: &Evidence, limits: InvLimits, cancel: &CancelToken) -> Result<(Inventory, Subject), ToolError> {
    let path = ev.params.get("path").and_then(Value::as_str).ok_or_else(|| ToolError::invalid("inventory evidence has no path"))?;
    let num = |k: &str| ev.params.get(k).and_then(Value::as_u64);
    let recorded = show_limits(
        num("max_depth").map_or(default_depth(), |v| u32::try_from(v).unwrap_or(u32::MAX)),
        num("max_entries").map_or(default_max_entries(), |v| usize::try_from(v).unwrap_or(usize::MAX)),
        num("max_total_bytes").unwrap_or_else(default_max_total),
    );
    // A file's id is the hash of its bytes, whatever the scope; a folder's depends on the scope.
    let check = if ev.subject.kind == "directory" { recorded } else { limits };
    let (inv, subject) = inventory_path(Path::new(path), check, cancel)?;
    if subject.sha256 != ev.subject.sha256 {
        return Err(ToolError::new(ErrorCode::FileChanged, format!("{path} changed since evidence {} was recorded", ev.id))
            .with_remediation("Run core_archive_show again, or pass the path directly."));
    }
    if same_limits(&check, &limits) {
        return Ok((inv, subject));
    }
    inventory_path(Path::new(path), limits, cancel)
}

fn same_limits(a: &InvLimits, b: &InvLimits) -> bool {
    a.max_entries == b.max_entries
        && a.max_depth == b.max_depth
        && a.max_nested_bytes == b.max_nested_bytes
        && a.max_entry_bytes == b.max_entry_bytes
        && a.max_total_bytes == b.max_total_bytes
}

fn core_archive_show(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: InspectArtifactParams = parse_params(params)?;
    let path = target_path(ctx, p.path.as_deref())?;
    let limits = show_limits(p.max_depth, p.max_entries, p.max_total_bytes);
    ctx.report(None, format!("Inventorying {}", path.display()));
    let (inv, subject, unlisted) = inventory_path_unlisted(&path, limits, &ctx.cancel)?;
    let blocking = inv.contradictions.iter().any(|c| c.get("reason").and_then(Value::as_str).is_some_and(|r| r.contains("integrity") || r.contains("CRC")));
    if blocking && p.if_tampered == IntegrityPolicy::Fail {
        return Err(integrity_error(&inv));
    }
    let total = inv.entries.len();
    let limit = p.limit.clamp(1, 20_000);
    let page: Vec<&craft_anything_analysis::js_inventory::InvEntry> = inv.entries.iter().skip(p.offset).take(limit).collect();
    let files = inv.entries.iter().filter(|e| e.sha256.is_some()).count();
    let summary = format!(
        "{} ({}) holds {} files in {} entries{}; {} nested container(s){}.",
        inv.root,
        inv.root_kind,
        files,
        total,
        if inv.truncated { " (listing cut short by a limit)" } else { "" },
        inv.containers.len().saturating_sub(1),
        if inv.contradictions.is_empty() { String::new() } else { format!(", {} integrity contradiction(s)", inv.contradictions.len()) }
    );
    let mut lims = Vec::new();
    if inv.truncated {
        lims.push(Limitation::new(
            "truncated",
            "A size, count or depth limit stopped the inventory early; raise max_entries, max_total_bytes or max_depth to see more.",
        ));
    }
    lims.extend(unlisted_limitation(&unlisted));
    lims.push(Limitation::new("no_disk_images", "Disk images (DMG), installers (PKG/MSI) and compressed tarballs are listed as single files, not opened."));
    let mut coverage = Coverage::page(page.len() as u64, total as u64, p.offset as u64);
    if !unlisted.is_empty() {
        coverage.status = craft_anything_evidence::CoverageStatus::Partial;
    }
    let ev = EvidenceBuilder::new("core_archive_show", subject, env(ctx))
        .params(json!({"path": path, "if_tampered": p.if_tampered == IntegrityPolicy::Fail, "offset": p.offset, "limit": limit, "max_depth": limits.max_depth, "max_entries": limits.max_entries, "max_total_bytes": limits.max_total_bytes}))
        .result(json!({
            "path": path,
            "root": inv.root, "root_kind": inv.root_kind, "content_id": inv.content_id(),
            "files": files, "entries_total": total, "by_kind": inv.by_kind(), "hashed_bytes": inv.hashed_bytes,
            "containers": inv.containers, "contradictions": inv.contradictions, "truncated": inv.truncated,
            "entries": page,
        }))
        .summary(summary)
        .confidence(Confidence::Observed)
        .authority(Authority::OriginalFiles)
        .limitations(lims)
        .coverage(coverage)
        .location(Location::new("path", path.display().to_string()))
        .build()?;
    Ok(ToolOutput::evidence(ev))
}

// ---------------------------------------------------------------------------------------------
// Extraction

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ExtractArtifactParams {
    /// Absolute path of the ZIP/APK/IPA/JAR or ASAR. Defaults to the active target.
    #[serde(default)]
    pub path: Option<String>,
    /// What to do when an ASAR integrity hash or ZIP CRC does not match.
    #[serde(default)]
    pub if_tampered: IntegrityPolicy,
    /// Most files written.
    #[serde(default = "default_extract_files")]
    pub max_files: usize,
    /// Most bytes written in total.
    #[serde(default = "default_max_total")]
    pub max_bytes: u64,
}

fn default_extract_files() -> usize {
    100_000
}

fn core_archive_extract(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ExtractArtifactParams = parse_params(params)?;
    let path = target_path(ctx, p.path.as_deref())?;
    if path.is_dir() {
        return Err(
            ToolError::unsupported(format!("{} is already a folder", path.display())).with_remediation("Folders don't need extracting; analyse them directly.")
        );
    }
    let bytes = read_capped(&path, crate::target::MAX_TARGET_BYTES)?;
    let name = path.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
    let kind = craft_anything_analysis::js_inventory::sniff_kind(&bytes, &name);
    // Collect (name, bytes-or-error) without touching the disk first.
    enum Member<'a> {
        Data(&'a [u8]),
        Owned(Vec<u8>),
        Skip(String),
    }
    let mut members: Vec<(String, Member<'_>)> = Vec::new();
    let mut contradictions = Vec::new();
    match kind {
        "asar" => {
            let a = asar::parse(&bytes, p.max_files.saturating_mul(2)).map_err(|e| ToolError::new(ErrorCode::GarbledOutput, e.to_string()))?;
            for r in &a.rejected_names {
                members.push((r.clone(), Member::Skip("name could escape the folder".into())));
            }
            for e in a.entries.iter().filter(|e| e.kind == asar::AsarKind::File) {
                if e.unpacked {
                    let side = PathBuf::from(format!("{}.unpacked", path.display()));
                    match safe_components(&e.path) {
                        Ok(c) => {
                            let src = c.iter().fold(side, |acc, x| acc.join(x));
                            match std::fs::symlink_metadata(&src) {
                                Ok(m) if m.is_file() && m.len() <= p.max_bytes => match std::fs::read(&src) {
                                    Ok(b) => members.push((e.path.clone(), Member::Owned(b))),
                                    Err(err) => members.push((e.path.clone(), Member::Skip(err.to_string()))),
                                },
                                _ => members.push((e.path.clone(), Member::Skip("unpacked file not found beside the archive".into()))),
                            }
                        }
                        Err(r) => members.push((e.path.clone(), Member::Skip(r.into()))),
                    }
                    continue;
                }
                match asar::file_bytes(&bytes, &a, e) {
                    Some(d) => {
                        if let Some(i) = &e.integrity
                            && i.algorithm.eq_ignore_ascii_case("sha256")
                            && sha256_hex(d) != i.hash
                        {
                            contradictions.push(json!({"path": e.path, "reason": "ASAR integrity hash does not match"}));
                        }
                        members.push((e.path.clone(), Member::Data(d)));
                    }
                    None => members.push((e.path.clone(), Member::Skip("data lies outside the archive".into()))),
                }
            }
        }
        "zip" | "apk" | "ipa" | "jar" | "hap" | "msix" => {
            let z = zip::parse(&bytes, p.max_files.saturating_mul(2)).map_err(|e| ToolError::new(ErrorCode::GarbledOutput, e.to_string()))?;
            for e in z.entries.iter().filter(|e| !e.is_dir) {
                match zip::read_entry(&bytes, e, p.max_bytes) {
                    Ok(d) => members.push((e.name.clone(), Member::Owned(d))),
                    Err(err @ zip::ZipError::CrcMismatch { .. }) => {
                        contradictions.push(json!({"path": e.name, "reason": err.to_string()}));
                        members.push((e.name.clone(), Member::Skip(err.to_string())));
                    }
                    Err(err) => members.push((e.name.clone(), Member::Skip(err.to_string()))),
                }
            }
        }
        other => {
            return Err(ToolError::unsupported(format!("{name} is a {other} file, not an archive this tool extracts"))
                .with_remediation("core_archive_extract handles ZIP-based packages (zip, apk, ipa, jar, hap, msix) and Electron ASAR archives."));
        }
    }
    if !contradictions.is_empty() && p.if_tampered == IntegrityPolicy::Fail {
        return Err(ToolError::new(ErrorCode::FileHashMismatch, format!("{} member(s) fail their integrity check", contradictions.len()))
            .with_remediation("Pass if_tampered=continue to extract anyway.")
            .with_details(json!({"contradictions": contradictions})));
    }
    let out = fresh_temp_dir("craft-anything-extract")?;
    let mut written = 0usize;
    let mut total = 0u64;
    let mut skipped = Vec::new();
    for (i, (mname, m)) in members.iter().enumerate() {
        if i % 64 == 0 {
            ctx.cancel.check()?;
        }
        let data: &[u8] = match m {
            Member::Data(d) => d,
            Member::Owned(d) => d,
            Member::Skip(r) => {
                skipped.push(json!({"path": mname, "reason": r}));
                continue;
            }
        };
        if written >= p.max_files || total.saturating_add(data.len() as u64) > p.max_bytes {
            skipped.push(json!({"path": mname, "reason": "file count or size limit reached"}));
            continue;
        }
        let comps = match safe_components(mname) {
            Ok(c) => c,
            Err(r) => {
                skipped.push(json!({"path": mname, "reason": r}));
                continue;
            }
        };
        match write_new_file(&out, &comps, data) {
            Ok(_) => {
                written += 1;
                total += data.len() as u64;
            }
            Err(r) => skipped.push(json!({"path": mname, "reason": r})),
        }
    }
    let summary = format!(
        "Extracted {written} files ({total} bytes) from {name} into {}{}.",
        out.display(),
        if skipped.is_empty() { String::new() } else { format!("; skipped {}", skipped.len()) }
    );
    let ev = EvidenceBuilder::new("core_archive_extract", Subject { kind: kind.into(), sha256: Some(sha256_hex(&bytes)), name: Some(name) }, env(ctx))
        .params(json!({"path": path, "max_files": p.max_files, "max_bytes": p.max_bytes}))
        .result(json!({"output_directory": out, "files_written": written, "bytes_written": total, "skipped": skipped.iter().take(2000).collect::<Vec<_>>(), "contradictions": contradictions}))
        .summary(summary)
        .confidence(Confidence::Observed)
        .limitation(Limitation::new("nested_not_extracted", "Archives inside the archive are written as files, not unpacked; run core_archive_extract on them."))
        .coverage(Coverage { status: if skipped.is_empty() { craft_anything_evidence::CoverageStatus::Complete } else { craft_anything_evidence::CoverageStatus::Partial }, examined: Some(written as u64), total: Some(members.len() as u64), next_offset: None })
        .location(Location::new("path", out.display().to_string()).with_label("output folder"))
        .build()?;
    Ok(ToolOutput::evidence(ev))
}

// ---------------------------------------------------------------------------------------------
// Compare

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct CompareArtifactsParams {
    /// The older artifact: an absolute path, or core_archive_show evidence (inline or {"kind":"saved","evidence_id":…}).
    pub left: Value,
    /// The newer artifact, in the same forms.
    pub right: Value,
    /// Most rows per list.
    #[serde(default = "default_rows")]
    pub max_rows: usize,
}

fn default_rows() -> usize {
    500
}

fn inventory_input(ctx: &Ctx<'_>, v: &Value) -> Result<(Inventory, Option<String>), ToolError> {
    if let Some(p) = is_path_input(v) {
        let (inv, _) = inventory_path(&abs_path(p, "path")?, InvLimits::default(), &ctx.cancel)?;
        return Ok((inv, None));
    }
    let ev = resolve_evidence_input(ctx, v, &["core_archive_show"])?;
    // Evidence holds one page; re-read the recorded path for the full inventory and check it is unchanged.
    let (inv, _) = recorded_inventory(&ev, InvLimits::default(), &ctx.cancel)?;
    Ok((inv, Some(ev.id)))
}

fn core_archives_compare(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: CompareArtifactsParams = parse_params(params)?;
    let (l, lid) = inventory_input(ctx, &p.left)?;
    ctx.cancel.check()?;
    let (r, rid) = inventory_input(ctx, &p.right)?;
    let d = compare_inventories(&l, &r, p.max_rows.clamp(1, 100_000));
    let c = &d["counts"];
    let summary = format!(
        "{} → {}: {} added, {} removed, {} changed, {} moved, {} unchanged.",
        l.root, r.root, c["added"], c["removed"], c["changed"], c["moved"], c["unchanged"]
    );
    let mut b = EvidenceBuilder::new(
        "core_archives_compare",
        Subject { kind: "artifact-pair".into(), sha256: None, name: Some(format!("{} vs {}", l.root, r.root)) },
        env(ctx),
    )
    .params(json!({"left": l.content_id(), "right": r.content_id()}))
    .result(d)
    .summary(summary)
    .confidence(Confidence::Derived);
    if l.truncated || r.truncated {
        b = b.limitation(Limitation::new("truncated", "One inventory was cut short by a limit; files beyond it are not compared."));
    }
    for id in [lid, rid].into_iter().flatten() {
        b = b.link(id);
    }
    Ok(ToolOutput::evidence(b.build()?))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{CallOptions, Caller, Engine};
    use craft_anything_testkit::electron as fx;

    fn call(e: &Engine, id: &str, p: Value) -> Result<Value, ToolError> {
        e.call(id, p, CallOptions::new(Caller::Cli)).map(|o| o.to_json())
    }

    #[test]
    fn inventory_and_extract_asar() {
        let dir = tempfile::tempdir().unwrap();
        let a = dir.path().join("app.asar");
        std::fs::write(&a, fx::notes_app_asar()).unwrap();
        let e = Engine::new(crate::testing::session());
        let inv = call(&e, "core_archive_show", json!({"path": a})).unwrap();
        assert_eq!(inv["result"]["root_kind"], "asar");
        assert_eq!(inv["result"]["files"], 5);
        assert!(inv["result"]["entries"].as_array().unwrap().iter().any(|x| x["path"] == "renderer/app.js" && x["kind"] == "javascript"));
        let page = call(&e, "core_archive_show", json!({"path": a, "offset": 0, "limit": 2})).unwrap();
        assert_eq!(page["coverage"]["status"], "partial");
        assert_eq!(page["coverage"]["next_offset"], 2);
        let x = call(&e, "core_archive_extract", json!({"path": a})).unwrap();
        let out = PathBuf::from(x["result"]["output_directory"].as_str().unwrap());
        assert_eq!(std::fs::read_to_string(out.join("main.js")).unwrap(), fx::MAIN_JS);
        assert_eq!(x["result"]["files_written"], 5);
        std::fs::remove_dir_all(out).unwrap();
    }

    #[test]
    fn zip_slip_is_refused() {
        let dir = tempfile::tempdir().unwrap();
        let z = dir.path().join("evil.zip");
        std::fs::write(&z, fx::zip_stored(&[("../../escape.txt", b"x"), ("/etc/abs", b"y"), ("C:/win", b"z"), ("ok/fine.txt", b"ok")])).unwrap();
        let e = Engine::new(crate::testing::session());
        let x = call(&e, "core_archive_extract", json!({"path": z})).unwrap();
        assert_eq!(x["result"]["files_written"], 1);
        assert_eq!(x["result"]["skipped"].as_array().unwrap().len(), 3);
        let out = PathBuf::from(x["result"]["output_directory"].as_str().unwrap());
        assert!(out.join("ok/fine.txt").exists());
        assert!(!out.parent().unwrap().join("escape.txt").exists());
        std::fs::remove_dir_all(out).unwrap();
    }

    #[test]
    fn compare_two_folders_and_evidence_inputs() {
        let dir = tempfile::tempdir().unwrap();
        let a = fx::write_files(&dir.path().join("v1"), &fx::notes_app_files()).unwrap();
        let b = fx::write_files(&dir.path().join("v2"), &fx::notes_app_v2_files()).unwrap();
        let e = Engine::new(crate::testing::session());
        let d = call(&e, "core_archives_compare", json!({"left": a, "right": b})).unwrap();
        assert_eq!(d["result"]["counts"]["changed"], 2, "{}", d["result"]);
        let inv = call(&e, "core_archive_show", json!({"path": a})).unwrap();
        let id = inv["id"].as_str().unwrap();
        let d2 = call(&e, "core_archives_compare", json!({"left": {"kind": "saved", "evidence_id": id}, "right": b})).unwrap();
        assert_eq!(d2["result"]["counts"], d["result"]["counts"]);
        assert!(call(&e, "core_archives_compare", json!({"left": "relative/path", "right": b})).is_err());
    }

    #[test]
    fn folder_evidence_scope_is_not_a_change() {
        let dir = tempfile::tempdir().unwrap();
        let app = dir.path().join("app");
        std::fs::create_dir(&app).unwrap();
        let l3 = fx::zip_stored(&[("leaf.txt", b"leaf")]);
        let l2 = fx::zip_stored(&[("l3.zip", &l3)]);
        let l1 = fx::zip_stored(&[("l2.zip", &l2)]);
        std::fs::write(app.join("l1.zip"), &l1).unwrap();
        std::fs::write(app.join("other.txt"), b"other").unwrap();
        let e = Engine::new(crate::testing::session());
        let tools = ["core_archives_compare", "android_app_graph_build", "apple_app_graph_build", "harmony_app_graph_build"];
        let consume = |tool: &str, input: Value| {
            let p = if tool == "core_archives_compare" { json!({"left": input, "right": app}) } else { json!({"inventory": input}) };
            call(&e, tool, p)
        };
        let scopes = [json!({"max_depth": 2}), json!({"max_depth": 3}), json!({"max_entries": 2}), json!({"max_total_bytes": 10})];
        let mut recorded = Vec::new();
        for scope in scopes {
            let mut p = scope.clone();
            p["path"] = json!(app);
            let inv = call(&e, "core_archive_show", p).unwrap();
            let id = inv["id"].as_str().unwrap().to_string();
            for tool in tools {
                for input in [json!({"kind": "saved", "evidence_id": id}), inv.clone()] {
                    let out = consume(tool, input).unwrap_or_else(|err| panic!("{scope} {tool}: {err:?}"));
                    assert!(out["links"].as_array().unwrap().contains(&json!(id)), "{scope} {tool}");
                    if tool == "core_archives_compare" {
                        for k in ["added", "removed", "changed", "moved"] {
                            assert_eq!(out["result"]["counts"][k], 0, "{scope} {k}");
                        }
                    }
                }
            }
            recorded.push((id, inv));
        }
        // Real changes are still refused (both files change, so each recorded scope covers one).
        std::fs::write(app.join("l1.zip"), fx::zip_stored(&[("l2.zip", b"changed")])).unwrap();
        std::fs::write(app.join("other.txt"), b"changed").unwrap();
        for (id, inv) in recorded {
            for tool in tools {
                for input in [json!({"kind": "saved", "evidence_id": id}), inv.clone()] {
                    let err = consume(tool, input).unwrap_err();
                    assert_eq!(err.code, ErrorCode::FileChanged, "{tool}");
                }
            }
        }
    }

    #[test]
    fn if_tampered() {
        let dir = tempfile::tempdir().unwrap();
        let mut z = fx::zip_stored(&[("a.txt", b"hello")]);
        // Corrupt the stored data so the CRC no longer matches.
        let pos = z.windows(5).position(|w| w == b"hello").unwrap();
        z[pos] = b'j';
        let p = dir.path().join("bad.zip");
        std::fs::write(&p, &z).unwrap();
        let e = Engine::new(crate::testing::session());
        let err = call(&e, "core_archive_show", json!({"path": p})).unwrap_err();
        assert_eq!(err.code, ErrorCode::FileHashMismatch);
        let ok = call(&e, "core_archive_show", json!({"path": p, "if_tampered": "continue"})).unwrap();
        assert_eq!(ok["result"]["contradictions"].as_array().unwrap().len(), 1);
    }

    #[test]
    fn safe_components_rules() {
        assert!(safe_components("../x").is_err());
        assert!(safe_components("/x").is_err());
        assert!(safe_components("a\\..\\..\\x").is_err());
        assert!(safe_components("C:\\x").is_err());
        assert_eq!(safe_components("./a//b").unwrap(), vec!["a", "b"]);
        assert!(safe_components("").is_err());
    }

    /// #294: a folder that couldn't be listed looked like an ordinary empty folder.
    #[cfg(unix)]
    #[test]
    fn a_folder_that_cant_be_listed_is_marked_and_leaves_coverage_partial() {
        use std::os::unix::fs::PermissionsExt;
        let dir = tempfile::tempdir().unwrap();
        let bundle = dir.path().join("bundle");
        let closed = bundle.join("closed");
        std::fs::create_dir_all(&closed).unwrap();
        std::fs::write(closed.join("hidden.js"), "console.log('hidden');\n").unwrap();
        std::fs::write(bundle.join("visible.js"), "console.log('visible');\n").unwrap();
        let e = Engine::new(crate::testing::session());
        let readable = call(&e, "core_archive_show", json!({"path": bundle})).unwrap();
        std::fs::set_permissions(&closed, std::fs::Permissions::from_mode(0o000)).unwrap();
        if std::fs::read_dir(&closed).is_ok() {
            std::fs::set_permissions(&closed, std::fs::Permissions::from_mode(0o755)).unwrap();
            return; // Run as root: nothing is unreadable.
        }
        let child = call(&e, "core_archive_show", json!({"path": bundle}));
        let root = call(&e, "core_archive_show", json!({"path": closed}));
        std::fs::set_permissions(&closed, std::fs::Permissions::from_mode(0o755)).unwrap();
        let v = child.unwrap();
        assert_eq!(v["coverage"]["status"], "partial", "{v}");
        assert!(v["limitations"].as_array().unwrap().iter().any(|l| l["code"] == "unlisted_folders"), "{v}");
        let entry = v["result"]["entries"].as_array().unwrap().iter().find(|x| x["path"] == "closed").cloned().unwrap();
        assert!(entry["note"].as_str().is_some_and(|n| n.contains("couldn't be listed")), "{v}");
        assert!(root.is_err(), "a root folder that can't be listed is an error, not an empty inventory");
        assert_eq!(call(&e, "core_archive_show", json!({"path": bundle})).unwrap()["result"], readable["result"]);
    }
}
