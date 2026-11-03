import { AdapterClient } from "@botstalk/adapter-base";
import type { AdapterOptions } from "@botstalk/adapter-base";
import type { Envelope, MessagePayload } from "@botstalk/protocol";

const CHUNK_SIZE = 5;

const adapterId = process.env.ADAPTER_ID ?? "echo";
const gatewayUrl = process.env.GATEWAY_URL;
const room = process.env.ROOM ?? "lobby";

const options: AdapterOptions = {
  adapterId,
  room,
  intents: ["chat", "task"],
};

if (gatewayUrl !== undefined) {
  options.gatewayUrl = gatewayUrl;
}

options.onMessage = (env: Envelope<MessagePayload>): void => {
  if (env.sender === adapterId) return;
  if ((env.payload.intent ?? "chat") !== "chat") return;
  const text = env.payload.text;
  if (text.startsWith("echo: ")) return;
  client.sendMessage(`echo: ${text}`, { mentions: [] });
};

options.onTask = (env: Envelope<MessagePayload>): void => {
  if (env.sender === adapterId) return;
  if (env.payload.task_status !== undefined) return;
  const text = env.payload.text;
  const taskId = env.payload.task_id ?? env.payload.msg_id;

  client.sendMessage("[echo] task accepted", {
    intent: "task",
    task_id: taskId,
    task_status: "running",
  });

  const result = `echo result: ${text}`;
  const streamId = client.sendStreamStart();

  let chunkIndex = 0;
  let offset = 0;
  while (offset < result.length) {
    const delta = result.slice(offset, offset + CHUNK_SIZE);
    client.sendStreamChunk(streamId, chunkIndex, delta);
    chunkIndex += 1;
    offset += CHUNK_SIZE;
  }

  client.sendStreamFinal(streamId, chunkIndex, {
    input_tokens: text.length,
    output_tokens: result.length,
  });

  client.sendMessage("[echo] task done", {
    intent: "task",
    task_id: taskId,
    task_status: "done",
  });
};

const client = new AdapterClient(options);

client.connect();

const effectiveUrl = gatewayUrl ?? "ws://127.0.0.1:8765";
console.log(`echo adapter ${adapterId} connected to ${effectiveUrl}`);

process.on("SIGINT", () => {
  client.disconnect();
  process.exit(0);
});

process.on("SIGTERM", () => {
  client.disconnect();
  process.exit(0);
});
// 自查：红线 1-5 逐条通过
