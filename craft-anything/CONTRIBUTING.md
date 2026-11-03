# Contributing

Thanks for helping. The rules every change follows (people and AI agents alike) are in
[AGENTS.md](AGENTS.md); the mistakes they come from are in [docs/pitfalls.md](docs/pitfalls.md).
In short:

- **Pick work from [docs/ROADMAP.md](docs/ROADMAP.md)** (`cargo xtask pending` lists what's open).
  Claim it first: add `— claimed: <your name>, branch <branch>` to its line and open a draft PR,
  so nobody else does the same work.
- **One change per PR**, on a branch named `feature/`, `bugfix/`, `docs/`, `test/`, `refactor/` or
  `chore/` plus the roadmap id (`feature/r1.4-provider-key-ui`). PRs are squash-merged, so the
  title is the commit message: plain English, what changed for the person or developer.
- **Where things go:** [docs/extending.md](docs/extending.md) (tools, target kinds, checks, coding
  agents, engines, plugins).
- **Never crash, safe Rust only, every external program through `craft_anything_platform::process`,
  no secrets or personal data anywhere.** Everything is our own work: no code, names or wording copied from other projects.

Before you ask for review:

```sh
cargo fmt --all
cargo test -p <crates you touched>
cargo clippy -p <crates> --all-targets -- -D warnings
cargo xtask layers
cargo xtask secrets
```

Enable the secret-scan hook once per clone: `git config core.hooksPath .githooks`.

Code is dual-licensed under MIT or Apache-2.0 ([LICENSE-MIT](LICENSE-MIT),
[LICENSE-APACHE](LICENSE-APACHE)); by contributing you agree your work is licensed the same way.
