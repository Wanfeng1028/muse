//! Facts extracted from one JavaScript source. Plain serde data; every position is a 1-based line
//! plus a byte offset into the source we were given.

use serde::{Deserialize, Serialize};

/// How the facts were obtained.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "kebab-case")]
pub enum ParseMode {
    /// Parsed into a full syntax tree.
    #[default]
    Parsed,
    /// Parsed, but the parser recovered from errors; some code may be missing.
    ParsedWithErrors,
    /// The parser was not used (too large, too deeply nested, or it failed); facts come from a
    /// token scan and are less complete.
    Lexer,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ImportRef {
    /// `import`, `dynamic-import`, `require`, `re-export`, `worker`, `service-worker`,
    /// `import-scripts`, `utility-process`, `html-script`, `modulepreload`.
    pub kind: String,
    /// The specifier, or a template with `{…}` holes when it is only partly literal.
    pub specifier: String,
    /// False when the specifier was not a plain literal.
    pub literal: bool,
    /// Imported names (`default`, `*`, or named).
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub names: Vec<String>,
    pub line: u32,
    pub offset: u32,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct ExportShape {
    /// ES module export names (`default` for the default export, `*` for `export *`).
    pub esm: Vec<String>,
    /// CommonJS `exports.x` / `module.exports.x` names.
    pub cjs: Vec<String>,
    /// What `module.exports = …` was assigned: `object`, `function`, `class`, `identifier`, `call`, `other`.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub cjs_whole: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IpcUse {
    /// `main` (ipcMain), `renderer` (ipcRenderer), `web-contents` (webContents.send).
    pub side: String,
    /// `handle`, `handleOnce`, `on`, `once`, `invoke`, `send`, `sendSync`, `sendTo`, `postMessage`, `removeHandler`…
    pub method: String,
    pub channel: Option<String>,
    pub line: u32,
    pub offset: u32,
    /// Innermost enclosing function name.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub function: Option<String>,
    /// For listeners/handlers: the function that handles it, when named or inline.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub handler: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ExposedMember {
    pub name: String,
    /// Function that implements it (qualified name), when known.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub function: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Exposed {
    /// `exposeInMainWorld` or `exposeInIsolatedWorld`.
    pub method: String,
    /// The global key, e.g. `api` → `window.api`.
    pub key: Option<String>,
    pub members: Vec<ExposedMember>,
    pub line: u32,
    pub offset: u32,
}

/// A `webPreferences` value: a literal, or `dynamic` when computed.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(untagged)]
pub enum PrefValue {
    Bool(bool),
    Text(String),
}

/// A variable holding an object literal, and the line it was declared on.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct NamedObjectRef {
    pub name: String,
    pub line: u32,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct WindowFact {
    /// `BrowserWindow`, `BrowserView`, `WebContentsView`.
    pub class: String,
    /// Variable or property the window was stored in.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub binding: Option<String>,
    /// Preload path as written (string parts joined), when it could be read.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub preload: Option<String>,
    /// Explicit webPreferences: contextIsolation, nodeIntegration, sandbox, webSecurity, …
    pub web_preferences: std::collections::BTreeMap<String, PrefValue>,
    /// The local object the options (or their webPreferences) were read from, when they weren't
    /// written inline: `opts` for `const opts = {…}; new BrowserWindow(opts)`.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub options_from: Option<NamedObjectRef>,
    pub line: u32,
    pub offset: u32,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub function: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct LoadFact {
    /// `loadFile` or `loadURL`.
    pub method: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub receiver: Option<String>,
    pub target: Option<String>,
    pub line: u32,
    pub offset: u32,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Endpoint {
    /// `fetch`, `axios`, `xhr`, `websocket`, `eventsource`, `beacon`, `jquery`, `http`, `literal`.
    pub api: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub method: Option<String>,
    /// URL, or a template with `{…}` holes for the parts that were not literal.
    pub url: String,
    /// True when the whole URL was literal (constants included).
    pub literal: bool,
    pub line: u32,
    pub offset: u32,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub function: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Route {
    pub path: String,
    /// `router-config`, `server`, `jsx`, `protocol`.
    pub source: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub method: Option<String>,
    pub line: u32,
    pub offset: u32,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ApiUse {
    /// Canonical API path, e.g. `fs.writeFile`, `dialog.showSaveDialog`, `localStorage.setItem`.
    pub api: String,
    /// First argument when it is (partly) literal.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub arg: Option<String>,
    pub line: u32,
    pub offset: u32,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub function: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct EventUse {
    /// What the listener is attached to (`app`, `win`, `document.getElementById(save)`, …).
    pub target: String,
    pub event: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub handler: Option<String>,
    pub line: u32,
    pub offset: u32,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub function: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct FunctionFact {
    /// Qualified name (`saveNotes`, `api.exportNotes`, `Store.load`, `ipcMain.handle(export-notes)`, `<anonymous@12>`).
    pub name: String,
    /// `declaration`, `expression`, `arrow`, `method`.
    pub kind: String,
    pub line: u32,
    pub end_line: u32,
    pub start: u32,
    pub end: u32,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub params: Vec<String>,
    /// Canonical callee paths, in first-seen order.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub calls: Vec<String>,
    /// String literals used directly in this function.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub strings: Vec<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub parent: Option<String>,
    pub exported: bool,
}

/// A GraphQL operation or tRPC procedure the code appears to define or call. Always inferred from how
/// the code is written, and nothing is run to check it.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ApiOperation {
    /// `graphql` or `trpc`.
    pub protocol: String,
    /// `query`, `mutation`, `subscription`; `operation` when it's named but its kind can't be told;
    /// `endpoint` for a URL the API lives at; `unknown` when run-time text or a spread hides what's there.
    pub kind: String,
    /// Operation name or dotted procedure path. With `literal` true, `None` is an anonymous operation.
    /// With `literal` false it's what is known: the router key something unreadable sits under, or nothing.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub url: Option<String>,
    /// False when part of this was only known at run time.
    pub literal: bool,
    /// `gql-template`, `gql-call`, `document-text`, `compiled-document`, `request-body`, `router`, `client-call`, `url`.
    pub source: String,
    pub line: u32,
    pub offset: u32,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub function: Option<String>,
}

/// A banner or marker naming bundled third-party code.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Vendor {
    pub name: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub version: Option<String>,
    /// `banner`, `marker`, `package-json`, `module-path`.
    pub source: String,
    pub line: u32,
}

/// Everything we learned from one source.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct ModuleFacts {
    pub mode: ParseMode,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub mode_reason: Option<String>,
    pub parse_errors: usize,
    /// `module`, `script` or `commonjs` (as detected).
    pub source_kind: String,
    pub bytes: usize,
    pub lines: u32,
    pub jsx: bool,
    pub imports: Vec<ImportRef>,
    pub exports: ExportShape,
    pub ipc: Vec<IpcUse>,
    pub exposed: Vec<Exposed>,
    pub windows: Vec<WindowFact>,
    pub loads: Vec<LoadFact>,
    pub endpoints: Vec<Endpoint>,
    pub routes: Vec<Route>,
    /// GraphQL operations and tRPC procedures (inferred).
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub api_operations: Vec<ApiOperation>,
    pub storage: Vec<ApiUse>,
    /// Side-effecting platform APIs: files, processes, shell, dialogs, network, crypto…
    pub effects: Vec<ApiUse>,
    pub events: Vec<EventUse>,
    pub functions: Vec<FunctionFact>,
    /// Required `.node` binaries and `bindings('x')` names.
    pub native_modules: Vec<String>,
    /// Bundler runtime markers seen (identifier → count).
    pub bundler_markers: std::collections::BTreeMap<String, u32>,
    pub vendors: Vec<Vendor>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub source_map_url: Option<String>,
    /// Distinct short string literals (bounded), for matching and search.
    pub strings: Vec<String>,
    /// Name-insensitive structural fingerprint of the whole source (sha256 hex).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub fingerprint: Option<String>,
    /// Lists cut short by a limit.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub truncated: Vec<String>,
}

/// One module found inside a bundle.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct BundleModule {
    /// The bundle's own id for it (number or path).
    pub id: String,
    /// `webpack`, `webpack-chunk`, `esbuild-cjs`, `esbuild-esm`, `browserify`.
    pub format: String,
    /// Chunk ids declared by the push that carried it (webpack chunks).
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub chunk_ids: Vec<String>,
    pub start: u32,
    pub end: u32,
    /// Inner body range (without braces) when the module function has a block body.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub body: Option<(u32, u32)>,
    pub line: u32,
    pub params: Vec<String>,
    /// Module ids this module requires.
    pub deps: Vec<String>,
    pub sha256: String,
    pub fingerprint: String,
}

/// What the bundle splitter found.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct BundleInfo {
    /// Bundlers identified, most likely first: `webpack`, `esbuild`, `vite`, `rollup`, `parcel`, `browserify`, `systemjs`, `turbopack`, `tsc`, `babel`.
    pub bundlers: Vec<String>,
    pub modules: Vec<BundleModule>,
    /// Ids of chunks this file registers (webpack `push`).
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub chunk_ids: Vec<String>,
    pub truncated: bool,
}
