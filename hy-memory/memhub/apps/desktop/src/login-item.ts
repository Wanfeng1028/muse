import type { App } from "electron";

export const LOGIN_ITEM = { type: "mainAppService" } as const;
export const LOGIN_SERVICE_NAME = "one-memory-background.plist";

type LoginApp = Pick<
  App,
  "isPackaged" | "getLoginItemSettings" | "setLoginItemSettings"
>;

export function wasOpenedByLegacyLoginItem(
  app: LoginApp,
  platform: NodeJS.Platform,
): boolean {
  if (platform !== "darwin" || !app.isPackaged) return false;
  try {
    return app.getLoginItemSettings(LOGIN_ITEM).wasOpenedAtLogin === true;
  } catch {
    return false;
  }
}

export function disableLegacyLoginItem(
  app: LoginApp,
  platform: NodeJS.Platform,
): void {
  if (platform !== "darwin" || !app.isPackaged) return;
  const before = app.getLoginItemSettings(LOGIN_ITEM);
  if (
    !before.openAtLogin &&
    (before.status === "not-registered" || before.status === "not-found")
  ) {
    return;
  }
  app.setLoginItemSettings({ ...LOGIN_ITEM, openAtLogin: false });
  const after = app.getLoginItemSettings(LOGIN_ITEM);
  if (after.openAtLogin || after.status === "enabled") {
    throw new Error("legacy_login_item_disable_failed");
  }
}
