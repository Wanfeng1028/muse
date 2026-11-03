//! Sample data for the offscreen snapshot and UI tests: a tiny fake program, a few evidence records
//! and a conversation. Nothing here touches the disk or the network.

use crate::state::{CenterTab, ChatItem, Fill, RailKind, RightTab, Screen};
use crate::{CraftApp, TargetInfo};
use craft_anything_ai::{AiHub, BackendConfig, BackendKind, Detected};
use craft_anything_engine::evidence::{Confidence, Coverage, Environment, Evidence, EvidenceBuilder, Limitation, Location, Severity, Unknown};
use craft_anything_engine::target::Target;
use craft_anything_engine::workspace::{CheckResult, Claim, Manifest, Status, TargetRef, Workspace};
use craft_anything_engine::{Engine, Mode, Session, Settings};
use serde_json::json;
use std::path::PathBuf;
use std::sync::Arc;

/// Bytes that sniff as a small Linux program, with some readable strings inside.
pub fn sample_program() -> Vec<u8> {
    let mut b = vec![0x7f, b'E', b'L', b'F', 2, 1, 1, 0];
    b.resize(64, 0);
    for s in ["Calculator", "%g", "percent_key_pressed", "display_update", "https://updates.example.com/check", "libgtk-3.so.0", "Division by zero"] {
        b.extend_from_slice(s.as_bytes());
        b.push(0);
    }
    for i in 0..1400u32 {
        b.push((i.wrapping_mul(2_654_435_761) >> 24) as u8);
    }
    b
}

fn sample_target() -> Target {
    Target::from_bytes(PathBuf::from("/samples/calculator"), "calculator".into(), sample_program())
}

fn build(op: &str, summary: &str, c: Confidence, result: serde_json::Value, t: &Target) -> Option<Evidence> {
    EvidenceBuilder::new(op, t.subject(), Environment::builtin(true)).summary(summary).confidence(c).result(result).coverage(Coverage::complete(1)).build().ok()
}

/// The "how does % work" proof.
pub fn percent_evidence() -> Option<Evidence> {
    let t = sample_target();
    EvidenceBuilder::new("native_function_pseudocode", t.subject(), Environment::builtin(true))
        .summary("When you press %, the calculator divides the number on screen by 100 and shows the result. It reads the display, does one division, then redraws.")
        .confidence(Confidence::Derived)
        .result(json!({
            "function": "percent_key_pressed",
            "address": "0x401a30",
            "pseudo_c": "void percent_key_pressed(Calc *c) {\n    double v = display_value(c);\n    v = v / 100.0;   // the whole trick\n    display_update(c, v);\n}"
        }))
        .location(Location::address(0x401a30).with_label("percent_key_pressed"))
        .location(Location::address(0x401a52).with_label("divide by 100"))
        .location(Location::address(0x401b10).with_label("display_update"))
        .limitation(Limitation::new("stripped_binary", "Names were removed from the program; we worked them out from the strings around them."))
        .coverage(Coverage::complete(3))
        .build()
        .ok()
}

pub fn functions_evidence() -> Option<Evidence> {
    let t = sample_target();
    let names = [
        ("_start", 0x401000, 42),
        ("main", 0x401030, 310),
        ("init_window", 0x401170, 220),
        ("on_key", 0x401250, 488),
        ("digit_key_pressed", 0x401440, 96),
        ("operator_key_pressed", 0x4014a0, 180),
        ("percent_key_pressed", 0x401a30, 64),
        ("equals_key_pressed", 0x401a70, 256),
        ("display_value", 0x401b00, 16),
        ("display_update", 0x401b10, 140),
        ("format_number", 0x401ba0, 330),
        ("check_for_updates", 0x401cf0, 410),
        ("http_get", 0x401e90, 512),
        ("show_error", 0x402090, 88),
        ("sub_4020f0", 0x4020f0, 24),
        ("sub_402108", 0x402108, 36),
    ];
    let items: Vec<_> = names.iter().map(|(n, a, s)| json!({"name": n, "address": a, "size": s})).collect();
    build(
        "native_functions_list",
        "16 functions found by following calls from the entry point.",
        Confidence::Derived,
        json!({"total": items.len(), "functions": items}),
        &t,
    )
}

fn strings_evidence() -> Option<Evidence> {
    let t = sample_target();
    build(
        "native_strings_browse",
        "7 readable strings, including a web address used to check for updates.",
        Confidence::Observed,
        json!({"strings": [
            {"value": "Calculator", "offset": 64},
            {"value": "https://updates.example.com/check", "offset": 120}
        ]}),
        &t,
    )
}

/// An engine with the sample program open and a few findings in the ledger.
pub fn engine(mode: Mode, first_run_done: bool) -> Arc<Engine> {
    let settings = Settings { mode, first_run_done, language: "en".into(), ..Default::default() };
    let mut session = Session::new(settings);
    session.add_target(sample_target());
    for e in [strings_evidence(), functions_evidence(), percent_evidence()].into_iter().flatten() {
        let _ = session.record(e);
    }
    let _ = session.put_unknown(Unknown::new("Does check_for_updates send anything about the user?", "network", Severity::Medium));
    Arc::new(Engine::new(session))
}

/// Deep mode on, in the app and its engine: for scenes and tests that look inside the sample.
pub fn deep(app: &mut CraftApp) {
    app.settings.deep_mode = true;
    app.engine.session().settings.deep_mode = true;
}

/// A headless app over `engine` (no disk writes, no dialogs).
pub fn app(engine: Arc<Engine>) -> CraftApp {
    // AI changes made in a demo or a test (adding, turning off, removing one) go to a folder of
    // its own, never the person's settings or system keychain.
    static N: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
    let now = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map_or(0, |d| d.as_nanos());
    let store = std::env::temp_dir().join(format!("craft-anything-demo-{now}-{}", N.fetch_add(1, std::sync::atomic::Ordering::Relaxed)));
    let keys = craft_anything_ai::KeyStore::file_only(store.join("keys.toml"));
    let hub = Arc::new(AiHub::with_stores(engine.clone(), store.join("config.toml"), keys));
    let mut app = CraftApp::new(engine, hub);
    app.persist = false;
    app.headless = true;
    app.backends = vec![BackendConfig {
        name: "Claude".into(),
        kind: BackendKind::Anthropic,
        model: "claude-opus-5-5".into(),
        base_url: None,
        ssh_host: None,
        enabled: true,
    }];
    app.settings.recent = vec![PathBuf::from("/samples/calculator"), PathBuf::from("/Applications/Notes.app"), PathBuf::from("/home/me/Downloads/game.apk")];
    app
}

/// A conversation that shows every kind of chat item.
pub fn fill_ask(app: &mut CraftApp) {
    deep(app);
    app.state.screen = Screen::Ask;
    app.state.backend = Some("Claude".into());
    app.state.chat = vec![
        ChatItem::User("How does the % key work?".into()),
        ChatItem::Tool { call_id: "c1".into(), tool: "native_strings_browse".into(), ok: Some(true), summary: "Found the word \"percent\" next to a function.".into(), evidence_id: None, evidence: None },
        ChatItem::Assistant {
            text: "Short version: **% just divides by 100.**\n\nWhen you press the key, the program runs one small function. It reads the number on the display, divides it by 100, and puts the answer back on screen. There's no special maths library involved.\n\n- The function sits right next to the other key handlers.\n- It's only a few bytes of code, so there's nothing hidden.".into(),
            backend: Some("Claude".into()),
            streaming: false,
        },
    ];
    if let Some(e) = percent_evidence() {
        app.state.chat.push(ChatItem::Proof { intro: String::new(), evidence: Box::new(e) });
    }
    app.state.chat.push(ChatItem::Consent {
        call_id: "c2".into(),
        tool: "runtime_walkthrough_record".into(),
        title: "Watch it run".into(),
        explanation: "To be certain, I'd run the calculator in a sandbox and press % once while watching.".into(),
        answer: None,
    });
}

/// The workbench with a populated rail and the built-in hex view.
pub fn fill_workbench(app: &mut CraftApp) {
    deep(app);
    app.settings.mode = Mode::Experienced;
    if let Some(e) = functions_evidence() {
        let sel = crate::workbench::rows(&e.result).get(6).cloned();
        app.state.selection = sel;
        app.state.lists.insert(RailKind::Functions, Fill::Ready(Box::new(e)));
    }
    app.state.rail = RailKind::Functions;
    app.state.center = CenterTab::PseudoC;
    if let Some(e) = percent_evidence() {
        app.state.views.insert(CenterTab::PseudoC, Fill::Ready(Box::new(e)));
    }
    app.state.right = RightTab::Evidence;
    app.state.backend = Some("Claude".into());
    app.state.chat = vec![
        ChatItem::User("Where is the update check called from?".into()),
        ChatItem::Tool { call_id: "x1".into(), tool: "native_function_callers_list".into(), ok: Some(true), summary: "1 caller: main+0x8c".into(), evidence_id: None, evidence: None },
        ChatItem::Assistant { text: "`check_for_updates` (0x401cf0) is called once, from `main` at 0x4010bc, after the window opens. It calls `http_get` with the URL string at offset 0x78.".into(), backend: Some("Claude".into()), streaming: false },
    ];
}

/// A target summary for report tests.
pub fn target_info() -> TargetInfo {
    let t = sample_target();
    TargetInfo { id: t.id.clone(), name: t.name.clone(), kind: t.kind, path: t.path.clone(), sha256: t.sha256.clone(), bytes: t.bytes.clone() }
}

/// What "Pick a brain" might find on a typical machine.
pub fn detected() -> Vec<Detected> {
    let cfg = |name: &str, kind, model: &str| BackendConfig { name: name.into(), kind, model: model.into(), base_url: None, ssh_host: None, enabled: true };
    vec![
        Detected {
            suggestion: cfg("Claude Code", BackendKind::AgentCli, "claude-code"),
            reason: "Found the claude command on this computer.".into(),
            needs_key: false,
        },
        Detected {
            suggestion: cfg("Ollama", BackendKind::OpenaiCompatible, "llama3.2"),
            reason: "Found Ollama running with 3 models.".into(),
            needs_key: false,
        },
        Detected { suggestion: cfg("OpenRouter", BackendKind::Openrouter, "auto"), reason: "Use any model through one key.".into(), needs_key: true },
    ]
}

fn workspace(slug: &str, name: &str, request: &str, target: TargetRef, status: Status, age_min: u64) -> Workspace {
    let at = craft_anything_engine::inbox::now_ms().saturating_sub(age_min * 60_000);
    Workspace {
        root: PathBuf::from(format!("/demo/Craft Anything/{slug}")),
        manifest: Manifest {
            version: craft_anything_engine::workspace::MANIFEST_VERSION,
            name: name.into(),
            request: request.into(),
            target,
            stack: "React + TypeScript (Vite)".into(),
            status,
            note: String::new(),
            created_ms: at,
            updated_ms: at,
            checks: Vec::new(),
            agent_session: None,
            agent_session_by: None,
            allowed_actions: Vec::new(),
            last_reply: String::new(),
            asset_budget_usd: craft_anything_engine::workspace::ASSET_BUDGET_USD,
            generate_assets: false,
            app_in_root: false,
            start_files: Vec::new(),
            builder: None,
            questions: None,
            awaiting_check: false,
        },
    }
}

/// A few projects on Home, and an agent app ready to build.
pub fn fill_projects(app: &mut CraftApp) {
    app.backends = vec![BackendConfig {
        name: "Claude Code".into(),
        kind: BackendKind::AgentCli,
        model: "claude-code".into(),
        base_url: None,
        ssh_host: None,
        enabled: true,
    }];
    app.state.make.url = "https://example.com".into();
    app.state.make.request = "Recreate this website".into();
    app.projects = vec![
        workspace("example-com", "example.com", "Recreate this website", TargetRef::Website { url: "https://example.com".into() }, Status::Building, 3),
        workspace("snake", "Snake", "A snake game in Rust", TargetRef::None, Status::Ready, 60 * 26),
        workspace("notes", "Notes", "Rebuild this app in Rust", TargetRef::Local { path: PathBuf::from("/Applications/Notes.app") }, Status::NeedsYou, 60 * 50),
    ];
}

/// A project mid-build: steps, the agent's words, collapsed tool work, a question and a check.
pub fn fill_project(app: &mut CraftApp) {
    use crate::state::FeedItem;
    use craft_anything_ai::rebuild::Step;
    use craft_anything_engine::inbox::{Request, RequestKind};
    let mut ws = workspace("example-com", "example.com", "Recreate this website", TargetRef::Website { url: "https://example.com".into() }, Status::Ready, 2);
    let page = |name: &str, dir: &str, similarity| craft_anything_engine::workspace::PageLikeness { name: name.into(), dir: dir.into(), similarity };
    let check = CheckResult {
        similarity: Some(93.4),
        at_ms: 0,
        pages: vec![page("start page", "", 96.0), page("/about", "routes/about", 90.8)],
        claims: vec![
            Claim::new("The start page doesn't scroll sideways at 390 px", true, ""),
            Claim::new("The start page loads every file it asks for", true, ""),
            Claim::new("/about doesn't scroll sideways at 390 px", false, "it's 412 px wide"),
        ],
        ..CheckResult::new(CheckResult::WEB_VISUAL, 1, true, "1440 px: 95% alike (page height 900 vs 912 px); 390 px: 92% alike (page height 900 vs 940 px)")
    };
    ws.manifest.checks.push(check.clone());
    app.backends = vec![BackendConfig {
        name: "Claude Code".into(),
        kind: BackendKind::AgentCli,
        model: "claude-code".into(),
        base_url: None,
        ssh_host: None,
        enabled: true,
    }];
    app.state.feed = vec![
        FeedItem::User("Recreate this website".into()),
        FeedItem::Step { step: Step::Study, text: "Opening https://example.com in a private browser…".into() },
        FeedItem::Step { step: Step::Study, text: "Photographing the page and reading its layout…".into() },
        FeedItem::Step { step: Step::Build, text: "Building the first version…".into() },
        FeedItem::Agent { text: "I studied the screenshots and the layout: one centred card with a heading, two short paragraphs and a link, on a soft grey page.".into(), streaming: false },
        FeedItem::Work { tools: ["Read", "Read", "Write", "Write", "Write", "Bash", "Bash"].iter().map(|t| (t.to_string(), Some(true))).collect(), notes: Vec::new() },
        FeedItem::Ask {
            request: Request { id: "1-1-0".into(), kind: RequestKind::Question, title: "Is example.com your site, or should I use placeholder text?".into(), detail: "If it's yours, I can keep the original wording.".into(), choices: vec!["It's mine — keep the text".into(), "Use placeholder text".into()], allow_text: true, action: None, created_ms: 0 },
            answer: Some("Use placeholder text".into()),
        },
        FeedItem::Step { step: Step::Check, text: "Checking the build against the original…".into() },
        FeedItem::Check(check),
        FeedItem::Agent { text: "Your version is ready: a centred card with the same spacing, font sizes and colours as the original, built with React. The words are placeholders. You could ask for a dark mode or a contact form next.".into(), streaming: false },
        FeedItem::Ask {
            request: Request { id: "1-1-1".into(), kind: RequestKind::Approval, title: "Run a command: `curl https://example.com/robots.txt`".into(), detail: "{\n  \"command\": \"curl https://example.com/robots.txt\"\n}".into(), choices: vec![], allow_text: false, action: Some("bash:curl".into()), created_ms: 0 },
            answer: None,
        },
    ];
    app.facts = crate::project::Facts {
        root: ws.root.clone(),
        open_questions: vec!["May the original's logo and text be reused, or must they be placeholders?".into()],
        ..Default::default()
    };
    app.workspace = Some(ws);
    app.state.screen = Screen::Project;
}
