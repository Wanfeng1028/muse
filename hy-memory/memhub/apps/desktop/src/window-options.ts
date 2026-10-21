import type { BrowserWindowConstructorOptions } from "electron";

export function createWindowOptions(
  preloadPath?: string,
  workArea?: { x: number; y: number; width: number; height: number },
): BrowserWindowConstructorOptions {
  const width = Math.min(
    1440,
    workArea ? Math.max(320, workArea.width - 40) : 1440,
  );
  const height = Math.min(
    960,
    workArea ? Math.max(320, workArea.height - 40) : 960,
  );
  return {
    width,
    height,
    minWidth: Math.min(1000, width),
    minHeight: Math.min(700, height),
    ...(workArea
      ? {
          x: Math.round(workArea.x + (workArea.width - width) / 2),
          y: Math.round(workArea.y + (workArea.height - height) / 2),
        }
      : {}),
    ...(process.platform === "darwin"
      ? {
          titleBarStyle: "hiddenInset" as const,
          trafficLightPosition: { x: 20, y: 20 },
        }
      : {}),
    backgroundColor: "#e9edf2",
    show: false,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      ...(preloadPath ? { preload: preloadPath } : {}),
    },
  };
}
