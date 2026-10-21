import { describe, expect, it } from "vitest";
import { classifyModelActivate, classifyModelRemove } from "./model-operation";

describe("model remove classification", () => {
  it("treats 404 and 409 as refusals, matching the CLI", () => {
    expect(classifyModelRemove(404, "model_profile_not_found")).toEqual({
      state: "refused",
      code: "model_profile_not_found",
    });
    expect(classifyModelRemove(409, "active_model_profile")).toEqual({
      state: "refused",
      code: "active_model_profile",
    });
  });

  it("prefers the stable detail over the status code", () => {
    expect(classifyModelRemove(409, "model_profile_not_found").state).toBe(
      "refused",
    );
    expect(classifyModelRemove(404, "active_model_profile")).toEqual({
      state: "refused",
      code: "active_model_profile",
    });
  });

  it("treats 204 as removed and other non-2xx as unknown", () => {
    expect(classifyModelRemove(204)).toEqual({ state: "removed" });
    expect(classifyModelRemove(503, "secure_storage_unavailable")).toEqual({
      state: "unknown",
      code: "secure_storage_unavailable",
    });
    expect(classifyModelRemove(500)).toEqual({
      state: "unknown",
      code: "http_500",
    });
  });
});

describe("model activate classification", () => {
  it("separates a 2xx from a client rejection and a server fault", () => {
    expect(classifyModelActivate(200)).toEqual({ state: "activated" });
    expect(classifyModelActivate(404, "model_profile_not_found")).toEqual({
      state: "rejected",
      code: "model_profile_not_found",
    });
    expect(classifyModelActivate(500)).toEqual({
      state: "unknown",
      code: "http_500",
    });
  });
});
