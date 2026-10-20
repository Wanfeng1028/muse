#!/usr/bin/env node

import crypto from "node:crypto";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { addVoiceAsset } from "./production-kit.mjs";

const BASE_URL = "https://api.fish.audio";
const TTS_MODELS = new Set(["s2.1-pro-free", "s2.1-pro", "s2-pro", "s1"]);
const LANGUAGES = /^[a-z]{2,3}(?:-[A-Z]{2})?$/;

function filled(value) {
  return typeof value === "string" && value.trim().length > 0;
}

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, "utf8").replace(/^\uFEFF/, ""));
}

function writeJsonAtomic(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const temporary = `${file}.tmp`;
  fs.writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`, "utf8");
  fs.renameSync(temporary, file);
}

function sha256(file) {
  return crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
}

function fishApiKey() {
  let key = String(process.env.FISH_API_KEY ?? "").trim();
  const configured = String(process.env.FISH_API_KEY_FILE ?? "").trim();
  const keyFile = configured ? path.resolve(configured) : path.join(os.homedir(), ".codex", "secrets", "fish.key");
  if (!key && fs.existsSync(keyFile)) key = fs.readFileSync(keyFile, "utf8").replace(/^\uFEFF/, "").trim();
  if (!key) throw new Error("缺少 FISH_API_KEY、FISH_API_KEY_FILE 或 ~/.codex/secrets/fish.key");
  return key;
}

function curlCommand() {
  return process.platform === "win32" ? "curl.exe" : "curl";
}

function curlBaseArgs(endpoint, options = {}) {
  const timeoutSeconds = Math.max(1, Math.ceil((options.timeoutMs ?? 120000) / 1000));
  const args = ["--silent", "--show-error", "--max-time", String(timeoutSeconds), "--request", options.method ?? "GET", `${BASE_URL}${endpoint}`, "--header", `Authorization: Bearer ${fishApiKey()}`];
  for (const [name, value] of Object.entries(options.headers ?? {})) args.push("--header", `${name}: ${value}`);
  if (options.json !== undefined) args.push("--data-raw", JSON.stringify(options.json));
  for (const value of options.formStrings ?? []) args.push("--form-string", value);
  for (const value of options.formFiles ?? []) args.push("--form", value);
  return args;
}

function curlFailure(result) {
  if (result.error) throw new Error(`curl 启动失败: ${result.error.message}`);
  if (result.status !== 0) throw new Error(`curl 请求失败: ${String(result.stderr ?? "").trim().slice(0, 1000) || `exit ${result.status}`}`);
}

function fishJsonRequest(endpoint, options = {}) {
  const marker = "\n__FISH_HTTP_STATUS__:";
  const result = spawnSync(curlCommand(), [...curlBaseArgs(endpoint, options), "--write-out", `${marker}%{http_code}`], { encoding: "utf8", maxBuffer: 20 * 1024 * 1024, windowsHide: true });
  curlFailure(result);
  const output = String(result.stdout ?? "");
  const index = output.lastIndexOf(marker);
  if (index < 0) throw new Error("Fish 响应缺少 HTTP 状态");
  const body = output.slice(0, index);
  const status = Number(output.slice(index + marker.length).trim());
  if (status < 200 || status >= 300) throw new Error(`Fish Audio HTTP ${status}: ${body.slice(0, 1000)}`);
  try { return JSON.parse(body); }
  catch { throw new Error(`Fish 返回非 JSON 响应: ${body.slice(0, 500)}`); }
}

function fishDownload(endpoint, output, options = {}) {
  const args = [...curlBaseArgs(endpoint, options), "--output", output, "--write-out", "%{http_code}"];
  const result = spawnSync(curlCommand(), args, { encoding: "utf8", maxBuffer: 1024 * 1024, windowsHide: true });
  if (result.error || result.status !== 0) {
    if (fs.existsSync(output)) fs.unlinkSync(output);
    curlFailure(result);
  }
  const status = Number(String(result.stdout ?? "").trim());
  if (status < 200 || status >= 300) {
    const body = fs.existsSync(output) ? fs.readFileSync(output, "utf8").slice(0, 1000) : "";
    if (fs.existsSync(output)) fs.unlinkSync(output);
    throw new Error(`Fish Audio HTTP ${status}: ${body}`);
  }
}

export function buildVoiceDiscoveryQuery(input = {}) {
  const language = input.language ?? "zh";
  const count = Number(input.count ?? 20);
  const page = Number(input.page ?? 1);
  const sortBy = input.sortBy ?? "task_count";
  if (!LANGUAGES.test(language)) throw new Error(`language 格式无效: ${language}`);
  if (!Number.isInteger(count) || count < 1 || count > 50) throw new Error("count 必须为 1–50");
  if (!Number.isInteger(page) || page < 1) throw new Error("page 必须为正整数");
  if (!new Set(["score", "task_count", "created_at"]).has(sortBy)) throw new Error(`sort 无效: ${sortBy}`);
  const query = new URLSearchParams({ page_size: String(count), page_number: String(page), language, sort_by: sortBy });
  if (filled(input.title)) query.set("title", input.title.trim());
  if (filled(input.tag)) query.set("tag", input.tag.trim());
  return query.toString();
}

export function buildFishTtsRequest(input) {
  const model = input.model ?? "s2.1-pro-free";
  if (!TTS_MODELS.has(model)) throw new Error(`不支持 Fish TTS model: ${model}`);
  if (!filled(input.text)) throw new Error("TTS text 不能为空");
  if (!filled(input.referenceId)) throw new Error("必须提供 Fish reference_id");
  const licenseScope = input.licenseScope ?? "evaluation-only";
  if (!new Set(["evaluation-only", "commercial"]).has(licenseScope)) throw new Error(`无效 licenseScope: ${licenseScope}`);
  if (model === "s2.1-pro-free" && licenseScope !== "evaluation-only") throw new Error("s2.1-pro-free 只能登记为 evaluation-only");
  return {
    model,
    licenseScope,
    payload: {
      text: input.text,
      reference_id: input.referenceId,
      format: "wav",
      sample_rate: 44100,
      prosody: { speed: input.speed ?? 1, volume: 0, normalize_loudness: true },
      normalize: true,
      latency: "normal"
    }
  };
}

export function wavDurationSeconds(file) {
  const buffer = fs.readFileSync(file);
  if (buffer.length < 44 || buffer.toString("ascii", 0, 4) !== "RIFF" || buffer.toString("ascii", 8, 12) !== "WAVE") throw new Error(`不是有效 WAV: ${file}`);
  let offset = 12;
  let byteRate = 0;
  let dataBytes = 0;
  while (offset + 8 <= buffer.length) {
    const id = buffer.toString("ascii", offset, offset + 4);
    const size = buffer.readUInt32LE(offset + 4);
    const start = offset + 8;
    if (id === "fmt " && size >= 16 && start + 12 <= buffer.length) byteRate = buffer.readUInt32LE(start + 8);
    if (id === "data") dataBytes += Math.min(size, Math.max(0, buffer.length - start));
    offset = start + size + (size % 2);
  }
  if (!byteRate || !dataBytes) throw new Error(`WAV 缺少 fmt/data: ${file}`);
  return dataBytes / byteRate;
}

export function normalizeWavHeader(file) {
  const buffer = fs.readFileSync(file);
  if (buffer.length < 44 || buffer.toString("ascii", 0, 4) !== "RIFF" || buffer.toString("ascii", 8, 12) !== "WAVE") throw new Error(`不是有效 WAV: ${file}`);
  let offset = 12;
  let dataHeader = -1;
  while (offset + 8 <= buffer.length) {
    const id = buffer.toString("ascii", offset, offset + 4);
    const size = buffer.readUInt32LE(offset + 4);
    if (id === "data") { dataHeader = offset; break; }
    offset += 8 + size + (size % 2);
  }
  if (dataHeader < 0) throw new Error(`WAV 缺少 data: ${file}`);
  buffer.writeUInt32LE(buffer.length - 8, 4);
  buffer.writeUInt32LE(buffer.length - (dataHeader + 8), dataHeader + 4);
  fs.writeFileSync(file, buffer);
  return { durationSeconds: wavDurationSeconds(file), sampleRate: buffer.readUInt32LE(24) };
}

export function registerFishMaster(manifest, manifestPath, input) {
  const output = path.resolve(input.output);
  const durationSeconds = wavDurationSeconds(output);
  if (durationSeconds < 2 || durationSeconds > 15) throw new Error(`H3 声音母版必须为 2–15 秒，当前 ${durationSeconds.toFixed(2)} 秒`);
  return addVoiceAsset(manifest, manifestPath, {
    voiceAssetId: input.voiceAssetId,
    characterId: input.characterId,
    path: output,
    language: input.language ?? "zh",
    durationSeconds: Number(durationSeconds.toFixed(3)),
    sampleType: input.sampleType ?? "voice-master",
    rights: input.rights ?? "synthetic",
    notes: input.notes ?? "Fish Audio 生成；需人工试听后批准",
    provider: "fish-audio",
    providerModel: input.model,
    providerVoiceId: input.referenceId,
    sourceType: input.sourceType ?? "voice-library-or-private-model",
    licenseScope: input.licenseScope,
    generatedAt: new Date().toISOString(),
    generationSha256: sha256(output)
  });
}

function argsObject(argv) {
  const result = { _: [] };
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith("--")) result._.push(token);
    else if (token === "--execute") result.execute = true;
    else {
      const value = argv[index + 1];
      if (value === undefined || value.startsWith("--")) throw new Error(`${token} 缺少值`);
      result[token.slice(2)] = value;
      index += 1;
    }
  }
  return result;
}

function required(args, name) {
  if (!filled(args[name])) throw new Error(`缺少 --${name}`);
  return args[name];
}

function confirmExecute(args, id) {
  if (!args.execute) return false;
  if (args.confirm !== id) throw new Error(`执行外部生成必须提供 --confirm ${id}`);
  return true;
}

async function discoverCommand(args) {
  const id = required(args, "id");
  const output = path.resolve(required(args, "out"));
  const query = buildVoiceDiscoveryQuery({ language: args.language, count: Number(args.count ?? 20), page: Number(args.page ?? 1), sortBy: args.sort, title: args.title, tag: args.tag });
  const endpoint = `/model?${query}`;
  if (!confirmExecute(args, id)) {
    console.log(JSON.stringify({ action: "dry-run", endpoint, id, output, note: "read-only public voice discovery" }, null, 2));
    return;
  }
  const value = fishJsonRequest(endpoint);
  const items = (Array.isArray(value.items) ? value.items : []).map((item) => ({
    referenceId: item._id, title: item.title, description: item.description, tags: item.tags, languages: item.languages,
    visibility: item.visibility, licensed: item.licensed === true, taskCount: item.task_count,
    samples: (Array.isArray(item.samples) ? item.samples : []).map((sample) => ({ title: sample.title, text: sample.text, audio: sample.audio }))
  }));
  const record = { provider: "fish-audio", generatedAt: new Date().toISOString(), query: Object.fromEntries(new URLSearchParams(query)), licenseScope: "evaluation-only", total: value.total, items };
  writeJsonAtomic(output, record);
  console.log(JSON.stringify({ output, count: items.length, total: value.total }, null, 2));
}

async function auditionCommand(args) {
  const id = required(args, "id");
  const outputDir = path.resolve(required(args, "out"));
  const referenceIds = required(args, "reference-ids").split(",").map((value) => value.trim()).filter(Boolean);
  if (!referenceIds.length || referenceIds.length > 4 || new Set(referenceIds).size !== referenceIds.length) throw new Error("--reference-ids 必须包含 1–4 个不重复 ID");
  const requestBase = { model: args.model ?? "s2.1-pro-free", text: required(args, "text"), licenseScope: args["license-scope"], speed: Number(args.speed ?? 1) };
  if (!confirmExecute(args, id)) {
    console.log(JSON.stringify({ action: "dry-run", endpoint: "/v1/tts", id, outputDir, referenceIds, model: requestBase.model, text: requestBase.text, licenseScope: requestBase.licenseScope ?? "evaluation-only" }, null, 2));
    return;
  }
  fs.mkdirSync(outputDir, { recursive: true });
  const candidates = [];
  for (const [index, referenceId] of referenceIds.entries()) {
    const voice = fishJsonRequest(`/model/${referenceId}`);
    const request = buildFishTtsRequest({ ...requestBase, referenceId });
    const file = path.join(outputDir, `${id}-candidate-${String(index + 1).padStart(2, "0")}.wav`);
    const temporary = `${file}.part`;
    fishDownload("/v1/tts", temporary, { method: "POST", headers: { "Content-Type": "application/json", model: request.model }, json: request.payload });
    const audio = normalizeWavHeader(temporary);
    fs.renameSync(temporary, file);
    candidates.push({ index: index + 1, referenceId, sourceVoiceTitle: voice.title, sourceVisibility: voice.visibility, sourceLicensed: voice.licensed === true, path: file, durationSeconds: Number(audio.durationSeconds.toFixed(3)), sampleRate: audio.sampleRate, sha256: sha256(file) });
  }
  const record = { provider: "fish-audio", model: requestBase.model, generatedAt: new Date().toISOString(), auditionText: requestBase.text, licenseScope: "evaluation-only", humanApproval: "pending", productionExportAllowed: false, candidates };
  const manifest = path.join(outputDir, `${id}-candidates.json`);
  writeJsonAtomic(manifest, record);
  console.log(JSON.stringify({ manifest, candidates }, null, 2));
}

async function cloneCommand(args) {
  const id = required(args, "id");
  const sample = path.resolve(required(args, "sample"));
  const output = path.resolve(required(args, "out"));
  if (!fs.existsSync(sample) || !fs.statSync(sample).isFile()) throw new Error(`克隆样本不存在: ${sample}`);
  const visibility = args.visibility ?? "private";
  if (!new Set(["private", "unlist", "public"]).has(visibility)) throw new Error(`visibility 无效: ${visibility}`);
  if (!confirmExecute(args, id)) {
    console.log(JSON.stringify({ action: "dry-run", endpoint: "/model", id, sample, sampleSha256: sha256(sample), title: args.title ?? id, visibility, output }, null, 2));
    return;
  }
  const value = fishJsonRequest("/model", {
    method: "POST",
    formStrings: ["type=tts", `title=${args.title ?? id}`, `visibility=${visibility}`, "train_mode=fast"],
    formFiles: [`voices=@${sample};type=audio/wav`]
  });
  const record = { provider: "fish-audio", referenceId: value._id, state: value.state, title: value.title, visibility: value.visibility, sample, sampleSha256: sha256(sample), createdAt: new Date().toISOString(), licenseScope: "evaluation-only" };
  writeJsonAtomic(output, record);
  console.log(JSON.stringify(record, null, 2));
}

async function masterCommand(args) {
  const manifestPath = path.resolve(required(args, "production"));
  const voiceAssetId = required(args, "id");
  const output = path.resolve(required(args, "out"));
  const request = buildFishTtsRequest({ model: args.model ?? "s2.1-pro-free", text: required(args, "text"), referenceId: required(args, "reference-id"), licenseScope: args["license-scope"], speed: Number(args.speed ?? 1) });
  if (!confirmExecute(args, voiceAssetId)) {
    console.log(JSON.stringify({ action: "dry-run", endpoint: "/v1/tts", voiceAssetId, model: request.model, licenseScope: request.licenseScope, output, payload: request.payload }, null, 2));
    return;
  }
  fs.mkdirSync(path.dirname(output), { recursive: true });
  const temporary = `${output}.part`;
  fishDownload("/v1/tts", temporary, { method: "POST", headers: { "Content-Type": "application/json", model: request.model }, json: request.payload });
  normalizeWavHeader(temporary);
  fs.renameSync(temporary, output);
  const manifest = readJson(manifestPath);
  const asset = registerFishMaster(manifest, manifestPath, {
    output, voiceAssetId, characterId: required(args, "character"), language: args.language ?? "zh",
    model: request.model, referenceId: request.payload.reference_id, licenseScope: request.licenseScope,
    rights: args.rights ?? "unknown", sourceType: args.source ?? "voice-library-or-private-model", notes: args.note ?? ""
  });
  manifest.project.updatedAt = new Date().toISOString();
  writeJsonAtomic(manifestPath, manifest);
  console.log(JSON.stringify(asset, null, 2));
}

function help() {
  console.log(`Fish Audio voice adapter

  node scripts/fish-voice.mjs discover --id <search-id> --out <voices.json> [--title <term>] [--language zh] [--count 20] [--execute --confirm <search-id>]
  node scripts/fish-voice.mjs audition --id <audition-id> --reference-ids <id1,id2,id3> --text <preview> --out <dir> [--model s2.1-pro-free] [--execute --confirm <audition-id>]
  node scripts/fish-voice.mjs clone --id <voice-id> --sample <candidate.wav> --out <voice.json> [--visibility private] [--execute --confirm <voice-id>]
  node scripts/fish-voice.mjs master --production <production.json> --id <asset-id> --character <C01> --reference-id <fish-id> --text <master text> --out <master.wav> [--model s2.1-pro-free] [--execute --confirm <asset-id>]

Omit --execute for a network-free dry run. API keys are read only from FISH_API_KEY, FISH_API_KEY_FILE, or ~/.codex/secrets/fish.key.`);
}

async function main() {
  const [command, ...rest] = process.argv.slice(2);
  if (!command || ["help", "--help", "-h"].includes(command)) return help();
  const args = argsObject(rest);
  if (command === "discover") return discoverCommand(args);
  if (command === "audition") return auditionCommand(args);
  if (command === "clone") return cloneCommand(args);
  if (command === "master") return masterCommand(args);
  throw new Error(`未知命令: ${command}`);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((error) => { console.error(`ERROR ${error.message}`); process.exitCode = 1; });
}
