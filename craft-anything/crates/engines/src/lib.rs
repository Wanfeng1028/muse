//! Adapters for optional external engines (Ghidra, adb, Chromium, Frida, JADX…).
//!
//! Every engine is an entry in [`ENGINES`] (see [`table`]). Each is found, in order: the path the
//! user set in Settings → Engines, the managed install in the engine store, `PATH`, then the
//! engine's standard install folders. Nothing here is required for Clean room analysis.
#![deny(clippy::unwrap_used, clippy::expect_used, clippy::panic, clippy::unimplemented, clippy::todo, clippy::unreachable)]

pub mod adb;
pub mod assets;
pub mod cdp;
pub mod cutter;
pub mod frida;
pub mod game;
pub mod gdb;
pub mod ghidra;
pub mod install;
pub mod jadx;
pub mod mcp_client;
pub mod rizin;
pub mod table;
#[cfg(feature = "wasm-plugins")]
pub mod wasm_plugin;

pub use table::{ArchiveFormat, ENGINES, ExternalEngine, Install, Pin};

use std::path::{Path, PathBuf};

/// User overrides, mirrored from the engine settings so this crate doesn't depend on the engine.
pub trait ToolPathLookup {
    fn override_for(&self, id: &str) -> Option<PathBuf>;
}

/// The table entry for an engine id.
pub fn engine(id: &str) -> Option<&'static ExternalEngine> {
    ENGINES.iter().find(|e| e.id == id)
}

/// The ids that have a path override in Settings → Engines, in table order.
pub fn path_setting_ids() -> impl Iterator<Item = &'static str> {
    ENGINES.iter().filter(|e| e.path_setting).map(|e| e.id)
}

pub fn display_name(id: &str) -> &'static str {
    engine(id).map(|e| e.name).unwrap_or("an external tool")
}

/// Find an engine: user override, then the managed store (`<store>/<id>/bin/<exe>`), then PATH,
/// then its standard install folders.
pub fn locate(id: &str, overrides: &dyn ToolPathLookup, store: &Path) -> Option<PathBuf> {
    locate_configured(id, overrides, store).or_else(|| {
        let e = engine(id)?;
        find_on_path(e.host_exes()).or_else(|| e.known_install_paths().into_iter().find(|p| p.is_file()))
    })
}

/// Find an engine where the settings or the managed store say only: what [`locate`] finds before
/// it looks around the computer (PATH and standard install folders).
pub fn locate_configured(id: &str, overrides: &dyn ToolPathLookup, store: &Path) -> Option<PathBuf> {
    if let Some(p) = overrides.override_for(id)
        && p.exists()
    {
        return Some(p);
    }
    let e = engine(id)?;
    let exes = e.host_exes();
    if let Some(p) = in_managed(&store.join(id), exes) {
        return Some(p);
    }
    // A single-file install (a .jar) is found by the name its pin saved it under.
    for pin in e.pins() {
        if let ArchiveFormat::File { name } = pin.format
            && store.join(id).join(name).is_file()
        {
            return Some(store.join(id).join(name));
        }
    }
    None
}

/// An executable in a managed install folder: `<dir>/<exe>`, `<dir>/bin/<exe>` or
/// `<dir>/support/<exe>`, in `dir` itself or in one of its sub-folders, newest name first (an
/// archive unpacks into one top folder, often versioned: `ghidra_12.1.4_PUBLIC/support/…`).
fn in_managed(dir: &Path, exes: &[&str]) -> Option<PathBuf> {
    let here = |d: &Path| exes.iter().flat_map(|exe| [d.join(exe), d.join("bin").join(exe), d.join("support").join(exe)]).find(|p| p.is_file());
    if let Some(p) = here(dir) {
        return Some(p);
    }
    let mut subs: Vec<PathBuf> = std::fs::read_dir(dir).ok()?.flatten().map(|e| e.path()).filter(|p| p.is_dir()).collect();
    subs.sort();
    subs.iter().rev().find_map(|d| here(d))
}

/// Standard install locations for programs that don't put themselves on PATH (browsers on
/// Windows and macOS, Ghidra from Linux packages), most common first.
pub fn well_known(id: &str) -> Vec<PathBuf> {
    engine(id).map(ExternalEngine::known_install_paths).unwrap_or_default()
}

pub(crate) fn find_on_path(exes: &[&str]) -> Option<PathBuf> {
    let path = craft_anything_platform::which::search_path()?;
    for dir in std::env::split_paths(&path) {
        for exe in exes {
            let p = dir.join(exe);
            if p.is_file() {
                return Some(p);
            }
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    struct NoOverrides;
    impl ToolPathLookup for NoOverrides {
        fn override_for(&self, _: &str) -> Option<PathBuf> {
            None
        }
    }

    #[test]
    fn unknown_engine_is_none() {
        assert!(locate("definitely-not-an-engine", &NoOverrides, Path::new("/nonexistent")).is_none());
        assert_eq!(display_name("adb"), "Android platform tools (adb)");
    }

    /// Ghidra's zip unpacks into `<store>/ghidra/ghidra_<version>_PUBLIC/`, with the launcher in
    /// `support/`; `engines_list` said "not found" for an install that Deep mode was using.
    #[test]
    fn a_managed_install_in_a_versioned_folder_is_found() {
        let store = tempfile::tempdir().unwrap();
        let exe = if cfg!(windows) { "analyzeHeadless.bat" } else { "analyzeHeadless" };
        let launcher = store.path().join("ghidra").join("ghidra_12.1.4_PUBLIC").join("support").join(exe);
        std::fs::create_dir_all(launcher.parent().unwrap()).unwrap();
        std::fs::write(&launcher, b"x").unwrap();
        assert_eq!(locate("ghidra", &NoOverrides, store.path()), Some(launcher));
        // An older unpack beside it loses to the newest name.
        let newer = store.path().join("ghidra").join("ghidra_12.2.0_PUBLIC").join("support").join(exe);
        std::fs::create_dir_all(newer.parent().unwrap()).unwrap();
        std::fs::write(&newer, b"x").unwrap();
        assert_eq!(locate("ghidra", &NoOverrides, store.path()), Some(newer));
        // Nothing but folders: still none, not a panic.
        let empty = tempfile::tempdir().unwrap();
        std::fs::create_dir_all(empty.path().join("ghidra").join("ghidra_12.1.4_PUBLIC")).unwrap();
        // (Unless this computer has Ghidra on PATH or from a system package.)
        let installed = find_on_path(&[exe]).is_some() || well_known("ghidra").iter().any(|p| p.is_file());
        assert!(locate("ghidra", &NoOverrides, empty.path()).is_none() || installed);
    }

    #[test]
    fn browsers_have_well_known_locations_off_path() {
        assert!(well_known("adb").is_empty());
        let paths = well_known("chromium");
        if cfg!(any(windows, target_os = "macos")) {
            assert!(paths.iter().any(|p| p.to_string_lossy().contains("Chrome")));
            assert!(paths.iter().any(|p| p.to_string_lossy().contains("Edge")));
        }
        // #85: Linux packages put Ghidra in its own folder with only a start script on PATH.
        let ghidra = well_known("ghidra");
        if cfg!(target_os = "linux") {
            assert_eq!(ghidra, [PathBuf::from("/opt/ghidra/support/analyzeHeadless"), PathBuf::from("/usr/share/ghidra/support/analyzeHeadless")]);
        } else {
            assert!(ghidra.is_empty());
        }
    }
}
