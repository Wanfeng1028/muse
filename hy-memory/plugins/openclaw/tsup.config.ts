import { defineConfig } from "tsup";

export default defineConfig({
  entry: ["index.ts"],
  format: ["esm"],
  dts: false,  // DTS requires openclaw/plugin-sdk types (available in OpenClaw host environment)
  splitting: false,
  clean: true,
  external: [
    "openclaw/plugin-sdk",
    "openclaw/plugin-sdk/plugin-entry",
  ],
});
