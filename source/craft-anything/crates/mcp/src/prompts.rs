//! The six guided prompts. Each renders one user message: the objective, the steps, and the rules
//! that keep the answer honest. Wording is our own.

use serde_json::{Value, json};
use std::collections::BTreeMap;

pub struct Arg {
    pub name: &'static str,
    pub description: &'static str,
    pub required: bool,
}

pub struct PromptDef {
    pub name: &'static str,
    pub title: &'static str,
    pub description: &'static str,
    pub args: &'static [Arg],
    pub objective: &'static str,
    pub steps: &'static [&'static str],
}

const fn req(name: &'static str, description: &'static str) -> Arg {
    Arg { name, description, required: true }
}

const fn opt(name: &'static str, description: &'static str) -> Arg {
    Arg { name, description, required: false }
}

/// Rules appended to every prompt.
const DISCIPLINE: &[&str] = &[
    "Keep the investigation memory current: core_investigation_show first; core_brief_write and core_plan_update before analysis on a new question; core_hypothesis_record / core_hypothesis_update as claims change; core_finding_record only with evidence ids; core_handoff_write before you stop.",
    "Separate what you observed, what you derived, and what you infer. Cite the evidence id for every claim.",
    "Absence is not proof: if a search finds nothing, say what was searched and how much was covered.",
    "Predict before you look, then check the prediction against the evidence.",
    "Ask for summaries first and page for detail (offset/limit) instead of pulling everything at once.",
    "Record open questions with core_unknown_add rather than guessing.",
];

pub const PROMPTS: &[PromptDef] = &[
    PromptDef {
        name: "core_feature_explain",
        title: "Explain a feature",
        description: "Find out how a feature of a program or app works, with evidence for each step.",
        args: &[
            req("what", "The feature or behaviour to explain, in your own words."),
            opt("path", "Absolute path of the program, app bundle, package or folder."),
            opt("target_id", "An already open target id to use instead of opening a path."),
            opt("function", "A function name or address to start from, if you know one."),
            opt("evidence", "Earlier evidence to build on."),
        ],
        objective: "Explain how the feature works, from where it starts (UI action, command, entry point) through the data it touches to the result, backed by evidence.",
        steps: &[
            "Open the target (core_target_open) unless it is already open; check core_session_show.",
            "Write the brief (the feature question and what a complete answer looks like) and a short plan.",
            "Locate entry points: search strings, symbols, routes or IPC channels that name the feature.",
            "Follow the path: callers and callees, data flow, files or network endpoints involved.",
            "Record each claim as a hypothesis with a prediction, test it, then record findings with evidence ids.",
            "Summarise: the path step by step, the evidence for each step, and the unknowns that remain.",
        ],
    },
    PromptDef {
        name: "app_graphs_compare",
        title: "Compare two versions",
        description: "Explain what changed between two versions of an application.",
        args: &[
            req("older_path", "Absolute path of the older version."),
            req("newer_path", "Absolute path of the newer version."),
            opt("older_evidence", "Existing evidence describing the older version."),
            opt("newer_evidence", "Existing evidence describing the newer version."),
        ],
        objective: "Describe the behavioural differences between the two versions and how sure we are of each.",
        steps: &[
            "Open both targets and take an overview of each.",
            "Write the brief and a plan: which areas to compare (code, resources, endpoints, permissions).",
            "Compare like with like; only call something added or removed when both sides were fully covered.",
            "For each difference, record a finding with the evidence ids from both sides.",
            "List what could not be compared and why.",
        ],
    },
    PromptDef {
        name: "app_rebuild_claim_check",
        title: "Verify a rebuild",
        description: "Check a rebuilt implementation against the evidence about the original.",
        args: &[
            req("goal", "What the rebuild is supposed to reproduce."),
            opt("comparison_evidence", "Evidence from an earlier comparison."),
            opt("original_path", "Absolute path of the original program."),
        ],
        objective: "Decide, expectation by expectation, whether the rebuild matches the original, and say what is still unproven.",
        steps: &[
            "Read the investigation findings; they are the list of behaviours to match.",
            "Turn each finding into a checkable expectation with the evidence that defines it.",
            "Check each expectation against the rebuild and mark it met, not met, or not yet testable.",
            "Record a finding per expectation and an unknown for each gap.",
        ],
    },
    PromptDef {
        name: "native_crash_explain",
        title: "Explain a crash",
        description: "Work out where and why a program crashes.",
        args: &[
            req("symptom", "What you saw: the error, signal, message or log line."),
            opt("path", "Absolute path of the crashing program."),
            opt("target_id", "An already open target id."),
            opt("function", "The function or address where it seems to crash."),
            opt("evidence", "Evidence from an earlier capture or crash dump."),
        ],
        objective: "Find the code path that leads to the crash and the condition that triggers it.",
        steps: &[
            "Open the target and find code that produces or handles the crash signal (strings, handlers, asserts).",
            "Write hypotheses for the triggering condition, each with a prediction.",
            "Walk callers back from the crash site to an input you can name.",
            "Only run the program if static evidence cannot settle it, and only with the user's consent.",
            "Report the path, the trigger, and the evidence for each link.",
        ],
    },
    PromptDef {
        name: "core_unknowns_review",
        title: "Review open questions",
        description: "Go through the open unknowns and settle, narrow or justify each one.",
        args: &[
            req("scope", "Which part of the investigation to review (all, an area, a feature)."),
            opt("unknown", "A single unknown to focus on."),
            opt("evidence", "Evidence relevant to the review."),
        ],
        objective: "Leave every unknown in scope either resolved with evidence, narrowed with a next probe, or explicitly blocked with a reason.",
        steps: &[
            "List the unknowns in scope (core_unknowns_show) and read the current findings.",
            "For each, state what evidence would settle it and whether a tool can produce it.",
            "Run the cheapest decisive probe; update the unknown with the result.",
            "Never mark something resolved without an evidence id.",
        ],
    },
    PromptDef {
        name: "runtime_run_plan",
        title: "Plan a short run",
        description: "Plan a short, controlled run of a program to answer a behaviour question.",
        args: &[
            req("question", "The question the run should answer."),
            req("program", "Absolute path of the program to run."),
            req("folder", "Absolute path of a throwaway working folder."),
            opt("earlier_run_evidence", "Evidence from an earlier run to compare with."),
        ],
        objective: "Design the smallest run that answers the question, with limits, before anything is executed.",
        steps: &[
            "Check whether static evidence already answers the question; if so, stop there.",
            "Write the plan: inputs, time and output limits, what will be observed, and what could go wrong.",
            "Show the plan to the user; running the program needs their explicit consent.",
            "After the run, compare what happened with the prediction and record findings with the capture evidence id.",
        ],
    },
];

pub fn find(name: &str) -> Option<&'static PromptDef> {
    PROMPTS.iter().find(|p| p.name == name)
}

pub fn list_json() -> Value {
    let prompts: Vec<Value> = PROMPTS
        .iter()
        .map(|p| {
            json!({
                "name": p.name,
                "title": p.title,
                "description": p.description,
                "arguments": p.args.iter().map(|a| json!({"name": a.name, "description": a.description, "required": a.required})).collect::<Vec<_>>(),
            })
        })
        .collect();
    json!({ "prompts": prompts })
}

/// Render a prompt, or explain which argument is missing.
pub fn render(name: &str, args: &BTreeMap<String, String>) -> Result<Value, String> {
    let p = find(name).ok_or_else(|| format!("No prompt named {name}"))?;
    for a in p.args.iter().filter(|a| a.required) {
        if args.get(a.name).is_none_or(|v| v.trim().is_empty()) {
            return Err(format!("Missing required argument {}", a.name));
        }
    }
    let mut text = format!("# {}\n\n**Objective:** {}\n\n", p.title, p.objective);
    let given: Vec<&Arg> = p.args.iter().filter(|a| args.get(a.name).is_some_and(|v| !v.trim().is_empty())).collect();
    if !given.is_empty() {
        text.push_str("**Inputs:**\n");
        for a in given {
            text.push_str(&format!("- {}: {}\n", a.name, args.get(a.name).map(String::as_str).unwrap_or_default().trim()));
        }
        text.push('\n');
    }
    text.push_str("**Steps:**\n");
    for (i, s) in p.steps.iter().enumerate() {
        text.push_str(&format!("{}. {s}\n", i + 1));
    }
    text.push_str("\n**Rules:**\n");
    for r in DISCIPLINE {
        text.push_str(&format!("- {r}\n"));
    }
    Ok(json!({
        "description": p.description,
        "messages": [{"role": "user", "content": {"type": "text", "text": text}}],
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn six_prompts_render_and_validate() {
        assert_eq!(PROMPTS.len(), 6);
        let mut a = BTreeMap::new();
        assert!(render("core_feature_explain", &a).is_err());
        a.insert("what".to_string(), "  ".to_string());
        assert!(render("core_feature_explain", &a).is_err());
        a.insert("what".to_string(), "saving files".to_string());
        let v = render("core_feature_explain", &a).unwrap();
        let text = v["messages"][0]["content"]["text"].as_str().unwrap();
        assert!(text.contains("saving files") && text.contains("core_handoff_write"));
        assert!(render("nope", &a).is_err());
    }
}
