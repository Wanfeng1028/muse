/**
 * Starting points for the connection form. Not a verified model catalog.
 *
 * These fill in an endpoint and a model name so a first-time user is not
 * typing a URL from memory. What they are not is a claim that the pairing
 * works today: verifying that would mean a paid call against the vendor,
 * which this project does not make on the user's behalf, so the only honest
 * basis is the vendor's own published OpenAI-compatible endpoint. Vendors
 * retire model ids far faster than they move endpoints, so treat every
 * `model` below as a field to confirm rather than a recommendation — the form
 * tests the pairing before anything is enabled, and every provider can be
 * overridden by hand.
 *
 * Provenance. Endpoints were read from vendor documentation on 2026-09-20;
 * model ids are the ones those same pages use in their own quickstart, which
 * is the most defensible default available without spending the user's money.
 * - OpenAI: the placeholder already shown by the model name field in
 *   `ModelSettings.tsx`. Never called from this repository.
 * - DeepSeek: vendor-compatible endpoint and a dated quickstart model id;
 *   `apps/core/tests/test_matter_discovery.py` uses the same endpoint shape.
 * - 阿里云百炼 / Kimi / 智谱 / 火山方舟 / 腾讯混元 / 硅基流动 / OpenRouter:
 *   vendor quickstart pages, 2026-09-20. Not called from this repository.
 * - Ollama: local, so the model depends entirely on what the user pulled.
 *   Left blank rather than guessing.
 *
 * Two shapes deliberately ship with an empty `model`, because guessing would
 * be worse than asking: Ollama depends on the local pull, and the aggregators
 * (OpenRouter, and to a lesser degree 硅基流动) require a namespaced id such
 * as `deepseek-ai/DeepSeek-V3`, which cannot be inferred. An empty model is
 * the signal the form uses to open the advanced panel straight away.
 *
 * `custom` is not listed here. It is appended by the caller so that picking it
 * clears every field instead of inheriting someone else's endpoint — see
 * `OnboardingModelController.tsx`. Anything not covered below is meant to go
 * through it, not to wait for this list to grow.
 */
export const PROVIDER_PRESETS = [
  {
    id: "openai",
    label: "OpenAI",
    provider: "openai_compatible",
    baseUrl: "https://api.openai.com/v1",
    model: "gpt-4o-mini",
  },
  {
    id: "deepseek",
    label: "DeepSeek",
    provider: "openai_compatible",
    baseUrl: "https://api.deepseek.com",
    model: "deepseek-flash",
  },
  {
    id: "dashscope",
    label: "阿里云百炼（通义千问）",
    provider: "openai_compatible",
    baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1",
    model: "qwen-flash",
  },
  {
    id: "moonshot",
    label: "Kimi（月之暗面）",
    provider: "openai_compatible",
    baseUrl: "https://api.moonshot.cn/v1",
    model: "kimi-k3",
  },
  {
    id: "zhipu",
    label: "智谱 GLM",
    provider: "openai_compatible",
    baseUrl: "https://open.bigmodel.cn/api/paas/v4",
    model: "glm-4-flash",
  },
  {
    id: "volcengine",
    label: "火山方舟（豆包）",
    provider: "openai_compatible",
    baseUrl: "https://ark.cn-beijing.volces.com/api/v3",
    // Ark accepts either a preset Model ID or the user's own Endpoint ID, and
    // the preset ids carry a dated suffix, so this one is especially likely
    // to need editing.
    model: "doubao-seed-2-1-pro-260628",
  },
  {
    id: "hunyuan",
    label: "腾讯混元",
    provider: "openai_compatible",
    baseUrl: "https://api.hunyuan.cloud.tencent.com/v1",
    model: "hunyuan-turbos-latest",
  },
  {
    id: "siliconflow",
    label: "硅基流动 SiliconFlow",
    provider: "openai_compatible",
    baseUrl: "https://api.siliconflow.cn/v1",
    model: "deepseek-ai/DeepSeek-V3",
  },
  {
    id: "openrouter",
    label: "OpenRouter",
    provider: "openai_compatible",
    baseUrl: "https://openrouter.ai/api/v1",
    // Namespaced ids only; there is no sensible default to pick for the user.
    model: "",
  },
  {
    id: "ollama",
    label: "Ollama（本机）",
    provider: "ollama",
    baseUrl: "http://127.0.0.1:11434",
    model: "",
  },
] as const;
