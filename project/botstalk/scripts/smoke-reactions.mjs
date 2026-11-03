/**
 * Smoke tests for OpenAgents round 12 message reactions.
 *
 * Usage:
 *   1. Build gateway: npx tsc -p tsconfig.json in gateway/
 *   2. Run from botstalk/: node scripts/smoke-reactions.mjs
 *
 * Seeding Method:
 *   The script spawns the gateway, waits for healthz, then opens the SQLite DB
 *   directly using node:sqlite to insert a test message. This avoids needing
 *   a WebSocket client or internal test seams. The gateway reads messages by id
 *   on demand, so no restart is needed after seeding.
 *
 * Safety:
 *   This script never touches production data. It uses a temporary directory
 *   (or SMOKE_DATA_DIR if provided) and cleans up afterwards.
 */

import { spawn } from 'node:child_process';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import os from 'node:os';
import { DatabaseSync } from 'node:sqlite';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, '..');
const gatewayEntry = path.join(repoRoot, 'gateway', 'dist', 'index.js');
const PORT = 8787;

let gatewayProcess;
let dataDir;

function assert(condition, stepName, message) {
    if (!condition) {
        throw new Error(`Assertion failed in ${stepName}: ${message}`);
    }
}

function fetch(method, pathStr, body) {
    return new Promise((resolve, reject) => {
        const data = body ? JSON.stringify(body) : null;
        const req = http.request({
            method,
            hostname: '127.0.0.1',
            port: PORT,
            path: pathStr,
            headers: {
                'Content-Type': 'application/json'
            }
        }, (res) => {
            let chunks = '';
            res.on('data', (chunk) => chunks += chunk);
            res.on('end', () => {
                let parsed = null;
                try { parsed = JSON.parse(chunks); } catch (e) {}
                resolve({ status: res.statusCode, body: parsed, raw: chunks });
            });
        });
        req.on('error', reject);
        if (data) {
            req.setHeader('Content-Length', Buffer.byteLength(data));
            req.write(data);
        }
        req.end();
    });
}

async function waitForHealthz() {
    const start = Date.now();
    while (Date.now() - start < 15000) {
        try {
            const res = await fetch('GET', '/healthz');
            if (res.status === 200) return true;
        } catch (e) {
            // ignore
        }
        await new Promise(r => setTimeout(r, 500));
    }
    throw new Error('Gateway did not become healthy within 15 seconds');
}

async function main() {
    dataDir = process.env.SMOKE_DATA_DIR || path.join(os.tmpdir(), `botstalk-smoke-reactions-${process.pid}`);
    
    fs.mkdirSync(dataDir, { recursive: true });
    
    gatewayProcess = spawn('node', [gatewayEntry], {
        cwd: repoRoot,
        env: { ...process.env, DATA_DIR: dataDir, GATEWAY_PORT: String(PORT) },
        stdio: 'inherit'
    });
    
    gatewayProcess.on('error', (err) => {
        console.error(`Failed to spawn gateway: ${err.message}`);
        process.exitCode = 1;
    });

    await waitForHealthz();
    
    // Step 1: Create room
    const createRoomRes = await fetch('POST', '/api/rooms', { id: "room1", name: "Room 1", owner: "alice" });
    assert(createRoomRes.status === 201, 'Step 1', `Expected 201, got ${createRoomRes.status}`);

    // Step 2: Seed message
    const dbPath = path.join(dataDir, 'botstalk.db');
    const db = new DatabaseSync(dbPath);
    db.exec(`INSERT INTO messages (room, sender, seq, type, payload, ts) VALUES ('room1', 'alice', 1, 'message', '{"text":"hello"}', ${Date.now()})`);
    const messageId = db.prepare('SELECT last_insert_rowid() as id').get().id;
    db.close();

    // Step 3: Get reactions (empty)
    const getReactions1 = await fetch('GET', `/api/rooms/room1/messages/${messageId}/reactions`);
    assert(getReactions1.status === 200, 'Step 3', `Expected 200, got ${getReactions1.status}`);
    assert(Array.isArray(getReactions1.body?.reactions) && getReactions1.body.reactions.length === 0, 'Step 3', `Expected empty reactions array`);

    // Step 4: Add heart by bob
    const res4 = await fetch("POST", `/api/rooms/room1/messages/${messageId}/reactions`, { reaction: "heart", requester: "bob" });
    assert(res4.status === 200, "Step 4", "POST heart by bob should return 200");
    assert(res4.body.added === true, "Step 4", "heart should be added");
    const heart4 = res4.body.reactions.find((r) => r.reaction === "heart");
    assert(heart4.count === 1, "Step 4", "heart count should be 1");
    assert(JSON.stringify(heart4.reactors) === JSON.stringify(["bob"]), "Step 4", "heart reactors should be ['bob']");

    // Step 5: Same POST again
    const res5 = await fetch("POST", `/api/rooms/room1/messages/${messageId}/reactions`, { reaction: "heart", requester: "bob" });
    assert(res5.status === 200, "Step 5", "POST heart by bob again should return 200");
    assert(res5.body.added === false, "Step 5", "heart should not be added again");
    const heart5 = res5.body.reactions.find((r) => r.reaction === "heart");
    assert(heart5.count === 1, "Step 5", "heart count should still be 1");

    // Step 6: POST heart by carol
    const res6 = await fetch("POST", `/api/rooms/room1/messages/${messageId}/reactions`, { reaction: "heart", requester: "carol" });
    assert(res6.status === 200, "Step 6", "POST heart by carol should return 200");
    assert(res6.body.added === true, "Step 6", "heart should be added for carol");
    const heart6 = res6.body.reactions.find((r) => r.reaction === "heart");
    assert(heart6.count === 2, "Step 6", "heart count should be 2");
    assert(JSON.stringify(heart6.reactors) === JSON.stringify(["bob", "carol"]), "Step 6", "heart reactors should be ['bob', 'carol'] in order");

    // Step 7: POST invalid reaction
    const res7 = await fetch("POST", `/api/rooms/room1/messages/${messageId}/reactions`, { reaction: "Love", requester: "bob" });
    assert(res7.status === 400, "Step 7", "POST Love should return 400");
    assert(res7.body.error === "INVALID_REACTION", "Step 7", "error should be INVALID_REACTION");

    // Step 8: POST heart without requester
    const res8 = await fetch("POST", `/api/rooms/room1/messages/${messageId}/reactions`, { reaction: "heart" });
    assert(res8.status === 400, "Step 8", "POST heart without requester should return 400");
    assert(res8.body.error === "requester required", "Step 8", "error should be requester required");

    // Step 9: POST heart to non-existent message
    const res9 = await fetch("POST", "/api/rooms/room1/messages/999999/reactions", { reaction: "heart", requester: "bob" });
    assert(res9.status === 404, "Step 9", "POST heart to non-existent message should return 404");
    assert(res9.body.error === "MESSAGE_NOT_FOUND", "Step 9", "error should be MESSAGE_NOT_FOUND");

    // Step 10: DELETE heart by bob
    const res10a = await fetch("DELETE", `/api/rooms/room1/messages/${messageId}/reactions?reaction=heart&requester=bob`);
    assert(res10a.status === 200, "Step 10", "DELETE heart by bob should return 200");
    assert(res10a.body.removed === true, "Step 10", "heart should be removed");

    const res10b = await fetch("DELETE", `/api/rooms/room1/messages/${messageId}/reactions?reaction=heart&requester=bob`);
    assert(res10b.status === 200, "Step 10", "DELETE heart by bob again should return 200");
    assert(res10b.body.removed === false, "Step 10", "heart should not be removed again");

    // Step 10 (continued): DELETE heart by carol, added in Step 6, or Step 11 cannot be empty
    const res10c = await fetch("DELETE", `/api/rooms/room1/messages/${messageId}/reactions?reaction=heart&requester=carol`);
    assert(res10c.status === 200, "Step 10", "DELETE heart by carol should return 200");
    assert(res10c.body.removed === true, "Step 10", "carol heart should be removed");

    const res10d = await fetch("DELETE", `/api/rooms/room1/messages/${messageId}/reactions?reaction=heart&requester=carol`);
    assert(res10d.status === 200, "Step 10", "DELETE heart by carol again should return 200");
    assert(res10d.body.removed === false, "Step 10", "carol heart should not be removed again");

    // Step 11: GET reactions, expect empty
    const res11 = await fetch("GET", `/api/rooms/room1/messages/${messageId}/reactions`);
    assert(res11.status === 200, "Step 11", "GET reactions should return 200");
    assert(Array.isArray(res11.body.reactions) && res11.body.reactions.length === 0, "Step 11", "reactions array should be empty");

    // Step 12: GET reactions for invalid message ID
    const res12 = await fetch("GET", "/api/rooms/room1/messages/abc/reactions");
    assert(res12.status === 400, "Step 12", "GET invalid message ID should return 400");
    assert(res12.body.error === "INVALID_MESSAGE_ID", "Step 12", "error should be INVALID_MESSAGE_ID");

    console.log("SMOKE_REACTIONS_PASS");
}
main().catch((err) => { console.error(err); process.exitCode = 1; }).finally(() => { if (gatewayProcess && !gatewayProcess.killed) gatewayProcess.kill("SIGTERM"); try { fs.rmSync(dataDir, { recursive: true, force: true }); } catch (e) {} });
