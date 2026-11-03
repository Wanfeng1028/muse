//! What the AI has used: each project's building time, tokens and reported cost (saved by its
//! runs in `usage.json`, so they add up across restarts), and the session's total since the app
//! opened. An API key's cost comes from what it was charged; Claude Code gives its own estimate
//! at API prices, which isn't a bill (a subscription may cover it); other agents give tokens only.

use std::path::Path;
use std::time::{Duration, Instant};

use craft_anything_engine::workspace::ProjectUsage;

use crate::i18n::{tr, trf};

/// A project's usage as the app shows it: what its runs saved, plus the time since the run going
/// now last saved (it saves at each agent turn and when it ends).
#[derive(Debug, Clone, Default)]
pub struct ProjectClock {
    pub saved: ProjectUsage,
    /// A run is working: since when its time isn't in `saved` yet.
    pub since: Option<Instant>,
}

impl ProjectClock {
    pub fn load(root: &Path) -> ProjectClock {
        ProjectClock { saved: ProjectUsage::load(root), since: None }
    }

    /// The run saved its usage (an agent turn ended, or the run did): read it again.
    pub fn saved_again(&mut self, root: &Path, still_working: bool) {
        self.saved = ProjectUsage::load(root);
        self.since = still_working.then(Instant::now);
    }

    pub fn working(&self) -> bool {
        self.since.is_some()
    }

    /// Building time so far, the run going now included.
    pub fn elapsed(&self) -> Duration {
        Duration::from_millis(self.saved.work_ms) + self.since.map_or(Duration::ZERO, |s| s.elapsed())
    }
}

/// "about $3.20".
pub fn cost_words(usd: f64) -> String {
    trf("about ${n}", &[("n", &format!("{usd:.2}"))])
}

/// Below this, a difference between two amounts is rounding, not money.
const NOT_MONEY: f64 = 0.005;

/// Approximate asset price, retaining the asset table's sub-cent precision rule.
pub fn asset_cost_words(usd: f64) -> String {
    if usd > 0.0 && usd < NOT_MONEY { tr("under $0.01") } else { cost_words(usd) }
}

/// How to show a project's cost. A coding agent's figure is an estimate and is called one: it's
/// never shown as if it were what the person paid.
#[derive(Debug, Clone, PartialEq)]
pub struct CostStat {
    /// Translated when drawn.
    pub label: &'static str,
    pub value: String,
    /// Shown under the number. Translated when drawn.
    pub note: Option<&'static str>,
}

pub fn cost_stat(u: &ProjectUsage) -> CostStat {
    let estimated = u.estimated_usd();
    if estimated < NOT_MONEY {
        return CostStat { label: "AI cost", value: cost_words(u.cost_usd), note: None };
    }
    if u.api_billed_usd < NOT_MONEY {
        return CostStat { label: "AI cost (estimate)", value: cost_words(u.cost_usd), note: Some(ESTIMATE_NOTE) };
    }
    CostStat { label: "AI cost (part estimate)", value: cost_words(u.cost_usd), note: Some(ESTIMATE_NOTE) }
}

/// The cost in few words, for the title bar.
pub fn cost_short(u: &ProjectUsage) -> String {
    if u.estimated_usd() < NOT_MONEY { cost_words(u.cost_usd) } else { trf("{cost} (estimate)", &[("cost", &cost_words(u.cost_usd))]) }
}

const ESTIMATE_NOTE: &str = "The coding agent's estimate at API prices, not your bill. A subscription isn't charged this.";

/// "830", "12k", "1.2M".
pub fn tokens_short(n: u64) -> String {
    match n {
        0..1_000 => n.to_string(),
        1_000..1_000_000 => format!("{}k", n / 1_000),
        _ => format!("{:.1}M", n as f64 / 1_000_000.0),
    }
}

/// "830 tokens", "12k tokens", "1.2M tokens".
pub fn tokens_words(n: u64) -> String {
    trf("{n} tokens", &[("n", &tokens_short(n))])
}

/// "45s", "12m 05s", "1h 04m".
pub fn duration_words(d: Duration) -> String {
    let s = d.as_secs();
    match s {
        0..60 => format!("{s}s"),
        60..3600 => format!("{}m {:02}s", s / 60, s % 60),
        _ => format!("{}h {:02}m", s / 3600, (s % 3600) / 60),
    }
}

/// The tooltip for usage: what each number is, and what it counts (`counts`, e.g. "Every build
/// of this project." or "Since Craft Anything opened.").
pub fn explain(u: &ProjectUsage, counts: &str) -> String {
    let mut lines = vec![trf("{in} in, {out} out.", &[("in", &tokens_words(u.input_tokens)), ("out", &tokens_words(u.output_tokens))])];
    if u.priced && u.estimated_usd() >= NOT_MONEY {
        lines.push(tr(ESTIMATE_NOTE));
        if u.api_billed_usd >= NOT_MONEY {
            lines.push(trf("Of this, {cost} was charged to an API key.", &[("cost", &cost_words(u.api_billed_usd))]));
        }
    }
    lines.push(tr(counts));
    lines.join("\n")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_projects_clock_adds_the_running_time_to_what_was_saved() {
        let dir = tempfile::tempdir().unwrap();
        let mut c = ProjectClock::load(dir.path());
        assert!(!c.working() && c.elapsed().is_zero());
        ProjectUsage::update(dir.path(), |u| u.work_ms = 725_000).unwrap();
        c.saved_again(dir.path(), true);
        assert!(c.working() && c.elapsed() >= Duration::from_secs(725));
        c.saved_again(dir.path(), false);
        assert_eq!(c.elapsed(), Duration::from_secs(725));
    }

    #[test]
    fn a_coding_agents_cost_is_called_an_estimate_and_a_keys_is_not() {
        let mut agent = ProjectUsage::default();
        agent.add_turn(10, 10, Some(3.12), true);
        let stat = cost_stat(&agent);
        assert_eq!((stat.label, stat.value.as_str()), ("AI cost (estimate)", "about $3.12"));
        assert!(stat.note.unwrap().contains("not your bill"));
        assert_eq!(cost_short(&agent), "about $3.12 (estimate)");
        assert!(explain(&agent, "x").contains("not your bill"));

        let mut key = ProjectUsage::default();
        key.add_turn(10, 10, Some(1.5), false);
        assert_eq!(cost_stat(&key), CostStat { label: "AI cost", value: "about $1.50".into(), note: None });
        assert_eq!(cost_short(&key), "about $1.50");
        assert!(!explain(&key, "x").contains("estimate"));

        // Both in one project: the total, said to be partly an estimate, and the charged part.
        key.add_turn(10, 10, Some(2.0), true);
        assert_eq!(cost_stat(&key).label, "AI cost (part estimate)");
        assert_eq!(cost_stat(&key).value, "about $3.50");
        assert!(explain(&key, "x").contains("about $1.50 was charged"));
    }

    #[test]
    fn a_saved_cost_from_before_the_split_counts_as_an_estimate() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::write(
            dir.path().join(craft_anything_engine::workspace::USAGE_FILE),
            r#"{"version":1,"work_ms":5,"input_tokens":1,"output_tokens":1,"cost_usd":3.12,"priced":true}"#,
        )
        .unwrap();
        assert_eq!(cost_stat(&ProjectUsage::load(dir.path())).label, "AI cost (estimate)");
    }

    #[test]
    fn plain_words_for_numbers() {
        assert_eq!(asset_cost_words(0.0031), "under $0.01");
        assert_eq!(asset_cost_words(0.65), "about $0.65");
        assert_eq!(tokens_words(830), "830 tokens");
        assert_eq!(tokens_short(1_180_000), "1.2M");
        assert_eq!(cost_words(3.21), "about $3.21");
        assert_eq!(duration_words(Duration::from_secs(45)), "45s");
        assert_eq!(duration_words(Duration::from_secs(725)), "12m 05s");
        assert_eq!(duration_words(Duration::from_secs(3840)), "1h 04m");
    }
}
