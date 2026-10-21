import { describe, expect, it } from "vitest";

import { resolveHostWorkspacePath } from "./host-workspace.js";

const home = "/Users/example";

describe("which project the caller is in", () => {
  it("believes the host over its own working directory", () => {
    // The host may spawn the MCP server with home as cwd and state the
    // workspace separately in the environment.
    expect(
      resolveHostWorkspacePath({
        env: { WORKSPACE_FOLDER_PATHS: "/Users/example/hy-memory-admin" },
        cwd: home,
        home,
      }),
    ).toBe("/Users/example/hy-memory-admin");
  });

  it("uses the working directory when the host says nothing", () => {
    expect(
      resolveHostWorkspacePath({
        env: {},
        cwd: "/Users/example/work/api-service",
        home,
      }),
    ).toBe("/Users/example/work/api-service");
  });

  it("refuses to call the home directory a project", () => {
    // This is what a host that told us nothing looks like. Home is itself a
    // recorded workspace on this machine, so accepting it would fold
    // unrelated home-rooted memories into every project's recall.
    expect(
      resolveHostWorkspacePath({ env: {}, cwd: home, home }),
    ).toBeUndefined();
    expect(
      resolveHostWorkspacePath({ env: {}, cwd: `${home}/`, home }),
    ).toBeUndefined();
  });

  it("takes the first folder of a multi-root window", () => {
    expect(
      resolveHostWorkspacePath({
        env: {
          WORKSPACE_FOLDER_PATHS: "/Users/example/a,/Users/example/b",
        },
        cwd: home,
        home,
      }),
    ).toBe("/Users/example/a");
  });

  it("ignores anything that is not an absolute directory", () => {
    for (const value of ["", "   ", "relative/path", "~/work"]) {
      expect(
        resolveHostWorkspacePath({
          env: { WORKSPACE_FOLDER_PATHS: value },
          cwd: home,
          home,
        }),
      ).toBeUndefined();
    }
  });

  it("drops a trailing separator that would hash differently", () => {
    expect(
      resolveHostWorkspacePath({
        env: { WORKSPACE_FOLDER_PATHS: "/Users/example/work/api-service/" },
        cwd: home,
        home,
      }),
    ).toBe("/Users/example/work/api-service");
  });
});
