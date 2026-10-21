import { describe, expect, it } from "vitest";
import {
  defaultPythonCommand,
  getVenvPythonPath,
  isAutoPythonPath,
  systemPythonCandidates,
} from "./python-env.ts";

describe("python-env", () => {
  it("isAutoPythonPath accepts generic defaults", () => {
    expect(isAutoPythonPath(undefined)).toBe(true);
    expect(isAutoPythonPath("python3")).toBe(true);
    expect(isAutoPythonPath("python")).toBe(true);
    expect(isAutoPythonPath("C:\\Python311\\python.exe")).toBe(false);
  });

  it("getVenvPythonPath uses Scripts on win32", () => {
    const path = getVenvPythonPath();
    if (process.platform === "win32") {
      expect(path).toMatch(/Scripts[\\/]python\.exe$/i);
    } else {
      expect(path).toMatch(/bin[\\/]python$/);
    }
  });

  it("defaultPythonCommand is platform-aware", () => {
    if (process.platform === "win32") {
      expect(defaultPythonCommand()).toBe("python");
    } else {
      expect(defaultPythonCommand()).toBe("python3");
    }
  });

  it("systemPythonCandidates includes python on Windows", () => {
    if (process.platform === "win32") {
      expect(systemPythonCandidates()[0]).toBe("python");
    }
  });
});
