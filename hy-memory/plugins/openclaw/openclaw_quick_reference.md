# OpenClaw Hy Memory Plugin - Quick Reference

## File Locations

| File | Purpose | Key Code |
|------|---------|----------|
| `plugins/openclaw/index.ts` | Plugin entry, lifecycle hooks, CLI | Auto-recall (line 564), Auto-capture (line 699), Server mgmt (line 101) |
| `plugins/openclaw/provider.ts` | HTTP API client | Search method (line 75), Add method (line 50) |
| `plugins/openclaw/types.ts` | TypeScript interfaces | SearchResult (line 97), MemoryItem (line 73) |
| `plugins/openclaw/config.ts` | Config parsing | buildServerEnv() (line 130) |
| `plugins/openclaw/tools/memory-search.ts` | Search tool | execute() memory iteration (line 45) |
| `plugins/openclaw/tools/memory-add.ts` | Add tool | execute() add logic (line 32) |
| `plugins/openclaw/tools/memory-list.ts` | List tool | execute() list logic (line 17) |
| `plugins/openclaw/tools/memory-get.ts` | Get tool | execute() get logic (line 15) |
| `plugins/openclaw/tools/memory-update.ts` | Update tool | execute() update logic (line 16) |
| `plugins/openclaw/tools/memory-delete.ts` | Delete tool | execute() delete logic (line 18) |

## Search Results Pattern - All Files That Process Them

```
Accessing result.memories:
  - index.ts line 574: if (!result.memories || result.memories.length === 0)
  - index.ts line 286: if (!result.memories.length)
  - index.ts line 290: for (const m of result.memories)
  - index.ts line 295: console.log(`\n${result.memories.length} result(s)`)
  - tools/memory-search.ts line 38: if (!result.memories || result.memories.length === 0)
  - tools/memory-search.ts line 45: result.memories.map(...)
  - tools/memory-list.ts line 29: if (!result.memories || result.memories.length === 0)
  - tools/memory-list.ts line 37: { total: result.total, memories: result.memories }
```

## Memory Search Process

### 1. Search Request (provider.ts line 75)
```typescript
POST /api/v1/search
{
  "query": "user query",
  "user_ids": ["user_id"],
  "limit": 10,
  "min_score": 0.3
}
```

### 2. Response Structure (types.ts line 97)
```typescript
{
  request_id: string;
  memories: MemoryItem[];    // Array of results
  elapsed_ms: number;
}
```

### 3. Memory Item Structure (types.ts line 73)
```typescript
{
  memory_id: string;          // UUID identifier
  content: string;            // Memory text
  score?: number;             // Similarity score 0-1
  layer?: string;             // Processing layer (L0, L1, etc.)
  speculate?: string | null;
  source_raw_memory_id?: string | null;
  tags?: string[];
  memory_at?: string | null;
  gmt_created?: string | null;
  user_id?: string;
  agent_id?: string;
  session_id?: string;
}
```

## Auto-Recall Integration (index.ts line 564)

**Trigger**: `before_prompt_build` hook  
**Condition**: `cfg.autoRecall === true`

```
Flow:
1. Agent about to build LLM prompt
2. Plugin intercepts with before_prompt_build hook
3. Calls provider.search(event.prompt, {...})
4. Formats memories into context block
5. Returns prependContext to inject into prompt
```

## Auto-Capture Integration (index.ts line 699)

**Trigger**: `agent_end` hook  
**Condition**: `cfg.autoCapture === true`

```
Flow:
1. Every agent turn completes (agent_end event)
2. Increment turn counter
3. Every 5th turn (CAPTURE_INTERVAL), call doCapture()
4. Extract messages since last cursor position
5. Call provider.add(incremental, {...}) to store
6. Update cursor position for next capture
7. On session_end, flush any remaining messages
```

## Memory Tool Calls

### memory_search
```typescript
{
  query: "search text",      // Required
  limit?: number,            // Optional, default: cfg.topK
  userId?: string            // Optional, default: cfg.userId
}
```

### memory_add
```typescript
{
  text?: string,             // Optional (mutually exclusive with messages)
  messages?: [               // Optional (mutually exclusive with text)
    { role: "user", content: "..." },
    { role: "assistant", content: "..." }
  ],
  userId?: string,           // Optional
  agentId?: string,          // Optional
  sessionId?: string         // Optional
}
```

### memory_list
```typescript
{
  userId?: string,           // Optional
  agentId?: string,          // Optional
  limit?: number             // Optional, default: 50
}
```

### memory_get
```typescript
{
  memoryId: string           // Required (UUID from search/list)
}
```

### memory_update
```typescript
{
  memoryId: string,          // Required (UUID from search/list)
  text: string               // Required (new content)
}
```

### memory_delete
```typescript
{
  memoryId?: string,         // Optional (UUID from search/list)
  all?: boolean,             // Optional (delete all for user)
  confirm?: boolean,         // Required if all=true
  userId?: string            // Optional (for --all)
}
```

## Environment Variables

**Set by**: `buildServerEnv()` in config.ts line 130

```
Core:
  MEMORY_ENABLE_AGENT = "true"
  MEMORY_ENABLE_GRAPH = "false"
  MEMORY_ENABLE_SEARCH_QUERY = "false"
  MEMORY_CACHE_BACKEND = "sqlite"

LLM:
  MEMORY_LLM_PROVIDER = cfg.llm.provider
  MEMORY_LLM_MODEL = cfg.llm.model
  MEMORY_LLM_API_KEY = cfg.llm.apiKey
  MEMORY_LLM_BASE_URL = cfg.llm.baseUrl
  MEMORY_LLM_TEMPERATURE = cfg.llm.temperature
  MEMORY_LLM_MAX_TOKENS = cfg.llm.maxTokens
  HY_MEMORY_THINKING_MODE = cfg.llm.thinkingMode

Embedder:
  MEMORY_EMBEDDER_PROVIDER = cfg.embedder.provider
  MEMORY_EMBEDDER_MODEL = cfg.embedder.model
  MEMORY_EMBEDDER_API_KEY = cfg.embedder.apiKey
  MEMORY_EMBEDDER_BASE_URL = cfg.embedder.baseUrl
  MEMORY_EMBEDDING_DIMS = cfg.embedder.dims

Vector Store:
  MEMORY_VECTOR_STORE = cfg.vectorStore.provider (default: "chroma")
  MEMORY_VECTOR_HOST = cfg.vectorStore.host
  MEMORY_VECTOR_PORT = cfg.vectorStore.port
  MEMORY_VECTOR_API_KEY = cfg.vectorStore.apiKey
  MEMORY_COLLECTION_NAME = cfg.vectorStore.collectionName
  MEMORY_PERSIST_DIR = cfg.vectorStore.persistDirectory

Logging:
  MEMORY_LOG_LEVEL = cfg.logLevel
```

## CLI Commands

```bash
# Server status
openclaw hy-memory status

# Search memories
openclaw hy-memory search "query" --limit 10 --user-id USER

# Add memory
openclaw hy-memory add "text to remember" --user-id USER

# List memories
openclaw hy-memory list --user-id USER --limit 50

# Inspect single memory
openclaw hy-memory inspect MEMORY_ID

# Delete memory
openclaw hy-memory delete MEMORY_ID

# Delete all (dangerous!)
openclaw hy-memory reset --yes

# Interactive setup wizard
openclaw hy-memory init
```

## Python Server Details

**Location**: Spawned in subprocess  
**Module**: `hy_memory.server`  
**Port**: `cfg.serverPort` (default: 19527)  
**Python Path**: `cfg.pythonPath` (default: "python3")  
**Venv**: `~/.openclaw/hy-memory-venv/`  
**Package**: `hy-memory` (auto-installed)

## Default Configuration

```json
{
  "serverUrl": "http://127.0.0.1:19527",
  "userId": "current_system_user",
  "agentId": "default_agent",
  "sessionId": "default_session",
  "autoRecall": false,
  "autoCapture": false,
  "topK": 10,
  "searchThreshold": 0.3,
  "pythonPath": "python3",
  "autoStartServer": true,
  "serverPort": 19527,
  "logLevel": "INFO",
  "llm": {
    "provider": "openai",
    "model": "gpt-4.1-nano"
  },
  "embedder": {
    "provider": "openai",
    "model": "text-embedding-3-small"
  },
  "vectorStore": {
    "provider": "chroma"  // Embedded, local, no external service
  }
}
```

## Code Location Map

| Functionality | File | Lines |
|---------------|------|-------|
| Plugin entry | index.ts | 1-776 |
| Plugin name & description | index.ts | 219-222 |
| Plugin registration | index.ts | 224-773 |
| Tool registration | index.ts | 233-236 |
| Auto-recall logic | index.ts | 563-596 |
| Auto-capture logic | index.ts | 599-745 |
| Python server startup | index.ts | 101-204 |
| CLI commands registration | index.ts | 242-556 |
| Lifecycle: gateway_start | index.ts | 755-767 |
| Lifecycle: gateway_stop | index.ts | 769-772 |
| HTTP search call | provider.ts | 75-95 |
| HTTP add call | provider.ts | 50-73 |
| HTTP list call | provider.ts | 109-118 |
| HTTP delete call | provider.ts | 126-141 |
| Memory item type | types.ts | 73-86 |
| Search result type | types.ts | 97-101 |
| Config schema | config.ts | 20-124 |
| Env var mapping | config.ts | 130-185 |
| Search tool | tools/memory-search.ts | 1-75 |
| Add tool | tools/memory-add.ts | 1-95 |
| List tool | tools/memory-list.ts | 1-48 |
| Get tool | tools/memory-get.ts | 1-44 |
| Update tool | tools/memory-update.ts | 1-38 |
| Delete tool | tools/memory-delete.ts | 1-60 |
| Tool registry | tools/index.ts | 1-28 |

## Key Search Patterns

- `result.memories.length` - Check if results exist
- `result.memories.map(r => ...)` - Process each result
- `for (const m of result.memories)` - Iterate results
- `r.score ?? 0` - Get similarity score
- `r.layer ?? "?"` - Get memory layer
- `r.memory_id` - Get result ID
- `r.content` - Get memory text

