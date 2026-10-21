import { describe, expect, it } from "vitest";

import {
  parseTomlDocument,
  readTomlServer,
  renderTomlServer,
  serializeTomlDocument,
  serverBlockIndices,
} from "./toml-mcp.js";

/** Synthetic `~/.codex/config.toml` fixture, comments included. */
const SYNTHETIC_CONFIG = `personality = "pragmatic"

# Synthetic managed-memory server entry.
# The comment must stay attached to this table.
[mcp_servers.one-memory]
command = "node"
args = ["/Users/example/example-mcp/bin/server.mjs"]
enabled = true

[mcp_servers.example-service]
command = "/Applications/Example.app/Contents/MacOS/example-runtime"
args = ["run", "example-mcp@1.0.0"]
enabled = true

[mcp_servers.example-service.env]
EXAMPLE_API_KEY = "example-api-key-placeholder"

[features]
hooks = true
`;

describe("TOML MCP editing", () => {
  it("round-trips a synthetic config byte for byte", () => {
    const document = parseTomlDocument(SYNTHETIC_CONFIG);

    expect(serializeTomlDocument(document)).toBe(SYNTHETIC_CONFIG);
  });

  it("keeps a table's comments attached to that table", () => {
    const document = parseTomlDocument(SYNTHETIC_CONFIG);
    const [index] = serverBlockIndices(document, "one-memory");

    // The comment explains the synthetic entry, so removing it has to take
    // the comment with it rather than leave it pointing at our block.
    expect(document.blocks[index].text).toContain("Synthetic");
    expect(document.blocks[index].header).toBe("mcp_servers.one-memory");
    // A blank line separates it from `personality`, which stays in the preamble.
    expect(document.preamble).toContain("personality");
    expect(document.preamble).not.toContain("Synthetic");
  });

  it("treats sub-tables as part of the same server", () => {
    const document = parseTomlDocument(SYNTHETIC_CONFIG);

    expect(serverBlockIndices(document, "example-service")).toHaveLength(2);
    expect(readTomlServer(document, "example-service")).toEqual({
      command: "/Applications/Example.app/Contents/MacOS/example-runtime",
      args: ["run", "example-mcp@1.0.0"],
      env: { EXAMPLE_API_KEY: "example-api-key-placeholder" },
    });
  });

  it("removes only the named server and leaves every other byte alone", () => {
    const document = parseTomlDocument(SYNTHETIC_CONFIG);
    const indices = new Set(serverBlockIndices(document, "one-memory"));
    const stripped = serializeTomlDocument({
      ...document,
      blocks: document.blocks.filter((_block, index) => !indices.has(index)),
    });

    expect(stripped).not.toContain("example-mcp/bin/server.mjs");
    expect(stripped).not.toContain("Synthetic");
    expect(stripped).toContain('personality = "pragmatic"');
    expect(stripped).toContain("EXAMPLE_API_KEY");
    expect(stripped).toContain("[features]");
  });

  it("reads back exactly what it rendered", () => {
    const server = {
      command: "/Applications/One Memory.app/Contents/MacOS/One Memory",
      args: ["/Applications/One Memory.app/Contents/Resources/mcp.cjs"],
      env: { ELECTRON_RUN_AS_NODE: "1", ONE_MEMORY_MANAGED_BY: "one-memory" },
    };
    const document = parseTomlDocument(SYNTHETIC_CONFIG);
    const installed = {
      ...document,
      blocks: [
        ...document.blocks,
        ...renderTomlServer("one-memory-app", server),
      ],
    };

    const reparsed = parseTomlDocument(serializeTomlDocument(installed));
    expect(readTomlServer(reparsed, "one-memory-app")).toEqual(server);
  });

  it("escapes values that would otherwise break the file", () => {
    const server = {
      command: 'C:\\weird\\path with "quotes"',
      args: ['a"b', "c\\d"],
      env: { "needs-quoting.key": "tab\there" },
    };

    const document = parseTomlDocument(
      serializeTomlDocument({
        preamble: "",
        blocks: renderTomlServer("edge", server),
      }),
    );

    expect(readTomlServer(document, "edge")).toEqual(server);
  });

  it("returns null for a server whose shape we did not write", () => {
    const document = parseTomlDocument("[mcp_servers.other]\nargs = [1, 2]\n");

    expect(readTomlServer(document, "other")).toBeNull();
    expect(readTomlServer(document, "absent")).toBeNull();
  });

  it("handles a file with no tables at all", () => {
    const document = parseTomlDocument('personality = "pragmatic"\n');

    expect(document.blocks).toHaveLength(0);
    expect(serializeTomlDocument(document)).toBe('personality = "pragmatic"\n');
  });
});
