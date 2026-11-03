# Using Claude Code as the builder

Craft Anything can build with the person's own local Claude Code. This page records what the
integration does, why it is shaped this way, and what remains to confirm.

## How it works

- Craft Anything finds the `claude` program on the computer (PATH or `~/.local/bin`) and runs it
  as a child process in headless mode, as documented by Anthropic: `claude -p <task>
  --output-format stream-json --verbose`, with `--resume <session>` to continue a project.
- The working folder is the project folder. Craft Anything's own tools are offered through
  `--mcp-config` (our MCP server, `craft-anything-cli mcp --project … --inbox …`) with
  `--strict-mcp-config`. A build checks that `craft-anything-cli` starts before doing anything
  else, and says so plainly if not. Without the server Claude Code stops at its first approval
  with `MCP tool mcp__craft-anything__core_action_approve … not found. Available MCP tools: none`,
  and its MCP log blames an executable called `stdio`: that's Claude Code's wording for a command
  that wouldn't start, whatever the command was, not something in our config.
- Our MCP server runs in the build's mode (`--deep` or `--clean-room`); in Deep mode it lists
  every tool (`--all-tools`).
- Permissions: read-only tools (`Read`, `Glob`, `Grep`) and our MCP tools are pre-allowed in Deep
  mode. In Clean room only `TodoWrite` is: reads go through the approval tool too, which refuses
  anything in the original's folder or on its site (the project folder excepted).
  Every other action (writing files, running commands, fetching the web) goes through
  `--permission-prompt-tool mcp__craft-anything__core_action_approve`. That tool allows edits
  inside the project's `app/` folder and a fixed list of build commands (`npm install`,
  `npm run build`, `cargo build`…), refuses dev servers (they never exit), and asks the person
  in the app for anything else ("Allow once / Always for this project / Don't allow").
- Questions: Claude Code's own question tool is disabled for these runs (`--disallowedTools
  AskUserQuestion`); the agent uses our `core_person_ask` tool, which shows a card with buttons.
- Before a build starts, `claude auth status` is checked. If Claude Code isn't signed in, the run
  stops with: "Sign in to Claude Code: open a terminal and run `claude auth login`".

## Why this is within Anthropic's terms (as published, October 2026)

From Claude Code's *Legal and compliance* page:

- Third-party developers may not offer Claude.ai login in their own apps, route requests through
  Free/Pro/Max credentials on users' behalf, or collect, store or intermediate Claude.ai
  credentials or session tokens. Sign-in must complete through Anthropic's own flow.
- This "does not … prevent an end user from signing in to the unmodified Claude Code binary with
  their own Claude subscription".
- Products that run Claude Code must not modify the binary or disable its authentication
  methods, and may not pay for, resell or intermediate Claude usage.

Craft Anything:

- runs the unmodified `claude` binary that the person installed;
- never reads, stores or forwards credentials or tokens, and offers no Claude login of its own
  (sign-in happens in Claude Code: `claude auth login`);
- doesn't pay for, resell or meter Claude usage — usage is billed to the person under their own
  agreement;
- uses only documented flags (headless mode, MCP config, permission-prompt tool);
- describes it in plain text ("Builds with Claude Code") and doesn't use Anthropic's logos or
  the Claude Code name as a product or feature name.

## Whose account and terms

Craft Anything is open source and runs on the person's own computer. Whoever runs it runs their
own Claude Code, signed in to their own account, so their use falls under their agreement with
Anthropic, as with any other script that calls `claude -p`. The free release ships on that basis.
The questions below matter for a paid offering, where we would be the party.

## Open questions (need confirmation before a paid offering)

1. The Agent SDK overview says third-party developers may not "offer claude.ai login or rate
   limits for their products, including agents built on the Claude Agent SDK" without approval.
   Craft Anything doesn't offer a login, but it does let a person's subscription do work that
   our app orchestrates. The legal page explicitly allows end users to use their own
   subscription with the unmodified binary, which is what we do. Still, **confirm with Anthropic
   (sales/partnerships) that orchestrating the user's own CLI this way is acceptable at scale**,
   especially for the planned managed-subscription tier.
2. "Advertised usage limits for Pro and Max plans assume ordinary, individual usage." Rebuild
   rounds are bounded (default: first build + up to 6 refinements in the app, 2 in the CLI; `--rounds` changes it) to keep
   usage ordinary.
3. The managed tier (we pay for model access) must use the Claude API with our own key under
   the Commercial Terms, never users' subscriptions.

## The compliant alternative

If the subscription route is ever unsuitable, the same workflow runs with API-key backends:
Settings → AI → Anthropic (Claude API) or OpenRouter. Today those backends answer questions and
analyse targets; building with them needs a file-writing tool loop in our own agent (see
docs/STATUS.md, "Next").
