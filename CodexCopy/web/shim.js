/**
 * CodexCopy — Electron API shim for browser reproduction.
 *
 * The reversed Codex frontend talks to the desktop shell through
 * `window.electronBridge` (injected by Electron's preload script).
 * Every call site in the bundle is optional-chained, so a minimal
 * stub is enough to let the UI boot in a plain browser.
 */
(function () {
  if (typeof window === 'undefined') return;
  if (window.electronBridge) return;

  window.electronBridge = {
    // 'prod' | 'dev' | 'beta' — the app reads this for flavor-specific UI.
    getBuildFlavor: function () { return 'prod'; },
    // Return null so Sentry init is skipped in the reproduction.
    getSentryInitOptions: function () { return null; },
    // File drag/drop helper — not available in browser, leave undefined
    // so the app falls back to its web code path.
    getPathForFile: undefined,
    // Renderer -> main messages — no-op in the browser, but must return
    // a Promise because the bundle calls `.catch()` on the result.
    sendMessageFromView: function () { return Promise.resolve(); },
    // Sentry test hook — not available.
    triggerSentryTestError: undefined,
    // The bundle checks `isPackaged === false` to enable dev affordances.
    isPackaged: true,
  };

  // Mark the environment so the reproduction is identifiable.
  window.__CODEXCOPY__ = { reproduction: true, source: 'Codex (Beta) 26.415.40636 webview' };
})();
