//! The Craft Anything engine: one session, one registry of tools, one way in.
//!
//! The desktop UI, the CLI, the MCP server and the built-in AI agent all call [`Engine::call`]
//! with a tool id and JSON params. The engine checks availability and consent, runs the tool,
//! records the evidence it returns, and turns any escaped panic into an error.
#![deny(clippy::unwrap_used, clippy::expect_used, clippy::panic, clippy::unimplemented, clippy::todo, clippy::unreachable)]

pub mod clean_room;
pub mod feed;
pub mod inbox;
pub mod journal;
pub mod mechanics;
pub mod outputs;
pub mod pins;
pub mod plugins;
pub mod project;
pub mod questions;
pub mod registry;
pub mod self_test;
pub mod session;
pub mod settings;
pub mod target;
#[doc(hidden)]
pub mod testing;
pub mod tool;
pub mod tool_list;
pub mod tools;
pub mod versioned;
pub mod wasm_plugins;
pub mod workspace;

pub use craft_anything_evidence as evidence;
pub use registry::Registry;
pub use session::Session;
pub use settings::{Mode, Settings};
pub use target::{Target, TargetKind};
pub use tool::{Caller, CancelToken, Ctx, Effects, Progress, Requires, ToolOutput, ToolSpec, Toolset};

use craft_anything_evidence::{ErrorCode, ToolError};
use craft_anything_platform::sync::{Mutex, MutexGuard};
use serde_json::Value;
use std::sync::PoisonError;

/// Whether the caller has the user's consent for a tool that runs code or changes a device.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum Consent {
    /// Not asked: the engine refuses consent-gated tools unless the project or settings allow them.
    #[default]
    NotAsked,
    /// The user approved this one call.
    Granted,
}

/// Options for one call.
pub struct CallOptions<'a> {
    pub caller: Caller,
    pub consent: Consent,
    pub cancel: CancelToken,
    pub progress: &'a tool::ProgressFn,
}

fn no_progress(_: Progress) {}

impl CallOptions<'static> {
    pub fn new(caller: Caller) -> Self {
        CallOptions { caller, consent: Consent::NotAsked, cancel: CancelToken::default(), progress: &no_progress }
    }
}

impl<'a> CallOptions<'a> {
    pub fn with_consent(mut self, consent: Consent) -> Self {
        self.consent = consent;
        self
    }

    pub fn with_cancel(mut self, cancel: CancelToken) -> Self {
        self.cancel = cancel;
        self
    }

    pub fn with_progress<'b>(self, progress: &'b tool::ProgressFn) -> CallOptions<'b> {
        CallOptions { caller: self.caller, consent: self.consent, cancel: self.cancel, progress }
    }
}

/// Why a tool can't run right now, in words a beginner understands, plus how to fix it.
#[derive(Debug, Clone, PartialEq, serde::Serialize)]
pub struct Availability {
    pub available: bool,
    pub reason: Option<String>,
    pub remediation: Option<String>,
}

impl Availability {
    fn ok() -> Self {
        Availability { available: true, reason: None, remediation: None }
    }

    pub(crate) fn no(reason: impl Into<String>, remediation: impl Into<String>) -> Self {
        Availability { available: false, reason: Some(reason.into()), remediation: Some(remediation.into()) }
    }
}

/// The engine. Cheap to share behind an `Arc`.
pub struct Engine {
    registry: Registry,
    session: Mutex<Session>,
}

/// A handle to the engine a tool runs in, for tools that start work which calls back into it (a
/// rebuild run). Only set on engines made with [`Engine::shared`]; it never keeps the engine alive.
pub struct EngineRef(pub std::sync::Weak<Engine>);

impl Engine {
    pub fn new(session: Session) -> Self {
        Engine { registry: Registry::with_all_tools(), session: Mutex::new(session) }
    }

    /// The engine as most apps use it: shared, with tools from higher layers (`extra`, e.g. the
    /// AI layer's rebuild tools) registered next to the engine's own, and an [`EngineRef`] in the
    /// session so those tools can reach it. A duplicate id keeps the engine's own tool.
    pub fn shared(session: Session, extra: Vec<ToolSpec>) -> std::sync::Arc<Engine> {
        Engine::shared_with(session, extra, Vec::new())
    }

    /// [`Engine::shared`] plus tools defined at run time (a plugin's, an external MCP server's):
    /// owned names and a JSON schema, served by a function that can tell them apart by
    /// [`Ctx::tool`]. Invalid or duplicate ones are skipped and logged.
    pub fn shared_with(session: Session, extra: Vec<ToolSpec>, runtime: Vec<registry::RuntimeTool>) -> std::sync::Arc<Engine> {
        let mut tools = tools::all();
        tools.extend(extra);
        std::sync::Arc::new_cyclic(|me| {
            let mut session = session;
            session.ext.insert(std::sync::Arc::new(EngineRef(me.clone())));
            Engine { registry: Registry::new(tools).with_runtime(runtime), session: Mutex::new(session) }
        })
    }

    pub fn registry(&self) -> &Registry {
        &self.registry
    }

    /// Lock the session (recovering from a poisoned lock rather than cascading a panic).
    #[track_caller]
    pub fn session(&self) -> MutexGuard<'_, Session> {
        self.session.lock().unwrap_or_else(PoisonError::into_inner)
    }

    /// Try to lock without blocking (the UI uses this so a long tool never freezes a frame).
    #[track_caller]
    pub fn try_session(&self) -> Option<MutexGuard<'_, Session>> {
        match self.session.try_lock() {
            Ok(g) => Some(g),
            Err(std::sync::TryLockError::Poisoned(p)) => Some(p.into_inner()),
            Err(std::sync::TryLockError::WouldBlock) => None,
        }
    }

    pub fn availability(&self, spec: &ToolSpec, session: &Session) -> Availability {
        if let Some(no) = clean_room::availability(spec.id, session.clean_room()) {
            return no;
        }
        match spec.requires {
            Requires::Nothing => Availability::ok(),
            Requires::Target => {
                if session.active_id().is_some() {
                    Availability::ok()
                } else {
                    Availability::no("Nothing is open yet.", "Open a file, app or folder first.")
                }
            }
            Requires::Ghidra => {
                if !session.clean_room() {
                    Availability::ok()
                } else {
                    Availability::no("This needs Deep mode (with Ghidra), and you're in Clean room mode.", "Turn on Deep mode in the title bar or Settings.")
                }
            }
            Requires::Engine(id) => match session.settings.engine_path(id) {
                Some(_) => Availability::ok(),
                None => Availability::no(
                    format!("This needs {} installed.", craft_anything_engines::display_name(id)),
                    format!("Install {} from Settings → Engines.", craft_anything_engines::display_name(id)),
                ),
            },
            Requires::Os(hosts) => {
                if hosts.contains(&std::env::consts::OS) {
                    Availability::ok()
                } else {
                    let names = hosts.iter().map(|h| match *h {
                        "macos" => "macOS",
                        "windows" => "Windows",
                        "linux" => "Linux",
                        other => other,
                    });
                    let names = names.collect::<Vec<_>>().join(" or ");
                    Availability::no(
                        format!("This needs {names} and is not available on this host ({}).", craft_anything_evidence::host_triple()),
                        format!("Run it on {names}."),
                    )
                }
            }
        }
    }

    /// Run a tool by id. When a project is open, the call is appended to its journal.
    pub fn call(&self, id: &str, params: Value, opts: CallOptions<'_>) -> Result<ToolOutput, ToolError> {
        let started = std::time::Instant::now();
        let logged_params = journal::bounded(&params);
        let caller = opts.caller;
        let result = self.call_inner(id, params, opts);
        let outcome = match &result {
            Ok(ToolOutput::Evidence(ev)) => serde_json::json!({"ok": true, "evidence_id": ev.id}),
            Ok(ToolOutput::Value(_)) => serde_json::json!({"ok": true}),
            Err(e) => serde_json::json!({"ok": false, "error_code": e.code, "error": e.message}),
        };
        let mut entry = serde_json::json!({"tool": id, "caller": caller, "params": logged_params, "duration_ms": started.elapsed().as_millis() as u64});
        if let (Some(m), serde_json::Value::Object(o)) = (entry.as_object_mut(), outcome) {
            m.extend(o);
        }
        self.journal("tool_call", entry);
        result
    }

    /// Append an entry to the open project's journal (no-op without a project). Never fails.
    pub fn journal(&self, kind: &str, entry: Value) {
        let root = self.session().project.as_ref().map(|p| p.root.clone());
        if let Some(root) = root {
            journal::append(&root, kind, entry);
        }
    }

    fn call_inner(&self, id: &str, params: Value, opts: CallOptions<'_>) -> Result<ToolOutput, ToolError> {
        let spec = *self.registry.get(id).ok_or_else(|| {
            ToolError::invalid(format!("No tool named {id}")).with_remediation("List tools with `craft-anything-cli commands` or the command palette.")
        })?;
        // Stop works while waiting for the session, and a holder that looks stuck is an error here,
        // not a wait forever. Tools are long jobs: the label says so (they have their own deadlines).
        let cancel = opts.cancel.clone();
        let mut session = match self.session.lock_unless(&|| cancel.is_cancelled()) {
            Ok(g) => g.unwrap_or_else(PoisonError::into_inner),
            Err(craft_anything_platform::sync::GaveUp::Stopped) => return Err(ToolError::cancelled()),
            Err(craft_anything_platform::sync::GaveUp::Stuck(why)) => {
                return Err(ToolError::new(ErrorCode::TimedOut, format!("{} couldn't start because another part of the app is stuck.", spec.title))
                    .with_remediation("Restart the app; your work is kept.")
                    .with_details(serde_json::json!({"lock": why})));
            }
        };
        session.label(spec.id);
        if session.clean_room() && !clean_room::allows(spec.id) {
            return Err(clean_room::refusal(spec.id));
        }
        let avail = self.availability(&spec, &session);
        if !avail.available {
            let code = match spec.requires {
                Requires::Target => ErrorCode::NotFound,
                // A missing external engine (adb, frida, …) is a provider problem, not a capability
                // the build lacks; agents branch on this to offer an install.
                Requires::Engine(_) => ErrorCode::EngineMissing,
                _ => ErrorCode::FeatureMissing,
            };
            let mut err = ToolError::new(code, avail.reason.unwrap_or_default());
            err.remediation = avail.remediation;
            if matches!(spec.requires, Requires::Os(_)) {
                err = err.with_details(serde_json::json!({"reason": "wrong_os", "tool": spec.id}));
            }
            return Err(err);
        }
        if spec.effects.needs_consent() && opts.consent != Consent::Granted {
            let allowed = !session.settings.ask_before_running || session.project.as_ref().is_some_and(|p| p.is_allowed(spec.id));
            if !allowed {
                return Err(ToolError::new(ErrorCode::ConsentRequired, format!("{} runs code or changes a device, so it needs your OK first.", spec.title))
                    .with_remediation("Approve it when asked, or allow it for this project in Settings.")
                    .with_details(serde_json::json!({"tool": spec.id})));
            }
        }
        let run = spec.run;
        let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            let mut ctx = Ctx { tool: spec.id, session: &mut session, cancel: opts.cancel.clone(), progress: opts.progress, caller: opts.caller };
            run(&mut ctx, params)
        }));
        let output = match result {
            Ok(r) => r?,
            Err(panic) => {
                let what = panic.downcast_ref::<&str>().map(|s| s.to_string()).or_else(|| panic.downcast_ref::<String>().cloned()).unwrap_or_default();
                log::error!("tool {id} panicked: {what}");
                return Err(ToolError::internal(format!("{} hit a bug and stopped safely. Your work is kept. ({what})", spec.title)));
            }
        };
        if let ToolOutput::Evidence(ev) = &output {
            session.record((**ev).clone())?;
        }
        Ok(output)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unknown_tool_is_an_error_not_a_panic() {
        let e = Engine::new(crate::testing::session());
        let err = e.call("no_such_tool", Value::Null, CallOptions::new(Caller::Cli)).unwrap_err();
        assert_eq!(err.code, ErrorCode::BadInput);
    }

    #[test]
    fn every_engine_a_tool_needs_is_in_the_engine_table() {
        let e = Engine::new(crate::testing::session());
        for spec in e.registry().all() {
            if let Requires::Engine(id) = spec.requires {
                assert!(craft_anything_engines::engine(id).is_some(), "{} needs unknown engine {id:?}", spec.id);
            }
        }
    }

    #[test]
    fn target_tools_explain_what_to_do() {
        let e = Engine::new(crate::testing::session());
        let err = e.call("native_cursor_show", Value::Null, CallOptions::new(Caller::Mcp)).unwrap_err();
        assert_eq!(err.code, ErrorCode::NotFound);
        assert!(err.remediation.is_some());
    }

    #[test]
    fn higher_layers_add_tools_and_reach_the_engine() {
        fn whoami(ctx: &mut Ctx<'_>, _: Value) -> Result<ToolOutput, ToolError> {
            let alive = ctx.session.ext.get::<EngineRef>().and_then(|r| r.0.upgrade()).is_some();
            Ok(ToolOutput::Value(serde_json::json!({"engine": alive})))
        }
        let extra = ToolSpec {
            id: "test_whoami",
            title: "Who am I",
            summary: "Test tool.",
            beginner: "Test tool.",
            toolset: Toolset::Core,
            effects: Effects::READ_ONLY,
            requires: Requires::Nothing,
            input_schema: tool::empty_schema,
            run: whoami,
        };
        let e = Engine::shared(crate::testing::session(), vec![extra]);
        assert!(e.registry().get("core_target_triage").is_some(), "the engine's own tools are still there");
        let out = e.call("test_whoami", Value::Null, CallOptions::new(Caller::Cli)).unwrap().to_json();
        assert_eq!(out["result"]["engine"], true);
    }

    #[test]
    fn tools_defined_at_run_time_get_their_own_schema_group_and_id() {
        use registry::{RuntimeTool, custom_toolset};
        fn echo(ctx: &mut Ctx<'_>, params: Value) -> Result<ToolOutput, ToolError> {
            Ok(ToolOutput::Value(serde_json::json!({"tool": ctx.tool, "params": params})))
        }
        let group = custom_toolset("demo_plugin").unwrap();
        let tool = |id: &str, schema: Value| RuntimeTool {
            id: id.into(),
            title: format!("Demo {id}"),
            summary: "A demo tool.".into(),
            beginner: "A demo tool.".into(),
            toolset: group,
            effects: Effects::READ_ONLY,
            requires: Requires::Nothing,
            schema,
            run: echo,
        };
        let schema = serde_json::json!({"type": "object", "properties": {"word": {"type": "string"}}});
        let e = Engine::shared_with(
            crate::testing::session(),
            Vec::new(),
            vec![
                tool("demo_one", schema.clone()),
                tool("demo_two", schema.clone()),
                tool("Bad Id", schema.clone()),
                tool("core_target_triage", schema.clone()),
                tool("demo_three", serde_json::json!("not an object")),
            ],
        );
        let r = e.registry();
        assert!(r.get("demo_one").is_some() && r.get("demo_two").is_some());
        assert!(r.get("demo_three").is_none(), "a schema must be an object");
        assert_ne!(r.get("core_target_triage").map(|s| s.title), Some("Demo core_target_triage"), "an engine tool keeps its id");
        assert!(r.get("bad_id").is_none());
        // One function serves both; it knows which was called.
        let out = e.call("demo_two", serde_json::json!({"word": "hi"}), CallOptions::new(Caller::Cli)).unwrap().to_json();
        assert_eq!(out["result"]["tool"], "demo_two");
        let spec = *r.get("demo_one").unwrap();
        assert_eq!(r.mcp_descriptor(&spec)["inputSchema"], schema);
        assert!(r.toolsets().contains(&group) && r.toolset("demo_plugin") == Some(group));
        assert_eq!(serde_json::to_value(group).unwrap(), "demo_plugin");
        assert!(custom_toolset("No Spaces").is_none());
        assert_eq!(custom_toolset("core"), Some(Toolset::Core), "a built-in id is the built-in group");
    }
}
