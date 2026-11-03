//! GraphQL operations and tRPC procedures, read from the syntax tree. Text and objects only partly
//! known at parse time (spreads, computed keys, `${…}`) give an unknown row, never a guess.

use super::*;
use crate::api_ops::{self, HOLE, MAX_DOCUMENT_BYTES, Row};

const MAX_ROUTER_DEPTH: usize = 16;
const MAX_CHAIN: usize = 32;
const MAX_ROUTER_ROWS: usize = 2_000;

/// A row read from a router, before knowing whether the object really is one.
struct RouterRow {
    kind: &'static str,
    name: Option<String>,
    literal: bool,
    offset: u32,
}

/// What reading one object as a router found.
#[derive(Default)]
struct RouterRead {
    rows: Vec<RouterRow>,
    /// Procedures recognised for certain: the evidence that this object is a router at all.
    definite: usize,
    /// Router calls nested inside, which the walk will reach later and must not read twice.
    nested: Vec<u32>,
}

fn joined(t: &TemplateLiteral<'_>, between: &str) -> Option<String> {
    let mut out = String::new();
    for (i, q) in t.quasis.iter().enumerate() {
        if i > 0 {
            out.push_str(between);
        }
        out.push_str(q.value.cooked.as_ref().map_or(q.value.raw.as_str(), |c| c.as_str()));
        if out.len() > MAX_DOCUMENT_BYTES {
            return None;
        }
    }
    Some(out)
}

fn procedure_method(name: &str) -> Option<&'static str> {
    match name {
        "query" => Some("query"),
        "mutation" => Some("mutation"),
        "subscription" => Some("subscription"),
        _ => None,
    }
}

fn vanilla_call(name: &str) -> Option<&'static str> {
    match name {
        "query" => Some("query"),
        "mutate" => Some("mutation"),
        "subscribe" => Some("subscription"),
        _ => None,
    }
}

fn prefixed(prefix: &str, key: &str) -> String {
    if prefix.is_empty() { key.to_string() } else { format!("{prefix}.{key}") }
}

fn known_prefix(prefix: &str) -> Option<String> {
    (!prefix.is_empty()).then(|| prefix.to_string())
}

impl FactVisitor<'_> {
    fn api_rows(&mut self, rows: Vec<Row>, source: &str, off: u32) {
        for r in rows {
            self.api_row(r, source, off);
        }
    }

    fn api_row(&mut self, r: Row, source: &str, off: u32) {
        let (line, function) = (self.line(off), self.current_fn());
        let op = ApiOperation {
            protocol: r.protocol.into(),
            kind: r.kind.into(),
            name: r.name.map(|n| clip(&n, MAX_STRING_LEN)),
            url: r.url.map(|u| clip(&u, MAX_STRING_LEN)),
            literal: r.literal,
            source: source.into(),
            line,
            offset: off,
            function,
        };
        if !api_ops::push_operation(&mut self.facts.api_operations, op, MAX_LIST) {
            self.truncated("api_operations");
        }
    }

    /// A string in the source: a whole GraphQL document, or a URL naming an API.
    pub(super) fn api_string(&mut self, s: &str, off: u32) {
        let rows = api_ops::text_rows(s);
        self.api_rows(rows, "document-text", off);
    }

    /// A template with `${…}` in it. Without any, it was read as a string already.
    pub(super) fn api_template(&mut self, t: &TemplateLiteral<'_>) {
        if t.expressions.is_empty() {
            return;
        }
        let off = t.span.start;
        if let Some(text) = joined(t, &HOLE.to_string())
            && api_ops::may_be_document(&text)
            && let Some(doc) = api_ops::read_document(&text, false)
        {
            self.api_rows(api_ops::document_rows(&doc), "document-text", off);
        }
        if let Some(url) = joined(t, "{…}") {
            let rows = api_ops::url_rows(&url);
            self.api_rows(rows, "url", off);
        }
    }

    /// `gql` and `graphql` tags: the tag has already said this text is a document.
    pub(super) fn api_tagged(&mut self, it: &TaggedTemplateExpression<'_>) {
        let is_tag = self.expr_ref(&it.tag, 0).is_some_and(|r| matches!(r.last(), Some("gql" | "graphql")));
        if !is_tag {
            return;
        }
        let off = it.quasi.span.start;
        let text = joined(&it.quasi, &HOLE.to_string());
        self.api_document(text.as_deref(), "gql-template", off);
    }

    fn api_document(&mut self, text: Option<&str>, source: &str, off: u32) {
        match text.and_then(|t| api_ops::read_document(t, true)) {
            Some(doc) => self.api_rows(api_ops::document_rows(&doc), source, off),
            None => self.api_row(Row::unknown("graphql"), source, off),
        }
    }

    /// Objects that are GraphQL: a compiled document's definition, or a request's body.
    pub(super) fn api_object(&mut self, o: &ObjectExpression<'_>) {
        let mut spread = false;
        let (mut kind, mut operation, mut name, mut operation_name, mut has_request_part) = (None, None, None, None, false);
        for p in &o.properties {
            match p {
                ObjectPropertyKind::SpreadProperty(_) => spread = true,
                ObjectPropertyKind::ObjectProperty(p) => match p.key.static_name().as_deref() {
                    Some("kind") => kind = Some(&p.value),
                    Some("operation") => operation = Some(&p.value),
                    Some("name") => name = Some(&p.value),
                    Some("operationName") => operation_name = Some(&p.value),
                    Some("query" | "variables" | "extensions") => has_request_part = true,
                    _ => {}
                },
            }
        }
        let off = o.span.start;
        if let Some(Expression::StringLiteral(k)) = kind.map(|k| k.get_inner_expression())
            && k.value == "OperationDefinition"
        {
            let op_kind = match operation.map(|e| e.get_inner_expression()) {
                Some(Expression::StringLiteral(s)) => procedure_method(s.value.as_str()),
                _ => None,
            };
            // No name, or `void 0`, is an anonymous operation; anything else there can't be read.
            let (op_name, known) = match name.map(|e| e.get_inner_expression()) {
                None | Some(Expression::UnaryExpression(_) | Expression::NullLiteral(_)) => (None, true),
                Some(Expression::ObjectExpression(n)) => match compiled_name(n) {
                    Some(v) => (Some(v), true),
                    None => (None, false),
                },
                Some(_) => (None, false),
            };
            let row = match op_kind {
                Some(k) if known && !spread => Row { protocol: "graphql", kind: k, name: op_name, url: None, literal: true },
                _ => Row::unknown("graphql"),
            };
            self.api_row(row, "compiled-document", off);
            return;
        }
        if let Some(v) = operation_name
            && has_request_part
        {
            let read = if spread { None } else { self.render_value(v.get_inner_expression(), 0).filter(|(_, literal)| *literal) };
            let row = match read {
                Some((n, _)) => Row { protocol: "graphql", kind: "operation", name: Some(n), url: None, literal: true },
                None => Row::unknown("graphql"),
            };
            self.api_row(row, "request-body", off);
        }
    }

    /// Calls: a `gql(…)`, a router's definition, or a client asking for a procedure.
    pub(super) fn api_call(&mut self, call: &CallExpression<'_>) {
        let off = call.span.start;
        let Some(r) = self.expr_ref(&call.callee, 0) else {
            // `trpc[name].useQuery()`: a procedure, but which one is decided at run time.
            if let Expression::StaticMemberExpression(m) = call.callee.get_inner_expression()
                && api_ops::client_hook(m.property.name.as_str()).is_some()
                && matches!(m.object.get_inner_expression(), Expression::ComputedMemberExpression(_))
            {
                self.api_row(Row::unknown("trpc"), "client-call", off);
            }
            return;
        };
        let last = r.last().unwrap_or_default();
        if matches!(last, "gql" | "graphql") && call.arguments.len() == 1 {
            self.api_gql_call(call);
            return;
        }
        if last == "mergeRouters" {
            self.api_row(Row::unknown("trpc"), "router", off);
            return;
        }
        if self.client_call(&r, call, off) {
            return;
        }
        if !self.routers_read.contains(&off)
            && let Some(Expression::ObjectExpression(o)) = call.arguments.first().and_then(|a| a.as_expression()).map(|e| e.get_inner_expression())
        {
            // A name that says what this is may hold procedures we can't recognise on sight, and
            // `createTRPCRouter` is enough on its own; any other call needs a procedure to show it.
            let loose = matches!(last, "router" | "createRouter" | "createTRPCRouter");
            let mut read = RouterRead::default();
            self.read_router(o, "", loose, 0, &mut read);
            if read.definite > 0 || last == "createTRPCRouter" {
                self.routers_read.extend(read.nested);
                for row in read.rows {
                    let RouterRow { kind, name, literal, offset } = row;
                    self.api_row(Row { protocol: "trpc", kind, name, url: None, literal }, "router", offset);
                }
            }
        }
    }

    fn api_gql_call(&mut self, call: &CallExpression<'_>) {
        let Some(arg) = call.arguments.first().and_then(|a| a.as_expression()) else { return };
        let off = arg.span().start;
        match arg.get_inner_expression() {
            Expression::StringLiteral(s) => self.api_document(Some(s.value.as_str()), "gql-call", s.span.start),
            Expression::TemplateLiteral(t) => {
                let text = joined(t, &HOLE.to_string());
                self.api_document(text.as_deref(), "gql-call", t.span.start);
            }
            _ => self.api_row(Row::unknown("graphql"), "gql-call", off),
        }
    }

    /// `trpc.post.byId.useQuery(…)`, or `client.post.byId.query(…)` when the name says tRPC.
    fn client_call(&mut self, r: &Ref, call: &CallExpression<'_>, off: u32) -> bool {
        let last = r.last().unwrap_or_default();
        let hook = api_ops::client_hook(last);
        let root_says_trpc = r.segs.first().is_some_and(|s| s.to_ascii_lowercase().contains("trpc"));
        let Some(kind) = hook.or_else(|| if root_says_trpc { vanilla_call(last) } else { None }) else { return false };
        // Other libraries have hooks of these names, called directly or on their own objects.
        if r.module.as_deref().is_some_and(|m| m.contains("react-query") || m.contains("@reduxjs") || m == "urql" || m.contains("apollo")) {
            return false;
        }
        let Some((_, before)) = r.segs.split_last() else { return false };
        let path: &[String] = match r.module {
            // `require("x").post.list`: nothing here names the client object itself…
            Some(_) => match before.split_first() {
                // …unless it's the import's own name.
                Some((first, rest)) if matches!(first.as_str(), "default" | "trpc" | "api") => rest,
                _ => before,
            },
            None => before.split_first().map_or(&[], |(_, rest)| rest),
        };
        if path.is_empty() {
            // The oldest client: `trpc.useQuery(["post.byId", input])`.
            if !root_says_trpc || hook.is_none() {
                return false;
            }
            let name = match call.arguments.first().and_then(|a| a.as_expression()).map(|e| e.get_inner_expression()) {
                Some(Expression::ArrayExpression(a)) => {
                    a.elements.first().and_then(|e| e.as_expression()).and_then(|e| self.render_value(e, 0)).filter(|(_, l)| *l).map(|(v, _)| v)
                }
                _ => None,
            };
            let row = match name {
                Some(n) if api_ops::is_procedure_path(&n) => Row { protocol: "trpc", kind, name: Some(n), url: None, literal: true },
                _ => Row::unknown("trpc"),
            };
            self.api_row(row, "client-call", off);
            return true;
        }
        if path.iter().any(|s| s == "endpoints") {
            return false;
        }
        let row = if path.iter().any(|s| s.contains('(')) {
            Row::unknown("trpc")
        } else {
            Row { protocol: "trpc", kind, name: Some(path.join(".")), url: None, literal: true }
        };
        self.api_row(row, "client-call", off);
        true
    }

    fn read_router(&self, o: &ObjectExpression<'_>, prefix: &str, loose: bool, depth: usize, read: &mut RouterRead) {
        let unknown = |name: Option<String>, offset: u32| RouterRow { kind: "unknown", name, literal: false, offset };
        for p in &o.properties {
            if read.rows.len() >= MAX_ROUTER_ROWS {
                return;
            }
            let p = match p {
                ObjectPropertyKind::SpreadProperty(s) => {
                    read.rows.push(unknown(known_prefix(prefix), s.span.start));
                    continue;
                }
                ObjectPropertyKind::ObjectProperty(p) => p,
            };
            let off = p.span.start;
            let key = if p.computed && !matches!(p.key, PropertyKey::StringLiteral(_)) { None } else { p.key.static_name() };
            let value = p.value.get_inner_expression();
            let name = key.as_deref().map(|k| prefixed(prefix, k));
            if let Some(kind) = procedure_kind(value, loose) {
                read.definite += 1;
                match name {
                    Some(n) => read.rows.push(RouterRow { kind, name: Some(n), literal: true, offset: off }),
                    None => read.rows.push(unknown(known_prefix(prefix), off)),
                }
                continue;
            }
            let Some(name) = name else {
                read.rows.push(unknown(known_prefix(prefix), off));
                continue;
            };
            let nested = match value {
                Expression::ObjectExpression(inner) => Some((inner, loose, None)),
                Expression::CallExpression(c) => match c.arguments.first().and_then(|a| a.as_expression()).map(|e| e.get_inner_expression()) {
                    Some(Expression::ObjectExpression(inner)) => {
                        let callee = self.expr_ref(&c.callee, 0);
                        let last = callee.as_ref().and_then(Ref::last).unwrap_or_default();
                        Some((inner, loose || matches!(last, "router" | "createRouter" | "createTRPCRouter"), Some(c.span.start)))
                    }
                    _ => None,
                },
                _ => None,
            };
            match nested {
                Some((inner, inner_loose, call_at)) if depth < MAX_ROUTER_DEPTH => {
                    let mut sub = RouterRead::default();
                    self.read_router(inner, &name, inner_loose, depth + 1, &mut sub);
                    if sub.definite > 0 {
                        read.definite += sub.definite;
                        read.rows.append(&mut sub.rows);
                        read.nested.append(&mut sub.nested);
                        read.nested.extend(call_at);
                    } else {
                        read.rows.push(unknown(Some(name), off));
                    }
                }
                // Another router by name (`post: postRouter`), or something else: what's under
                // this key can't be read from here.
                _ => read.rows.push(unknown(Some(name), off)),
            }
        }
    }

    /// Endpoints whose URLs were only partly literal: seen here, and not as one string.
    pub(super) fn api_finish(&mut self) {
        let urls: Vec<(String, u32)> = self.facts.endpoints.iter().map(|e| (e.url.clone(), e.offset)).collect();
        for (url, off) in urls {
            let rows = api_ops::url_rows(&url);
            self.api_rows(rows, "url", off);
        }
    }
}

fn compiled_name(n: &ObjectExpression<'_>) -> Option<String> {
    let mut value = None;
    for p in &n.properties {
        match p {
            ObjectPropertyKind::SpreadProperty(_) => return None,
            ObjectPropertyKind::ObjectProperty(p) if p.key.static_name().as_deref() == Some("value") => value = Some(&p.value),
            ObjectPropertyKind::ObjectProperty(_) => {}
        }
    }
    match value?.get_inner_expression() {
        Expression::StringLiteral(s) => Some(s.value.to_string()),
        _ => None,
    }
}

/// The kind of procedure this expression defines: `….query(handler)` on a chain that shows it's a
/// procedure builder, or on anything when the surrounding call was named as a router.
fn procedure_kind(e: &Expression<'_>, loose: bool) -> Option<&'static str> {
    let Expression::CallExpression(c) = e else { return None };
    let Expression::StaticMemberExpression(m) = c.callee.get_inner_expression() else { return None };
    let kind = procedure_method(m.property.name.as_str())?;
    if c.arguments.len() != 1 {
        return None;
    }
    let arg = c.arguments.first()?.as_expression()?.get_inner_expression();
    if !(is_function_like(arg) || matches!(arg, Expression::Identifier(_) | Expression::StaticMemberExpression(_))) {
        return None;
    }
    if loose {
        return Some(kind);
    }
    let mentions = |s: &str| s.to_ascii_lowercase().contains("procedure");
    let mut cur = m.object.get_inner_expression();
    for _ in 0..MAX_CHAIN {
        match cur {
            Expression::CallExpression(inner) => match inner.callee.get_inner_expression() {
                Expression::StaticMemberExpression(step) => {
                    let n = step.property.name.as_str();
                    if matches!(n, "input" | "output" | "use" | "meta" | "concat" | "unstable_concat") || mentions(n) {
                        return Some(kind);
                    }
                    cur = step.object.get_inner_expression();
                }
                Expression::Identifier(id) => return mentions(id.name.as_str()).then_some(kind),
                _ => return None,
            },
            Expression::StaticMemberExpression(step) => {
                if mentions(step.property.name.as_str()) {
                    return Some(kind);
                }
                cur = step.object.get_inner_expression();
            }
            Expression::Identifier(id) => return mentions(id.name.as_str()).then_some(kind),
            _ => return None,
        }
    }
    None
}
