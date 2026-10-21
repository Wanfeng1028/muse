import type { Session } from "electron";
import { expect, it, vi } from "vitest";

import { installDenyAllPermissionPolicy } from "./permissions";

it("denies permission checks, requests, and display media", () => {
  let checkHandler: (() => boolean) | undefined;
  let requestHandler:
    | ((
        webContents: unknown,
        permission: string,
        callback: (allowed: boolean) => void,
      ) => void)
    | undefined;
  let displayHandler:
    | ((request: unknown, callback: (streams: object) => void) => void)
    | undefined;
  const target = {
    setPermissionCheckHandler: vi.fn((handler) => {
      checkHandler = handler;
    }),
    setPermissionRequestHandler: vi.fn((handler) => {
      requestHandler = handler;
    }),
    setDisplayMediaRequestHandler: vi.fn((handler) => {
      displayHandler = handler;
    }),
  } as unknown as Session;

  installDenyAllPermissionPolicy(target);

  expect(checkHandler?.()).toBe(false);
  const permissionResult = vi.fn();
  requestHandler?.({}, "media", permissionResult);
  expect(permissionResult).toHaveBeenCalledWith(false);
  const displayResult = vi.fn();
  displayHandler?.({}, displayResult);
  expect(displayResult).toHaveBeenCalledWith({});
});
