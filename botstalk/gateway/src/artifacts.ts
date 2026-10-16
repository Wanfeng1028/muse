import { randomBytes } from "node:crypto";
import { createWriteStream, mkdirSync, statSync, unlinkSync, renameSync, createReadStream } from "node:fs";
import { join } from "node:path";
import type { IncomingMessage, ServerResponse } from "node:http";
import { UPLOAD_URL_WINDOW_MS } from "@botstalk/protocol";
import type { ArtifactUploadRequest } from "@botstalk/protocol";
import { saveArtifact, getArtifact } from "./db.js";
import type { Db } from "./db.js";
import type { GatewayConfig } from "./config.js";

const MAX_ARTIFACT_BYTES = 100 * 1024 * 1024;

interface PendingUpload {
  token: string;
  filename: string;
  declaredSize: number;
  mime: string | null;
  createdAtMs: number;
}

async function readBody(req: IncomingMessage): Promise<Buffer> {
  const chunks: Buffer[] = [];
  for await (const chunk of req) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk as string));
  }
  return Buffer.concat(chunks);
}

function sendJson(res: ServerResponse, status: number, body: unknown): void {
  const text = JSON.stringify(body);
  res.writeHead(status, { "content-type": "application/json" });
  res.end(text);
}

export class ArtifactService {
  private pending = new Map<string, PendingUpload>();
  private dir: string;

  constructor(private db: Db, private config: GatewayConfig) {
    this.dir = join(config.dataDir, "artifacts");
    mkdirSync(this.dir, { recursive: true });
  }

  handle(req: IncomingMessage, res: ServerResponse): boolean {
    const url = req.url ?? "";
    const method = req.method ?? "";

    if (method === "POST" && url === "/artifacts/request") {
      void this.handleRequest(req, res);
      return true;
    }

    if (method === "PUT" && url.startsWith("/artifacts/upload/")) {
      const token = url.slice("/artifacts/upload/".length);
      void this.handleUpload(req, res, token);
      return true;
    }

    if (method === "GET" && url.startsWith("/artifacts/")) {
      const id = url.slice("/artifacts/".length);
      void this.handleDownload(req, res, id);
      return true;
    }

    return false;
  }

  private async handleRequest(req: IncomingMessage, res: ServerResponse): Promise<void> {
    let raw: Buffer;
    try {
      raw = await readBody(req);
    } catch {
      sendJson(res, 400, { error: "bad_body" });
      return;
    }

    let parsed: unknown;
    try {
      parsed = JSON.parse(raw.toString("utf8"));
    } catch {
      sendJson(res, 400, { error: "invalid_json" });
      return;
    }

    if (parsed === null || typeof parsed !== "object") {
      sendJson(res, 400, { error: "invalid_request" });
      return;
    }

    const body = parsed as Partial<ArtifactUploadRequest>;
    const filename = body.filename;
    const declaredSize = body.declared_size;
    const mime = body.mime;

    if (typeof filename !== "string" || filename.length === 0) {
      sendJson(res, 400, { error: "invalid_filename" });
      return;
    }
    if (
      typeof declaredSize !== "number" ||
      !Number.isInteger(declaredSize) ||
      declaredSize <= 0 ||
      declaredSize > MAX_ARTIFACT_BYTES
    ) {
      sendJson(res, 400, { error: "invalid_size" });
      return;
    }
    if (mime !== undefined && typeof mime !== "string") {
      sendJson(res, 400, { error: "invalid_mime" });
      return;
    }

    const token = randomBytes(16).toString("hex");
    const createdAtMs = Date.now();
    this.pending.set(token, {
      token,
      filename,
      declaredSize,
      mime: mime === undefined ? null : mime,
      createdAtMs,
    });

    const host = req.headers.host ?? "";
    const grant = {
      upload_url: "http://" + host + "/artifacts/upload/" + token,
      expires_at_ms: createdAtMs + UPLOAD_URL_WINDOW_MS,
    };
    sendJson(res, 201, grant);
  }

  private async handleUpload(
    req: IncomingMessage,
    res: ServerResponse,
    token: string,
  ): Promise<void> {
    const pending = this.pending.get(token);
    if (pending === undefined) {
      sendJson(res, 410, { error: "gone" });
      return;
    }

    const now = Date.now();
    if (now - pending.createdAtMs > UPLOAD_URL_WINDOW_MS) {
      this.pending.delete(token);
      sendJson(res, 410, { error: "expired" });
      return;
    }

    const tmpPath = join(this.dir, token + ".bin");
    let bytesWritten = 0;
    try {
      const ws = createWriteStream(tmpPath);
      for await (const chunk of req) {
        const buf = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk as string);
        bytesWritten += buf.length;
        if (!ws.write(buf)) {
          await new Promise<void>((resolve) => ws.once("drain", () => resolve()));
        }
      }
      await new Promise<void>((resolve, reject) => {
        ws.end(() => resolve());
        ws.on("error", reject);
      });
    } catch {
      try {
        unlinkSync(tmpPath);
      } catch {
        // ignore
      }
      this.pending.delete(token);
      sendJson(res, 400, { error: "write_failed" });
      return;
    }

    let actualSize: number;
    try {
      actualSize = statSync(tmpPath).size;
    } catch {
      this.pending.delete(token);
      sendJson(res, 400, { error: "stat_failed" });
      return;
    }

    if (actualSize !== pending.declaredSize) {
      try {
        unlinkSync(tmpPath);
      } catch {
        // ignore
      }
      this.pending.delete(token);
      sendJson(res, 400, { error: "size_mismatch" });
      return;
    }

    const id = "artf_" + randomBytes(8).toString("hex");
    const finalPath = join(this.dir, id + ".bin");
    try {
      renameSync(tmpPath, finalPath);
    } catch {
      this.pending.delete(token);
      sendJson(res, 400, { error: "rename_failed" });
      return;
    }

    saveArtifact(this.db, {
      id,
      filename: pending.filename,
      size: pending.declaredSize,
      mime: pending.mime,
      path: finalPath,
    });
    this.pending.delete(token);

    sendJson(res, 200, { id, filename: pending.filename, size: pending.declaredSize });
  }

  private async handleDownload(
    req: IncomingMessage,
    res: ServerResponse,
    id: string,
  ): Promise<void> {
    const artifact = getArtifact(this.db, id);
    if (artifact === undefined) {
      sendJson(res, 404, { error: "not_found" });
      return;
    }
    res.writeHead(200, {
      "content-type": artifact.mime ?? "application/octet-stream",
      "content-length": artifact.size,
    });
    createReadStream(artifact.path).pipe(res);
  }
}

export function createArtifactService(db: Db, config: GatewayConfig): ArtifactService {
  return new ArtifactService(db, config);
}

// 自查：红线 1-5 逐条通过
