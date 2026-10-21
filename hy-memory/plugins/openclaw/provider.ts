/**
 * HY Memory Provider — HTTP client that talks to the local Python server.
 */

import type {
  HyMemoryConfig,
  HyMemoryProvider,
  AddResult,
  SearchResult,
  ListResult,
  DeleteResult,
  MemoryItem,
} from "./types.ts";

/**
 * Normalize the `memories` field from the search API response.
 * HY Memory Server returns a grouped object: { profile: [...], proactive: [...], normal: [...] }
 * but downstream code expects a flat MemoryItem[].
 * This function handles both shapes for backward compatibility.
 */
function normalizeSearchMemories(raw: unknown): MemoryItem[] {
  if (Array.isArray(raw)) return raw;
  if (raw && typeof raw === "object") {
    const groups = raw as Record<string, unknown>;
    const ordered = ["profile", "proactive", "normal"];
    const result: MemoryItem[] = [];
    for (const key of ordered) {
      if (Array.isArray(groups[key])) result.push(...(groups[key] as MemoryItem[]));
    }
    for (const [key, value] of Object.entries(groups)) {
      if (!ordered.includes(key) && Array.isArray(value)) {
        result.push(...(value as MemoryItem[]));
      }
    }
    return result;
  }
  return [];
}

export class HttpProvider implements HyMemoryProvider {
  private baseUrl: string;

  constructor(private readonly cfg: HyMemoryConfig) {
    this.baseUrl = cfg.serverUrl.replace(/\/+$/, "");
  }

  private async _request(
    method: string,
    path: string,
    opts?: { json?: unknown },
  ): Promise<unknown> {
    const url = `${this.baseUrl}${path}`;
    const fetchOpts: RequestInit = {
      method,
      headers: { "Content-Type": "application/json" },
      signal: AbortSignal.timeout(120_000),
    };
    if (opts?.json) {
      fetchOpts.body = JSON.stringify(opts.json);
    }
    const resp = await fetch(url, fetchOpts);
    if (!resp.ok) {
      let detail: string;
      try {
        const body = (await resp.json()) as Record<string, unknown>;
        detail = String(body.error ?? resp.statusText);
      } catch {
        detail = resp.statusText;
      }
      throw new Error(`HTTP ${resp.status}: ${detail}`);
    }
    return resp.json();
  }

  async add(
    data: string | Array<{ role: string; content: string }>,
    options: {
      user_id: string;
      agent_id?: string;
      session_id?: string;
      enable_agent?: boolean;
      memory_at?: string;
    },
  ): Promise<AddResult> {
    const payload: Record<string, unknown> = {
      user_id: options.user_id,
      agent_id: options.agent_id ?? this.cfg.agentId,
      session_id: options.session_id ?? this.cfg.sessionId,
      enable_agent: options.enable_agent ?? true,
      memory_at: options.memory_at ?? new Date().toISOString(),
    };
    if (typeof data === "string") {
      payload.text = data;
    } else {
      payload.messages = data;
    }
    return (await this._request("POST", "/api/v1/add", {
      json: payload,
    })) as AddResult;
  }

  async addExtracted(
    contents: string | string[],
    options: {
      user_id: string;
      agent_id?: string;
      session_id?: string;
      memory_at?: string;
    },
  ): Promise<AddResult> {
    const payload: Record<string, unknown> = {
      contents,
      user_id: options.user_id,
      agent_id: options.agent_id ?? this.cfg.agentId,
      session_id: options.session_id ?? this.cfg.sessionId,
      memory_at: options.memory_at ?? new Date().toISOString(),
    };
    return (await this._request("POST", "/api/v1/add_extracted", {
      json: payload,
    })) as AddResult;
  }

  async search(
    query: string,
    options: {
      user_id: string;
      user_ids?: string[];
      agent_ids?: string[];
      limit?: number;
      min_score?: number;
      profile_limit?: number;
      profile_min_score?: number;
    },
  ): Promise<SearchResult> {
    const payload: Record<string, unknown> = {
      query,
      user_ids: options.user_ids ?? [options.user_id],
      limit: options.limit ?? this.cfg.topK,
      min_score: options.min_score ?? this.cfg.searchThreshold,
      profile_limit: options.profile_limit ?? this.cfg.profileLimit,
      profile_min_score: options.profile_min_score ?? this.cfg.profileMinScore,
    };
    if (options.agent_ids) payload.agent_ids = options.agent_ids;
    const resp = (await this._request("POST", "/api/v1/search", {
      json: payload,
    })) as Record<string, unknown>;
    return {
      ...resp,
      memories: normalizeSearchMemories(resp.memories),
    } as SearchResult;
  }

  async get(memoryId: string): Promise<MemoryItem | null> {
    try {
      return (await this._request(
        "GET",
        `/api/v1/memories/${memoryId}`,
      )) as MemoryItem;
    } catch (err) {
      if (String(err).includes("404")) return null;
      throw err;
    }
  }

  async list(options: {
    user_id: string;
    agent_id?: string;
    limit?: number;
    offset?: number;
  }): Promise<ListResult> {
    return (await this._request("POST", "/api/v1/list", {
      json: options,
    })) as ListResult;
  }

  async update(memoryId: string, content: string): Promise<AddResult> {
    return (await this._request("PUT", `/api/v1/memories/${memoryId}`, {
      json: { content },
    })) as AddResult;
  }

  async delete(memoryId: string): Promise<DeleteResult> {
    return (await this._request(
      "DELETE",
      `/api/v1/memories/${memoryId}`,
    )) as DeleteResult;
  }

  async deleteAll(options: {
    user_id: string;
    agent_ids?: string[];
    session_ids?: string[];
  }): Promise<DeleteResult> {
    return (await this._request("POST", "/api/v1/delete_all", {
      json: options,
    })) as DeleteResult;
  }

  async healthCheck(): Promise<boolean> {
    try {
      const resp = await fetch(`${this.baseUrl}/healthz`, {
        signal: AbortSignal.timeout(3_000),
      });
      return resp.ok;
    } catch {
      return false;
    }
  }
}
