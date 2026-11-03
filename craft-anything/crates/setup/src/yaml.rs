//! Minimal, comment-preserving edits to a YAML file's top-level `<table>:` mapping.
//!
//! We only ever add, replace or remove one child block (`  craft-anything:` and the lines indented
//! under it) inside one top-level block mapping. Everything else is left byte-for-byte. Every
//! result is re-parsed with a real YAML parser before it is written.

use serde_json::{Map, Value};
use yaml_rust2::{Yaml, YamlLoader};

/// Parse to JSON-like data (first document; an empty file is an empty mapping).
pub fn parse(text: &str) -> Result<Value, String> {
    let docs = YamlLoader::load_from_str(text).map_err(|e| e.to_string())?;
    match docs.into_iter().next() {
        None | Some(Yaml::Null) => Ok(Value::Object(Map::new())),
        Some(y @ Yaml::Hash(_)) => Ok(to_json(&y, 0)),
        Some(_) => Err("the top level must be a mapping".into()),
    }
}

fn to_json(y: &Yaml, depth: usize) -> Value {
    if depth > 64 {
        return Value::Null;
    }
    match y {
        Yaml::Real(s) => s.parse::<f64>().ok().and_then(serde_json::Number::from_f64).map(Value::Number).unwrap_or(Value::String(s.clone())),
        Yaml::Integer(i) => Value::from(*i),
        Yaml::String(s) => Value::String(s.clone()),
        Yaml::Boolean(b) => Value::Bool(*b),
        Yaml::Array(a) => Value::Array(a.iter().map(|v| to_json(v, depth + 1)).collect()),
        Yaml::Hash(h) => {
            let mut m = Map::new();
            for (k, v) in h {
                let key = match k {
                    Yaml::String(s) => s.clone(),
                    Yaml::Integer(i) => i.to_string(),
                    Yaml::Boolean(b) => b.to_string(),
                    Yaml::Real(r) => r.clone(),
                    _ => continue,
                };
                m.insert(key, to_json(v, depth + 1));
            }
            Value::Object(m)
        }
        _ => Value::Null,
    }
}

fn indent_of(line: &str) -> usize {
    line.len() - line.trim_start_matches(' ').len()
}

fn is_blank_or_comment(line: &str) -> bool {
    let t = line.trim();
    t.is_empty() || t.starts_with('#')
}

/// `key:` with optional comment, possibly quoted. Returns the rest after the colon.
fn key_line<'a>(line: &'a str, key: &str) -> Option<&'a str> {
    let t = line.trim_start();
    for k in [key.to_string(), format!("\"{key}\""), format!("'{key}'")] {
        if let Some(rest) = t.strip_prefix(&k)
            && let Some(rest) = rest.strip_prefix(':')
        {
            return Some(rest);
        }
    }
    None
}

fn only_comment(rest: &str) -> bool {
    let t = rest.trim();
    t.is_empty() || t.starts_with('#')
}

/// Render `name:` and its mapping value as block YAML at `indent` spaces. Scalars are written as
/// JSON strings/numbers, which are valid YAML.
fn render_entry(name: &str, value: &Value, indent: usize) -> String {
    let mut out = String::new();
    let pad = " ".repeat(indent);
    out.push_str(&format!("{pad}{}:\n", key(name)));
    render_map(value, indent + 2, &mut out);
    out
}

fn scalar(v: &Value) -> String {
    match v {
        Value::String(s) => serde_json::to_string(s).unwrap_or_else(|_| "\"\"".into()),
        Value::Null => "null".into(),
        other => other.to_string(),
    }
}

/// Plain keys stay plain (`command:`); anything unusual is quoted.
fn key(k: &str) -> String {
    let plain = !k.is_empty() && k.chars().all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-') && !k.starts_with('-');
    if plain { k.to_string() } else { scalar(&Value::String(k.to_string())) }
}

fn render_map(value: &Value, indent: usize, out: &mut String) {
    let pad = " ".repeat(indent);
    let Value::Object(m) = value else { return };
    for (k, v) in m {
        let key = key(k);
        match v {
            Value::Object(inner) if !inner.is_empty() => {
                out.push_str(&format!("{pad}{key}:\n"));
                render_map(v, indent + 2, out);
            }
            Value::Object(_) => out.push_str(&format!("{pad}{key}: {{}}\n")),
            Value::Array(items) if !items.is_empty() => {
                out.push_str(&format!("{pad}{key}:\n"));
                for it in items {
                    out.push_str(&format!("{pad}  - {}\n", scalar(it)));
                }
            }
            Value::Array(_) => out.push_str(&format!("{pad}{key}: []\n")),
            s => out.push_str(&format!("{pad}{key}: {}\n", scalar(s))),
        }
    }
}

struct Block {
    /// Line index of `table:`.
    header: usize,
    /// One past the last line belonging to the block (trailing blank/comment lines excluded).
    end: usize,
}

fn find_table(lines: &[&str], table: &str) -> Result<Option<Block>, String> {
    for (i, l) in lines.iter().enumerate() {
        if indent_of(l) != 0 || is_blank_or_comment(l) {
            continue;
        }
        if let Some(rest) = key_line(l, table) {
            if !only_comment(rest) {
                if rest.trim() == "{}" || rest.trim().starts_with("{}") && only_comment(rest.trim().get(2..).unwrap_or_default()) {
                    return Ok(Some(Block { header: i, end: i + 1 }));
                }
                return Err(format!("`{table}` uses inline (flow) style; edit it by hand or convert it to a block mapping"));
            }
            let mut end = i + 1;
            for (j, l2) in lines.iter().enumerate().skip(i + 1) {
                if is_blank_or_comment(l2) {
                    continue;
                }
                if indent_of(l2) == 0 {
                    break;
                }
                end = j + 1;
            }
            return Ok(Some(Block { header: i, end }));
        }
    }
    Ok(None)
}

/// Child block `[start, end)` named `name` inside the table block, with its indent.
fn find_child(lines: &[&str], block: &Block, name: &str) -> Option<(usize, usize)> {
    let mut child_indent = None;
    let mut i = block.header + 1;
    while i < block.end {
        let l = lines.get(i).copied().unwrap_or_default();
        if is_blank_or_comment(l) {
            i += 1;
            continue;
        }
        let ind = indent_of(l);
        let ci = *child_indent.get_or_insert(ind);
        if ind == ci && key_line(l, name).is_some() {
            let mut end = i + 1;
            for (j, l2) in lines.iter().enumerate().take(block.end).skip(i + 1) {
                if is_blank_or_comment(l2) {
                    continue;
                }
                if indent_of(l2) <= ci {
                    break;
                }
                end = j + 1;
            }
            return Some((i, end));
        }
        i += 1;
    }
    None
}

fn child_indent(lines: &[&str], block: &Block) -> usize {
    lines.iter().take(block.end).skip(block.header + 1).find(|l| !is_blank_or_comment(l)).map(|l| indent_of(l)).unwrap_or(2)
}

fn join(lines: &[String], had_trailing_newline: bool) -> String {
    let mut s = lines.join("\n");
    if had_trailing_newline || !s.is_empty() {
        s.push('\n');
    }
    s
}

/// Set `table.name` to `value` (a mapping). Returns the new text.
pub fn set(text: &str, table: &str, name: &str, value: &Value) -> Result<String, String> {
    parse(text)?;
    let trailing = text.ends_with('\n');
    let lines: Vec<&str> = text.lines().collect();
    let mut out: Vec<String> = lines.iter().map(|s| s.to_string()).collect();
    match find_table(&lines, table)? {
        None => {
            out.push(format!("{table}:"));
            out.extend(render_entry(name, value, 2).lines().map(str::to_string));
        }
        Some(block) => {
            if block.end == block.header + 1
                && let Some(h) = out.get_mut(block.header)
                && key_line(h, table).is_some_and(|r| r.trim().starts_with("{}"))
            {
                *h = format!("{table}:");
            }
            let indent = child_indent(&lines, &block);
            let rendered: Vec<String> = render_entry(name, value, indent).lines().map(str::to_string).collect();
            match find_child(&lines, &block, name) {
                Some((s, e)) => {
                    out.splice(s..e, rendered);
                }
                None => {
                    let at = block.end.min(out.len());
                    out.splice(at..at, rendered);
                }
            }
        }
    }
    let new = join(&out, trailing);
    parse(&new).map_err(|e| format!("the edited file would not parse: {e}"))?;
    Ok(new)
}

/// Remove `table.name`. Returns `None` when it was not there.
pub fn remove(text: &str, table: &str, name: &str) -> Option<String> {
    let lines: Vec<&str> = text.lines().collect();
    let block = find_table(&lines, table).ok()??;
    let (s, e) = find_child(&lines, &block, name)?;
    let mut out: Vec<String> = lines.iter().map(|s| s.to_string()).collect();
    out.drain(s..e);
    let new = join(&out, text.ends_with('\n'));
    parse(&new).ok()?;
    Some(new)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    const FIXTURE: &str =
        "# my agent\nmodel: big # inline\nmcp_servers:\n  # a friend\n  other:\n    command: x\n    args: [a]\n\n# tail comment\nskills: on\n";

    #[test]
    fn insert_replace_remove_preserve_comments() {
        let entry = json!({"command": "/opt/craft-anything-cli", "args": ["mcp"], "enabled": true});
        let new = set(FIXTURE, "mcp_servers", "craft-anything", &entry).unwrap();
        assert!(new.contains("# a friend") && new.contains("# tail comment") && new.contains("model: big # inline"));
        let v = parse(&new).unwrap();
        assert_eq!(v["mcp_servers"]["craft-anything"], entry);
        assert_eq!(v["mcp_servers"]["other"]["command"], "x");
        assert_eq!(v["skills"], "on");
        let changed = json!({"command": "/new", "args": ["mcp"], "enabled": true});
        let new2 = set(&new, "mcp_servers", "craft-anything", &changed).unwrap();
        assert_eq!(parse(&new2).unwrap()["mcp_servers"]["craft-anything"], changed);
        assert_eq!(new2.matches("craft-anything").count(), 1);
        assert_eq!(remove(&new2, "mcp_servers", "craft-anything").unwrap(), FIXTURE);
        assert!(remove(FIXTURE, "mcp_servers", "craft-anything").is_none());
    }

    #[test]
    fn creates_table_and_handles_flow_style() {
        let e = json!({"command": "c", "args": []});
        let new = set("", "mcp_servers", "craft-anything", &e).unwrap();
        assert_eq!(parse(&new).unwrap()["mcp_servers"]["craft-anything"], e);
        let new = set("a: 1\n", "mcp_servers", "craft-anything", &e).unwrap();
        assert_eq!(parse(&new).unwrap()["a"], 1);
        let new = set("mcp_servers: {}\n", "mcp_servers", "craft-anything", &e).unwrap();
        assert_eq!(parse(&new).unwrap()["mcp_servers"]["craft-anything"], e);
        assert!(set("mcp_servers: {a: 1}\n", "mcp_servers", "craft-anything", &e).is_err());
        assert!(set("a: [", "mcp_servers", "x", &e).is_err());
        assert!(parse("- 1\n").is_err());
    }
}
