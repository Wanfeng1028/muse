<!-- The title is the commit message (PRs are squash-merged): plain English, what changed for the
person or developer, with the roadmap id, e.g. "Decode radio recordings with rtl_433 (R3.1)". -->

**Roadmap item:** <!-- R1.4, R3.9… and the line you claimed in docs/ROADMAP.md -->

**What changed:**

**Verified:** <!-- tests run, and anything tried for real (a live build, a real file, a device) -->

**Not verified:** <!-- what you couldn't try, so the docs and STATUS say so -->

- [ ] `cargo fmt --all --check`, `cargo clippy -p <crates> --all-targets -- -D warnings`,
      `cargo test -p <crates>`, `cargo xtask layers`, `cargo xtask secrets`
- [ ] Docs in this PR: the roadmap line ticked (and new `- [ ]` lines for what's left), STATUS if
      what works changed, `cargo xtask tools` if tools were added
- [ ] No other tool's code, scripts or wording copied (behaviour only; AGENTS.md)
