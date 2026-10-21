import { expect, it, vi } from "vitest";

import { installApplicationMenu } from "./application-menu";

it("exports logs from Help without requiring a renderer window", async () => {
  const exportLogs = vi.fn(async () => undefined);
  let template: Array<Record<string, unknown>> = [];
  installApplicationMenu({
    productName: "MemHub",
    buildMenu: (value) => {
      template = value as Array<Record<string, unknown>>;
      return {} as never;
    },
    setMenu: vi.fn(),
    exportLogs,
    reportError: vi.fn(),
  });
  const help = template.find((item) => item.label === "帮助");
  expect(help).toBeDefined();
  const submenu = help?.submenu as Array<Record<string, unknown>> | undefined;
  const exportItem = submenu?.find(
    (item) => item.label === "导出日志（发给开发排查）",
  );
  expect(exportItem).toBeDefined();
  const click = exportItem?.click;
  if (typeof click !== "function") throw new Error("missing export click");
  await (click as () => Promise<void>)();
  expect(exportLogs).toHaveBeenCalledOnce();
});
