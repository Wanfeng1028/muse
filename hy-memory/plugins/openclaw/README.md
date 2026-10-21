# OpenClaw Hy Memory Plugin

由腾讯混元团队研发的 [OpenClaw](https://github.com/nicepkg/openclaw) 插件，专注于为 AI Agent 提供智能长期记忆能力。

## Features

- **5 Memory Tools** — `memory_search`, `memory_add`, `memory_get`, `memory_update`, `memory_delete`
- **Auto-Recall** — Automatically injects relevant memories before each agent turn
- **Auto-Capture** — Stores key facts from conversations after each agent turn
- **Auto-Start Server** — Manages a local Python Hy Memory server automatically
- **Migrate Legacy Memories** — `import-from-openclaw` imports existing OpenClaw `memory-core` memories into Hy Memory
- **CLI Commands** — `openclaw hy-memory status`, `search`, `add`, `list`, `delete`, `reset`, `init`, `import-from-openclaw`

## Quick Start

### 1. Install the plugin

```bash
openclaw plugin install openclaw-hy-memory --dangerously-force-unsafe-install
```

> **为什么必须加 `--dangerously-force-unsafe-install`？**
>
> Hy-Memory 以 Python 子进程的方式随插件启动来提供服务。OpenClaw 出于安全考虑默认拒绝安装会启动外部进程的插件，因此需要显式加上该参数以确认你知晓并允许此行为。

### Windows

插件会自动使用 `~/.openclaw/hy-memory-venv`（venv 内为 `Scripts\python.exe`）。请确保系统已安装 **Python 3.9+** 且 `python` 在 PATH 中。一般无需改 `pythonPath`；若使用自定义解释器，填完整路径，例如 `D:\Python311\python.exe`。

### 2. Run the setup wizard

```bash
openclaw hy-memory init
```

This will guide you through configuring:
- **LLM Provider** — OpenAI, DeepSeek, Moonshot, Hunyuan, or Ollama (local)
- **Embedding Provider** — OpenAI, Aliyun Bailian, or Ollama
- **Vector Store** — Qdrant, ChromaDB (embedded), or FAISS

### 3. Restart the gateway

```bash
openclaw gateway restart
```

### 4. Verify services

```bash
openclaw hy-memory status
```

确认 VDB、Embed、LLM 三项服务均为 `ok` 状态。

## Manual Configuration

Add to `~/.openclaw/openclaw.json`:

```json
{
  "plugins": {
    "slots": { "memory": "openclaw-hy-memory" },
    "entries": {
      "openclaw-hy-memory": {
        "enabled": true,
        "hooks": { "allowConversationAccess": true },
        "config": {
          "userId": "your-username",
          "autoRecall": true,
          "autoCapture": true,
          "memoryWriteTurnWindow": 5,
          "topK": 10,
          "llm": {
            "provider": "openai",
            "model": "gpt-4.1-nano",
            "apiKey": "sk-your-key"
          },
          "embedder": {
            "provider": "openai",
            "model": "text-embedding-3-small",
            "apiKey": "sk-your-key"
          },
          "vectorStore": {
            "provider": "chroma"
          }
        }
      }
    }
  }
}
```

### Ultra mode (manual config only)

Not part of `openclaw hy-memory init`. Set `mode` in `openclaw.json` and restart the gateway:

```json
{
  "config": {
    "mode": "ultra",
    "logLevel": "DEBUG"
  }
}
```

Ultra uses embedded **Kuzu** under `~/.hy_memory/data/kuzu_db/` (no Neo4j). Requires `hy-memory` core package (includes `kuzu`).

## Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `serverUrl` | `http://127.0.0.1:19527` | Hy Memory server URL |
| `userId` | OS username | User ID for scoping memories |
| `agentId` | `default_agent` | Agent ID |
| `mode` | `pro` | `lite` / `pro` / `ultra`. `ultra` enables System 2 + embedded Kuzu graph (local, no extra service) |
| `autoRecall` | `false` | Inject memories before each turn |
| `autoCapture` | `false` | Store conversation after each turn |
| `memoryWriteTurnWindow` | `5` | Agent turns between each auto-capture write |
| `topK` | `10` | Max search results |
| `searchThreshold` | `0.3` | Min similarity score |
| `autoStartServer` | `true` | Auto-start Python server |
| `serverPort` | `19527` | Python server port |
| `llm` | — | LLM config (see below) |
| `embedder` | — | Embedding config (see below) |
| `vectorStore` | ChromaDB | Vector store config |

### LLM Config

```json
{
  "provider": "openai",
  "model": "deepseek-chat",
  "apiKey": "sk-...",
  "baseUrl": "https://api.deepseek.com"
}
```

Any OpenAI-compatible API works — just set `baseUrl` accordingly.

## CLI Commands

```bash
openclaw hy-memory status              # Check server connectivity
openclaw hy-memory search "query"      # Search memories
openclaw hy-memory add "text"          # Add a memory
openclaw hy-memory list                # List all memories
openclaw hy-memory delete <id>         # Delete a memory
openclaw hy-memory reset --yes         # Delete all memories
openclaw hy-memory init                # Setup wizard
openclaw hy-memory import-from-openclaw # Migrate legacy memory-core memories (see below)
```

## Migrating from OpenClaw memory-core

If you previously used OpenClaw's built-in **`memory-core`** (file-backed markdown
memory), this command imports those memories into Hy Memory. It reads the agent
workspace's `MEMORY.md` + `memory/**/*.md` and writes each file into Hy Memory via
`add`, which runs Hy Memory's LLM extraction to produce structured, layered memories.

```bash
# Interactive: preview the plan, confirm, then migrate
openclaw hy-memory import-from-openclaw

# Preview only (no server needed, nothing written)
openclaw hy-memory import-from-openclaw --dry-run

# Non-interactive
openclaw hy-memory import-from-openclaw --yes
```

**What gets imported (automatic — no modes to choose)**
- `MEMORY.md` (long-term) + daily notes (`memory/*.md`).
- Session transcripts (`agents/<id>/sessions/*.jsonl`) **only for days that have no
  daily note** — a daily note already digests that day's sessions, so importing both
  would double-count.
- `memory/dreaming/**` is **not** imported.

**Key behaviours**
- **Chronological**: items are imported in `memory_at` order (oldest → newest), so HY
  Memory's evolution/dedup/recency logic sees the correct time order.
- **Per-file**: each markdown file is one `add` (oversized files are split on blank lines).
- **Timestamps preserved**: daily-note dates / file mtimes / session timestamps → `memory_at`.
- **Idempotent + resumable**: a ledger at `<workspace>/.hy-memory-import.json` records imported files by content hash; re-running skips unchanged files and imports only the delta. Use `--force` to re-import everything.
- **Ordered + gentle writes**: writes are **sequential** (to preserve order) with a small inter-write delay and exponential-backoff retry on transient errors (429 / rate-limit / 5xx, `--retries`).
- **Traceable / rollback**: imported memories are tagged `session_id = "imported-from-openclaw"`.

**Options**

| Option | Default | Description |
|--------|---------|-------------|
| `--workspace <dir>` | auto | OpenClaw agent workspace (auto-detected from config) |
| `--agent <id>` | `main` | OpenClaw agent id (locates workspace + sessions) |
| `--state-dir <dir>` | `$OPENCLAW_STATE_DIR` or `~/.openclaw` | OpenClaw state dir holding `openclaw.json` |
| `--user-id <id>` | configured `userId` | Target Hy Memory user id |
| `--dry-run` | off | Preview the plan without writing |
| `--force` | off | Re-import everything, ignoring the ledger |
| `--retries <n>` | `4` | Retries per unit on transient errors |
| `--yes` | off | Skip the confirmation prompt |

> Requires the Hy Memory server to be reachable (it runs a pre-flight health
> check). For `--dry-run` no server is needed.

## Development

```bash
cd plugins/openclaw/
npm install
npm run build
```

## License

Apache-2.0. See the repository root [LICENSE](../../LICENSE).
