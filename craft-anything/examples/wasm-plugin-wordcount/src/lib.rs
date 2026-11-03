//! An example Craft Anything plugin: one tool, `count_words`, that counts the words, lines and
//! characters of a text. It implements `craft-anything:plugin/tools` from
//! `crates/engines/wit/plugin.wit` and imports nothing.

use serde_json::{Value, json};

wit_bindgen::generate!({
    path: "../../crates/engines/wit/plugin.wit",
    world: "plugin",
});

struct Plugin;

impl exports::craft_anything::plugin::tools::Guest for Plugin {
    fn describe() -> String {
        json!([{
            "name": "count_words",
            "title": "Count words",
            "description": "Count the words, lines and characters of a text.",
            "input_schema": {
                "type": "object",
                "properties": {"text": {"type": "string", "description": "The text to count."}},
                "required": ["text"]
            }
        }])
        .to_string()
    }

    fn call(name: String, input: String) -> String {
        let answer = match name.as_str() {
            "count_words" => count_words(&input),
            other => Err(format!("this plugin has no tool called {other}")),
        };
        match answer {
            Ok(v) => json!({"ok": v}),
            Err(e) => json!({"error": e}),
        }
        .to_string()
    }
}

fn count_words(input: &str) -> Result<Value, String> {
    let v: Value = serde_json::from_str(input).map_err(|e| format!("the input isn't JSON: {e}"))?;
    let text = v.get("text").and_then(Value::as_str).ok_or("give the text to count as \"text\"")?;
    Ok(json!({
        "words": text.split_whitespace().count(),
        "lines": text.lines().count(),
        "characters": text.chars().count(),
    }))
}

export!(Plugin);
