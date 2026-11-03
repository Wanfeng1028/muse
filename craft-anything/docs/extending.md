# Extending Craft Anything

Every part people tend to change sits behind a seam: a trait or a table with built-in entries and one
place to add yours. Follow `AGENTS.md` (never crash, layers, external programs through
`craft_anything_platform::process`) and give each addition tests.

| You want to add | Where | How |
|---|---|---|
| A tool | `crates/engine/src/tools/<area>.rs` | A `ToolSpec` (id per [tool-ids.md](tool-ids.md), title, summary, beginner text, toolset, honest effects, a schemars params type, `run`), and one `v.extend(<area>::specs())` line in `tools/mod.rs`. It's then a CLI command, an MCP tool and callable by the agent and the app. It runs only in Deep mode until it's listed in `crates/engine/src/clean_room.rs`; list it there only if it touches no target or watches from outside, as a visitor or user would. |
| A tool from a higher layer | that crate, e.g. `crates/ai/src/rebuild/tools.rs` | Static `ToolSpec`s passed to `Engine::shared(session, extra)`; reach the engine through `ctx.session.ext.get::<EngineRef>()`. Never block a tool on work that calls back into the engine: start it and return. |
| A kind of thing to make | `crates/ai/src/rebuild/kinds/` | Implement `TargetKind` (detection score, default stack, brief sections, checks, refine message, the app's words) and `KindRegistry::register` it. |
| A way to judge a build | `crates/ai/src/rebuild/kinds/` | Implement `Check` (`run(&mut CheckCx) -> CheckResult`; `applies` to skip it in some runs, or wrap it in `DeepOnly`); return it from your kind's `checks`. Decide on `passed`/`similarity`, never on text. |
| A stack | `crates/ai/src/rebuild/stacks.toml` | One `[[stack]]` entry: name, the builder's steps, the phrases that ask for it, its engine, the package.json dependencies that show a build uses it. A component or styling library is a `[[library]]` entry (name, phrases, the stacks it works with, steps). |
| A coding agent | `crates/ai/src/cli_agents/adapters.rs` | Implement `AgentAdapter` (args, required flags, stream parsing, resume, sign-in check) and register it in `AgentAdapters`. Agents it doesn't know run with the plain adapter. An agent that speaks ACP needs only a row in `cli_agents::acp::ACP_AGENTS` (its id and the arguments that start ACP mode); if its ACP mode takes the backend's model, a row in `ACP_MODEL_FLAGS` too. |
| An asset provider | `crates/engines/src/assets/` | Implement `AssetProvider` (`key_env` names its environment variable); add its models and prices to `assets.toml`. Its key is its own: `assets_key_set` with `provider`, kept as `assets:<id>`. |
| An external engine | `crates/engines/src/table.rs` | One `ExternalEngine` entry (exes, known paths, what it's for, install pins with SHA-256 checked against the publisher), plus a `tool_paths!` id in `settings.rs` if people can point at their own install. |
| A front end for builds | anywhere above L5 | Hold a `rebuild::RunSet` (it queues past its limit) and `poll` it; test it with `RunSet::with_starter(StandIns::starter())`, whose runs report only what the test sends. |
| A persisted file | its owner module | A version field and a migration step; see [file-formats.md](file-formats.md). |
| A UI language | `crates/ui-egui/src/i18n/` and `i18n.rs` | Add a TSV catalog and a language registry entry; preserve placeholders and run the catalog tests and `cargo xtask i18n-coverage`. See [localisation](localization.md) for scope and font setup. |

## Plugins: external MCP servers

Any MCP server, local (stdio) or remote (Streamable HTTP), can add tools without changing code.
Add it in Settings → Plugins, with `plugins_add` (`craft-anything-cli plugins-add --id notes
--command notes-mcp --args '["--stdio"]'`), or list it in `config.toml`. A plugin added through the tool
or the app always asks before each call; `plugins_remove` takes one away.

```toml
[[plugins.mcp]]
id = "notes"            # its toolset id; its tools become notes_<tool>
name = "Notes"          # shown to people (default: the id)
command = "notes-mcp"
args = ["--stdio"]
consent = true          # ask before each call (the default): it runs someone else's code
# enabled = false       # keep it configured but off
# env = { NOTES_DIR = "C:/notes" }

[[plugins.mcp]]
id = "docs"             # a remote server: url instead of command
url = "https://mcp.example.com/mcp"   # https, or http:// to this computer
headers = { Authorization = "Bearer …" }
```

Then `craft-anything-cli plugins-refresh --allow-run` starts it once and caches its tool list; from
the next start its tools are offered everywhere, in a toolset of their own (MCP agents enable it with
`enable_toolset`). `plugins-list` shows what's configured and cached.

- A local server starts on its first call and stays up for the session; one that exits is started
  again. A remote one is reached on its first call; its session id is sent back with each request.
- Effects come from the server's tool annotations (`readOnlyHint`, `destructiveHint`,
  `openWorldHint`), plus launching a process (local) or the network (remote). With
  `consent = true` every call asks first.
- `env` and `headers` values are never shown by `settings_show` or `plugins_list`.
- Another transport implements `engines::mcp_client::Transport` and is passed to
  `McpClient::with_transport`.
- Results are recorded as evidence from an external service (`engine: plugin:<id>`).
- Tool ids are `<plugin id>_<tool name>`, lower-cased with `_` for anything else; a clash is skipped
  and logged.

## Plugins: WASM components

A build with `--features wasm-plugins` (it compiles wasmtime, so it's off by default) also loads
WASM components. A component exports `craft-anything:plugin/tools` from
[`crates/engines/wit/plugin.wit`](../crates/engines/wit/plugin.wit): `describe` returns its tools
(name, title, description, input schema) as JSON, and `call(name, input)` answers
`{"ok": …}` or `{"error": "…"}`. List it in `config.toml`:

```toml
[[plugins.wasm]]
id = "wordtools"        # its toolset id; its tools become wordtools_<tool>
path = "C:/plugins/wordtools.wasm"
```

- It may also (or instead) export `craft-anything:plugin/checks`: ways of judging a build, run
  after the built-in checks of each round for the kinds of project they name. A check gets the
  build as JSON (every file's path and size, plus the text of the extensions it asks for) and
  answers passed, an optional 0-100 similarity and a summary; a failed one is shown to the builder
  to fix. Asset providers can't be plugins: they need the network.
- It may import nothing: no files, network, environment or clock, so its tools run without asking.
- Each call runs in a fresh instance with a work limit (fuel) and 256 MiB of memory; one that runs
  past them is stopped with an error.
- A plugin that can't be loaded, or a tool whose id is invalid or taken, is skipped and logged.
- Complete plugins in Rust, with build steps: a tool,
  [`examples/wasm-plugin-wordcount`](../examples/wasm-plugin-wordcount), and a check,
  [`examples/wasm-plugin-readme-check`](../examples/wasm-plugin-readme-check).

### Plugin API versions

The plugin API is `package craft-anything:plugin@<version>` in `plugin.wit`, versioned with semver;
a plugin exports the interfaces at the version it was built against
(`craft-anything:plugin/tools@0.1.0`).

- **Compatible means the same major version, and while it's 0.x the same minor too** (0.1.0 and
  0.1.7 work together; 0.2.0 doesn't). Craft Anything loads a compatible plugin whatever its patch
  version, and refuses an incompatible one by name ("exports … for API 0.2.0; this Craft Anything
  speaks 0.1.0") instead of silently skipping it.
- **A patch version only adds optional JSON fields**: in what a plugin returns (Craft Anything
  ignores fields it doesn't know) and in what it's given (plugins must ignore unknown fields too).
- **A minor version (while 0.x) or a major one** is anything else: a new or changed function, a
  field that becomes required, a changed meaning. The host's `API_VERSION`
  (`engines::wasm_plugin`) and the WIT package move together; a test checks they agree.

Code that defines tools at run time itself (a WASM host, a proxy for another protocol) uses
`registry::RuntimeTool` with `Engine::shared_with`: owned names, a JSON schema, and a function that
serves its tools, telling them apart by `ctx.tool`.
