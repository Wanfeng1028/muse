import { getAllEndpoints, getEndpoint } from "./providers/index.js";
import { probeModelsFromUpstream } from "./providers/probe.js";
import { isApiKeyOptionalForEndpoint } from "../utils/llm-endpoint-auth.js";

export interface ServicePreset {
  readonly providerFamily: "openai" | "anthropic";
  readonly api: string;
  readonly baseUrl: string;
  readonly label: string;
  readonly temperatureRange?: readonly [number, number];
  readonly defaultTemperature?: number;
  readonly writingTemperature?: number;
  readonly temperatureHint?: string;
  readonly modelsBaseUrl?: string;
}

export function resolveServicePreset(service: string): ServicePreset | undefined {
  const endpoint = getEndpoint(service);
  if (!endpoint) return undefined;
  const providerFamily = endpoint.api === "anthropic-messages" ? "anthropic" : "openai";
  return {
    providerFamily,
    api: endpoint.api,
    baseUrl: endpoint.baseUrl,
    label: endpoint.label,
    ...(endpoint.temperatureRange ? { temperatureRange: endpoint.temperatureRange } : {}),
    ...(endpoint.defaultTemperature !== undefined ? { defaultTemperature: endpoint.defaultTemperature } : {}),
    ...(endpoint.writingTemperature !== undefined ? { writingTemperature: endpoint.writingTemperature } : {}),
    ...(endpoint.temperatureHint ? { temperatureHint: endpoint.temperatureHint } : {}),
    ...(endpoint.modelsBaseUrl ? { modelsBaseUrl: endpoint.modelsBaseUrl } : {}),
  };
}

export function resolveServiceProviderFamily(service: string): "openai" | "anthropic" | undefined {
  return resolveServicePreset(service)?.providerFamily;
}

export function resolveServicePiProvider(service: string): string | undefined {
  const endpoint = getEndpoint(service);
  if (!endpoint) return undefined;
  if (endpoint.id === "google") return "google";
  if (endpoint.id === "zhipu") return "zai";
  if (endpoint.id === "openrouter") return "openrouter";
  if (endpoint.id === "githubCopilot") return "githubCopilot";
  if (endpoint.id === "ollama") return "ollama";
  return endpoint.api === "anthropic-messages" ? "anthropic" : "openai";
}

export function resolveServiceModelsBaseUrl(service: string): string | undefined {
  const endpoint = getEndpoint(service);
  return endpoint?.modelsBaseUrl ?? endpoint?.baseUrl;
}

const DEFAULT_TEMPERATURE_RANGE: readonly [number, number] = [0, 2];

export function clampTemperature(service: string, temperature: number): number {
  const [min, max] = resolveServicePreset(service)?.temperatureRange ?? DEFAULT_TEMPERATURE_RANGE;
  return Math.max(min, Math.min(max, temperature));
}

export function getWritingTemperature(service: string): number {
  const preset = resolveServicePreset(service);
  return preset?.writingTemperature ?? preset?.defaultTemperature ?? 1;
}

export function guessServiceFromBaseUrl(baseUrl: string): string {
  for (const endpoint of getAllEndpoints()) {
    if (endpoint.id === "custom" || !endpoint.baseUrl) continue;
    try {
      if (baseUrl.includes(new URL(endpoint.baseUrl).hostname)) return endpoint.id;
    } catch {
      continue;
    }
  }
  return "custom";
}

export const SERVICE_TO_PI_PROVIDER: Record<string, string> = Object.fromEntries(
  getAllEndpoints()
    .filter((endpoint) => endpoint.id !== "custom")
    .map((endpoint) => [endpoint.id, resolveServicePiProvider(endpoint.id)!]),
);

export interface ModelInfo {
  readonly id: string;
  readonly name: string;
  readonly contextWindow: number;
  readonly maxOutput?: number;
}

function toModelInfo(model: { id: string; maxOutput: number; contextWindowTokens: number }): ModelInfo {
  return {
    id: model.id,
    name: model.id,
    contextWindow: model.contextWindowTokens,
    maxOutput: model.maxOutput,
  };
}

export async function listModelsForService(
  service: string,
  apiKey?: string,
  liveBaseUrl?: string,
): Promise<ReadonlyArray<ModelInfo>> {
  const endpoint = getEndpoint(service);
  if (!endpoint) return [];
  const byId = new Map<string, ModelInfo>();
  const probeBaseUrl = liveBaseUrl || endpoint.modelsBaseUrl || endpoint.baseUrl;
  const providerFamily = endpoint.api === "anthropic-messages" ? "anthropic" : "openai";
  const canProbeWithoutApiKey = isApiKeyOptionalForEndpoint({ provider: providerFamily, baseUrl: probeBaseUrl });
  if ((apiKey || canProbeWithoutApiKey) && probeBaseUrl) {
    const probed = await probeModelsFromUpstream(probeBaseUrl, apiKey ?? "", 10_000);
    if (probed.length > 0) {
      const { lookupModel } = await import("./providers/lookup.js");
      for (const model of probed) {
        const card = lookupModel(service, model.id);
        byId.set(model.id, card
          ? toModelInfo(card)
          : { id: model.id, name: model.name, contextWindow: model.contextWindow });
      }
    }
  }
  for (const model of endpoint.models) {
    if (model.enabled === false || byId.has(model.id)) continue;
    byId.set(model.id, toModelInfo(model));
  }
  return [...byId.values()];
}

export async function listServicesWithModelCount(): Promise<ReadonlyArray<{ service: string; label: string; modelCount: number }>> {
  const result: Array<{ service: string; label: string; modelCount: number }> = [];
  for (const endpoint of getAllEndpoints()) {
    result.push({
      service: endpoint.id,
      label: endpoint.label,
      modelCount: endpoint.id === "custom" ? 0 : (await listModelsForService(endpoint.id)).length,
    });
  }
  return result;
}
