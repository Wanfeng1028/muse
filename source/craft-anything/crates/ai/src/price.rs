//! The cost meter: USD per million tokens by model, overridable in settings.

use crate::config::Price;
use crate::model::Usage;
use std::collections::BTreeMap;

const fn p(input: f64, output: f64, cache_read: f64) -> Price {
    Price { input_per_mtok: input, output_per_mtok: output, cache_read_per_mtok: Some(cache_read), cache_write_per_mtok: None }
}

/// Built-in list prices (USD per million tokens, first-party API rates, checked 2026-10).
pub fn builtin(model: &str) -> Option<Price> {
    let m = model.rsplit('/').next().unwrap_or(model);
    Some(match m {
        "claude-opus-5-5" => p(4.0, 20.0, 0.20),
        "claude-sonnet-5-5" => p(2.0, 10.0, 0.20),
        "claude-haiku-5-5" => p(0.10, 0.50, 0.01),
        "claude-fable-5-1" => p(10.0, 50.0, 0.25),
        "claude-opus-5" => p(5.0, 25.0, 0.50),
        "claude-sonnet-5" => p(2.0, 10.0, 0.20),
        // OpenRouter's list price (checked 2026-10-20); cached input isn't listed, so the default.
        "kimi-k3" => Price { input_per_mtok: 0.239, output_per_mtok: 11.936, cache_read_per_mtok: None, cache_write_per_mtok: None },
        _ => return None,
    })
}

/// Cost of one turn's usage, or `None` when the price is unknown. Local models cost nothing.
pub fn cost(model: &str, usage: &Usage, overrides: &BTreeMap<String, Price>, local: bool) -> Option<f64> {
    if local {
        return Some(0.0);
    }
    let price = overrides.get(model).copied().or_else(|| builtin(model))?;
    let per = |tokens: u64, rate: f64| tokens as f64 * rate / 1_000_000.0;
    let read = price.cache_read_per_mtok.unwrap_or(price.input_per_mtok * 0.1);
    let write = price.cache_write_per_mtok.unwrap_or(price.input_per_mtok * 1.25);
    Some(
        per(usage.input_tokens, price.input_per_mtok)
            + per(usage.output_tokens, price.output_per_mtok)
            + per(usage.cache_read_tokens, read)
            + per(usage.cache_write_tokens, write),
    )
}

/// Running totals for a conversation.
#[derive(Debug, Clone, Default, PartialEq)]
pub struct Meter {
    pub usage: Usage,
    pub cost_usd: f64,
    /// False once any turn had an unknown price.
    pub cost_known: bool,
    turns: u64,
}

impl Meter {
    pub fn add(&mut self, usage: Usage, cost: Option<f64>) {
        if self.turns == 0 {
            self.cost_known = true;
        }
        self.turns += 1;
        self.usage.add(usage);
        match cost {
            Some(c) => self.cost_usd += c,
            None => self.cost_known = false,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn price_math() {
        let u = Usage { input_tokens: 1_000_000, output_tokens: 100_000, cache_read_tokens: 1_000_000, cache_write_tokens: 0 };
        let c = cost("claude-opus-5-5", &u, &BTreeMap::new(), false).unwrap();
        assert!((c - (4.0 + 2.0 + 0.2)).abs() < 1e-9, "{c}");
        assert_eq!(cost("anthropic/claude-sonnet-5-5", &Usage { output_tokens: 1_000_000, ..Default::default() }, &BTreeMap::new(), false), Some(10.0));
        assert_eq!(cost("mystery", &u, &BTreeMap::new(), false), None);
        // Kimi K3 through OpenRouter is priced by its model id.
        let k =
            cost("moonshotai/kimi-k3", &Usage { input_tokens: 1_000_000, output_tokens: 1_000_000, ..Default::default() }, &BTreeMap::new(), false).unwrap();
        assert!((k - (0.239 + 11.936)).abs() < 1e-9, "{k}");
        assert_eq!(cost("mystery", &u, &BTreeMap::new(), true), Some(0.0));
        let mut o = BTreeMap::new();
        o.insert("mystery".into(), Price { input_per_mtok: 1.0, output_per_mtok: 1.0, cache_read_per_mtok: None, cache_write_per_mtok: None });
        let w = Usage { cache_write_tokens: 1_000_000, ..Default::default() };
        assert_eq!(cost("mystery", &w, &o, false), Some(1.25));
        let mut m = Meter::default();
        m.add(u, Some(1.0));
        m.add(u, None);
        assert!(!m.cost_known);
        assert_eq!(m.usage.input_tokens, 2_000_000);
    }
}
