//! Managed engine installs: download a pinned archive, verify its SHA-256 **before** unpacking, and
//! lay it out in the engine store so [`crate::locate`] finds it. The pins live in the engine table
//! ([`crate::table`]); every pin carries the publisher's SHA-256.
//!
//! Safety rules:
//! - every pinned download is hashed as it streams to disk; a mismatch removes the file and is an
//!   error, so nothing unverified is ever unpacked;
//! - extraction is zip-slip safe (no `..`, absolute or drive-letter members; links in tars are
//!   skipped, never followed or created);
//! - we download and unpack into a temporary folder and only then swap it into place, so a failed or
//!   cancelled install never leaves a half-written engine behind.

use craft_anything_evidence::{ErrorCode, ToolError};
use craft_anything_platform::fs::write_atomic;
use craft_anything_platform::process::Cancel;
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::time::Duration;

use crate::table::Install;
pub use crate::table::{ArchiveFormat, Pin};

/// Largest archive we will download (protects memory and disk).
pub const MAX_ARCHIVE_BYTES: u64 = 256 * 1024 * 1024;
/// Largest single file we will extract from an archive.
pub const MAX_ENTRY_BYTES: u64 = 256 * 1024 * 1024;
/// Largest uncompressed tar we will unpack (tars are decompressed in memory, then walked).
pub const MAX_TAR_BYTES: u64 = 512 * 1024 * 1024;
const MAX_ENTRIES: usize = 20_000;

/// The pin [`install`] would use for an engine on a host, if the engine is installed that way.
pub fn pinned(engine_id: &str, os: &str, arch: &str) -> Option<&'static Pin> {
    match crate::engine(engine_id)?.install {
        Install::Pinned(pins) => pins.iter().find(|p| p.matches(os, arch)),
        Install::Manual | Install::Guided { .. } => None,
    }
}

/// What an install produced.
#[derive(Debug, Clone, Serialize)]
pub struct InstallReport {
    pub engine_id: String,
    pub url: String,
    pub sha256: String,
    pub bytes: u64,
    pub files_written: usize,
    pub install_dir: PathBuf,
    /// The located executable, if `locate` now finds it.
    pub located: Option<PathBuf>,
}

/// Download, verify and install `engine_id` into `store_dir` from its pin in the engine table.
///
/// `expect_sha256` (64 hex), when given, must equal the pinned hash: it confirms what the caller
/// expects and can never replace the pin. `report` receives short progress lines. Honours `cancel`
/// between download chunks.
pub fn install(
    engine_id: &str,
    store_dir: &Path,
    expect_sha256: Option<&str>,
    cancel: Option<Cancel>,
    report: &dyn Fn(&str),
) -> Result<InstallReport, ToolError> {
    let (os, arch) = (std::env::consts::OS, std::env::consts::ARCH);
    // A malformed hash is the caller's mistake on every system, so it's named before what this
    // one can't install (FreeBSD has no pinned adb).
    let want = expect_sha256.map(|w| w.trim().to_ascii_lowercase());
    if want.as_ref().is_some_and(|w| w.len() != 64 || !w.bytes().all(|b| b.is_ascii_hexdigit())) {
        return Err(ToolError::invalid("sha256 must be 64 hex characters"));
    }
    let engine = crate::engine(engine_id).ok_or_else(|| {
        ToolError::new(ErrorCode::NotSupported, format!("There is no engine called {engine_id:?}."))
            .with_remediation("See Settings → Engines for the engines Craft Anything knows.")
    })?;
    let pins = match engine.install {
        Install::Pinned(pins) => pins,
        Install::Guided { how, .. } => {
            return Err(ToolError::new(ErrorCode::NotSupported, format!("{} is installed by its own setup, not here.", engine.name)).with_remediation(how));
        }
        Install::Manual => {
            return Err(ToolError::new(ErrorCode::NotSupported, format!("Craft Anything doesn't install {} for you.", engine.name))
                .with_remediation("Install it by hand and set its path in Settings → Engines."));
        }
    };
    let pin = pins.iter().find(|p| p.matches(os, arch)).ok_or_else(|| {
        ToolError::new(ErrorCode::NotSupported, format!("No pinned download for {} on {os} ({arch}).", engine.name))
            .with_remediation("Install it by hand and set its path in Settings → Engines.")
    })?;
    if want.is_some_and(|w| w != pin.sha256) {
        return Err(ToolError::invalid(format!("That sha256 is not the pinned hash for {engine_id} on {os}."))
            .with_remediation("Leave sha256 out: the pinned hash is always checked.")
            .with_details(serde_json::json!({"url": pin.url, "pinned": pin.sha256})));
    }

    std::fs::create_dir_all(store_dir).map_err(|e| ToolError::io(store_dir.display(), e))?;
    let archive = store_dir.join(format!(".{engine_id}-{}.archive", std::process::id()));
    report(&format!("downloading {}", pin.url));
    download_verified(pin.url, &archive, pin.sha256, MAX_ARCHIVE_BYTES, cancel.as_ref(), &|_, _| {})?;
    report("checksum verified");
    let data = std::fs::read(&archive).map_err(|e| ToolError::io(archive.display(), e));
    let _ = std::fs::remove_file(&archive);
    let data = data?;

    // Unpack into a sibling temp dir, then swap it into place.
    let incoming = store_dir.join(format!(".{engine_id}.incoming-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&incoming);
    std::fs::create_dir(&incoming).map_err(|e| ToolError::io(incoming.display(), e))?;
    let files_written = match unpack(&data, pin.format, &incoming, pin.strip_prefix, cancel.as_ref(), report) {
        Ok(n) => n,
        Err(e) => {
            let _ = std::fs::remove_dir_all(&incoming);
            return Err(e);
        }
    };

    let dest = store_dir.join(engine_id);
    let _ = std::fs::remove_dir_all(&dest);
    if let Err(e) = std::fs::rename(&incoming, &dest) {
        let _ = std::fs::remove_dir_all(&incoming);
        return Err(ToolError::io(dest.display(), e));
    }

    let located = crate::locate(engine_id, &NoOverrides, store_dir);
    report("done");
    Ok(InstallReport {
        engine_id: engine_id.to_string(),
        url: pin.url.to_string(),
        sha256: pin.sha256.to_string(),
        bytes: data.len() as u64,
        files_written,
        install_dir: dest,
        located,
    })
}

struct NoOverrides;
impl crate::ToolPathLookup for NoOverrides {
    fn override_for(&self, _: &str) -> Option<PathBuf> {
        None
    }
}

/// Download a URL into a file: written beside it first and moved into place only when complete,
/// so a broken or cancelled download never leaves a half file. `progress` gets (bytes so far,
/// total when the server says).
pub fn download_file(url: &str, dest: &Path, max_bytes: u64, cancel: Option<&Cancel>, progress: &dyn Fn(u64, Option<u64>)) -> Result<(), ToolError> {
    download_file_checked(url, dest, None, max_bytes, cancel, progress)
}

/// [`download_file`] for a pinned download: the bytes are hashed as they arrive, and if the
/// SHA-256 isn't `sha256` (lowercase hex) the file is removed and the result is an
/// `FileHashMismatch` error.
pub fn download_verified(
    url: &str,
    dest: &Path,
    sha256: &str,
    max_bytes: u64,
    cancel: Option<&Cancel>,
    progress: &dyn Fn(u64, Option<u64>),
) -> Result<(), ToolError> {
    download_file_checked(url, dest, Some(sha256), max_bytes, cancel, progress)
}

/// A file sink that also hashes what it writes.
struct Hashing<'a> {
    file: &'a mut std::fs::File,
    hasher: Sha256,
}

impl Write for Hashing<'_> {
    fn write(&mut self, buf: &[u8]) -> std::io::Result<usize> {
        let n = self.file.write(buf)?;
        self.hasher.update(buf.get(..n).unwrap_or_default());
        Ok(n)
    }

    fn flush(&mut self) -> std::io::Result<()> {
        self.file.flush()
    }
}

fn download_file_checked(
    url: &str,
    dest: &Path,
    sha256: Option<&str>,
    max_bytes: u64,
    cancel: Option<&Cancel>,
    progress: &dyn Fn(u64, Option<u64>),
) -> Result<(), ToolError> {
    write_checked(dest, sha256, url, &mut |sink| download_to(url, sink, max_bytes, cancel, progress))
}

/// Write `fill`'s bytes beside `dest`, hash them, and move the file into place only when `fill`
/// succeeded and the hash (if given) matches; otherwise the partial file is removed.
fn write_checked(dest: &Path, sha256: Option<&str>, url: &str, fill: &mut dyn FnMut(&mut dyn Write) -> Result<u64, ToolError>) -> Result<(), ToolError> {
    let part = dest.with_extension("download");
    let mut f = std::fs::File::create(&part).map_err(|e| ToolError::io(part.display(), e))?;
    let mut sink = Hashing { file: &mut f, hasher: Sha256::new() };
    let streamed = fill(&mut sink);
    let got = hex::encode(sink.hasher.finalize());
    let r = streamed.and_then(|_| f.sync_all().map_err(|e| ToolError::io(part.display(), e))).and_then(|_| match sha256 {
        Some(want) if !got.eq_ignore_ascii_case(want.trim()) => Err(integrity_error(url, want, &got)),
        _ => Ok(()),
    });
    drop(f);
    match r.and_then(|_| std::fs::rename(&part, dest).map_err(|e| ToolError::io(dest.display(), e))) {
        Ok(()) => Ok(()),
        Err(e) => {
            let _ = std::fs::remove_file(&part);
            Err(e)
        }
    }
}

fn integrity_error(url: &str, expected: &str, actual: &str) -> ToolError {
    ToolError::new(ErrorCode::FileHashMismatch, "The downloaded file's SHA-256 does not match its published checksum, so it was deleted unused.")
        .with_remediation("Do not use this download. The URL may have changed or the file may be corrupt or tampered with; try again later.")
        .with_details(serde_json::json!({"expected": expected, "actual": actual, "url": url}))
}

/// Stream an https URL into `sink` with a size cap, checking `cancel` between chunks.
pub fn download_to(
    url: &str,
    sink: &mut dyn std::io::Write,
    max_bytes: u64,
    cancel: Option<&Cancel>,
    progress: &dyn Fn(u64, Option<u64>),
) -> Result<u64, ToolError> {
    if !url.starts_with("https://") {
        return Err(ToolError::invalid("engine downloads must use https"));
    }
    let agent = ureq::Agent::config_builder()
        .http_status_as_error(false)
        .user_agent("CraftAnything-dev")
        .timeout_connect(Some(Duration::from_secs(20)))
        .timeout_recv_response(Some(Duration::from_secs(60)))
        .timeout_recv_body(Some(Duration::from_secs(60 * 20)))
        .build()
        .new_agent();
    let resp = agent.get(url).call().map_err(|e| {
        let code = if matches!(e, ureq::Error::Timeout(_)) { ErrorCode::TimedOut } else { ErrorCode::EngineMissing };
        ToolError::new(code, format!("Couldn't download {url}: {e}")).with_remediation("Check your internet connection and try again.")
    })?;
    let status = resp.status().as_u16();
    if !(200..300).contains(&status) {
        return Err(ToolError::new(ErrorCode::EngineMissing, format!("The download server answered {status} for {url}."))
            .with_remediation("The URL may have moved; update the pinned URL."));
    }
    let total = resp.headers().get("content-length").and_then(|v| v.to_str().ok()).and_then(|s| s.parse::<u64>().ok());
    let mut reader = resp.into_body().into_reader().take(max_bytes + 1);
    let mut got = 0u64;
    let mut chunk = vec![0u8; 256 * 1024];
    progress(0, total);
    loop {
        if cancel.is_some_and(|c| c()) {
            return Err(ToolError::cancelled());
        }
        let n = reader.read(&mut chunk).map_err(|e| ToolError::new(ErrorCode::EngineMissing, format!("The download broke off: {e}")))?;
        if n == 0 {
            break;
        }
        if got + n as u64 > max_bytes {
            return Err(ToolError::new(ErrorCode::OverLimit, format!("The download is larger than {max_bytes} bytes."))
                .with_remediation("Install this engine by hand instead."));
        }
        sink.write_all(chunk.get(..n).unwrap_or_default()).map_err(|e| ToolError::new(ErrorCode::ProgramFailed, format!("Couldn't save the download: {e}")))?;
        got += n as u64;
        progress(got, total);
    }
    Ok(got)
}

/// Unpack a verified archive of `format` into `dest`, stripping `strip_prefix` and skipping unsafe
/// member names. Returns the number of files written.
pub fn unpack(
    data: &[u8],
    format: ArchiveFormat,
    dest: &Path,
    strip_prefix: Option<&str>,
    cancel: Option<&Cancel>,
    report: &dyn Fn(&str),
) -> Result<usize, ToolError> {
    match format {
        ArchiveFormat::Zip => unpack_zip(data, dest, strip_prefix, MAX_ENTRY_BYTES, cancel, report),
        ArchiveFormat::TarGz => {
            let (tar, _) = craft_anything_formats::firmware::gunzip(data, MAX_TAR_BYTES).map_err(|e| decompress_error("gzip", e.to_string()))?;
            unpack_tar(&tar, dest, strip_prefix, cancel, report)
        }
        ArchiveFormat::TarXz => {
            let tar = craft_anything_formats::decompress::xz(data, MAX_TAR_BYTES).map_err(|e| decompress_error("xz", e.to_string()))?;
            unpack_tar(&tar, dest, strip_prefix, cancel, report)
        }
        ArchiveFormat::File { name } => {
            if name.is_empty() || name.contains(['/', '\\']) || name == "." || name == ".." {
                return Err(ToolError::internal(format!("pinned file name {name:?} isn't a plain file name")));
            }
            let path = dest.join(name);
            std::fs::write(&path, data).map_err(|e| ToolError::io(path.display(), e))?;
            report(&format!("saved {name}"));
            Ok(1)
        }
    }
}

fn decompress_error(what: &str, why: String) -> ToolError {
    ToolError::new(ErrorCode::GarbledOutput, format!("The {what} archive could not be decompressed: {why}"))
        .with_remediation(format!("Archives over {} MB unpacked are installed by hand.", MAX_TAR_BYTES / (1024 * 1024)))
}

/// Unpack a zip that was already verified into `dest` (zip-slip safe). Returns the files written.
pub fn unpack_zip_into(data: &[u8], dest: &Path, max_entry: u64, cancel: Option<&Cancel>) -> Result<usize, ToolError> {
    unpack_zip(data, dest, None, max_entry, cancel, &|_| {})
}

/// The safe path inside the install folder for an archive member, or `None` to skip it (outside
/// the expected top-level folder, or an unsafe name).
fn member_path(dest: &Path, name: &str, strip_prefix: Option<&str>) -> Option<PathBuf> {
    let name = match strip_prefix {
        Some(p) => name.strip_prefix(p)?,
        None => name,
    };
    let rel = safe_components(name).ok().filter(|r| !r.is_empty())?;
    let mut path = dest.to_path_buf();
    for c in &rel {
        path.push(c);
    }
    Some(path)
}

fn write_member(path: &Path, bytes: &[u8]) -> Result<(), ToolError> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).map_err(|e| ToolError::io(parent.display(), e))?;
    }
    write_atomic(path, bytes)?;
    set_executable(path);
    Ok(())
}

/// Unpack a zip into `dest`, stripping `strip_prefix`, rejecting unsafe member names. Returns the
/// number of files written.
fn unpack_zip(
    data: &[u8],
    dest: &Path,
    strip_prefix: Option<&str>,
    max_entry: u64,
    cancel: Option<&Cancel>,
    report: &dyn Fn(&str),
) -> Result<usize, ToolError> {
    use craft_anything_formats::zip;
    let archive = zip::parse(data, MAX_ENTRIES).map_err(|e| ToolError::new(ErrorCode::GarbledOutput, format!("The archive could not be read: {e}")))?;
    let mut written = 0usize;
    for (i, entry) in archive.entries.iter().enumerate() {
        if cancel.is_some_and(|c| c()) {
            return Err(ToolError::cancelled());
        }
        if entry.is_dir {
            continue;
        }
        let Some(path) = member_path(dest, &entry.name, strip_prefix) else { continue };
        if i % 25 == 0 {
            report(&format!("unpacking ({written} files)"));
        }
        let bytes = zip::read_entry(data, entry, max_entry)
            .map_err(|e| ToolError::new(ErrorCode::GarbledOutput, format!("A file in the archive could not be extracted: {e}")))?;
        write_member(&path, &bytes)?;
        written += 1;
    }
    if written == 0 {
        return Err(ToolError::new(ErrorCode::GarbledOutput, "The archive contained no usable files."));
    }
    Ok(written)
}

/// Unpack an (uncompressed) tar into `dest`. Only regular files are written: folders are made as
/// needed, and symlinks, hard links and device nodes are skipped.
fn unpack_tar(data: &[u8], dest: &Path, strip_prefix: Option<&str>, cancel: Option<&Cancel>, report: &dyn Fn(&str)) -> Result<usize, ToolError> {
    use craft_anything_formats::tarcpio::{self, MemberKind};
    let listing = tarcpio::tar(data, MAX_ENTRIES).ok_or_else(|| ToolError::new(ErrorCode::GarbledOutput, "The archive is not a tar file."))?;
    if listing.truncated {
        return Err(ToolError::new(ErrorCode::OverLimit, format!("The archive has more than {MAX_ENTRIES} entries."))
            .with_remediation("Install this engine by hand instead."));
    }
    let mut written = 0usize;
    for (i, m) in listing.members.iter().enumerate() {
        if cancel.is_some_and(|c| c()) {
            return Err(ToolError::cancelled());
        }
        if m.kind != MemberKind::File {
            continue;
        }
        let Some(path) = member_path(dest, &m.name, strip_prefix) else { continue };
        if m.size > MAX_ENTRY_BYTES {
            return Err(ToolError::new(ErrorCode::OverLimit, format!("A file in the archive is larger than {MAX_ENTRY_BYTES} bytes.")));
        }
        if i % 25 == 0 {
            report(&format!("unpacking ({written} files)"));
        }
        let bytes = tarcpio::member_data(data, m)
            .ok_or_else(|| ToolError::new(ErrorCode::GarbledOutput, "A file in the archive is cut short; it was not unpacked."))?;
        write_member(&path, bytes)?;
        written += 1;
    }
    if written == 0 {
        return Err(ToolError::new(ErrorCode::GarbledOutput, "The archive contained no usable files."));
    }
    Ok(written)
}

/// Turn an archive member name into safe relative components (no `..`, absolute or drive-letter
/// paths, no NUL).
fn safe_components(name: &str) -> Result<Vec<String>, &'static str> {
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
            ".." => return Err("path climbs out of the folder"),
            c if c.len() == 2 && c.ends_with(':') => return Err("drive-letter path"),
            c => out.push(c.to_string()),
        }
    }
    Ok(out)
}

#[cfg(unix)]
fn set_executable(path: &Path) {
    use std::os::unix::fs::PermissionsExt as _;
    let _ = std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o755));
}

#[cfg(not(unix))]
fn set_executable(_path: &Path) {}

#[cfg(test)]
mod tests {
    use super::*;

    /// A real install, only where `CRAFT_ANYTHING_TEST_INSTALL` names an engine (it downloads)
    /// and `CRAFT_ANYTHING_TEST_INSTALL_STORE` a folder to install into: the pin downloads,
    /// verifies, unpacks, and `locate` finds the engine.
    #[test]
    fn a_pinned_engine_installs_for_real() {
        let (Ok(id), Ok(store)) = (std::env::var("CRAFT_ANYTHING_TEST_INSTALL"), std::env::var("CRAFT_ANYTHING_TEST_INSTALL_STORE")) else { return };
        let r = install(&id, Path::new(&store), None, None, &|_| {}).unwrap();
        assert!(r.files_written > 0, "{r:?}");
        assert!(r.located.as_ref().is_some_and(|p| p.is_file()), "installed but not found: {r:?}");
    }

    #[test]
    fn adb_and_jadx_are_pinned_on_every_desktop() {
        for os in ["linux", "macos", "windows"] {
            assert!(pinned("adb", os, "x86_64").is_some(), "adb on {os}");
            assert!(pinned("jadx", os, "aarch64").is_some(), "jadx on {os}");
        }
        assert!(pinned("totally-unknown-engine", "linux", "x86_64").is_none());
        // Guided and manual engines have no generic pin.
        assert!(pinned("ghidra", "windows", "x86_64").is_none());
        assert!(pinned("gdb", "linux", "x86_64").is_none());
    }

    #[test]
    fn rejects_bad_or_different_hash_before_downloading() {
        let dir = tempfile::tempdir().unwrap();
        let err = install("adb", dir.path(), Some("not-a-hash"), None, &|_| {}).unwrap_err();
        assert_eq!(err.code, ErrorCode::BadInput);
        // A well-formed hash that isn't the pin can't replace it.
        let err = install("jadx", dir.path(), Some(&"0".repeat(64)), None, &|_| {}).unwrap_err();
        assert_eq!(err.code, ErrorCode::BadInput);
        assert!(err.remediation.is_some());
        assert_eq!(std::fs::read_dir(dir.path()).unwrap().count(), 0, "nothing was written");
    }

    #[test]
    fn unknown_manual_and_guided_engines_are_unsupported() {
        let dir = tempfile::tempdir().unwrap();
        for id in ["nope", "gdb", "ghidra", "java"] {
            let err = install(id, dir.path(), None, None, &|_| {}).unwrap_err();
            assert_eq!(err.code, ErrorCode::NotSupported, "{id}");
            assert!(err.remediation.is_some(), "{id}");
        }
    }

    #[test]
    fn a_hash_mismatch_removes_the_file() {
        let dir = tempfile::tempdir().unwrap();
        let dest = dir.path().join("thing.zip");
        let body = b"pretend archive";
        let good = hex::encode(Sha256::digest(body));
        let mut fill = |w: &mut dyn Write| w.write_all(body).map(|_| body.len() as u64).map_err(|e| ToolError::io("test", e));
        let err = write_checked(&dest, Some(&"0".repeat(64)), "https://example.invalid/x", &mut fill).unwrap_err();
        assert_eq!(err.code, ErrorCode::FileHashMismatch);
        assert_eq!(std::fs::read_dir(dir.path()).unwrap().count(), 0, "the download was deleted");
        write_checked(&dest, Some(&good.to_ascii_uppercase()), "https://example.invalid/x", &mut fill).unwrap();
        assert_eq!(std::fs::read(&dest).unwrap(), body);
        // A failed stream leaves nothing behind either.
        let mut broken = |_: &mut dyn Write| Err(ToolError::cancelled());
        assert!(write_checked(&dir.path().join("other.zip"), None, "https://example.invalid/y", &mut broken).is_err());
        assert_eq!(std::fs::read_dir(dir.path()).unwrap().count(), 1);
    }

    #[test]
    fn unpacks_tar_gz_files_only_and_safely() {
        use craft_anything_testkit::firmware as fx;
        let tar = fx::tar_entries(&[
            ("jdk/", b'5', b"", ""),
            ("jdk/bin/java", b'0', b"#!/bin/sh\n", ""),
            ("jdk/link", b'2', b"", "/etc/passwd"),
            ("jdk/../../escape", b'0', b"no", ""),
            ("other/readme", b'0', b"outside the prefix", ""),
        ]);
        let gz = fx::gzip(&tar, None);
        let dir = tempfile::tempdir().unwrap();
        let n = unpack(&gz, ArchiveFormat::TarGz, dir.path(), Some("jdk/"), None, &|_| {}).unwrap();
        assert_eq!(n, 1);
        assert_eq!(std::fs::read(dir.path().join("bin/java")).unwrap(), b"#!/bin/sh\n");
        assert!(!dir.path().join("link").exists());
        assert!(!dir.path().join("readme").exists());
        // Not a gzip at all.
        let err = unpack(b"not gzip", ArchiveFormat::TarGz, dir.path(), None, None, &|_| {}).unwrap_err();
        assert_eq!(err.code, ErrorCode::GarbledOutput);
    }

    #[test]
    fn unpacks_tar_xz() {
        // pkg/ (dir), pkg/bin/tool (file), pkg/evil -> /etc/passwd (symlink), ../escape (file).
        let xz = hex::decode(TAR_XZ).unwrap();
        let dir = tempfile::tempdir().unwrap();
        let n = unpack(&xz, ArchiveFormat::TarXz, dir.path(), None, None, &|_| {}).unwrap();
        assert_eq!(n, 1);
        assert_eq!(std::fs::read(dir.path().join("pkg/bin/tool")).unwrap(), b"#!/bin/sh\necho tool\n");
        assert!(!dir.path().join("pkg/evil").exists());
        assert!(!dir.path().parent().unwrap().join("escape").exists());
        // Corrupt xz is an error, never a panic.
        let mut bad = xz.clone();
        bad.truncate(bad.len() / 2);
        assert!(unpack(&bad, ArchiveFormat::TarXz, dir.path(), None, None, &|_| {}).is_err());
    }

    /// A ustar archive compressed with xz (CRC64 check), built with Python's tarfile and lzma.
    const TAR_XZ: &str = "fd377a585a000004e6d6b4460200210116000000742fe5a3e027ff00b95d00381ac91598acd1b234b7cf2f9dad0e287d129d13e5581d0f65aacbc6993ed65c623bb34f1cec998f414b193ae8d64e266bd6a04145e33d28c8b0f03106162354da1e0244e42f3bfa05dce43926c9b28039e5719c8a26e70d04b2ed7073f11a50f3f0e4679408db9327796c40719e04310e15eb36b3663fe42e616563e2ffbe3ccca4ceda11b6140a97d1412818e287480942a93c90ef60056a8a2f34f413d850e4add9e54f0541ac9ac93abcafdaaabdb075c3e49ce4a1f60000000000f2d8b968b3c5292a0001d501805000007ae8233db1c467fb020000000004595a";

    #[test]
    fn safe_components_rejects_traversal() {
        assert!(safe_components("../etc/passwd").is_err());
        assert!(safe_components("/abs").is_err());
        assert!(safe_components("a/b/c").unwrap().len() == 3);
        assert!(safe_components("./a").unwrap() == vec!["a".to_string()]);
    }

    /// Downloads the real pins for this computer (about 80 MB). Run with `--ignored`.
    #[test]
    #[ignore = "downloads from the network"]
    fn installs_the_real_pins() {
        for id in ["adb", "jadx"] {
            let dir = tempfile::tempdir().unwrap();
            let rep = install(id, dir.path(), None, None, &|_| {}).unwrap();
            assert!(rep.located.is_some(), "{id}: {rep:?}");
            assert_eq!(std::fs::read_dir(dir.path()).unwrap().count(), 1, "{id}: only the install folder is left");
        }
    }

    #[test]
    fn unpacks_a_zip_and_strips_prefix() {
        // Build a tiny stored (uncompressed) zip with one file under platform-tools/.
        let data = make_stored_zip("platform-tools/adb", b"#!/bin/sh\necho adb\n");
        let dir = tempfile::tempdir().unwrap();
        let n = unpack_zip(&data, dir.path(), Some("platform-tools/"), MAX_ENTRY_BYTES, None, &|_| {}).unwrap();
        // A file over the limit stops the unpack instead of being read into memory.
        let small = tempfile::tempdir().unwrap();
        assert!(unpack_zip(&data, small.path(), Some("platform-tools/"), 4, None, &|_| {}).is_err());
        assert_eq!(n, 1);
        let adb = dir.path().join("adb");
        assert!(adb.is_file());
        assert_eq!(std::fs::read(&adb).unwrap(), b"#!/bin/sh\necho adb\n");
    }

    /// Minimal single-entry stored zip (local header + central directory + EOCD), for tests only.
    fn make_stored_zip(name: &str, body: &[u8]) -> Vec<u8> {
        let crc = craft_anything_formats::zip::crc32(body);
        let nb = name.as_bytes();
        let mut out = Vec::new();
        // local file header
        out.extend_from_slice(&0x0403_4b50u32.to_le_bytes());
        out.extend_from_slice(&20u16.to_le_bytes()); // version needed
        out.extend_from_slice(&0u16.to_le_bytes()); // flags
        out.extend_from_slice(&0u16.to_le_bytes()); // method: stored
        out.extend_from_slice(&0u16.to_le_bytes()); // mod time
        out.extend_from_slice(&0u16.to_le_bytes()); // mod date
        out.extend_from_slice(&crc.to_le_bytes());
        out.extend_from_slice(&(body.len() as u32).to_le_bytes());
        out.extend_from_slice(&(body.len() as u32).to_le_bytes());
        out.extend_from_slice(&(nb.len() as u16).to_le_bytes());
        out.extend_from_slice(&0u16.to_le_bytes()); // extra len
        out.extend_from_slice(nb);
        out.extend_from_slice(body);
        let cd_offset = out.len() as u32;
        // central directory header
        let mut cd = Vec::new();
        cd.extend_from_slice(&0x0201_4b50u32.to_le_bytes());
        cd.extend_from_slice(&20u16.to_le_bytes()); // version made by
        cd.extend_from_slice(&20u16.to_le_bytes()); // version needed
        cd.extend_from_slice(&0u16.to_le_bytes()); // flags
        cd.extend_from_slice(&0u16.to_le_bytes()); // method
        cd.extend_from_slice(&0u16.to_le_bytes()); // time
        cd.extend_from_slice(&0u16.to_le_bytes()); // date
        cd.extend_from_slice(&crc.to_le_bytes());
        cd.extend_from_slice(&(body.len() as u32).to_le_bytes());
        cd.extend_from_slice(&(body.len() as u32).to_le_bytes());
        cd.extend_from_slice(&(nb.len() as u16).to_le_bytes());
        cd.extend_from_slice(&0u16.to_le_bytes()); // extra
        cd.extend_from_slice(&0u16.to_le_bytes()); // comment
        cd.extend_from_slice(&0u16.to_le_bytes()); // disk
        cd.extend_from_slice(&0u16.to_le_bytes()); // internal attrs
        cd.extend_from_slice(&0u32.to_le_bytes()); // external attrs
        cd.extend_from_slice(&0u32.to_le_bytes()); // local header offset
        cd.extend_from_slice(nb);
        let cd_size = cd.len() as u32;
        out.extend_from_slice(&cd);
        // end of central directory
        out.extend_from_slice(&0x0605_4b50u32.to_le_bytes());
        out.extend_from_slice(&0u16.to_le_bytes()); // disk
        out.extend_from_slice(&0u16.to_le_bytes()); // cd disk
        out.extend_from_slice(&1u16.to_le_bytes()); // entries on disk
        out.extend_from_slice(&1u16.to_le_bytes()); // total entries
        out.extend_from_slice(&cd_size.to_le_bytes());
        out.extend_from_slice(&cd_offset.to_le_bytes());
        out.extend_from_slice(&0u16.to_le_bytes()); // comment len
        out
    }
}
