//! Finding Ghidra and the Java it runs on, and getting both for the person once they agree:
//! pinned releases, each checked against its publisher's SHA-256 before anything is unpacked.

use craft_anything_evidence::{ErrorCode, ToolError};
use craft_anything_platform::process::Cancel;
use std::path::{Path, PathBuf};

/// Ghidra's engine id, as the engine table, Settings and every listing name it.
pub const ID: &str = "ghidra";
/// The Ghidra release Craft Anything installs (it needs Java 21).
pub const VERSION: &str = "12.1.4";
/// What the person downloads, for the question we ask first (Ghidra 543 MB + Java 196 MB).
pub const DOWNLOAD_MB: u32 = 740;
/// Where to get Ghidra by hand when we can't install it here.
pub const PAGE: &str = "https://github.com/NationalSecurityAgency/ghidra/releases";

/// The host's pin for a guided engine (`ghidra`, `java`) from the engine table.
fn pin(id: &str) -> Option<&'static crate::Pin> {
    crate::engine(id).and_then(crate::ExternalEngine::host_pin)
}

/// Whether [`install`] works on this computer: Ghidra and its Java both have a pin here (Java is
/// pinned for Windows x64 and for Linux and macOS on x64 and arm64).
pub fn can_install() -> bool {
    pin(ID).is_some() && pin("java").is_some()
}

/// Ghidra's headless launcher: in the folder the person picked (Ghidra's own folder, or one that
/// holds it), then the managed install, then PATH, then where system packages put it.
pub fn headless(install_dir: Option<&Path>, store: &Path) -> Option<PathBuf> {
    headless_configured(install_dir, store)
        .or_else(|| crate::find_on_path(&["analyzeHeadless.bat", "analyzeHeadless"]))
        .or_else(|| crate::well_known(ID).into_iter().find(|p| p.is_file()))
}

/// Ghidra's headless launcher in the folder the person picked or the managed install only: what
/// [`headless`] finds before it looks around the computer.
pub fn headless_configured(install_dir: Option<&Path>, store: &Path) -> Option<PathBuf> {
    if let Some(dir) = install_dir {
        if dir.is_file() {
            return Some(dir.to_path_buf());
        }
        if let Some(p) = in_root_or_child(dir, launcher) {
            return Some(p);
        }
    }
    in_child(&store.join(ID), launcher)
}

/// The Java runtime to run Ghidra with: the one the person set, else the managed one. `None` lets
/// Ghidra look for its own.
pub fn java_home(java_home: Option<&Path>, store: &Path) -> Option<PathBuf> {
    java_home.filter(|p| p.is_dir()).map(Path::to_path_buf).or_else(|| in_child(&store.join("jdk"), |d| has_java(d).then(|| d.to_path_buf())))
}

/// Download, check and unpack Java (unless one is already managed) and Ghidra into the engine
/// store, then point Ghidra at that Java. `progress` gets (what, bytes so far, total); a step with
/// no bytes (0, `None`) is setting up. Returns the headless launcher.
pub fn install(store: &Path, cancel: Option<Cancel>, progress: &dyn Fn(&str, u64, Option<u64>)) -> Result<PathBuf, ToolError> {
    let (Some(ghidra), Some(java)) = (pin(ID), pin("java")) else {
        return Err(ToolError::new(ErrorCode::NotSupported, "Ghidra can't be installed for you on this computer.")
            .with_remediation(format!("Install Ghidra {VERSION} from {PAGE}, then choose its folder in Settings → Engines.")));
    };
    if java_home(None, store).is_none() {
        fetch(java, store, "jdk", "Java runtime", cancel.clone(), progress)?;
    }
    fetch(ghidra, store, "ghidra", "Ghidra", cancel, progress)?;
    let exe =
        headless(None, store).ok_or_else(|| ToolError::new(ErrorCode::GarbledOutput, "Ghidra was unpacked, but its launcher wasn't where we expected."))?;
    if let (Some(java), Some(support)) = (java_home(None, store), exe.parent()) {
        point_at_java(&support.join("launch.properties"), &java)?;
    }
    Ok(exe)
}

/// One pinned archive: download beside the store (hashed as it streams; a mismatch deletes it),
/// unpack into a temporary folder and only then swap it in as `<store>/<folder>`.
fn fetch(pin: &crate::Pin, store: &Path, folder: &str, what: &str, cancel: Option<Cancel>, progress: &dyn Fn(&str, u64, Option<u64>)) -> Result<(), ToolError> {
    std::fs::create_dir_all(store).map_err(|e| ToolError::io(store.display(), e))?;
    let archive = store.join(format!(".{folder}.archive"));
    crate::install::download_verified(pin.url, &archive, pin.sha256, 1 << 30, cancel.as_ref(), &|got, total| progress(what, got, total))?;
    progress(&format!("Setting up {what}"), 0, None);
    let data = std::fs::read(&archive).map_err(|e| ToolError::io(archive.display(), e));
    let _ = std::fs::remove_file(&archive);
    let data = data?;
    let incoming = store.join(format!(".{folder}.incoming"));
    let _ = std::fs::remove_dir_all(&incoming);
    let dest = store.join(folder);
    let swapped = crate::install::unpack(&data, pin.format, &incoming, pin.strip_prefix, cancel.as_ref(), &|_| {}).and_then(|_| {
        let _ = std::fs::remove_dir_all(&dest);
        std::fs::rename(&incoming, &dest).map_err(|e| ToolError::io(dest.display(), e))
    });
    if swapped.is_err() {
        let _ = std::fs::remove_dir_all(&incoming);
    }
    swapped
}

/// Ghidra's supported way to choose its Java: `JAVA_HOME_OVERRIDE` in support/launch.properties.
fn point_at_java(props: &Path, java: &Path) -> Result<(), ToolError> {
    // Forward slashes: Ghidra reads this file without escapes, and Java takes them on Windows too.
    let line = format!("JAVA_HOME_OVERRIDE={}", java.display().to_string().replace('\\', "/"));
    let old = std::fs::read_to_string(props).unwrap_or_default();
    let mut lines: Vec<String> = old.lines().filter(|l| !l.trim_start().starts_with("JAVA_HOME_OVERRIDE")).map(str::to_string).collect();
    lines.push(line);
    std::fs::write(props, lines.join("\n") + "\n").map_err(|e| ToolError::io(props.display(), e))
}

fn launcher(root: &Path) -> Option<PathBuf> {
    let names: &[&str] = if cfg!(windows) { &["analyzeHeadless.bat"] } else { &["analyzeHeadless"] };
    names.iter().map(|n| root.join("support").join(n)).find(|p| p.is_file())
}

fn has_java(dir: &Path) -> bool {
    dir.join("bin").join(if cfg!(windows) { "java.exe" } else { "java" }).is_file()
}

/// `find` on `dir` itself, else on its sub-folders (a zip unpacks into one top folder).
fn in_root_or_child(dir: &Path, find: impl Fn(&Path) -> Option<PathBuf>) -> Option<PathBuf> {
    find(dir).or_else(|| in_child(dir, find))
}

fn in_child(dir: &Path, find: impl Fn(&Path) -> Option<PathBuf>) -> Option<PathBuf> {
    let mut subs: Vec<PathBuf> = std::fs::read_dir(dir).ok()?.flatten().map(|e| e.path()).filter(|p| p.is_dir()).collect();
    subs.sort();
    subs.iter().rev().find_map(|d| find(d))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn touch(p: &Path) {
        std::fs::create_dir_all(p.parent().unwrap()).unwrap();
        std::fs::write(p, b"x").unwrap();
    }

    #[test]
    fn a_macos_jdk_unpacks_to_a_java_home_we_find() {
        use craft_anything_testkit::firmware as fx;
        let pin = crate::engine("java").and_then(|e| e.pin_for("macos", "aarch64")).unwrap();
        let java = if cfg!(windows) { "java.exe" } else { "java" };
        let tar = fx::tar_entries(&[
            ("jdk-21.0.12.1+1/Contents/Info.plist", b'0', b"<plist/>", ""),
            (&format!("jdk-21.0.12.1+1/Contents/Home/bin/{java}"), b'0', b"java", ""),
            ("jdk-21.0.12.1+1/Contents/Home/lib/modules", b'0', b"m", ""),
        ]);
        let store = tempfile::tempdir().unwrap();
        let jdk = store.path().join("jdk");
        crate::install::unpack(&fx::gzip(&tar, None), pin.format, &jdk, pin.strip_prefix, None, &|_| {}).unwrap();
        assert_eq!(java_home(None, store.path()), Some(jdk.join("Home")));
        let linux = crate::engine("java").and_then(|e| e.pin_for("linux", "x86_64")).unwrap();
        assert_eq!((linux.format, linux.strip_prefix), (crate::ArchiveFormat::TarGz, None), "Linux keeps jdk-…/bin/java, one folder down");
    }

    #[test]
    fn finds_ghidra_and_java_where_they_really_live() {
        let d = tempfile::tempdir().unwrap();
        let store = d.path().join("store");
        let exe = if cfg!(windows) { "analyzeHeadless.bat" } else { "analyzeHeadless" };
        // None, unless this computer has Ghidra on PATH or from a system package.
        let installed = crate::find_on_path(&[exe]).is_some() || crate::well_known(ID).iter().any(|p| p.is_file());
        assert!(headless(None, &store).is_none() || installed);
        // The managed install: the zip's own top folder under <store>/ghidra.
        let managed = store.join("ghidra/ghidra_12.1.4_PUBLIC/support").join(exe);
        touch(&managed);
        assert_eq!(headless(None, &store), Some(managed));
        // A folder the person picked wins, whether it's Ghidra's folder or the one holding it.
        let own = d.path().join("tools/ghidra_11.4/support").join(exe);
        touch(&own);
        assert_eq!(headless(Some(&d.path().join("tools/ghidra_11.4")), &store), Some(own.clone()));
        assert_eq!(headless(Some(&d.path().join("tools")), &store), Some(own));

        assert!(java_home(None, &store).is_none());
        let jdk = store.join("jdk/jdk-21.0.12.1+1");
        touch(&jdk.join("bin").join(if cfg!(windows) { "java.exe" } else { "java" }));
        assert_eq!(java_home(None, &store), Some(jdk));
        assert_eq!(java_home(Some(d.path()), &store).as_deref(), Some(d.path()), "a Java the person set wins");
    }

    #[test]
    fn ghidra_is_pointed_at_our_java() {
        let d = tempfile::tempdir().unwrap();
        let props = d.path().join("launch.properties");
        std::fs::write(&props, "VMARGS=-Xshare:off\nJAVA_HOME_OVERRIDE=\n").unwrap();
        point_at_java(&props, Path::new(r"C:\store\jdk\jdk-21")).unwrap();
        let text = std::fs::read_to_string(&props).unwrap();
        assert_eq!(text, "VMARGS=-Xshare:off\nJAVA_HOME_OVERRIDE=C:/store/jdk/jdk-21\n");
    }

    #[test]
    fn pins_come_from_the_engine_table() {
        // Checksum handling is tested once, in `install` (download_verified).
        let ghidra = crate::engine("ghidra").unwrap().pins();
        assert!(ghidra.iter().all(|p| p.url.contains(VERSION)));
        let java_pinned = cfg!(any(
            all(windows, target_arch = "x86_64"),
            all(any(target_os = "linux", target_os = "macos"), any(target_arch = "x86_64", target_arch = "aarch64"))
        ));
        assert_eq!(can_install(), java_pinned);
    }
}
