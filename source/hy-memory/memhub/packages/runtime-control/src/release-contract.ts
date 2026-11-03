export const RUNTIME_MANIFEST_SCHEMA = 1 as const;
export const CLI_PROTOCOL = 1 as const;
export const CLI_SUPPORTED_RUNTIME_PROTOCOL = Object.freeze({
  min: 1,
  max: 1,
});
export const RUNTIME_PROTOCOL = 1 as const;
export const RUNTIME_SUPPORTED_CLI_PROTOCOL = Object.freeze({
  min: 1,
  max: 1,
});

export interface ProtocolRange {
  min: number;
  max: number;
}

export function protocolRange(value: unknown): value is ProtocolRange {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    return false;
  }
  const range = value as Partial<ProtocolRange>;
  return (
    Number.isSafeInteger(range.min) &&
    Number.isSafeInteger(range.max) &&
    (range.min ?? 0) >= 1 &&
    (range.max ?? 0) >= (range.min ?? 0)
  );
}

export function protocolIncludes(
  range: ProtocolRange,
  version: number,
): boolean {
  return version >= range.min && version <= range.max;
}
