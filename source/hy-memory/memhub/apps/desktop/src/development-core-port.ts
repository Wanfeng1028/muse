const DEFAULT_DEVELOPMENT_CORE_PORT = 8765;
const DEFAULT_DEVELOPMENT_BROKER_PORT = 18_765;

export function developmentCorePort(
  environment: NodeJS.ProcessEnv = process.env,
): number {
  return developmentPort(
    environment.ONE_MEMORY_CORE_PORT,
    DEFAULT_DEVELOPMENT_CORE_PORT,
  );
}

export function developmentBrokerPort(
  environment: NodeJS.ProcessEnv = process.env,
): number {
  return developmentPort(
    environment.ONE_MEMORY_BROKER_PORT,
    DEFAULT_DEVELOPMENT_BROKER_PORT,
  );
}

function developmentPort(
  rawValue: string | undefined,
  fallback: number,
): number {
  const raw = rawValue?.trim();
  if (raw === undefined || raw === "") return fallback;
  const value = Number(raw);
  if (!Number.isSafeInteger(value) || value < 1024 || value > 65_535) {
    throw new Error("desktop_development_port_invalid");
  }
  return value;
}
