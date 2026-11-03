//! What makes a `web_walkthrough_record` script wrong, in one place: the recorder refuses by these
//! rules and `web_walkthrough_check` reports by them, so the two can't disagree. Checking needs no
//! browser and touches no target.

use super::{Locator, WalkthroughAction, WalkthroughParams, WalkthroughStep, parse_params};
use craft_anything_evidence::ToolError;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use std::collections::BTreeMap;

const MAX_STEPS: usize = 200;
/// Most problems listed. A hostile script gets the rest counted.
const MAX_PROBLEMS: usize = 500;
const MAX_MESSAGE: usize = 400;
const MAX_SELECTOR: usize = 4096;
/// Longest a `wait` step or a `goto`'s `wait_ms` really waits (the recorder caps them).
pub(super) const MAX_WAIT_MS: u64 = 120_000;
pub(super) const MAX_GOTO_WAIT_MS: u64 = 60_000;

const LOCATOR_FIELDS: &[&str] = &["selector", "test_id", "role", "name"];
pub(super) const LOCATOR_SHAPE: &str = "each step needs exactly one of: selector, test_id, or role with name";

/// Every step kind: its name, the fields it must have, and the others it can have besides a locator.
/// A test checks this against the types, so a new kind can't be forgotten here.
const STEP_KINDS: &[StepKind] = &[
    StepKind { name: "goto", locator: false, required: &["url"], optional: &["wait_ms"] },
    StepKind { name: "click", locator: true, required: &[], optional: &[] },
    StepKind { name: "fill", locator: true, required: &["value"], optional: &[] },
    StepKind { name: "press", locator: true, required: &["key"], optional: &[] },
    StepKind { name: "select", locator: true, required: &["value"], optional: &[] },
    StepKind { name: "wait", locator: false, required: &["ms"], optional: &[] },
];

struct StepKind {
    name: &'static str,
    locator: bool,
    required: &'static [&'static str],
    optional: &'static [&'static str],
}

impl StepKind {
    fn knows(&self, field: &str) -> bool {
        field == "kind"
            || field == "step_id"
            || self.required.contains(&field)
            || self.optional.contains(&field)
            || (self.locator && LOCATOR_FIELDS.contains(&field))
    }

    fn fields(&self) -> Vec<&'static str> {
        let mut all = vec!["kind", "step_id"];
        all.extend(self.required);
        all.extend(self.optional);
        if self.locator {
            all.extend(LOCATOR_FIELDS);
        }
        all
    }
}

/// Why a parsed step can't run. Its message is what the recorder says too.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(super) struct StepRefusal {
    pub code: &'static str,
    pub field: Option<&'static str>,
    pub message: String,
}

impl StepRefusal {
    fn new(code: &'static str, field: Option<&'static str>, message: impl Into<String>) -> Self {
        StepRefusal { code, field, message: message.into() }
    }
}

impl From<StepRefusal> for ToolError {
    fn from(r: StepRefusal) -> ToolError {
        ToolError::invalid(r.message)
    }
}

/// What's wrong with a CSS selector's form, if that can be told without a page. Only forms a browser
/// is sure to reject: another tool's selector language, or brackets and quotes that never close.
pub(super) fn selector_problem(css: &str) -> Option<String> {
    if css.trim().is_empty() {
        return Some("selector is empty".into());
    }
    if css.len() > MAX_SELECTOR {
        return Some(format!("selector is longer than {MAX_SELECTOR} bytes"));
    }
    if css.chars().any(char::is_control) {
        return Some("selector can't contain control characters".into());
    }
    let t = css.trim_start();
    if t.starts_with('/') || t.starts_with("(/") || t.starts_with("./") {
        return Some(format!("selector {} looks like XPath; only CSS selectors work here", shown(css)));
    }
    for prefix in ["xpath=", "text=", "css=", "id=", "role=", "data-testid=", "testid="] {
        if t.len() >= prefix.len() && t.get(..prefix.len()).is_some_and(|p| p.eq_ignore_ascii_case(prefix)) {
            return Some(format!("selector {} uses another tool's {prefix} prefix; use plain CSS, or test_id, or role with name", shown(css)));
        }
    }
    let mut quote: Option<char> = None;
    let mut stack: Vec<char> = Vec::new();
    let mut chars = css.char_indices().peekable();
    while let Some((i, c)) = chars.next() {
        if c == '\\' {
            chars.next();
            continue;
        }
        if let Some(q) = quote {
            if c == q {
                quote = None;
            }
            continue;
        }
        match c {
            '"' | '\'' => quote = Some(c),
            '(' | '[' => stack.push(c),
            ')' | ']' => {
                let open = if c == ')' { '(' } else { '[' };
                if stack.pop() != Some(open) {
                    return Some(format!("selector {} has a {c} with nothing to close", shown(css)));
                }
            }
            '>' if stack.is_empty() && matches!(chars.peek(), Some((_, '>'))) => {
                return Some(format!("selector {} chains with >>, which CSS doesn't have", shown(css)));
            }
            ':' if !matches!(stack.last(), Some('[')) => {
                let rest = css.get(i + 1..).unwrap_or_default();
                let name: String = rest.chars().take_while(|x| x.is_ascii_alphanumeric() || *x == '-').collect::<String>().to_ascii_lowercase();
                let foreign = [
                    "has-text",
                    "text",
                    "text-is",
                    "text-matches",
                    "contains",
                    "visible",
                    "hidden",
                    "eq",
                    "gt",
                    "lt",
                    "first",
                    "last",
                    "nth-match",
                    "near",
                    "above",
                    "below",
                    "left-of",
                    "right-of",
                ];
                if foreign.contains(&name.as_str()) {
                    return Some(format!("selector {} uses :{name}, which CSS doesn't have; use role with name to find an element by its text", shown(css)));
                }
            }
            _ => {}
        }
    }
    if quote.is_some() {
        return Some(format!("selector {} has a quote that never closes", shown(css)));
    }
    if !stack.is_empty() {
        return Some(format!("selector {} has a bracket that never closes", shown(css)));
    }
    None
}

fn shown(s: &str) -> String {
    let short: String = s.chars().take(80).collect();
    format!("{short:?}")
}

impl Locator {
    /// Whether this names one element in a form that can be looked for.
    pub(super) fn check(&self) -> Result<(), StepRefusal> {
        match (&self.selector, &self.test_id, &self.role) {
            (Some(css), None, None) if self.name.is_none() => match selector_problem(css) {
                Some(why) => Err(StepRefusal::new("bad_selector", Some("selector"), why)),
                None => Ok(()),
            },
            (None, Some(id), None) if self.name.is_none() => {
                if id.is_empty() {
                    return Err(StepRefusal::new("bad_locator", Some("test_id"), "test_id is empty"));
                }
                if id.chars().any(char::is_control) {
                    return Err(StepRefusal::new("bad_locator", Some("test_id"), "test_id can't contain control characters"));
                }
                Ok(())
            }
            (None, None, Some(role)) => {
                let Some(name) = self.name.as_deref() else {
                    return Err(StepRefusal::new("bad_locator", Some("name"), "a role locator needs the element's name too"));
                };
                if role.is_empty() || !role.chars().all(|c| c.is_ascii_alphabetic() || c == '-') {
                    return Err(StepRefusal::new("bad_locator", Some("role"), format!("role {} isn't an ARIA role like button or link", shown(role))));
                }
                if name.is_empty() {
                    return Err(StepRefusal::new("bad_locator", Some("name"), "a role locator's name is empty"));
                }
                Ok(())
            }
            _ => Err(StepRefusal::new("bad_locator", None, LOCATOR_SHAPE)),
        }
    }
}

impl WalkthroughAction {
    /// Whether this step can run at all. The recorder asks this before each step; finding the element
    /// on the page is the only thing left that can go wrong with its form.
    pub(super) fn check(&self) -> Result<(), StepRefusal> {
        match self {
            WalkthroughAction::Goto { url, .. } => {
                if url.starts_with("http://") || url.starts_with("https://") || url.starts_with("file://") {
                    Ok(())
                } else {
                    Err(StepRefusal::new("bad_url", Some("url"), "goto url must be http(s) or file"))
                }
            }
            WalkthroughAction::Wait { .. } => Ok(()),
            WalkthroughAction::Click { at } | WalkthroughAction::Fill { at, .. } | WalkthroughAction::Select { at, .. } => at.check(),
            WalkthroughAction::Press { at, key } => {
                at.check()?;
                if key.is_empty() { Err(StepRefusal::new("bad_key", Some("key"), "press needs a key, like Enter")) } else { Ok(()) }
            }
        }
    }
}

impl WalkthroughParams {
    /// Everything about the script except its steps' contents, in the order the recorder has always
    /// checked it.
    pub(super) fn check_settings(&self) -> Result<(), ToolError> {
        check_step_count(self.actions.len())?;
        self.check_settings_without_steps()
    }

    fn check_settings_without_steps(&self) -> Result<(), ToolError> {
        self.environment.check()?;
        self.storage.check()?;
        if self.capture.after_each_step.len() > 5 || self.capture.at_end.len() > 5 {
            return Err(ToolError::invalid("capture lists take at most the 5 artifact kinds"));
        }
        if self.keep_bodies.any() && !self.capture_network {
            return Err(ToolError::invalid("keep_bodies needs capture_network"));
        }
        if !(1..=600).contains(&self.timeout_secs) {
            return Err(ToolError::invalid("timeout_secs must be 1..=600"));
        }
        Ok(())
    }
}

fn check_step_count(n: usize) -> Result<(), ToolError> {
    if n == 0 || n > MAX_STEPS {
        return Err(ToolError::invalid(format!("actions must be 1..={MAX_STEPS}")));
    }
    Ok(())
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum Severity {
    /// The recorder would refuse this, or fail at this step.
    Error,
    /// It would run, but probably not as meant.
    Warning,
}

/// One thing wrong with a script.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct ScriptProblem {
    pub severity: Severity,
    /// `missing_kind`, `unknown_kind`, `missing_field`, `bad_value`, `bad_selector`, `bad_locator`, `bad_url`,
    /// `bad_key`, `not_a_step`, `bad_actions`, `bad_settings` are errors; `unknown_field`, `duplicate_step_id`,
    /// `wait_capped`, `no_page_yet` are warnings.
    pub code: &'static str,
    /// The step's position in `actions`, from 0. None for the script as a whole.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub step: Option<usize>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub step_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub field: Option<String>,
    pub message: String,
    /// What was probably meant.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub did_you_mean: Option<String>,
}

fn clipped(s: String) -> String {
    if s.len() <= MAX_MESSAGE {
        return s;
    }
    let cut: String = s.chars().take(MAX_MESSAGE).collect();
    format!("{cut}…")
}

/// How many single-character edits apart two short names are, or `None` when clearly unrelated.
fn edit_distance(a: &str, b: &str) -> Option<usize> {
    let (a, b): (Vec<char>, Vec<char>) = (a.to_ascii_lowercase().chars().take(64).collect(), b.to_ascii_lowercase().chars().take(64).collect());
    if a.len().abs_diff(b.len()) > 3 {
        return None;
    }
    let mut row: Vec<usize> = (0..=b.len()).collect();
    for (i, x) in a.iter().enumerate() {
        let mut prev = row.first().copied().unwrap_or(i);
        if let Some(first) = row.first_mut() {
            *first = i + 1;
        }
        for (j, y) in b.iter().enumerate() {
            let above = row.get(j + 1).copied().unwrap_or(usize::MAX);
            let left = row.get(j).copied().unwrap_or(usize::MAX);
            let cost = prev.saturating_add(usize::from(x != y));
            prev = above;
            if let Some(cell) = row.get_mut(j + 1) {
                *cell = cost.min(above.saturating_add(1)).min(left.saturating_add(1));
            }
        }
    }
    row.last().copied()
}

fn closest(name: &str, options: &[&str]) -> Option<String> {
    // Names AIs carry over from other tools, which no spelling check would find.
    let carried = match name.to_ascii_lowercase().as_str() {
        "navigate" | "open" | "visit" | "load" => Some("goto"),
        "type" | "input" | "enter" | "settext" => Some("fill"),
        "sleep" | "pause" | "delay" | "waitfor" | "wait_for" => Some("wait"),
        "tap" | "dblclick" => Some("click"),
        "key" | "keypress" | "keydown" => Some("press"),
        "css" | "locator" | "element" | "target" => Some("selector"),
        "text" | "label" => Some("name"),
        "testid" | "testId" | "data_testid" | "data-testid" => Some("test_id"),
        "duration" | "time" | "timeout" | "milliseconds" => Some("ms"),
        "href" | "link" | "address" => Some("url"),
        _ => None,
    };
    if let Some(c) = carried.filter(|c| options.contains(c)) {
        return Some(c.to_string());
    }
    options.iter().filter_map(|o| edit_distance(name, o).filter(|d| *d <= 2 && *d < o.len()).map(|d| (d, *o))).min().map(|(_, o)| o.to_string())
}

#[derive(Default)]
struct Report {
    problems: Vec<ScriptProblem>,
    not_listed: u64,
    errors: u64,
    warnings: u64,
}

impl Report {
    fn add(
        &mut self,
        severity: Severity,
        code: &'static str,
        step: Option<(usize, Option<&str>)>,
        field: Option<&str>,
        message: String,
        did_you_mean: Option<String>,
    ) {
        match severity {
            Severity::Error => self.errors += 1,
            Severity::Warning => self.warnings += 1,
        }
        if self.problems.len() >= MAX_PROBLEMS {
            self.not_listed += 1;
            return;
        }
        self.problems.push(ScriptProblem {
            severity,
            code,
            step: step.map(|(i, _)| i),
            step_id: step.and_then(|(_, id)| id).map(|id| clipped(id.to_string())),
            field: field.map(|f| clipped(f.to_string())),
            message: clipped(message),
            did_you_mean,
        });
    }
}

fn check_step(report: &mut Report, index: usize, raw: &Value, seen_ids: &mut BTreeMap<String, usize>) {
    let Some(o) = raw.as_object() else {
        report.add(Severity::Error, "not_a_step", Some((index, None)), None, "a step is an object with a kind".into(), None);
        return;
    };
    let id = o.get("step_id").and_then(Value::as_str);
    let at = Some((index, id));
    if let Some(id) = id {
        if let Some(first) = seen_ids.get(id) {
            report.add(
                Severity::Warning,
                "duplicate_step_id",
                at,
                Some("step_id"),
                format!("step_id {} is already used by step {first}; comparing two runs lines steps up by step_id", shown(id)),
                None,
            );
        } else if seen_ids.len() < MAX_STEPS {
            seen_ids.insert(id.to_string(), index);
        }
    }
    let names: Vec<&str> = STEP_KINDS.iter().map(|k| k.name).collect();
    let Some(kind_name) = o.get("kind").and_then(Value::as_str) else {
        let code = if o.contains_key("kind") { "bad_value" } else { "missing_kind" };
        report.add(
            Severity::Error,
            code,
            at,
            Some("kind"),
            format!("a step needs a kind, one of: {}", names.join(", ")),
            o.keys().find_map(|k| closest(k, &names)),
        );
        return;
    };
    let Some(kind) = STEP_KINDS.iter().find(|k| k.name == kind_name) else {
        report.add(
            Severity::Error,
            "unknown_kind",
            at,
            Some("kind"),
            format!("{} isn't a step kind; the kinds are: {}", shown(kind_name), names.join(", ")),
            closest(kind_name, &names),
        );
        return;
    };
    // The recorder ignores fields it doesn't know, so these can't fail on their own; but a misspelt
    // one is usually why a required field looks missing.
    let fields = kind.fields();
    for k in o.keys() {
        if !kind.knows(k) {
            report.add(
                Severity::Warning,
                "unknown_field",
                at,
                Some(k),
                format!("a {kind_name} step has no field {}, so it's ignored; its fields are: {}", shown(k), fields.join(", ")),
                closest(k, &fields),
            );
        }
    }
    let mut missing = false;
    for field in kind.required {
        if !o.contains_key(*field) {
            missing = true;
            let hint = o.keys().filter(|k| !kind.knows(k)).find_map(|k| closest(k, &[*field]).map(|_| format!("{field} (not {k})")));
            report.add(Severity::Error, "missing_field", at, Some(field), format!("a {kind_name} step needs {field}"), hint);
        }
    }
    if missing {
        return;
    }
    let step: WalkthroughStep = match serde_json::from_value(raw.clone()) {
        Ok(s) => s,
        Err(e) => {
            report.add(Severity::Error, "bad_value", at, None, format!("this step can't be read: {e}"), None);
            return;
        }
    };
    if let Err(r) = step.action.check() {
        report.add(Severity::Error, r.code, at, r.field, r.message, None);
        return;
    }
    match step.action {
        WalkthroughAction::Wait { ms } if ms > MAX_WAIT_MS => {
            report.add(Severity::Warning, "wait_capped", at, Some("ms"), format!("a wait is cut to {MAX_WAIT_MS} ms"), None);
        }
        WalkthroughAction::Goto { wait_ms: Some(ms), .. } if ms > MAX_GOTO_WAIT_MS => {
            report.add(Severity::Warning, "wait_capped", at, Some("wait_ms"), format!("wait_ms is cut to {MAX_GOTO_WAIT_MS} ms"), None);
        }
        _ => {}
    }
}

/// Every problem in a script for `web_walkthrough_record`, without a browser. No errors here means
/// the recorder accepts the script and every step's form; elements may still not be on the page.
pub fn check_script(script: &Value) -> (Vec<ScriptProblem>, u64, u64, u64) {
    let mut report = Report::default();
    let Some(top) = script.as_object() else {
        report.add(Severity::Error, "bad_settings", None, None, "a script is an object with actions".into(), None);
        return (report.problems, report.errors, report.warnings, report.not_listed);
    };
    match top.get("actions") {
        None => report.add(Severity::Error, "bad_actions", None, Some("actions"), "a script needs actions, a list of steps".into(), None),
        Some(Value::Array(steps)) => {
            if let Err(e) = check_step_count(steps.len()) {
                report.add(Severity::Error, "bad_actions", None, Some("actions"), format!("{} (this script has {})", e.message, steps.len()), None);
            }
            let mut seen_ids = BTreeMap::new();
            // A script over the limit is refused anyway: its first steps still show the rest's mistakes.
            for (i, raw) in steps.iter().enumerate().take(MAX_STEPS) {
                check_step(&mut report, i, raw, &mut seen_ids);
            }
            // Nothing's open until something opens it, unless attaching to a browser that has a page.
            let first_kind = steps.first().and_then(|s| s.get("kind")).and_then(Value::as_str);
            let needs_a_page = first_kind.is_some_and(|k| STEP_KINDS.iter().any(|known| known.name == k && known.locator));
            if needs_a_page && top.get("cdp_endpoint").is_none_or(Value::is_null) {
                report.add(
                    Severity::Warning,
                    "no_page_yet",
                    Some((0, None)),
                    Some("kind"),
                    "this script starts a new browser, which has a blank page until a goto".into(),
                    Some("goto".into()),
                );
            }
        }
        Some(_) => report.add(Severity::Error, "bad_actions", None, Some("actions"), "actions must be a list of steps".into(), None),
    }
    // Everything else, read the way the recorder reads it, with the steps judged above set aside.
    let mut rest = top.clone();
    rest.insert("actions".into(), json!([]));
    match parse_params::<WalkthroughParams>(Value::Object(rest)) {
        Ok(p) => {
            if let Err(e) = p.check_settings_without_steps() {
                report.add(Severity::Error, "bad_settings", None, None, e.message, None);
            }
        }
        Err(e) => report.add(Severity::Error, "bad_settings", None, None, e.message, None),
    }
    (report.problems, report.errors, report.warnings, report.not_listed)
}

#[derive(Debug, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct WalkthroughCheckParams {
    /// What you'd pass to web_walkthrough_record, or only its list of actions.
    pub script: Value,
}

pub(super) fn web_walkthrough_check(_ctx: &mut crate::tool::Ctx<'_>, params: Value) -> Result<crate::tool::ToolOutput, ToolError> {
    let p: WalkthroughCheckParams = parse_params(params)?;
    let script = if p.script.is_array() { json!({"actions": p.script}) } else { p.script };
    let (problems, errors, warnings, not_listed) = check_script(&script);
    let steps = script.get("actions").and_then(Value::as_array).map_or(0, Vec::len);
    Ok(crate::tool::ToolOutput::Value(json!({
        "valid": errors == 0,
        "steps": steps,
        "errors": errors,
        "warnings": warnings,
        "problems": problems,
        "problems_not_listed": not_listed,
        "note": "This checks the script's form, without a browser. Whether each element is on the page only a run can tell.",
    })))
}

#[cfg(test)]
pub(super) fn step_kinds() -> Vec<(&'static str, Vec<&'static str>, Vec<&'static str>)> {
    STEP_KINDS.iter().map(|k| (k.name, k.required.to_vec(), k.fields())).collect()
}
