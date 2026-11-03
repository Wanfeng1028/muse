//! Headless parity (R1.6): everything a person can do in the app, the CLI and MCP can do too.
//!
//! **The rule:** a new action in the app (a `CraftApp` method that does something, a button,
//! a setting) gets a row in [`ACTIONS`] naming its headless counterpart: a tool id (MCP and
//! `craft-anything-cli <tool-id-in-kebab-case>`) or a built-in CLI command (`rebuild …`). An
//! action with no counterpart yet is `Pending`, naming the tool it waits for and the roadmap item;
//! a pure view action (theme, panels, the palette) is `UiOnly` with the reason.
//!
//! The tests check that:
//! - every tool named here is registered and reachable by its CLI spelling;
//! - every CLI command and flag named here exists in `apps/craft-anything-cli/src`;
//! - a pending tool that now exists fails the test, so its row is moved to `Tool`;
//! - every `&mut self` method on `CraftApp` is either a row here or in [`PLUMBING`], so a new
//!   method can't slip in without a decision.

use craft_anything_engine::Registry;
use std::path::{Path, PathBuf};

/// How a person does the same thing without the app.
enum Headless {
    /// Tool ids (MCP, and the CLI as `craft-anything-cli <id-in-kebab-case>`).
    Tool(&'static [&'static str]),
    /// A built-in CLI command; `<…>` are arguments, `--flags` must exist.
    Cli(&'static str),
    /// No counterpart yet. `tool` is the id it waits for (if one is planned).
    Pending { tool: Option<&'static str>, why: &'static str },
    /// A view action with no product logic behind it.
    UiOnly(&'static str),
}
use Headless::*;

struct Action {
    /// A `CraftApp` method name, or (with spaces) where the control lives in the app.
    ui: &'static str,
    /// What the person gets, in a few words.
    does: &'static str,
    headless: Headless,
}

const fn a(ui: &'static str, does: &'static str, headless: Headless) -> Action {
    Action { ui, does, headless }
}

#[rustfmt::skip]
const ACTIONS: &[Action] = &[
    // ---- Projects: making something --------------------------------------------------------
    a("start_make",          "start a new project from the Home prompt",       Cli("rebuild <target> <request> --build-with --backend --generate-assets")),
    a("set_backend_enabled", "turn an AI on or off",                           Cli("ai on <name> / ai off <name>")),
    a("remove_backend",      "remove an AI and its key",                       Cli("ai remove <name>")),
    a("set_agent_program",   "run an agent app from a program it isn't found as", Cli("ai program <name> <path>")),
    a("refresh_projects",    "list the projects",                              Tool(&["project_list"])),
    a("remember_project",    "keep a project in a picked folder in the list",  Tool(&["rebuild_start"])),
    a("add_project_folder",  "list projects from another folder too",          Tool(&["settings_set"])),
    a("remove_project_folder", "stop listing a folder's projects",             Tool(&["settings_set"])),
    a("open_workspace",      "show one project, its feed and checks",          Tool(&["project_show"])),
    a("rename_project",      "give a project a new name",                      Tool(&["project_rename"])),
    a("duplicate_project",   "copy a project to try something else",           Tool(&["project_duplicate"])),
    a("delete_project",      "delete a project, keeping the person's files",   Tool(&["project_delete"])),
    a("follow_up",           "ask a finished project for a change",            Cli("rebuild <target> <request> --continue-in")),
    a("send_message",        "send the project's prompt box (a follow-up)",    Cli("rebuild <target> <request> --continue-in")),
    a("answer_request",      "answer a question or approval card",             Tool(&["project_inbox_answer"])),
    a("pause",               "stop the running build",                         Tool(&["rebuild_stop"])),
    a("unsend",              "take back a note the builder hasn't read yet",   Tool(&["rebuild_note_withdraw"])),
    a("continue_build",      "carry on a build that stopped part-way",         Cli("rebuild <target> <request> --continue-in --resume")),
    a("open_preview",        "open the built website in the browser",          Tool(&["project_preview"])),
    a("play",                "play the built game or start the built app",     Tool(&["project_play"])),
    a("ask_about_build",     "a question about the build, answered without building", Tool(&["rebuild_question_ask"])),
    a("set_questions",       "ask me, or let the builder decide its questions", Tool(&["project_questions_set"])),
    a("ask_pin",             "pin a build, frozen or light (its size first)",  Tool(&["project_pin_create"])),
    a("refresh_pins",        "the sidebar's pinned builds, and which run",     Tool(&["project_pins_list"])),
    a("open_pin",            "open a pinned build (or another copy)",          Tool(&["project_pin_open"])),
    a("stop_pin",            "close what a pin opened",                        Tool(&["project_pin_stop"])),
    a("add_pictures",        "pictures of the original for the builder",       Tool(&["rebuild_start"])),
    a("attach",              "attach pictures to the next message",            Pending { tool: None, why: "rebuild_note and rebuild_start take text; attachments with a message come next" }),
    a("raise_asset_budget",  "give a project another default budget for generated assets", Tool(&["project_assets_budget"])),
    a("set_generate_assets", "let a game's builder generate pictures and 3D models, or not", Tool(&["project_assets_allow"])),
    a("Project › Open folder", "show the project folder in the file manager",  Tool(&["project_open_folder"])),
    a("Project › Details",   "switch to the Experienced workbench",            UiOnly("a view switch")),

    // ---- Engines, Deep mode and assets --------------------------------------------------------
    a("refresh_game_engines","which game engines are on this computer",        Tool(&["engines_list"])),
    a("get_engine",          "download or install a game engine",              Tool(&["engines_install"])),
    a("get_ghidra",          "download Ghidra for Deep mode",                  Tool(&["engines_install"])),
    a("detect_game_engine",  "find the engine the original game was made with", Cli("rebuild <target> <request>")),
    a("set_deep",            "Clean room or Deep mode (Ghidra)",               Tool(&["settings_set"])),
    a("check_asset_keys",    "which asset providers have a key set up",        Tool(&["assets_key_status"])),
    a("save_asset_key",      "save an asset provider's key in the keychain",   Tool(&["assets_key_set"])),
    a("remove_asset_key",    "forget an asset provider's key",                 Tool(&["assets_key_remove"])),
    a("Engine › Open",       "open Unity Hub or the Epic Games Launcher",      Tool(&["engines_app_open"])),
    a("Download pages",      "open an engine's or fal.ai's download page",     UiOnly("a link; engines_install returns the page for vendor installs")),

    // ---- Settings ----------------------------------------------------------------------------
    a("set_mode",            "Beginner or Experienced",                        Tool(&["settings_set"])),
    a("finish_first_run",    "finish the welcome steps",                       Tool(&["settings_set"])),
    a("Settings › Language", "the app's language",                             Tool(&["settings_set"])),
    a("Settings › Projects folder", "where new projects go",                   Tool(&["settings_set"])),
    a("Settings › Ghidra folder and Java", "where Ghidra and Java are",        Tool(&["settings_set"])),
    a("Settings › Engine paths", "where external engines are",                 Tool(&["settings_set"])),
    a("Settings › Ask before running", "consent before running programs",     Tool(&["settings_set"])),
    a("Settings › Auto mode", "decide routine questions automatically",        Tool(&["settings_set"])),
    a("Settings › Asset budget", "budget for generated assets",                Tool(&["settings_set"])),
    a("Settings (all)",      "see every setting",                              Tool(&["settings_show"])),
    a("Theme",               "light or dark",                                  UiOnly("a look, not a product action (it is stored in settings, so settings_set theme also works)")),

    // ---- AI brains ---------------------------------------------------------------------------
    a("refresh_backends",    "the connected AI brains",                        Cli("ai list")),
    a("detect_backends",     "find AI on this computer",                       Cli("ai detect")),
    a("add_backend",         "connect an AI brain",                            Cli("ai add <name> --kind --model --base-url --ssh-host --key-env --key-stdin")),
    a("add_server",          "connect an AI server by its address",            Cli("ai add <name> --kind --base-url --key-env --key-stdin")),
    a("pick_model",          "list the models an AI can use",                  Cli("ai model <name>")),
    a("set_model",           "change the model an AI uses",                    Cli("ai model <name> <model>")),
    a("set_effort",          "change how hard a Claude AI thinks",             Cli("ai effort <name> <level>")),
    a("choose_backend",      "pick the AI brain",                              Cli("chat <question> --backend")),
    a("set_role",            "choose which AI builds or extracts",             Cli("ai extractor <name>")),

    // ---- Studying a target -------------------------------------------------------------------
    a("open_path",           "open an app or file as the target",              Tool(&["core_target_open"])),
    a("first_look",          "a first look at the target",                     Tool(&["core_target_triage"])),
    a("Home › Open a website", "open a web page as the target",                Tool(&["web_site_open"])),
    a("Workbench › Targets", "switch between open targets",                    Tool(&["core_target_select", "core_targets_list"])),
    a("send",                "ask about the target",                           Cli("chat <question> --target")),
    a("answer_consent",      "allow or refuse running a program",              Cli("tool <id> --allow-run")),
    a("export_report",       "save a Markdown report",                         Tool(&["core_report_save"])),
    a("run_tool",            "run any tool (palette, rails, views)",           Cli("tool <id>")),
    a("stop",                "stop answering and cancel running work",         UiOnly("cancelling belongs to the caller: Ctrl-C in the CLI, notifications/cancelled over MCP")),
    a("load_rail",           "fill a workbench list",                          UiOnly("a view; each list is a tool call by id")),
    a("load_view",           "fill a workbench view",                          UiOnly("a view; each view is a tool call by id")),
    a("ensure_rail_loaded",  "fill the current list if empty",                 UiOnly("a view")),
    a("pick",                "a native open or save dialog",                   UiOnly("dialogs never open for programmatic calls; headless callers pass paths")),
    a("Palette",             "find a command or tool",                         UiOnly("a view; `commands` and `tool <id> --help` list the same tools")),
    a("Panels and screens",  "Home, Ask, Workbench, Settings, panels",         UiOnly("navigation")),
];

/// `CraftApp` methods that aren't person-facing actions: callbacks, polling, drawing, helpers.
#[rustfmt::skip]
const PLUMBING: &[(&str, &str)] = &[
    ("stuck_banner", "draws what the lock watchdog found; `sync::problems` and its log are the headless side"),
    ("act", "runs a button's tool on a worker (play, preview, open folder)"),
    ("waiting_question", "finds the question an answer is for"),
    ("acted", "shows a button tool's result (toast, open the preview)"),
    ("engines_found", "a job's result"), ("engine_got", "a job's result"), ("ghidra_got", "a job's result"),
    ("ghidra_ready", "a query"), ("ghidra_missing", "a query"),
    ("load_prefs", "startup"), ("log", "the log panel"), ("toast", "a message"),
    ("settings_changed", "marks settings dirty; each setting has its row"), ("flush_settings", "saves settings"),
    ("refresh_view", "redraw data"), ("resolve_chat_evidence", "redraw data"), ("mark_dirty", "redraw data"),
    ("poll_conversation", "polling"), ("allow_for_project", "part of answer_consent"),
    ("handle_done", "a job's result"), ("tool_done", "a job's result"),
    ("tick", "the frame loop"), ("show", "drawing"), ("toasts", "drawing"), ("shortcuts", "keys"),
    ("builder_backend", "part of start_make"), ("need_builder", "part of start_make"), ("start_run", "part of start_make"), ("start_run_with", "part of start_run and continue_build"),
    ("resume", "part of follow_up"), ("poll_run", "polling"), ("launch", "part of start_run: RunSet::start, the queue rebuild_start uses too"),
    ("thumb_ready", "a job's result"), ("thumb", "drawing"), ("refresh_side_panel", "a view tally"),
];

fn crate_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
}

fn rust_files(dir: &Path) -> Vec<PathBuf> {
    let mut out: Vec<PathBuf> = std::fs::read_dir(dir).unwrap().flatten().map(|e| e.path()).filter(|p| p.extension().is_some_and(|x| x == "rs")).collect();
    out.sort();
    out
}

/// Names of `&mut self` methods inside `impl CraftApp { … }` blocks.
fn craft_app_methods() -> Vec<String> {
    let mut names = Vec::new();
    for f in rust_files(&crate_dir().join("src")) {
        let text = std::fs::read_to_string(&f).unwrap();
        let mut inside = false;
        for line in text.lines() {
            if line.starts_with("impl CraftApp ") {
                inside = true;
            } else if line == "}" {
                inside = false;
            } else if inside
                && let Some(rest) = line.trim_start().strip_prefix("pub fn ").or_else(|| line.trim_start().strip_prefix("fn "))
                && let Some((name, sig)) = rest.split_once('(')
                && sig.starts_with("&mut self")
            {
                names.push(name.to_string());
            }
        }
    }
    names
}

fn is_method_row(ui: &str) -> bool {
    !ui.contains(' ') && ui.chars().all(|c| c.is_ascii_lowercase() || c == '_')
}

/// Every tool the shipped apps have: the engine's plus the AI and setup layers' (as `Engine::shared`).
fn registry() -> Registry {
    Registry::new(craft_anything_engine::tools::all().into_iter().chain(craft_anything_ai::tools()).chain(craft_anything_setup::tools::specs()).collect())
}

#[test]
fn named_tools_exist_and_are_reachable_from_the_cli() {
    let r = registry();
    let mut missing = Vec::new();
    for act in ACTIONS {
        if let Tool(ids) = act.headless {
            for id in ids {
                match r.get(id) {
                    Some(s) if s.id == *id => {}
                    _ => missing.push(format!("{} -> {id}: not a registered tool", act.ui)),
                }
                let cli = id.replace('_', "-");
                if r.get(&cli).map(|s| s.id) != Some(*id) {
                    missing.push(format!("{} -> {id}: `craft-anything-cli {cli}` doesn't reach it", act.ui));
                }
            }
        }
    }
    assert!(missing.is_empty(), "headless parity:\n{}", missing.join("\n"));
}

#[test]
fn pending_tools_do_not_exist_yet() {
    let r = registry();
    let landed: Vec<String> = ACTIONS
        .iter()
        .filter_map(|act| match act.headless {
            Pending { tool: Some(id), .. } if r.get(id).is_some() => Some(format!("{} -> {id} exists now: make this row `Tool(&[\"{id}\"])`", act.ui)),
            _ => None,
        })
        .collect();
    assert!(landed.is_empty(), "headless parity:\n{}", landed.join("\n"));
}

#[test]
fn named_cli_commands_and_flags_exist() {
    let cli_src = crate_dir().join("../../apps/craft-anything-cli/src");
    let text: String = rust_files(&cli_src).iter().map(|f| std::fs::read_to_string(f).unwrap()).collect::<Vec<_>>().join("\n");
    let mut missing = Vec::new();
    for act in ACTIONS {
        let Cli(command) = act.headless else { continue };
        for word in command.split_whitespace().filter(|w| !w.starts_with('<')) {
            let found = if let Some(flag) = word.strip_prefix("--") {
                // A clap field (`pub continue_in:`, `out:`) or a flag the CLI reads by hand (`"--allow-run"`).
                text.contains(&format!(" {}:", flag.replace('-', "_"))) || text.contains(&format!("\"{word}\""))
            } else {
                // A subcommand: an enum variant (`Rebuild(…)`, `Add {`, `List,`).
                let variant: String = word.split('-').map(|p| p[..1].to_uppercase() + &p[1..]).collect();
                text.contains(&format!("\n    {variant}"))
            };
            if !found {
                missing.push(format!("{} -> `{command}`: no `{word}` in the CLI", act.ui));
            }
        }
    }
    assert!(missing.is_empty(), "headless parity:\n{}", missing.join("\n"));
}

#[test]
fn every_craft_app_action_has_a_row() {
    let methods = craft_app_methods();
    assert!(methods.iter().any(|m| m == "start_make"), "the method scan found nothing: {methods:?}");
    let listed = |m: &str| ACTIONS.iter().any(|a| a.ui == m) || PLUMBING.iter().any(|(p, _)| *p == m);
    let new: Vec<&String> = methods.iter().filter(|m| !listed(m)).collect();
    assert!(new.is_empty(), "new CraftApp methods: add each to ACTIONS (with its tool or CLI command) or PLUMBING: {new:?}");
    let gone: Vec<&str> = ACTIONS
        .iter()
        .map(|a| a.ui)
        .filter(|ui| is_method_row(ui))
        .chain(PLUMBING.iter().map(|(p, _)| *p))
        .filter(|m| !methods.iter().any(|x| x == m))
        .collect();
    assert!(gone.is_empty(), "rows name CraftApp methods that no longer exist (renamed or removed): {gone:?}");
}

#[test]
fn every_row_says_why_when_there_is_no_counterpart() {
    for act in ACTIONS {
        match act.headless {
            Pending { why, .. } | UiOnly(why) => assert!(!why.trim().is_empty(), "{}: give the reason", act.ui),
            Tool(ids) => assert!(!ids.is_empty(), "{}: name a tool", act.ui),
            Cli(c) => assert!(!c.trim().is_empty(), "{}: name a command", act.ui),
        }
        assert!(!act.does.is_empty());
    }
}

/// Counts, for the PR and the roadmap: `cargo test -p craft-anything-ui-egui --test headless_parity -- --nocapture`.
#[test]
fn summary() {
    let (mut covered, mut pending, mut ui_only) = (0, 0, 0);
    for act in ACTIONS {
        match act.headless {
            Tool(_) | Cli(_) => covered += 1,
            Pending { .. } => pending += 1,
            UiOnly(_) => ui_only += 1,
        }
    }
    println!("headless parity: {covered} covered, {pending} pending, {ui_only} UI-only ({} actions)", ACTIONS.len());
}
