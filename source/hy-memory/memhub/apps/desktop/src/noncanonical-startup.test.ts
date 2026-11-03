import { readFile } from "node:fs/promises";
import path from "node:path";
import { expect, it } from "vitest";

it("starts Core and UI without creating a Broker for a noncanonical data dir", async () => {
  const source = await readFile(path.join(__dirname, "main.ts"), "utf8");
  expect(source).toContain("if (!hostIntegrationEnabled)");
  expect(source).toContain('event: "broker.disabled"');
  expect(source).toContain('reason: "noncanonical_data_dir"');
  expect(source.indexOf("if (!hostIntegrationEnabled)")).toBeLessThan(
    source.indexOf("const discoveryPath = path.join("),
  );
});
