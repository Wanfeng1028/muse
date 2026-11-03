//! Hermes Agent (`hermes -z`).
//!
//! Hermes declares `-z/--oneshot` with `metavar="PROMPT"`, taking the prompt as its value.
//! Model `-m` and custom args come before `-z <prompt>`.

use super::*;

pub struct Hermes;

impl AgentAdapter for Hermes {
    fn ids(&self) -> &'static [&'static str] {
        &["hermes"]
    }

    fn args(&self, cx: &ArgsCx) -> Vec<String> {
        let mut v = Vec::new();
        if let Some(m) = &cx.options.cli_model {
            v.extend(["-m".into(), m.clone()]);
        }
        v.extend(cx.options.args.iter().cloned());
        v.extend(["-z".into(), format!("{}{}", cx.preamble, cx.prompt)]);
        v
    }

    fn required_flags(&self) -> (&'static [&'static str], &'static [&'static str]) {
        (&["--help"], &["--oneshot"])
    }

    /// Plain `hermes <prompt>` opens the interactive session; a failed flag check keeps this adapter.
    fn plain_fallback(&self) -> bool {
        false
    }

    fn streams_json(&self) -> bool {
        false
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn args(builder: bool, options: &BackendOptions) -> Vec<String> {
        let mcp = McpCommand { command: "craft-anything-cli".into(), args: vec!["mcp".into()], notes: None };
        Hermes.args(&ArgsCx { options, prompt: "make a game", preamble: "PRE ", mcp: &mcp, resume: None, builder, reads_checked: false, question: false })
    }

    #[test]
    fn the_prompt_goes_to_oneshot_after_the_flags() {
        assert_eq!(args(false, &BackendOptions::default()), ["-z", "PRE make a game"]);
        let options = BackendOptions { cli_model: Some("custom/qwen-2.5-coder".into()), args: vec!["-t".into(), "0.2".into()], ..Default::default() };
        assert_eq!(args(true, &options), ["-m", "custom/qwen-2.5-coder", "-t", "0.2", "-z", "PRE make a game"]);
        assert!(AgentAdapters::built_in().for_agent("hermes").ids().contains(&"hermes"), "registered, not the plain adapter");
        assert_eq!(Hermes.required_flags(), (&["--help"][..], &["--oneshot"][..]));
        assert!(!Hermes.plain_fallback());
    }
}
