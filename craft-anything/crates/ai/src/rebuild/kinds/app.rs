//! Desktop apps: the fallback kind. Checked by building; in Deep mode the builder must
//! decompile a program target first and keep the mechanics sheet, which is checked too.

use super::*;

pub struct AppKind;

/// What a console program's brief asks for, instead of a picture.
pub const RUNS_BRIEF: &str = "The original is a console program, so it's compared by its runs: capture/runs/ holds, for each input it was run with, what it printed and how it exited. Make the rebuild a console program that prints the same text for each input (its own name may differ) and exits the same way. Craft Anything runs yours with the same inputs after each build and checks each one; rebuild_check shows you the result while you work.";

impl AppKind {
    pub const ID: &'static str = "app";
}

impl TargetKind for AppKind {
    fn id(&self) -> &'static str {
        Self::ID
    }

    fn words(&self) -> KindWords {
        KindWords {
            button: "Open the app",
            icon: "app-window",
            ready: "Your app is ready",
            change_hint: "Ask for a change, e.g. \"bigger buttons\" or \"add a dark mode\"",
        }
    }

    fn detect(&self, _cx: &DetectCx) -> Option<u32> {
        // Whatever isn't recognised as something else is an app.
        Some(1)
    }

    /// A console program is rebuilt as one; anything else as a windowed app. Telling them apart
    /// reads the program, so only in Deep mode.
    fn default_stack(&self, cx: &DetectCx) -> &'static str {
        match cx.target {
            TargetRef::Local { path } if cx.deep && runs::is_console(&locate(path, false).0) => "Rust (console)",
            _ => "Rust + egui (eframe)",
        }
    }

    fn goal(&self) -> &'static str {
        "a desktop app with the same core features"
    }

    fn brief_sections(&self, cx: &BriefCx) -> Vec<String> {
        let mut s = Vec::new();
        if cx.deep && matches!(cx.ws.manifest.target, TargetRef::Local { .. }) {
            s.push(decompile_note(false, cx.ghidra).trim_start().to_string());
            s.push(mechanics::MECHANICS_CONTRACT.to_string());
        }
        // A console program is compared by its runs, not pictured.
        if runs::captured(cx.ws).is_empty() {
            s.push(screenshot::SCREENSHOT_CONTRACT.to_string());
        } else {
            s.push(RUNS_BRIEF.to_string());
        }
        s
    }

    fn checks(&self, _ws: &Workspace) -> Vec<Box<dyn Check>> {
        // The sheet is asked for only when Deep mode decompiles a program target.
        vec![Box::new(BuildCheck), Box::new(RunsCheck), Box::new(ScreenshotCheck), Box::new(DeepOnly(MechanicsCheck))]
    }
}
