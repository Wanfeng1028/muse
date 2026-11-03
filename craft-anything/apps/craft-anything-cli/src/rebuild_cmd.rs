//! `rebuild`: the whole study → build → check workflow, headless. Questions and approvals are
//! answered on the terminal, or automatically with `--unattended` (first choice; approvals are
//! refused, so nothing outside the project happens without a person).

use crate::{Cli, INTERRUPTED, make_engine};
use clap::Args;
use craft_anything_ai::rebuild::{self, RebuildRun, RunEvent, RunOptions};
use craft_anything_ai::{AgentEvent, AiHub, BackendKind};
use craft_anything_engine::inbox::{Answer, Request, RequestKind};
use craft_anything_engine::workspace::Workspace;
use craft_anything_evidence::ToolError;
use std::io::{BufRead as _, Write as _};
use std::path::PathBuf;
use std::sync::atomic::Ordering;
use std::time::Duration;

#[derive(Debug, Args)]
pub struct RebuildArgs {
    /// A web address, an absolute path to an app, game or file, or `-` for none.
    pub target: String,
    /// What to make, in your words.
    pub request: String,
    /// Where the new project folder goes (default: the projects folder from settings).
    #[arg(long, conflicts_with = "project_folder")]
    pub projects_dir: Option<PathBuf>,
    /// Start the new project in this folder itself (it's added to the project list). If it
    /// already has files, --existing says what they are.
    #[arg(long, conflicts_with = "continue_in")]
    pub project_folder: Option<PathBuf>,
    /// With --project-folder that has files: `edit` (they're the app, edited in place) or
    /// `start-from` (material to start from; the app is built in app/ beside them).
    #[arg(long, requires = "project_folder", value_parser = ["edit", "start-from"])]
    pub existing: Option<String>,
    /// Continue an existing project folder; the request becomes a follow-up message.
    #[arg(long)]
    pub continue_in: Option<PathBuf>,
    /// With --continue-in: carry on where the project's last run stopped (paused, or the app or
    /// the computer stopped); the request is ignored.
    #[arg(long, requires = "continue_in")]
    pub resume: bool,
    /// The coding agent to use (a backend name from `ai list`).
    #[arg(long)]
    pub backend: Option<String>,
    /// Refinement rounds after the first build.
    #[arg(long, default_value_t = 2)]
    pub rounds: u32,
    /// Answer questions with the first choice and refuse approvals, without asking.
    #[arg(long)]
    pub unattended: bool,
    /// What to build with: an engine (unity, unreal, godot, rust) or a stack's full name.
    /// New projects only; otherwise it's chosen from the request and target.
    #[arg(long)]
    pub build_with: Option<String>,
    /// Let the builder generate pictures and 3D models for a new game (needs a fal.ai key; paid
    /// within the project's asset budget). Change it later with `project-assets-allow`.
    #[arg(long)]
    pub generate_assets: bool,
}

pub fn rebuild(cli: &Cli, a: &RebuildArgs) -> u8 {
    match run(cli, a) {
        Ok(true) => 0,
        Ok(false) => 1,
        Err(e) => {
            eprintln!("rebuild: {}", e.message);
            if let Some(r) = e.remediation {
                eprintln!("  {r}");
            }
            1
        }
    }
}

/// Use the configured agent app, or add the first one found on this computer.
fn ensure_agent(hub: &AiHub) -> Result<(), ToolError> {
    if hub.backends().iter().any(|b| b.kind == BackendKind::AgentCli && b.enabled) {
        return Ok(());
    }
    if let Some(d) = hub.detect().into_iter().find(|d| d.suggestion.kind == BackendKind::AgentCli) {
        eprintln!("Using {} ({}).", d.suggestion.name, d.reason);
        hub.add_backend(d.suggestion, None)?;
    }
    Ok(())
}

fn run(cli: &Cli, a: &RebuildArgs) -> Result<bool, ToolError> {
    let engine = make_engine(None, cli.deep_for_run())?;
    let hub = AiHub::new(engine.clone());
    ensure_agent(&hub)?;
    if a.build_with.is_some() && a.continue_in.is_some() {
        return Err(ToolError::invalid("--build-with is for new projects; a project keeps the stack it was built with.")
            .with_remediation("Leave out --build-with, or start a new project."));
    }
    if a.generate_assets && a.continue_in.is_some() {
        return Err(ToolError::invalid("--generate-assets is for new projects.").with_remediation("Use project-assets-allow for an existing project."));
    }
    let (ws, message) = match &a.continue_in {
        Some(dir) => (Workspace::open(&std::path::absolute(dir).map_err(|e| ToolError::io(dir.display(), e))?)?, (!a.resume).then(|| a.request.clone())),
        None => {
            use craft_anything_ai::rebuild::project::Place;
            use craft_anything_engine::workspace::ExistingFiles;
            let settings = engine.session().settings.clone();
            let existing = a.existing.as_deref().map(|e| if e == "edit" { ExistingFiles::Edit } else { ExistingFiles::StartFrom });
            let folder = a.project_folder.as_deref().map(std::path::absolute).transpose().map_err(|e| ToolError::io("--project-folder", e))?;
            let place = match (&folder, &a.projects_dir) {
                (Some(f), _) => Place::At(f, existing),
                (None, Some(d)) => Place::In(d),
                (None, None) => Place::Projects,
            };
            let ws = rebuild::project::new_project(&settings, &a.target, &a.request, place, a.build_with.as_deref(), a.generate_assets, a.backend.as_deref())?;
            if folder.is_some() {
                engine.session().remember_project(&ws.root)?;
            }
            (ws, None)
        }
    };
    println!("Project: {}", ws.root.display());
    // A follow-up shows in the project's feed as the person typed it.
    let shown = message.clone();
    let good_enough = engine.session().settings.build.good_enough;
    let opts = RunOptions {
        backend: a.backend.clone(),
        message,
        shown,
        continuing: a.resume,
        max_rounds: a.rounds,
        good_enough,
        beginner: !cli.json,
        ..RunOptions::default()
    };
    let mut run = RebuildRun::start(&hub, ws, opts)?;
    let mut ok = false;
    let mut line_open = false;
    loop {
        if INTERRUPTED.load(Ordering::SeqCst) {
            run.stop();
        }
        for e in run.poll() {
            match e {
                RunEvent::Step { step, text } => {
                    end_line(&mut line_open);
                    println!("[{}] {text}", step.label());
                }
                RunEvent::Agent(AgentEvent::TextDelta { text }) => {
                    print!("{text}");
                    line_open = !text.ends_with('\n');
                }
                RunEvent::Agent(AgentEvent::ToolStarted { tool, input, .. }) => {
                    end_line(&mut line_open);
                    println!("  · {}", rebuild::activity::describe(&tool, &input, &[]).words());
                }
                RunEvent::Agent(AgentEvent::Error { message, remediation, log }) => {
                    end_line(&mut line_open);
                    println!("  ! {message}");
                    if let Some(r) = remediation {
                        println!("{r}");
                    }
                    if let Some(l) = log {
                        println!("  log: {}", l.display());
                    }
                }
                RunEvent::Agent(_) => {}
                RunEvent::Note(text) => {
                    end_line(&mut line_open);
                    println!("  + {text}");
                }
                RunEvent::Ask(r) => {
                    end_line(&mut line_open);
                    let answer = if a.unattended { auto_answer(&r) } else { prompt_answer(&r) };
                    run.answer(&r.id, &answer)?;
                }
                RunEvent::Checked(c) => {
                    end_line(&mut line_open);
                    match c.similarity {
                        Some(s) => println!("[Check {}] {s:.0}% alike — {}", c.round, c.note),
                        None => println!("[Check {}] {}", c.round, c.note),
                    }
                }
                RunEvent::Preview(url) => println!("Preview: {url}"),
                RunEvent::Finished { ok: o, message, paused } => {
                    end_line(&mut line_open);
                    println!(
                        "{}",
                        if o {
                            format!("Done. {message}")
                        } else if paused {
                            message
                        } else {
                            format!("Stopped: {message}")
                        }
                    );
                    ok = o;
                }
            }
        }
        if !run.is_running() && run.poll().is_empty() {
            break;
        }
        std::thread::sleep(Duration::from_millis(100));
    }
    let _ = std::io::stdout().flush();
    Ok(ok)
}

fn end_line(open: &mut bool) {
    if *open {
        println!();
        *open = false;
    }
}

fn auto_answer(r: &Request) -> Answer {
    match r.kind {
        RequestKind::Question => {
            println!("? {} → {} (unattended)", r.title, r.choices.first().map(String::as_str).unwrap_or("no preference"));
            Answer {
                choice: r.choices.first().cloned(),
                text: r.choices.is_empty().then(|| "No preference; use your best judgement.".to_string()),
                ..Default::default()
            }
        }
        RequestKind::Approval => {
            println!("? {} → refused (unattended)", r.title);
            Answer { allow: Some(false), text: Some("Unattended run: actions outside the project aren't allowed.".into()), ..Default::default() }
        }
    }
}

fn read_line() -> String {
    let mut s = String::new();
    let _ = std::io::stdin().lock().read_line(&mut s);
    s.trim().to_string()
}

fn prompt_answer(r: &Request) -> Answer {
    println!("\n? {}", r.title);
    if !r.detail.is_empty() {
        println!("  {}", r.detail.lines().take(12).collect::<Vec<_>>().join("\n  "));
    }
    match r.kind {
        RequestKind::Question => {
            for (i, c) in r.choices.iter().enumerate() {
                println!("  {}) {c}", i + 1);
            }
            print!("Your answer (number or text): ");
            let _ = std::io::stdout().flush();
            let line = read_line();
            match line.parse::<usize>().ok().and_then(|n| n.checked_sub(1)).and_then(|i| r.choices.get(i)) {
                Some(c) => Answer { choice: Some(c.clone()), ..Default::default() },
                None => Answer { text: Some(line), ..Default::default() },
            }
        }
        RequestKind::Approval => {
            print!("Allow? [y]es / [a]lways for this project / [n]o: ");
            let _ = std::io::stdout().flush();
            let line = read_line().to_lowercase();
            Answer { allow: Some(line.starts_with('y') || line.starts_with('a')), always: line.starts_with('a'), ..Default::default() }
        }
    }
}
