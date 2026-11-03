/**
 * 火山方舟 Coding Plan (豆包编程订阅)
 *
 * - 官网：https://www.volcengine.com/product/ark
 * - 订阅入口：https://www.volcengine.com/docs/82379/1925114
 * - 快速开始：https://www.volcengine.com/docs/82379/1928261
 * - 支持的模型：https://www.volcengine.com/docs/82379/1928262?lang=zh
 * - 模型价格：https://www.volcengine.com/docs/82379/1544106
 * - Anthropic 协议 baseUrl：https://ark.cn-beijing.volces.com/api/coding
 *
 * 火山方舟 Coding Plan 是火山引擎针对编程场景的订阅服务，订阅包内解锁多家
 * 主力编程模型（豆包 / MiniMax / GLM / DeepSeek / Kimi），同时提供 OpenAI
 * 与 Anthropic 兼容网关。InkOS 使用 OpenAI-compatible /api/coding/v3。
 *
 * 这份静态目录只负责首次配置和无 /models 时的保守兜底。Studio 保存的实测目录
 * 与用户手动添加的模型优先，避免合作物料更新滞后时阻断真实可用模型。
 */
import type { InkosEndpoint } from "../types.js";

export const VOLCENGINE_CODING_PLAN: InkosEndpoint = {
  id: "volcengineCodingPlan",
  label: "火山 Coding Plan",
  group: "codingPlan",
  api: "openai-responses",
  baseUrl: "https://ark.cn-beijing.volces.com/api/coding/v3",
  checkModel: "doubao-seed-2.0-lite",
  temperatureRange: [0, 1],
  defaultTemperature: 0.7,
  writingTemperature: 1,
  models: [
    { id: "ark-code-latest", maxOutput: 32_768, contextWindowTokens: 262_144, enabled: true },
    { id: "doubao-seed-2.1-turbo", maxOutput: 32_768, contextWindowTokens: 256_000, enabled: true },
    { id: "doubao-seed-2.0-lite", maxOutput: 32_768, contextWindowTokens: 256_000, enabled: true, releasedAt: "2026-02-15" },
    { id: "minimax-m2.7", maxOutput: 32_768, contextWindowTokens: 200_000, enabled: true },
    { id: "minimax-m3", maxOutput: 32_768, contextWindowTokens: 512_000, enabled: true },
    { id: "kimi-k2.6", maxOutput: 32_000, contextWindowTokens: 256_000, enabled: true, temperature: 1 },
    { id: "kimi-k2.7-code", maxOutput: 32_000, contextWindowTokens: 256_000, enabled: true, temperature: 1 },
    { id: "glm-5.3", maxOutput: 32_768, contextWindowTokens: 1_024_000, enabled: true, deploymentName: "glm-latest" },
    { id: "glm-5.2", maxOutput: 32_768, contextWindowTokens: 1_024_000, enabled: true },
    { id: "deepseek-v4-flash", maxOutput: 32_768, contextWindowTokens: 1_024_000, enabled: true },
    { id: "deepseek-v4-pro", maxOutput: 32_768, contextWindowTokens: 1_024_000, enabled: true },
    { id: "doubao-seed-2.0-code", maxOutput: 32_768, contextWindowTokens: 256_000, enabled: false, status: "deprecated", replacement: "doubao-seed-2.1-turbo" },
    { id: "doubao-seed-2.0-pro", maxOutput: 32_768, contextWindowTokens: 256_000, enabled: false, status: "deprecated", replacement: "doubao-seed-2.1-turbo" },
    { id: "doubao-seed-code", maxOutput: 32_000, contextWindowTokens: 256_000, enabled: false, status: "deprecated", replacement: "doubao-seed-2.1-turbo" },
    { id: "minimax-m2.5", maxOutput: 32_768, contextWindowTokens: 204_800, enabled: false, status: "deprecated", replacement: "minimax-m2.7" },
    { id: "glm-4.7", maxOutput: 32_768, contextWindowTokens: 200_000, enabled: false, status: "deprecated", replacement: "glm-5.3" },
    { id: "deepseek-v3.2", maxOutput: 32_768, contextWindowTokens: 262_144, enabled: false, status: "deprecated", replacement: "deepseek-v4-flash" },
    { id: "kimi-k2.5", maxOutput: 32_000, contextWindowTokens: 262_144, enabled: false, status: "deprecated", replacement: "kimi-k2.7-code", temperature: 1 },
  ],
};
