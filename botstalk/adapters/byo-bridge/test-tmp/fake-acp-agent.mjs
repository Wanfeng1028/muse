// 测试用假 ACP agent：经 stdio 说 NDJSON JSON-RPC 2.0。
// initialize -> 固定能力；session/new -> 固定会话 id；session/prompt ->
// 先发两条 agent_message_chunk 更新（"Hello, " + "world"），再回 end_turn；
// prompt 文本含 REFUSE 时发一条更新后回 refusal。
import { createInterface } from "node:readline";

const rl = createInterface({ input: process.stdin });

function send(obj) {
  process.stdout.write(`${JSON.stringify(obj)}\n`);
}

rl.on("line", (line) => {
  const trimmed = line.trim();
  if (trimmed.length === 0) return;
  let msg;
  try {
    msg = JSON.parse(trimmed);
  } catch {
    return;
  }
  const { id, method, params } = msg;
  if (method === "initialize") {
    send({ jsonrpc: "2.0", id, result: { protocolVersion: 1, agentCapabilities: {} } });
    return;
  }
  if (method === "session/new") {
    send({ jsonrpc: "2.0", id, result: { sessionId: "fake-session-1" } });
    return;
  }
  if (method === "session/prompt") {
    const sessionId = params?.sessionId ?? "fake-session-1";
    const text = params?.prompt?.[0]?.text ?? "";
    const chunk = (t) =>
      send({
        jsonrpc: "2.0",
        method: "session/update",
        params: {
          sessionId,
          update: { sessionUpdate: "agent_message_chunk", content: { type: "text", text: t } },
        },
      });
    if (text.includes("REFUSE")) {
      chunk("I refuse.");
      send({ jsonrpc: "2.0", id, result: { stopReason: "refusal" } });
      return;
    }
    chunk("Hello, ");
    chunk("world");
    send({ jsonrpc: "2.0", id, result: { stopReason: "end_turn" } });
    return;
  }
  if (method === "session/cancel") {
    return; // 通知，无响应
  }
  if (typeof id === "number") {
    send({ jsonrpc: "2.0", id, error: { code: -32601, message: `unknown method: ${method}` } });
  }
});
