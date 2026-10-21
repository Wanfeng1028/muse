/**
 * Configuration parsing for the OpenClaw HY Memory plugin.
 */

import { userInfo } from "node:os";
import type {
  HyMemoryConfig,
  LLMProviderConfig,
  EmbedderProviderConfig,
  VectorStoreConfig,
  MemoryMode,
} from "./types.ts";
import { MEMORY_MODES } from "./types.ts";

const DEFAULT_SERVER_PORT = 19527;
const DEFAULT_MODE: MemoryMode = "pro";

function parseMemoryMode(raw: unknown): MemoryMode {
  if (typeof raw !== "string") return DEFAULT_MODE;
  const mode = raw.toLowerCase().trim() as MemoryMode;
  if ((MEMORY_MODES as readonly string[]).includes(mode)) return mode;
  return DEFAULT_MODE;
}

function parseSubConfig<T>(raw: unknown, defaults: T): T {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return defaults;
  return { ...defaults, ...(raw as Record<string, unknown>) } as T;
}

export const hyMemoryConfigSchema = {
  parse(value: unknown): HyMemoryConfig {
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      throw new Error("openclaw-hy-memory config required");
    }
    const cfg = value as Record<string, unknown>;

    const serverPort =
      typeof cfg.serverPort === "number" ? cfg.serverPort : DEFAULT_SERVER_PORT;

    let defaultUserId: string;
    try {
      defaultUserId = userInfo().username || "default";
    } catch {
      defaultUserId = "default";
    }

    // LLM config
    let llm: LLMProviderConfig | undefined;
    if (cfg.llm && typeof cfg.llm === "object") {
      const raw = cfg.llm as Record<string, unknown>;
      llm = {
        provider: typeof raw.provider === "string" ? raw.provider : "openai",
        model: typeof raw.model === "string" ? raw.model : "gpt-4.1-nano",
        apiKey: typeof raw.apiKey === "string" ? raw.apiKey : undefined,
        baseUrl: typeof raw.baseUrl === "string" ? raw.baseUrl : undefined,
        temperature: typeof raw.temperature === "number" ? raw.temperature : undefined,
        maxTokens: typeof raw.maxTokens === "number" ? raw.maxTokens : undefined,
        thinkingMode: typeof raw.thinkingMode === "string" ? raw.thinkingMode : undefined,
      };
    }

    // Embedder config
    let embedder: EmbedderProviderConfig | undefined;
    if (cfg.embedder && typeof cfg.embedder === "object") {
      const raw = cfg.embedder as Record<string, unknown>;
      embedder = {
        provider: typeof raw.provider === "string" ? raw.provider : "openai",
        model:
          typeof raw.model === "string"
            ? raw.model
            : "text-embedding-3-small",
        apiKey: typeof raw.apiKey === "string" ? raw.apiKey : undefined,
        baseUrl: typeof raw.baseUrl === "string" ? raw.baseUrl : undefined,
        dims: typeof raw.dims === "number" ? raw.dims : undefined,
        extraHeaders: raw.extraHeaders && typeof raw.extraHeaders === "object" ? raw.extraHeaders as Record<string, string> : undefined,
        extraBody: raw.extraBody && typeof raw.extraBody === "object" ? raw.extraBody as Record<string, unknown> : undefined,
      };
    }

    // Vector store config (default: chroma embedded, zero external deps)
    let vectorStore: VectorStoreConfig | undefined;
    if (cfg.vectorStore && typeof cfg.vectorStore === "object") {
      const raw = cfg.vectorStore as Record<string, unknown>;
      vectorStore = {
        provider: typeof raw.provider === "string" ? raw.provider : "chroma",
        host: typeof raw.host === "string" ? raw.host : undefined,
        port: typeof raw.port === "number" ? raw.port : undefined,
        apiKey: typeof raw.apiKey === "string" ? raw.apiKey : undefined,
        collectionName:
          typeof raw.collectionName === "string"
            ? raw.collectionName
            : undefined,
        persistDirectory:
          typeof raw.persistDirectory === "string"
            ? raw.persistDirectory
            : undefined,
      };
    }

    return {
      serverUrl:
        typeof cfg.serverUrl === "string" && cfg.serverUrl
          ? cfg.serverUrl
          : `http://127.0.0.1:${serverPort}`,
      userId:
        typeof cfg.userId === "string" && cfg.userId
          ? cfg.userId
          : defaultUserId,
      agentId:
        typeof cfg.agentId === "string" && cfg.agentId
          ? cfg.agentId
          : "default_agent",
      sessionId:
        typeof cfg.sessionId === "string" && cfg.sessionId
          ? cfg.sessionId
          : "default_session",
      mode: parseMemoryMode(cfg.mode),
      autoRecall: cfg.autoRecall === true,
      autoCapture: cfg.autoCapture === true,
      topK: typeof cfg.topK === "number" ? cfg.topK : 5,
      searchThreshold:
        typeof cfg.searchThreshold === "number" ? cfg.searchThreshold : 0.4,
      profileLimit:
        typeof cfg.profileLimit === "number" ? cfg.profileLimit : 5,
      profileMinScore:
        typeof cfg.profileMinScore === "number" ? cfg.profileMinScore : 0.4,
      pythonPath:
        typeof cfg.pythonPath === "string" && cfg.pythonPath
          ? cfg.pythonPath
          : (process.platform === "win32" ? "python" : "python3"),
      autoStartServer: cfg.autoStartServer !== false,
      serverPort,
      memoryWriteTurnWindow:
        typeof cfg.memoryWriteTurnWindow === "number" && cfg.memoryWriteTurnWindow > 0
          ? cfg.memoryWriteTurnWindow
          : 5,
      logLevel: typeof cfg.logLevel === "string" ? cfg.logLevel : undefined,
      llm,
      embedder,
      vectorStore,
    };
  },
};

/**
 * Build environment variables from plugin config to pass to the Python server.
 * These map to the SDK's MemoryConfig environment variables.
 */
export function buildServerEnv(cfg: HyMemoryConfig): Record<string, string> {
  const env: Record<string, string> = {};

  // SDK mode: lite | pro | ultra (ultra enables System 2 + embedded Kuzu graph)
  env.MEMORY_MODE = cfg.mode;

  if (cfg.mode === "ultra") {
    // OpenClaw C-end: graph is always local embedded Kuzu (no Neo4j/Memgraph option)
    env.MEMORY_GRAPH_PROVIDER = "kuzu";
  }

  // Reconcile: 不用 LLM 扩写 search query；每条新 memory 直接 hybrid 检索（向量池 limit×3 + BM25）
  env.MEMORY_ENABLE_SEARCH_QUERY = "false";

  // Use SQLite cache (no Redis dependency)
  env.MEMORY_CACHE_BACKEND = "sqlite";

  // C-end: skip SQLite pipeline trace (Inspector); JSONL pipeline log stays on
  env.MEMORY_PIPELINE_TRACE_ENABLED = "false";

  // LLM
  if (cfg.llm) {
    if (cfg.llm.provider) env.MEMORY_LLM_PROVIDER = cfg.llm.provider;
    if (cfg.llm.model) env.MEMORY_LLM_MODEL = cfg.llm.model;
    if (cfg.llm.apiKey) env.MEMORY_LLM_API_KEY = cfg.llm.apiKey;
    if (cfg.llm.baseUrl) env.MEMORY_LLM_BASE_URL = cfg.llm.baseUrl;
    if (cfg.llm.temperature != null) env.MEMORY_LLM_TEMPERATURE = String(cfg.llm.temperature);
    if (cfg.llm.maxTokens != null) env.MEMORY_LLM_MAX_TOKENS = String(cfg.llm.maxTokens);
    if (cfg.llm.thinkingMode) env.HY_MEMORY_THINKING_MODE = cfg.llm.thinkingMode;
  }

  // Embedder
  if (cfg.embedder) {
    if (cfg.embedder.provider) env.MEMORY_EMBEDDER_PROVIDER = cfg.embedder.provider;
    if (cfg.embedder.model) env.MEMORY_EMBEDDER_MODEL = cfg.embedder.model;
    if (cfg.embedder.apiKey) env.MEMORY_EMBEDDER_API_KEY = cfg.embedder.apiKey;
    if (cfg.embedder.baseUrl) env.MEMORY_EMBEDDER_BASE_URL = cfg.embedder.baseUrl;
    if (cfg.embedder.dims) env.MEMORY_EMBEDDING_DIMS = String(cfg.embedder.dims);
    if (cfg.embedder.extraHeaders) env.MEMORY_EMBEDDER_EXTRA_HEADERS = JSON.stringify(cfg.embedder.extraHeaders);
  }

  // Force float embeddings by default. Some OpenAI-compatible gateways (e.g. the
  // internal LLM gateway / 蒸馏平台) cannot parse the openai SDK's default base64
  // embedding response and return HTTP 502. Requesting float is harmless for
  // OpenAI itself. Any user-provided embedder.extraBody keys take precedence.
  env.MEMORY_EMBEDDER_EXTRA_BODY = JSON.stringify({
    encoding_format: "float",
    ...(cfg.embedder?.extraBody ?? {}),
  });

  // Vector store (default: chroma embedded, zero external deps)
  if (cfg.vectorStore) {
    if (cfg.vectorStore.provider) env.MEMORY_VECTOR_STORE = cfg.vectorStore.provider;
    if (cfg.vectorStore.host) env.MEMORY_VECTOR_HOST = cfg.vectorStore.host;
    if (cfg.vectorStore.port) env.MEMORY_VECTOR_PORT = String(cfg.vectorStore.port);
    if (cfg.vectorStore.apiKey) env.MEMORY_VECTOR_API_KEY = cfg.vectorStore.apiKey;
    if (cfg.vectorStore.collectionName) env.MEMORY_COLLECTION_NAME = cfg.vectorStore.collectionName;
    if (cfg.vectorStore.persistDirectory) env.MEMORY_PERSIST_DIR = cfg.vectorStore.persistDirectory;
  } else {
    // No vector store configured: use chroma embedded (local files, no external service)
    env.MEMORY_VECTOR_STORE = "chroma";
  }

  // Log level
  if (cfg.logLevel) env.MEMORY_LOG_LEVEL = cfg.logLevel.toUpperCase();

  return env;
}
