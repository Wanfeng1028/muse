#!/usr/bin/env node

import { spawn, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import http from "node:http";
import https from "node:https";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../..",
);

export async function verifyReleaseProxy(options = {}) {
  if (process.platform !== "linux") {
    throw new Error("release_proxy_verification_requires_linux");
  }
  const temporary = await mkdtemp(
    path.join(os.tmpdir(), "memhub-release-proxy-"),
  );
  const originRequests = [];
  const proxyConnects = [];
  const tunnelSockets = new Set();
  let origin;
  let proxy;
  try {
    assertTrackedGitTreeClean(root);
    const tls = generateTlsFixture(temporary);
    const rootPackage = JSON.parse(
      await readFile(path.join(root, "package.json"), "utf8"),
    );
    const version = rootPackage.version;
    const buildNumber = rootPackage.release?.build_number;
    if (!Number.isSafeInteger(buildNumber) || buildNumber < 0) {
      throw new Error("release_proxy_build_number_invalid");
    }
    const gitCommit = commandOutput("git", ["rev-parse", "HEAD"], root);
    command("pnpm", ["--filter", "@one-memory/cli", "build"], root, {
      ...process.env,
      ONE_MEMORY_VERSION: version,
      ONE_MEMORY_BUILD_NUMBER: String(buildNumber),
      ONE_MEMORY_COMMIT: gitCommit,
    });

    origin = https.createServer(
      {
        key: await readFile(tls.serverKey),
        cert: await readFile(tls.serverCertificate),
      },
      (request, response) => {
        originRequests.push(request.url ?? "");
        if (request.url !== "/release-manifest.json") {
          response.writeHead(404).end();
          return;
        }
        const body = Buffer.from(
          JSON.stringify(releaseManifest(version, buildNumber, gitCommit)),
        );
        response.writeHead(200, {
          "content-type": "application/json",
          "content-length": String(body.byteLength),
        });
        response.end(body);
      },
    );
    await listen(origin);
    const originAddress = origin.address();
    if (!originAddress || typeof originAddress === "string") {
      throw new Error("release_proxy_origin_address_unavailable");
    }

    proxy = http.createServer((_request, response) => {
      response.writeHead(405).end();
    });
    proxy.on("connect", (request, client, head) => {
      proxyConnects.push(request.url ?? "");
      tunnelSockets.add(client);
      client.once("close", () => tunnelSockets.delete(client));
      const [host, portText] = (request.url ?? "").split(":");
      const port = Number(portText);
      if (!host || !Number.isSafeInteger(port)) {
        client.end("HTTP/1.1 400 Bad Request\r\n\r\n");
        return;
      }
      const upstream = net.connect(port, host, () => {
        client.write("HTTP/1.1 200 Connection Established\r\n\r\n");
        if (head.byteLength > 0) upstream.write(head);
        upstream.pipe(client);
        client.pipe(upstream);
      });
      tunnelSockets.add(upstream);
      upstream.once("close", () => tunnelSockets.delete(upstream));
      upstream.on("error", () => client.destroy());
      client.on("error", () => upstream.destroy());
    });
    await listen(proxy);
    const proxyAddress = proxy.address();
    if (!proxyAddress || typeof proxyAddress === "string") {
      throw new Error("release_proxy_address_unavailable");
    }

    const manifestUrl = `https://127.0.0.1:${originAddress.port}/release-manifest.json`;
    const proxyUrl = `http://127.0.0.1:${proxyAddress.port}`;
    const proxied = await preview({
      temporary,
      name: "proxied",
      manifestUrl,
      caCertificate: tls.caCertificate,
      proxyUrl,
      noProxy: "",
    });
    if (proxyConnects.length !== 1) {
      throw new Error("release_proxy_not_used");
    }
    const connectsAfterProxy = proxyConnects.length;
    const bypassed = await preview({
      temporary,
      name: "bypassed",
      manifestUrl,
      caCertificate: tls.caCertificate,
      proxyUrl,
      noProxy: "127.0.0.1",
    });
    if (proxyConnects.length !== connectsAfterProxy) {
      throw new Error("release_no_proxy_not_honored");
    }
    if (originRequests.length !== 2) {
      throw new Error("release_proxy_origin_request_count_invalid");
    }
    const receipt = {
      schema_version: 1,
      product: "memhub-release-proxy-verification",
      version,
      build_number: buildNumber,
      git_commit: gitCommit,
      manifest_url: manifestUrl,
      proxy_url: proxyUrl,
      proxy_connects: proxyConnects,
      origin_requests: originRequests,
      proxied,
      bypassed,
      result: "passed",
    };
    if (options.receipt) {
      const receiptPath = path.resolve(options.receipt);
      await mkdir(path.dirname(receiptPath), { recursive: true, mode: 0o700 });
      await writeFile(receiptPath, `${JSON.stringify(receipt, null, 2)}\n`, {
        mode: 0o600,
      });
    }
    return receipt;
  } finally {
    for (const socket of tunnelSockets) socket.destroy();
    await close(proxy);
    await close(origin);
    await rm(temporary, { recursive: true, force: true });
  }
}

function releaseManifest(version, buildNumber, gitCommit) {
  const artifactBytes = Buffer.from("not downloaded during preview\n");
  return {
    schema_version: 1,
    product: "memhub-release",
    version,
    build_number: buildNumber,
    git_commit: gitCommit,
    channel: version.includes("-") ? "prerelease" : "stable",
    cli_protocol: 1,
    supported_runtime_protocol: { min: 1, max: 1 },
    runtime_protocol: 1,
    supported_cli_protocol: { min: 1, max: 1 },
    published_at: "2026-10-13T00:00:00Z",
    artifacts: [
      {
        kind: "runtime",
        platform: "linux",
        arch: process.arch,
        format: "tar.gz",
        filename: `memhub-runtime-v${version}-linux-${process.arch}.tar.gz`,
        url: "https://127.0.0.1/runtime.tar.gz",
        bytes: artifactBytes.byteLength,
        unpacked_bytes: 1,
        sha256: createHash("sha256").update(artifactBytes).digest("hex"),
        runtime_manifest_schema: 1,
      },
    ],
  };
}

async function preview(options) {
  const work = path.join(options.temporary, options.name);
  const home = path.join(work, "home");
  await mkdir(home, { recursive: true, mode: 0o700 });
  const environment = {
    ...process.env,
    HOME: home,
    XDG_CONFIG_HOME: path.join(home, ".config"),
    XDG_DATA_HOME: path.join(home, ".local", "share"),
    NODE_EXTRA_CA_CERTS: options.caCertificate,
    HTTPS_PROXY: options.proxyUrl,
    https_proxy: "",
    HTTP_PROXY: "",
    http_proxy: "",
    ALL_PROXY: "",
    all_proxy: "",
    NO_PROXY: options.noProxy,
    no_proxy: "",
    MEMHUB_RELEASE_ALLOWED_HOSTS: "127.0.0.1",
    NO_COLOR: "1",
  };
  const result = await run(
    process.execPath,
    [
      path.join(root, "apps/cli/dist/one-memory.cjs"),
      "install",
      "--release-manifest-url",
      options.manifestUrl,
      "--install-root",
      path.join(work, "install"),
      "--home",
      home,
      "--bin-dir",
      path.join(work, "bin"),
      "--data-dir",
      path.join(work, "data"),
      "--xdg-config-home",
      environment.XDG_CONFIG_HOME,
      "--no-shell-path",
      "--json",
    ],
    { cwd: root, env: environment },
  );
  if (result.status !== 0) {
    throw new Error(
      `release_proxy_preview_failed:${result.stderr || result.stdout}`,
    );
  }
  const document = JSON.parse(result.stdout);
  if (document.apply !== false || document.release?.version === undefined) {
    throw new Error("release_proxy_preview_invalid");
  }
  return {
    version: document.release.version,
    git_commit: document.release.git_commit,
    cli_protocol: document.release.cli_protocol,
    runtime_protocol: document.release.runtime_protocol,
  };
}

function generateTlsFixture(directory) {
  const caKey = path.join(directory, "ca-key.pem");
  const caCertificate = path.join(directory, "ca-cert.pem");
  const serverKey = path.join(directory, "server-key.pem");
  const serverRequest = path.join(directory, "server.csr");
  const serverCertificate = path.join(directory, "server-cert.pem");
  const extension = path.join(directory, "server.ext");
  command(
    "openssl",
    [
      "req",
      "-x509",
      "-newkey",
      "rsa:2048",
      "-nodes",
      "-days",
      "1",
      "-subj",
      "/CN=MemHub Proxy Test CA",
      "-addext",
      "basicConstraints=critical,CA:TRUE",
      "-addext",
      "keyUsage=critical,keyCertSign,cRLSign",
      "-keyout",
      caKey,
      "-out",
      caCertificate,
    ],
    root,
  );
  command(
    "openssl",
    [
      "req",
      "-newkey",
      "rsa:2048",
      "-nodes",
      "-subj",
      "/CN=127.0.0.1",
      "-keyout",
      serverKey,
      "-out",
      serverRequest,
    ],
    root,
  );
  spawnSync(
    process.execPath,
    [
      "-e",
      "require('fs').writeFileSync(process.argv[1], process.argv[2])",
      extension,
      [
        "basicConstraints=critical,CA:FALSE",
        "keyUsage=critical,digitalSignature,keyEncipherment",
        "extendedKeyUsage=serverAuth",
        "subjectAltName=IP:127.0.0.1,DNS:localhost",
        "",
      ].join("\n"),
    ],
    { stdio: "inherit" },
  );
  command(
    "openssl",
    [
      "x509",
      "-req",
      "-days",
      "1",
      "-CA",
      caCertificate,
      "-CAkey",
      caKey,
      "-CAcreateserial",
      "-in",
      serverRequest,
      "-out",
      serverCertificate,
      "-extfile",
      extension,
    ],
    root,
  );
  return { caCertificate, serverCertificate, serverKey };
}

function command(program, arguments_, cwd, env = process.env) {
  const result = spawnSync(program, arguments_, { cwd, env, stdio: "inherit" });
  if (result.status !== 0) {
    throw new Error(`release_proxy_command_failed:${program}:${result.status}`);
  }
}

function commandOutput(program, arguments_, cwd) {
  const result = spawnSync(program, arguments_, { cwd, encoding: "utf8" });
  const value = result.stdout?.trim();
  if (result.status !== 0 || !value) {
    throw new Error(`release_proxy_command_failed:${program}:${result.status}`);
  }
  return value;
}

function assertTrackedGitTreeClean(directory) {
  for (const arguments_ of [
    ["diff", "--quiet", "--"],
    ["diff", "--cached", "--quiet", "--"],
  ]) {
    const result = spawnSync("git", arguments_, { cwd: directory });
    if (result.status !== 0) {
      throw new Error("release_proxy_source_modified");
    }
  }
}

function run(program, arguments_, options) {
  return new Promise((resolve, reject) => {
    const child = spawn(program, arguments_, {
      cwd: options.cwd,
      env: options.env,
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.setEncoding("utf8");
    child.stderr.setEncoding("utf8");
    child.stdout.on("data", (chunk) => (stdout += chunk));
    child.stderr.on("data", (chunk) => (stderr += chunk));
    child.once("error", reject);
    child.once("close", (status) => resolve({ status, stdout, stderr }));
  });
}

function listen(server) {
  return new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
}

function close(server) {
  if (!server) return Promise.resolve();
  return new Promise((resolve) => server.close(resolve));
}

function parseArguments(arguments_) {
  const options = {};
  for (let index = 0; index < arguments_.length; index += 1) {
    const flag = arguments_[index];
    const value = arguments_[++index];
    if (!value) throw new Error(`missing value for ${flag}`);
    if (flag === "--receipt") options.receipt = value;
    else throw new Error(`invalid argument: ${flag}`);
  }
  return options;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  verifyReleaseProxy(parseArguments(process.argv.slice(2)))
    .then((receipt) =>
      process.stdout.write(`${JSON.stringify(receipt, null, 2)}\n`),
    )
    .catch((error) => {
      process.stderr.write(
        `${error instanceof Error ? error.message : error}\n`,
      );
      process.exitCode = 1;
    });
}
