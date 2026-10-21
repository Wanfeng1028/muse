/**
 * Init Wizard — provider definitions, config builders, and connectivity checks.
 *
 * Extracted from index.ts for clarity. Used by the `openclaw hy-memory init` command.
 */

// ============================================================================
// Provider definitions
// ============================================================================

export interface ProviderDef {
  id: string;
  label: string;
  needsApiKey: boolean;
  needsUrl: boolean;
  defaultModel: string;
  defaultUrl?: string;
}

export interface EmbedderDef extends ProviderDef {
  defaultDims: number;
}

export interface VectorDef {
  id: string;
  label: string;
  needsConnection: boolean;
  defaultUrl?: string;
  setupHint?: string;
}

// ── LLM Providers ──────────────────────────────────────────────────────────

export const LLM_PROVIDERS: ProviderDef[] = [
  { id: "openai",     label: "OpenAI",                   needsApiKey: true,  needsUrl: false, defaultModel: "gpt-5.5-instant" },
  { id: "anthropic",  label: "Anthropic",                needsApiKey: true,  needsUrl: false, defaultModel: "claude-sonnet-4.6" },
  { id: "google",     label: "Google Gemini",            needsApiKey: true,  needsUrl: false, defaultModel: "gemini-3.1-pro",          defaultUrl: "https://generativelanguage.googleapis.com/v1beta/openai" },
  { id: "openrouter", label: "OpenRouter (multi-model)", needsApiKey: true,  needsUrl: false, defaultModel: "openrouter/auto",         defaultUrl: "https://openrouter.ai/api/v1" },
  { id: "deepseek",   label: "DeepSeek",                 needsApiKey: true,  needsUrl: false, defaultModel: "deepseek-v4-flash",       defaultUrl: "https://api.deepseek.com" },
  { id: "hunyuan",    label: "Hy (Tencent)",             needsApiKey: true,  needsUrl: false, defaultModel: "hy3-preview",             defaultUrl: "https://tokenhub.tencentmaas.com/v1" },
  { id: "moonshot",   label: "Moonshot (Kimi)",          needsApiKey: true,  needsUrl: false, defaultModel: "kimi-k2.5",               defaultUrl: "https://api.moonshot.cn/v1" },
  { id: "minimax",    label: "MiniMax",                  needsApiKey: true,  needsUrl: false, defaultModel: "minimax-m2.1",            defaultUrl: "https://api.minimax.chat/v1" },
  { id: "zhipu",      label: "Z.ai (智谱)",              needsApiKey: true,  needsUrl: false, defaultModel: "glm-4.7-flash",           defaultUrl: "https://open.bigmodel.cn/api/paas/v4" },
  { id: "ollama",     label: "Ollama (local, free)",     needsApiKey: false, needsUrl: true,  defaultModel: "qwen3-7b-instruct",       defaultUrl: "http://localhost:11434/v1" },
];

// ── Embedding Providers ────────────────────────────────────────────────────

export const EMBEDDER_PROVIDERS: EmbedderDef[] = [
  { id: "openai",   label: "OpenAI",                needsApiKey: true,  needsUrl: false, defaultModel: "text-embedding-3-small",  defaultDims: 768 },
  { id: "gemini",   label: "Google Gemini",          needsApiKey: true,  needsUrl: false, defaultModel: "text-embedding-004",      defaultDims: 768,  defaultUrl: "https://generativelanguage.googleapis.com/v1beta/openai" },
  { id: "aliyun",   label: "Aliyun Bailian (百炼)",  needsApiKey: true,  needsUrl: false, defaultModel: "text-embedding-v4",       defaultDims: 1024, defaultUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1" },
  { id: "moonshot", label: "Moonshot",               needsApiKey: true,  needsUrl: false, defaultModel: "moonshot-v1-embedding",   defaultDims: 1024, defaultUrl: "https://api.moonshot.cn/v1" },
  { id: "ollama",   label: "Ollama (local, free)",   needsApiKey: false, needsUrl: true,  defaultModel: "nomic-embed-text",        defaultDims: 768,  defaultUrl: "http://localhost:11434/v1" },
];

// ── Vector Store Providers ─────────────────────────────────────────────────

export const VECTOR_PROVIDERS: VectorDef[] = [
  { id: "chroma", label: "ChromaDB (embedded, zero setup)", needsConnection: false },
  { id: "qdrant", label: "Qdrant",                          needsConnection: true,  defaultUrl: "http://localhost:6333", setupHint: "docker run -d -p 6333:6333 qdrant/qdrant" },
  { id: "faiss",  label: "FAISS (local file)",               needsConnection: false },
];

// Known embedding dimensions by model name
export const KNOWN_EMBEDDER_DIMS: Record<string, number> = {
  "text-embedding-3-small": 768,
  "text-embedding-3-large": 3072,
  "text-embedding-ada-002": 1536,
  "text-embedding-004": 768,
  "text-embedding-v4": 1024,
  "moonshot-v1-embedding": 1024,
  "nomic-embed-text": 768,
  "mxbai-embed-large": 1024,
};

// ============================================================================
// Config builders
// ============================================================================

export interface LlmConfigInput {
  apiKey?: string;
  model?: string;
  url?: string;
}

export function buildLlmConfig(
  providerId: string,
  input: LlmConfigInput,
): Record<string, unknown> {
  const def = LLM_PROVIDERS.find((p) => p.id === providerId);
  if (!def) throw new Error(`Unknown LLM provider: ${providerId}`);

  const model = input.model || def.defaultModel;

  // Anthropic uses its own provider; everything else is OpenAI-compatible
  if (providerId === "anthropic") {
    return {
      provider: "anthropic",
      model,
      apiKey: input.apiKey,
    };
  }

  const config: Record<string, unknown> = {
    provider: "openai",
    model,
  };
  if (input.apiKey) config.apiKey = input.apiKey;

  // Set baseUrl for non-OpenAI providers
  const baseUrl = input.url || def.defaultUrl;
  if (baseUrl) config.baseUrl = baseUrl;

  // Always disable thinking for memory extraction — it wastes tokens and slows down writes
  config.thinkingMode = "disabled";

  return config;
}

export interface EmbedderConfigInput {
  apiKey?: string;
  model?: string;
  url?: string;
}

export function buildEmbedderConfig(
  providerId: string,
  input: EmbedderConfigInput,
): { config: Record<string, unknown>; dims: number } {
  const def = EMBEDDER_PROVIDERS.find((p) => p.id === providerId);
  if (!def) throw new Error(`Unknown embedder provider: ${providerId}`);

  const model = input.model || def.defaultModel;
  const dims = KNOWN_EMBEDDER_DIMS[model] ?? def.defaultDims;

  const config: Record<string, unknown> = {
    provider: "openai",
    model,
    dims,
  };
  if (input.apiKey) config.apiKey = input.apiKey;

  const baseUrl = input.url || def.defaultUrl;
  if (baseUrl) config.baseUrl = baseUrl;

  return { config, dims };
}

export function buildVectorConfig(
  providerId: string,
  input: { host?: string; port?: number },
): Record<string, unknown> {
  if (providerId === "qdrant") {
    return {
      provider: "qdrant",
      host: input.host || "localhost",
      port: input.port || 6333,
    };
  }
  // chroma / faiss: no extra config needed
  return { provider: providerId };
}

// ============================================================================
// Connectivity checks
// ============================================================================

export async function checkOllamaConnectivity(
  url: string,
): Promise<{ ok: boolean; error?: string }> {
  try {
    // Ollama's native endpoint (not the /v1 OpenAI compat)
    const base = url.replace(/\/v1\/?$/, "").replace(/\/+$/, "");
    const resp = await fetch(`${base}/api/tags`, {
      signal: AbortSignal.timeout(3000),
    });
    if (resp.ok) return { ok: true };
    return { ok: false, error: `Ollama returned HTTP ${resp.status}` };
  } catch {
    return {
      ok: false,
      error: `Cannot reach Ollama at ${url}. Install: https://ollama.com/download`,
    };
  }
}

// ============================================================================
// Interactive wizard (uses @clack/prompts for OpenClaw-style UI)
// ============================================================================

import {
  intro,
  outro,
  select,
  text,
  spinner,
  isCancel,
  cancel,
  note,
} from "@clack/prompts";
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { homedir, userInfo } from "node:os";

function getDefaultUserId(): string {
  try {
    return userInfo().username || "default";
  } catch {
    return "default";
  }
}

/**
 * Run the 4-step interactive init wizard.
 * Uses @clack/prompts for arrow-key selection, styled text input, and spinners.
 */
export async function runInitWizard(): Promise<void> {
  intro("🧠 HY Memory — Interactive Setup");

  // ── Step 1/4: LLM Provider ──────────────────────────────────────────

  const llmProviderId = await select({
    message: "Step 1/4: Choose your LLM provider (for memory extraction & reasoning)",
    options: LLM_PROVIDERS.map((p) => ({
      value: p.id,
      label: p.label,
      hint: p.defaultModel,
    })),
  });
  if (isCancel(llmProviderId)) { cancel("Setup cancelled."); process.exit(0); }

  const llmDef = LLM_PROVIDERS.find((p) => p.id === llmProviderId)!;

  let llmApiKey: string | undefined;
  let llmUrl: string | undefined;
  let llmModel: string | undefined;

  if (llmDef.needsApiKey) {
    const key = await text({
      message: `${llmDef.label} API Key`,
      placeholder: "sk-...",
      validate: (v) => (!v || v.length < 3 ? "API key is required" : undefined),
    });
    if (isCancel(key)) { cancel("Setup cancelled."); process.exit(0); }
    llmApiKey = key;
  }

  if (llmDef.needsUrl) {
    const url = await text({
      message: "API URL",
      initialValue: llmDef.defaultUrl || "",
    });
    if (isCancel(url)) { cancel("Setup cancelled."); process.exit(0); }
    llmUrl = url;

    if (llmProviderId === "ollama") {
      const s = spinner();
      s.start("Checking Ollama connectivity...");
      const check = await checkOllamaConnectivity(llmUrl || llmDef.defaultUrl || "");
      if (check.ok) {
        s.stop("Ollama connected ✓");
      } else {
        s.stop(`⚠ ${check.error}`);
      }
    }
  }

  const model = await text({
    message: "Model",
    initialValue: llmDef.defaultModel,
  });
  if (isCancel(model)) { cancel("Setup cancelled."); process.exit(0); }
  llmModel = model;

  const llmConfig = buildLlmConfig(llmProviderId as string, {
    apiKey: llmApiKey,
    model: llmModel,
    url: llmUrl,
  });

  // ── Step 2/4: Embedding Provider ────────────────────────────────────

  const embedProviderId = await select({
    message: "Step 2/4: Choose your embedding provider",
    options: EMBEDDER_PROVIDERS.map((p) => ({
      value: p.id,
      label: p.label,
      hint: `${p.defaultModel} (${p.defaultDims}d)`,
    })),
  });
  if (isCancel(embedProviderId)) { cancel("Setup cancelled."); process.exit(0); }

  const embedDef = EMBEDDER_PROVIDERS.find((p) => p.id === embedProviderId)!;

  let embedApiKey: string | undefined;
  let embedUrl: string | undefined;
  let embedModel: string | undefined;

  if (embedDef.needsApiKey) {
    // Smart reuse: if same provider family, suggest LLM key
    const canReuse = llmApiKey && (
      (embedProviderId === "openai" && llmProviderId === "openai") ||
      (embedProviderId === "gemini" && llmProviderId === "google") ||
      (embedProviderId === "moonshot" && llmProviderId === "moonshot")
    );
    const key = await text({
      message: `${embedDef.label} API Key`,
      initialValue: canReuse ? llmApiKey : undefined,
      placeholder: canReuse ? "(reusing LLM key)" : "sk-...",
      validate: (v) => (!v || v.length < 3 ? "API key is required" : undefined),
    });
    if (isCancel(key)) { cancel("Setup cancelled."); process.exit(0); }
    embedApiKey = key;
  }

  if (embedDef.needsUrl) {
    const url = await text({
      message: "API URL",
      initialValue: embedDef.defaultUrl || "",
    });
    if (isCancel(url)) { cancel("Setup cancelled."); process.exit(0); }
    embedUrl = url;

    if (embedProviderId === "ollama") {
      const s = spinner();
      s.start("Checking Ollama connectivity...");
      const check = await checkOllamaConnectivity(embedUrl || embedDef.defaultUrl || "");
      if (check.ok) {
        s.stop("Ollama connected ✓");
      } else {
        s.stop(`⚠ ${check.error}`);
      }
    }
  }

  const eModel = await text({
    message: "Embedding model",
    initialValue: embedDef.defaultModel,
  });
  if (isCancel(eModel)) { cancel("Setup cancelled."); process.exit(0); }
  embedModel = eModel;

  // Ask for embedding dimensions — important for vector store collection sizing
  const knownDims = KNOWN_EMBEDDER_DIMS[embedModel as string] ?? embedDef.defaultDims;
  const dimsInput = await text({
    message: "Embedding dimensions",
    initialValue: String(knownDims),
    validate: (v) => {
      const n = parseInt(v, 10);
      if (isNaN(n) || n <= 0) return "Must be a positive integer";
      return undefined;
    },
  });
  if (isCancel(dimsInput)) { cancel("Setup cancelled."); process.exit(0); }
  const finalDims = parseInt(dimsInput as string, 10);

  const { config: embedConfig } = buildEmbedderConfig(embedProviderId as string, {
    apiKey: embedApiKey,
    model: embedModel,
    url: embedUrl,
  });
  // Override dims with user-confirmed value
  embedConfig.dims = finalDims;

  // ── Step 3/4: Vector Store ──────────────────────────────────────────

  const vsProviderId = await select({
    message: "Step 3/4: Choose your vector store",
    options: VECTOR_PROVIDERS.map((p) => ({
      value: p.id,
      label: p.label,
      hint: p.needsConnection ? "requires server" : "no setup needed",
    })),
  });
  if (isCancel(vsProviderId)) { cancel("Setup cancelled."); process.exit(0); }

  const vsDef = VECTOR_PROVIDERS.find((p) => p.id === vsProviderId)!;
  let vsConfig: Record<string, unknown>;

  if (vsProviderId === "qdrant") {
    const host = await text({ message: "Qdrant host", initialValue: "localhost" });
    if (isCancel(host)) { cancel("Setup cancelled."); process.exit(0); }
    const port = await text({ message: "Qdrant port", initialValue: "6333" });
    if (isCancel(port)) { cancel("Setup cancelled."); process.exit(0); }

    vsConfig = buildVectorConfig("qdrant", { host: host as string, port: parseInt(port as string, 10) });

    const s = spinner();
    s.start("Checking Qdrant connectivity...");
    const check = await checkQdrantConnectivity(`http://${host}:${port}`);
    if (check.ok) {
      s.stop("Qdrant connected ✓");
    } else {
      s.stop(`⚠ ${check.error}`);
      if (vsDef.setupHint) {
        note(vsDef.setupHint, "Quick start");
      }
    }
  } else {
    vsConfig = buildVectorConfig(vsProviderId as string, {});
  }

  // ── Step 4/4: User ID ───────────────────────────────────────────────

  const userId = await text({
    message: "Step 4/4: User ID (your memory namespace)",
    initialValue: getDefaultUserId(),
  });
  if (isCancel(userId)) { cancel("Setup cancelled."); process.exit(0); }

  // ── Write config ────────────────────────────────────────────────────

  const pluginConfig = {
    userId,
    autoRecall: true,
    autoCapture: true,
    memoryWriteTurnWindow: 5,
    topK: 10,
    llm: llmConfig,
    embedder: embedConfig,
    vectorStore: vsConfig,
  };

  const configPath = join(homedir(), ".openclaw", "openclaw.json");
  try {
    const raw = readFileSync(configPath, "utf-8");
    const config = JSON.parse(raw);
    if (!config.plugins) config.plugins = {};
    if (!config.plugins.entries) config.plugins.entries = {};
    config.plugins.slots = { ...config.plugins.slots, memory: "openclaw-hy-memory" };
    config.plugins.entries["openclaw-hy-memory"] = {
      ...config.plugins.entries["openclaw-hy-memory"],
      enabled: true,
      hooks: { allowConversationAccess: true },
      config: pluginConfig,
    };
    if (!config.hooks) config.hooks = {};
    if (!config.hooks.internal) config.hooks.internal = { enabled: true, entries: {} };
    if (!config.hooks.internal.entries) config.hooks.internal.entries = {};
    config.hooks.internal.entries["session-memory"] = { enabled: true };

    writeFileSync(configPath, JSON.stringify(config, null, 2) + "\n");

    note(
      `LLM: ${llmDef.label} (${llmModel})\n` +
      `Embed: ${embedDef.label} (${embedModel})\n` +
      `Vector: ${vsDef.label}\n` +
      `User: ${userId}`,
      "Configuration saved"
    );

    outro("Setup complete! Run `openclaw gateway restart` to activate.");
  } catch (err) {
    cancel(`Failed to write config: ${err}`);
    console.log("\nManual config to add to ~/.openclaw/openclaw.json:");
    console.log(JSON.stringify({
      plugins: {
        slots: { memory: "openclaw-hy-memory" },
        entries: { "openclaw-hy-memory": { enabled: true, config: pluginConfig } },
      },
    }, null, 2));
  }
}

export async function checkQdrantConnectivity(
  url: string,
): Promise<{ ok: boolean; error?: string }> {
  try {
    const resp = await fetch(`${url.replace(/\/+$/, "")}/healthz`, {
      signal: AbortSignal.timeout(3000),
    });
    if (resp.ok) return { ok: true };
    return { ok: false, error: `Qdrant returned HTTP ${resp.status}` };
  } catch {
    return {
      ok: false,
      error: `Cannot reach Qdrant at ${url}. Start with: docker run -d -p 6333:6333 qdrant/qdrant`,
    };
  }
}
