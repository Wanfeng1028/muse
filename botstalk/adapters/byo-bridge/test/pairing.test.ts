import { describe, it, expect, vi, beforeEach } from "vitest";
import { redeemPairingCode, PairingError } from "../src/pairing.js";

describe("redeemPairingCode", () => {
  const mockFetch = vi.fn();

  beforeEach(() => {
    mockFetch.mockReset();
  });

  const setupMock = (ok: boolean, status: number, json: any) => {
    mockFetch.mockResolvedValue({
      ok,
      status,
      json: () => Promise.resolve(json),
    });
  };

  it("should return fields on success and send correct request", async () => {
    const responseJson = { room: "room1", adapter_id: "adapter1", redeemed_at_ms: 123456 };
    setupMock(true, 200, responseJson);

    const result = await redeemPairingCode("http://base", "code1", "adapter1", mockFetch);

    expect(result).toEqual(responseJson);
    expect(mockFetch).toHaveBeenCalledTimes(1);
    
    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toBe("http://base/api/pairing-codes/redeem");
    expect(init.method).toBe("POST");
    expect(init.headers).toEqual({ "Content-Type": "application/json" });
    expect(JSON.parse(init.body)).toEqual({ code: "code1", adapter_id: "adapter1" });
  });

  it("should throw PairingError with server error code on 404", async () => {
    setupMock(false, 404, { error: "NOT_FOUND", message: "Resource not found" });

    const p = redeemPairingCode("http://base", "c", "a", mockFetch);
    await expect(p).rejects.toBeInstanceOf(PairingError);
    await expect(p).rejects.toHaveProperty("code", "NOT_FOUND");
  });

  it("should throw PairingError with PAIRING_CODE_USED on 409", async () => {
    setupMock(false, 409, { error: "PAIRING_CODE_USED", message: "Code already used" });

    const p = redeemPairingCode("http://base", "c", "a", mockFetch);
    await expect(p).rejects.toBeInstanceOf(PairingError);
    await expect(p).rejects.toHaveProperty("code", "PAIRING_CODE_USED");
  });

  it("should throw invalid_argument and not call fetch for empty arguments", async () => {
    setupMock(true, 200, {});

    const p1 = redeemPairingCode("", "c", "a", mockFetch);
    await expect(p1).rejects.toHaveProperty("code", "invalid_argument");

    const p2 = redeemPairingCode("http://base", "", "a", mockFetch);
    await expect(p2).rejects.toHaveProperty("code", "invalid_argument");

    const p3 = redeemPairingCode("http://base", "c", "", mockFetch);
    await expect(p3).rejects.toHaveProperty("code", "invalid_argument");

    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("should not have double slashes in URL when httpBase has trailing slash", async () => {
    setupMock(true, 200, { room: "r", adapter_id: "a", redeemed_at_ms: 1 });
    
    await redeemPairingCode("http://base/", "c", "a", mockFetch);
    
    const url = mockFetch.mock.calls[0][0] as string;
    expect(url).toBe("http://base/api/pairing-codes/redeem");
    expect(url.replace(/^https?:\/\//, "")).not.toMatch(/\/\//);
  });
});
