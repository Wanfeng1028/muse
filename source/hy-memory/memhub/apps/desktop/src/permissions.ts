import type { Session } from "electron";

export function installDenyAllPermissionPolicy(target: Session): void {
  target.setPermissionCheckHandler(() => false);
  target.setPermissionRequestHandler((_webContents, _permission, callback) => {
    callback(false);
  });
  target.setDisplayMediaRequestHandler((_request, callback) => {
    callback({});
  });
}
