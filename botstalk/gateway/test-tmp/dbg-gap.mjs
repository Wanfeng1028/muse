import { WebSocketServer, WebSocket } from "ws";
import { makeEnvelope } from "@botstalk/protocol";
import { Hub } from "../dist/hub.js";
import { openDb } from "../dist/db.js";

const db = openDb("/home/hatch/workspace/botstalk/gateway/test-tmp/dbgdb");
const wss = new WebSocketServer({ port: 0 });
await new Promise((r) => wss.once("listening", r));
const port = wss.address().port;
const hub = new Hub(db);
wss.on("connection", (ws) => hub.handleConnection(ws));

const ws = new WebSocket(`ws://127.0.0.1:${port}`);
await new Promise((r) => ws.once("open", r));
console.log("client open");

ws.on("message", (d) => console.log("CLIENT GOT:", String(d).slice(0, 120)));

const helloEnv = makeEnvelope("hello", "gapc", "room-a", 1, 0,
  { adapter_id: "gapc", protocol_version: "1.0", last_seen_seq: 0 });
ws.send(JSON.stringify(helloEnv));
console.log("hello sent");

await new Promise((r) => setTimeout(r, 300));
console.log("conn:", hub.getConn("gapc") ? "exists" : "MISSING");

const f1 = makeEnvelope("message", "gateway", "room-a", hub.serverSeq.nextSeq(), 0, { msg_id: "a", text: "one", mentions: [] });
console.log("f1.seq=", f1.seq);
const ok = hub.sendTo("gapc", f1);
console.log("sendTo returned:", ok);

await new Promise((r) => setTimeout(r, 500));
ws.close();
wss.close();
process.exit(0);
