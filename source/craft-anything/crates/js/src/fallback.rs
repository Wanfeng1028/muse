//! Facts from tokens alone, for sources the parser can't or shouldn't take. Coarser than the
//! syntax-tree pass: no functions, aliases or window options, but imports, IPC channels, URLs,
//! source map comments and banners still come through.

use crate::api_ops::{self, Row};
use crate::lex::{TokKind, Token, string_value, unescape};
use crate::model::*;
use crate::util::{LineIndex, push_unique};

pub(crate) fn facts_from_tokens(tokens: &[Token<'_>], lines: &LineIndex) -> ModuleFacts {
    let mut f = ModuleFacts { mode: ParseMode::Lexer, ..Default::default() };
    let sig: Vec<&Token<'_>> = tokens.iter().filter(|t| t.kind != TokKind::Comment).collect();
    let at = |i: usize| sig.get(i).map(|t| (t.kind, t.text));
    let mut seen = std::collections::HashSet::new();
    for (i, t) in sig.iter().enumerate() {
        let off = u32::try_from(t.offset).unwrap_or(u32::MAX);
        let line = lines.line(off);
        api_token(&mut f, &sig, i, off, line);
        match (t.kind, t.text) {
            (TokKind::Ident, "require" | "import") if at(i + 1) == Some((TokKind::Punct, "(")) => {
                if let Some((TokKind::Str, s)) = at(i + 2)
                    && at(i + 3) == Some((TokKind::Punct, ")"))
                    && f.imports.len() < crate::facts::MAX_LIST
                {
                    let kind = if t.text == "require" { "require" } else { "dynamic-import" };
                    let spec = string_value(s);
                    if spec.ends_with(".node") {
                        push_unique(&mut f.native_modules, spec.clone(), 1000);
                    }
                    f.imports.push(ImportRef { kind: kind.into(), specifier: spec, literal: true, names: Vec::new(), line, offset: off });
                }
            }
            (TokKind::Ident, "from") => {
                if let Some((TokKind::Str, s)) = at(i + 1)
                    && f.imports.len() < crate::facts::MAX_LIST
                {
                    f.imports.push(ImportRef { kind: "import".into(), specifier: string_value(s), literal: true, names: Vec::new(), line, offset: off });
                }
            }
            (TokKind::Ident, "fetch") if at(i + 1) == Some((TokKind::Punct, "(")) => {
                if let Some((TokKind::Str, s)) = at(i + 2) {
                    f.endpoints.push(Endpoint { api: "fetch".into(), method: None, url: string_value(s), literal: true, line, offset: off, function: None });
                }
            }
            (TokKind::Ident, method @ ("handle" | "handleOnce" | "invoke" | "on" | "once" | "send" | "sendSync" | "exposeInMainWorld"))
                if i >= 2 && at(i - 1) == Some((TokKind::Punct, ".")) && at(i + 1) == Some((TokKind::Punct, "(")) =>
            {
                let recv = sig.get(i - 2).map_or("", |t| t.text);
                let Some((TokKind::Str, s)) = at(i + 2) else { continue };
                let channel = string_value(s);
                if method == "exposeInMainWorld" {
                    f.exposed.push(Exposed { method: method.into(), key: Some(channel), members: Vec::new(), line, offset: off });
                    continue;
                }
                let side = match (recv, method) {
                    ("ipcMain", _) | (_, "handle" | "handleOnce") => "main",
                    ("ipcRenderer", _) | (_, "invoke" | "sendSync") => "renderer",
                    _ => continue,
                };
                if f.ipc.len() < crate::facts::MAX_LIST {
                    f.ipc.push(IpcUse { side: side.into(), method: method.into(), channel: Some(channel), line, offset: off, function: None, handler: None });
                }
            }
            (TokKind::Str, raw) => {
                let v = string_value(raw);
                if v.len() <= crate::facts::MAX_STRING_LEN && !v.is_empty() && f.strings.len() < crate::facts::MAX_STRINGS && seen.insert(v.clone()) {
                    let lower = v.get(..8).unwrap_or(&v).to_ascii_lowercase();
                    if lower.starts_with("http://") || lower.starts_with("https://") || lower.starts_with("ws://") || lower.starts_with("wss://") {
                        f.endpoints.push(Endpoint { api: "literal".into(), method: None, url: v.clone(), literal: true, line, offset: off, function: None });
                    }
                    f.strings.push(v);
                }
            }
            (TokKind::Ident, name) => {
                let key = if name.starts_with("webpackChunk") { "webpackChunk" } else { name };
                if matches!(
                    key,
                    "__webpack_require__"
                        | "webpackChunk"
                        | "__webpack_modules__"
                        | "__vitePreload"
                        | "__vite__mapDeps"
                        | "__commonJS"
                        | "__esm"
                        | "__toESM"
                        | "parcelRequire"
                        | "__turbopack_require__"
                        | "_interopRequireDefault"
                        | "__importDefault"
                ) {
                    *f.bundler_markers.entry(key.to_string()).or_insert(0) += 1;
                }
            }
            _ => {}
        }
    }
    f
}

/// GraphQL and tRPC from tokens: documents and URLs in strings, `gql` templates and client hooks.
/// Routers need the syntax tree, so they aren't seen here.
fn api_token(f: &mut ModuleFacts, sig: &[&Token<'_>], i: usize, off: u32, line: u32) {
    let at = |n: usize| sig.get(n).map(|t| (t.kind, t.text));
    let Some(t) = sig.get(i).copied() else { return };
    let (rows, source): (Vec<Row>, &str) = match t.kind {
        TokKind::Str => (api_ops::text_rows(&string_value(t.text)), "document-text"),
        TokKind::Template if t.text.starts_with('`') => {
            let tagged = i.checked_sub(1).and_then(at).is_some_and(|p| matches!(p, (TokKind::Ident, "gql" | "graphql")));
            let inner = t.text.get(1..).unwrap_or_default();
            if let Some(whole) = inner.strip_suffix('`') {
                let text = unescape(whole);
                if tagged {
                    let doc = api_ops::read_document(&text, true);
                    (doc.map_or_else(|| vec![Row::unknown("graphql")], |d| api_ops::document_rows(&d)), "gql-template")
                } else {
                    (api_ops::text_rows(&text), "document-text")
                }
            } else if tagged {
                // The rest of the document is in pieces the token scan doesn't join up.
                (vec![Row::unknown("graphql")], "gql-template")
            } else {
                (api_ops::url_rows(&format!("{}{{…}}", inner.strip_suffix("${").unwrap_or(inner))), "url")
            }
        }
        TokKind::Ident => {
            let Some(kind) = api_ops::client_hook(t.text) else { return };
            // Back along `a.b.c.useQuery`, as far as plain names go.
            let mut path: Vec<&str> = Vec::new();
            let mut j = i;
            while j >= 2 && at(j - 1) == Some((TokKind::Punct, ".")) && path.len() < 24 {
                match at(j - 2) {
                    Some((TokKind::Ident, name)) => path.push(name),
                    _ => return,
                }
                j -= 2;
            }
            // The first name is the client itself, so a procedure needs at least one after it.
            if path.len() < 2 || path.contains(&"endpoints") {
                return;
            }
            let name = path.iter().rev().skip(1).copied().collect::<Vec<_>>().join(".");
            (vec![Row { protocol: "trpc", kind, name: Some(name), url: None, literal: true }], "client-call")
        }
        _ => return,
    };
    for r in rows {
        let op = ApiOperation {
            protocol: r.protocol.into(),
            kind: r.kind.into(),
            name: r.name,
            url: r.url,
            literal: r.literal,
            source: source.into(),
            line,
            offset: off,
            function: None,
        };
        if !api_ops::push_operation(&mut f.api_operations, op, crate::facts::MAX_LIST) {
            if !f.truncated.iter().any(|x| x == "api_operations") {
                f.truncated.push("api_operations".into());
            }
            return;
        }
    }
}
