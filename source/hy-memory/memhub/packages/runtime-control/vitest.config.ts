import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    // Ledger and filesystem concurrency cases exceed Vitest's 5s default
    // under the parallel release gate, while their own bounded waits remain.
    testTimeout: 30_000,
  },
});
