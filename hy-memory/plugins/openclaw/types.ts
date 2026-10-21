/**
 * Shared type definitions for the OpenClaw HY Memory plugin.
 */

/** HY Memory processing mode (maps to SDK MEMORY_MODE) */
export type MemoryMode = "lite" | "pro" | "ultra";

export const MEMORY_MODES: readonly MemoryMode[] = ["lite", "pro", "ultra"] as const;

/** LLM provider configuration */
export interface LLMProviderConfig {
  provider: string;    // "openai" | "ollama" | "anthropic"
  model: string;
  apiKey?: string;
  baseUrl?: string;
  temperature?: number;
  maxTokens?: number;
  thinkingMode?: string;  // "disabled" | "enabled" | "auto"
}

/** Embedding provider configuration */
export interface EmbedderProviderConfig {
  provider: string;    // "openai" | "ollama" | etc.
  model: string;
  apiKey?: string;
  baseUrl?: string;
  dims?: number;
  extraHeaders?: Record<string, string>;
  extraBody?: Record<string, unknown>;
}

/** Vector store configuration */
export interface VectorStoreConfig {
  provider: string;    // "chroma" | "qdrant" | "faiss"
  host?: string;
  port?: number;
  apiKey?: string;
  collectionName?: string;
  persistDirectory?: string;
}

export interface HyMemoryConfig {
  /** Base URL of the HY Memory server */
  serverUrl: string;
  /** User ID for scoping memories */
  userId: string;
  /** Agent ID (default: "default_agent") */
  agentId: string;
  /** Session ID (default: "default_session") */
  sessionId: string;
  /**
   * SDK processing mode: lite (embed only) | pro (LLM extract) | ultra (pro + System 2 + Kuzu graph).
   * ultra always uses embedded Kuzu; no external graph service.
   */
  mode: MemoryMode;
  /** Auto-recall: inject relevant memories before each agent turn */
  autoRecall: boolean;
  /** Auto-capture: store conversation context after each agent turn */
  autoCapture: boolean;
  /** Max results for search */
  topK: number;
  /** Min score threshold for search */
  searchThreshold: number;
  /** Max results for profile memories */
  profileLimit: number;
  /** Min score threshold for profile memories */
  profileMinScore: number;
  /** Python executable path */
  pythonPath: string;
  /** Whether to auto-start the Python server */
  autoStartServer: boolean;
  /** Port for the Python server */
  serverPort: number;
  /** How many agent turns between each auto-capture write (default: 5) */
  memoryWriteTurnWindow: number;
  /** Whether setup is needed (server not reachable) */
  needsSetup?: boolean;

  /** LLM provider (for memory extraction / reconciliation) */
  llm?: LLMProviderConfig;
  /** Embedding provider */
  embedder?: EmbedderProviderConfig;
  /** Vector store backend */
  vectorStore?: VectorStoreConfig;
  /** Python server log level (default: "INFO") */
  logLevel?: string;
}

export interface MemoryItem {
  memory_id: string;
  content: string;
  score?: number;
  layer?: string;
  speculate?: string | null;
  source_raw_memory_id?: string | null;
  tags?: string[];
  memory_at?: string | null;
  gmt_created?: string | null;
  user_id?: string;
  agent_id?: string;
  session_id?: string;
}

export interface AddResult {
  success: boolean;
  memory_id: string;
  request_id: string;
  elapsed_ms: number;
  error_code?: number | null;
  error_message?: string | null;
}

export interface SearchResult {
  request_id: string;
  memories: MemoryItem[];
  elapsed_ms: number;
}

export interface ListBucket {
  memories: MemoryItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface GraphListBucket {
  nodes: MemoryItem[];
  total: number;
  limit: number;
  offset: number;
  isolation_key?: string;
}

export interface ListResult {
  vdb: ListBucket;
  graph?: GraphListBucket;
  elapsed_ms: number;
}

export interface DeleteResult {
  success: boolean;
  deleted_count: number;
  request_id: string;
  elapsed_ms: number;
}

export interface HyMemoryProvider {
  add(
    data: string | Array<{ role: string; content: string }>,
    options: {
      user_id: string;
      agent_id?: string;
      session_id?: string;
      enable_agent?: boolean;
      memory_at?: string;
    },
  ): Promise<AddResult>;

  addExtracted(
    contents: string | string[],
    options: {
      user_id: string;
      agent_id?: string;
      session_id?: string;
      memory_at?: string;
    },
  ): Promise<AddResult>;

  search(
    query: string,
    options: { user_id: string; user_ids?: string[]; agent_ids?: string[]; limit?: number; min_score?: number; profile_limit?: number; profile_min_score?: number },
  ): Promise<SearchResult>;

  get(memoryId: string): Promise<MemoryItem | null>;

  list(options: { user_id: string; agent_id?: string; limit?: number; offset?: number }): Promise<ListResult>;

  update(memoryId: string, content: string): Promise<AddResult>;

  delete(memoryId: string): Promise<DeleteResult>;

  deleteAll(options: { user_id: string; agent_ids?: string[]; session_ids?: string[] }): Promise<DeleteResult>;

  healthCheck(): Promise<boolean>;
}
