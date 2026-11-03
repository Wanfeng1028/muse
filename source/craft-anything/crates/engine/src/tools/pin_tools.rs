//! Pinned builds as tools: pin a project's build (a frozen or light copy), list pins with what's
//! running, open, stop, rename and remove them. Play shares their run list, so a program runs once
//! per folder unless another copy is asked for. See `crate::pins`.

use crate::pins::{self, Opened, PinMode, Runs};
use crate::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use crate::workspace::Workspace;
use craft_anything_evidence::{ErrorCode, ToolError};
use craft_anything_platform::Launch;
use schemars::JsonSchema;
use serde::Deserialize;
use serde_json::{Value, json};
use std::path::{Path, PathBuf};
use std::sync::Arc;

pub fn specs() -> Vec<ToolSpec> {
    vec![
        ToolSpec {
            id: "project_pin_create",
            title: "Pin a project's build",
            summary: "Keep the project's current build at hand to open later, whatever the builder changes next. `frozen` (the default) copies the app's files and its program into the project's pinned/ folder, without compiler output or dependencies it doesn't start from, so rebuilds can't change or break it. `light` copies the program and the code too but hard-links dependencies and media to the project's, saving their space: replacing or deleting those in the project leaves the pin's as they were, but a file rewritten in place changes in both. With `estimate`, only says what each would take. Websites can't be pinned yet.",
            beginner: "Keeps this version so you can always open it.",
            toolset: Toolset::Projects,
            effects: Effects::WRITES_FILESYSTEM,
            requires: Requires::Nothing,
            input_schema: schema_of::<CreateParams>,
            run: project_pin_create,
        },
        ToolSpec {
            id: "project_pins_list",
            title: "List pinned builds",
            summary: "The pins of one project, or of every project in the project folders from settings: id, name, frozen or light, the round it was pinned at, its size, and whether it's running (started in this session).",
            beginner: "Shows the versions you kept.",
            toolset: Toolset::Projects,
            effects: Effects::READ_ONLY,
            requires: Requires::Nothing,
            input_schema: schema_of::<ListParams>,
            run: project_pins_list,
        },
        ToolSpec {
            id: "project_pin_open",
            title: "Open a pinned build",
            summary: "Start a pinned build in its own window. If it's already running, says so instead of starting a second copy, unless `another` is true (copies of one pin share the files they save beside themselves). A start that quits within two seconds is reported with its exit code and last output. It runs the code the builder wrote, so it needs the person's consent.",
            beginner: "Opens a version you kept.",
            toolset: Toolset::Projects,
            effects: Effects::LAUNCHES_PROCESS.union(Effects::EXECUTES_FOREIGN_CODE),
            requires: Requires::Nothing,
            input_schema: schema_of::<OpenParams>,
            run: project_pin_open,
        },
        ToolSpec {
            id: "project_pin_stop",
            title: "Stop a pinned build",
            summary: "Close what a pin started in this session (every copy of it).",
            beginner: "Closes a version you opened.",
            toolset: Toolset::Projects,
            effects: Effects::MUTATES_SESSION,
            requires: Requires::Nothing,
            input_schema: schema_of::<PinParams>,
            run: project_pin_stop,
        },
        ToolSpec {
            id: "project_pin_rename",
            title: "Rename a pinned build",
            summary: "Give a pin a new name.",
            beginner: "Renames a version you kept.",
            toolset: Toolset::Projects,
            effects: Effects::WRITES_FILESYSTEM,
            requires: Requires::Nothing,
            input_schema: schema_of::<RenameParams>,
            run: project_pin_rename,
        },
        ToolSpec {
            id: "project_pin_delete",
            title: "Remove a pinned build",
            summary: "Remove a pin. Its copy goes with it, including anything the program saved beside itself there, so `confirm` must be true; a running pin is refused until it's stopped.",
            beginner: "Removes a version you kept.",
            toolset: Toolset::Projects,
            effects: Effects::WRITES_FILESYSTEM.union(Effects::MAY_DISCARD_DATA),
            requires: Requires::Nothing,
            input_schema: schema_of::<DeleteParams>,
            run: project_pin_delete,
        },
    ]
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct CreateParams {
    /// The project's folder.
    pub project: PathBuf,
    /// `frozen` (default): a copy of its own; `light`: shares dependencies and media with the
    /// project. `live` was retired and is refused.
    #[serde(default)]
    pub mode: PinMode,
    /// Its name (default: the project's name and round).
    #[serde(default)]
    pub name: Option<String>,
    /// Only say what each kind of copy would take; pin nothing.
    #[serde(default)]
    pub estimate: bool,
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct ListParams {
    /// Only this project's pins (default: every project's).
    #[serde(default)]
    pub project: Option<PathBuf>,
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct PinParams {
    /// The project's folder.
    pub project: PathBuf,
    /// The pin's id (from project_pins_list).
    pub pin: u32,
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct OpenParams {
    /// The project's folder.
    pub project: PathBuf,
    /// The pin's id (from project_pins_list).
    pub pin: u32,
    /// Start another copy even if one is running.
    #[serde(default)]
    pub another: bool,
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct RenameParams {
    /// The project's folder.
    pub project: PathBuf,
    /// The pin's id.
    pub pin: u32,
    /// Its new name.
    pub name: String,
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct DeleteParams {
    /// The project's folder.
    pub project: PathBuf,
    /// The pin's id.
    pub pin: u32,
    /// Must be true: a pin's copy, and what it saved, can't be brought back.
    #[serde(default)]
    pub confirm: bool,
}

fn open_project(project: &Path) -> Result<Workspace, ToolError> {
    Workspace::open(project).map_err(|e| {
        ToolError::new(ErrorCode::NotFound, format!("{} isn't a project folder: {}", project.display(), e.message))
            .with_remediation("Pass a folder from project_list (it holds craft.json).")
    })
}

/// The Godot a Godot project opens in.
pub(crate) fn godot(ctx: &Ctx<'_>) -> Option<PathBuf> {
    let store = ctx.session.settings.engine_store_dir();
    craft_anything_engines::game::inventory(&craft_anything_engines::game::Places::here(store))
        .best(craft_anything_engines::game::Builder::Godot)
        .map(|i| i.program.clone())
}

/// This session's run list (made on first use).
pub(crate) fn runs(ctx: &mut Ctx<'_>) -> Arc<Runs> {
    match ctx.session.ext.get::<Runs>() {
        Some(r) => r,
        None => {
            let r = Arc::new(Runs::default());
            ctx.session.ext.insert(r.clone());
            r
        }
    }
}

/// Start what `app` holds through the run list, logging to `log`, and describe what happened. A
/// program that quit straight away with an error is an error carrying its last output.
pub(crate) fn start(ctx: &mut Ctx<'_>, app: &Path, log: &Path, another: bool, label: &str) -> Result<Value, ToolError> {
    let Some((program, args)) = crate::outputs::launch(app, godot(ctx).as_deref()) else {
        return Err(ToolError::new(ErrorCode::NotFound, "There's nothing to start: no built program here.")
            .with_remediation("Finish a build first (rebuild), or open the folder to look."));
    };
    start_program(ctx, app, log, another, label, (program, args))
}

fn start_program(ctx: &mut Ctx<'_>, app: &Path, log: &Path, another: bool, label: &str, (program, args): (PathBuf, Vec<String>)) -> Result<Value, ToolError> {
    if let Some(dir) = log.parent() {
        std::fs::create_dir_all(dir).map_err(|e| ToolError::io(dir.display(), e))?;
    }
    let launch = Launch::new(&program).args(&args).cwd(app).hide_console().log_to(log).label(label).remediation("Open the folder and start it by hand.");
    let (launched, quit) = match runs(ctx).open(app, launch, another)? {
        Opened::AlreadyRunning(l) => return Ok(json!({"already_running": true, "pid": l.pid(), "started": program.display().to_string()})),
        Opened::Started { launched, quit } => (launched, quit),
    };
    let last_output = pins::tail(log);
    match quit {
        Some(ended) if ended.code != Some(0) => {
            let code = ended.code.map_or_else(|| "it was stopped".to_string(), |c| format!("exit code {c}"));
            let said = if last_output.is_empty() { String::new() } else { format!(" It printed:\n{last_output}") };
            Err(ToolError::new(ErrorCode::ProgramFailed, format!("{label} closed straight away ({code}).{said}"))
                .with_remediation(format!("Its whole output is in {}.", log.display())))
        }
        _ => Ok(json!({
            "already_running": false,
            "started": program.display().to_string(),
            "args": args,
            "pid": launched.pid(),
            "closed_at_once": quit.map(|e| json!({"code": e.code, "after_ms": e.after.as_millis() as u64})),
            "last_output": quit.map(|_| last_output),
        })),
    }
}

fn project_pin_create(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: CreateParams = parse_params(params)?;
    let ws = open_project(&p.project)?;
    let godot = godot(ctx);
    if p.estimate {
        let size = pins::estimate(&ws, godot.as_deref())?;
        return Ok(ToolOutput::Value(json!({"estimate": size})));
    }
    let cancel = ctx.cancel.clone();
    let mut last = std::time::Instant::now();
    let mut progress = |done: u64, total: u64| {
        if last.elapsed().as_millis() >= 250 || done == total {
            last = std::time::Instant::now();
            let fraction = if total == 0 { 1.0 } else { done as f32 / total as f32 };
            ctx.report(Some(fraction), format!("Copying the build: {} of {} MB", done / 1_000_000, total / 1_000_000));
        }
        !cancel.is_cancelled()
    };
    let pin = pins::create(&ws, p.mode, p.name.as_deref(), godot.as_deref(), &mut progress)?;
    Ok(ToolOutput::Value(json!({"pin": pin, "folder": pin.dir(&ws).display().to_string()})))
}

fn project_pins_list(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ListParams = parse_params(params)?;
    let projects = match &p.project {
        Some(dir) => vec![open_project(dir)?],
        None => Workspace::list_in(&ctx.session.settings.project_locations()),
    };
    let runs = runs(ctx);
    let mut out = Vec::new();
    for ws in &projects {
        for pin in pins::list(ws) {
            let running = runs.running(&pin.app_dir(ws));
            out.push(json!({
                "project": ws.root.display().to_string(),
                "project_name": ws.manifest.name,
                "pin": pin,
                "folder": pin.dir(ws).display().to_string(),
                "running": !running.is_empty(),
                "pids": running.iter().map(|l| l.pid()).collect::<Vec<_>>(),
            }));
        }
    }
    Ok(ToolOutput::Value(json!({"count": out.len(), "pins": out})))
}

fn project_pin_open(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: OpenParams = parse_params(params)?;
    let ws = open_project(&p.project)?;
    let pin = pins::get(&ws, p.pin)?;
    let launch = pin.launch(&ws, godot(ctx).as_deref())?;
    let mut out = start_program(ctx, &pin.app_dir(&ws), &pin.log_path(&ws), p.another, &pin.name, launch)?;
    if let Some(o) = out.as_object_mut() {
        o.insert("pin".into(), json!(pin.id));
    }
    Ok(ToolOutput::Value(out))
}

fn project_pin_stop(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: PinParams = parse_params(params)?;
    let ws = open_project(&p.project)?;
    let pin = pins::get(&ws, p.pin)?;
    let stopped = runs(ctx).stop(&pin.app_dir(&ws));
    Ok(ToolOutput::Value(json!({"pin": pin.id, "stopped": stopped})))
}

fn project_pin_rename(_ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: RenameParams = parse_params(params)?;
    let ws = open_project(&p.project)?;
    Ok(ToolOutput::Value(json!({"pin": pins::rename(&ws, p.pin, &p.name)?})))
}

fn project_pin_delete(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: DeleteParams = parse_params(params)?;
    if !p.confirm {
        return Err(ToolError::invalid("Removing a pin can't be undone.").with_remediation("Pass confirm: true to remove it."));
    }
    let ws = open_project(&p.project)?;
    let pin = pins::get(&ws, p.pin)?;
    // An old live pin runs the project's app: what's running there isn't the pin's to keep.
    if pin.mode.keeps_copy() && !runs(ctx).running(&pin.app_dir(&ws)).is_empty() {
        return Err(ToolError::invalid(format!("{} is open.", pin.name)).with_remediation("Close it (project_pin_stop), then remove it."));
    }
    pins::delete(&ws, p.pin)?;
    Ok(ToolOutput::Value(json!({"removed": p.pin})))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::workspace::TargetRef;
    use crate::{CallOptions, Caller, Consent, Engine};

    #[cfg(unix)]
    #[test]
    fn opening_a_pin_keeps_the_program_selected_before_copying() {
        use std::os::unix::fs::PermissionsExt;
        use std::time::{Duration, SystemTime};

        let d = tempfile::tempdir().unwrap();
        let ws = Workspace::create(d.path(), "Game", "a packaged game", TargetRef::None).unwrap();
        let build = ws.app_dir().join("Build");
        std::fs::create_dir_all(build.join("obj")).unwrap();
        let game = build.join("game");
        let helper = build.join("obj/helper");
        for (path, output, seconds) in [(&game, "selected-game", 20), (&helper, "wrong-helper", 10)] {
            std::fs::write(path, format!("#!/bin/sh\nprintf '%s\\n' '{output}'\n")).unwrap();
            std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o755)).unwrap();
            let times = std::fs::FileTimes::new().set_modified(SystemTime::UNIX_EPOCH + Duration::from_secs(seconds));
            std::fs::File::options().write(true).open(path).unwrap().set_times(times).unwrap();
        }
        assert_eq!(crate::outputs::packaged_program(&build), Some(game));
        let e = Engine::new(crate::testing::session());
        let call = |id: &str, params: Value| {
            e.call(id, params, CallOptions::new(Caller::Cli).with_consent(Consent::Granted)).map(|out| out.to_json()["result"].clone())
        };
        for mode in ["frozen", "light"] {
            let made = call("project_pin_create", json!({"project": ws.root, "mode": mode})).unwrap();
            let id = made["pin"]["id"].as_u64().unwrap() as u32;
            let pin = pins::get(&ws, id).unwrap();
            let copy = pin.app_dir(&ws);
            let future = std::fs::FileTimes::new().set_modified(SystemTime::now() + Duration::from_secs(60));
            std::fs::File::options().write(true).open(copy.join("Build/obj/helper")).unwrap().set_times(future).unwrap();
            assert_eq!(crate::outputs::packaged_program(&copy.join("Build")), Some(copy.join("Build/obj/helper")));
            let opened = call("project_pin_open", json!({"project": ws.root, "pin": id})).unwrap();
            assert_eq!(opened["started"], copy.join("Build/game").display().to_string());
            assert_eq!(pins::tail(&pin.log_path(&ws)), "selected-game");
            std::fs::remove_file(copy.join("Build/game")).unwrap();
            assert_eq!(call("project_pin_open", json!({"project": ws.root, "pin": id})).unwrap_err().code, ErrorCode::NotFound);
        }
    }

    #[test]
    fn pin_list_rename_and_remove_from_the_cli() {
        let d = tempfile::tempdir().unwrap();
        let ws = Workspace::create(d.path(), "Snake", "a snake game", TargetRef::None).unwrap();
        let app = ws.app_dir();
        std::fs::create_dir_all(app.join("src")).unwrap();
        std::fs::write(app.join("Cargo.toml"), "[package]\nname = \"snake\"\n").unwrap();
        std::fs::write(app.join("src/main.rs"), "fn main() {}").unwrap();
        std::fs::create_dir_all(app.join("target/debug")).unwrap();
        let program = app.join("target/debug").join(if cfg!(windows) { "snake.exe" } else { "snake" });
        std::fs::write(&program, b"program").unwrap();
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            std::fs::set_permissions(&program, std::fs::Permissions::from_mode(0o755)).unwrap();
        }
        let e = Engine::new(crate::testing::session());
        let call = |id: &str, p: Value| e.call(id, p, CallOptions::new(Caller::Cli).with_consent(Consent::Granted)).map(|o| o.to_json()["result"].clone());

        let est = call("project_pin_create", json!({"project": ws.root, "estimate": true})).unwrap();
        assert!(est["estimate"]["bytes"].as_u64().unwrap() > 0);
        assert!(pins::list(&ws).is_empty(), "an estimate pins nothing");
        let made = call("project_pin_create", json!({"project": ws.root})).unwrap();
        assert_eq!(made["pin"]["mode"], "frozen");
        call("project_pin_create", json!({"project": ws.root, "mode": "light", "name": "Latest"})).unwrap();

        let list = call("project_pins_list", json!({"project": ws.root})).unwrap();
        assert_eq!(list["count"], 2);
        assert_eq!(list["pins"][1]["pin"]["name"], "Latest");
        assert_eq!(list["pins"][0]["running"], false);

        call("project_pin_rename", json!({"project": ws.root, "pin": 1, "name": "Keeper"})).unwrap();
        assert!(call("project_pin_delete", json!({"project": ws.root, "pin": 1})).is_err(), "removing needs confirm");
        call("project_pin_delete", json!({"project": ws.root, "pin": 1, "confirm": true})).unwrap();
        let list = call("project_pins_list", json!({"project": ws.root})).unwrap();
        assert_eq!(list["count"], 1);
        assert_eq!(call("project_pin_open", json!({"project": ws.root, "pin": 1})).unwrap_err().code, ErrorCode::NotFound);
    }
}
