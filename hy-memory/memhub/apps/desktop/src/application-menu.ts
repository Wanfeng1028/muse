import type { Menu, MenuItemConstructorOptions } from "electron";

export function installApplicationMenu(options: {
  productName: string;
  buildMenu(template: MenuItemConstructorOptions[]): Menu;
  setMenu(menu: Menu): void;
  exportLogs(): Promise<void>;
  reportError(message: string): void;
}): void {
  const runExport = async () => {
    try {
      await options.exportLogs();
    } catch {
      options.reportError("日志未能导出，请稍后重试。");
    }
  };
  options.setMenu(
    options.buildMenu([
      {
        label: options.productName,
        submenu: [{ role: "about" }, { type: "separator" }, { role: "quit" }],
      },
      { role: "editMenu" },
      { role: "windowMenu" },
      {
        label: "帮助",
        submenu: [
          {
            label: "导出日志（发给开发排查）",
            click: runExport,
          },
        ],
      },
    ]),
  );
}
