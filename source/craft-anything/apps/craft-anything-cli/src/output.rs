//! Output formats: json (pretty on a TTY), jsonl, md, text, csv and tsv (a result's rows, for a spreadsheet).

use clap::ValueEnum;
use serde_json::{Map, Value};
use std::io::IsTerminal as _;

#[derive(Debug, Clone, Copy, PartialEq, Eq, ValueEnum, Default)]
pub enum Format {
    #[default]
    Json,
    Jsonl,
    Md,
    Text,
    Csv,
    Tsv,
}

pub fn render(v: &Value, f: Format) -> String {
    match f {
        Format::Json => {
            if std::io::stdout().is_terminal() {
                serde_json::to_string_pretty(v).unwrap_or_default()
            } else {
                serde_json::to_string(v).unwrap_or_default()
            }
        }
        Format::Jsonl => match v {
            Value::Array(items) => items.iter().map(|i| serde_json::to_string(i).unwrap_or_default()).collect::<Vec<_>>().join("\n"),
            _ => serde_json::to_string(v).unwrap_or_default(),
        },
        Format::Md => markdown(v),
        Format::Text => text(v, 0),
        Format::Csv => table(v, ','),
        Format::Tsv => table(v, '\t'),
    }
}

/// The rows a table shows: an array of objects itself, or the largest one in a result (evidence's
/// `result`, where a tool's list sits); otherwise the object's own fields as one row.
fn rows(v: &Value) -> Vec<Map<String, Value>> {
    // A tool's plain value comes wrapped as `{"result": …}`, like evidence's result.
    let wrapped = v.as_object().is_some_and(|m| m.len() == 1 && m.contains_key("result"));
    let body = if is_evidence(v) || wrapped { &v["result"] } else { v };
    let objects = |a: &[Value]| a.iter().filter_map(|i| i.as_object().cloned()).collect::<Vec<_>>();
    let found = match body {
        Value::Array(a) => objects(a),
        Value::Object(m) => m.values().filter_map(Value::as_array).map(|a| objects(a)).max_by_key(Vec::len).unwrap_or_default(),
        _ => Vec::new(),
    };
    if !found.is_empty() {
        return found;
    }
    match body {
        Value::Object(m) => vec![m.clone()],
        _ => Vec::new(),
    }
}

fn table(v: &Value, sep: char) -> String {
    if let Some(e) = v.get("error") {
        return text(&serde_json::json!({"error": e}), 0);
    }
    let rows = rows(v);
    let mut columns: Vec<&String> = Vec::new();
    for key in rows.iter().flat_map(|r| r.keys()) {
        if !columns.contains(&key) {
            columns.push(key);
        }
    }
    let line = |cells: Vec<String>| cells.join(&sep.to_string());
    let mut out = vec![line(columns.iter().map(|c| cell(&Value::String((*c).clone()), sep)).collect())];
    for r in &rows {
        out.push(line(columns.iter().map(|c| r.get(*c).map_or_else(String::new, |x| cell(x, sep))).collect()));
    }
    out.join("\n")
}

/// One table cell. What's in a result comes from the file being studied, so text a spreadsheet
/// would run as a formula is kept as text.
fn cell(v: &Value, sep: char) -> String {
    let raw = match v {
        Value::Null => String::new(),
        Value::String(s) => s.clone(),
        other => other.to_string(),
    };
    let safe = if matches!(v, Value::String(_)) && raw.starts_with(['=', '+', '-', '@', '\t', '\r']) { format!("'{raw}") } else { raw };
    if sep == '\t' {
        return safe.replace(['\t', '\n', '\r'], " ");
    }
    if safe.contains([sep, '"', '\n', '\r']) { format!("\"{}\"", safe.replace('"', "\"\"")) } else { safe }
}

fn is_evidence(v: &Value) -> bool {
    v.get("id").and_then(Value::as_str).is_some_and(|i| i.starts_with("ev_")) && v.get("operation").is_some()
}

fn markdown(v: &Value) -> String {
    if let Some(e) = v.get("error") {
        let mut s = format!("**Error ({})**: {}\n", e["code"].as_str().unwrap_or("error"), e["message"].as_str().unwrap_or_default());
        if let Some(r) = e.get("remediation").and_then(Value::as_str) {
            s.push_str(&format!("\n**What to do:** {r}\n"));
        }
        return s;
    }
    if is_evidence(v) {
        let mut s = format!("## {}\n\n", v["operation"].as_str().unwrap_or_default());
        if let Some(sum) = v.get("summary").and_then(Value::as_str).filter(|s| !s.is_empty()) {
            s.push_str(&format!("{sum}\n\n"));
        }
        s.push_str(&format!("- Evidence: `{}`\n- Confidence: {}\n", v["id"].as_str().unwrap_or_default(), v["confidence"].as_str().unwrap_or_default()));
        if let Some(ls) = v.get("limitations").and_then(Value::as_array).filter(|l| !l.is_empty()) {
            s.push_str("- Limitations:\n");
            for l in ls {
                s.push_str(&format!("  - {}\n", l["message"].as_str().unwrap_or_default()));
            }
        }
        s.push_str(&format!("\n```json\n{}\n```\n", serde_json::to_string_pretty(&v["result"]).unwrap_or_default()));
        return s;
    }
    format!("```json\n{}\n```\n", serde_json::to_string_pretty(v).unwrap_or_default())
}

fn text(v: &Value, depth: usize) -> String {
    if depth == 0 {
        if let Some(e) = v.get("error") {
            let mut s = format!("error: {}", e["message"].as_str().unwrap_or_default());
            if let Some(r) = e.get("remediation").and_then(Value::as_str) {
                s.push_str(&format!("\nfix: {r}"));
            }
            return s;
        }
        if is_evidence(v) {
            let sum = v.get("summary").and_then(Value::as_str).unwrap_or_default();
            return format!("{sum}\n[{}; {}]\n{}", v["id"].as_str().unwrap_or_default(), v["confidence"].as_str().unwrap_or_default(), text(&v["result"], 1));
        }
    }
    let pad = "  ".repeat(depth.saturating_sub(1));
    match v {
        Value::Object(m) => m
            .iter()
            .map(|(k, val)| match val {
                Value::Object(_) | Value::Array(_) => format!("{pad}{k}:\n{}", text(val, depth + 1)),
                _ => format!("{pad}{k}: {}", scalar(val)),
            })
            .collect::<Vec<_>>()
            .join("\n"),
        Value::Array(a) => a
            .iter()
            .map(|val| match val {
                Value::Object(_) | Value::Array(_) => format!("{pad}-\n{}", text(val, depth + 1)),
                _ => format!("{pad}- {}", scalar(val)),
            })
            .collect::<Vec<_>>()
            .join("\n"),
        _ => format!("{pad}{}", scalar(v)),
    }
}

fn scalar(v: &Value) -> String {
    match v {
        Value::String(s) => s.clone(),
        other => other.to_string(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn formats() {
        let v = json!({"a": 1, "b": {"c": [1, "x"]}});
        assert_eq!(render(&v, Format::Jsonl), r#"{"a":1,"b":{"c":[1,"x"]}}"#);
        let t = render(&v, Format::Text);
        assert!(t.contains("a: 1") && t.contains("- x"), "{t}");
        assert!(render(&v, Format::Md).starts_with("```json"));
        let e = json!({"error": {"code": "bad_input", "message": "bad", "remediation": "fix it"}});
        assert!(render(&e, Format::Text).contains("fix: fix it"));
        assert!(render(&e, Format::Md).contains("What to do"));
        assert_eq!(render(&json!([1, 2]), Format::Jsonl), "1\n2");
    }

    fn evidence(result: Value) -> Value {
        json!({"id": "ev_1", "operation": "op", "summary": "s", "confidence": "observed", "result": result})
    }

    #[test]
    fn tables_show_the_largest_list_of_rows() {
        let v = evidence(json!({"total": 2, "notes": [{"a": 1}], "entries": [{"path": "a,b", "size": 1}, {"path": "c\"d", "kind": "x"}]}));
        assert_eq!(render(&v, Format::Csv), "path,size,kind\n\"a,b\",1,\n\"c\"\"d\",,x");
        assert_eq!(render(&v, Format::Tsv), "path\tsize\tkind\na,b\t1\t\nc\"d\t\tx");
    }

    #[test]
    fn a_bare_array_and_a_plain_object_are_tables_too() {
        assert_eq!(render(&json!([{"a": 1}, {"a": 2}]), Format::Csv), "a\n1\n2");
        assert_eq!(render(&json!({"a": 1, "b": "x"}), Format::Csv), "a,b\n1,x");
        assert_eq!(render(&json!([1, 2]), Format::Csv), "");
    }

    #[test]
    fn a_plain_tools_wrapped_value_is_unwrapped() {
        assert_eq!(render(&json!({"result": {"count": 0, "projects": [{"id": "a"}]}}), Format::Csv), "id\na");
        assert_eq!(render(&json!({"result": {"count": 0}}), Format::Csv), "count\n0");
    }

    #[test]
    fn nested_values_stay_json_in_one_cell() {
        assert_eq!(render(&json!([{"a": {"b": [1, 2]}}]), Format::Csv), "a\n\"{\"\"b\"\":[1,2]}\"");
    }

    #[test]
    fn text_from_a_hostile_file_cannot_become_a_spreadsheet_formula() {
        for evil in ["=cmd|' /C calc'!A0", "+1+1", "-2", "@SUM(A1)", "\t=1"] {
            let csv = render(&json!([{"name": evil}]), Format::Csv);
            let cell = csv.lines().nth(1).unwrap().trim_start_matches('"');
            assert!(cell.starts_with('\''), "{csv}");
            let tsv = render(&json!([{"name": evil}]), Format::Tsv);
            assert!(tsv.lines().nth(1).unwrap().starts_with('\''), "{tsv}");
        }
        assert_eq!(render(&json!([{"n": -2}]), Format::Csv), "n\n-2", "real numbers stay numbers");
    }

    #[test]
    fn line_breaks_and_tabs_cannot_add_rows_or_columns() {
        assert_eq!(render(&json!([{"a": "x\ny"}]), Format::Csv), "a\n\"x\ny\"");
        assert_eq!(render(&json!([{"a": "x\n\ty"}]), Format::Tsv), "a\nx  y");
    }

    #[test]
    fn errors_stay_readable_in_table_formats() {
        let e = json!({"error": {"code": "x", "message": "boom"}});
        assert!(render(&e, Format::Csv).contains("boom"));
    }
}
