//! The syntax-tree fact extractor: one pass over a parsed program that records imports, exports,
//! Electron IPC and windows, network endpoints, routes, storage, platform effects, events and a
//! per-function call/string summary. Execution-free: nothing is evaluated.

use crate::model::*;
use crate::util::{LineIndex, push_unique};
use oxc_ast::ast::*;
use oxc_ast_visit::{Visit, walk};
use oxc_semantic::Scoping;
use oxc_span::GetSpan;
use oxc_syntax::scope::ScopeFlags;
use oxc_syntax::symbol::SymbolId;
use std::collections::{BTreeMap, HashMap, HashSet};

mod api;

/// Caps that keep one hostile file from producing unbounded output.
pub const MAX_LIST: usize = 5_000;
pub const MAX_FUNCTIONS: usize = 20_000;
pub const MAX_STRINGS: usize = 4_000;
pub const MAX_STRING_LEN: usize = 240;
const MAX_FN_CALLS: usize = 200;
const MAX_FN_STRINGS: usize = 64;
const MAX_PATH_DEPTH: usize = 24;
const MAX_NAMED_OBJECTS: usize = 4_096;

/// Keys that make an object literal worth remembering as window options, or as webPreferences.
const WINDOW_OPTION_KEYS: &[&str] = &["webPreferences", "width", "height", "show", "frame", "title", "parent", "modal"];
const WEB_PREFERENCE_KEYS: &[&str] = &[
    "nodeIntegration",
    "contextIsolation",
    "sandbox",
    "webSecurity",
    "preload",
    "nodeIntegrationInWorker",
    "nodeIntegrationInSubFrames",
    "allowRunningInsecureContent",
    "webviewTag",
    "enableRemoteModule",
    "experimentalFeatures",
];

/// webPreferences and preload as read from window options.
#[derive(Debug, Clone, Default)]
struct WindowOptions {
    prefs: BTreeMap<String, PrefValue>,
    preload: Option<String>,
    /// The named objects they were read through, outermost first.
    via: Vec<Key>,
}

impl WindowOptions {
    fn dynamic() -> Self {
        WindowOptions { prefs: BTreeMap::from([("webPreferences".to_string(), PrefValue::Text("dynamic".into()))]), ..Default::default() }
    }
}

/// An object literal bound to a variable, read both ways a window can use it.
struct NamedObject {
    at: NamedObjectRef,
    /// Read as `new BrowserWindow(it)`, when it looks like window options.
    options: Option<WindowOptions>,
    /// Read as `webPreferences: it`, when it looks like webPreferences.
    prefs: Option<WindowOptions>,
}

/// A resolved reference: an optional module plus a member path.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub(crate) struct Ref {
    pub module: Option<String>,
    pub segs: Vec<String>,
}

impl Ref {
    fn local(name: &str) -> Ref {
        Ref { module: None, segs: vec![name.to_string()] }
    }

    fn push(mut self, s: &str) -> Ref {
        self.segs.push(s.to_string());
        self
    }

    /// Canonical dotted form: `ipcMain.handle`, `fs.writeFile`, `api.exportNotes`, `fetch`.
    /// Very long chains keep only their last few links.
    pub fn render(&self) -> String {
        let full = self.render_full();
        if full.len() <= 96 {
            return full;
        }
        let tail: Vec<&str> = self.segs.iter().rev().take(3).map(String::as_str).collect::<Vec<_>>().into_iter().rev().collect();
        let t = tail.join(".");
        let t: String = t.chars().rev().take(96).collect::<Vec<_>>().into_iter().rev().collect();
        format!("…{t}")
    }

    fn render_full(&self) -> String {
        match self.module.as_deref() {
            Some("electron") => {
                if self.segs.is_empty() {
                    "electron".into()
                } else {
                    self.segs.join(".")
                }
            }
            Some(m) => {
                let mut segs: &[String] = &self.segs;
                while let Some((first, rest)) = segs.split_first() {
                    if first == "default" || (m == "fs" && first == "promises") {
                        segs = rest;
                    } else {
                        break;
                    }
                }
                if segs.is_empty() { m.to_string() } else { format!("{m}.{}", segs.join(".")) }
            }
            None => {
                let mut segs: &[String] = &self.segs;
                if let Some((first, rest)) = segs.split_first()
                    && matches!(first.as_str(), "window" | "globalThis" | "self")
                    && !rest.is_empty()
                {
                    segs = rest;
                }
                segs.join(".")
            }
        }
    }

    fn last(&self) -> Option<&str> {
        self.segs.last().map(String::as_str)
    }
}

/// Normalise a module specifier for alias purposes (`node:fs` → `fs`, `electron/main` → `electron`).
pub(crate) fn normalize_module(spec: &str) -> String {
    let s = spec.strip_prefix("node:").unwrap_or(spec);
    match s {
        "fs/promises" | "original-fs" => "fs".into(),
        "electron/main" | "electron/renderer" | "electron/common" | "electron/utility" => "electron".into(),
        "child_process" | "node:child_process" => "child_process".into(),
        _ => s.to_string(),
    }
}

struct Frame {
    index: usize,
}

pub(crate) struct FactVisitor<'s> {
    src: &'s str,
    lines: &'s LineIndex,
    pub facts: ModuleFacts,
    /// Scope analysis, when available: aliases then follow bindings, not names.
    scoping: Option<&'s Scoping>,
    aliases: HashMap<Key, Ref>,
    const_strings: HashMap<Key, String>,
    /// Object literals bound to a variable: name → (prop → qualified function name).
    object_members: HashMap<Key, Vec<ExposedMember>>,
    frames: Vec<Frame>,
    /// Names for upcoming functions, keyed by the function's span start.
    pending: HashMap<u32, String>,
    pending_window: Option<String>,
    object_prefix: Vec<String>,
    class_names: Vec<String>,
    string_set: std::collections::HashSet<String>,
    /// Object literals a window may be made from (`const opts = {…}; new BrowserWindow(opts)`).
    named_objects: HashMap<Key, NamedObject>,
    /// How many references to each named object are uses as window options or webPreferences.
    option_uses: HashMap<Key, usize>,
    /// Windows read through named objects: index in `facts.windows`, the objects' keys.
    named_windows: Vec<(usize, Vec<Key>)>,
    /// Variables other modules can reach (`export const opts`, or by name `export { opts }`).
    exported: HashSet<Key>,
    /// Router calls already read as part of an outer router (by span start).
    routers_read: HashSet<u32>,
}

/// What an alias, constant or object is recorded under: its symbol when scopes are known,
/// otherwise its name (minified code reuses short names, so symbols are much more precise).
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub(crate) enum Key {
    Sym(SymbolId),
    Name(String),
}

impl<'s> FactVisitor<'s> {
    pub fn new(src: &'s str, lines: &'s LineIndex, scoping: Option<&'s Scoping>) -> Self {
        FactVisitor {
            src,
            lines,
            scoping,
            facts: ModuleFacts::default(),
            aliases: HashMap::new(),
            const_strings: HashMap::new(),
            object_members: HashMap::new(),
            frames: Vec::new(),
            pending: HashMap::new(),
            pending_window: None,
            object_prefix: Vec::new(),
            class_names: Vec::new(),
            string_set: Default::default(),
            named_objects: HashMap::new(),
            option_uses: HashMap::new(),
            named_windows: Vec::new(),
            exported: HashSet::new(),
            routers_read: HashSet::new(),
        }
    }

    /// Windows read through named objects keep what was read only when every reference to those
    /// objects is a use as window options or webPreferences: a write, an export or any other use
    /// could change them, so the window goes back to `dynamic`. Call after the walk.
    pub fn finish(&mut self) {
        self.api_finish();
        let mut spoiled: HashSet<&Key> = HashSet::new();
        // Past the cap an export may have gone unrecorded.
        let all_exported = self.exported.len() >= MAX_LIST;
        for (k, o) in &self.named_objects {
            let consumed = match (self.scoping, k) {
                (Some(sc), Key::Sym(s)) => sc.get_resolved_reference_ids(*s).len() == self.option_uses.get(k).copied().unwrap_or(0),
                _ => false,
            };
            if !consumed || all_exported || self.exported.contains(k) || self.exported.contains(&Key::Name(o.at.name.clone())) {
                // An options object that escapes takes its webPreferences objects with it.
                spoiled.insert(k);
                spoiled.extend(o.options.iter().flat_map(|w| &w.via));
            }
        }
        for (i, via) in &self.named_windows {
            if via.iter().any(|k| spoiled.contains(k))
                && let Some(w) = self.facts.windows.get_mut(*i)
            {
                w.web_preferences = WindowOptions::dynamic().prefs;
                w.preload = None;
                w.options_from = None;
            }
        }
    }

    fn key_bind(&self, b: &BindingIdentifier<'_>) -> Key {
        match (self.scoping, b.symbol_id.get()) {
            (Some(_), Some(sym)) => Key::Sym(sym),
            _ => Key::Name(b.name.to_string()),
        }
    }

    /// The key an identifier reference resolves to (`None`: an unresolved global under scope analysis).
    fn key_ref(&self, r: &IdentifierReference<'_>) -> Option<Key> {
        match self.scoping {
            Some(sc) => r.reference_id.get().and_then(|rid| sc.get_reference(rid).symbol_id()).map(Key::Sym),
            None => Some(Key::Name(r.name.to_string())),
        }
    }

    fn line(&self, offset: u32) -> u32 {
        self.lines.line(offset)
    }

    fn current_fn(&self) -> Option<String> {
        self.frames.last().and_then(|f| self.facts.functions.get(f.index)).map(|f| f.name.clone())
    }

    fn truncated(&mut self, what: &str) {
        push_unique(&mut self.facts.truncated, what.to_string(), 64);
    }

    fn text(&self, span: oxc_span::Span) -> &'s str {
        self.src.get(span.start as usize..span.end as usize).unwrap_or("")
    }

    // ---- reference resolution ----

    pub(crate) fn expr_ref(&self, e: &Expression<'_>, depth: usize) -> Option<Ref> {
        if depth > MAX_PATH_DEPTH {
            return None;
        }
        match e {
            Expression::Identifier(id) => Some(self.key_ref(id).and_then(|k| self.aliases.get(&k).cloned()).unwrap_or_else(|| Ref::local(id.name.as_str()))),
            Expression::ThisExpression(_) => Some(Ref::local("this")),
            Expression::ParenthesizedExpression(p) => self.expr_ref(&p.expression, depth + 1),
            Expression::SequenceExpression(s) => s.expressions.last().and_then(|x| self.expr_ref(x, depth + 1)),
            Expression::StaticMemberExpression(m) => Some(self.expr_ref(&m.object, depth + 1)?.push(m.property.name.as_str())),
            Expression::ComputedMemberExpression(m) => match &m.expression {
                Expression::StringLiteral(s) => Some(self.expr_ref(&m.object, depth + 1)?.push(s.value.as_str())),
                _ => None,
            },
            Expression::ChainExpression(c) => match &c.expression {
                ChainElement::StaticMemberExpression(m) => Some(self.expr_ref(&m.object, depth + 1)?.push(m.property.name.as_str())),
                ChainElement::CallExpression(call) => self.expr_ref(&call.callee, depth + 1),
                _ => None,
            },
            Expression::CallExpression(call) => {
                if let Some(spec) = require_spec(call) {
                    return Some(Ref { module: Some(normalize_module(&spec)), segs: Vec::new() });
                }
                // Interop wrappers: _interopRequireDefault(require("x")), __toESM(require("x")), __importDefault(...)
                if call.arguments.len() == 1
                    && let Some(Argument::CallExpression(inner)) = call.arguments.first()
                    && let Some(spec) = require_spec(inner)
                {
                    return Some(Ref { module: Some(normalize_module(&spec)), segs: Vec::new() });
                }
                // A call inside a member chain: `document.getElementById("x").addEventListener`.
                let mut r = self.expr_ref(&call.callee, depth + 1)?;
                let arg = match call.arguments.first().and_then(|a| a.as_expression()).map(|e| e.get_inner_expression()) {
                    Some(Expression::StringLiteral(s)) if s.value.len() <= 64 => s.value.to_string(),
                    _ => String::new(),
                };
                let last = r.segs.pop().unwrap_or_default();
                r.segs.push(format!("{last}({arg})"));
                Some(r)
            }
            Expression::AwaitExpression(a) => self.expr_ref(&a.argument, depth + 1),
            Expression::ImportExpression(i) => match &i.source {
                Expression::StringLiteral(s) => Some(Ref { module: Some(normalize_module(s.value.as_str())), segs: Vec::new() }),
                _ => None,
            },
            _ => None,
        }
    }

    fn callee_name(&self, e: &Expression<'_>) -> Option<String> {
        self.expr_ref(e, 0).map(|r| r.render())
    }

    /// Render an expression as a string when it is (partly) literal: `(text, fully_literal)`.
    pub(crate) fn render_value(&self, e: &Expression<'_>, depth: usize) -> Option<(String, bool)> {
        if depth > 16 {
            return None;
        }
        match e {
            Expression::StringLiteral(s) => Some((s.value.to_string(), true)),
            Expression::NumericLiteral(n) => Some((self.text(n.span).to_string(), true)),
            Expression::ParenthesizedExpression(p) => self.render_value(&p.expression, depth + 1),
            Expression::TemplateLiteral(t) => {
                let mut out = String::new();
                let mut literal = true;
                for (i, q) in t.quasis.iter().enumerate() {
                    out.push_str(q.value.cooked.as_ref().map_or(q.value.raw.as_str(), |c| c.as_str()));
                    if let Some(x) = t.expressions.get(i) {
                        match self.render_value(x, depth + 1) {
                            Some((v, true)) => out.push_str(&v),
                            _ => {
                                literal = false;
                                out.push_str(&hole(x, self));
                            }
                        }
                    }
                }
                Some((out, literal))
            }
            Expression::BinaryExpression(b) if b.operator == BinaryOperator::Addition => {
                let l = self.render_value(&b.left, depth + 1);
                let r = self.render_value(&b.right, depth + 1);
                if l.is_none() && r.is_none() {
                    return None;
                }
                let (ls, ll) = l.unwrap_or_else(|| (hole(&b.left, self), false));
                let (rs, rl) = r.unwrap_or_else(|| (hole(&b.right, self), false));
                Some((format!("{ls}{rs}"), ll && rl))
            }
            Expression::Identifier(id) => self.key_ref(id).and_then(|k| self.const_strings.get(&k)).map(|v| (v.clone(), true)),
            _ => None,
        }
    }

    fn arg_value(&self, args: &[Argument<'_>], i: usize) -> Option<(String, bool)> {
        args.get(i).and_then(|a| a.as_expression()).and_then(|e| self.render_value(e, 0))
    }

    fn arg_str(&self, args: &[Argument<'_>], i: usize) -> Option<String> {
        args.get(i).and_then(|a| a.as_expression()).and_then(|e| match e.get_inner_expression() {
            Expression::StringLiteral(s) => Some(s.value.to_string()),
            Expression::TemplateLiteral(t) if t.expressions.is_empty() => t.quasis.first().map(|q| q.value.raw.to_string()),
            other => self.render_value(other, 0).filter(|(_, lit)| *lit).map(|(v, _)| v),
        })
    }

    // ---- recording ----

    fn add_import(&mut self, kind: &str, specifier: String, literal: bool, names: Vec<String>, offset: u32) {
        if self.facts.imports.len() >= MAX_LIST {
            self.truncated("imports");
            return;
        }
        if specifier.ends_with(".node") {
            push_unique(&mut self.facts.native_modules, specifier.clone(), MAX_LIST);
        }
        let line = self.line(offset);
        self.facts.imports.push(ImportRef { kind: kind.into(), specifier, literal, names, line, offset });
    }

    fn add_function(&mut self, name: String, kind: &str, span: oxc_span::Span, params: &FormalParameters<'_>) -> bool {
        if self.facts.functions.len() >= MAX_FUNCTIONS {
            self.truncated("functions");
            return false;
        }
        let params = params.items.iter().take(16).map(|p| p.pattern.get_identifier_name().map_or_else(|| "{…}".to_string(), |n| n.to_string())).collect();
        let parent = self.current_fn();
        let f = FunctionFact {
            name,
            kind: kind.into(),
            line: self.line(span.start),
            end_line: self.line(span.end),
            start: span.start,
            end: span.end,
            params,
            calls: Vec::new(),
            strings: Vec::new(),
            parent,
            exported: false,
        };
        self.facts.functions.push(f);
        self.frames.push(Frame { index: self.facts.functions.len() - 1 });
        true
    }

    fn fn_name(&mut self, explicit: Option<&str>, span: oxc_span::Span) -> String {
        let pending = self.pending.remove(&span.start);
        match (explicit, pending) {
            (_, Some(p)) => p,
            (Some(n), None) => n.to_string(),
            (None, None) => format!("<anonymous@{}>", self.line(span.start)),
        }
    }

    fn note_call(&mut self, callee: &str) {
        if let Some(f) = self.frames.last().and_then(|f| self.facts.functions.get_mut(f.index)) {
            push_unique(&mut f.calls, callee.to_string(), MAX_FN_CALLS);
        }
    }

    /// Name the function (or class) expression `e` when the visitor reaches it.
    fn name_next(&mut self, e: &Expression<'_>, name: String) {
        let inner = e.get_inner_expression();
        if is_function_like(inner) || matches!(inner, Expression::ClassExpression(_)) {
            self.pending.insert(inner.span().start, name);
        }
    }

    // ---- the big dispatcher ----

    /// Record what a call means. Returns true when it already walked the arguments itself.
    fn on_call(&mut self, call: &CallExpression<'_>) -> bool {
        let args = &call.arguments;
        let off = call.span.start;
        if let Some(spec) = require_spec(call) {
            self.add_import("require", spec, true, Vec::new(), off);
            return false;
        }
        let Some(r) = self.expr_ref(&call.callee, 0) else {
            // require("bindings")("addon")
            if let Expression::CallExpression(inner) = call.callee.get_inner_expression()
                && require_spec(inner).as_deref() == Some("bindings")
                && let Some(n) = self.arg_str(args, 0)
            {
                push_unique(&mut self.facts.native_modules, format!("bindings:{n}"), MAX_LIST);
            }
            return false;
        };
        let name = r.render();
        self.note_call(&name);
        let last = r.last().unwrap_or("");
        let f = self.current_fn();

        // `require` with a dynamic argument.
        if name == "require" {
            if let Some((v, lit)) = self.arg_value(args, 0) {
                self.add_import("require", v, lit, Vec::new(), off);
            } else {
                self.add_import("require", "{dynamic}".into(), false, Vec::new(), off);
            }
            return false;
        }
        if name == "bindings" || r.module.as_deref() == Some("bindings") {
            if let Some(n) = self.arg_str(args, 0) {
                push_unique(&mut self.facts.native_modules, format!("bindings:{n}"), MAX_LIST);
            }
            return false;
        }
        if name == "process.dlopen"
            && let Some((v, _)) = self.arg_value(args, 1)
        {
            push_unique(&mut self.facts.native_modules, v, MAX_LIST);
        }
        if name == "importScripts" {
            for i in 0..args.len().min(16) {
                if let Some((v, lit)) = self.arg_value(args, i) {
                    self.add_import("import-scripts", v, lit, Vec::new(), off);
                }
            }
            return false;
        }
        if name.ends_with("serviceWorker.register") {
            if let Some((v, lit)) = self.arg_value(args, 0) {
                self.add_import("service-worker", v, lit, Vec::new(), off);
            }
            return false;
        }
        if (name == "utilityProcess.fork" || name == "child_process.fork")
            && let Some((v, lit)) = self.arg_value(args, 0)
        {
            self.add_import("utility-process", v, lit, Vec::new(), off);
        }
        if name == "Object.defineProperty"
            && let Some(Expression::Identifier(id)) = args.first().and_then(|a| a.as_expression()).map(|e| e.get_inner_expression())
            && id.name == "exports"
            && let Some(n) = self.arg_str(args, 1)
            && n != "__esModule"
        {
            push_unique(&mut self.facts.exports.cjs, n, MAX_LIST);
        }

        // ---- Electron IPC ----
        let ipc_side = if name.starts_with("ipcMain.") || name.contains(".ipcMain.") {
            Some("main")
        } else if name.starts_with("ipcRenderer.") || name.contains(".ipcRenderer.") {
            Some("renderer")
        } else if (name.contains("webContents.") || name.contains("sender.")) && matches!(last, "send" | "postMessage") {
            Some("web-contents")
        } else if matches!(last, "invoke" | "send" | "sendSync") && r.segs.len() >= 2 && self.arg_str(args, 0).is_some() {
            // A call through a preload bridge (`window.api.invoke("channel")`); paired later.
            Some("bridge")
        } else {
            None
        };
        if let Some(side) = ipc_side {
            let channel = self.arg_str(args, 0);
            let handler_label = match side {
                "main" => format!("ipcMain.{last}({})", channel.as_deref().unwrap_or("?")),
                "bridge" => format!("{name}({})", channel.as_deref().unwrap_or("?")),
                _ => format!("ipcRenderer.{last}({})", channel.as_deref().unwrap_or("?")),
            };
            let method = if side == "bridge" { name.clone() } else { last.to_string() };
            let handler = args.get(1).and_then(|a| a.as_expression()).and_then(|e| match e.get_inner_expression() {
                Expression::Identifier(id) => Some(id.name.to_string()),
                x if is_function_like(x) => Some(handler_label.clone()),
                _ => None,
            });
            if matches!(last, "handle" | "handleOnce" | "on" | "once" | "addListener")
                && let Some(e) = args.get(1).and_then(|a| a.as_expression())
            {
                self.name_next(e, handler_label);
            }
            if self.facts.ipc.len() < MAX_LIST {
                let line = self.line(off);
                self.facts.ipc.push(IpcUse { side: side.into(), method, channel, line, offset: off, function: f.clone(), handler });
            } else {
                self.truncated("ipc");
            }
            return false;
        }
        if matches!(last, "exposeInMainWorld" | "exposeInIsolatedWorld") && name.contains("contextBridge") {
            return self.on_expose(call, last);
        }
        if matches!(last, "loadFile" | "loadURL") {
            let receiver = r.segs.len().checked_sub(1).and_then(|n| r.segs.get(..n)).map(|s| s.join(".")).filter(|s| !s.is_empty());
            let target = args.first().and_then(|a| a.as_expression()).and_then(|e| self.path_like(e));
            let line = self.line(off);
            if self.facts.loads.len() < MAX_LIST {
                self.facts.loads.push(LoadFact { method: last.into(), receiver, target, line, offset: off });
            }
            return false;
        }
        if matches!(name.as_str(), "protocol.handle" | "protocol.registerFileProtocol" | "protocol.registerHttpProtocol" | "protocol.registerStreamProtocol")
            && let Some(s) = self.arg_str(args, 0)
        {
            self.add_route(format!("{s}://"), "protocol", None, off);
        }

        // ---- network ----
        let http_methods = ["get", "post", "put", "delete", "patch", "head", "options", "request"];
        let endpoint = if name == "fetch" {
            let method = args.get(1).and_then(|a| a.as_expression()).and_then(|e| self.object_string_prop(e, "method"));
            Some(("fetch", method))
        } else if name == "axios" || (r.module.as_deref() == Some("axios") && r.segs.is_empty()) {
            Some(("axios", None))
        } else if (name.starts_with("axios.")
            || r.module.as_deref() == Some("axios")
            || name.starts_with("this.http.")
            || name.starts_with("http.") && r.module.is_none())
            && http_methods.contains(&last)
        {
            Some(("axios", Some(last.to_ascii_uppercase())))
        } else if (name.starts_with("$.") || name.starts_with("jQuery.")) && matches!(last, "ajax" | "get" | "post" | "getJSON") {
            Some(("jquery", (last != "ajax").then(|| last.trim_end_matches("JSON").to_ascii_uppercase())))
        } else if name.ends_with("sendBeacon") {
            Some(("beacon", Some("POST".into())))
        } else if (r.module.as_deref() == Some("https") || r.module.as_deref() == Some("http") || name == "net.request") && matches!(last, "get" | "request") {
            Some(("http", None))
        } else {
            None
        };
        if let Some((api, method)) = endpoint {
            let first = args.first().and_then(|a| a.as_expression());
            let (url, literal) = match first.map(|e| e.get_inner_expression()) {
                Some(Expression::ObjectExpression(_)) => {
                    let o = first.and_then(|e| self.object_value_prop(e, "url"));
                    match o {
                        Some(v) => v,
                        None => (String::from("{config}"), false),
                    }
                }
                Some(e) => self.render_value(e, 0).unwrap_or_else(|| (hole(e, self), false)),
                None => (String::new(), false),
            };
            let method = method.or_else(|| first.and_then(|e| self.object_string_prop(e, "method")).map(|m| m.to_ascii_uppercase()));
            self.add_endpoint(api, method, url, literal, off);
            return false;
        }
        if last == "open"
            && args.len() >= 2
            && let Some(m) = self.arg_str(args, 0)
            && matches!(m.to_ascii_uppercase().as_str(), "GET" | "POST" | "PUT" | "DELETE" | "PATCH" | "HEAD" | "OPTIONS")
            && let Some((u, lit)) = self.arg_value(args, 1)
        {
            self.add_endpoint("xhr", Some(m.to_ascii_uppercase()), u, lit, off);
            return false;
        }

        // ---- server-style routes ----
        if matches!(last, "get" | "post" | "put" | "delete" | "patch" | "all" | "use" | "route")
            && let Some(recv) = r.segs.len().checked_sub(2).and_then(|i| r.segs.get(i))
            && matches!(recv.as_str(), "app" | "router" | "server" | "fastify" | "api" | "routes")
            && let Some(p) = self.arg_str(args, 0)
            && (p.starts_with('/') || p == "*")
        {
            let m = (last != "use" && last != "route" && last != "all").then(|| last.to_ascii_uppercase());
            self.add_route(p, "server", m, off);
        }

        // ---- storage ----
        let storage = name.starts_with("localStorage.")
            || name.starts_with("sessionStorage.")
            || name == "indexedDB.open"
            || name == "caches.open"
            || name.starts_with("safeStorage.")
            || name.starts_with("keytar.")
            || matches!(r.module.as_deref(), Some("better-sqlite3" | "sqlite3" | "electron-store" | "keytar" | "level" | "lowdb"));
        if storage {
            let arg = self.arg_value(args, 0).map(|(v, _)| v);
            self.add_api(true, name.clone(), arg, off);
        }

        // ---- platform effects ----
        if is_effect(&name, r.module.as_deref()) {
            let arg = self.arg_value(args, 0).map(|(v, _)| v);
            self.add_api(false, name.clone(), arg, off);
        }

        // ---- events ----
        if matches!(last, "addEventListener" | "on" | "once") && r.segs.len() >= 2 {
            if let Some(ev) = self.arg_str(args, 0) {
                let target = r.segs.get(..r.segs.len() - 1).map(|s| s.join(".")).unwrap_or_default();
                let target = if let Some(m) = &r.module { if target.is_empty() { m.clone() } else { target } } else { target };
                let label = format!("{target}.{last}({ev})");
                let handler = args.get(1).and_then(|a| a.as_expression()).and_then(|e| match e.get_inner_expression() {
                    Expression::Identifier(id) => Some(id.name.to_string()),
                    Expression::StaticMemberExpression(_) => self.callee_name(e),
                    x if is_function_like(x) => Some(label.clone()),
                    _ => None,
                });
                if let Some(e) = args.get(1).and_then(|a| a.as_expression()) {
                    self.name_next(e, label);
                }
                if self.facts.events.len() < MAX_LIST {
                    let line = self.line(off);
                    self.facts.events.push(EventUse { target, event: ev, handler, line, offset: off, function: f });
                }
            }
        } else if args.len() <= 3 {
            // Name inline callbacks after what they are passed to: `setTimeout`, `then`, `map`…
            if let Some(a) = args.iter().filter_map(|a| a.as_expression()).find(|e| is_function_like(e.get_inner_expression())) {
                let n = format!("{name} callback@{}", self.line(off));
                self.name_next(a, n);
            }
        }
        false
    }

    fn object_string_prop(&self, e: &Expression<'_>, key: &str) -> Option<String> {
        self.object_value_prop(e, key).filter(|(_, lit)| *lit).map(|(v, _)| v)
    }

    fn object_value_prop(&self, e: &Expression<'_>, key: &str) -> Option<(String, bool)> {
        let Expression::ObjectExpression(o) = e.get_inner_expression() else { return None };
        for p in &o.properties {
            if let ObjectPropertyKind::ObjectProperty(p) = p
                && p.key.static_name().as_deref() == Some(key)
            {
                return self.render_value(&p.value, 0);
            }
        }
        None
    }

    fn add_endpoint(&mut self, api: &str, method: Option<String>, url: String, literal: bool, off: u32) {
        if self.facts.endpoints.len() >= MAX_LIST {
            self.truncated("endpoints");
            return;
        }
        let line = self.line(off);
        let function = self.current_fn();
        self.facts.endpoints.push(Endpoint { api: api.into(), method, url, literal, line, offset: off, function });
    }

    fn add_route(&mut self, path: String, source: &str, method: Option<String>, off: u32) {
        if self.facts.routes.len() >= MAX_LIST {
            self.truncated("routes");
            return;
        }
        let line = self.line(off);
        self.facts.routes.push(Route { path, source: source.into(), method, line, offset: off });
    }

    fn add_api(&mut self, storage: bool, api: String, arg: Option<String>, off: u32) {
        let list = if storage { &self.facts.storage } else { &self.facts.effects };
        if list.len() >= MAX_LIST {
            self.truncated(if storage { "storage" } else { "effects" });
            return;
        }
        let line = self.line(off);
        let function = self.current_fn();
        let arg = arg.map(|a| clip(&a, MAX_STRING_LEN));
        let u = ApiUse { api, arg, line, offset: off, function };
        if storage { self.facts.storage.push(u) } else { self.facts.effects.push(u) }
    }

    fn on_expose(&mut self, call: &CallExpression<'_>, method: &str) -> bool {
        let key_index = usize::from(method == "exposeInIsolatedWorld");
        let key = self.arg_str(&call.arguments, key_index);
        let off = call.span.start;
        let obj = call.arguments.get(key_index + 1).and_then(|a| a.as_expression());
        let mut members = Vec::new();
        let mut walked = false;
        let prefix = key.clone().unwrap_or_else(|| "?".into());
        match obj.map(|e| e.get_inner_expression()) {
            Some(Expression::ObjectExpression(o)) => {
                for p in &o.properties {
                    let ObjectPropertyKind::ObjectProperty(p) = p else { continue };
                    let Some(k) = p.key.static_name() else { continue };
                    let qualified = format!("{prefix}.{k}");
                    let function = match p.value.get_inner_expression() {
                        x if is_function_like(x) => Some(qualified.clone()),
                        Expression::Identifier(id) => Some(id.name.to_string()),
                        _ => None,
                    };
                    members.push(ExposedMember { name: k.to_string(), function });
                }
                // Walk arguments with qualified names for the inline functions.
                self.object_prefix.push(prefix);
                for a in &call.arguments {
                    if let Some(e) = a.as_expression() {
                        self.visit_expression(e);
                    }
                }
                self.object_prefix.pop();
                walked = true;
            }
            Some(Expression::Identifier(id)) => {
                members = self.key_ref(id).and_then(|k| self.object_members.get(&k).cloned()).unwrap_or_default();
            }
            _ => {}
        }
        let line = self.line(off);
        if self.facts.exposed.len() < MAX_LIST {
            self.facts.exposed.push(Exposed { method: method.into(), key, members, line, offset: off });
        }
        walked
    }

    fn on_new(&mut self, n: &NewExpression<'_>) {
        let Some(r) = self.expr_ref(&n.callee, 0) else { return };
        let name = r.render();
        self.note_call(&format!("new {name}"));
        let off = n.span.start;
        let last = r.last().unwrap_or("");
        match last {
            "BrowserWindow" | "BrowserView" | "WebContentsView" => {
                let opts = match n.arguments.first().and_then(|a| a.as_expression()).map(|e| e.get_inner_expression()) {
                    None => WindowOptions::default(),
                    Some(Expression::ObjectExpression(o)) => self.window_options(o),
                    Some(e) => self.use_named(e, |o| o.options.as_ref()).unwrap_or_else(WindowOptions::dynamic),
                };
                let binding = self.pending_window.take();
                let line = self.line(off);
                let function = self.current_fn();
                let options_from = opts.via.first().and_then(|k| self.named_objects.get(k)).map(|o| o.at.clone());
                if self.facts.windows.len() < MAX_LIST {
                    if !opts.via.is_empty() {
                        self.named_windows.push((self.facts.windows.len(), opts.via));
                    }
                    self.facts.windows.push(WindowFact {
                        class: last.into(),
                        binding,
                        preload: opts.preload,
                        web_preferences: opts.prefs,
                        options_from,
                        line,
                        offset: off,
                        function,
                    });
                }
            }
            "Worker" | "SharedWorker" => {
                if let Some((v, lit)) = self.arg_value(&n.arguments, 0) {
                    self.add_import("worker", v, lit, Vec::new(), off);
                } else if let Some(Expression::NewExpression(u)) = n.arguments.first().and_then(|a| a.as_expression()).map(|e| e.get_inner_expression())
                    && let Some((v, lit)) = self.arg_value(&u.arguments, 0)
                {
                    // new Worker(new URL("./w.js", import.meta.url))
                    self.add_import("worker", v, lit, Vec::new(), off);
                }
            }
            "WebSocket" | "EventSource" => {
                if let Some(first) = n.arguments.first().and_then(|a| a.as_expression()) {
                    let (u, lit) = self.render_value(first, 0).unwrap_or_else(|| (hole(first, self), false));
                    self.add_endpoint(if last == "WebSocket" { "websocket" } else { "eventsource" }, None, u, lit, off);
                }
            }
            _ => {
                if matches!(r.module.as_deref(), Some("better-sqlite3" | "sqlite3" | "electron-store" | "level" | "lowdb"))
                    || name.ends_with("sqlite3.Database")
                {
                    let arg = self.arg_value(&n.arguments, 0).map(|(v, _)| v);
                    self.add_api(true, format!("new {name}"), arg, off);
                } else if matches!(last, "Notification" | "Tray") && r.module.as_deref() == Some("electron") {
                    self.add_api(false, format!("new {name}"), None, off);
                }
            }
        }
    }

    /// BrowserWindow options written as an object literal: their webPreferences, read inline or
    /// through a named object, `dynamic` where they can't be read. As in JavaScript, a later
    /// property replaces an earlier one, and a spread (or computed key) may bring its own.
    fn window_options(&mut self, o: &ObjectExpression<'_>) -> WindowOptions {
        let mut out = WindowOptions::default();
        for p in &o.properties {
            let ObjectPropertyKind::ObjectProperty(p) = p else {
                out = WindowOptions { via: out.via, ..WindowOptions::dynamic() };
                continue;
            };
            match p.key.static_name().as_deref() {
                Some("webPreferences") => {}
                Some(_) => continue,
                None => {
                    out = WindowOptions { via: out.via, ..WindowOptions::dynamic() };
                    continue;
                }
            }
            let mut read = match p.value.get_inner_expression() {
                Expression::ObjectExpression(wp) => self.web_preferences(wp),
                e => self.use_named(e, |o| o.prefs.as_ref()).unwrap_or_else(WindowOptions::dynamic),
            };
            read.via.splice(0..0, out.via);
            out = read;
        }
        out
    }

    /// webPreferences written as an object literal: literal values, `dynamic` for computed ones,
    /// and the preload path. A spread (or computed key) may set or replace any of them, so only
    /// what is written after the last one is known.
    fn web_preferences(&self, wp: &ObjectExpression<'_>) -> WindowOptions {
        let mut out = WindowOptions::default();
        for p in &wp.properties {
            let named = match p {
                ObjectPropertyKind::ObjectProperty(q) => q.key.static_name().map(|k| (k, q)),
                ObjectPropertyKind::SpreadProperty(_) => None,
            };
            let Some((k, q)) = named else {
                out = WindowOptions::dynamic();
                continue;
            };
            if k == "preload" {
                out.preload = self.path_like(&q.value);
                continue;
            }
            let v = match q.value.get_inner_expression() {
                Expression::BooleanLiteral(b) => PrefValue::Bool(b.value),
                Expression::StringLiteral(s) => PrefValue::Text(s.value.to_string()),
                Expression::UnaryExpression(u) if u.operator == UnaryOperator::LogicalNot => match &u.argument {
                    Expression::NumericLiteral(x) => PrefValue::Bool(x.value == 0.0),
                    _ => PrefValue::Text("dynamic".into()),
                },
                _ => PrefValue::Text("dynamic".into()),
            };
            out.prefs.insert(k.to_string(), v);
        }
        out
    }

    /// A named object used as window options or webPreferences (`pick` chooses the reading): counts
    /// the use and returns the reading, with the object first in `via`. `None` when `e` isn't one.
    fn use_named(&mut self, e: &Expression<'_>, pick: impl Fn(&NamedObject) -> Option<&WindowOptions>) -> Option<WindowOptions> {
        let Expression::Identifier(id) = e else { return None };
        let k = self.key_ref(id)?;
        let mut read = self.named_objects.get(&k).and_then(pick)?.clone();
        *self.option_uses.entry(k.clone()).or_default() += 1;
        read.via.insert(0, k);
        Some(read)
    }

    /// Remember an object literal bound to a variable when it looks like window options or
    /// webPreferences, so a window made from it can be read ([`Self::finish`] checks its uses).
    fn remember_object(&mut self, k: Key, name: &str, o: &ObjectExpression<'_>, offset: u32) {
        if !matches!(k, Key::Sym(_)) || self.named_objects.len() >= MAX_NAMED_OBJECTS {
            return;
        }
        let has = |keys: &[&str]| {
            o.properties.iter().any(|p| matches!(p, ObjectPropertyKind::ObjectProperty(q) if q.key.static_name().is_some_and(|n| keys.contains(&n.as_ref()))))
        };
        let (as_options, as_prefs) = (has(WINDOW_OPTION_KEYS), has(WEB_PREFERENCE_KEYS));
        if !as_options && !as_prefs {
            return;
        }
        let options = as_options.then(|| self.window_options(o));
        let prefs = as_prefs.then(|| self.web_preferences(o));
        let at = NamedObjectRef { name: name.to_string(), line: self.line(offset) };
        self.named_objects.insert(k, NamedObject { at, options, prefs });
    }

    /// `path.join(__dirname, "preload.js")` → `preload.js`; plain strings and templates pass through.
    fn path_like(&self, e: &Expression<'_>) -> Option<String> {
        match e.get_inner_expression() {
            Expression::CallExpression(c) => {
                let parts: Vec<String> = c
                    .arguments
                    .iter()
                    .filter_map(|a| a.as_expression())
                    .filter_map(|x| match x.get_inner_expression() {
                        Expression::StringLiteral(s) => Some(s.value.to_string()),
                        other => self.render_value(other, 0).filter(|(_, l)| *l).map(|(v, _)| v),
                    })
                    .collect();
                if parts.is_empty() { None } else { Some(parts.join("/").replace("//", "/").trim_start_matches("./").to_string()) }
            }
            other => {
                let (v, _) = self.render_value(other, 0)?;
                let v = v.replace("{__dirname}", "").replace("{__filename}", "");
                Some(v.trim_start_matches('/').trim_start_matches("./").to_string())
            }
        }
    }

    fn bind_pattern_aliases(&mut self, pattern: &BindingPattern<'_>, base: &Ref) {
        match pattern {
            BindingPattern::BindingIdentifier(id) => {
                let k = self.key_bind(id);
                self.aliases.insert(k, base.clone());
            }
            BindingPattern::ObjectPattern(o) => {
                for p in o.properties.iter().take(256) {
                    let Some(k) = p.key.static_name() else { continue };
                    if let BindingPattern::BindingIdentifier(local) = &p.value {
                        let key = self.key_bind(local);
                        self.aliases.insert(key, base.clone().push(&k));
                    } else if let BindingPattern::AssignmentPattern(ap) = &p.value
                        && let BindingPattern::BindingIdentifier(local) = &ap.left
                    {
                        let key = self.key_bind(local);
                        self.aliases.insert(key, base.clone().push(&k));
                    }
                }
            }
            _ => {}
        }
    }

    fn record_string(&mut self, s: &str, offset: u32) {
        if s.is_empty() || s.len() > MAX_STRING_LEN {
            return;
        }
        if let Some(f) = self.frames.last().and_then(|f| self.facts.functions.get_mut(f.index)) {
            push_unique(&mut f.strings, s.to_string(), MAX_FN_STRINGS);
        }
        if self.string_set.len() < MAX_STRINGS {
            if self.string_set.insert(s.to_string()) {
                self.facts.strings.push(s.to_string());
            }
        } else {
            self.truncated("strings");
        }
        let lower = s.get(..8).unwrap_or(s).to_ascii_lowercase();
        if lower.starts_with("http://") || lower.starts_with("https://") || lower.starts_with("wss://") || lower.starts_with("ws://") {
            // Literal URLs anywhere count as weak endpoint evidence.
            if !self.facts.endpoints.iter().any(|e| e.url == s) && self.facts.endpoints.len() < MAX_LIST {
                let function = self.current_fn();
                let line = self.line(offset);
                self.facts.endpoints.push(Endpoint { api: "literal".into(), method: None, url: s.to_string(), literal: true, line, offset, function });
            }
        }
    }

    fn marker(&mut self, name: &str) {
        let key = if name.starts_with("webpackChunk") || name == "webpackJsonp" {
            "webpackChunk"
        } else {
            match name {
                "__webpack_require__"
                | "__webpack_modules__"
                | "__webpack_exports__"
                | "__webpack_module_cache__"
                | "__vitePreload"
                | "__vite__mapDeps"
                | "__commonJS"
                | "__esm"
                | "__toESM"
                | "__toCommonJS"
                | "__export"
                | "__reExport"
                | "parcelRequire"
                | "__turbopack_require__"
                | "__turbopack_context__"
                | "_interopRequireDefault"
                | "__importDefault"
                | "__importStar"
                | "__createBinding"
                | "__exportStar"
                | "_interopRequireWildcard"
                | "__vite_ssr_import__"
                | "__swcpack_require__" => name,
                _ => return,
            }
        };
        if let Some(n) = self.facts.bundler_markers.get_mut(key) {
            *n = n.saturating_add(1);
        } else {
            self.facts.bundler_markers.insert(key.to_string(), 1);
        }
    }
}

fn clip(s: &str, max: usize) -> String {
    if s.len() <= max {
        return s.to_string();
    }
    let mut end = max;
    while !s.is_char_boundary(end) {
        end -= 1;
    }
    format!("{}…", s.get(..end).unwrap_or(""))
}

/// `{name}` placeholder for a non-literal part.
fn hole(e: &Expression<'_>, v: &FactVisitor<'_>) -> String {
    match e.get_inner_expression() {
        Expression::Identifier(id) => format!("{{{}}}", id.name),
        x => match v.callee_name(x) {
            Some(n) if n.len() <= 48 => format!("{{{n}}}"),
            _ => "{…}".into(),
        },
    }
}

pub(crate) fn is_function_like(e: &Expression<'_>) -> bool {
    matches!(e, Expression::FunctionExpression(_) | Expression::ArrowFunctionExpression(_))
}

/// `require("x")` → `x` (string or no-substitution template only).
pub(crate) fn require_spec(call: &CallExpression<'_>) -> Option<String> {
    let Expression::Identifier(id) = &call.callee else { return None };
    if id.name != "require" || call.arguments.len() != 1 {
        return None;
    }
    match call.arguments.first()?.as_expression()?.get_inner_expression() {
        Expression::StringLiteral(s) => Some(s.value.to_string()),
        Expression::TemplateLiteral(t) if t.expressions.is_empty() => t.quasis.first().map(|q| q.value.raw.to_string()),
        _ => None,
    }
}

fn is_effect(name: &str, module: Option<&str>) -> bool {
    const PREFIXES: &[&str] = &[
        "fs.",
        "child_process.",
        "shell.",
        "dialog.",
        "clipboard.",
        "net.",
        "crypto.",
        "session.",
        "autoUpdater.",
        "globalShortcut.",
        "powerSaveBlocker.",
        "systemPreferences.",
        "nativeTheme.",
        "Menu.",
        "app.getPath",
        "app.setPath",
        "app.quit",
        "app.relaunch",
        "app.setAsDefaultProtocolClient",
        "app.setLoginItemSettings",
        "app.requestSingleInstanceLock",
        "process.exit",
        "webContents.executeJavaScript",
        "eval",
        "navigator.clipboard.",
        "Notification.",
        "os.",
        "zlib.",
        "worker_threads.",
    ];
    if PREFIXES.iter().any(|p| name.starts_with(p)) || name == "eval" || name == "Function" {
        return true;
    }
    matches!(module, Some("fs" | "child_process" | "fs-extra" | "graceful-fs" | "execa" | "cross-spawn" | "open" | "shelljs" | "node-pty"))
}

impl<'a> Visit<'a> for FactVisitor<'_> {
    fn visit_program(&mut self, it: &Program<'a>) {
        self.facts.source_kind = if it.source_type.is_module() {
            "module".into()
        } else if it.source_type.is_commonjs() {
            "commonjs".into()
        } else {
            "script".into()
        };
        walk::walk_program(self, it);
    }

    fn visit_import_declaration(&mut self, it: &ImportDeclaration<'a>) {
        let spec = it.source.value.to_string();
        let module = normalize_module(&spec);
        let mut names = Vec::new();
        for s in it.specifiers.iter().flatten() {
            match s {
                ImportDeclarationSpecifier::ImportSpecifier(x) => {
                    let imported = x.imported.name().to_string();
                    let k = self.key_bind(&x.local);
                    self.aliases.insert(k, Ref { module: Some(module.clone()), segs: vec![imported.clone()] });
                    names.push(imported);
                }
                ImportDeclarationSpecifier::ImportDefaultSpecifier(x) => {
                    let k = self.key_bind(&x.local);
                    self.aliases.insert(k, Ref { module: Some(module.clone()), segs: Vec::new() });
                    names.push("default".into());
                }
                ImportDeclarationSpecifier::ImportNamespaceSpecifier(x) => {
                    let k = self.key_bind(&x.local);
                    self.aliases.insert(k, Ref { module: Some(module.clone()), segs: Vec::new() });
                    names.push("*".into());
                }
            }
        }
        self.add_import("import", spec, true, names, it.span.start);
    }

    fn visit_export_declaration(&mut self, it: &ExportDeclaration<'a>) {
        let before = self.facts.functions.len();
        match &it.declaration {
            Declaration::VariableDeclaration(v) => {
                for d in &v.declarations {
                    if let Some(n) = d.id.get_identifier_name() {
                        push_unique(&mut self.facts.exports.esm, n.to_string(), MAX_LIST);
                    }
                    if let BindingPattern::BindingIdentifier(b) = &d.id
                        && self.exported.len() < MAX_LIST
                    {
                        self.exported.insert(self.key_bind(b));
                    }
                }
            }
            Declaration::FunctionDeclaration(f) => {
                if let Some(id) = &f.id {
                    push_unique(&mut self.facts.exports.esm, id.name.to_string(), MAX_LIST);
                }
            }
            Declaration::ClassDeclaration(c) => {
                if let Some(id) = &c.id {
                    push_unique(&mut self.facts.exports.esm, id.name.to_string(), MAX_LIST);
                }
            }
            _ => {}
        }
        walk::walk_export_declaration(self, it);
        if let Some(f) = self.facts.functions.get_mut(before) {
            f.exported = true;
        }
    }

    fn visit_export_named_declaration(&mut self, it: &ExportNamedDeclaration<'a>) {
        for s in &it.specifiers {
            push_unique(&mut self.facts.exports.esm, s.exported.name().to_string(), MAX_LIST);
            let local = s.local.name().to_string();
            for f in self.facts.functions.iter_mut().filter(|f| f.name == local) {
                f.exported = true;
            }
            if self.exported.len() < MAX_LIST {
                self.exported.insert(Key::Name(local));
            }
        }
        walk::walk_export_named_declaration(self, it);
    }

    fn visit_export_from_declaration(&mut self, it: &ExportFromDeclaration<'a>) {
        let mut names = Vec::new();
        for s in &it.specifiers {
            push_unique(&mut self.facts.exports.esm, s.exported.name().to_string(), MAX_LIST);
            names.push(s.local.name().to_string());
        }
        self.add_import("re-export", it.source.value.to_string(), true, names, it.span.start);
    }

    fn visit_export_all_declaration(&mut self, it: &ExportAllDeclaration<'a>) {
        let name = it.exported.as_ref().map_or_else(|| "*".to_string(), |e| e.name().to_string());
        push_unique(&mut self.facts.exports.esm, name, MAX_LIST);
        self.add_import("re-export", it.source.value.to_string(), true, vec!["*".into()], it.span.start);
    }

    fn visit_export_default_declaration(&mut self, it: &ExportDefaultDeclaration<'a>) {
        push_unique(&mut self.facts.exports.esm, "default".into(), MAX_LIST);
        let before = self.facts.functions.len();
        if let ExportDefaultDeclarationKind::FunctionDeclaration(f) = &it.declaration
            && f.id.is_none()
        {
            self.pending.insert(f.span.start, "default".into());
        }
        walk::walk_export_default_declaration(self, it);
        if let Some(f) = self.facts.functions.get_mut(before) {
            f.exported = true;
        }
    }

    fn visit_import_expression(&mut self, it: &ImportExpression<'a>) {
        let (spec, lit) = self.render_value(&it.source, 0).unwrap_or_else(|| (hole(&it.source, self), false));
        self.add_import("dynamic-import", spec, lit, Vec::new(), it.span.start);
        walk::walk_import_expression(self, it);
    }

    fn visit_variable_declarator(&mut self, it: &VariableDeclarator<'a>) {
        let name = it.id.get_identifier_name().map(|n| n.to_string());
        if let Some(init) = &it.init {
            let inner = init.get_inner_expression();
            // Aliases: require/import bindings and member re-bindings.
            match inner {
                Expression::CallExpression(_) | Expression::StaticMemberExpression(_) | Expression::AwaitExpression(_) => {
                    if let Some(r) = self.expr_ref(inner, 0)
                        && r.module.is_some()
                    {
                        self.bind_pattern_aliases(&it.id, &r);
                    }
                }
                Expression::Identifier(id) => {
                    if let Some(r) = self.key_ref(id).and_then(|k| self.aliases.get(&k).cloned()) {
                        self.bind_pattern_aliases(&it.id, &r);
                    } else if !matches!(it.id, BindingPattern::BindingIdentifier(_)) {
                        // const { ipcRenderer } = electron (unresolved base)
                        self.bind_pattern_aliases(&it.id, &Ref::local(id.name.as_str()));
                    }
                }
                _ => {}
            }
            if let Some(n) = &name {
                if let Some((v, true)) = self.render_value(inner, 0)
                    && let BindingPattern::BindingIdentifier(b) = &it.id
                {
                    let k = self.key_bind(b);
                    self.const_strings.insert(k, v);
                }
                if is_function_like(inner) {
                    self.name_next(inner, n.clone());
                } else if let Expression::NewExpression(_) = inner {
                    self.pending_window = Some(n.clone());
                } else if let Expression::ObjectExpression(o) = inner {
                    let members = o
                        .properties
                        .iter()
                        .filter_map(|p| match p {
                            ObjectPropertyKind::ObjectProperty(p) => {
                                let k = p.key.static_name()?.to_string();
                                let function = match p.value.get_inner_expression() {
                                    x if is_function_like(x) => Some(format!("{n}.{k}")),
                                    Expression::Identifier(id) => Some(id.name.to_string()),
                                    _ => None,
                                };
                                Some(ExposedMember { name: k, function })
                            }
                            _ => None,
                        })
                        .take(512)
                        .collect();
                    if let BindingPattern::BindingIdentifier(b) = &it.id {
                        let k = self.key_bind(b);
                        self.object_members.insert(k.clone(), members);
                        self.remember_object(k, n, o, it.span.start);
                    }
                    self.object_prefix.push(n.clone());
                    walk::walk_variable_declarator(self, it);
                    self.object_prefix.pop();
                    return;
                }
            }
        }
        walk::walk_variable_declarator(self, it);
        self.pending_window = None;
    }

    fn visit_assignment_expression(&mut self, it: &AssignmentExpression<'a>) {
        let target = match &it.left {
            AssignmentTarget::AssignmentTargetIdentifier(id) => Some(id.name.to_string()),
            t => t.as_member_expression().and_then(|m| match m {
                MemberExpression::StaticMemberExpression(s) => self.expr_ref(&s.object, 0).map(|r| r.push(s.property.name.as_str()).render()),
                MemberExpression::ComputedMemberExpression(c) => match &c.expression {
                    Expression::StringLiteral(k) => self.expr_ref(&c.object, 0).map(|r| r.push(k.value.as_str()).render()),
                    _ => None,
                },
                _ => None,
            }),
        };
        let right = it.right.get_inner_expression();
        if let Some(t) = &target {
            if let Some(rest) = t.strip_prefix("module.exports.").or_else(|| t.strip_prefix("exports.")) {
                push_unique(&mut self.facts.exports.cjs, rest.to_string(), MAX_LIST);
            } else if t == "module.exports" {
                let kind = match right {
                    Expression::ObjectExpression(o) => {
                        for p in &o.properties {
                            if let ObjectPropertyKind::ObjectProperty(p) = p
                                && let Some(k) = p.key.static_name()
                            {
                                push_unique(&mut self.facts.exports.cjs, k.to_string(), MAX_LIST);
                            }
                        }
                        "object"
                    }
                    Expression::FunctionExpression(_) | Expression::ArrowFunctionExpression(_) => "function",
                    Expression::ClassExpression(_) => "class",
                    Expression::Identifier(_) => "identifier",
                    Expression::CallExpression(_) | Expression::NewExpression(_) => "call",
                    _ => "other",
                };
                self.facts.exports.cjs_whole = Some(kind.into());
            }
            if is_function_like(right) {
                self.name_next(right, t.clone());
            } else if let Expression::NewExpression(_) = right {
                self.pending_window = Some(t.clone());
            }
            if let Some(ev) = t.rsplit('.').next().and_then(|p| p.strip_prefix("on")).filter(|e| !e.is_empty() && e.chars().all(|c| c.is_ascii_lowercase())) {
                let target = t.rsplit_once('.').map(|(a, _)| a.to_string()).unwrap_or_default();
                if !target.is_empty() && self.facts.events.len() < MAX_LIST {
                    let handler = match right {
                        Expression::Identifier(id) => Some(id.name.to_string()),
                        x if is_function_like(x) => Some(t.clone()),
                        _ => None,
                    };
                    let line = self.line(it.span.start);
                    let function = self.current_fn();
                    self.facts.events.push(EventUse { target, event: ev.to_string(), handler, line, offset: it.span.start, function });
                }
            }
        }
        walk::walk_assignment_expression(self, it);
        self.pending_window = None;
    }

    fn visit_object_property(&mut self, it: &ObjectProperty<'a>) {
        if let Some(k) = it.key.static_name() {
            if is_function_like(it.value.get_inner_expression()) {
                let n = match self.object_prefix.last() {
                    Some(p) => format!("{p}.{k}"),
                    None => k.to_string(),
                };
                self.name_next(&it.value, n);
            }
            if k == "path"
                && let Expression::StringLiteral(s) = it.value.get_inner_expression()
                && (s.value.starts_with('/') || s.value.as_str() == "*" || s.value.starts_with(":"))
            {
                self.add_route(s.value.to_string(), "router-config", None, it.span.start);
            }
        }
        walk::walk_object_property(self, it);
    }

    fn visit_class(&mut self, it: &Class<'a>) {
        let pending = self.pending.remove(&it.span.start);
        let name = it.id.as_ref().map(|i| i.name.to_string()).or(pending).unwrap_or_else(|| "<class>".into());
        self.class_names.push(name);
        walk::walk_class(self, it);
        self.class_names.pop();
    }

    fn visit_method_definition(&mut self, it: &MethodDefinition<'a>) {
        if let Some(k) = it.key.static_name() {
            let c = self.class_names.last().cloned().unwrap_or_default();
            self.pending.insert(it.value.span.start, if c.is_empty() { k.to_string() } else { format!("{c}.{k}") });
        }
        walk::walk_method_definition(self, it);
    }

    fn visit_function(&mut self, it: &Function<'a>, flags: ScopeFlags) {
        let declared = matches!(it.r#type, FunctionType::FunctionDeclaration);
        let name = match (&it.id, declared) {
            (Some(id), true) => {
                self.pending.remove(&it.span.start);
                id.name.to_string()
            }
            (id, _) => self.fn_name(id.as_ref().map(|i| i.name.as_str()), it.span),
        };
        let kind = if matches!(it.r#type, FunctionType::FunctionDeclaration) { "declaration" } else { "expression" };
        let pushed = self.add_function(name, kind, it.span, &it.params);
        self.pending_window = None;
        walk::walk_function(self, it, flags);
        if pushed {
            self.frames.pop();
        }
    }

    fn visit_arrow_function_expression(&mut self, it: &ArrowFunctionExpression<'a>) {
        let name = self.fn_name(None, it.span);
        let pushed = self.add_function(name, "arrow", it.span, &it.params);
        self.pending_window = None;
        walk::walk_arrow_function_expression(self, it);
        if pushed {
            self.frames.pop();
        }
    }

    fn visit_tagged_template_expression(&mut self, it: &TaggedTemplateExpression<'a>) {
        self.api_tagged(it);
        walk::walk_tagged_template_expression(self, it);
    }

    fn visit_object_expression(&mut self, it: &ObjectExpression<'a>) {
        self.api_object(it);
        walk::walk_object_expression(self, it);
    }

    fn visit_call_expression(&mut self, it: &CallExpression<'a>) {
        self.api_call(it);
        if self.on_call(it) {
            // Arguments were already walked (with qualified names).
            self.visit_expression(&it.callee);
            return;
        }
        walk::walk_call_expression(self, it);
    }

    fn visit_new_expression(&mut self, it: &NewExpression<'a>) {
        self.on_new(it);
        walk::walk_new_expression(self, it);
    }

    fn visit_string_literal(&mut self, it: &StringLiteral<'a>) {
        let v = it.value.to_string();
        self.record_string(&v, it.span.start);
        self.api_string(&v, it.span.start);
        if v.starts_with("webpackChunk") {
            self.marker("webpackChunk");
        }
    }

    fn visit_template_literal(&mut self, it: &TemplateLiteral<'a>) {
        if it.expressions.is_empty()
            && let Some(q) = it.quasis.first()
        {
            let v = q.value.cooked.as_ref().map_or_else(|| q.value.raw.to_string(), |c| c.to_string());
            self.record_string(&v, it.span.start);
            self.api_string(&v, it.span.start);
        }
        self.api_template(it);
        walk::walk_template_literal(self, it);
    }

    fn visit_identifier_reference(&mut self, it: &IdentifierReference<'a>) {
        self.marker(it.name.as_str());
    }

    fn visit_identifier_name(&mut self, it: &IdentifierName<'a>) {
        self.marker(it.name.as_str());
    }

    fn visit_binding_identifier(&mut self, it: &BindingIdentifier<'a>) {
        self.marker(it.name.as_str());
    }

    fn visit_jsx_opening_element(&mut self, it: &JSXOpeningElement<'a>) {
        self.facts.jsx = true;
        let el = match &it.name {
            JSXElementName::Identifier(i) => i.name.to_string(),
            JSXElementName::IdentifierReference(i) => i.name.to_string(),
            JSXElementName::MemberExpression(_) => self.text(it.name.span()).to_string(),
            _ => String::new(),
        };
        for a in &it.attributes {
            let JSXAttributeItem::Attribute(a) = a else { continue };
            let JSXAttributeName::Identifier(n) = &a.name else { continue };
            let attr = n.name.as_str();
            if attr == "path"
                && el.ends_with("Route")
                && let Some(JSXAttributeValue::StringLiteral(s)) = &a.value
            {
                self.add_route(s.value.to_string(), "jsx", None, a.span.start);
            }
            if let Some(ev) = attr.strip_prefix("on").filter(|e| e.chars().next().is_some_and(|c| c.is_ascii_uppercase())) {
                let handler = match &a.value {
                    Some(JSXAttributeValue::ExpressionContainer(c)) => match &c.expression {
                        JSXExpression::Identifier(id) => Some(id.name.to_string()),
                        e => e.as_expression().and_then(|x| self.callee_name(x)).or_else(|| Some(format!("<{el} {attr}>"))),
                    },
                    _ => None,
                };
                if let Some(Some(JSXAttributeValue::ExpressionContainer(c))) = Some(&a.value)
                    && let Some(e) = c.expression.as_expression()
                    && is_function_like(e.get_inner_expression())
                {
                    self.name_next(e, format!("<{el} {attr}>"));
                }
                if self.facts.events.len() < MAX_LIST {
                    let line = self.line(a.span.start);
                    let function = self.current_fn();
                    self.facts.events.push(EventUse {
                        target: format!("<{el}>"),
                        event: ev.to_ascii_lowercase(),
                        handler,
                        line,
                        offset: a.span.start,
                        function,
                    });
                }
            }
        }
        walk::walk_jsx_opening_element(self, it);
    }
}
