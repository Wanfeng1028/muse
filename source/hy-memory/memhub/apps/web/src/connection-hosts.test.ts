import { expect, it } from "vitest";
import { preferenceHasSource } from "./connection-hosts";

it("treats claude and claude-code as the same insertion preference", () => {
  expect(preferenceHasSource(["claude"], "claude-code")).toBe(true);
  expect(preferenceHasSource(["claude-code"], "claude")).toBe(true);
  expect(preferenceHasSource(["cursor"], "workbuddy")).toBe(false);
});
