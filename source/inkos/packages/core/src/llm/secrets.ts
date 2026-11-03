import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { z } from "zod";
import { commitAtomicFileSet } from "../utils/atomic-file-set.js";

export interface SecretsFile {
  services: Record<string, { apiKey: string }>;
}

const SecretsFileSchema = z.object({
  services: z.record(z.string(), z.object({ apiKey: z.string().min(1) }).strict()).default({}),
}).strict();

const SECRETS_DIR = ".inkos";
const SECRETS_FILE = "secrets.json";

async function readSecretsRaw(projectRoot: string): Promise<SecretsFile> {
  try {
    const raw = await readFile(
      join(projectRoot, SECRETS_DIR, SECRETS_FILE),
      "utf-8",
    );
    return SecretsFileSchema.parse(JSON.parse(raw));
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return { services: {} };
    throw error;
  }
}

export async function loadSecrets(projectRoot: string): Promise<SecretsFile> {
  return readSecretsRaw(projectRoot);
}

export async function saveSecrets(
  projectRoot: string,
  secrets: SecretsFile,
): Promise<void> {
  const parsed = SecretsFileSchema.parse(secrets);
  await commitAtomicFileSet({
    rootDir: projectRoot,
    writes: [{
      relativePath: join(SECRETS_DIR, SECRETS_FILE),
      content: `${JSON.stringify(parsed, null, 2)}\n`,
    }],
  });
}

export async function getServiceApiKey(
  projectRoot: string,
  service: string,
): Promise<string | null> {
  // 1. secrets.json
  const secrets = await loadSecrets(projectRoot);
  const entry = secrets.services[service];
  if (entry?.apiKey) return entry.apiKey;

  // 2. Environment variable: MOONSHOT_API_KEY, DEEPSEEK_API_KEY, etc.
  const envKey = `${service.replace(/[^a-zA-Z0-9]/g, "_").toUpperCase()}_API_KEY`;
  if (process.env[envKey]) return process.env[envKey]!;

  return null;
}
