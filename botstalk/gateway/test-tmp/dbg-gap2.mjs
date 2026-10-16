import { WebSocketServer, WebSocket } from "ws";
import { makeEnvelope } from "@botstalk/protocol";
import { Hub } from "../dist/hub.js";
import { openDb } from "../dist/db.js";

const db = openDb("/home/hatch/workspace/botstalk/gateway/test-tmp/dbgdb2");
const wss = new WebSocketServer({ port: 0 });
await new Promise((r) => wss.once("listening", r));
const port = wss.address().port;
const hub = new Hub(db);
wss.on("connection", (ws) => hub.handleConnection(ws));

const ws = new WebSocket(`ws://127.0.0.1:${port}`);
await new Promise((r) => ws.once("open", r));
const received = [];
ws.on("message", (d) => {
  const e = JSON.parse(String(d));
  received.push(e);
  console.log(`GOT type=${e.type} seq=${e.seq} sender=${e.sender}`);
});

ws.send(JSON.stringify(makeEnvelope("hello", "gapc", "room-a", 1, 0,
  { adapter_id: "gapc", protocol_version: "1.0", last_seen_seq: 0 })));
await new Promise((r) => setTimeout(r, 200));

const f1 = makeEnvelope("message", "gateway", "room-a", hub.serverSeq.nextSeq(), 0, { msg_id: "a", text: "one", mentions: [] });
const f2 = makeEnvelope("message", "gateway", "room-a", hub.serverSeq.nextSeq(), 0, { msg_id: "b", text: "two", mentions: [] });
const f3 = makeEnvelope("message", "gateway", "room-a", hub.serverSeq.nextSeq(), 0, { msg_id: "c", text: "three", mentions: [] });
hub.sendTo("gapc", f1); hub.sendTo("gapc", f2); hub.sendTo("gapc", f3);
await new Promise((r) => setTimeout(r, 200));
console.log("--- sending gap request ---");
ws.send(JSON.stringify(makeEnvelope("gap", "gapc", "room-a", 2, 0, { from_seq: 2, to_seq: 2 })));
await new Promise((r) => setTimeout(r, 500));
console.log(`total received: ${received.length}`);
ws.close(); wss.close(); process.exit(0);
