# Security

Craft Anything reads hostile files and runs other programs, so we take reports seriously.

## Reporting a vulnerability

Please report it privately: on GitHub, open the repository's **Security** tab and choose
**Report a vulnerability**. Don't open a public issue for it. Say what's affected, how to reproduce
it, and what an attacker gains. We'll reply within a week and tell you what we'll do.

## What counts

- A crash, hang or runaway memory use on any input file or website (never-crash is a hard rule:
  [AGENTS.md](AGENTS.md)).
- Code from a target running without the person's consent, or a tool doing more than its declared
  effects.
- A path that lets a coding agent act outside its project without approval.
- A key, token or other secret reaching a log, a tool's output, evidence or the repository.
- A plugin escaping its sandbox (WASM plugins import nothing; MCP plugins ask before each call).

## Supported versions

Fixes go into the latest release.
