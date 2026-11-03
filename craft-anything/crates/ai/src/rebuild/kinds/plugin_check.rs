//! Checks from WASM plugins (`craft-anything:plugin/checks`), run after a kind's own checks. A
//! plugin can't read files, so it gets the build as JSON: every file's path and size, and the text
//! of the files with the extensions it asked for (capped). A plugin that fails to run doesn't fail
//! the build: its result passes with a note saying why, so the builder isn't sent to fix it.

use super::*;
use craft_anything_engine::wasm_plugins::PluginCheck;
use std::sync::Arc;

/// Files listed per build.
const MAX_FILES: usize = 20_000;
/// Text given per file, and in all.
const MAX_TEXT: u64 = 256 << 10;
const MAX_TOTAL_TEXT: u64 = 8 << 20;
/// Folders of dependencies, caches and build output, left out of the listing.
const SKIP_DIRS: &[&str] = &[
    "node_modules",
    "target",
    ".git",
    "dist",
    "build",
    "Library",
    "Temp",
    "obj",
    "bin",
    ".godot",
    "Intermediate",
    "Saved",
    "DerivedDataCache",
    "__pycache__",
    ".venv",
];

/// A plugin check for one kind of project.
pub struct PluginJudge {
    pub check: Arc<PluginCheck>,
    pub kind: &'static str,
}

impl Check for PluginJudge {
    fn id(&self) -> &'static str {
        self.check.id
    }

    fn run(&self, cx: &mut CheckCx) -> Result<CheckResult, ToolError> {
        Ok(self.judge(cx.ws, cx.round))
    }
}

impl PluginJudge {
    /// The plugin's verdict on the build in `ws`, for round `round`.
    fn judge(&self, ws: &Workspace, round: u32) -> CheckResult {
        let build = build_json(ws, self.kind, round, &self.check.extensions);
        match self.check.run(&build) {
            Ok(v) => {
                let passed = v.get("passed").and_then(Value::as_bool).unwrap_or(false);
                let summary = v.get("summary").and_then(Value::as_str).unwrap_or(if passed { "Passed." } else { "Didn't pass." });
                let similarity = v.get("similarity").and_then(Value::as_f64).filter(|s| s.is_finite()).map(|s| s.clamp(0.0, 100.0));
                CheckResult { similarity, ..CheckResult::new(self.check.id, round, passed, format!("{}: {summary}", self.check.title)) }
            }
            Err(e) => CheckResult::new(self.check.id, round, true, format!("The {} check couldn't run: {}", self.check.title, e.message)),
        }
    }
}

/// The build as a plugin check sees it (see plugin.wit).
pub fn build_json(ws: &Workspace, kind: &str, round: u32, extensions: &[String]) -> Value {
    let app = ws.app_dir();
    let mut files = Vec::new();
    let mut truncated = false;
    let mut text_total = 0u64;
    let mut stack = vec![(app.clone(), 0usize)];
    let mut found: Vec<(String, PathBuf, u64)> = Vec::new();
    while let Some((dir, depth)) = stack.pop() {
        let Ok(rd) = std::fs::read_dir(&dir) else { continue };
        for entry in rd.flatten() {
            let path = entry.path();
            let Ok(meta) = entry.metadata() else { continue };
            if meta.is_dir() {
                let name = entry.file_name();
                if depth < 32 && !SKIP_DIRS.iter().any(|d| name.to_str() == Some(*d)) {
                    stack.push((path, depth + 1));
                }
                continue;
            }
            if found.len() >= MAX_FILES {
                truncated = true;
                continue;
            }
            let rel = path.strip_prefix(&app).unwrap_or(&path).to_string_lossy().replace('\\', "/");
            found.push((rel, path, meta.len()));
        }
    }
    found.sort_by(|a, b| a.0.cmp(&b.0));
    for (rel, path, size) in found {
        let wanted = path.extension().and_then(|e| e.to_str()).is_some_and(|e| extensions.iter().any(|x| x.trim_start_matches('.').eq_ignore_ascii_case(e)));
        let mut entry = json!({"path": rel, "size": size});
        if wanted {
            if size > MAX_TEXT || text_total + size > MAX_TOTAL_TEXT {
                truncated = true;
            } else if let Ok(text) = std::fs::read_to_string(&path) {
                text_total += size;
                entry["text"] = json!(text);
            }
        }
        files.push(entry);
    }
    json!({
        "request": ws.manifest.request,
        "kind": kind,
        "stack": ws.manifest.stack,
        "round": round,
        "files": files,
        "truncated": truncated,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use craft_anything_engine::workspace::TargetRef;

    #[test]
    fn a_plugin_sees_the_files_and_the_text_it_asked_for() {
        let d = tempfile::tempdir().unwrap();
        let ws = Workspace::create(d.path(), "Game", "A snake game", TargetRef::None).unwrap();
        let app = ws.app_dir();
        std::fs::create_dir_all(app.join("src")).unwrap();
        std::fs::create_dir_all(app.join("node_modules/x")).unwrap();
        std::fs::write(app.join("README.md"), "# Snake").unwrap();
        std::fs::write(app.join("src/main.rs"), "fn main() {}").unwrap();
        std::fs::write(app.join("node_modules/x/index.js"), "x").unwrap();
        let b = build_json(&ws, "game", 2, &["md".into()]);
        assert_eq!((b["kind"].clone(), b["round"].clone(), b["request"].clone()), (json!("game"), json!(2), json!("A snake game")));
        assert_eq!(b["files"], json!([{"path": "README.md", "size": 7, "text": "# Snake"}, {"path": "src/main.rs", "size": 12}]), "dependencies are left out");
    }

    #[test]
    fn a_plugin_that_fails_to_run_doesnt_fail_the_build() {
        let d = tempfile::tempdir().unwrap();
        let ws = Workspace::create(d.path(), "Game", "A snake game", TargetRef::None).unwrap();
        let judge = |answer: Result<Value, ToolError>| {
            let check = PluginCheck::new("judge_style", "Style", Vec::new(), Vec::new(), move |_| answer.clone());
            PluginJudge { check: Arc::new(check), kind: "game" }
        };
        let r = judge(Ok(json!({"passed": false, "similarity": 140, "summary": "No title screen."}))).judge(&ws, 1);
        assert_eq!((r.passed, r.similarity, r.note.as_str()), (false, Some(100.0), "Style: No title screen."));
        let r = judge(Err(ToolError::invalid("boom"))).judge(&ws, 1);
        assert!(r.passed && r.similarity.is_none() && r.note.contains("couldn't run: boom"), "{r:?}");
    }
}
