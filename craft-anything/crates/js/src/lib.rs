//! JavaScript, Electron and web-bundle analysis for Craft Anything.
//!
//! Everything here is static and runs nothing: sources are parsed (with oxc, a pure-Rust
//! parser) or, when parsing is refused or fails, tokenized; facts are read from the result.
//! The parser recurses without a depth limit, so we estimate nesting first and hand very deep
//! sources to the token scanner instead. On native targets parsing runs on a worker thread with
//! a large stack, which also contains any parser panic.
#![deny(clippy::unwrap_used, clippy::expect_used, clippy::panic, clippy::unimplemented, clippy::todo, clippy::unreachable)]

pub mod api_ops;
mod bundle;
mod facts;
mod fallback;
mod fingerprint;
pub mod html;
pub mod lex;
pub mod model;
pub mod recover;
pub mod util;
pub mod vendor;

pub use model::*;

use oxc_allocator::Allocator;
use oxc_ast_visit::Visit;
use oxc_parser::{ParseOptions, Parser};
use oxc_span::SourceType;
use std::sync::Arc;

/// Bounds for one source.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Limits {
    /// Sources larger than this are token-scanned instead of parsed.
    pub max_parse_bytes: usize,
    /// Sources whose estimated nesting exceeds this are token-scanned instead of parsed.
    pub max_nesting: usize,
    /// Most tokens the scanner produces.
    pub max_tokens: usize,
}

#[cfg(not(target_arch = "wasm32"))]
const DEFAULT_NESTING: usize = 4096;
#[cfg(target_arch = "wasm32")]
const DEFAULT_NESTING: usize = 160;

/// Stack for the parser thread. Virtual reservation only; pages are touched as needed.
#[cfg(not(target_arch = "wasm32"))]
const PARSE_STACK: usize = 256 * 1024 * 1024;

impl Default for Limits {
    fn default() -> Self {
        Limits { max_parse_bytes: 32 * 1024 * 1024, max_nesting: DEFAULT_NESTING, max_tokens: 20_000_000 }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum JsError {
    #[error("{0}")]
    Refused(String),
    #[error("the JavaScript parser failed: {0}")]
    Parser(String),
}

/// Run `f` where a deep recursion can't take the process down and a panic is contained.
#[cfg(not(target_arch = "wasm32"))]
pub(crate) fn guarded<T: Send + 'static>(f: impl FnOnce() -> T + Send + 'static) -> Result<T, JsError> {
    let handle = std::thread::Builder::new()
        .name("craft-js-parse".into())
        .stack_size(PARSE_STACK)
        .spawn(f)
        .map_err(|e| JsError::Parser(format!("could not start a parser thread: {e}")))?;
    handle.join().map_err(|_| JsError::Parser("the parser stopped unexpectedly on this input".into()))
}

#[cfg(target_arch = "wasm32")]
pub(crate) fn guarded<T: Send + 'static>(f: impl FnOnce() -> T + Send + 'static) -> Result<T, JsError> {
    Ok(f())
}

/// Pick a source type from the file name.
pub fn source_type_for(path: &str) -> SourceType {
    let lower = path.to_ascii_lowercase();
    if lower.ends_with(".tsx") {
        SourceType::tsx()
    } else if lower.ends_with(".ts") || lower.ends_with(".mts") || lower.ends_with(".cts") {
        SourceType::ts()
    } else if lower.ends_with(".mjs") {
        SourceType::mjs().with_jsx(false)
    } else if lower.ends_with(".cjs") {
        SourceType::cjs()
    } else {
        SourceType::unambiguous().with_jsx(true)
    }
}

pub(crate) fn parse_options() -> ParseOptions {
    ParseOptions { allow_return_outside_function: true, ..ParseOptions::default() }
}

/// The result of analysing one source.
#[derive(Debug, Clone, Default, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub struct Analysis {
    pub facts: ModuleFacts,
    pub bundle: BundleInfo,
}

/// Decide whether a source may go to the parser. `Err(reason)` means "token-scan it instead".
pub fn admit(src: &str, limits: &Limits) -> Result<(), String> {
    if src.len() > limits.max_parse_bytes {
        return Err(format!("{} bytes is over the {}-byte parse limit", src.len(), limits.max_parse_bytes));
    }
    let mut nesting = lex::Nesting::default();
    let truncated = lex::scan(src, limits.max_tokens, |t| nesting.feed(&t));
    if truncated {
        return Err(format!("more than {} tokens", limits.max_tokens));
    }
    let depth = nesting.max;
    if depth > limits.max_nesting {
        return Err(format!("nests about {depth} levels deep (limit {})", limits.max_nesting));
    }
    Ok(())
}

/// Analyse one JavaScript/TypeScript source. Never fails: when parsing is refused or fails the
/// facts come from the token scanner and say so (`mode: lexer`, `mode_reason`).
pub fn analyze(path: &str, src: &str, limits: &Limits) -> Analysis {
    let lines = util::LineIndex::new(src);
    let mut analysis = match admit(src, limits) {
        Err(reason) => lexer_analysis(src, &lines, limits, reason),
        Ok(()) => {
            let owned: Arc<str> = Arc::from(src);
            let st = source_type_for(path);
            match guarded(move || parse_and_visit(&owned, st)) {
                Ok(Some(a)) => a,
                Ok(None) => lexer_analysis(src, &lines, limits, "the source has a syntax error the parser could not recover from".into()),
                Err(e) => lexer_analysis(src, &lines, limits, e.to_string()),
            }
        }
    };
    let f = &mut analysis.facts;
    f.bytes = src.len();
    f.lines = lines.count();
    if f.source_map_url.is_none() {
        f.source_map_url = find_map_url(src);
    }
    for v in vendor::marker_vendors(&f.strings) {
        if !f.vendors.iter().any(|x| x.name == v.name) {
            f.vendors.push(v);
        }
    }
    analysis.bundle.bundlers = bundle::classify(&f.bundler_markers, &analysis.bundle, &f.strings);
    analysis
}

fn find_map_url(src: &str) -> Option<String> {
    // Only the tail: the comment must be the last thing in the file to count.
    let mut start = src.len().saturating_sub(4096);
    while !src.is_char_boundary(start) {
        start += 1;
    }
    let tail = src.get(start..).unwrap_or("");
    for line in tail.lines().rev().take(8) {
        let t = line.trim();
        for p in ["//# sourceMappingURL=", "//@ sourceMappingURL=", "/*# sourceMappingURL="] {
            if let Some(u) = t.strip_prefix(p) {
                let u = u.trim_end_matches("*/").trim();
                if !u.is_empty() {
                    return Some(u.chars().take(4096).collect());
                }
            }
        }
    }
    None
}

/// Most tokens the fallback keeps in memory at once.
const FALLBACK_TOKENS: usize = 4_000_000;

fn lexer_analysis(src: &str, lines: &util::LineIndex, limits: &Limits, mut reason: String) -> Analysis {
    let (tokens, cut) = lex::tokenize(src, limits.max_tokens.min(FALLBACK_TOKENS));
    if cut {
        reason.push_str(&format!("; only the first {} tokens were scanned", FALLBACK_TOKENS.min(limits.max_tokens)));
    }
    let mut facts = fallback::facts_from_tokens(&tokens, lines);
    facts.mode_reason = Some(reason);
    facts.source_kind = "unknown".into();
    for t in tokens.iter().filter(|t| t.kind == lex::TokKind::Comment).take(10_000) {
        if facts.vendors.len() >= 256 {
            break;
        }
        let line = lines.line(u32::try_from(t.offset).unwrap_or(u32::MAX));
        if let Some(v) = vendor::banner_vendor(t.text, line) {
            facts.vendors.push(v);
        }
    }
    Analysis { facts, bundle: BundleInfo::default() }
}

/// Sources larger than this skip scope analysis (aliases then follow names).
const SEMANTIC_MAX_BYTES: usize = 16 * 1024 * 1024;

fn parse_and_visit(src: &str, st: SourceType) -> Option<Analysis> {
    let alloc = Allocator::default();
    let ret = Parser::new(&alloc, src, st).with_options(parse_options()).parse();
    if ret.fatal_error {
        return None;
    }
    let lines = util::LineIndex::new(src);
    // Scope analysis makes alias tracking follow bindings (minified code reuses short names).
    let semantic = (src.len() <= SEMANTIC_MAX_BYTES).then(|| oxc_semantic::SemanticBuilder::new().build(&ret.program));
    let scoping = semantic.as_ref().map(|s| s.semantic.scoping());
    let mut v = facts::FactVisitor::new(src, &lines, scoping);
    v.visit_program(&ret.program);
    v.finish();
    let mut facts = v.facts;
    facts.parse_errors = ret.diagnostics.errors().count();
    if facts.parse_errors > 0 {
        facts.mode = ParseMode::ParsedWithErrors;
        facts.mode_reason = ret.diagnostics.errors().next().map(|e| e.to_string().chars().take(300).collect());
    }
    for c in ret.program.comments.iter().take(20_000) {
        if facts.vendors.len() >= 256 {
            break;
        }
        let text = util::slice(src, c.span.start, c.span.end);
        if let Some(v) = vendor::banner_vendor(text, lines.line(c.span.start)) {
            facts.vendors.push(v);
        }
    }
    let mut fp = fingerprint::Fingerprint::new();
    fp.visit_program(&ret.program);
    facts.fingerprint = Some(fp.finish());
    let webpack_hint = facts.bundler_markers.keys().any(|k| k.contains("webpack"));
    let mut bv = bundle::BundleVisitor::new(src, &lines, webpack_hint, scoping);
    bv.visit_program(&ret.program);
    let bundle = bv.finish();
    Some(Analysis { facts, bundle })
}

#[cfg(test)]
mod tests;
