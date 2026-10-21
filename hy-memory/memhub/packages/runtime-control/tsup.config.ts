import { createRequire } from "node:module";
import { defineConfig } from "tsup";

const require = createRequire(import.meta.url);
const { resolveBuildNumber, resolveBuildVersion } =
  require("../../scripts/release-version.cjs") as {
    resolveBuildNumber(environment?: NodeJS.ProcessEnv, root?: string): number;
    resolveBuildVersion(environment?: NodeJS.ProcessEnv, root?: string): string;
  };
const releaseVersion = resolveBuildVersion(process.env);
const releaseBuildNumber = resolveBuildNumber(process.env);

export default defineConfig({
  entry: { runtime: "src/runtime-entry.ts" },
  format: ["cjs"],
  platform: "node",
  outDir: "dist",
  clean: true,
  define: {
    __ONE_MEMORY_VERSION__: JSON.stringify(releaseVersion),
    __ONE_MEMORY_BUILD_NUMBER__: JSON.stringify(String(releaseBuildNumber)),
    __ONE_MEMORY_COMMIT__: JSON.stringify(
      process.env.ONE_MEMORY_COMMIT ?? "unknown",
    ),
  },
  noExternal: [
    "@one-memory/contracts",
    "@one-memory/host-bridge",
    "axios",
    "fflate",
    "https-proxy-agent",
    "proxy-from-env",
  ],
});
