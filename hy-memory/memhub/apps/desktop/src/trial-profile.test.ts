import { expect, it } from "vitest";
import { resolveTrialProfile } from "./trial-profile";

it("does not change normal builds or let a runtime variable enable trial mode", () => {
  expect(
    resolveTrialProfile(null, "/home/user", "/app-data", "smoke"),
  ).toBeNull();
});

it("binds both stores to the compiled trial identity", () => {
  expect(resolveTrialProfile("20260919", "/home/user", "/app-data")).toEqual({
    dataDir: "/home/user/.one-memory-trial-20260919",
    userDataDir: "/app-data/One Memory Trial 20260919",
  });
});

it("isolates smoke instances without accepting arbitrary paths", () => {
  expect(
    resolveTrialProfile("20260919", "/home/user", "/app-data", "smoke-1"),
  ).toEqual({
    dataDir: "/home/user/.one-memory-trial-20260919-smoke-1",
    userDataDir: "/app-data/One Memory Trial 20260919-smoke-1",
  });
});

it.each([
  "",
  "../daily",
  "/tmp/data",
  "x/y",
  "x\\y",
  "A",
  "a".repeat(49),
  true,
])("rejects invalid build identity instead of falling back: %s", (id) => {
  expect(() => resolveTrialProfile(id, "/home/user", "/app-data")).toThrow(
    "invalid_trial_profile",
  );
});

it.each(["../daily", "/tmp/data", "", "x y", "a".repeat(33)])(
  "rejects invalid test-instance suffix: %s",
  (instance) => {
    expect(() =>
      resolveTrialProfile("20260919", "/home/user", "/app-data", instance),
    ).toThrow("invalid_trial_instance");
  },
);
