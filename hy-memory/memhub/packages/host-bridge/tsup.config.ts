import { defineConfig } from "tsup";

export default defineConfig({
  entry: ["src/mcp.ts", "src/installer-cli.ts", "src/recall-cli.ts"],
  format: ["cjs"],
  platform: "node",
  outDir: "dist",
  // Preserve the separately built sync-hook asset directory.
  clean: false,
  noExternal: ["axios"],
});
