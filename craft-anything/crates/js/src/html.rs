//! HTML pages: script references, inline scripts, module preloads and the Content Security Policy.
//! A tolerant tag scanner, not a full HTML parser.

use serde::{Deserialize, Serialize};

const MAX_TAGS: usize = 2_000;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct HtmlScript {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub src: Option<String>,
    pub module: bool,
    /// Byte range of inline script text.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub inline: Option<(u32, u32)>,
    pub line: u32,
}

#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct HtmlFacts {
    pub scripts: Vec<HtmlScript>,
    pub preloads: Vec<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub csp: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub title: Option<String>,
}

/// Attributes of the tag starting at `start` (just after the tag name). Returns (attrs, end of tag).
fn attributes(src: &str, lower: &str, mut i: usize) -> (Vec<(String, String)>, usize) {
    let b = lower.as_bytes();
    let mut out = Vec::new();
    while i < b.len() && out.len() < 64 {
        while b.get(i).is_some_and(|c| c.is_ascii_whitespace() || *c == b'/') {
            i += 1;
        }
        match b.get(i) {
            None => break,
            Some(b'>') => return (out, i + 1),
            _ => {}
        }
        let ns = i;
        while b.get(i).is_some_and(|c| !c.is_ascii_whitespace() && *c != b'=' && *c != b'>') {
            i += 1;
        }
        let name = lower.get(ns..i).unwrap_or("").to_string();
        while b.get(i).is_some_and(u8::is_ascii_whitespace) {
            i += 1;
        }
        let mut value = String::new();
        if b.get(i) == Some(&b'=') {
            i += 1;
            while b.get(i).is_some_and(u8::is_ascii_whitespace) {
                i += 1;
            }
            match b.get(i) {
                Some(q @ (b'"' | b'\'')) => {
                    let q = *q;
                    let vs = i + 1;
                    i = vs;
                    while b.get(i).is_some_and(|c| *c != q) {
                        i += 1;
                    }
                    value = src.get(vs..i).unwrap_or("").to_string();
                    i += 1;
                }
                _ => {
                    let vs = i;
                    while b.get(i).is_some_and(|c| !c.is_ascii_whitespace() && *c != b'>') {
                        i += 1;
                    }
                    value = src.get(vs..i).unwrap_or("").to_string();
                }
            }
        }
        if name.is_empty() {
            i += 1;
        } else {
            out.push((name, decode_entities(&value)));
        }
    }
    (out, i.min(b.len()))
}

fn decode_entities(s: &str) -> String {
    s.replace("&amp;", "&").replace("&quot;", "\"").replace("&#39;", "'").replace("&lt;", "<").replace("&gt;", ">")
}

fn get<'v>(attrs: &'v [(String, String)], k: &str) -> Option<&'v str> {
    attrs.iter().find(|(n, _)| n == k).map(|(_, v)| v.as_str())
}

/// Scan an HTML document.
pub fn scan_html(src: &str) -> HtmlFacts {
    let lower = src.to_ascii_lowercase();
    let lines = crate::util::LineIndex::new(src);
    let mut out = HtmlFacts::default();
    let mut pos = 0usize;
    let mut tags = 0usize;
    while let Some(rel) = lower.get(pos..).and_then(|r| r.find('<')) {
        tags += 1;
        if tags > MAX_TAGS * 50 || out.scripts.len() >= MAX_TAGS {
            break;
        }
        let at = pos + rel;
        let rest = lower.get(at + 1..).unwrap_or("");
        let name_len = rest.bytes().take_while(|c| c.is_ascii_alphanumeric() || *c == b'-').count();
        let name = rest.get(..name_len).unwrap_or("");
        let after = at + 1 + name_len;
        match name {
            "script" => {
                let (attrs, end) = attributes(src, &lower, after);
                let close = lower.get(end..).and_then(|r| r.find("</script")).map_or(lower.len(), |c| end + c);
                let module = get(&attrs, "type").is_some_and(|t| t.eq_ignore_ascii_case("module"));
                let line = lines.line(u32::try_from(at).unwrap_or(u32::MAX));
                let src_attr = get(&attrs, "src").map(String::from);
                let js = javascript_type(get(&attrs, "type"));
                let inline = (src_attr.is_none() && close > end && js && src.get(end..close).is_some_and(|t| !t.trim().is_empty()))
                    .then(|| (u32::try_from(end).unwrap_or(u32::MAX), u32::try_from(close).unwrap_or(u32::MAX)));
                if js && (src_attr.is_some() || inline.is_some()) {
                    out.scripts.push(HtmlScript { src: src_attr, module, inline, line });
                }
                pos = close.max(end).max(at + 1);
            }
            "link" => {
                let (attrs, end) = attributes(src, &lower, after);
                let rel_attr = get(&attrs, "rel").unwrap_or("").to_ascii_lowercase();
                if (rel_attr == "modulepreload" || (rel_attr == "preload" && get(&attrs, "as") == Some("script")))
                    && let Some(h) = get(&attrs, "href")
                    && out.preloads.len() < MAX_TAGS
                {
                    out.preloads.push(h.to_string());
                }
                pos = end.max(at + 1);
            }
            "meta" => {
                let (attrs, end) = attributes(src, &lower, after);
                if get(&attrs, "http-equiv").is_some_and(|h| h.eq_ignore_ascii_case("content-security-policy")) {
                    out.csp = get(&attrs, "content").map(String::from);
                }
                pos = end.max(at + 1);
            }
            "title" => {
                let (_, end) = attributes(src, &lower, after);
                let close = lower.get(end..).and_then(|r| r.find("</title")).map_or(end, |c| end + c);
                out.title = src.get(end..close).map(|t| t.trim().chars().take(200).collect());
                pos = close.max(at + 1);
            }
            _ if rest.starts_with("!--") => {
                pos = lower.get(at..).and_then(|r| r.find("-->")).map_or(lower.len(), |c| at + c + 3);
            }
            _ => pos = at + 1,
        }
    }
    out
}

/// Whether a `<script type>` is code the page runs: no type, a JavaScript MIME type or `module`
/// (and JSX for in-browser Babel, which is code too). Import maps, speculation rules and data
/// blocks such as JSON or HTML templates aren't JavaScript (#285).
fn javascript_type(t: Option<&str>) -> bool {
    let Some(t) = t else { return true };
    let essence = t.split(';').next().unwrap_or_default().trim().to_ascii_lowercase();
    essence.is_empty()
        || essence == "module"
        || matches!(essence.as_str(), "text/babel" | "text/jsx" | "text/jscript" | "text/livescript")
        || [
            "text/javascript",
            "application/javascript",
            "application/ecmascript",
            "text/ecmascript",
            "application/x-javascript",
            "application/x-ecmascript",
            "text/x-javascript",
            "text/x-ecmascript",
        ]
        .iter()
        .any(|m| essence == *m || essence.strip_prefix(m).is_some_and(|v| v.starts_with('1')))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn finds_scripts_and_csp() {
        let h = r#"<!doctype html><html><head><meta http-equiv="Content-Security-Policy" content="default-src 'self'">
<title>Notes</title><link rel="modulepreload" href="/assets/vendor-abc.js">
<script type="module" src="./app.js"></script><!-- <script src="no.js"></script> -->
<script>window.x = 1;</script><script type="application/json">{}</script></head></html>"#;
        let f = scan_html(h);
        assert_eq!(f.scripts.len(), 2);
        assert_eq!(f.scripts[0].src.as_deref(), Some("./app.js"));
        assert!(f.scripts[0].module);
        let (s, e) = f.scripts[1].inline.unwrap();
        assert_eq!(&h[s as usize..e as usize], "window.x = 1;");
        assert_eq!(f.preloads, vec!["/assets/vendor-abc.js"]);
        assert_eq!(f.csp.as_deref(), Some("default-src 'self'"));
        assert_eq!(f.title.as_deref(), Some("Notes"));
    }

    /// #285: import maps, speculation rules and HTML templates were read as JavaScript.
    #[test]
    fn only_javascript_types_are_scripts() {
        for t in ["importmap", "speculationrules", "text/html", "application/json", "text/x-template"] {
            let f = scan_html(&format!(r#"<script type="{t}">{{"imports": {{}}}}</script><script type="{t}" src="data.json"></script>"#));
            assert!(f.scripts.is_empty(), "{t}: {:?}", f.scripts);
        }
        for t in ["", "module", "text/javascript", "Application/JavaScript", "text/javascript; charset=utf-8", "text/babel"] {
            assert_eq!(scan_html(&format!(r#"<script type="{t}">fetch("/real-api");</script>"#)).scripts.len(), 1, "{t}");
        }
    }

    #[test]
    fn junk_does_not_panic() {
        for s in ["<", "<script", "<script src=", "<script src='x", "<<<<>>>", "<script>é", "<meta http-equiv=content-security-policy content=\"é", "<!--"] {
            let _ = scan_html(s);
        }
    }
}
