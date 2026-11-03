//! Turn `craft-anything-cli <tool> [path] [--json '{..}' | @file.json] [--key value…]` into tool params,
//! using the tool's JSON schema to type each flag.

use craft_anything_engine::{Requires, ToolSpec};
use serde_json::{Map, Value, json};

/// A parsed tool invocation.
#[derive(Debug, Default, PartialEq)]
pub struct ToolInvocation {
    pub params: Value,
    /// Path to open first (for tools that need an open target).
    pub open_path: Option<String>,
    /// Extra `core_target_open` params for that path (`format`, `architecture`, `entry_point`, `language_id`).
    pub open_params: Map<String, Value>,
    /// The output format asked for after the tool name (`--output-format`, or `--format` when the
    /// tool has no `format` option of its own).
    pub output_format: Option<String>,
    pub help: bool,
}

/// `core_target_open` options a target tool accepts for its `<target-path>` (raw binaries, Deep pins).
const OPEN_OPTIONS: [&str; 3] = ["architecture", "entry_point", "language_id"];
/// `--format` values that pick how the target is opened rather than how output is printed.
const OPEN_FORMATS: [&str; 2] = ["raw-binary", "dos-com"];

fn schema_props(schema: &Value) -> Map<String, Value> {
    schema.get("properties").and_then(Value::as_object).cloned().unwrap_or_default()
}

fn required(schema: &Value) -> Vec<String> {
    schema.get("required").and_then(Value::as_array).map(|a| a.iter().filter_map(|v| v.as_str().map(str::to_string)).collect()).unwrap_or_default()
}

/// The JSON type of a property ("string", "integer", "number", "boolean", "array", "object"), skipping "null".
fn prop_type(schema: &Value, prop: &Value) -> String {
    let resolved = resolve_ref(schema, prop);
    match resolved.get("type") {
        Some(Value::String(s)) => s.clone(),
        Some(Value::Array(a)) => a.iter().filter_map(Value::as_str).find(|t| *t != "null").unwrap_or("string").to_string(),
        _ => {
            // anyOf/oneOf of [X, null]
            for key in ["anyOf", "oneOf"] {
                if let Some(arr) = resolved.get(key).and_then(Value::as_array) {
                    for alt in arr {
                        let t = prop_type(schema, alt);
                        if t != "null" {
                            return t;
                        }
                    }
                }
            }
            if resolved.get("enum").is_some() { "string".into() } else { "any".into() }
        }
    }
}

fn resolve_ref<'a>(schema: &'a Value, prop: &'a Value) -> &'a Value {
    if let Some(r) = prop.get("$ref").and_then(Value::as_str) {
        let name = r.rsplit('/').next().unwrap_or_default();
        for defs in ["$defs", "definitions"] {
            if let Some(d) = schema.get(defs).and_then(|d| d.get(name)) {
                return d;
            }
        }
    }
    prop
}

fn convert(ty: &str, key: &str, raw: &str) -> Result<Value, String> {
    match ty {
        "integer" => {
            let t = raw.trim();
            if let Some(h) = t.strip_prefix("0x").or_else(|| t.strip_prefix("0X")) {
                u64::from_str_radix(h, 16).map(|n| json!(n)).map_err(|_| format!("--{key} expects a number, got {raw:?}"))
            } else {
                t.parse::<i64>().map(|n| json!(n)).map_err(|_| format!("--{key} expects a whole number, got {raw:?}"))
            }
        }
        "number" => raw.trim().parse::<f64>().map(|n| json!(n)).map_err(|_| format!("--{key} expects a number, got {raw:?}")),
        "boolean" => match raw.trim() {
            "true" | "yes" | "1" => Ok(json!(true)),
            "false" | "no" | "0" => Ok(json!(false)),
            _ => Err(format!("--{key} expects true or false, got {raw:?}")),
        },
        "object" => serde_json::from_str::<Value>(raw).map_err(|e| format!("--{key} expects JSON: {e}")),
        "array" => Ok(serde_json::from_str::<Value>(raw).ok().filter(Value::is_array).unwrap_or_else(|| json!([raw]))),
        "string" => Ok(json!(raw)),
        _ => Ok(serde_json::from_str::<Value>(raw).unwrap_or_else(|_| json!(raw))),
    }
}

/// Read inline JSON or `@file.json`.
pub fn read_json_arg(raw: &str) -> Result<Value, String> {
    let text = if raw == "-" {
        read_stdin_json(std::io::stdin())?
    } else {
        match raw.strip_prefix('@') {
            Some(path) => std::fs::read_to_string(path).map_err(|e| format!("can't read {path}: {e}"))?,
            None => raw.to_string(),
        }
    };
    serde_json::from_str(&text).map_err(|e| format!("params must be a JSON object: {e}"))
}

/// Most bytes of parameters taken from standard input.
const MAX_STDIN_JSON: u64 = 64 << 20;

/// Parameters piped in (`--json -`). Never waits at a terminal: nobody is going to type JSON there.
fn read_stdin_json<R: std::io::Read + std::io::IsTerminal>(input: R) -> Result<String, String> {
    if input.is_terminal() {
        return Err("--json - reads parameters from a pipe, but standard input is a terminal; pipe the JSON in, or pass it inline or as @file.json".into());
    }
    read_bounded_json(input)
}

fn read_bounded_json<R: std::io::Read>(input: R) -> Result<String, String> {
    use std::io::Read as _;
    let mut text = String::new();
    let read = input.take(MAX_STDIN_JSON + 1).read_to_string(&mut text).map_err(|e| format!("can't read parameters from standard input: {e}"))?;
    if read as u64 > MAX_STDIN_JSON {
        return Err(format!("parameters on standard input are over the limit of {MAX_STDIN_JSON} bytes; use @file.json"));
    }
    Ok(text)
}

pub fn parse(spec: &ToolSpec, schema: &Value, args: &[String]) -> Result<ToolInvocation, String> {
    let props = schema_props(schema);
    let mut params = Map::new();
    let mut positionals = Vec::new();
    let mut inv = ToolInvocation::default();
    let mut i = 0usize;
    while let Some(a) = args.get(i) {
        i += 1;
        if a == "--help" || a == "-h" {
            inv.help = true;
            continue;
        }
        if a == "--json" || a == "--params" {
            let raw = args.get(i).ok_or("--json needs a value")?;
            i += 1;
            merge(&mut params, read_json_arg(raw)?)?;
            continue;
        }
        if let Some(rest) = a.strip_prefix("--") {
            let (key, inline) = match rest.split_once('=') {
                Some((k, v)) => (k.to_string(), Some(v.to_string())),
                None => (rest.to_string(), None),
            };
            let snake = key.replace('-', "_");
            let is_target = spec.requires == Requires::Target;
            // Output format and target-open options, unless the tool has an option of the same name.
            if !props.contains_key(&snake) && (snake == "output_format" || snake == "format" || (is_target && OPEN_OPTIONS.contains(&snake.as_str()))) {
                let raw = match inline {
                    Some(v) => v,
                    None => {
                        let v = args.get(i).ok_or_else(|| format!("--{key} needs a value"))?.clone();
                        i += 1;
                        v
                    }
                };
                if snake == "output_format" || (snake == "format" && !(is_target && OPEN_FORMATS.contains(&raw.as_str()))) {
                    inv.output_format = Some(raw);
                } else {
                    inv.open_params.insert(snake, json!(raw));
                }
                continue;
            }
            let prop = props.get(&snake).ok_or_else(|| {
                let known: Vec<String> = props.keys().map(|k| format!("--{}", k.replace('_', "-"))).collect();
                format!("{} has no option --{key}. Options: {}", spec.cli_name(), if known.is_empty() { "(none)".into() } else { known.join(", ") })
            })?;
            let ty = prop_type(schema, prop);
            let raw = match inline {
                Some(v) => v,
                None if ty == "boolean" && args.get(i).is_none_or(|n| n.starts_with("--")) => "true".to_string(),
                None => {
                    let v = args.get(i).ok_or_else(|| format!("--{key} needs a value"))?.clone();
                    i += 1;
                    v
                }
            };
            let value = convert(&ty, &key, &raw)?;
            if ty == "array"
                && let Some(Value::Array(existing)) = params.get_mut(&snake)
                && let Value::Array(more) = value
            {
                existing.extend(more);
                continue;
            }
            params.insert(snake, value);
            continue;
        }
        if let Some(path) = a.strip_prefix('@')
            && path.ends_with(".json")
        {
            merge(&mut params, read_json_arg(a)?)?;
            continue;
        }
        positionals.push(a.clone());
    }
    // An architecture or entry point only means something for a raw binary.
    if (inv.open_params.contains_key("architecture") || inv.open_params.contains_key("entry_point")) && !inv.open_params.contains_key("format") {
        inv.open_params.insert("format".into(), json!("raw-binary"));
    }
    let mut positionals = positionals.into_iter();
    if spec.requires == Requires::Target
        && let Some(p) = positionals.next()
    {
        inv.open_path = Some(p);
    }
    // Remaining positionals fill required string params in order, then an optional path (what a bare
    // argument almost always is, whatever other options sort before it), then other string params.
    let mut slots: Vec<String> = required(schema).into_iter().filter(|k| !params.contains_key(k)).collect();
    if !slots.iter().any(|k| k == "path") && !params.contains_key("path") && props.get("path").is_some_and(|v| prop_type(schema, v) == "string") {
        slots.push("path".into());
    }
    for k in props.keys() {
        if !slots.contains(k) && !params.contains_key(k) && prop_type(schema, props.get(k).unwrap_or(&Value::Null)) == "string" {
            slots.push(k.clone());
        }
    }
    let mut slots = slots.into_iter();
    for p in positionals {
        let slot = slots.next().ok_or_else(|| format!("{} doesn't take another argument ({p:?})", spec.cli_name()))?;
        let ty = prop_type(schema, props.get(&slot).unwrap_or(&Value::Null));
        params.insert(slot.clone(), convert(&ty, &slot.replace('_', "-"), &p)?);
    }
    inv.params = Value::Object(params);
    Ok(inv)
}

fn merge(into: &mut Map<String, Value>, v: Value) -> Result<(), String> {
    match v {
        Value::Object(m) => {
            into.extend(m);
            Ok(())
        }
        _ => Err("params must be a JSON object".into()),
    }
}

/// Help text for one tool, generated from its schema.
/// The fields inside an object option (or an array of objects), listed under it as
/// `option.field`, two levels deep and at most 30 a level.
fn nested_fields(schema: &Value, prop: &Value, path: &str, depth: usize, out: &mut String) {
    if depth > 2 {
        return;
    }
    let mut obj = resolve_ref(schema, prop);
    // Option<T> arrives as anyOf/oneOf [T, null].
    if let Some(alt) = ["anyOf", "oneOf"]
        .iter()
        .find_map(|k| obj.get(*k).and_then(Value::as_array))
        .and_then(|a| a.iter().find(|x| x.get("type").and_then(Value::as_str) != Some("null")))
    {
        obj = resolve_ref(schema, alt);
    }
    if obj.get("type").and_then(Value::as_str) == Some("array")
        && let Some(items) = obj.get("items")
    {
        obj = resolve_ref(schema, items);
    }
    let Some(fields) = obj.get("properties").and_then(Value::as_object) else { return };
    let req = required(obj);
    for (name, f) in fields.iter().take(30) {
        let ty = prop_type(schema, f);
        let desc = f.get("description").and_then(Value::as_str).unwrap_or_default();
        let star = if req.contains(name) { " (required)" } else { "" };
        let field = format!("{path}.{name}");
        out.push_str(&format!("      {field:<26} {ty}{star}  {desc}\n"));
        nested_fields(schema, f, &field, depth + 1, out);
    }
}

pub fn help(spec: &ToolSpec, schema: &Value) -> String {
    let props = schema_props(schema);
    let req = required(schema);
    let mut s = format!("{} — {}\n\n{}\n\nUsage: craft-anything-cli {}", spec.cli_name(), spec.title, spec.summary, spec.cli_name());
    if spec.requires == Requires::Target {
        s.push_str(" <target-path>");
    }
    s.push_str(" [options] [--json '{...}' | @params.json | -]\n");
    if !props.is_empty() {
        s.push_str("\nOptions:\n");
        for (k, p) in &props {
            let ty = prop_type(schema, p);
            let desc = p.get("description").and_then(Value::as_str).unwrap_or_default();
            let star = if req.contains(k) { " (required)" } else { "" };
            s.push_str(&format!("  --{:<28} {ty}{star}  {desc}\n", k.replace('_', "-")));
            nested_fields(schema, p, k, 1, &mut s);
        }
    }
    if spec.requires == Requires::Target {
        s.push_str("\nTarget options (how <target-path> is opened):\n");
        s.push_str("  --architecture                 x86, x86_64, arm or arm64 for a raw binary (implies --format raw-binary)\n");
        s.push_str("  --entry-point                  Load/entry address (0x-hex) for a raw binary\n");
        s.push_str("  --format                       raw-binary or dos-com to force how the file is read\n");
        s.push_str("  --language-id                  Deep mode only: pin a Ghidra processor language\n");
    }
    let own_format = props.contains_key("format");
    s.push_str(&format!(
        "\nOutput:\n  --output-format                json, jsonl, md or text{}\n",
        if own_format { " (--format after the tool name is this tool's own option)" } else { " (--format works too)" }
    ));
    s
}

#[cfg(test)]
mod tests {
    use super::*;
    use craft_anything_engine::Registry;

    // The tests use built-in tools, whose schema is their own type's.
    fn parse(spec: &ToolSpec, args: &[String]) -> Result<ToolInvocation, String> {
        super::parse(spec, &(spec.input_schema)(), args)
    }
    fn help(spec: &ToolSpec) -> String {
        super::help(spec, &(spec.input_schema)())
    }

    #[test]
    fn help_lists_fields_inside_object_options() {
        let r = Registry::with_all_tools();
        let h = help(r.get("app_rebuild_claim_check").unwrap());
        assert!(h.contains("specification.goal"), "{h}");
        assert!(h.contains("specification.expectations.evidence_ids"), "array items are listed too: {h}");
        let plan = help(r.get("core_plan_update").unwrap());
        assert!(plan.contains("      steps."), "{plan}");
        let flat = help(r.get("core_target_open").unwrap());
        assert!(!flat.contains("      path."), "plain options have no nested lines");
    }

    #[test]
    fn flags_positionals_and_json() {
        let r = Registry::with_all_tools();
        let open = r.get("core_target_open").unwrap();
        let inv = parse(open, &["/bin/ls".into()]).unwrap();
        assert_eq!(inv.params["path"], "/bin/ls");
        assert!(inv.open_path.is_none());

        let upd = r.get("core_plan_update").unwrap();
        let inv = parse(upd, &["--json".into(), r#"{"steps":[]}"#.into(), "--based-on-revision".into(), "3".into()]).unwrap();
        assert_eq!(inv.params, json!({"steps": [], "based_on_revision": 3}));
        assert!(parse(upd, &["--nope".into(), "1".into()]).unwrap_err().contains("--steps"));
        assert!(parse(upd, &["--based-on-revision".into(), "x".into()]).is_err());

        let close = r.get("core_target_close").unwrap();
        let inv = parse(close, &["/tmp/a.bin".into()]).unwrap();
        assert_eq!(inv.open_path.as_deref(), Some("/tmp/a.bin"));

        let rj = r.get("core_journal_read").unwrap();
        let inv = parse(rj, &["--limit=5".into(), "--kind".into(), "tool_call".into()]).unwrap();
        assert_eq!(inv.params, json!({"limit": 5, "kind": "tool_call"}));
        assert!(parse(rj, &["--help".into()]).unwrap().help);
        assert!(help(rj).contains("--limit"));
    }

    #[test]
    fn format_flag_goes_to_the_tool_its_target_or_the_output() {
        let r = Registry::with_all_tools();
        // A tool with its own `format` option keeps it; the output format has its own flag.
        let open = r.get("core_target_open").unwrap();
        let inv = parse(open, &["--format".into(), "raw-binary".into(), "--output-format".into(), "text".into()]).unwrap();
        assert_eq!(inv.params["format"], "raw-binary");
        assert_eq!(inv.output_format.as_deref(), Some("text"));
        assert!(help(open).contains("this tool's own option"));
        // Without one, --format is the output format...
        let rj = r.get("core_journal_read").unwrap();
        let inv = parse(rj, &["--format=md".into()]).unwrap();
        assert_eq!(inv.output_format.as_deref(), Some("md"));
        assert_eq!(inv.params, json!({}));
        // ...and on a target tool, raw-binary/dos-com and the raw options describe how to open the path.
        let pc = r.get("native_function_pseudocode").unwrap();
        let args: Vec<String> = ["/tmp/raw.bin", "--architecture", "x86_64", "--entry-point", "0x1000", "--function", "0x1000", "--format", "text"]
            .iter()
            .map(|s| s.to_string())
            .collect();
        let inv = parse(pc, &args).unwrap();
        assert_eq!(inv.open_path.as_deref(), Some("/tmp/raw.bin"));
        assert_eq!(Value::Object(inv.open_params.clone()), json!({"architecture": "x86_64", "entry_point": "0x1000", "format": "raw-binary"}));
        assert_eq!(inv.output_format.as_deref(), Some("text"));
        let inv = parse(pc, &["/tmp/a.com".into(), "--format".into(), "dos-com".into()]).unwrap();
        assert_eq!(inv.open_params["format"], "dos-com");
        assert!(inv.output_format.is_none());
        assert!(help(pc).contains("--entry-point"));
    }

    #[test]
    fn at_file_input() {
        let dir = std::env::temp_dir().join(format!("cany-cli-test-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let f = dir.join("p.json");
        std::fs::write(&f, r#"{"question":"q?"}"#).unwrap();
        let r = Registry::with_all_tools();
        let inv = parse(r.get("core_brief_write").unwrap(), &[format!("@{}", f.display())]).unwrap();
        assert_eq!(inv.params["question"], "q?");
        let _ = std::fs::remove_dir_all(&dir);
    }

    #[test]
    fn parameters_from_a_pipe_are_bounded() {
        assert_eq!(read_bounded_json(&b"{\"a\":1}"[..]).unwrap(), "{\"a\":1}");
        let big = std::io::repeat(b' ').take(MAX_STDIN_JSON + 10);
        use std::io::Read as _;
        assert!(read_bounded_json(big).unwrap_err().contains("over the limit"));
        assert!(read_bounded_json(&[0xffu8, 0xfe][..]).is_err(), "bad text is an error");
    }
}
