export class PairingError extends Error {
  readonly code: string;
  constructor(code: string, message: string) {
    super(`${code}: ${message}`);
    this.name = "PairingError";
    this.code = code;
  }
}

export interface PairingRedeemResult {
  room: string;
  adapter_id: string;
  redeemed_at_ms: number;
}

export async function redeemPairingCode(
  httpBase: string,
  code: string,
  adapterId: string,
  fetchImpl: typeof fetch = fetch
): Promise<PairingRedeemResult> {
  if (!httpBase || !code || !adapterId) {
    throw new PairingError("invalid_argument", "Arguments cannot be empty");
  }

  const url = `${httpBase.replace(/\/+$/, "")}/api/pairing-codes/redeem`;
  
  const res = await fetchImpl(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ code, adapter_id: adapterId }),
  });

  if (res.ok) {
    const json = await res.json();
    return {
      room: json.room,
      adapter_id: json.adapter_id,
      redeemed_at_ms: json.redeemed_at_ms,
    };
  }

  let errorCode = `http_${res.status}`;
  let errorMessage = res.statusText;
  try {
    const errJson = await res.json();
    if (errJson.error) errorCode = errJson.error;
    if (errJson.message) errorMessage = errJson.message;
  } catch {
    // ignore json parse error
  }

  throw new PairingError(errorCode, errorMessage);
}
