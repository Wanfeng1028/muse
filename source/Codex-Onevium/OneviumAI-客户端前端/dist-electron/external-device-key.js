"use strict";
var __create = Object.create;
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __getProtoOf = Object.getPrototypeOf;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, { get: all[name], enumerable: true });
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toESM = (mod, isNodeMode, target) => (target = mod != null ? __create(__getProtoOf(mod)) : {}, __copyProps(
  // If the importer is in node compatibility mode or this is not an ESM
  // file that has been converted to a CommonJS file using a Babel-
  // compatible transform (i.e. "__esModule" has not been set), then set
  // "default" to the CommonJS "module.exports" for node compatibility.
  isNodeMode || !mod || !mod.__esModule ? __defProp(target, "default", { value: mod, enumerable: true }) : target,
  mod
));
var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

// electron/external-device-key.ts
var external_device_key_exports = {};
__export(external_device_key_exports, {
  handleExternalSignerMessage: () => handleExternalSignerMessage,
  startExternalDeviceSigner: () => startExternalDeviceSigner,
  stopExternalDeviceSigner: () => stopExternalDeviceSigner
});
module.exports = __toCommonJS(external_device_key_exports);
var import_node_http = require("node:http");
var import_node_crypto = __toESM(require("node:crypto"));
var import_node_fs = __toESM(require("node:fs"));
var import_node_path = __toESM(require("node:path"));
var import_electron = require("electron");
var server = null;
var starting = null;
var generation = 0;
var sockets = /* @__PURE__ */ new Set();
function deviceKey() {
  if (!import_electron.safeStorage.isEncryptionAvailable() || process.platform === "linux" && import_electron.safeStorage.getSelectedStorageBackend() === "basic_text") {
    throw new Error("OS credential storage is unavailable.");
  }
  const filename = import_node_path.default.join(import_electron.app.getPath("userData"), "external-device-key.v1");
  if (import_node_fs.default.existsSync(filename))
    return import_node_crypto.default.createPrivateKey(
      import_electron.safeStorage.decryptString(import_node_fs.default.readFileSync(filename))
    );
  const pair = import_node_crypto.default.generateKeyPairSync("ed25519");
  const encrypted = import_electron.safeStorage.encryptString(
    pair.privateKey.export({ format: "pem", type: "pkcs8" }).toString()
  );
  import_node_fs.default.mkdirSync(import_node_path.default.dirname(filename), { recursive: true, mode: 448 });
  const temporary = `${filename}.${import_node_crypto.default.randomBytes(8).toString("hex")}.tmp`;
  try {
    import_node_fs.default.writeFileSync(temporary, encrypted, { mode: 384, flag: "wx" });
    import_node_fs.default.renameSync(temporary, filename);
  } finally {
    try {
      import_node_fs.default.unlinkSync(temporary);
    } catch {
    }
  }
  return pair.privateKey;
}
function handleExternalSignerMessage(raw) {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
  const request = raw;
  if (request.type !== "external-signer:request" || typeof request.id !== "string" || !/^[A-Za-z0-9_-]{1,64}$/.test(request.id)) return null;
  const reply = { type: "external-signer:response", id: request.id };
  try {
    if (Object.keys(request).some((key) => !["type", "id", "operation", "challenge"].includes(key))) throw new Error("Invalid request.");
    if (request.operation === "identity" && request.challenge === void 0) {
      reply.result = { available: true, public_key: import_node_crypto.default.createPublicKey(deviceKey()).export({ format: "der", type: "spki" }).toString("base64") };
    } else if (request.operation === "sign" && typeof request.challenge === "string" && request.challenge.startsWith("onevium-gateway:") && Buffer.byteLength(request.challenge) <= 8192 && !/[\r\n\0]/.test(request.challenge)) {
      reply.result = { signature: import_node_crypto.default.sign(null, Buffer.from(request.challenge), deviceKey()).toString("base64") };
    } else throw new Error("Invalid request.");
  } catch {
    reply.error = "Secure device signing is unavailable or the request is invalid.";
  }
  return reply;
}
function startExternalDeviceSigner() {
  if (starting) return starting;
  const owner = ++generation;
  const token = import_node_crypto.default.randomBytes(32).toString("hex");
  const listener = (0, import_node_http.createServer)(async (request, response) => {
    response.setHeader("Cache-Control", "no-store");
    response.setHeader("Content-Type", "application/json");
    const bearer = request.headers.authorization?.replace(/^Bearer /, "") ?? "";
    if (request.headers.origin || bearer.length !== token.length || !import_node_crypto.default.timingSafeEqual(Buffer.from(bearer), Buffer.from(token))) {
      response.writeHead(403).end(JSON.stringify({ error: "Forbidden" }));
      return;
    }
    try {
      if (request.url === "/identity" && request.method === "GET") {
        const publicKey = import_node_crypto.default.createPublicKey(deviceKey()).export({ format: "der", type: "spki" }).toString("base64");
        response.end(
          JSON.stringify({ available: true, public_key: publicKey })
        );
        return;
      }
      if (request.url !== "/sign" || request.method !== "POST") {
        response.writeHead(404).end("{}");
        return;
      }
      if (Number(request.headers["content-length"] ?? 0) > 16384) {
        response.writeHead(413).end("{}");
        return;
      }
      const chunks = [];
      let size = 0;
      for await (const chunk of request) {
        size += chunk.length;
        if (size > 16384) {
          response.writeHead(413).end("{}");
          request.destroy();
          return;
        }
        chunks.push(chunk);
      }
      const body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
      if (Object.keys(body).length !== 1 || typeof body.challenge !== "string" || !body.challenge.startsWith("onevium-gateway:") || Buffer.byteLength(body.challenge) > 8192 || /[\r\n\0]/.test(body.challenge)) {
        response.writeHead(400).end("{}");
        return;
      }
      const signature = import_node_crypto.default.sign(null, Buffer.from(body.challenge), deviceKey()).toString("base64");
      response.end(JSON.stringify({ signature }));
    } catch {
      response.writeHead(503).end(
        JSON.stringify({
          error: "Device signing is unavailable. Reconnect using OS credential storage."
        })
      );
    }
  });
  listener.requestTimeout = 1e4;
  listener.headersTimeout = 1e4;
  listener.keepAliveTimeout = 2e3;
  listener.on("connection", (socket) => {
    sockets.add(socket);
    socket.once("close", () => sockets.delete(socket));
  });
  server = listener;
  starting = new Promise((resolve, reject) => {
    listener.once("error", reject);
    listener.listen(0, "127.0.0.1", () => {
      if (owner !== generation) {
        listener.close();
        reject(new Error("Device signer stopped."));
        return;
      }
      const address = listener.address();
      if (!address || typeof address === "string") {
        reject(new Error("Device signer could not bind."));
        return;
      }
      resolve({
        EXTERNAL_SIGNER_URL: `http://127.0.0.1:${address.port}`,
        EXTERNAL_SIGNER_TOKEN: token
      });
    });
  });
  return starting;
}
function stopExternalDeviceSigner() {
  generation++;
  server?.close();
  for (const socket of sockets) socket.destroy();
  sockets.clear();
  server = null;
  starting = null;
}
// Annotate the CommonJS export names for ESM import in node:
0 && (module.exports = {
  handleExternalSignerMessage,
  startExternalDeviceSigner,
  stopExternalDeviceSigner
});
