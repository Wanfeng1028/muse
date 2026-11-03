//! OpenCode (`opencode run`). Without `run` its first argument names the folder to open, so a
//! prompt given on its own was read as a folder and every run stopped at once (#32).

use super::*;

pub struct OpenCode;

impl AgentAdapter for OpenCode {
    fn ids(&self) -> &'static [&'static str] {
        &["opencode"]
    }

    fn args(&self, cx: &ArgsCx) -> Vec<String> {
        let mut a = vec!["run".to_string()];
        // A builder works unattended: what OpenCode would stop to ask is allowed, unless its own
        // settings deny it (as Codex gets a workspace-write sandbox).
        if cx.builder {
            a.push("--auto".into());
        }
        if let Some(m) = &cx.options.cli_model {
            a.extend(["--model".into(), m.clone()]);
        }
        a.extend(cx.options.args.iter().cloned());
        a.push(format!("{}{}", cx.preamble, cx.prompt));
        a
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
        OpenCode.args(&ArgsCx { options, prompt: "make a game", preamble: "PRE ", mcp: &mcp, resume: None, builder, reads_checked: false, question: false })
    }

    #[test]
    fn the_prompt_goes_to_run_after_the_flags() {
        assert_eq!(args(false, &BackendOptions::default()), ["run", "PRE make a game"]);
        let options =
            BackendOptions { cli_model: Some("anthropic/claude-sonnet-4-5".into()), args: vec!["--agent".into(), "build".into()], ..Default::default() };
        assert_eq!(args(true, &options), ["run", "--auto", "--model", "anthropic/claude-sonnet-4-5", "--agent", "build", "PRE make a game"]);
        assert!(AgentAdapters::built_in().for_agent("opencode").ids().contains(&"opencode"), "registered, not the plain adapter");
    }
}
