//! `craft-anything-cli`: every tool as a subcommand, the MCP server, setup, doctor and headless chat.
//!
//! Exit codes: 0 success, 1 the operation failed (a structured error is printed), 2 usage error,
//! 130 interrupted.
#![deny(clippy::unwrap_used, clippy::expect_used, clippy::panic, clippy::unimplemented, clippy::todo, clippy::unreachable)]

mod ai_cmd;
mod output;
mod rebuild_cmd;
mod setup_cmd;
mod tool_args;

use clap::{Parser, Subcommand};
use craft_anything_engine::project::{Project, Purpose};
use craft_anything_engine::{CallOptions, Caller, CancelToken, Consent, Engine, Requires, Session, Settings, ToolOutput};
use craft_anything_evidence::ToolError;
use output::Format;
use serde_json::{Value, json};
use std::path::{Path, PathBuf};
use std::process::ExitCode;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};

pub static INTERRUPTED: AtomicBool = AtomicBool::new(false);

#[derive(Debug, Parser)]
#[command(name = "craft-anything-cli", version, about = "Craft Anything on the command line: every tool, the MCP server, setup and doctor.")]
#[command(after_help = "Every tool is also a subcommand: `craft-anything-cli commands` lists them, `craft-anything-cli <tool> --help` shows its options.\n\
When a tool has its own --format option (core-target-open, ...), --format after the tool name goes to the tool; pick the output with --output-format (or --format before the tool name). `report` has no format option of its own: use `report --html` for HTML.")]
pub struct Cli {
    /// Output format. `--output-format` always means this, even after a tool that has its own `--format`.
    #[arg(long, global = true, value_enum, default_value_t = Format::Json, alias = "output-format")]
    pub format: Format,
    /// Shorthand for --format json.
    #[arg(long, global = true)]
    pub json: bool,
    /// A project folder (`*.cany`): evidence, memory and the journal are kept there. Created if missing.
    #[arg(long, global = true)]
    pub project: Option<PathBuf>,
    /// Allow tools that run code or change a device without asking.
    #[arg(long, global = true)]
    pub allow_run: bool,
    /// Deep mode for this run only: tools may read a target's code, files and page source.
    #[arg(long, global = true, conflicts_with = "clean_room")]
    pub deep: bool,
    /// Clean room for this run only, whatever Settings say: nothing inside a target is read.
    #[arg(long, global = true)]
    pub clean_room: bool,
    #[command(subcommand)]
    pub command: Command,
}

#[derive(Debug, Subcommand)]
pub enum Command {
    /// Run the MCP server on stdin/stdout.
    Mcp {
        /// List every tool instead of the Essentials plus enabled toolsets.
        #[arg(long)]
        all_tools: bool,
        /// A folder where questions and approvals for the person are posted (`core_person_ask`,
        /// `core_action_approve`); the Craft Anything app answers them.
        #[arg(long)]
        inbox: Option<PathBuf>,
    },
    /// Connect Craft Anything to your coding-agent apps.
    Setup(setup_cmd::SetupArgs),
    /// Check the install, registrations, engines, AI backends and the MCP server.
    Doctor(setup_cmd::DoctorArgs),
    /// Remove Craft Anything's registrations and skill from agent apps.
    Uninstall(setup_cmd::UninstallArgs),
    /// List every tool.
    Commands,
    /// What this install can do: toolsets, tool availability, engines.
    Capabilities,
    /// Open a file and run a first look at it.
    Triage { path: String },
    /// Write a readable investigation report (Markdown or HTML) from findings and evidence.
    Report {
        /// Optional target to open first (its sha256 ties evidence to a file). Omit to report on
        /// the open project's memory and ledger.
        path: Option<String>,
        /// Write a self-contained HTML page instead of Markdown.
        #[arg(long)]
        html: bool,
        /// Write to this file instead of printing to stdout.
        #[arg(long)]
        out: Option<PathBuf>,
        /// Leave out the evidence-ledger appendix.
        #[arg(long)]
        no_evidence: bool,
    },
    /// Ask the AI agent a question about a target (streams to stdout).
    Chat(ai_cmd::ChatArgs),
    /// Study a website, app or game and have a coding agent rebuild it in a new project folder.
    Rebuild(rebuild_cmd::RebuildArgs),
    /// Manage AI backends.
    Ai {
        #[command(subcommand)]
        command: ai_cmd::AiCommand,
    },
    /// For a coding agent's hook, run after each of its tool calls: hand over the notes the person
    /// added while it works (printed as the hook's JSON; nothing when none wait).
    #[command(hide = true)]
    BuilderNotes { dir: PathBuf },
    /// Run a tool by name: `craft-anything-cli <tool> [path] [--key value] [--json '{..}' | @file.json | -]`.
    #[command(external_subcommand)]
    Tool(Vec<String>),
}

impl Cli {
    pub fn format(&self) -> Format {
        if self.json { Format::Json } else { self.format }
    }

    /// The mode `--deep` or `--clean-room` asks for, if either.
    pub fn deep_for_run(&self) -> Option<bool> {
        (self.deep || self.clean_room).then_some(self.deep)
    }
}

fn main() -> ExitCode {
    init_logging();
    let _ = ctrlc::set_handler(|| {
        if INTERRUPTED.swap(true, Ordering::SeqCst) {
            // second Ctrl-C: leave now
            std::process::exit(130);
        }
    });
    let cli = match Cli::try_parse() {
        Ok(c) => c,
        Err(e) => {
            let code = if e.use_stderr() { 2 } else { 0 };
            let _ = e.print();
            return ExitCode::from(code);
        }
    };
    let code = run(cli);
    if INTERRUPTED.load(Ordering::SeqCst) { ExitCode::from(130) } else { ExitCode::from(code) }
}

fn init_logging() {
    struct Stderr(log::LevelFilter);
    impl log::Log for Stderr {
        fn enabled(&self, m: &log::Metadata<'_>) -> bool {
            m.level() <= self.0
        }
        fn log(&self, r: &log::Record<'_>) {
            if self.enabled(r.metadata()) {
                eprintln!("[{}] {}: {}", r.level(), r.target(), r.args());
            }
        }
        fn flush(&self) {}
    }
    let level = match std::env::var("CRAFT_ANYTHING_LOG").unwrap_or_default().to_ascii_lowercase().as_str() {
        "trace" => log::LevelFilter::Trace,
        "debug" => log::LevelFilter::Debug,
        "info" => log::LevelFilter::Info,
        "warn" => log::LevelFilter::Warn,
        "error" => log::LevelFilter::Error,
        _ => log::LevelFilter::Off,
    };
    if level != log::LevelFilter::Off && log::set_logger(Box::leak(Box::new(Stderr(level)))).is_ok() {
        log::set_max_level(level);
    }
}

/// Print a line to stdout; a closed pipe (`| head`) is not an error worth crashing over.
pub fn out(s: &str) {
    use std::io::Write as _;
    let mut o = std::io::stdout().lock();
    let _ = o.write_all(s.as_bytes()).and_then(|_| o.write_all(b"\n")).and_then(|_| o.flush());
}

/// Print a value in the chosen format.
pub fn emit(v: &Value, f: Format) {
    out(&output::render(v, f));
}

/// Print an error (to stdout as structured output, so scripts can parse it) and return exit code 1.
pub fn fail(e: &ToolError, f: Format) -> u8 {
    emit(&json!({"error": e}), f);
    1
}

pub fn usage_error(msg: &str) -> u8 {
    usage(msg)
}

fn usage(msg: &str) -> u8 {
    eprintln!("error: {msg}");
    2
}

/// The engine with settings loaded, the run's mode, and the project (if any) opened.
pub fn make_engine(project: Option<&Path>, deep_for_run: Option<bool>) -> Result<Arc<Engine>, ToolError> {
    craft_anything_platform::sync::start_watchdog(craft_anything_engine::settings::config_dir().join("logs"));
    let mut session = Session::new(Settings::load());
    session.deep_for_run = deep_for_run;
    if let Some(dir) = project {
        session.open_project(open_or_create_project(dir)?)?;
    }
    let plugins = craft_anything_engine::plugins::install(&mut session);
    let mut layer_tools = craft_anything_ai::tools();
    layer_tools.extend(craft_anything_setup::tools::specs());
    Ok(Engine::shared_with(session, layer_tools, plugins))
}

fn open_or_create_project(dir: &Path) -> Result<Project, ToolError> {
    let dir = std::path::absolute(dir).map_err(|e| ToolError::io(dir.display(), e))?;
    if dir.join("project.toml").is_file() {
        return Project::open(&dir);
    }
    let name = dir.file_stem().map(|s| s.to_string_lossy().into_owned()).unwrap_or_else(|| "project".into());
    Project::create(&dir, &name, Purpose::default())
}

pub fn call_options(cli: &Cli, cancel: &CancelToken) -> CallOptions<'static> {
    let consent = if cli.allow_run { Consent::Granted } else { Consent::NotAsked };
    CallOptions::new(Caller::Cli).with_consent(consent).with_cancel(cancel.clone())
}

/// A cancel token that trips on Ctrl-C.
pub fn interrupt_token() -> CancelToken {
    let token = CancelToken::default();
    let t = token.clone();
    let _ = std::thread::Builder::new().name("ctrl-c-watch".into()).spawn(move || {
        while !INTERRUPTED.load(Ordering::SeqCst) {
            std::thread::sleep(std::time::Duration::from_millis(50));
        }
        t.cancel();
    });
    token
}

fn run(cli: Cli) -> u8 {
    let f = cli.format();
    match &cli.command {
        // Runs after every tool call of a builder: no engine, nothing but the hook's JSON on stdout.
        Command::BuilderNotes { dir } => {
            use craft_anything_ai::rebuild::notes;
            if let Some(out) = notes::hook_output(&notes::claim(dir)) {
                println!("{out}");
            }
            0
        }
        Command::Mcp { all_tools, inbox } => {
            let engine = match make_engine(cli.project.as_deref(), cli.deep_for_run()) {
                Ok(e) => e,
                Err(e) => {
                    eprintln!("craft-anything mcp: {}", e.message);
                    return 1;
                }
            };
            if let Some(dir) = inbox {
                engine.session().ext.insert(Arc::new(craft_anything_engine::inbox::InboxDir(dir.clone())));
                // A builder can generate game assets with the person's keys (one per asset
                // provider), read here from the keychain so none appears on a command line or in
                // a log.
                let providers = engine.session().ext.get::<craft_anything_engines::assets::AssetProviders>().map(|p| p.as_ref().clone()).unwrap_or_default();
                let keys = craft_anything_ai::keys::asset_keys(&craft_anything_ai::KeyStore::system(), &providers);
                engine.session().ext.insert(Arc::new(keys));
            }
            let mut opts = craft_anything_mcp::ServerOptions::from_env();
            opts.all_tools |= *all_tools;
            opts.allow_run = cli.allow_run;
            match craft_anything_mcp::serve_stdio(engine, opts) {
                Ok(()) => 0,
                Err(e) => {
                    eprintln!("craft-anything mcp: {e}");
                    1
                }
            }
        }
        Command::Setup(a) => setup_cmd::setup(a, f),
        Command::Doctor(a) => setup_cmd::doctor(a, f),
        Command::Uninstall(a) => setup_cmd::uninstall(a, f),
        Command::Commands => commands(f),
        Command::Capabilities => capabilities(&cli, f),
        Command::Triage { path } => triage(&cli, path, f),
        Command::Report { path, html, out, no_evidence } => {
            report(&cli, path.as_deref(), if *html { "html" } else { "markdown" }, out.as_deref(), *no_evidence, f)
        }
        Command::Chat(a) => ai_cmd::chat(&cli, a),
        Command::Rebuild(a) => rebuild_cmd::rebuild(&cli, a),
        Command::Ai { command } => ai_cmd::ai(&cli, command, f),
        Command::Tool(args) => tool(&cli, args, f),
    }
}

fn commands(f: Format) -> u8 {
    // The same engine every command gets: settings, the AI layer's tools and plugins.
    let engine = match make_engine(None, None) {
        Ok(e) => e,
        Err(e) => return fail(&e, f),
    };
    if f == Format::Json || f == Format::Jsonl {
        let v: Vec<Value> = engine
            .registry()
            .all()
            .iter()
            .map(|s| json!({"command": s.cli_name(), "tool": s.id, "toolset": s.toolset.id(), "title": s.title, "summary": s.summary, "needs_target": s.requires == Requires::Target}))
            .collect();
        emit(&Value::Array(v), f);
    } else {
        for t in engine.registry().toolsets() {
            let specs: Vec<_> = engine.registry().in_toolset(t).collect();
            if specs.is_empty() {
                continue;
            }
            out(&format!("{}:", t.title()));
            for s in specs {
                out(&format!("  {:<34} {}", s.cli_name(), s.title));
            }
        }
    }
    0
}

fn capabilities(cli: &Cli, f: Format) -> u8 {
    let engine = match make_engine(cli.project.as_deref(), cli.deep_for_run()) {
        Ok(e) => e,
        Err(e) => return fail(&e, f),
    };
    let session = engine.session();
    let toolsets: Vec<Value> = engine
        .registry()
        .toolsets()
        .iter()
        .map(|t| {
            let tools: Vec<Value> = engine
                .registry()
                .in_toolset(*t)
                .map(|s| {
                    let a = engine.availability(s, &session);
                    // Before anything is open a target tool is still offered (needs_target says what
                    // it waits for), but not one the mode refuses (#249).
                    let refused = session.clean_room() && !craft_anything_engine::clean_room::allows(s.id);
                    let waived = s.requires == Requires::Target && !refused;
                    json!({"tool": s.id, "available": a.available || waived, "needs_target": s.requires == Requires::Target, "reason": if waived { None } else { a.reason }})
                })
                .collect();
            json!({"id": t.id(), "title": t.title(), "tools": tools})
        })
        .collect();
    let engines: Vec<Value> = craft_anything_engines::ENGINES
        .iter()
        .map(|e| {
            let found = session.settings.engine_path(e.id);
            json!({"id": e.id, "name": e.name, "needed_for": e.needed_for, "found": found.is_some(), "path": found, "installable_here": e.host_pin().is_some()})
        })
        .collect();
    emit(
        &json!({
            "version": env!("CARGO_PKG_VERSION"),
            "analysis_mode": if session.clean_room() { "clean-room" } else { "deep" },
            "tools": engine.registry().len(),
            "toolsets": toolsets,
            "engines": engines,
            "host": craft_anything_evidence::host_triple(),
        }),
        f,
    );
    0
}

/// open → op → close for one target. `open` carries extra `core_target_open` params (raw-binary
/// architecture and entry point, a forced format, a Deep language pin).
fn with_target(
    engine: &Engine,
    cli: &Cli,
    cancel: &CancelToken,
    path: &str,
    open: &serde_json::Map<String, Value>,
    op: impl FnOnce() -> Result<ToolOutput, ToolError>,
) -> Result<ToolOutput, ToolError> {
    let abs = std::path::absolute(path).map_err(|e| ToolError::io(path, e))?;
    let mut params = open.clone();
    params.insert("path".into(), json!(abs));
    engine.call("core_target_open", Value::Object(params), call_options(cli, cancel))?;
    let out = op();
    let _ = engine.call("core_target_close", json!({}), call_options(cli, cancel));
    out
}

fn triage(cli: &Cli, path: &str, f: Format) -> u8 {
    let engine = match make_engine(cli.project.as_deref(), cli.deep_for_run()) {
        Ok(e) => e,
        Err(e) => return fail(&e, f),
    };
    let cancel = interrupt_token();
    let tool = ["core_target_triage", "core_overview_show"].into_iter().find(|t| engine.registry().get(t).is_some());
    let r = with_target(&engine, cli, &cancel, path, &Default::default(), || match tool {
        Some(t) => engine.call(t, json!({}), call_options(cli, &cancel)),
        None => {
            let mut v = engine.call("core_session_show", json!({}), call_options(cli, &cancel))?.to_json();
            if let Some(m) = v.as_object_mut() {
                m.insert("note".into(), json!("No triage tool is registered in this build yet; showing what was opened."));
            }
            Ok(ToolOutput::Value(v))
        }
    });
    match r {
        Ok(out) => {
            emit(&out.to_json(), f);
            0
        }
        Err(e) => fail(&e, f),
    }
}

fn report(cli: &Cli, path: Option<&str>, format: &str, out_file: Option<&Path>, no_evidence: bool, f: Format) -> u8 {
    let format = format.to_ascii_lowercase();
    if format != "markdown" && format != "html" {
        return usage("--format must be markdown or html");
    }
    let engine = match make_engine(cli.project.as_deref(), cli.deep_for_run()) {
        Ok(e) => e,
        Err(e) => return fail(&e, f),
    };
    let cancel = interrupt_token();
    // The report tool writes the file itself when given an absolute path; otherwise it returns the
    // text and we print it (raw, so the Markdown/HTML is usable directly).
    let out_abs = match out_file {
        Some(p) => match std::path::absolute(p) {
            Ok(a) => Some(a),
            Err(e) => return fail(&ToolError::io(p.display(), e), f),
        },
        None => None,
    };
    let mut params = json!({"format": format, "include_evidence": !no_evidence});
    if let (Some(a), Some(m)) = (&out_abs, params.as_object_mut()) {
        m.insert("path".into(), json!(a));
    }
    let run = || engine.call("core_report_write", params.clone(), call_options(cli, &cancel));
    let result = match path {
        Some(p) => with_target(&engine, cli, &cancel, p, &Default::default(), run),
        None => run(),
    };
    match result {
        Ok(output) => {
            let v = output.to_json();
            match (out_abs, v["result"]["report"].as_str()) {
                // Printed report: emit the raw text so it can be piped to a file or viewer.
                (None, Some(text)) => out(text),
                // Wrote a file (or an unexpected shape): show the structured result.
                _ => emit(&v, f),
            }
            0
        }
        Err(e) => fail(&e, f),
    }
}

fn tool(cli: &Cli, args: &[String], f: Format) -> u8 {
    let Some((name, rest)) = args.split_first() else { return usage("missing command") };
    // Global flags written after the tool name land here; pick them out.
    let mut f = f;
    let (mut allow_run, mut deep, mut clean_room) = (cli.allow_run, cli.deep, cli.clean_room);
    let mut rest_args = Vec::new();
    let mut it = rest.iter().peekable();
    // `--format` and `--project` are left to tool_args when the tool has an option of that name
    // (`project-show --project <folder>`); otherwise they're the global flags.
    while let Some(a) = it.next() {
        match a.as_str() {
            "--allow-run" => allow_run = true,
            "--deep" => deep = true,
            "--clean-room" => clean_room = true,
            "--json" if it.peek().is_none_or(|n| !(n.starts_with('{') || n.starts_with('@') || n.as_str() == "-")) => f = Format::Json,
            _ => rest_args.push(a.clone()),
        }
    }
    // The engine first (tools from higher layers are only known through it), with the project
    // given before the tool name.
    if deep && clean_room {
        return usage("--deep and --clean-room can't be used together");
    }
    let mut cli = Cli { format: f, json: false, project: cli.project.clone(), allow_run, deep, clean_room, command: Command::Commands };
    let mut engine = match make_engine(cli.project.as_deref(), cli.deep_for_run()) {
        Ok(e) => e,
        Err(e) => return fail(&e, f),
    };
    let Some(spec) = engine.registry().get(name).copied() else {
        return usage(&format!("unknown command {name:?}. Run `craft-anything-cli commands` to list tools, or --help for built-in commands."));
    };
    let schema = engine.registry().input_schema(&spec);
    let tool_has_project = schema.pointer("/properties/project").is_some();
    if !tool_has_project && let Some(i) = rest_args.iter().position(|a| a == "--project") {
        let Some(p) = rest_args.get(i + 1).cloned() else { return usage("--project needs a folder") };
        rest_args.drain(i..i + 2);
        cli.project = Some(PathBuf::from(p));
        engine = match make_engine(cli.project.as_deref(), cli.deep_for_run()) {
            Ok(e) => e,
            Err(e) => return fail(&e, f),
        };
    }
    let cli = &cli;
    let rest = rest_args.as_slice();
    let inv = match tool_args::parse(&spec, &schema, rest) {
        Ok(i) => i,
        Err(m) => return usage(&m),
    };
    if let Some(v) = &inv.output_format {
        match <Format as clap::ValueEnum>::from_str(v, true) {
            Ok(v) => f = v,
            Err(_) => return usage("--output-format needs one of json, jsonl, md, text"),
        }
    }
    if inv.help {
        out(&tool_args::help(&spec, &schema));
        return 0;
    }
    let cancel = interrupt_token();
    let result = match (&inv.open_path, spec.requires) {
        (Some(path), _) => with_target(&engine, cli, &cancel, path, &inv.open_params, || engine.call(spec.id, inv.params.clone(), call_options(cli, &cancel))),
        (None, Requires::Target) => {
            return usage(&format!("{} needs a target: craft-anything-cli {} <path> …", spec.cli_name(), spec.cli_name()));
        }
        (None, _) => engine.call(spec.id, inv.params.clone(), call_options(cli, &cancel)),
    };
    match result {
        Ok(out) => {
            emit(&out.to_json(), f);
            0
        }
        Err(e) => fail(&e, f),
    }
}
