export function isAllowedNavigation(
  targetUrl: string,
  options: {
    packaged: boolean;
    developmentUrl: string;
  },
): boolean {
  try {
    const target = new URL(targetUrl);
    if (options.packaged) {
      return target.protocol === "one-memory:" && target.host === "app";
    }
    return target.origin === new URL(options.developmentUrl).origin;
  } catch {
    return false;
  }
}
