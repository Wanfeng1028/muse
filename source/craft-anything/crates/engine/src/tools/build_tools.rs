//! A builder's own hands, for coding agents that don't bring their own (an API-key model driven
//! by our agent loop): list, read, write and edit files in the project it's building, and run its
//! build commands. They work in the session's workspace (the one a rebuild run attached), paths
//! relative to its folder. Writes and commands go through the same approval policy as Claude
//! Code's (`interaction_tools::approve`): edits inside app/ and the usual build commands go ahead,
//! dev servers are refused, anything else asks the person (or goes ahead in Auto mode, except
//! what's never done unasked). Ids follow docs/tool-ids.md.

use super::interaction_tools::{approve, inbox, inside, resolve, workspace_of};
use crate::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use crate::workspace::Workspace;
use craft_anything_evidence::{ErrorCode, ToolError};
use craft_anything_platform::process::Process;
use schemars::JsonSchema;
use serde::Deserialize;
use serde_json::{Value, json};
use std::path::{Path, PathBuf};
use std::time::Duration;

/// Largest file one read returns (the rest is paged with offset/limit).
const MAX_READ: usize = 256 * 1024;
/// Largest file a write may create.
const MAX_WRITE: usize = 8 * 1024 * 1024;
/// Most entries one listing returns.
const MAX_ENTRIES: usize = 2_000;
/// Output kept from a command (its tail, where errors are).
const OUTPUT_TAIL: usize = 24 * 1024;

pub fn specs() -> Vec<ToolSpec> {
    let spec = |id, title, summary, beginner, effects, schema, run| ToolSpec {
        id,
        title,
        summary,
        beginner,
        toolset: Toolset::Build,
        effects,
        requires: Requires::Nothing,
        input_schema: schema,
        run,
    };
    vec![
        spec(
            "build_files_list",
            "List project files",
            "List files and folders in the project being built (default: app/), a few levels deep. Paths are relative to the project folder; build output and dependencies (node_modules, target, dist…) are skipped.",
            "Shows the files being built.",
            Effects::READ_ONLY,
            schema_of::<ListParams>,
            build_files_list,
        ),
        spec(
            "build_file_read",
            "Read a project file",
            "Read a text file in the project (app/, capture/, reference/…), paged by lines with offset/limit for big files.",
            "Reads one of the project's files.",
            Effects::READ_ONLY,
            schema_of::<ReadParams>,
            build_file_read,
        ),
        spec(
            "build_file_write",
            "Write a project file",
            "Create or replace a text file. Inside app/ this goes ahead; anywhere else asks the person.",
            "Writes one of the project's files.",
            Effects::WRITES_FILESYSTEM,
            schema_of::<WriteParams>,
            build_file_write,
        ),
        spec(
            "build_file_edit",
            "Edit a project file",
            "Replace exact text in a file: old_text must appear exactly once (or set replace_all). Inside app/ this goes ahead; anywhere else asks the person.",
            "Changes part of one of the project's files.",
            Effects::WRITES_FILESYSTEM,
            schema_of::<EditParams>,
            build_file_edit,
        ),
        spec(
            "build_checklist",
            "Update the checklist",
            "Show the person your plan as a short checklist and keep it current: todos with content (a plain step), activeForm (\"Drawing the map\") and status (pending, in_progress or completed). Call it again whenever a step changes; the app pins it above the prompt box.",
            "Shows the builder's plan as a checklist.",
            Effects::CHANGES_UI_STATE,
            schema_of::<ChecklistParams>,
            build_checklist,
        ),
        spec(
            "build_command_run",
            "Run a build command",
            "Run a command in app/ (npm install, npm run build, cargo build, the game engine's build…) and return its exit code and the end of its output. Common build commands go ahead; dev servers and watchers are refused (they never exit); anything else asks the person. Default limit 10 minutes, at most 2 hours.",
            "Runs a build step.",
            Effects::LAUNCHES_PROCESS.union(Effects::WRITES_FILESYSTEM).union(Effects::EXECUTES_FOREIGN_CODE),
            schema_of::<CommandParams>,
            build_command_run,
        ),
    ]
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ListParams {
    /// A folder relative to the project (default `app`).
    #[serde(default)]
    pub path: Option<String>,
    /// How many levels down (default 4, at most 8).
    #[serde(default)]
    pub depth: Option<usize>,
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ReadParams {
    /// A file relative to the project, e.g. `app/src/main.rs` or `capture/README.md`.
    pub path: String,
    /// First line to return (0-based).
    #[serde(default)]
    pub offset: Option<usize>,
    /// How many lines (default: up to 256 KB).
    #[serde(default)]
    pub limit: Option<usize>,
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct WriteParams {
    /// A file relative to the project, e.g. `app/src/main.rs`.
    pub path: String,
    /// The whole new contents.
    pub content: String,
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct EditParams {
    /// A file relative to the project.
    pub path: String,
    /// The exact text to replace.
    pub old_text: String,
    /// What replaces it.
    pub new_text: String,
    /// Replace every occurrence instead of exactly one.
    #[serde(default)]
    pub replace_all: bool,
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ChecklistParams {
    /// The steps, in order.
    pub todos: Vec<Todo>,
}

#[derive(Debug, Deserialize, JsonSchema)]
pub struct Todo {
    /// The step, in plain words.
    pub content: String,
    /// What it says while doing it ("Drawing the map").
    #[serde(default, rename = "activeForm")]
    pub active_form: Option<String>,
    /// `pending`, `in_progress` or `completed`.
    pub status: String,
}

/// The checklist is shown from the call itself (the run folds it into the project's feed); this
/// only checks it and says how far along it is.
fn build_checklist(_ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ChecklistParams = parse_params(params)?;
    if p.todos.is_empty() || p.todos.len() > 30 {
        return Err(ToolError::invalid("Give 1 to 30 steps."));
    }
    if let Some(bad) = p.todos.iter().find(|t| !["pending", "in_progress", "completed"].contains(&t.status.as_str())) {
        return Err(ToolError::invalid(format!("status {:?} must be pending, in_progress or completed", bad.status)));
    }
    let done = p.todos.iter().filter(|t| t.status == "completed").count();
    Ok(ToolOutput::Value(json!({"steps": p.todos.len(), "done": done})))
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct CommandParams {
    /// The command, run in app/ (`&&` joins steps).
    pub command: String,
    /// Time limit in seconds (default 600, at most 7200).
    #[serde(default)]
    pub timeout_secs: Option<u64>,
}

/// The workspace this session is building, from the inbox a rebuild run attached.
fn workspace(ctx: &Ctx<'_>) -> Result<Workspace, ToolError> {
    inbox(ctx).as_ref().and_then(workspace_of).ok_or_else(|| {
        ToolError::new(ErrorCode::FeatureMissing, "These tools work only while a project is being built.")
            .with_remediation("Start a build (rebuild_start or the app), then use them from the builder.")
    })
}

/// `rel` inside the project folder, or an error (no escaping with `..` or an absolute path).
/// Models often write the project's folders from the root (`/app/src/main.rs`): a path like that
/// whose first folder the project has is read inside the project, where it was meant (#24).
fn in_project(ws: &Workspace, rel: &str) -> Result<PathBuf, ToolError> {
    let from_root = rel.trim_start_matches(['/', '\\']);
    let names_a_folder = from_root != rel
        && from_root.split(['/', '\\']).next().is_some_and(|first| !first.is_empty() && (ws.root.join(first).is_dir() || ws.root.join(first) == ws.app_dir()));
    [Some(rel), names_a_folder.then_some(from_root)].into_iter().flatten().find_map(|r| resolve(&ws.root, r).filter(|p| inside(&ws.root, p))).ok_or_else(|| {
        ToolError::invalid(format!("{rel} is outside the project.")).with_remediation("Use a path relative to the project folder, like app/src/main.rs.")
    })
}

fn shown(ws: &Workspace, p: &Path) -> String {
    p.strip_prefix(&ws.root).unwrap_or(p).to_string_lossy().replace('\\', "/")
}

fn refused(why: String) -> ToolError {
    ToolError::new(ErrorCode::ConsentRequired, why)
}

fn build_files_list(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ListParams = parse_params(params)?;
    let ws = workspace(ctx)?;
    let root = in_project(&ws, p.path.as_deref().unwrap_or("app"))?;
    let depth = p.depth.unwrap_or(4).min(8);
    const SKIP: [&str; 8] = ["node_modules", "target", "dist", "build", ".git", "Library", "Temp", "Intermediate"];
    let mut entries = Vec::new();
    let mut stack = vec![(root.clone(), 0usize)];
    let mut truncated = false;
    while let Some((dir, d)) = stack.pop() {
        let mut items: Vec<_> = std::fs::read_dir(&dir).into_iter().flatten().flatten().collect();
        items.sort_by_key(|e| e.file_name());
        for e in items {
            if entries.len() >= MAX_ENTRIES {
                truncated = true;
                break;
            }
            let path = e.path();
            let name = e.file_name().to_string_lossy().into_owned();
            if path.is_dir() {
                entries.push(json!({"path": format!("{}/", shown(&ws, &path))}));
                if d + 1 < depth && !SKIP.contains(&name.as_str()) {
                    stack.push((path, d + 1));
                }
            } else {
                entries.push(json!({"path": shown(&ws, &path), "bytes": e.metadata().map(|m| m.len()).unwrap_or(0)}));
            }
        }
    }
    Ok(ToolOutput::Value(json!({"root": shown(&ws, &root), "entries": entries, "truncated": truncated})))
}

fn build_file_read(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ReadParams = parse_params(params)?;
    let ws = workspace(ctx)?;
    let path = in_project(&ws, &p.path)?;
    let bytes = std::fs::read(&path).map_err(|e| ToolError::io(path.display(), e))?;
    if bytes.iter().take(8000).any(|b| *b == 0) {
        return Err(ToolError::invalid(format!("{} is a binary file.", p.path)).with_remediation("Read text files; look at pictures with your own viewer."));
    }
    let text = String::from_utf8_lossy(&bytes);
    let lines: Vec<&str> = text.lines().collect();
    let start = p.offset.unwrap_or(0).min(lines.len());
    let mut out = String::new();
    let mut n = 0usize;
    let mut cut = false;
    for line in lines.iter().skip(start) {
        if p.limit.is_some_and(|l| n >= l) || (n > 0 && out.len() + line.len() > MAX_READ) {
            break;
        }
        // A line longer than a page comes cut to one, so reading always moves on (#280).
        let part = line.get(..line.floor_char_boundary(MAX_READ)).unwrap_or(line);
        cut |= part.len() < line.len();
        out.push_str(part);
        out.push('\n');
        n += 1;
    }
    let mut v = json!({"path": p.path, "offset": start, "lines": n, "total_lines": lines.len(), "more": start + n < lines.len(), "text": out});
    if cut {
        v["note"] = json!(format!("Line {} is longer than {} KiB, so only its start is shown.", start + 1, MAX_READ / 1024));
    }
    Ok(ToolOutput::Value(v))
}

fn write_checked(ctx: &mut Ctx<'_>, path: &Path, content: &str) -> Result<(), ToolError> {
    if content.len() > MAX_WRITE {
        return Err(ToolError::invalid("That file is too big to write in one go (8 MB at most)."));
    }
    approve(ctx, "Write", &json!({"file_path": path.display().to_string()}))?.map_err(refused)?;
    if let Some(dir) = path.parent() {
        std::fs::create_dir_all(dir).map_err(|e| ToolError::io(dir.display(), e))?;
    }
    crate::project::write_atomic(path, content.as_bytes())
}

fn build_file_write(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: WriteParams = parse_params(params)?;
    let ws = workspace(ctx)?;
    let path = in_project(&ws, &p.path)?;
    write_checked(ctx, &path, &p.content)?;
    let mut out = json!({"written": shown(&ws, &path), "bytes": p.content.len()});
    // A model that leaves out `app/` would otherwise build beside the app, where no check looks.
    if !inside(&ws.app_dir(), &path) {
        out["note"] = json!("This file is outside app/: the app's own files go in app/ (paths like app/package.json).");
    }
    Ok(ToolOutput::Value(out))
}

fn build_file_edit(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: EditParams = parse_params(params)?;
    let ws = workspace(ctx)?;
    let path = in_project(&ws, &p.path)?;
    let text = std::fs::read_to_string(&path).map_err(|e| ToolError::io(path.display(), e))?;
    let count = if p.old_text.is_empty() { 0 } else { text.matches(p.old_text.as_str()).count() };
    let new = match (count, p.replace_all) {
        (0, _) => return Err(ToolError::invalid(format!("old_text isn't in {}.", p.path)).with_remediation("Read the file again and copy the text exactly.")),
        (1, _) | (_, true) => text.replace(p.old_text.as_str(), &p.new_text),
        (n, false) => {
            return Err(ToolError::invalid(format!("old_text appears {n} times in {}.", p.path))
                .with_remediation("Include more surrounding text so it appears once, or set replace_all."));
        }
    };
    write_checked(ctx, &path, &new)?;
    Ok(ToolOutput::Value(json!({"edited": shown(&ws, &path), "replaced": if p.replace_all { count } else { 1 }})))
}

fn build_command_run(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: CommandParams = parse_params(params)?;
    let ws = workspace(ctx)?;
    approve(ctx, "Bash", &json!({"command": p.command}))?.map_err(refused)?;
    let app = ws.app_dir();
    std::fs::create_dir_all(&app).map_err(|e| ToolError::io(app.display(), e))?;
    let (shell, flag) = if cfg!(windows) { ("cmd", "/C") } else { ("sh", "-c") };
    let cancel = ctx.cancel.clone();
    ctx.report(None, format!("Running {}", p.command.chars().take(120).collect::<String>()));
    let out = Process::new(shell)
        .args([flag, p.command.as_str()])
        .cwd(&app)
        .timeout(Duration::from_secs(p.timeout_secs.unwrap_or(600).clamp(1, 7200)))
        .stdout_cap(4 * 1024 * 1024)
        .stderr_cap(4 * 1024 * 1024)
        .cancel_when(move || cancel.is_cancelled())
        .label("the build command")
        .run()?;
    let tail = |s: String| -> String {
        let skip = s.len().saturating_sub(OUTPUT_TAIL);
        let mut start = skip;
        while !s.is_char_boundary(start) {
            start += 1;
        }
        s.get(start..).unwrap_or_default().to_string()
    };
    Ok(ToolOutput::Value(json!({
        "command": p.command,
        "exit_code": out.code,
        "succeeded": out.success,
        "stdout": tail(out.stdout_text()),
        "stderr": tail(out.stderr_text()),
    })))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::inbox::InboxDir;
    use crate::workspace::TargetRef;
    use crate::{CallOptions, Caller, Consent, Engine};
    use std::sync::Arc;

    fn building() -> (std::path::PathBuf, Workspace, Engine) {
        let mut s = crate::testing::session();
        let dir = s.config_dir();
        let ws = Workspace::create(&dir, "Snake", "A snake game", TargetRef::None).unwrap();
        s.ext.insert(Arc::new(InboxDir(ws.inbox_dir())));
        (dir, ws, Engine::new(s))
    }

    fn call(e: &Engine, id: &str, p: Value) -> Result<Value, ToolError> {
        e.call(id, p, CallOptions::new(Caller::Mcp).with_consent(Consent::Granted)).map(|o| o.to_json()["result"].clone())
    }

    #[test]
    fn a_builder_reads_writes_and_edits_inside_its_project() {
        let (_d, ws, e) = building();
        call(&e, "build_file_write", json!({"path": "app/src/main.rs", "content": "fn main() {\n    println!(\"hi\");\n}\n"})).unwrap();
        let r = call(&e, "build_file_read", json!({"path": "app/src/main.rs"})).unwrap();
        assert_eq!(r["total_lines"], 3);
        call(&e, "build_file_edit", json!({"path": "app/src/main.rs", "old_text": "\"hi\"", "new_text": "\"hello\""})).unwrap();
        assert!(std::fs::read_to_string(ws.app_dir().join("src/main.rs")).unwrap().contains("hello"));
        let list = call(&e, "build_files_list", json!({})).unwrap();
        assert!(list["entries"].to_string().contains("app/src/main.rs"), "{list}");
        let page = call(&e, "build_file_read", json!({"path": "app/src/main.rs", "offset": 1, "limit": 1})).unwrap();
        assert_eq!(page["text"], "    println!(\"hello\");\n");
        assert_eq!(page["more"], true);
        // Not found, ambiguous, outside the project.
        assert!(call(&e, "build_file_edit", json!({"path": "app/src/main.rs", "old_text": "nope", "new_text": "x"})).is_err());
        assert!(call(&e, "build_file_read", json!({"path": "../../etc/passwd"})).is_err());
        assert!(call(&e, "build_file_write", json!({"path": "../outside.txt", "content": "x"})).is_err());
    }

    /// #280: a line longer than a page left reading stuck at it, with nothing shown.
    #[test]
    fn a_line_longer_than_a_page_is_shown_cut() {
        let (_d, _ws, e) = building();
        let long = "x".repeat(MAX_READ + 44_000);
        call(&e, "build_file_write", json!({"path": "app/min.js", "content": format!("{long}\nend\n")})).unwrap();
        let first = call(&e, "build_file_read", json!({"path": "app/min.js"})).unwrap();
        assert_eq!((first["lines"].as_u64(), first["more"].as_bool()), (Some(1), Some(true)));
        assert_eq!(first["text"].as_str().map(str::len), Some(MAX_READ + 1));
        assert!(first["note"].as_str().is_some_and(|n| n.contains("Line 1")), "{first}");
        let next = call(&e, "build_file_read", json!({"path": "app/min.js", "offset": 1})).unwrap();
        assert_eq!((next["text"].as_str(), next["more"].as_bool(), next.get("note")), (Some("end\n"), Some(false), None));
    }

    /// #24: a model that writes `/app/…` builds the app, and one that leaves out `app/` is told.
    #[test]
    fn paths_from_the_root_name_the_project_folders() {
        let (_d, ws, e) = building();
        let r = call(&e, "build_file_write", json!({"path": "/app/package.json", "content": "{}"})).unwrap();
        assert_eq!((r["written"].as_str(), r.get("note")), (Some("app/package.json"), None));
        assert!(ws.app_dir().join("package.json").is_file());
        // Backslashes separate folders only on Windows; elsewhere they're part of a name.
        let read = if cfg!(windows) { "\\app\\package.json" } else { "/app/package.json" };
        assert_eq!(call(&e, "build_file_read", json!({"path": read})).unwrap()["text"], "{}\n");
        assert!(call(&e, "build_files_list", json!({"path": "/app"})).unwrap()["entries"].to_string().contains("app/package.json"));
        // A folder the project doesn't have stays outside it.
        assert!(call(&e, "build_file_read", json!({"path": "/etc/passwd"})).is_err());
        assert!(call(&e, "build_file_write", json!({"path": "/nowhere/x.txt", "content": "x"})).is_err());
        assert!(call(&e, "build_file_write", json!({"path": "/../outside.txt", "content": "x"})).is_err());
        let stray = call(&e, "build_file_write", json!({"path": "index.html", "content": "<p>hi</p>"})).unwrap();
        assert!(stray["note"].as_str().unwrap().contains("outside app/"), "{stray}");
    }

    #[test]
    fn writes_outside_app_and_dev_servers_follow_the_policy() {
        let (_d, ws, e) = building();
        // Auto mode is on by default: outside app/ (but inside the project) goes ahead.
        call(&e, "build_file_write", json!({"path": "checks/notes.md", "content": "ok"})).unwrap();
        // The person's own records are never written unasked.
        assert!(call(&e, "build_file_write", json!({"path": "craft.json", "content": "{}"})).is_err());
        assert!(ws.root.join("craft.json").is_file(), "untouched");
        // Dev servers never exit: refused before anything runs.
        let err = call(&e, "build_command_run", json!({"command": "npm run dev"})).unwrap_err();
        assert!(err.message.contains("dev servers"), "{}", err.message);
    }

    #[test]
    fn the_checklist_is_checked() {
        let (_d, _ws, e) = building();
        let ok = call(&e, "build_checklist", json!({"todos": [{"content": "Draw the map", "activeForm": "Drawing the map", "status": "completed"}, {"content": "Add the snake", "status": "in_progress"}]})).unwrap();
        assert_eq!((ok["steps"].as_u64(), ok["done"].as_u64()), (Some(2), Some(1)));
        assert!(call(&e, "build_checklist", json!({"todos": [{"content": "x", "status": "maybe"}]})).is_err());
        assert!(call(&e, "build_checklist", json!({"todos": []})).is_err());
    }

    #[test]
    fn only_while_building() {
        let e = Engine::new(crate::testing::session());
        let err = call(&e, "build_files_list", json!({})).unwrap_err();
        assert_eq!(err.code, ErrorCode::FeatureMissing);
    }
}
