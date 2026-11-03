//! Reading GraphQL documents and tRPC URLs from text. No parser and no I/O: the syntax-tree pass and
//! the token scan both hand their strings here, so they recognise the same things.
//!
//! All of this is inference from how code is written. A piece of text the program fills in at run
//! time is an unknown, never a guess: see [`HOLE`].

use crate::model::ApiOperation;

/// Stands for text only known at run time, where a document was built with `${…}`.
pub const HOLE: char = '\u{1}';

/// Most operations read from one document.
const MAX_DOC_OPERATIONS: usize = 64;
/// Longest document read, in bytes.
pub const MAX_DOCUMENT_BYTES: usize = 1024 * 1024;
const MAX_URL_BYTES: usize = 2048;

/// One operation found in a document. `name` is `None` for an anonymous operation and for one whose
/// name was only known at run time (`literal` false tells them apart).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DocOperation {
    pub kind: &'static str,
    pub name: Option<String>,
    pub literal: bool,
}

/// What a document held.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Document {
    pub operations: Vec<DocOperation>,
    /// Run-time text sits between definitions, so it may add operations nobody can see here.
    pub open_ended: bool,
}

fn is_name_start(c: char) -> bool {
    c.is_ascii_alphabetic() || c == '_'
}

fn is_name_char(c: char) -> bool {
    c.is_ascii_alphanumeric() || c == '_'
}

/// Read the definitions of a GraphQL document. `None` when the text isn't one: it must start with a
/// definition, and its brackets and strings must close. Fragments count as definitions but aren't
/// operations. `{ a }` is valid GraphQL, but also plenty of other things, so it counts only when
/// `allow_shorthand` says the context already proved this is a document.
pub fn read_document(text: &str, allow_shorthand: bool) -> Option<Document> {
    if text.len() > MAX_DOCUMENT_BYTES {
        return None;
    }
    let mut doc = Document::default();
    let mut chars = text.char_indices().peekable();
    let mut definitions = 0usize;
    loop {
        // Between definitions.
        let mut hole_here = false;
        while let Some(&(_, c)) = chars.peek() {
            if c == HOLE {
                hole_here = true;
                chars.next();
            } else if c == '#' {
                for (_, c) in chars.by_ref() {
                    if c == '\n' || c == '\r' {
                        break;
                    }
                }
            } else if c.is_whitespace() || c == ',' || c == '\u{feff}' {
                chars.next();
            } else {
                break;
            }
        }
        if hole_here {
            doc.open_ended = true;
        }
        let Some(&(start, first)) = chars.peek() else { break };
        let (kind, is_operation) = if first == '{' {
            if !allow_shorthand {
                return None;
            }
            ("query", true)
        } else if is_name_start(first) {
            let mut end = start;
            while let Some(&(i, c)) = chars.peek() {
                if !is_name_char(c) {
                    break;
                }
                end = i + c.len_utf8();
                chars.next();
            }
            match text.get(start..end)? {
                "query" => ("query", true),
                "mutation" => ("mutation", true),
                "subscription" => ("subscription", true),
                "fragment" => ("fragment", false),
                // Type definitions and the like are GraphQL too, but say nothing a client calls.
                "type" | "schema" | "extend" | "input" | "interface" | "union" | "enum" | "scalar" | "directive" => ("other", false),
                _ => return None,
            }
        } else {
            return None;
        };

        // The header, up to the selection set.
        let mut name: Option<String> = None;
        let mut name_is_hole = false;
        let mut saw_anything = false;
        let mut parens = 0usize;
        while let Some(&(i, c)) = chars.peek() {
            if c == '{' && parens == 0 {
                break;
            }
            match c {
                '(' => parens += 1,
                ')' => parens = parens.checked_sub(1)?,
                HOLE if !saw_anything => name_is_hole = true,
                '"' => {
                    skip_string(&mut chars, text)?;
                    saw_anything = true;
                    continue;
                }
                _ => {}
            }
            if !saw_anything && is_name_start(c) && is_operation {
                let mut end = i;
                while let Some(&(j, d)) = chars.peek() {
                    if !is_name_char(d) {
                        break;
                    }
                    end = j + d.len_utf8();
                    chars.next();
                }
                name = text.get(i..end).map(String::from);
                saw_anything = true;
                // A name running straight into run-time text isn't all of the name.
                if chars.peek().is_some_and(|&(_, d)| d == HOLE) {
                    name = None;
                    name_is_hole = true;
                }
                continue;
            }
            if !c.is_whitespace() {
                saw_anything = true;
            }
            chars.next();
        }
        // The selection set: it must close, and must select something.
        chars.peek().filter(|&&(_, c)| c == '{')?;
        let mut depth = 0usize;
        let mut selected = false;
        let mut closed = false;
        while let Some(&(_, c)) = chars.peek() {
            match c {
                '{' => depth = depth.checked_add(1)?,
                '}' => {
                    depth = depth.checked_sub(1)?;
                    if depth == 0 {
                        chars.next();
                        closed = true;
                        break;
                    }
                }
                '"' => {
                    skip_string(&mut chars, text)?;
                    continue;
                }
                '#' => {
                    for (_, d) in chars.by_ref() {
                        if d == '\n' || d == '\r' {
                            break;
                        }
                    }
                    continue;
                }
                c if is_name_start(c) || c == HOLE => selected = true,
                _ => {}
            }
            chars.next();
        }
        if !closed || !selected {
            return None;
        }
        definitions += 1;
        if is_operation && doc.operations.len() < MAX_DOC_OPERATIONS {
            doc.operations.push(DocOperation { kind, literal: !name_is_hole, name: if name_is_hole { None } else { name } });
        }
    }
    (definitions > 0 || (allow_shorthand && doc.open_ended)).then_some(doc)
}

/// Step over a `"…"` or `"""…"""` string, leaving the iterator after it. `None` if it never closes.
fn skip_string(chars: &mut std::iter::Peekable<std::str::CharIndices<'_>>, text: &str) -> Option<()> {
    let (start, _) = chars.next()?;
    if text.get(start..start + 3) == Some("\"\"\"") {
        chars.next();
        chars.next();
        let mut quotes = 0;
        for (_, c) in chars.by_ref() {
            quotes = if c == '"' { quotes + 1 } else { 0 };
            if quotes == 3 {
                return Some(());
            }
        }
        return None;
    }
    let mut escaped = false;
    for (_, c) in chars.by_ref() {
        match c {
            _ if escaped => escaped = false,
            '\\' => escaped = true,
            '"' => return Some(()),
            '\n' => return None,
            _ => {}
        }
    }
    None
}

/// Where a document may start, after the whitespace, commas, byte-order mark and `#` comments
/// that may come first (the non-run-time part of the trivia [`read_document`] skips).
fn document_start(text: &str) -> &str {
    let mut rest = text;
    loop {
        let trimmed = rest.trim_start_matches(|c: char| c.is_whitespace() || c == ',' || c == '\u{feff}');
        let Some(after) = trimmed.strip_prefix('#') else { return trimmed };
        rest = after.find(['\n', '\r']).and_then(|i| after.get(i + 1..)).unwrap_or("");
    }
}

/// Could this text be a whole document? A quick test before the real read, on every string.
/// A document may begin with a comment, as a generated client often writes one.
pub fn may_be_document(text: &str) -> bool {
    let t = document_start(text);
    (t.starts_with("query") || t.starts_with("mutation") || t.starts_with("subscription") || t.starts_with("fragment")) && t.contains('{')
}

/// What a URL says about an API, as `(protocol, procedures)`: a GraphQL endpoint, or a tRPC one with
/// the procedures named in its path. `None` when it's neither. A procedure part with run-time text
/// in it comes back as `None`, because only part of its name is known; `holes` are the marks a
/// partly literal URL uses for that text (`{…}`).
pub fn url_api(url: &str) -> Option<UrlApi> {
    let without_scheme = url.split_once("://").map_or(url, |(_, r)| r.split_once('/').map_or("", |(_, p)| p));
    let is_relative_or_absolute = url.contains("://") || url.starts_with('/');
    if !is_relative_or_absolute {
        return None;
    }
    let path = without_scheme.split(['?', '#']).next().unwrap_or_default();
    let segs: Vec<&str> = path.split('/').filter(|s| !s.is_empty()).collect();
    if let Some(i) = segs.iter().position(|s| *s == "trpc") {
        let rest: Vec<&str> = segs.iter().skip(i + 1).copied().collect();
        return Some(match rest.as_slice() {
            [] => UrlApi::Trpc { procedures: Vec::new() },
            [one] => UrlApi::Trpc { procedures: one.split(',').take(MAX_DOC_OPERATIONS).map(|p| (is_procedure_path(p)).then(|| p.to_string())).collect() },
            // tRPC paths are dotted, so a further slash isn't one of its URLs as far as we can read.
            _ => UrlApi::Trpc { procedures: vec![None] },
        });
    }
    (segs.last().is_some_and(|s| *s == "graphql" || *s == "gql")).then_some(UrlApi::Graphql)
}

/// What [`url_api`] found.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum UrlApi {
    Graphql,
    /// Empty for the endpoint itself; `None` for a procedure whose name isn't fully known.
    Trpc {
        procedures: Vec<Option<String>>,
    },
}

/// `post.byId`: dotted names, nothing else.
pub fn is_procedure_path(p: &str) -> bool {
    !p.is_empty()
        && p.len() <= 200
        && p.split('.').all(|part| {
            part.chars().next().is_some_and(|c| c.is_ascii_alphabetic() || c == '_' || c == '$')
                && part.chars().all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '$' || c == '-')
        })
}

/// A row before it has a place in the source.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct Row {
    pub protocol: &'static str,
    pub kind: &'static str,
    pub name: Option<String>,
    pub url: Option<String>,
    pub literal: bool,
}

impl Row {
    /// Something of this protocol is here, but what it is depends on the run.
    pub fn unknown(protocol: &'static str) -> Row {
        Row { protocol, kind: "unknown", name: None, url: None, literal: false }
    }
}

/// The rows a document gives. Run-time text between definitions adds an unknown one, because it may
/// hold operations of its own.
pub(crate) fn document_rows(doc: &Document) -> Vec<Row> {
    let mut rows: Vec<Row> = doc
        .operations
        .iter()
        .map(|o| {
            if o.literal {
                Row { protocol: "graphql", kind: o.kind, name: o.name.clone(), url: None, literal: true }
            } else {
                Row { kind: o.kind, ..Row::unknown("graphql") }
            }
        })
        .collect();
    if doc.open_ended {
        rows.push(Row::unknown("graphql"));
    }
    rows
}

/// The rows a URL gives.
pub(crate) fn url_rows(url: &str) -> Vec<Row> {
    if url.len() > MAX_URL_BYTES || !(url.contains("graphql") || url.contains("gql") || url.contains("trpc")) {
        return Vec::new();
    }
    let literal = !url.contains('{');
    let at = || Some(url.to_string());
    match url_api(url) {
        Some(UrlApi::Graphql) => vec![Row { protocol: "graphql", kind: "endpoint", name: None, url: at(), literal }],
        Some(UrlApi::Trpc { procedures }) if procedures.is_empty() => vec![Row { protocol: "trpc", kind: "endpoint", name: None, url: at(), literal }],
        Some(UrlApi::Trpc { procedures }) => procedures
            .into_iter()
            .map(|p| match p {
                Some(n) => Row { protocol: "trpc", kind: "operation", name: Some(n), url: at(), literal },
                None => Row { url: at(), ..Row::unknown("trpc") },
            })
            .collect(),
        None => Vec::new(),
    }
}

/// The rows a whole string gives: it may be a document, or a URL.
pub(crate) fn text_rows(text: &str) -> Vec<Row> {
    if may_be_document(text)
        && let Some(doc) = read_document(text, false)
    {
        return document_rows(&doc);
    }
    url_rows(text)
}

/// The kind a client hook asks for: `useQuery` and its relatives, on a procedure's path.
pub fn client_hook(name: &str) -> Option<&'static str> {
    match name {
        "useQuery" | "useSuspenseQuery" | "useInfiniteQuery" | "useSuspenseInfiniteQuery" | "usePrefetchQuery" => Some("query"),
        "useMutation" => Some("mutation"),
        "useSubscription" => Some("subscription"),
        _ => None,
    }
}

/// Adds a row and says whether the list had room. A row is a repeat if it's the same thing at the same
/// place; a URL is the same thing wherever it's written.
pub(crate) fn push_operation(list: &mut Vec<ApiOperation>, op: ApiOperation, cap: usize) -> bool {
    if list
        .iter()
        .any(|o| o.protocol == op.protocol && o.kind == op.kind && o.name == op.name && o.url == op.url && (op.url.is_some() || o.offset == op.offset))
    {
        return true;
    }
    if list.len() >= cap {
        return false;
    }
    list.push(op);
    true
}

#[cfg(test)]
mod tests {
    use super::*;

    fn names(text: &str) -> Vec<(&'static str, Option<String>, bool)> {
        read_document(text, false).unwrap().operations.into_iter().map(|o| (o.kind, o.name, o.literal)).collect()
    }

    #[test]
    fn reads_named_operations_with_variables_directives_and_fragments() {
        assert_eq!(names("query GetUser($id: ID!) { user(id: $id) { name } }"), [("query", Some("GetUser".to_string()), true)]);
        assert_eq!(names("mutation M{a}"), [("mutation", Some("M".to_string()), true)]);
        assert_eq!(names("subscription S @live { a }"), [("subscription", Some("S".to_string()), true)]);
        assert_eq!(
            names("# leading\nfragment F on U { id }\nquery A { ...F }\nmutation B($x: String = \"}\") { b(x: $x) }"),
            [("query", Some("A".to_string()), true), ("mutation", Some("B".to_string()), true)]
        );
        assert_eq!(names("query { a }"), [("query", None, true)], "anonymous is known to be anonymous");
        assert_eq!(names("query($a: Int) { a }"), [("query", None, true)]);
    }

    #[test]
    fn text_that_only_looks_like_a_document_is_not_one() {
        for t in [
            "query the database for results",
            "mutation",
            "query {",
            "query { }",
            "query Foo",
            "{ a }",
            "queryFoo { a }",
            "mutations happen { often",
            "select * from t where {x}",
            "query Foo { a } trailing words",
            "query Foo(a: \"never closed) { a }",
            "}{",
            "",
            "query )( { a }",
        ] {
            assert!(read_document(t, false).is_none(), "{t}");
        }
        assert_eq!(read_document("{ a }", true).unwrap().operations.len(), 1, "a gql tag has already said it's a document");
    }

    #[test]
    fn run_time_text_makes_a_name_unknown_not_guessed() {
        let h = HOLE;
        assert_eq!(names(&format!("query {h} {{ a }}")), [("query", None, false)]);
        assert_eq!(names(&format!("query Get{h} {{ a }}")), [("query", None, false)], "only part of the name is known");
        let d = read_document(&format!("query A {{ ...F }} {h}"), false).unwrap();
        assert!(d.open_ended, "a fragment or another operation may be in there");
        assert_eq!(d.operations.len(), 1);
        assert!(!read_document("query A { a }", false).unwrap().open_ended);
        assert_eq!(names(&format!("query A {{ {h} }}")), [("query", Some("A".to_string()), true)], "run-time fields don't change the name");
        let only = read_document(&format!("{h}"), true).unwrap();
        assert!(only.operations.is_empty() && only.open_ended);
        assert!(read_document(&format!("{h}"), false).is_none());
    }

    #[test]
    fn a_document_may_begin_with_a_comment() {
        assert!(may_be_document("# note\nquery Q { a }"));
        assert!(may_be_document("  # one\n# two\nmutation M { a }"));
        assert!(may_be_document("# note\r\nquery Q { a }"));
        assert!(may_be_document("# note\rquery Q { a }"), "a lone CR ends a comment too");
        assert_eq!(read_document("# note\rquery Q { a }", false).and_then(|d| d.operations.first().and_then(|o| o.name.clone())).as_deref(), Some("Q"));
        assert!(may_be_document("\u{feff}# c\n, query Q { a }"));
        assert!(!may_be_document("# note\nconst a = { b: 1 }"));
        assert!(!may_be_document("# only a comment"));
        assert!(!may_be_document("# query Q { a }"), "no newline means the whole text is the comment");
        let doc = read_document("query Q { a # note\r b }", false).expect("a comment in a selection set ends at a lone CR");
        assert_eq!(doc.operations.first().and_then(|o| o.name.as_deref()), Some("Q"));
    }

    #[test]
    fn hostile_documents_are_bounded() {
        assert!(read_document(&"{".repeat(100_000), true).is_none());
        assert!(read_document(&"query ".repeat(100_000), false).is_none());
        assert!(read_document(&format!("query A {{ {} }}", "a ".repeat(MAX_DOCUMENT_BYTES)), false).is_none());
        let many: String = (0..1000).map(|i| format!("query Q{i} {{ a }}\n")).collect();
        assert_eq!(read_document(&many, false).unwrap().operations.len(), MAX_DOC_OPERATIONS);
        assert!(read_document("query A { \"é", false).is_none());
        assert!(read_document("é", false).is_none());
    }

    #[test]
    fn urls() {
        assert_eq!(url_api("/graphql"), Some(UrlApi::Graphql));
        assert_eq!(url_api("https://api.example.test/v1/graphql?x=1"), Some(UrlApi::Graphql));
        assert_eq!(url_api("/api/gql"), Some(UrlApi::Graphql));
        assert_eq!(url_api("/docs/graphql/intro"), None);
        assert_eq!(url_api("graphql"), None, "a word, not a URL");
        assert_eq!(url_api("/api/graphql-tools"), None);
        assert_eq!(url_api("/api/trpc"), Some(UrlApi::Trpc { procedures: vec![] }));
        assert_eq!(url_api("/api/trpc/post.byId?input=1"), Some(UrlApi::Trpc { procedures: vec![Some("post.byId".into())] }));
        assert_eq!(url_api("https://x.test/trpc/a.b,c.d?batch=1"), Some(UrlApi::Trpc { procedures: vec![Some("a.b".into()), Some("c.d".into())] }));
        assert_eq!(url_api("/trpc/{path}"), Some(UrlApi::Trpc { procedures: vec![None] }));
        assert_eq!(url_api("/trpc/post.{x}"), Some(UrlApi::Trpc { procedures: vec![None] }));
        assert_eq!(url_api("/api/users"), None);
        assert_eq!(url_api("https://trpc.io/docs"), None, "the host isn't the path");
    }
}
