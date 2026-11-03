//! Live end-to-end rebuild with a real coding agent. Opt-in: it needs network access, a
//! signed-in Claude Code (`claude auth login`) and spends the person's usage, so it only runs
//! with `CRAFT_E2E=1`:
//!
//! ```sh
//! CRAFT_E2E=1 cargo test -p craft-anything-cli --test live_rebuild -- --nocapture
//! ```

use craft_anything_platform::process::Process;
use serde_json::Value;
use std::time::Duration;

fn enabled() -> bool {
    let on = std::env::var("CRAFT_E2E").is_ok_and(|v| v == "1");
    if !on {
        eprintln!("skipped: set CRAFT_E2E=1 to run the live rebuild");
    }
    on
}

#[test]
fn website_clone_reaches_ready_and_looks_alike() {
    if !enabled() {
        return;
    }
    let projects = tempfile::tempdir().unwrap();
    let out = Process::new(env!("CARGO_BIN_EXE_craft-anything-cli"))
        .args(["rebuild", "https://example.com", "Clone this website", "--rounds", "1", "--unattended", "--format", "text"])
        .arg("--projects-dir")
        .arg(projects.path())
        .timeout(Duration::from_secs(45 * 60))
        .idle_timeout(Duration::from_secs(15 * 60))
        .run()
        .unwrap();
    let log = out.stdout_text();
    assert!(out.success, "rebuild failed:\n{log}");

    let dirs: Vec<_> = std::fs::read_dir(projects.path()).unwrap().filter_map(Result::ok).filter(|e| e.path().is_dir()).collect();
    assert_eq!(dirs.len(), 1, "one project folder");
    let root = dirs[0].path();
    let manifest: Value = serde_json::from_slice(&std::fs::read(root.join("craft.json")).unwrap()).unwrap();
    assert_eq!(manifest["status"], "ready", "{log}");
    assert_eq!(manifest["target"]["kind"], "website");
    let best = manifest["checks"].as_array().unwrap().iter().filter_map(|c| c["similarity"].as_f64()).fold(0.0, f64::max);
    assert!(best >= 80.0, "best likeness {best:.0}%:\n{log}");
    assert!(["dist", "out", "build"].iter().any(|d| root.join("app").join(d).join("index.html").is_file()), "a built site in app/dist, app/out or app/build");
}
