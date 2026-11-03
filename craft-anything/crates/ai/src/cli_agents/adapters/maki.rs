//! Maki (`maki -p`).
//!
//! `-p/--print` is a switch: the prompt is Maki's positional argument, so it goes last. Plain
//! `maki <prompt>` opens its terminal interface instead of answering.
//!
//! Maki lets its file tools write anywhere under its working folder without asking, and in `-p`
//! nothing can ask. So outside a build its tools that change something are switched off with
//! `--disallowed-tools` (names it doesn't know are skipped, so an older Maki still runs).
//! Anything else that would ask first (an MCP server's tools, in subagents too) is refused at once
//! in `-p`, since nobody can answer, unless the person allowed it in Maki's own permissions.
//!
//! Nothing here asks us, so a Clean room build's reads aren't checked: the same gap as every agent
//! that never asks us, left to the approval decision in the roadmap (R2.2).

use super::*;

pub struct Maki;

/// Maki's tools that change files or run something: writing tools, the shell, and code execution
/// (its `open()` writes through the write tool, but it can also remove and rename).
const CHANGES: &str = "write,edit,multiedit,edit_lines,insert_lines,bash,code_execution";

impl AgentAdapter for Maki {
    fn ids(&self) -> &'static [&'static str] {
        &["maki"]
    }

    fn args(&self, cx: &ArgsCx) -> Vec<String> {
        let mut v = Vec::new();
        if let Some(m) = &cx.options.cli_model {
            v.extend(["-m".into(), m.clone()]);
        }
        if !cx.builder {
            v.extend(["--disallowed-tools".into(), CHANGES.into()]);
        }
        v.extend(cx.options.args.iter().cloned());
        v.extend(["-p".into(), format!("{}{}", cx.preamble, cx.prompt)]);
        v
    }

    fn required_flags(&self) -> (&'static [&'static str], &'static [&'static str]) {
        (&["--help"], &["--print"])
    }

    /// Plain `maki <prompt>` opens the terminal interface; a failed flag check keeps this adapter.
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
        Maki.args(&ArgsCx { options, prompt: "make a game", preamble: "PRE ", mcp: &mcp, resume: None, builder, reads_checked: false, question: false })
    }

    #[test]
    fn the_prompt_goes_last_after_print_and_the_flags() {
        assert_eq!(args(true, &BackendOptions::default()), ["-p", "PRE make a game"]);
        let options =
            BackendOptions { cli_model: Some("anthropic/claude-sonnet-4-6".into()), args: vec!["--max-turns".into(), "40".into()], ..Default::default() };
        assert_eq!(args(true, &options), ["-m", "anthropic/claude-sonnet-4-6", "--max-turns", "40", "-p", "PRE make a game"]);
    }

    #[test]
    fn outside_a_build_maki_can_only_read() {
        let a = args(false, &BackendOptions::default());
        assert_eq!(a, ["--disallowed-tools", CHANGES, "-p", "PRE make a game"]);
        for tool in ["write", "edit", "multiedit", "edit_lines", "bash", "code_execution"] {
            assert!(CHANGES.split(',').any(|t| t == tool), "{tool} is switched off");
        }
        assert!(!args(true, &BackendOptions::default()).contains(&"--disallowed-tools".to_string()), "a builder keeps its tools");
    }

    #[test]
    fn maki_is_registered_and_never_run_plain() {
        assert!(AgentAdapters::built_in().for_agent("maki").ids().contains(&"maki"), "registered, not the plain adapter");
        assert_eq!(Maki.required_flags(), (&["--help"][..], &["--print"][..]));
        assert!(!Maki.plain_fallback() && !Maki.streams_json());
    }
}
