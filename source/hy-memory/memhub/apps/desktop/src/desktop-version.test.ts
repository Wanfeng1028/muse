import { describe, expect, it } from "vitest";
import { desktopVersionOutput } from "./desktop-version";

describe("Desktop version probe", () => {
  it("returns packaged SemVer for the product-private probe", () => {
    expect(
      desktopVersionOutput(["MemHub", "--memhub-version"], "0.1.0-internal.2"),
    ).toBe("MemHub 0.1.0-internal.2\n");
  });

  it("is inactive for normal application startup", () => {
    expect(desktopVersionOutput(["MemHub", "--background"], "1.0.0")).toBe(
      null,
    );
    expect(desktopVersionOutput(["MemHub"], "1.0.0")).toBeNull();
    expect(desktopVersionOutput(["MemHub", "--version"], "1.0.0")).toBeNull();
  });

  it("never prints an untrusted build value", () => {
    expect(
      desktopVersionOutput(["MemHub", "--memhub-version"], "release-one"),
    ).toBe("MemHub development\n");
  });
});
