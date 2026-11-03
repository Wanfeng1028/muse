import type { IncomingMessage, ServerResponse } from "node:http";
import { registry } from "@botstalk/registry";
import type { AgentDescriptor } from "@botstalk/registry";

/** 对外展示的白名单字段（不含 check_ready/resolve_env/env_config/launch/probe 等敏感信息） */
function toPublic(d: AgentDescriptor) {
  return {
    name: d.name,
    label: d.label,
    description: d.description,
    homepage: d.homepage,
    tags: d.tags,
    featured: d.featured,
    order: d.order,
    vendor: d.vendor,
    tagline: d.tagline,
    support: d.support,
    binary: d.install.binary,
    logo: d.logo,
  };
}

/**
 * registry 目录路由。处理了返回 true，未命中返回 false。
 * - GET /api/registry/agents → { agents: [...] }（白名单字段）
 * - GET /api/registry/agents/:name → 单项；不存在 404 { error: "agent not found" }
 */
export function handleRegistryRoutes(
  _req: IncomingMessage,
  res: ServerResponse,
  url: string,
  method: string,
): boolean {
  if (method !== "GET") return false;
  res.setHeader("access-control-allow-origin", "*");
  if (/^\/api\/registry\/agents(?:\?|$)/.test(url)) {
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ agents: registry.getCatalog().map(toPublic) }));
    return true;
  }
  const one = url.match(/^\/api\/registry\/agents\/([^/?]+)(?:\?|$)/);
  if (one) {
    const d = registry.getByName(decodeURIComponent(one[1]));
    if (!d) {
      res.writeHead(404, { "content-type": "application/json" });
      res.end(JSON.stringify({ error: "agent not found" }));
      return true;
    }
    res.writeHead(200, { "content-type": "application/json" });
    res.end(JSON.stringify({ agent: toPublic(d) }));
    return true;
  }
  return false;
}
