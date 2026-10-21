import { describe, expect, it } from "vitest";
import { isDefiniteRefusal, writeTraceStatus } from "./write-outcome";

function httpError(status: number) {
  return { response: { status, data: { detail: "refused" } } };
}

describe("isDefiniteRefusal", () => {
  it.each([400, 401, 403, 404, 409, 422, 429])(
    "treats %i as an answered refusal",
    (status) => {
      expect(isDefiniteRefusal(httpError(status))).toBe(true);
      expect(writeTraceStatus(httpError(status))).toBe("failed");
    },
  );

  it("does not treat a request timeout (408) as a refusal", () => {
    // The request may have been applied before the timeout answer was lost.
    expect(isDefiniteRefusal(httpError(408))).toBe(false);
    expect(writeTraceStatus(httpError(408))).toBe("unknown");
  });

  it.each([500, 502, 503, 504])(
    "treats %i as an unknown outcome, not a refusal",
    (status) => {
      expect(isDefiniteRefusal(httpError(status))).toBe(false);
      expect(writeTraceStatus(httpError(status))).toBe("unknown");
    },
  );

  it("treats a transport error with no response as unknown", () => {
    expect(
      isDefiniteRefusal(
        Object.assign(new Error("timeout of 30000ms exceeded"), {
          code: "ECONNABORTED",
        }),
      ),
    ).toBe(false);
    expect(isDefiniteRefusal(new Error("offline"))).toBe(false);
    expect(isDefiniteRefusal(undefined)).toBe(false);
    expect(isDefiniteRefusal(null)).toBe(false);
  });

  it("honours a wrapper that already classified the transport error", () => {
    // The hooks replace the axios error with a message-only Error, which would
    // otherwise erase the status and make a 409 indistinguishable from a
    // timeout. The carried flag has to win.
    expect(isDefiniteRefusal({ definiteRefusal: true })).toBe(true);
    expect(isDefiniteRefusal({ definiteRefusal: false })).toBe(false);
  });
});
