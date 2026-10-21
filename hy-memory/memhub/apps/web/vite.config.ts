import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    hookTimeout: 15_000,
    testTimeout: 15_000,
    setupFiles: ["./src/query-client.test-setup.ts"],
  },
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
  },
});
