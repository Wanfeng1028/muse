//! Helpers for tests in this and other crates. Tests never touch the real machine
//! (docs/pitfalls.md): use [`session`] instead of `Session::default()`, which points at this
//! computer's config folder and engine store.

use crate::Session;
use std::path::PathBuf;
use std::sync::atomic::{AtomicUsize, Ordering};

/// A fresh folder under the system temp folder, unique to this test process and call.
pub fn temp_dir() -> PathBuf {
    static N: AtomicUsize = AtomicUsize::new(0);
    let dir = std::env::temp_dir().join(format!("craft-anything-test-{}-{}", std::process::id(), N.fetch_add(1, Ordering::SeqCst)));
    let _ = std::fs::create_dir_all(&dir);
    dir
}

/// A session whose config, plugin caches, engine store and projects live in a fresh temp folder.
/// It is in Deep mode, so tools may look inside the sample targets tests open; a test of Clean room
/// turns `deep_mode` off. It finds no engine this computer has on PATH or in the usual install
/// folders (`engines.only_configured`), so a test behaves the same whether Ghidra or adb is
/// installed; a test that needs an engine points the settings or the store at one.
pub fn session() -> Session {
    let mut s = Session::isolated(&temp_dir());
    s.settings.deep_mode = true;
    s.settings.engines.only_configured = true;
    s
}

/// A [`session`] that finds the engines this computer has installed, for the `#[ignore]` tests
/// that run a real one (a browser, Ghidra).
pub fn live_session() -> Session {
    let mut s = session();
    s.settings.engines.only_configured = false;
    s
}
