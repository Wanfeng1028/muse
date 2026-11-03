//! An example Craft Anything check plugin: `readme_says_how_to_run` passes when the build has a
//! README.md at its root that tells a person how to start it. It implements
//! `craft-anything:plugin/checks` from `crates/engines/wit/plugin.wit`, imports nothing, and asks
//! only for `.md` files' text.

use serde_json::{Value, json};

wit_bindgen::generate!({
    path: "../../crates/engines/wit/plugin.wit",
    world: "checks-plugin",
});

struct Plugin;

/// Words that show the README says how to start the result.
const RUN_WORDS: &[&str] = &["run", "start", "open", "play", "launch", "npm ", "cargo ", "python", "./"];

impl exports::craft_anything::plugin::checks::Guest for Plugin {
    fn describe() -> String {
        json!([{
            "name": "readme_says_how_to_run",
            "title": "README says how to run it",
            "description": "The build has a README.md that tells a person how to start it.",
            "kinds": [],
            "extensions": ["md"]
        }])
        .to_string()
    }

    fn run(name: String, build: String) -> String {
        let answer = match name.as_str() {
            "readme_says_how_to_run" => judge(&build),
            other => Err(format!("this plugin has no check called {other}")),
        };
        match answer {
            Ok(v) => v,
            Err(e) => json!({"error": e}),
        }
        .to_string()
    }
}

fn judge(build: &str) -> Result<Value, String> {
    let b: Value = serde_json::from_str(build).map_err(|e| format!("the build isn't JSON: {e}"))?;
    let files = b.get("files").and_then(Value::as_array).ok_or("the build has no files list")?;
    let readme = files.iter().find(|f| f.get("path").and_then(Value::as_str).is_some_and(|p| p.eq_ignore_ascii_case("README.md")));
    let Some(readme) = readme else {
        return Ok(json!({"passed": false, "summary": "There's no README.md at the top of the build: add one that says what it is and how to start it."}));
    };
    let Some(text) = readme.get("text").and_then(Value::as_str) else {
        return Ok(json!({"passed": false, "summary": "README.md is too large to read; keep it short."}));
    };
    let lower = text.to_lowercase();
    let says_how = RUN_WORDS.iter().any(|w| lower.contains(w)) || text.contains("```");
    Ok(if text.trim().len() < 40 {
        json!({"passed": false, "summary": "README.md is nearly empty: say what this is and how to start it."})
    } else if says_how {
        json!({"passed": true, "summary": "README.md says how to start it."})
    } else {
        json!({"passed": false, "summary": "README.md doesn't say how to start it: add the command or the steps."})
    })
}

export!(Plugin);
