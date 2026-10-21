import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  CLI_PROTOCOL,
  CLI_SUPPORTED_RUNTIME_PROTOCOL,
  RUNTIME_MANIFEST_SCHEMA,
  RUNTIME_PROTOCOL,
  RUNTIME_SUPPORTED_CLI_PROTOCOL,
} from "./release-contract.js";

describe("release protocol contract", () => {
  it("matches the root release contract exactly", async () => {
    const root = path.resolve(
      path.dirname(fileURLToPath(import.meta.url)),
      "../../..",
    );
    const pkg = JSON.parse(
      await readFile(path.join(root, "package.json"), "utf8"),
    );
    expect({
      runtime_manifest_schema: RUNTIME_MANIFEST_SCHEMA,
      cli_protocol: CLI_PROTOCOL,
      cli_supported_runtime_protocol: CLI_SUPPORTED_RUNTIME_PROTOCOL,
      runtime_protocol: RUNTIME_PROTOCOL,
      runtime_supported_cli_protocol: RUNTIME_SUPPORTED_CLI_PROTOCOL,
    }).toEqual({
      runtime_manifest_schema: pkg.release.runtime_manifest_schema,
      cli_protocol: pkg.release.cli_protocol,
      cli_supported_runtime_protocol:
        pkg.release.cli_supported_runtime_protocol,
      runtime_protocol: pkg.release.runtime_protocol,
      runtime_supported_cli_protocol:
        pkg.release.runtime_supported_cli_protocol,
    });
  });
});
