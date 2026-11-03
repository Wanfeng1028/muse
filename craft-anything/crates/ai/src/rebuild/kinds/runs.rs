//! Console programs can't be photographed, so they are compared by their runs: with runtime study
//! on, Study runs the original with each input in [`CASES`] (`runtime_walkthrough_record`) and keeps
//! what it printed and how it exited in `capture/runs/`; [`RunsCheck`] runs the rebuild the same
//! way and claims, input by input, that it exits like the original and prints what it prints.

use super::*;
use craft_anything_engine::workspace::Claim;

/// Where the original's runs are kept in the capture folder.
pub const RUNS_DIR: &str = "runs";

/// The inputs both programs are run with: (name, arguments). Add an input with one line.
pub const CASES: &[(&str, &[&str])] = &[("no arguments", &[]), ("--help", &["--help"]), ("--version", &["--version"])];

/// How long one run may take; a program still running then (waiting for input) is a result too.
const RUN_MS: u64 = 8_000;
/// How much of the output's words must match for "prints what the original prints".
const OUTPUT_ALIKE: f64 = 80.0;

/// Libraries a windowed program loads, matched lower-case as part of the name. ELF and Mach-O
/// don't mark a console program, so one that loads none of these is taken for one (and Study
/// checks it really ran like one: [`ran_like_console`]).
const WINDOW_LIBRARIES: &[&str] = &[
    "libx11",
    "libxcb",
    "libwayland",
    "libgtk",
    "libgdk",
    "libqt",
    "libsdl",
    "libglfw",
    "libgl.",
    "libegl",
    "libvulkan",
    "appkit.framework",
    "cocoa.framework",
    "uikit.framework",
    "swiftui.framework",
    "metal.framework",
    "quartzcore.framework",
];

/// The most of a Linux or macOS program read to see what it loads.
const MAX_READ: u64 = 256 << 20;

/// A console program: a Windows program marked for the console, or a Linux or macOS executable
/// that loads no windowing library.
pub fn is_console(program: &Path) -> bool {
    use std::io::Read as _;
    let read = |limit: u64| -> Option<Vec<u8>> {
        let mut bytes = Vec::new();
        std::fs::File::open(program).and_then(|f| f.take(limit).read_to_end(&mut bytes)).ok()?;
        Some(bytes)
    };
    let Some(head) = read(64 * 1024) else { return false };
    if head.starts_with(b"MZ") {
        return craft_anything_formats::pe::headers(&head).is_ok_and(|h| h.subsystem == 3);
    }
    let Some(b) = read(MAX_READ).and_then(|bytes| craft_anything_formats::parse_binary(&bytes).ok()) else { return false };
    loads_no_window(&b)
}

/// An ELF or Mach-O executable that loads none of [`WINDOW_LIBRARIES`].
fn loads_no_window(b: &craft_anything_formats::Binary) -> bool {
    use craft_anything_formats::Format;
    matches!(b.format, Format::Elf | Format::MachO)
        && b.entry.is_some()
        && !b.libraries.iter().any(|l| {
            let l = l.to_lowercase();
            WINDOW_LIBRARIES.iter().any(|w| l.contains(w))
        })
}

/// Whether the kept runs look like a console program's: one of them printed something or ended
/// by itself. A program that sat silent through every input is a windowed one after all (one
/// that opens its windowing library only once it runs).
pub fn ran_like_console(runs: &[Value]) -> bool {
    runs.iter().any(|r| r.get("reason").and_then(Value::as_str) == Some("exited") || r.get("lines").and_then(Value::as_array).is_some_and(|l| !l.is_empty()))
}

/// The original's runs Study kept, by input name (none when it isn't a console program or
/// runtime study was off).
pub fn captured(ws: &Workspace) -> Vec<Value> {
    let dir = ws.capture_dir().join(RUNS_DIR);
    CASES.iter().filter_map(|(name, _)| std::fs::read(dir.join(format!("{}.json", slug(name)))).ok()).filter_map(|b| serde_json::from_slice(&b).ok()).collect()
}

fn slug(name: &str) -> String {
    let s: String = name.chars().map(|c| if c.is_ascii_alphanumeric() { c.to_ascii_lowercase() } else { '-' }).collect();
    s.split('-').filter(|p| !p.is_empty()).collect::<Vec<_>>().join("-")
}

/// One run as kept: its input, how it exited and the lines it left on the terminal.
fn run_record(name: &str, args: &[String], capture: &Value) -> Value {
    json!({
        "name": name,
        "arguments": args,
        "reason": capture.pointer("/exit/reason"),
        "exit_code": capture.pointer("/exit/code"),
        "lines": capture.pointer("/terminal/lines").cloned().unwrap_or_else(|| json!([])),
    })
}

/// The kept form of a `runtime_walkthrough_record` result.
fn result_of(out: &ToolOutput) -> Value {
    out.to_json().get("result").cloned().unwrap_or(Value::Null)
}

impl Worker {
    /// Run the original console program with each input and keep what it did in capture/runs/;
    /// returns the README section, or None (and keeps nothing) when it didn't run like a console
    /// program.
    pub(in crate::rebuild) fn capture_runs(&self, program: &Path, capture: &Path) -> Result<Option<String>, ToolError> {
        let dir = capture.join(RUNS_DIR);
        std::fs::create_dir_all(&dir).map_err(|e| ToolError::io(dir.display(), e))?;
        let mut kept = Vec::new();
        let mut records = Vec::new();
        for (name, args) in CASES {
            let args: Vec<String> = args.iter().map(|a| (*a).to_string()).collect();
            let mut params =
                json!({"executable": program.display().to_string(), "arguments": args, "timeout_ms": RUN_MS, "idle_timeout_ms": RUN_MS, "settle_ms": 200});
            if let Some(cwd) = program.parent() {
                params["working_directory"] = json!(cwd.display().to_string());
            }
            match self.call("runtime_walkthrough_record", params) {
                Ok(out) => {
                    let record = run_record(name, &args, &result_of(&out));
                    let bytes = serde_json::to_vec_pretty(&record).map_err(|e| ToolError::internal(e.to_string()))?;
                    craft_anything_engine::project::write_atomic(&dir.join(format!("{}.json", slug(name))), &bytes)?;
                    kept.push(*name);
                    records.push(record);
                }
                Err(e) => log::warn!("running {} with {name} failed: {}", program.display(), e.message),
            }
        }
        if !kept.is_empty() && !ran_like_console(&records) {
            let _ = std::fs::remove_dir_all(&dir);
            return Ok(None);
        }
        Ok(Some(if kept.is_empty() {
            "\n## How it runs\n\nIt's a console program, but running it to see its output didn't work.\n".to_string()
        } else {
            format!(
                "\n## How it runs\n\nIt's a console program. capture/runs/ holds what it printed and how it exited for each of these inputs: {}. Each file has the arguments, the exit code (or that it was still running after {} s) and the lines it left on the terminal.\n",
                kept.join(", "),
                RUN_MS / 1000
            )
        }))
    }
}

/// The words of a run's output, with both programs' own names made the same ("program"), so a
/// usage line naming the rebuild's file still matches.
fn output_words(run: &Value, names: &[String]) -> std::collections::BTreeMap<String, usize> {
    let mut text = run.get("lines").and_then(Value::as_array).into_iter().flatten().filter_map(Value::as_str).collect::<Vec<_>>().join("\n").to_lowercase();
    for n in names.iter().filter(|n| !n.is_empty()) {
        text = text.replace(&n.to_lowercase(), "program");
    }
    website::words(&text)
}

/// Dice over word counts, 0..=100; two empty outputs are alike.
fn alike(a: &std::collections::BTreeMap<String, usize>, b: &std::collections::BTreeMap<String, usize>) -> f64 {
    let (ta, tb): (usize, usize) = (a.values().sum(), b.values().sum());
    if ta + tb == 0 {
        return 100.0;
    }
    let shared: usize = a.iter().map(|(w, n)| (*n).min(b.get(w).copied().unwrap_or(0))).sum();
    200.0 * shared as f64 / (ta + tb) as f64
}

/// What one input's two runs claim: the same way out (exit code, or still running) and the same
/// output. `names`: both programs' file names without extension.
pub fn run_claims(original: &Value, built: &Value, names: &[String]) -> Vec<Claim> {
    let name = original.get("name").and_then(Value::as_str).unwrap_or("its input");
    let how = |r: &Value| match (r.get("reason").and_then(Value::as_str), r.get("exit_code").and_then(Value::as_i64)) {
        (Some("exited"), Some(c)) => format!("exits with code {c}"),
        (Some("exited"), None) => "exits".to_string(),
        (Some(other), _) => format!("is still running ({other})"),
        (None, _) => "didn't run".to_string(),
    };
    let score = alike(&output_words(original, names), &output_words(built, names));
    vec![
        Claim::new(format!("With {name}, it {} like the original", how(original)), how(original) == how(built), format!("it {}", how(built))),
        Claim::new(format!("With {name}, it prints what the original prints"), score >= OUTPUT_ALIKE, format!("{score:.0}% of the words match")),
    ]
}

/// Runs the rebuild with each input Study ran the original with and compares, claim by claim.
pub struct RunsCheck;

impl RunsCheck {
    pub const ID: &'static str = "app-runs";
}

impl Check for RunsCheck {
    fn id(&self) -> &'static str {
        Self::ID
    }

    fn applies(&self, cx: &CheckCx) -> bool {
        !captured(cx.ws).is_empty()
    }

    fn run(&self, cx: &mut CheckCx) -> Result<CheckResult, ToolError> {
        let (ws, round) = (cx.ws, cx.round);
        let godot = cx.godot();
        let Some((program, base)) = craft_anything_engine::outputs::launch(&ws.app_dir(), godot.as_deref()) else {
            return Ok(CheckResult::new(self.id(), round, false, screenshot::NO_PROGRAM));
        };
        let out = ws.checks_dir().join(format!("round-{round}")).join(RUNS_DIR);
        std::fs::create_dir_all(&out).map_err(|e| ToolError::io(out.display(), e))?;
        let original_name = match &ws.manifest.target {
            TargetRef::Local { path } => locate(path, false).0.file_stem().map(|s| s.to_string_lossy().into_owned()).unwrap_or_default(),
            _ => String::new(),
        };
        let names = vec![original_name, program.file_stem().map(|s| s.to_string_lossy().into_owned()).unwrap_or_default()];
        let (mut claims, mut notes, mut artifacts) = (Vec::new(), Vec::new(), Vec::new());
        for original in captured(ws) {
            let name = original.get("name").and_then(Value::as_str).unwrap_or_default().to_string();
            let mut args = base.clone();
            args.extend(original.get("arguments").and_then(Value::as_array).into_iter().flatten().filter_map(Value::as_str).map(String::from));
            let params = json!({"executable": program.display().to_string(), "arguments": args, "working_directory": ws.app_dir().display().to_string(), "timeout_ms": RUN_MS, "idle_timeout_ms": RUN_MS, "settle_ms": 200});
            let built = match cx.call("runtime_walkthrough_record", params) {
                Ok(o) => run_record(&name, &args, &result_of(&o)),
                Err(e) => {
                    notes.push(format!("with {name} the build couldn't be run: {}", e.message));
                    json!({"name": name})
                }
            };
            let file = out.join(format!("{}.json", slug(&name)));
            if let Ok(bytes) = serde_json::to_vec_pretty(&built) {
                craft_anything_engine::project::write_atomic(&file, &bytes)?;
                artifacts.extend(file.strip_prefix(&ws.root).ok().map(Path::to_path_buf));
            }
            claims.extend(run_claims(&original, &built, &names));
        }
        let failed: Vec<String> = claims.iter().filter(|c| !c.passed).map(|c| format!("{} ({})", c.title, c.detail)).collect();
        notes.insert(
            0,
            if failed.is_empty() {
                format!("It runs like the original with every input ({} claims hold).", claims.len())
            } else {
                format!(
                    "{} of {} claims don't hold yet: {}. Compare your runs in checks/round-{round}/runs/ with the original's in capture/runs/.",
                    failed.len(),
                    claims.len(),
                    failed.join("; ")
                )
            },
        );
        Ok(CheckResult { claims, artifacts, ..CheckResult::new(self.id(), round, true, notes.join(" ")) })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn each_input_claims_the_same_exit_and_output() {
        let names = vec!["orig-tool".to_string(), "rebuilt".to_string()];
        let original = json!({"name": "--help", "reason": "exited", "exit_code": 0, "lines": ["Usage: orig-tool [options] <file>", "  -v  print the version", "  -o  output folder"]});
        let same = json!({"name": "--help", "reason": "exited", "exit_code": 0, "lines": ["Usage: rebuilt [options] <file>", "  -v  print the version", "  -o  output folder"]});
        assert!(
            run_claims(&original, &same, &names).iter().all(|c| c.passed),
            "the programs' own names don't count: {:?}",
            run_claims(&original, &same, &names)
        );
        let other = json!({"name": "--help", "reason": "exited", "exit_code": 2, "lines": ["error: unknown option --help"]});
        let got: Vec<(String, bool, String)> = run_claims(&original, &other, &names).into_iter().map(|c| (c.title, c.passed, c.detail)).collect();
        assert_eq!(got[0], ("With --help, it exits with code 0 like the original".to_string(), false, "it exits with code 2".to_string()));
        assert!(!got[1].1 && got[1].0 == "With --help, it prints what the original prints" && got[1].2.ends_with("% of the words match"), "{got:?}");
        // A program that waits for input is still running at the deadline, in both.
        let waits = json!({"name": "no arguments", "reason": "timeout", "lines": []});
        assert!(run_claims(&waits, &waits, &names).iter().all(|c| c.passed));
        assert!(!run_claims(&waits, &json!({"name": "no arguments"}), &names)[0].passed, "a build that didn't run doesn't match");
    }

    #[test]
    fn a_unix_program_is_a_console_one_unless_it_loads_a_windowing_library() {
        let binary = |format, libs: &[&str]| {
            let mut b = craft_anything_formats::Binary::raw(craft_anything_formats::Arch::X86_64, 0, 0, 0);
            b.format = format;
            b.entry = Some(0x1000);
            b.libraries = libs.iter().map(|l| (*l).to_string()).collect();
            b
        };
        use craft_anything_formats::Format;
        assert!(loads_no_window(&binary(Format::Elf, &["libc.so.6", "libssl.so.3"])));
        assert!(!loads_no_window(&binary(Format::Elf, &["libc.so.6", "libX11.so.6"])));
        assert!(!loads_no_window(&binary(Format::Elf, &["libGL.so.1"])));
        assert!(loads_no_window(&binary(Format::MachO, &["/usr/lib/libSystem.B.dylib"])));
        assert!(!loads_no_window(&binary(Format::MachO, &["/System/Library/Frameworks/AppKit.framework/Versions/C/AppKit"])));
        assert!(!loads_no_window(&binary(Format::Pe, &[])), "Windows programs say so themselves");
        let mut library = binary(Format::Elf, &[]);
        library.entry = None;
        assert!(!loads_no_window(&library), "a library isn't run");
    }

    #[test]
    fn only_console_programs_are_run_and_inputs_have_file_names() {
        let d = tempfile::tempdir().unwrap();
        let fake = d.path().join("tool.exe");
        std::fs::write(&fake, b"MZ not really a program").unwrap();
        assert!(!is_console(&fake) && !is_console(&d.path().join("missing.exe")));
        assert!(ran_like_console(&[json!({"reason": "timeout", "lines": ["Usage: tool"]})]), "it printed");
        assert!(ran_like_console(&[json!({"reason": "exited", "lines": []})]), "it ended by itself");
        assert!(
            !ran_like_console(&[json!({"reason": "timeout", "lines": []}), json!({"reason": "idle_timeout", "lines": []})]),
            "silent and still open: a window"
        );
        // Programs made here, read but never run: a console tool and a windowed app.
        let (tool, app) = (d.path().join("tool.exe"), d.path().join("app.exe"));
        std::fs::write(&tool, craft_anything_testkit::pe64_subsystem(3)).unwrap();
        std::fs::write(&app, craft_anything_testkit::pe64_subsystem(2)).unwrap();
        assert!(is_console(&tool) && !is_console(&app));
        assert_eq!(CASES.iter().map(|(n, _)| slug(n)).collect::<Vec<_>>(), ["no-arguments", "help", "version"]);
        let ws = Workspace::create(d.path(), "Tool", "Rebuild this tool", TargetRef::None).unwrap();
        assert!(captured(&ws).is_empty());
        std::fs::create_dir_all(ws.capture_dir().join(RUNS_DIR)).unwrap();
        std::fs::write(
            ws.capture_dir().join(RUNS_DIR).join("help.json"),
            br#"{"name": "--help", "arguments": ["--help"], "reason": "exited", "exit_code": 0, "lines": ["Usage"]}"#,
        )
        .unwrap();
        assert_eq!(captured(&ws).len(), 1);
    }
}
