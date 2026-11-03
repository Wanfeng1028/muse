//! A picture of a program while it runs: start it, wait for its window, picture the window and
//! close the program. For studying how an app or game looks (R2.4) and, later, comparing a rebuild
//! with it. It runs the program, so it needs the person's consent. Ids follow docs/tool-ids.md.

use super::web_common::{Image, encode_png, png_artifact};
use crate::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use craft_anything_evidence::{Confidence, Coverage, ErrorCode, EvidenceBuilder, Location, Subject, ToolError};
use craft_anything_platform::process::Process;
use schemars::JsonSchema;
use serde::Deserialize;
use serde_json::{Value, json};
use std::path::PathBuf;
use std::time::{Duration, Instant};

/// Largest picture kept inline in the evidence (bigger ones are only written to `output`).
const MAX_INLINE: usize = 8 * 1024 * 1024;
/// Most UI elements saved to `ui_tree`.
const UI_TREE_NODES: usize = 1000;

pub fn specs() -> Vec<ToolSpec> {
    vec![ToolSpec {
        id: "native_window_capture",
        title: "Picture a program's window",
        summary: "Start a program (an app or a game), wait for its window, take a picture of it and close the program (Windows and macOS). Optionally save the PNG to `output`, and the UI tree of its windows (as runtime_ui_read reads it; Windows and macOS) to `ui_tree` as JSON. It runs the program, so it needs consent.",
        beginner: "Opens a program for a few seconds and takes a picture of its window.",
        toolset: Toolset::Runtime,
        effects: Effects::LAUNCHES_PROCESS.union(Effects::EXECUTES_FOREIGN_CODE).union(Effects::WRITES_FILESYSTEM).union(Effects::MUTATES_SESSION),
        requires: Requires::Nothing,
        input_schema: schema_of::<CaptureParams>,
        run: native_window_capture,
    }]
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct CaptureParams {
    /// The program to start (an absolute path).
    pub program: PathBuf,
    /// Arguments for it.
    #[serde(default)]
    pub args: Vec<String>,
    /// Seconds to let it start and draw before the picture (default 8, at most 120).
    #[serde(default)]
    pub wait_secs: Option<u64>,
    /// Save the picture here as a PNG (an absolute path; its folder must exist).
    #[serde(default)]
    pub output: Option<PathBuf>,
    /// Also save the UI tree of its windows here as JSON, read just before it's closed (an
    /// absolute path; its folder must exist). Windows and macOS.
    #[serde(default)]
    pub ui_tree: Option<PathBuf>,
}

fn native_window_capture(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: CaptureParams = parse_params(params)?;
    if !p.program.is_absolute() || !p.program.is_file() {
        return Err(
            ToolError::invalid(format!("{} isn't a program file.", p.program.display())).with_remediation("Pass the full path of the program to start.")
        );
    }
    if p.ui_tree.as_ref().is_some_and(|t| !t.is_absolute()) {
        return Err(ToolError::invalid("ui_tree must be an absolute path"));
    }
    // Refused before the program starts where no picture can be taken.
    if !craft_anything_platform::window::SUPPORTED {
        return Err(craft_anything_platform::window::unsupported());
    }
    let wait = Duration::from_secs(p.wait_secs.unwrap_or(8).clamp(1, 120));
    let dir = p.program.parent().map(PathBuf::from).unwrap_or_default();
    let cancel = ctx.cancel.clone();
    ctx.report(None, format!("Starting {} for {} s…", p.program.display(), wait.as_secs()));
    let mut running = Process::new(&p.program)
        .args(&p.args)
        .cwd(&dir)
        .timeout(wait + Duration::from_secs(60))
        .stdout_cap(64 * 1024)
        .cancel_when(move || cancel.is_cancelled())
        .label("the program")
        .spawn()?;
    let started = Instant::now();
    while started.elapsed() < wait {
        if ctx.cancel.is_cancelled() {
            running.kill_and_wait(Duration::from_secs(10));
            return Err(ToolError::cancelled());
        }
        if running.is_finished() {
            break;
        }
        std::thread::sleep(Duration::from_millis(200));
    }
    let name = p.program.file_stem().map(|s| s.to_string_lossy().into_owned());
    let shot = craft_anything_platform::window::capture_window(running.pid(), name.as_deref());
    // Read while it still runs; a tree that can't be read is only left out.
    let tree = p.ui_tree.as_ref().map(|_| super::apple_runtime::ui_tree(ctx, running.pid(), UI_TREE_NODES));
    // Always closed again, picture or not, and confirmed before we return (a caller such as the
    // CLI may exit right after, before a background kill would happen).
    if !running.kill_and_wait(Duration::from_secs(10)) {
        log::warn!("{} may still be running", p.program.display());
    }
    let shot = shot?;
    let png = encode_png(&Image { width: shot.width, height: shot.height, rgba: shot.rgba })?;
    if let Some(out) = &p.output {
        if !out.is_absolute() {
            return Err(ToolError::invalid("output must be an absolute path"));
        }
        crate::project::write_atomic(out, &png)?;
    }
    let mut result = json!({"title": shot.title, "app": shot.app, "width": shot.width, "height": shot.height, "after_secs": started.elapsed().as_secs()});
    if let Some(o) = result.as_object_mut() {
        if let Some(out) = &p.output {
            o.insert("output".into(), json!(out.display().to_string()));
        }
        if png.len() <= MAX_INLINE {
            o.insert("screenshot".into(), png_artifact(&png)?);
        }
        match (&p.ui_tree, tree) {
            (Some(path), Some(Ok(tree))) => {
                let json = serde_json::to_vec_pretty(&tree).map_err(|e| ToolError::internal(e.to_string()))?;
                crate::project::write_atomic(path, &json)?;
                let nodes = tree.get("nodes").and_then(Value::as_array).map_or(0, Vec::len);
                o.insert("ui_tree".into(), json!({"path": path.display().to_string(), "nodes": nodes}));
            }
            (_, Some(Err(e))) => {
                o.insert("ui_tree_error".into(), json!(e.message));
            }
            _ => {}
        }
    }
    let mut b =
        EvidenceBuilder::new("native_window_capture", Subject { kind: "program".into(), sha256: None, name: name.clone() }, super::artifact_tools::env(ctx))
            .params(json!({"program": p.program.display().to_string(), "args": p.args, "wait_secs": wait.as_secs()}))
            .result(result)
            .summary(format!("Pictured \"{}\" ({}×{}) after {} s.", shot.title, shot.width, shot.height, started.elapsed().as_secs()))
            .confidence(Confidence::Observed)
            .coverage(Coverage::complete(1));
    if let Some(out) = &p.output {
        b = b.location(Location::new("path", out.to_string_lossy()));
    }
    let ev = b.build().map_err(|e| ToolError::new(ErrorCode::Internal, e.message))?;
    Ok(ToolOutput::evidence(ev))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{CallOptions, Caller, Consent, Engine};

    #[test]
    fn it_needs_consent_and_a_real_program() {
        let e = Engine::new(crate::testing::session());
        let p = json!({"program": std::env::temp_dir().join("no-such-program.exe")});
        assert_eq!(e.call("native_window_capture", p.clone(), CallOptions::new(Caller::Mcp)).unwrap_err().code, ErrorCode::ConsentRequired);
        let granted = CallOptions::new(Caller::Mcp).with_consent(Consent::Granted);
        assert!(e.call("native_window_capture", p, granted).unwrap_err().message.contains("isn't a program file"));
        let exe = std::env::current_exe().unwrap();
        let relative = json!({"program": exe, "ui_tree": "tree.json"});
        assert!(
            e.call("native_window_capture", relative, CallOptions::new(Caller::Mcp).with_consent(Consent::Granted)).unwrap_err().message.contains("ui_tree"),
            "checked before anything starts"
        );
        // Where windows can't be pictured, nothing is started.
        if !craft_anything_platform::window::SUPPORTED {
            let err = e.call("native_window_capture", json!({"program": exe}), CallOptions::new(Caller::Mcp).with_consent(Consent::Granted)).unwrap_err();
            assert_eq!(err.code, ErrorCode::FeatureMissing);
        }
    }
}
