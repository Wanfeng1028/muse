import type { McpSession } from "./mcp-session.js";

export async function processMcpLine(
  session: McpSession,
  line: string,
): Promise<string | null> {
  if (!line.trim()) return null;
  let request: unknown;
  try {
    request = JSON.parse(line);
  } catch {
    return encode({
      jsonrpc: "2.0",
      id: null,
      error: { code: -32700, message: "Parse error" },
    });
  }
  if (!isJsonRpcRequest(request)) {
    return encode({
      jsonrpc: "2.0",
      id: null,
      error: { code: -32600, message: "Invalid Request" },
    });
  }
  const response = await session.handle(request);
  return response ? encode(response) : null;
}

function isJsonRpcRequest(value: unknown): value is {
  jsonrpc: "2.0";
  id?: string | number | null;
  method: string;
  params?: unknown;
} {
  return (
    Boolean(value) &&
    typeof value === "object" &&
    (value as { jsonrpc?: unknown }).jsonrpc === "2.0" &&
    typeof (value as { method?: unknown }).method === "string"
  );
}

function encode(value: unknown): string {
  return `${JSON.stringify(value)}\n`;
}
