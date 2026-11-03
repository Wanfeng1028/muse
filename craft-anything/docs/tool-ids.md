# Tool ids

Every tool has one id. The id is the MCP tool name and the agent's tool name, and its kebab-case
form is the CLI command.

## The scheme

`<area>_<object>_<action>`, all lower case, words joined by `_`:

- **area**: `core`, `native`, `managed`, `java`, `android`, `apple`, `harmony`, `js`, `web`, `app`,
  `firmware`, `formats`, `radio`, `packets`, `db`, `assets`, `game`, `project`, `rebuild`, `build`,
  `runtime`, `adb`, `frida`, `engines`, `settings`, `plugins`, `setup` (the list is
  `registry::AREAS`).
- **object**: what it works on, plural for collections (`functions`, `page`, `feed`, `inbox`).
- **action**: a plain verb (`list`, `show`, `open`, `capture`, `compare`, `start`, `answer`).

Examples: `native_functions_list`, `native_function_pseudocode`, `web_page_capture`,
`project_feed_show`, `rebuild_start`, `engines_ghidra_install`.

Ids can't contain dots or spaces: MCP clients and model APIs accept only letters, digits, `_` and
`-` in tool names. The CLI spelling swaps `_` for `-` (`craft-anything-cli web-page-capture`).

## Rules

- New tools use the scheme from the start; a test checks every id follows it.
- The Rust function behind a tool has the tool's id as its name.
- Text that agents and people read (prompts, summaries, errors) names tools by their ids.
- Code never decides on a tool's name as text: it compares `Registry::canonical(name)` (which
  covers CLI names and `mcp__<server>__<name>`), reads a declared fact from the tool
  (`Effects::CARRIES_TARGET_CONTENT`), or uses the id constant kept next to the tool
  (`PSEUDOCODE_TOOL`, `APPROVE_TOOL`, `SESSION_TOOL`).
- MCP prompts follow the same scheme (`core_feature_explain`, `native_crash_explain`,
  `core_unknowns_review`, `runtime_run_plan`, `app_graphs_compare`,
  `app_rebuild_claim_check`).
