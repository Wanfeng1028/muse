//! A lightweight C# declaration scanner (namespaces, types, methods, constructors, fields,
//! properties, events; nested types and generic arity) and a reconciliation of scanned
//! declarations against metadata members. It reads declarations only: method bodies are skipped,
//! so it says nothing about behaviour.

use super::model::Members;
use serde::Serialize;
use std::collections::{BTreeMap, BTreeSet};

const MAX_TOKENS: usize = 4_000_000;
const MAX_DEPTH: usize = 256;

#[derive(Debug, Clone, PartialEq, Eq)]
enum Tok {
    Ident(String),
    Punct(char),
    Arrow,
    Lit,
}

#[derive(Debug, Clone)]
struct T {
    tok: Tok,
    line: u32,
}

fn tokenize(src: &str) -> Vec<T> {
    let b: Vec<char> = src.chars().collect();
    let mut out = Vec::new();
    let mut i = 0usize;
    let mut line = 1u32;
    let mut line_start = true;
    let at = |i: usize| b.get(i).copied().unwrap_or('\0');
    while i < b.len() && out.len() < MAX_TOKENS {
        let c = at(i);
        if c == '\n' {
            line += 1;
            line_start = true;
            i += 1;
            continue;
        }
        if c.is_whitespace() {
            i += 1;
            continue;
        }
        if line_start && c == '#' {
            while i < b.len() && at(i) != '\n' {
                i += 1;
            }
            continue;
        }
        line_start = false;
        if c == '/' && at(i + 1) == '/' {
            while i < b.len() && at(i) != '\n' {
                i += 1;
            }
            continue;
        }
        if c == '/' && at(i + 1) == '*' {
            i += 2;
            while i < b.len() && !(at(i) == '*' && at(i + 1) == '/') {
                if at(i) == '\n' {
                    line += 1;
                }
                i += 1;
            }
            i += 2;
            continue;
        }
        // Strings: raw ("""…"""), verbatim (@"…"), interpolated ($"…"), regular.
        let mut j = i;
        let mut verbatim = false;
        while matches!(at(j), '@' | '$') && j < i + 3 {
            if at(j) == '@' {
                verbatim = true;
            }
            j += 1;
        }
        if at(j) == '"' {
            let line0 = line;
            let mut quotes = 0;
            while at(j + quotes) == '"' {
                quotes += 1;
            }
            if quotes >= 3 {
                let mut k = j + quotes;
                loop {
                    if k >= b.len() {
                        break;
                    }
                    let mut n = 0;
                    while at(k + n) == '"' {
                        n += 1;
                    }
                    if n >= quotes {
                        k += n;
                        break;
                    }
                    if at(k) == '\n' {
                        line += 1;
                    }
                    k += n.max(1);
                }
                i = k;
            } else {
                let mut k = j + 1;
                while k < b.len() {
                    let ch = at(k);
                    if ch == '\n' {
                        line += 1;
                    }
                    if verbatim {
                        if ch == '"' {
                            if at(k + 1) == '"' {
                                k += 2;
                                continue;
                            }
                            break;
                        }
                    } else if ch == '\\' {
                        k += 2;
                        continue;
                    } else if ch == '"' || ch == '\n' {
                        break;
                    }
                    k += 1;
                }
                i = k + 1;
            }
            out.push(T { tok: Tok::Lit, line: line0 });
            continue;
        }
        if c == '\'' {
            let mut k = i + 1;
            while k < b.len() && k < i + 12 {
                if at(k) == '\\' {
                    k += 2;
                    continue;
                }
                if at(k) == '\'' || at(k) == '\n' {
                    break;
                }
                k += 1;
            }
            i = k + 1;
            out.push(T { tok: Tok::Lit, line });
            continue;
        }
        if c.is_alphanumeric() || c == '_' || c == '@' {
            let start = i;
            i += 1;
            while i < b.len() && (at(i).is_alphanumeric() || at(i) == '_') {
                i += 1;
            }
            let word: String = b.get(start..i).map(|s| s.iter().collect()).unwrap_or_default();
            let word = word.trim_start_matches('@').to_string();
            if word.chars().next().is_some_and(|ch| ch.is_ascii_digit()) {
                out.push(T { tok: Tok::Lit, line });
            } else {
                out.push(T { tok: Tok::Ident(word), line });
            }
            continue;
        }
        if c == '=' && at(i + 1) == '>' {
            out.push(T { tok: Tok::Arrow, line });
            i += 2;
            continue;
        }
        out.push(T { tok: Tok::Punct(c), line });
        i += 1;
    }
    out
}

/// One scanned declaration.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct CsMember {
    /// method, constructor, field, property, event
    pub kind: &'static str,
    /// Declaring type, dotted (`Ns.Outer.Inner`).
    pub type_name: String,
    /// Metadata-style name (`.ctor`, `.cctor`, `Finalize`, `Item` for indexers).
    pub name: String,
    pub generic_arity: usize,
    pub params: Vec<String>,
    #[serde(rename = "type")]
    pub ty: String,
    pub line: u32,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct CsType {
    pub full_name: String,
    pub kind: String,
    pub generic_arity: usize,
    pub line: u32,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize)]
pub struct CsScan {
    pub types: Vec<CsType>,
    pub members: Vec<CsMember>,
    pub warnings: Vec<String>,
}

#[derive(Debug, Clone)]
enum Scope {
    Namespace(String),
    /// `positional` holds a record's positional properties, added when the body closes unless the body
    /// declares a member of the same name; `start` is the member count when the body opened.
    Type {
        full: String,
        simple: String,
        is_enum: bool,
        positional: Vec<CsMember>,
        start: usize,
    },
    Block,
}

const MODIFIERS: &[&str] = &[
    "public",
    "private",
    "protected",
    "internal",
    "static",
    "readonly",
    "const",
    "volatile",
    "virtual",
    "override",
    "abstract",
    "sealed",
    "extern",
    "unsafe",
    "new",
    "async",
    "partial",
    "fixed",
    "required",
    "file",
    "implicit",
    "explicit",
];
const TYPE_KW: &[&str] = &["class", "struct", "interface", "enum", "record", "delegate"];

fn ident(t: &T) -> Option<&str> {
    match &t.tok {
        Tok::Ident(s) => Some(s),
        _ => None,
    }
}

fn is_p(t: &T, c: char) -> bool {
    t.tok == Tok::Punct(c)
}

/// Join tokens into a type string.
fn join(ts: &[T]) -> String {
    let mut s = String::new();
    for t in ts {
        match &t.tok {
            Tok::Ident(w) => {
                if s.chars().last().is_some_and(|c| c.is_alphanumeric() || c == '_') {
                    s.push(' ');
                }
                s.push_str(w);
            }
            Tok::Punct(',') => s.push_str(", "),
            Tok::Punct(c) => s.push(*c),
            Tok::Arrow => s.push_str("=>"),
            Tok::Lit => s.push('…'),
        }
    }
    s
}

/// Split at top-level commas.
fn split_commas(ts: &[T]) -> Vec<&[T]> {
    let mut out = Vec::new();
    let mut depth = 0i32;
    let mut start = 0;
    for (i, t) in ts.iter().enumerate() {
        match t.tok {
            Tok::Punct('(' | '<' | '[' | '{') => depth += 1,
            Tok::Punct(')' | '>' | ']' | '}') => depth -= 1,
            Tok::Punct(',') if depth == 0 => {
                out.push(ts.get(start..i).unwrap_or(&[]));
                start = i + 1;
            }
            _ => {}
        }
    }
    if start < ts.len() {
        out.push(ts.get(start..).unwrap_or(&[]));
    }
    out
}

/// Index of the token matching the opener at `open` (same nesting kind), if any.
fn matching(ts: &[T], open: usize, o: char, c: char) -> Option<usize> {
    let mut depth = 0i32;
    for (i, t) in ts.iter().enumerate().skip(open) {
        if is_p(t, o) {
            depth += 1;
        } else if is_p(t, c) {
            depth -= 1;
            if depth == 0 {
                return Some(i);
            }
        }
    }
    None
}

/// Drop leading attributes (`[…]`) and modifiers.
fn strip_prefix(ts: &[T]) -> (&[T], Vec<String>) {
    let mut i = 0;
    let mut mods = Vec::new();
    loop {
        match ts.get(i) {
            Some(t) if is_p(t, '[') => match matching(ts, i, '[', ']') {
                Some(e) => i = e + 1,
                None => break,
            },
            Some(t) if ident(t).is_some_and(|w| MODIFIERS.contains(&w)) => {
                mods.push(ident(t).unwrap_or_default().to_string());
                i += 1;
            }
            _ => break,
        }
    }
    (ts.get(i..).unwrap_or(&[]), mods)
}

fn param_type(p: &[T]) -> String {
    let (p, _) = strip_prefix(p);
    // Default values.
    let p = match p.iter().position(|t| is_p(t, '=')) {
        Some(e) => p.get(..e).unwrap_or(p),
        None => p,
    };
    let mut byref = false;
    let mut start = 0;
    while let Some(w) = p.get(start).and_then(ident) {
        match w {
            "ref" | "out" | "in" => {
                byref = true;
                start += 1;
            }
            "this" | "params" | "scoped" | "readonly" => start += 1,
            _ => break,
        }
    }
    let body = p.get(start..).unwrap_or(&[]);
    // The last identifier is the parameter name.
    let ty = if body.len() >= 2 && body.last().and_then(ident).is_some() { body.get(..body.len() - 1).unwrap_or(&[]) } else { body };
    let s = join(ty);
    if byref { format!("ref {s}") } else { s }
}

/// Properties a positional record declares through its parameter list `params`.
fn positional_properties(kind: &str, params: &[T], type_name: &str, line: u32) -> Vec<CsMember> {
    if !kind.starts_with("record") {
        return Vec::new();
    }
    split_commas(params)
        .into_iter()
        .filter_map(|p| {
            let (p, _) = strip_prefix(p);
            let p = p.get(..p.iter().position(|t| is_p(t, '=')).unwrap_or(p.len())).unwrap_or(&[]);
            let name = p.last().and_then(ident)?;
            if p.len() < 2 {
                return None;
            }
            Some(CsMember {
                kind: "property",
                type_name: type_name.to_string(),
                name: name.to_string(),
                generic_arity: 0,
                params: vec![],
                ty: param_type(p),
                line,
            })
        })
        .collect()
}

struct Scanner {
    scopes: Vec<Scope>,
    file_ns: String,
    out: CsScan,
}

impl Scanner {
    fn prefix(&self) -> String {
        let mut parts: Vec<String> = Vec::new();
        if !self.file_ns.is_empty() {
            parts.push(self.file_ns.clone());
        }
        for s in &self.scopes {
            match s {
                Scope::Namespace(n) => parts.push(n.clone()),
                Scope::Type { simple, .. } => parts.push(simple.clone()),
                Scope::Block => {}
            }
        }
        parts.join(".")
    }

    fn current_type(&self) -> Option<(&str, &str, bool)> {
        match self.scopes.last()? {
            Scope::Type { full, simple, is_enum, .. } => Some((full, simple, *is_enum)),
            _ => None,
        }
    }

    /// Parse a type declaration header into its name, kind, generic arity, and line number.
    fn type_decl(&self, h: &[T]) -> Option<(String, String, usize, u32)> {
        let paren = h.iter().position(|t| is_p(t, '(')).unwrap_or(h.len());
        let kw = h.iter().take(paren).position(|t| ident(t).is_some_and(|w| TYPE_KW.contains(&w)))?;
        // A declaration keyword cannot follow an assignment or arrow operator.
        if h.iter().take(kw).any(|t| is_p(t, '=') || t.tok == Tok::Arrow) {
            return None;
        }
        let kind = ident(h.get(kw)?)?;
        if kind == "delegate" {
            if h.get(kw + 1).is_some_and(|t| is_p(t, '*')) {
                return None;
            }
            let is_reserved = |w: &str| w == "delegate" || w == "ref" || w == "void" || MODIFIERS.contains(&w) || TYPE_KW.contains(&w);
            let mut target = None;
            for p in (kw + 1)..h.len() {
                if !is_p(&h[p], '(') {
                    continue;
                }
                if p > kw + 1 && is_p(&h[p - 1], '>') {
                    let mut depth = 0i32;
                    let mut open_lt = None;
                    for i in (kw + 1..p).rev() {
                        let t = &h[i];
                        if is_p(t, '>') {
                            depth += 1;
                        } else if is_p(t, '<') {
                            depth -= 1;
                            if depth == 0 {
                                open_lt = Some(i);
                                break;
                            }
                        }
                    }
                    if let Some(lt) = open_lt
                        && lt > kw + 1
                        && let Some(name_tok) = h.get(lt - 1)
                        && let Some(name) = ident(name_tok)
                        && !is_reserved(name)
                    {
                        let arity = split_commas(h.get(lt + 1..p - 1).unwrap_or(&[])).len();
                        target = Some((name.to_string(), arity, name_tok.line));
                        break;
                    }
                } else if let Some(name_tok) = h.get(p - 1)
                    && let Some(name) = ident(name_tok)
                    && !is_reserved(name)
                {
                    target = Some((name.to_string(), 0, name_tok.line));
                    break;
                }
            }
            let (name, arity, line) = target?;
            return Some((name, "delegate".into(), arity, line));
        }
        let mut k = kw + 1;
        let mut kind = kind.to_string();
        if kind == "record" && h.get(k).and_then(ident).is_some_and(|w| w == "struct" || w == "class") {
            kind = format!("record {}", ident(h.get(k)?)?);
            k += 1;
        }
        let name = ident(h.get(k)?)?.to_string();
        let arity = if h.get(k + 1).is_some_and(|t| is_p(t, '<')) {
            let e = matching(h, k + 1, '<', '>')?;
            split_commas(h.get(k + 2..e)?).len()
        } else {
            0
        };
        Some((name, kind, arity, h.get(k)?.line))
    }

    /// Record a member declared by header `h` inside the current type.
    fn member(&mut self, h: &[T], has_body: bool) {
        let Some((full, simple, is_enum)) = self.current_type().map(|(a, b, c)| (a.to_string(), b.to_string(), c)) else { return };
        let (rest, mods) = strip_prefix(h);
        if rest.is_empty() {
            return;
        }
        let line = rest.first().map(|t| t.line).unwrap_or(0);
        if is_enum {
            for part in split_commas(rest) {
                if let Some(n) = part.first().and_then(ident) {
                    self.push(CsMember { kind: "field", type_name: full.clone(), name: n.into(), generic_arity: 0, params: vec![], ty: simple.clone(), line });
                }
            }
            return;
        }
        // Top-level '=' or '=>' (default parameter values sit inside parentheses).
        let mut depth = 0i32;
        let mut eq = rest.len();
        let mut paren = None;
        for (i, t) in rest.iter().enumerate() {
            match t.tok {
                Tok::Punct('(') => {
                    if depth == 0 && paren.is_none() {
                        paren = Some(i);
                    }
                    depth += 1;
                }
                Tok::Punct(')') => depth -= 1,
                Tok::Punct('=') | Tok::Arrow if depth == 0 => {
                    eq = i;
                    break;
                }
                _ => {}
            }
        }
        let op_at = rest.iter().position(|t| ident(t) == Some("operator"));
        if let Some(op) = op_at {
            let p = rest.iter().skip(op).position(|t| is_p(t, '(')).map(|x| x + op);
            let params = p
                .and_then(|p| matching(rest, p, '(', ')').map(|c| (p, c)))
                .map(|(p, c)| split_commas(rest.get(p + 1..c).unwrap_or(&[])).into_iter().map(param_type).collect())
                .unwrap_or_default();
            let ret = join(rest.get(..op).unwrap_or(&[]));
            self.push(CsMember { kind: "method", type_name: full, name: "operator".into(), generic_arity: 0, params, ty: ret, line });
            return;
        }
        if let Some(p) = paren.filter(|&p| p < eq) {
            let decl = rest;
            let close = matching(decl, p, '(', ')').unwrap_or(decl.len());
            let params: Vec<String> = split_commas(decl.get(p + 1..close).unwrap_or(&[])).into_iter().map(param_type).filter(|s| !s.is_empty()).collect();
            let mut name_at = p.checked_sub(1);
            let mut arity = 0;
            if name_at.and_then(|i| decl.get(i)).is_some_and(|t| is_p(t, '>')) {
                // Walk back to the matching '<'.
                let mut depth = 0i32;
                for i in (0..p).rev() {
                    let Some(t) = decl.get(i) else { break };
                    if is_p(t, '>') {
                        depth += 1;
                    } else if is_p(t, '<') {
                        depth -= 1;
                        if depth == 0 {
                            arity = split_commas(decl.get(i + 1..p - 1).unwrap_or(&[])).len();
                            name_at = i.checked_sub(1);
                            break;
                        }
                    }
                }
            }
            let Some(ni) = name_at else { return };
            let Some(name) = decl.get(ni).and_then(ident) else { return };
            let is_finalizer = ni > 0 && decl.get(ni - 1).is_some_and(|t| is_p(t, '~'));
            let raw = join(decl.get(..ni).unwrap_or(&[]));
            let (kind, mname, ret) = if is_finalizer {
                ("method", "Finalize".to_string(), "void".to_string())
            } else if name == simple && raw.is_empty() {
                ("constructor", if mods.iter().any(|m| m == "static") { ".cctor".to_string() } else { ".ctor".to_string() }, "void".to_string())
            } else if let Some(q) = raw.strip_suffix('.') {
                // Explicit interface implementation: `void IFoo.Bar()`.
                let (ret, qual) = q.rsplit_once(' ').unwrap_or(("", q));
                ("method", format!("{qual}.{name}"), ret.to_string())
            } else {
                ("method", name.to_string(), raw)
            };
            self.push(CsMember { kind, type_name: full, name: mname, generic_arity: arity, params, ty: ret, line });
            return;
        }
        let decl = rest.get(..eq).unwrap_or(&[]);
        let is_event = decl.first().and_then(ident) == Some("event");
        let decl = if is_event { decl.get(1..).unwrap_or(&[]) } else { decl };
        // Indexers.
        if let Some(ti) = decl.iter().position(|t| ident(t) == Some("this"))
            && decl.get(ti + 1).is_some_and(|t| is_p(t, '['))
        {
            let close = matching(decl, ti + 1, '[', ']').unwrap_or(decl.len());
            let params = split_commas(decl.get(ti + 2..close).unwrap_or(&[])).into_iter().map(param_type).collect();
            self.push(CsMember {
                kind: "property",
                type_name: full,
                name: "Item".into(),
                generic_arity: 0,
                params,
                ty: join(decl.get(..ti).unwrap_or(&[])),
                line,
            });
            return;
        }
        // Properties (with an accessor body or `=>`) and fields/events (possibly several declarators).
        let is_property = !is_event && (has_body || rest.get(eq).is_some_and(|t| t.tok == Tok::Arrow));
        let whole = if is_event { rest.get(1..).unwrap_or(&[]) } else { rest };
        let parts: Vec<&[T]> = if is_property { vec![decl] } else { split_commas(whole) };
        let cut = |p: &'_ [T]| -> usize { p.iter().position(|t| is_p(t, '=')).unwrap_or(p.len()) };
        let first = parts.first().copied().map(|p| p.get(..cut(p)).unwrap_or(&[])).unwrap_or(&[]);
        if first.len() < 2 {
            return;
        }
        let ty = join(first.get(..first.len() - 1).unwrap_or(&[]));
        for (i, part) in parts.iter().enumerate() {
            let part = part.get(..cut(part)).unwrap_or(&[]);
            let name_tok = if i == 0 { part.last() } else { part.first() };
            let Some(name) = name_tok.and_then(ident) else { continue };
            let kind = if is_event {
                "event"
            } else if is_property {
                "property"
            } else {
                "field"
            };
            self.push(CsMember { kind, type_name: full.clone(), name: name.into(), generic_arity: 0, params: vec![], ty: ty.clone(), line });
            if is_property {
                break;
            }
        }
    }

    fn push(&mut self, m: CsMember) {
        if self.out.members.len() < 1_000_000 {
            self.out.members.push(m);
        }
    }

    /// Scan token stream into types, members, and namespace scopes.
    fn run(mut self, toks: &[T]) -> CsScan {
        let mut cur: Vec<T> = Vec::new();
        let mut expr_depth = 0i32;
        let mut i = 0usize;
        while let Some(t) = toks.get(i) {
            i += 1;
            // Inside a method/accessor block: only track braces.
            if matches!(self.scopes.last(), Some(Scope::Block)) {
                if is_p(t, '{') {
                    if self.scopes.len() < MAX_DEPTH {
                        self.scopes.push(Scope::Block);
                    }
                } else if is_p(t, '}') {
                    self.scopes.pop();
                }
                continue;
            }
            let in_expr = cur.iter().any(|x| x.tok == Tok::Arrow || is_p(x, '='));
            if in_expr && expr_depth > 0 {
                if is_p(t, '{') {
                    expr_depth += 1;
                } else if is_p(t, '}') {
                    expr_depth -= 1;
                }
                continue;
            }
            match t.tok {
                Tok::Punct('[') if cur.is_empty() || cur.last().is_some_and(|x| is_p(x, ']')) => {
                    // Attribute: keep it in cur (strip_prefix drops it) but skip its contents.
                    let mut depth = 1;
                    cur.push(t.clone());
                    while let Some(n) = toks.get(i) {
                        i += 1;
                        if is_p(n, '[') {
                            depth += 1;
                        } else if is_p(n, ']') {
                            depth -= 1;
                            if depth == 0 {
                                cur.push(n.clone());
                                break;
                            }
                        }
                    }
                }
                Tok::Punct('{') if in_expr => {
                    expr_depth = 1;
                }
                Tok::Punct('{') => {
                    let h = std::mem::take(&mut cur);
                    if self.scopes.len() >= MAX_DEPTH {
                        self.out.warnings.push("nesting too deep; the rest of the file was skipped".into());
                        break;
                    }
                    if let Some(p) = h.iter().position(|x| ident(x) == Some("namespace")) {
                        let name = join(h.get(p + 1..).unwrap_or(&[]));
                        self.scopes.push(Scope::Namespace(name));
                    } else if let Some((name, kind, arity, line)) = self.type_decl(&h) {
                        let prefix = self.prefix();
                        let full = if prefix.is_empty() { name.clone() } else { format!("{prefix}.{name}") };
                        if self.out.types.len() < 200_000 {
                            self.out.types.push(CsType { full_name: full.clone(), kind: kind.clone(), generic_arity: arity, line });
                        }
                        // Positional records declare a constructor and properties.
                        let mut positional = Vec::new();
                        if kind != "delegate"
                            && let Some(p) = h.iter().position(|x| is_p(x, '('))
                        {
                            let close = matching(&h, p, '(', ')').unwrap_or(h.len());
                            let list = h.get(p + 1..close).unwrap_or(&[]);
                            let params: Vec<String> = split_commas(list).into_iter().map(param_type).collect();
                            self.push(CsMember {
                                kind: "constructor",
                                type_name: full.clone(),
                                name: ".ctor".into(),
                                generic_arity: 0,
                                params,
                                ty: "void".into(),
                                line,
                            });
                            positional = positional_properties(&kind, list, &full, line);
                        }
                        let start = self.out.members.len();
                        self.scopes.push(Scope::Type { full, simple: name, is_enum: kind == "enum", positional, start });
                    } else if self.current_type().is_some() {
                        self.member(&h, true);
                        self.scopes.push(Scope::Block);
                    } else {
                        self.scopes.push(Scope::Block);
                    }
                }
                Tok::Punct('}') => {
                    if self.current_type().is_some_and(|(_, _, e)| e) && !cur.is_empty() {
                        let h = std::mem::take(&mut cur);
                        self.member(&h, false);
                    }
                    cur.clear();
                    expr_depth = 0;
                    if let Some(Scope::Type { full, positional, start, .. }) = self.scopes.pop() {
                        // A member of the same name replaces the synthesized property.
                        for m in positional {
                            let declared = self.out.members.get(start..).unwrap_or(&[]).iter().any(|d| d.type_name == full && d.name == m.name);
                            if !declared {
                                self.push(m);
                            }
                        }
                    }
                }
                Tok::Punct(';') => {
                    let h = std::mem::take(&mut cur);
                    expr_depth = 0;
                    if let Some(p) = h.iter().position(|x| ident(x) == Some("namespace")) {
                        if self.scopes.is_empty() {
                            self.file_ns = join(h.get(p + 1..).unwrap_or(&[]));
                        }
                    } else if let Some((name, kind, arity, line)) = self.type_decl(&h) {
                        let prefix = self.prefix();
                        let full = if prefix.is_empty() { name } else { format!("{prefix}.{name}") };
                        if kind != "delegate"
                            && let Some(p) = h.iter().position(|x| is_p(x, '('))
                        {
                            let close = matching(&h, p, '(', ')').unwrap_or(h.len());
                            let list = h.get(p + 1..close).unwrap_or(&[]);
                            let params: Vec<String> = split_commas(list).into_iter().map(param_type).collect();
                            self.push(CsMember {
                                kind: "constructor",
                                type_name: full.clone(),
                                name: ".ctor".into(),
                                generic_arity: 0,
                                params,
                                ty: "void".into(),
                                line,
                            });
                            for m in positional_properties(&kind, list, &full, line) {
                                self.push(m);
                            }
                        }
                        if self.out.types.len() < 200_000 {
                            self.out.types.push(CsType { full_name: full, kind, generic_arity: arity, line });
                        }
                    } else if self.current_type().is_some() {
                        self.member(&h, false);
                    }
                }
                _ => cur.push(t.clone()),
            }
        }
        self.out
    }
}

/// Scan C# source for declarations.
pub fn scan(src: &str) -> CsScan {
    let toks = tokenize(src);
    let mut s = Scanner { scopes: Vec::new(), file_ns: String::new(), out: CsScan::default() }.run(&toks);
    if toks.len() >= MAX_TOKENS {
        s.warnings.push(format!("stopped after {MAX_TOKENS} tokens"));
    }
    s
}

/// Simplify a type for comparison: drop namespaces, map system type names to C# keywords, remove
/// spaces.
pub fn norm_type(s: &str) -> String {
    let mut out = String::new();
    let mut word = String::new();
    let flush = |word: &mut String, out: &mut String| {
        if !word.is_empty() {
            let last = word.rsplit('.').next().unwrap_or(word).to_string();
            let last = last.split('`').next().unwrap_or("").to_string();
            let mapped = match last.as_str() {
                "Void" => "void",
                "Boolean" => "bool",
                "Char" => "char",
                "SByte" => "sbyte",
                "Byte" => "byte",
                "Int16" => "short",
                "UInt16" => "ushort",
                "Int32" => "int",
                "UInt32" => "uint",
                "Int64" => "long",
                "UInt64" => "ulong",
                "Single" => "float",
                "Double" => "double",
                "String" => "string",
                "Object" => "object",
                "IntPtr" => "nint",
                "UIntPtr" => "nuint",
                "Decimal" => "decimal",
                "dynamic" => "object",
                other => other,
            };
            out.push_str(mapped);
            word.clear();
        }
    };
    for c in s.chars() {
        if c.is_alphanumeric() || c == '_' || c == '.' || c == '`' {
            word.push(c);
        } else {
            flush(&mut word, &mut out);
            if c == '/' {
                continue;
            }
            if !c.is_whitespace() {
                out.push(c);
            }
        }
    }
    flush(&mut word, &mut out);
    // `ref` and `out` both decode to a by-reference type.
    out.replace("ref", "ref ").replace("ref  ", "ref ")
}

/// Normalise a metadata type name (`Ns.Outer/Inner`1`) to the dotted form without arity.
fn norm_type_name(s: &str) -> (String, usize) {
    let mut arity = 0;
    let parts: Vec<String> = s
        .replace('/', ".")
        .split('.')
        .map(|p| match p.rsplit_once('`') {
            Some((n, a)) => {
                arity = a.parse().unwrap_or(0);
                n.to_string()
            }
            None => p.to_string(),
        })
        .collect();
    (parts.join("."), arity)
}

#[derive(Debug, Clone, Serialize)]
pub struct MemberMatch {
    pub kind: &'static str,
    pub type_name: String,
    pub name: String,
    pub metadata: Option<String>,
    pub source: Option<String>,
    pub line: Option<u32>,
    pub token: Option<String>,
    pub reason: Option<String>,
}

#[derive(Debug, Clone, Default, Serialize)]
pub struct Reconciliation {
    pub matched: Vec<MemberMatch>,
    pub signature_mismatch: Vec<MemberMatch>,
    /// In metadata but not declared in the source.
    pub missing: Vec<MemberMatch>,
    /// Declared in the source but not in metadata.
    pub extra: Vec<MemberMatch>,
    /// Members the compiler emits without a declaration (accessors, default constructors…).
    pub implicit: Vec<MemberMatch>,
    pub missing_types: Vec<String>,
    pub extra_types: Vec<String>,
    pub matched_types: usize,
}

/// Explicit interface implementations are named `Iface.Member` (namespaced in metadata).
fn key_name(n: &str) -> &str {
    if n.starts_with('.') { n } else { n.rsplit('.').next().unwrap_or(n) }
}

fn compiler_generated(name: &str) -> bool {
    name.contains('<') || name.contains('$') || name.starts_with("CS$")
}

/// An accessor (`get_P`, `add_E`…) of a property or event in `props`. Explicit interface
/// implementations keep the qualifier in front: `Iface.get_P` belongs to `Iface.P`.
fn is_accessor(name: &str, props: &BTreeSet<&str>) -> bool {
    let (qualifier, local) = match name.rsplit_once('.') {
        Some((q, l)) => (Some(q), l),
        None => (None, name),
    };
    if !["get_", "set_", "add_", "remove_", "raise_"].iter().any(|p| local.starts_with(p)) {
        return false;
    }
    let Some((_, prop)) = local.split_once('_') else { return false };
    match qualifier {
        Some(q) => props.contains(format!("{q}.{prop}").as_str()),
        None => props.contains(prop),
    }
}

/// Check scanned declarations against metadata members.
pub fn reconcile(members: &Members, scan: &CsScan) -> Reconciliation {
    let mut r = Reconciliation::default();
    // Source members by (type, name).
    let mut src: BTreeMap<(String, String), Vec<(usize, &CsMember)>> = BTreeMap::new();
    for (i, m) in scan.members.iter().enumerate() {
        src.entry((m.type_name.clone(), key_name(&m.name).to_string())).or_default().push((i, m));
    }
    let mut used: BTreeSet<usize> = BTreeSet::new();
    let src_types: BTreeSet<String> = scan.types.iter().map(|t| t.full_name.clone()).collect();
    let mut meta_types = BTreeSet::new();
    let src_sig = |m: &CsMember| format!("{}({})", m.name, m.params.join(", "));
    for ty in &members.types {
        if ty.kind == "module" || compiler_generated(&ty.full_name) {
            continue;
        }
        let (tname, _) = norm_type_name(&ty.full_name);
        meta_types.insert(tname.clone());
        if src_types.contains(&tname) {
            r.matched_types += 1;
        } else {
            r.missing_types.push(ty.full_name.clone());
        }
        let props: BTreeSet<&str> = ty.properties.iter().map(|p| p.name.as_str()).chain(ty.events.iter().map(|e| e.name.as_str())).collect();
        let mut check = |kind: &'static str, name: &str, params: Vec<String>, meta_text: String, token: String, r: &mut Reconciliation| {
            let mm = |source: Option<&CsMember>, reason: Option<String>| MemberMatch {
                kind,
                type_name: ty.full_name.clone(),
                name: name.to_string(),
                metadata: Some(meta_text.clone()),
                source: source.map(src_sig),
                line: source.map(|s| s.line),
                token: Some(token.clone()),
                reason,
            };
            let cands = src.get(&(tname.clone(), key_name(name).to_string())).cloned().unwrap_or_default();
            let want: Vec<String> = params.iter().map(|p| norm_type(p)).collect();
            if let Some((i, s)) = cands.iter().find(|(i, s)| !used.contains(i) && s.params.iter().map(|p| norm_type(p)).collect::<Vec<_>>() == want) {
                used.insert(*i);
                r.matched.push(mm(Some(s), None));
            } else if let Some((i, s)) = cands.iter().find(|(i, s)| !used.contains(i) && s.params.len() == want.len()) {
                used.insert(*i);
                let got: Vec<String> = s.params.iter().map(|p| norm_type(p)).collect();
                r.signature_mismatch.push(mm(Some(s), Some(format!("parameters ({}) vs ({})", want.join(", "), got.join(", ")))));
            } else if compiler_generated(name)
                || name == ".cctor"
                || (name == ".ctor" && params.is_empty())
                || is_accessor(name, &props)
                || (ty.kind == "delegate" && ["Invoke", "BeginInvoke", "EndInvoke", ".ctor"].contains(&name))
                || (ty.kind == "enum" && name == "value__")
            {
                r.implicit.push(mm(None, Some("emitted by the compiler without a declaration".into())));
            } else {
                r.missing.push(mm(None, None));
            }
        };
        for m in &ty.methods {
            let params: Vec<String> = m.params.iter().map(|p| p.ty.clone()).collect();
            check("method", &m.name, params, m.signature.clone(), m.token.clone(), &mut r);
        }
        for f in &ty.fields {
            check("field", &f.name, vec![], format!("{} {}", f.ty, f.name), f.token.clone(), &mut r);
        }
        for p in &ty.properties {
            check("property", &p.name, vec![], format!("{} {}", p.ty, p.name), String::new(), &mut r);
        }
        for e in &ty.events {
            check("event", &e.name, vec![], format!("event {} {}", e.ty, e.name), String::new(), &mut r);
        }
    }
    for t in &scan.types {
        if !meta_types.contains(&t.full_name) {
            r.extra_types.push(t.full_name.clone());
        }
    }
    for (i, m) in scan.members.iter().enumerate() {
        if !used.contains(&i) {
            r.extra.push(MemberMatch {
                kind: m.kind,
                type_name: m.type_name.clone(),
                name: m.name.clone(),
                metadata: None,
                source: Some(src_sig(m)),
                line: Some(m.line),
                token: None,
                reason: None,
            });
        }
    }
    r
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::dotnet::model::{MethodInfo, PropertyInfo, TypeInfo};

    #[test]
    fn scans_declarations() {
        let s = scan(
            r#"
namespace A.B;
/* comment { */
public sealed class Box<T> : IDisposable where T : class
{
    private readonly List<int> _items = new() { 1, 2 }, _other;
    public int Count { get; set; } = 3;
    public string Name => "x{";
    public T this[int i] => default;
    public event EventHandler Changed;
    public Box() : base() { var s = @"a""b"; }
    static Box() { }
    ~Box() { }
    public static Box<T> Create<U, V>(ref int x, out string y, params object[] rest) where U : struct { return null; }
    void IDisposable.Dispose() { }
    public static bool operator ==(Box<T> a, Box<T> b) => true;
    public enum Mode { A, B = 2, C }
    public record Point(int X, int Y);
}
"#,
        );
        let names: Vec<(&str, &str)> = s.members.iter().map(|m| (m.kind, m.name.as_str())).collect();
        assert!(names.contains(&("field", "_items")), "{names:?}");
        assert!(names.contains(&("field", "_other")));
        assert!(names.contains(&("property", "Count")));
        assert!(names.contains(&("property", "Name")));
        assert!(names.contains(&("property", "Item")));
        assert!(names.contains(&("event", "Changed")));
        assert!(names.contains(&("constructor", ".ctor")));
        assert!(names.contains(&("constructor", ".cctor")));
        assert!(names.contains(&("method", "Finalize")));
        assert!(names.contains(&("method", "IDisposable.Dispose")));
        assert!(names.contains(&("method", "operator")));
        assert!(names.contains(&("field", "C")));
        let create = s.members.iter().find(|m| m.name == "Create").unwrap();
        assert_eq!(create.generic_arity, 2);
        assert_eq!(create.params, vec!["ref int", "ref string", "object[]"]);
        assert_eq!(create.ty, "Box<T>");
        assert_eq!(create.type_name, "A.B.Box");
        let types: Vec<&str> = s.types.iter().map(|t| t.full_name.as_str()).collect();
        assert_eq!(types, vec!["A.B.Box", "A.B.Box.Mode", "A.B.Box.Point"]);
        assert_eq!(s.types[0].generic_arity, 1);
    }

    #[test]
    fn normalises_types() {
        assert_eq!(norm_type("System.Collections.Generic.List<System.Int32>"), "List<int>");
        assert_eq!(norm_type("List<int>"), "List<int>");
        assert_eq!(norm_type("ref int"), "ref int");
        assert_eq!(norm_type_name("Ns.Outer/Inner`1"), ("Ns.Outer.Inner".into(), 1));
    }

    fn method(name: &str) -> MethodInfo {
        MethodInfo {
            token: String::new(),
            name: name.into(),
            key: String::new(),
            signature: name.into(),
            return_type: String::new(),
            params: vec![],
            generic_params: vec![],
            visibility: "private",
            modifiers: vec![],
            code_type: "il",
            internal_call: false,
            pinvoke: false,
            rva: 0,
            body: None,
        }
    }

    fn ty(name: &str, kind: &'static str, methods: &[&str], props: &[&str]) -> TypeInfo {
        TypeInfo {
            token: String::new(),
            full_name: name.into(),
            namespace: String::new(),
            name: name.into(),
            kind,
            visibility: "internal",
            modifiers: vec![],
            extends: None,
            enclosing_type: None,
            generic_params: vec![],
            interfaces: vec![],
            fields: vec![],
            methods: methods.iter().map(|m| method(m)).collect(),
            properties: props.iter().map(|p| PropertyInfo { name: (*p).into(), ty: "int".into() }).collect(),
            events: vec![],
        }
    }

    #[test]
    fn explicit_interface_property_accessors_are_implicit() {
        let members = Members {
            types: vec![
                ty("Interface", "interface", &["get_Property", "set_Property"], &["Property"]),
                ty("Class", "class", &["Interface.get_Property", "Interface.set_Property", ".ctor", "Other.get_X"], &["Interface.Property"]),
            ],
            total_types: 2,
            total_methods: 6,
            total_fields: 0,
            truncated: false,
            warnings: vec![],
        };
        let s = scan("interface Interface { int Property { get; set; } } class Class : Interface { int Interface.Property { get; set; } }");
        let r = reconcile(&members, &s);
        let missing: Vec<&str> = r.missing.iter().map(|m| m.name.as_str()).collect();
        assert_eq!(missing, vec!["Other.get_X"]);
        assert!(r.extra.is_empty(), "{:?}", r.extra);
        assert_eq!(r.matched.iter().filter(|m| m.kind == "property").count(), 2);
        let implicit: Vec<&str> = r.implicit.iter().map(|m| m.name.as_str()).collect();
        assert!(implicit.contains(&"Interface.get_Property"), "{implicit:?}");
        assert!(implicit.contains(&"Interface.set_Property"), "{implicit:?}");
    }

    #[test]
    fn scans_and_reconciles_delegate_declarations() {
        let s = scan(
            r#"
namespace Newtonsoft.Json.Serialization;

public delegate void ExtensionDataSetter(object o, string key, object value);
public delegate TResult Func<out TResult>();
public delegate (int, int) Pair();
public delegate (string Name, int Age) GetUser<T>(T id);

public class Container {
    public delegate bool Filter(int item);
    public Action callback = delegate { };
    public Action<int> onCount = delegate(int x) { };
    public unsafe delegate*<int, void> fp;
}
"#,
        );
        let types: Vec<(&str, &str, usize)> = s.types.iter().map(|t| (t.full_name.as_str(), t.kind.as_str(), t.generic_arity)).collect();
        assert!(types.contains(&("Newtonsoft.Json.Serialization.ExtensionDataSetter", "delegate", 0)), "{types:?}");
        assert!(types.contains(&("Newtonsoft.Json.Serialization.Func", "delegate", 1)), "{types:?}");
        assert!(types.contains(&("Newtonsoft.Json.Serialization.Pair", "delegate", 0)), "{types:?}");
        assert!(types.contains(&("Newtonsoft.Json.Serialization.GetUser", "delegate", 1)), "{types:?}");
        assert!(types.contains(&("Newtonsoft.Json.Serialization.Container.Filter", "delegate", 0)), "{types:?}");
        assert!(!types.iter().any(|(name, _, _)| name.ends_with(".delegate")), "anonymous delegates must not register as types: {types:?}");

        let fields: Vec<(&str, &str)> = s.members.iter().filter(|m| m.kind == "field").map(|m| (m.name.as_str(), m.ty.as_str())).collect();
        assert!(fields.contains(&("callback", "Action")), "{fields:?}");
        assert!(fields.contains(&("onCount", "Action<int>")), "{fields:?}");
        assert!(fields.iter().any(|(name, _)| *name == "fp"), "{fields:?}");

        let members = Members {
            types: vec![ty("Newtonsoft.Json.Serialization.ExtensionDataSetter", "delegate", &[".ctor", "Invoke", "BeginInvoke", "EndInvoke"], &[])],
            total_types: 1,
            total_methods: 4,
            total_fields: 0,
            truncated: false,
            warnings: vec![],
        };
        let r = reconcile(&members, &s);
        assert_eq!(r.matched_types, 1);
        assert!(r.missing_types.is_empty(), "delegate is not missing: {:?}", r.missing_types);
        assert!(r.missing.is_empty(), "synthetic delegate methods are not missing: {:?}", r.missing);
    }

    #[test]
    fn junk_does_not_panic() {
        for src in ["", "{{{{", "}}}}", "class", "class X {", "\"unterminated", "'", "/*", "@\"", "$\"\"\"", "namespace ;", "class X { void (", "enum E { , }"]
        {
            let _ = scan(src);
        }
        let deep = "{".repeat(10_000);
        let _ = scan(&deep);
        let mut weird = String::new();
        for i in 0..2000u32 {
            weird.push(char::from_u32(i * 7 % 0x2fff).unwrap_or('x'));
        }
        let _ = scan(&weird);
    }

    #[test]
    fn positional_record_declares_properties() {
        use crate::dotnet::model::PropertyInfo;
        use crate::dotnet::{MethodInfo, Param, TypeInfo};
        let method = |name: &str, params: &[&str], ty: &str| MethodInfo {
            token: String::new(),
            name: name.into(),
            key: String::new(),
            signature: name.into(),
            return_type: ty.into(),
            params: params.iter().map(|p| Param { name: String::new(), ty: (*p).into() }).collect(),
            generic_params: vec![],
            visibility: "public",
            modifiers: vec![],
            code_type: "il",
            internal_call: false,
            pinvoke: false,
            rva: 0,
            body: None,
        };
        let members = Members {
            types: vec![TypeInfo {
                token: "0x02000002".into(),
                full_name: "N.Point".into(),
                namespace: "N".into(),
                name: "Point".into(),
                kind: "class",
                visibility: "public",
                modifiers: vec![],
                extends: Some("object".into()),
                enclosing_type: None,
                generic_params: vec![],
                interfaces: vec![],
                fields: vec![],
                methods: vec![
                    method(".ctor", &["int", "int"], "void"),
                    method("get_X", &[], "int"),
                    method("set_X", &["int"], "void"),
                    method("get_Y", &[], "int"),
                    method("set_Y", &["int"], "void"),
                ],
                properties: vec![PropertyInfo { name: "X".into(), ty: "int".into() }, PropertyInfo { name: "Y".into(), ty: "int".into() }],
                events: vec![],
            }],
            total_types: 1,
            total_methods: 5,
            total_fields: 0,
            truncated: false,
            warnings: vec![],
        };
        for src in [
            "namespace N { public record Point(int X, int Y); }",
            "namespace N { public record Point(int X, int Y) { } }",
            "namespace N { public record Point(int X, int Y) { public int X { get; init; } = X; } }",
            "namespace N { public record Point(int X, [property: Obsolete] int Y) { public int X { get; init; } = X; public int Y { get; init; } = Y; } }",
        ] {
            let s = scan(src);
            let props: Vec<(&str, &str, &str)> =
                s.members.iter().filter(|m| m.kind == "property").map(|m| (m.type_name.as_str(), m.name.as_str(), m.ty.as_str())).collect();
            assert_eq!(props.len(), 2, "{src}: {props:?}");
            assert!(props.contains(&("N.Point", "X", "int")), "{src}: {props:?}");
            assert!(props.contains(&("N.Point", "Y", "int")), "{src}: {props:?}");
            let r = reconcile(&members, &s);
            assert!(r.missing.is_empty(), "{src}: {:?}", r.missing);
            assert!(r.extra.is_empty(), "{src}: {:?}", r.extra);
            assert_eq!(r.matched.len(), 3, "{src}");
        }
        // A class with a primary constructor does not get properties.
        let s = scan("namespace N { public class C(int x) { } }");
        assert!(s.members.iter().all(|m| m.kind != "property"));
    }
}
