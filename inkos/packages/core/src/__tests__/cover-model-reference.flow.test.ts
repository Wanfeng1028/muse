import { mkdtemp, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { it, expect, vi } from "vitest";
import { saveSecrets } from "../llm/secrets.js";
import { resolveCoverGenerationRequest, generateImageFromPrompt } from "../pipeline/short-fiction-runner.js";
import { createServer } from "node:http";
import { once } from "node:events";

it("keeps provider credentials on its own origin when an image URL requires authentication", async () => {
  const remoteHeaders: Array<string | undefined> = [], localHeaders: Array<string | undefined> = [];
  const image = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=', 'base64');
  const remote = createServer((req, res) => {remoteHeaders.push(req.headers.authorization); res.writeHead(403); res.end();});
  remote.listen(0, "127.0.0.1"); await once(remote, "listening");
  const remoteUrl = `http://127.0.0.1:${(remote.address() as {port:number}).port}/image.png`;
  let generation = 0;
  const provider = createServer((req, res) => {
    if (req.method === "POST") {
      req.resume(); generation++;
      res.writeHead(200, {"Content-Type":"application/json"});
      res.end(JSON.stringify({data:[{url:generation === 1 ? remoteUrl : `http://127.0.0.1:${(provider.address() as {port:number}).port}/private.png`}]}));
    } else {
      localHeaders.push(req.headers.authorization);
      res.writeHead(req.headers.authorization ? 200 : 401, {"Content-Type":"image/png"});
      res.end(req.headers.authorization ? image : undefined);
    }
  });
  provider.listen(0, "127.0.0.1"); await once(provider, "listening");
  try {
    const request = {api:"images" as const,baseUrl:`http://127.0.0.1:${(provider.address() as {port:number}).port}/v1`,model:"image-fixture",apiKey:"fixture-key"};
    await expect(generateImageFromPrompt(request, "A lantern", "1024x1024")).rejects.toMatchObject({code:"IMAGE_DOWNLOAD_FAILED",status:403});
    expect(remoteHeaders).toEqual([undefined]);
    expect((await generateImageFromPrompt(request, "A lantern", "1024x1024")).buffer).toEqual(image);
    expect(localHeaders).toEqual([undefined,"Bearer fixture-key"]);
  } finally {
    for (const server of [provider, remote]) {server.closeAllConnections(); await new Promise<void>(resolve => server.close(() => resolve()));}
  }
});

it("resolves configured service labels to model IDs while preserving other explicit models", async () => {
  const root = await mkdtemp(join(tmpdir(), "inkos-cover-model-"));
  vi.stubEnv("INKOS_COVER_ENDPOINT", "");
  vi.stubEnv("INKOS_COVER_BASE_URL", "");
  try {
    const config = { name: "fixture", version: "0.1.0", language: "zh", notify: [],
      llm: { provider: "openai", model: "fixture", baseUrl: "https://api.kkaiapi.com/v1", cover: { service: "kkaiapi", model: "gpt-image-2" } } };
    await writeFile(join(root, "inkos.json"), JSON.stringify(config));
    await saveSecrets(root, { services: { kkaiapi: { apiKey: "fixture-key" } } });
    const requests = [];
    for (const coverModel of [undefined, "gpt-image-2", "kkaiapi gpt-image-2", "kkaiapi/gpt-image-2", "kkaiapi · gpt-image-2", "vendor/custom-image"]) {
      requests.push(await resolveCoverGenerationRequest({ root, coverModel }));
    }
    expect(requests.map(request => request.model)).toEqual([
      "gpt-image-2", "gpt-image-2", "gpt-image-2", "gpt-image-2", "gpt-image-2", "vendor/custom-image",
    ]);
    expect(requests.every(request => request.baseUrl === "https://api.kkaiapi.com/v1" && request.apiKey === "fixture-key")).toBe(true);
    config.llm.cover.model = "vendor/custom-image";
    await writeFile(join(root, "inkos.json"), JSON.stringify(config));
    expect((await resolveCoverGenerationRequest({ root, coverModel: "kkaiapi/vendor/custom-image" })).model).toBe("vendor/custom-image");
    expect((await resolveCoverGenerationRequest({ root, coverModel: "kkaiapi/unknown-model" })).model).toBe("kkaiapi/unknown-model");
    vi.stubEnv("INKOS_COVER_BASE_URL", "https://api.kkaiapi.com/v1");
    vi.stubEnv("INKOS_COVER_API_KEY", "fixture-key");
    expect((await resolveCoverGenerationRequest({ root, coverModel: "kkaiapi/gpt-image-2" })).model).toBe("gpt-image-2");
    expect((await resolveCoverGenerationRequest({ root, coverBaseUrl: "https://custom.example/v1", coverModel: "kkaiapi/gpt-image-2" })).model).toBe("kkaiapi/gpt-image-2");
  } finally {
    vi.unstubAllEnvs();
    await rm(root, { recursive: true, force: true });
  }
});
