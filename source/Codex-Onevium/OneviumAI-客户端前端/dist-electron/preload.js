"use strict";

// electron/preload.ts
var { contextBridge, ipcRenderer, webUtils } = require("electron");
contextBridge.exposeInMainWorld("electronAPI", {
  platform: process.platform,
  openFileWindow: (path) => ipcRenderer.invoke("external-files:open", path),
  publishFileAuth: (status) => ipcRenderer.invoke("external-files:auth", status),
  documentLifecycle: {
    register: (getState, onApproved) => {
      const query = (_event, id) => ipcRenderer.send("document-lifecycle:state", id, getState());
      const beforeUnload = () => {
        ipcRenderer.sendSync("document-lifecycle:before-unload", getState());
      };
      window.addEventListener("beforeunload", beforeUnload);
      ipcRenderer.on("document-lifecycle:query", query);
      ipcRenderer.on("document-lifecycle:approved", onApproved);
      ipcRenderer.send("document-lifecycle:ready", true);
      return () => {
        window.removeEventListener("beforeunload", beforeUnload);
        ipcRenderer.removeListener("document-lifecycle:query", query);
        ipcRenderer.removeListener("document-lifecycle:approved", onApproved);
        ipcRenderer.send("document-lifecycle:ready", false);
      };
    }
  },
  minimapAudio: {
    reportFailure: (name) => ipcRenderer.invoke("minimap-audio:report-failure", name),
    openSettings: () => ipcRenderer.invoke("minimap-audio:open-settings"),
    prepare: () => ipcRenderer.invoke("minimap-audio:prepare"),
    cancel: () => ipcRenderer.invoke("minimap-audio:cancel"),
    onAwake: (callback) => {
      const listener = (_event, awake) => callback(awake);
      ipcRenderer.on("minimap-audio:awake", listener);
      return () => ipcRenderer.removeListener("minimap-audio:awake", listener);
    }
  },
  versions: {
    electron: process.versions.electron,
    node: process.versions.node,
    chrome: process.versions.chrome
  },
  window: {
    toggleMaximize: () => ipcRenderer.invoke("window:toggle-maximize"),
    /** Windows window strip menus (electron/window-menu-commands.ts); Windows only. */
    ...process.platform === "win32" ? { menuCommand: (command) => ipcRenderer.invoke("window:menu-command", command) } : {},
    setAppMode: () => ipcRenderer.invoke("window:set-app-mode"),
    setAlwaysOnTop: (enabled) => ipcRenderer.invoke("window:set-always-on-top", enabled),
    /**
     * True window visibility (minimize/hide/restore/show from the main
     * process). Needed because backgroundThrottling:false pins
     * document.visibilityState to 'visible' — see lib/window-visibility.ts.
     * Returns an unsubscribe function.
     */
    onVisibilityChanged: (callback) => {
      const listener = (_event, visible) => callback(visible);
      ipcRenderer.on("window:visibility-changed", listener);
      return () => {
        ipcRenderer.removeListener("window:visibility-changed", listener);
      };
    },
    /** Current key-window state, for subscribers that attach after the last change. */
    isFocused: () => ipcRenderer.invoke("window:is-focused"),
    /** Key-window (focus/blur) state of the BrowserWindow. Returns an unsubscribe function. */
    onFocusChanged: (callback) => {
      const listener = (_event, focused) => callback(focused);
      ipcRenderer.on("window:focus-changed", listener);
      return () => {
        ipcRenderer.removeListener("window:focus-changed", listener);
      };
    },
    /** Ask for (or drop) the system material behind the shell frame; resolves to whether it is on. */
    setFrameTranslucency: (wanted) => ipcRenderer.invoke("window:set-frame-translucency", wanted),
    /** The material went on or off without a request (e.g. Reduce transparency). Returns an unsubscribe function. */
    onFrameMaterialChanged: (callback) => {
      const listener = (_event, on) => callback(on);
      ipcRenderer.on("window:frame-material-changed", listener);
      return () => {
        ipcRenderer.removeListener("window:frame-material-changed", listener);
      };
    }
  },
  shell: {
    openPath: (folderPath) => ipcRenderer.invoke("shell:open-path", folderPath),
    openExternal: (url) => ipcRenderer.invoke("shell:open-external", url)
  },
  gpu: {
    /** Chromium GPU feature map (gpu_compositing etc.) — drives low-gfx
     *  auto-degrade. Null when unavailable. */
    getFeatureStatus: () => ipcRenderer.invoke("gpu:feature-status")
  },
  gfx: {
    /** Display topology snapshot — drives low-gfx auto-degrade on mixed
     *  refresh-rate setups (display-flicker-defense). Payload:
     *  { displays: Array<{ id, frequency, scaleFactor, internal }>,
     *    mixedRefresh: boolean }. */
    getDisplayTopology: () => ipcRenderer.invoke("gfx:display-topology"),
    /** Subscribe to hotplug topology changes; returns an unsubscribe fn. */
    onDisplayTopologyChange: (callback) => {
      const listener = (_event, topology) => callback(topology);
      ipcRenderer.on("gfx:display-topology-change", listener);
      return () => {
        ipcRenderer.removeListener("gfx:display-topology-change", listener);
      };
    },
    /** Persist the "disable hardware acceleration" escape hatch (marker file
     *  read at next launch — takes effect after restart). */
    setHwAccelDisabled: (disabled) => ipcRenderer.invoke("gfx:set-hw-accel", disabled)
  },
  notification: {
    /**
     * Fire a native desktop notification (F2 — turn-continuity-v2.md).
     * Returns true if shown, false if Electron's Notification.isSupported() is false.
     */
    show: (options) => ipcRenderer.invoke("notification:show", options),
    /**
     * Probe platform notification capability so the Settings UI can render
     * the correct enable-tutorial.
     */
    capability: () => ipcRenderer.invoke("notification:capability"),
    /**
     * Open the OS notification preferences pane. Returns true if a deep-link
     * was opened (macOS / Windows); false on platforms without a stable URL
     * (most Linux DEs).
     */
    openSystemSettings: () => ipcRenderer.invoke("notification:openSystemSettings")
  },
  dialog: {
    openPreviewFile: (defaultPath) => ipcRenderer.invoke("dialog:open-preview-file", defaultPath),
    openFolder: (options) => ipcRenderer.invoke("dialog:open-folder", options)
  },
  files: {
    /**
     * Absolute path of a File the OS handed to the renderer (paste / drop /
     * <input type=file>). Electron ≥32 removed `File.path`; webUtils is the
     * only resolver and must run in the preload — a File can't cross IPC.
     * Empty string for JS-constructed Files (blob fetches, screenshots).
     */
    getPathForFile: (file) => {
      try {
        return webUtils.getPathForFile(file) || "";
      } catch {
        return "";
      }
    }
  },
  speech: {
    getCatalog: () => ipcRenderer.invoke("speech:get-catalog"),
    ensureMicAccess: () => ipcRenderer.invoke("speech:ensure-mic"),
    getModelStates: () => ipcRenderer.invoke("speech:get-model-states"),
    downloadModel: (modelId) => ipcRenderer.invoke("speech:download-model", modelId),
    cancelDownload: (modelId) => ipcRenderer.invoke("speech:cancel-download", modelId),
    deleteModel: (modelId) => ipcRenderer.invoke("speech:delete-model", modelId),
    start: (modelId, sessionId) => ipcRenderer.invoke("speech:start", modelId, sessionId),
    /**
     * Float32Array data gets zeroed out when crossing the contextBridge +
     * IPC boundary; wrapping in a Buffer preserves the raw bytes reliably.
     */
    feed: (samples, sampleRate, sessionId) => ipcRenderer.invoke(
      "speech:feed",
      Buffer.from(samples.buffer, samples.byteOffset, samples.byteLength),
      sampleRate,
      sessionId
    ),
    stop: (sessionId) => ipcRenderer.invoke("speech:stop", sessionId),
    getRecords: () => ipcRenderer.invoke("speech:get-records"),
    deleteRecord: (recordId) => ipcRenderer.invoke("speech:delete-record", recordId),
    exportRecord: (recordId) => ipcRenderer.invoke("speech:export-record", recordId),
    setRecordsEdited: (edits) => ipcRenderer.invoke("speech:set-records-edited", edits),
    onRecordsChanged: (callback) => {
      const listener = () => callback();
      ipcRenderer.on("speech:records-changed", listener);
      return () => ipcRenderer.removeListener("speech:records-changed", listener);
    },
    setRecordRefined: (recordId, refined) => ipcRenderer.invoke("speech:set-record-refined", recordId, refined),
    onEvent: (callback) => {
      const listener = (_event, data) => callback(data);
      ipcRenderer.on("speech:event", listener);
      return () => {
        ipcRenderer.removeListener("speech:event", listener);
      };
    },
    onDownloadProgress: (callback) => {
      const listener = (_event, data) => callback(data);
      ipcRenderer.on("speech:download-progress", listener);
      return () => {
        ipcRenderer.removeListener("speech:download-progress", listener);
      };
    }
  },
  install: {
    checkClaudeUpdate: () => ipcRenderer.invoke("install:check-claude-update"),
    checkPrerequisites: () => ipcRenderer.invoke("install:check-prerequisites"),
    start: (options) => ipcRenderer.invoke("install:start", options),
    upgradeClaude: () => ipcRenderer.invoke("install:upgrade-claude"),
    cancel: () => ipcRenderer.invoke("install:cancel"),
    getLogs: () => ipcRenderer.invoke("install:get-logs"),
    onProgress: (callback) => {
      const listener = (_event, data) => callback(data);
      ipcRenderer.on("install:progress", listener);
      return () => {
        ipcRenderer.removeListener("install:progress", listener);
      };
    },
    onClaudeUpgradeProgress: (callback) => {
      const listener = (_event, data) => callback(data);
      ipcRenderer.on("install:claude-upgrade-progress", listener);
      return () => {
        ipcRenderer.removeListener("install:claude-upgrade-progress", listener);
      };
    }
  },
  scheduler: {
    onSuspensionsProcessed: (callback) => {
      const listener = (_event, data) => callback(data);
      ipcRenderer.on("scheduler:suspensions-processed", listener);
      return () => {
        ipcRenderer.removeListener("scheduler:suspensions-processed", listener);
      };
    }
  },
  updater: {
    checkForUpdates: () => ipcRenderer.invoke("updater:check"),
    downloadUpdate: () => ipcRenderer.invoke("updater:download"),
    quitAndInstall: () => ipcRenderer.invoke("updater:quit-and-install"),
    onStatus: (callback) => {
      const listener = (_event, data) => callback(data);
      ipcRenderer.on("updater:status", listener);
      return () => {
        ipcRenderer.removeListener("updater:status", listener);
      };
    }
  },
  chromeBridge: {
    start: () => ipcRenderer.invoke("chrome-bridge:start"),
    stop: () => ipcRenderer.invoke("chrome-bridge:stop"),
    status: () => ipcRenderer.invoke("chrome-bridge:status"),
    onStatusChange: (callback) => {
      const listener = (_event, data) => callback(data);
      ipcRenderer.on("chrome-bridge:status-changed", listener);
      return () => {
        ipcRenderer.removeListener("chrome-bridge:status-changed", listener);
      };
    }
  },
  browserRuntime: {
    getBackend: () => ipcRenderer.invoke("browser-runtime:get-backend"),
    setBackend: (backend) => ipcRenderer.invoke("browser-runtime:set-backend", backend),
    /**
     * Action lifecycle and heartbeats, scoped to a stable browser tab.
     */
    onActionProgress: (callback) => {
      const listener = (_event, data) => callback(data);
      ipcRenderer.on("browser-runtime:action-progress", listener);
      return () => {
        ipcRenderer.removeListener("browser-runtime:action-progress", listener);
      };
    },
    /**
     * Fires when NativeBrowserProvider opens a browser for a *chat-owned*
     * instance (T3.2). The renderer uses it to auto-open the Inspector's
     * Browser tab and bind the freshly-created view, so the user actually sees
     * the page the agent just opened (main-process open() alone never reaches
     * the renderer's inspector state).
     */
    onInstanceOpened: (callback) => {
      const listener = (_event, data) => callback(data);
      ipcRenderer.on("browser-runtime:instance-opened", listener);
      return () => {
        ipcRenderer.removeListener("browser-runtime:instance-opened", listener);
      };
    }
  },
  widget: {
    captureArea: (rect) => ipcRenderer.invoke("widget:capture-area", rect),
    renderHtml: (html, width) => ipcRenderer.invoke("widget:render-html", html, width)
  },
  webPreview: {
    showToolbarPopup: () => ipcRenderer.invoke("web-preview:toolbar-popup-ready"),
    listHistory: (sessionId, query, offset) => ipcRenderer.invoke("web-preview:history-list", { sessionId, query, offset }),
    listTabs: (sessionId) => ipcRenderer.invoke("web-preview:tabs-list", { sessionId }),
    // `profileId` picks which browser profile (cookie jar) the tab belongs
    // to; omitted, the tab inherits the session's current identity.
    createTab: (sessionId, url, profileId) => ipcRenderer.invoke("web-preview:tabs-create", { sessionId, url, profileId }),
    adoptTabs: (from, to) => ipcRenderer.invoke("web-preview:tabs-adopt", { from, to }),
    selectTab: (sessionId, tabId) => ipcRenderer.invoke("web-preview:tabs-select", { sessionId, tabId }),
    closeTab: (sessionId, tabId) => ipcRenderer.invoke("web-preview:tabs-close", { sessionId, tabId }),
    ensureTab: (sessionId, tabId, url) => ipcRenderer.invoke("web-preview:tabs-ensure", { sessionId, tabId, url }),
    onTabsChanged: (callback) => {
      const listener = (_event, data) => callback(data);
      ipcRenderer.on("web-preview:tabs-changed", listener);
      return () => {
        ipcRenderer.removeListener("web-preview:tabs-changed", listener);
      };
    },
    createView: (sessionId, sourceKind, profileId) => ipcRenderer.invoke("web-preview:create-view", { sessionId, sourceKind, profileId }),
    getViewForSession: (sessionId) => ipcRenderer.invoke("web-preview:get-view-for-session", { sessionId }),
    destroyView: (viewId) => ipcRenderer.invoke("web-preview:destroy-view", { viewId }),
    loadUrl: (viewId, url) => ipcRenderer.invoke("web-preview:load-url", { viewId, url }),
    loadHtml: (viewId, html) => ipcRenderer.invoke("web-preview:load-html", { viewId, html }),
    reloadHtml: (viewId, html) => ipcRenderer.invoke("web-preview:reload-html", { viewId, html }),
    nav: (viewId, action) => ipcRenderer.invoke("web-preview:nav", { viewId, action }),
    onViewportPan: (callback) => {
      const listener = (_event, payload) => callback(payload);
      ipcRenderer.on("web-preview:pan", listener);
      return () => ipcRenderer.removeListener("web-preview:pan", listener);
    },
    setBounds: (viewId, bounds) => ipcRenderer.invoke("web-preview:set-bounds", { viewId, bounds }),
    setVisible: (viewId, visible) => ipcRenderer.invoke("web-preview:set-visible", { viewId, visible }),
    syncAnnotationDock: (viewId, state) => ipcRenderer.invoke("web-preview:picker:sync-dock", { viewId, state }),
    annotationSnapshot: (viewId, seed) => ipcRenderer.invoke("web-preview:annotation-snapshot", { viewId, seed }),
    mutateAnnotations: (viewId, mutation) => ipcRenderer.invoke("web-preview:mutate-annotations", { viewId, mutation }),
    onAnnotationsChanged: (callback) => {
      const listener = (_event, snapshot) => callback(snapshot);
      ipcRenderer.on("web-preview:annotations-changed", listener);
      return () => ipcRenderer.removeListener("web-preview:annotations-changed", listener);
    },
    routeWorkspaceDockAnnotation: (viewId, action) => ipcRenderer.invoke("workspace-dock:annotation-action", { viewId, action }),
    onAnnotationDockAction: (callback) => {
      const listener = (_event, payload) => callback(payload);
      ipcRenderer.on("web-preview:annotation-dock-action", listener);
      return () => ipcRenderer.removeListener("web-preview:annotation-dock-action", listener);
    },
    /** The workbench side: which conversation floats over this page, and where. */
    syncWorkspaceDock: (viewId, request) => ipcRenderer.invoke("workspace-dock:sync", { viewId, request }),
    onWorkspaceDockPlacement: (callback) => {
      const listener = (_event, payload) => callback(payload);
      ipcRenderer.on("workspace-dock:placement", listener);
      return () => ipcRenderer.removeListener("workspace-dock:placement", listener);
    },
    onWorkspaceDockCommand: (callback) => {
      const listener = (_event, payload) => callback(payload);
      ipcRenderer.on("workspace-dock:command", listener);
      return () => ipcRenderer.removeListener("workspace-dock:command", listener);
    },
    /** The floating side: the room it has, then how big it drew itself in it. */
    workspaceDockFrame: () => ipcRenderer.invoke("workspace-dock:frame"),
    measureWorkspaceDock: (size) => ipcRenderer.invoke("workspace-dock:measure", size),
    dragWorkspaceDock: (message) => ipcRenderer.invoke("workspace-dock:drag", message),
    commandWorkspaceDock: (command) => ipcRenderer.invoke("workspace-dock:command", command),
    // The saved-login dropdown is drawn by the main process over the native
    // page (electron/preview/login-fill-overlay.ts). The renderer only supplies
    // its translations and resolved theme colours and hears the outcome — no
    // password is on this channel in either direction.
    syncLoginFillAppearance: (viewId, appearance) => ipcRenderer.invoke("web-preview:login-fill:appearance", { viewId, appearance }),
    dismissLoginFill: (viewId) => ipcRenderer.invoke("web-preview:login-fill:dismiss", { viewId }),
    onLoginFillResult: (callback) => {
      const listener = (_event, payload) => callback(payload);
      ipcRenderer.on("web-preview:login-fill:result", listener);
      return () => ipcRenderer.removeListener("web-preview:login-fill:result", listener);
    },
    onLoginFillManage: (callback) => {
      const listener = (_event, payload) => callback(payload);
      ipcRenderer.on("web-preview:login-fill:manage", listener);
      return () => ipcRenderer.removeListener("web-preview:login-fill:manage", listener);
    },
    setActivityLabel: (viewId, text) => ipcRenderer.invoke("web-preview:set-activity-label", { viewId, text }),
    setActivityHold: (viewId, on) => ipcRenderer.invoke("web-preview:set-activity-hold", { viewId, on }),
    // locale carries i18n strings AND a nested `palette` object whose values
    // are all CSS color strings — see src/lib/browser-preview/picker-palette.ts.
    // The IPC validator (preview-ipc.ts) accepts a flat key→string map plus
    // one level of nested string→string objects; anything else is dropped.
    enablePicker: (viewId, locale) => ipcRenderer.invoke("web-preview:enable-picker", { viewId, locale }),
    disablePicker: (viewId) => ipcRenderer.invoke("web-preview:disable-picker", { viewId }),
    captureElement: (viewId, sessionId, rect) => ipcRenderer.invoke("web-preview:capture-element", { viewId, sessionId, rect }),
    captureOverview: (viewId, sessionId, badges) => ipcRenderer.invoke("web-preview:capture-overview", { viewId, sessionId, badges }),
    syncPins: (viewId, pins, locale) => ipcRenderer.invoke("web-preview:picker:sync-pins", { viewId, pins, locale }),
    editPin: (viewId, pinId, rect, initial) => ipcRenderer.invoke("web-preview:picker:edit-pin", { viewId, pinId, rect, initial }),
    onPickerEvent: (callback) => {
      const listener = (_event, data) => callback(data);
      ipcRenderer.on("web-preview:picker:element-picked", listener);
      ipcRenderer.on("web-preview:picker:region-picked", listener);
      ipcRenderer.on("web-preview:picker:cancelled", listener);
      ipcRenderer.on("web-preview:picker:pin-click", listener);
      ipcRenderer.on("web-preview:picker:pin-delete", listener);
      ipcRenderer.on("web-preview:picker:pin-edit-result", listener);
      return () => {
        ipcRenderer.removeListener("web-preview:picker:element-picked", listener);
        ipcRenderer.removeListener("web-preview:picker:region-picked", listener);
        ipcRenderer.removeListener("web-preview:picker:cancelled", listener);
        ipcRenderer.removeListener("web-preview:picker:pin-click", listener);
        ipcRenderer.removeListener("web-preview:picker:pin-delete", listener);
        ipcRenderer.removeListener("web-preview:picker:pin-edit-result", listener);
      };
    },
    onNavEvent: (callback) => {
      const listener = (_event, data) => callback(data);
      ipcRenderer.on("web-preview:nav:did-navigate", listener);
      ipcRenderer.on("web-preview:nav:did-fail", listener);
      return () => {
        ipcRenderer.removeListener("web-preview:nav:did-navigate", listener);
        ipcRenderer.removeListener("web-preview:nav:did-fail", listener);
      };
    },
    onLoadEvent: (callback) => {
      const make = (type) => (_event, data) => {
        callback({ ...data, type });
      };
      const lLoading = make("loading");
      const lFinished = make("finished");
      const lHotReload = make("hot-reload");
      ipcRenderer.on("web-preview:load:loading", lLoading);
      ipcRenderer.on("web-preview:load:finished", lFinished);
      ipcRenderer.on("web-preview:load:hot-reload-detected", lHotReload);
      return () => {
        ipcRenderer.removeListener("web-preview:load:loading", lLoading);
        ipcRenderer.removeListener("web-preview:load:finished", lFinished);
        ipcRenderer.removeListener("web-preview:load:hot-reload-detected", lHotReload);
      };
    },
    onCrash: (callback) => {
      const listener = (_event, data) => callback(data);
      ipcRenderer.on("web-preview:crash", listener);
      return () => {
        ipcRenderer.removeListener("web-preview:crash", listener);
      };
    },
    onViewDestroyed: (callback) => {
      const listener = (_event, data) => callback(data);
      ipcRenderer.on("web-preview:view-destroyed", listener);
      return () => {
        ipcRenderer.removeListener("web-preview:view-destroyed", listener);
      };
    },
    // ── Toolbar menu capabilities (W7-T3) ──
    getZoomFactor: (viewId) => ipcRenderer.invoke("web-preview:zoom:get", { viewId }),
    setZoomFactor: (viewId, factor) => ipcRenderer.invoke("web-preview:zoom:set", { viewId, factor }),
    resetZoom: (viewId) => ipcRenderer.invoke("web-preview:zoom:reset", { viewId }),
    findInPage: (viewId, text, forward) => ipcRenderer.invoke("web-preview:find", { viewId, text, forward }),
    stopFindInPage: (viewId) => ipcRenderer.invoke("web-preview:find:stop", { viewId }),
    onFindResult: (callback) => {
      const listener = (_event, data) => callback(data);
      ipcRenderer.on("web-preview:find:result", listener);
      return () => {
        ipcRenderer.removeListener("web-preview:find:result", listener);
      };
    },
    print: (viewId) => ipcRenderer.invoke("web-preview:print", { viewId }),
    captureFrame: (viewId, options) => ipcRenderer.invoke("web-preview:capture-frame", { viewId, maxWidth: options?.maxWidth }),
    setViewport: (viewId, override) => ipcRenderer.invoke("web-preview:set-viewport", { viewId, override }),
    screenshotViewport: (viewId, sessionId) => ipcRenderer.invoke("web-preview:screenshot-viewport", { viewId, sessionId }),
    listDownloads: () => ipcRenderer.invoke("web-preview:downloads:list"),
    clearDownloads: () => ipcRenderer.invoke("web-preview:downloads:clear"),
    onDownloadUpdated: (callback) => {
      const listener = (_event, data) => callback(data);
      ipcRenderer.on("web-preview:download:updated", listener);
      return () => {
        ipcRenderer.removeListener("web-preview:download:updated", listener);
      };
    },
    clearBrowsingData: (viewId) => ipcRenderer.invoke("web-preview:clear-browsing-data", { viewId }),
    // One site, not the whole profile — see clearSiteData in the view manager.
    clearSiteData: (viewId, origin) => ipcRenderer.invoke("web-preview:clear-site-data", { viewId, origin })
  },
  browserCookies: {
    detect: () => ipcRenderer.invoke("browser-cookies:detect"),
    import: (args) => ipcRenderer.invoke("browser-cookies:import", args)
  },
  // Saved-password store. Metadata, deletes and reveals all come through here
  // because the ciphertext is only openable in the main process — see
  // electron/browser-runtime/credential-ipc.ts.
  browserCredentials: {
    detect: () => ipcRenderer.invoke("browser-credentials:detect"),
    storageAvailable: () => ipcRenderer.invoke("browser-credentials:storage-available"),
    importPasswords: (args) => ipcRenderer.invoke("browser-credentials:import-passwords", args),
    sources: (args) => ipcRenderer.invoke("browser-credentials:sources", args),
    list: (args) => ipcRenderer.invoke("browser-credentials:list", args),
    canReveal: () => ipcRenderer.invoke("browser-credentials:can-reveal"),
    reveal: (args) => ipcRenderer.invoke("browser-credentials:reveal", args),
    delete: (args) => ipcRenderer.invoke("browser-credentials:delete", args),
    deleteSource: (args) => ipcRenderer.invoke("browser-credentials:delete-source", args),
    // Passwords only — cookies live in the Electron session partition.
    moveSource: (args) => ipcRenderer.invoke("browser-credentials:move-source", args)
  },
  keybindings: {
    /**
     * Replace all OS-global (system-scope) shortcut registrations. Returns
     * per-command results; ok:false = accelerator taken by another app.
     */
    syncSystem: (bindings) => ipcRenderer.invoke("keybindings:sync-system", bindings),
    /** Enable/disable the native double-⌘ capture gesture ('double-cmd' | null). */
    setCaptureGesture: (gesture) => ipcRenderer.invoke("keybindings:set-capture-gesture", gesture),
    /** Whether the OS trusts us to observe global keystrokes (macOS gate). */
    gesturePermission: () => ipcRenderer.invoke("keybindings:gesture-permission"),
    /** Open the macOS accessibility-trust prompt for the gesture. */
    promptGesturePermission: () => ipcRenderer.invoke("keybindings:prompt-gesture-permission")
  },
  screenshot: {
    /** Fires after a global-shortcut window capture lands on disk. */
    onCaptured: (callback) => {
      const listener = (_event, data) => callback(data);
      ipcRenderer.on("screenshot:captured", listener);
      return () => {
        ipcRenderer.removeListener("screenshot:captured", listener);
      };
    },
    /** Fires when a capture was blocked by the macOS Screen Recording TCC gate. */
    onPermissionNeeded: (callback) => {
      const listener = () => callback();
      ipcRenderer.on("screenshot:permission-needed", listener);
      return () => {
        ipcRenderer.removeListener("screenshot:permission-needed", listener);
      };
    },
    /** Pull a captured PNG as a data URL (path must be inside the appshots dir). */
    readAsDataUrl: (filePath) => ipcRenderer.invoke("screenshot:read-data-url", filePath),
    /** Push localized notification copy into the main process. */
    setLabels: (labels) => ipcRenderer.invoke("screenshot:set-labels", labels),
    openPermissionSettings: () => ipcRenderer.invoke("screenshot:open-permission-settings"),
    permissionStatus: () => ipcRenderer.invoke("screenshot:permission-status")
  },
  startup: {
    ready: () => ipcRenderer.invoke("startup:ready"),
    stage: (stage) => ipcRenderer.invoke("startup:stage", stage),
    syncTheme: (colors) => ipcRenderer.invoke("startup:theme", colors)
  },
  theme: {
    save: (theme) => ipcRenderer.invoke("theme:save", theme)
  },
  auth: {
    getDeviceInfo: () => ipcRenderer.invoke("auth:device-info"),
    store: (key, value) => ipcRenderer.invoke("auth:store", key, value),
    read: (key) => ipcRenderer.invoke("auth:read", key),
    remove: (key) => ipcRenderer.invoke("auth:remove", key),
    clear: () => ipcRenderer.invoke("auth:clear")
  },
  diag: {
    /**
     * Fire-and-forget log append. The renderer-side `@/lib/diagnostics` module
     * is the only intended caller — see its docs for build-time enablement.
     */
    append: (payload) => ipcRenderer.send("diag:append", payload)
  },
  terminal: {
    create: (options) => ipcRenderer.invoke("terminal:create", options),
    input: (id, data) => ipcRenderer.invoke("terminal:input", id, data),
    resize: (id, cols, rows) => ipcRenderer.invoke("terminal:resize", id, cols, rows),
    close: (id) => ipcRenderer.invoke("terminal:close", id),
    getBuffer: (id) => ipcRenderer.invoke("terminal:get-buffer", id),
    /** xterm parsed `chars` of output; lets the main process pause a PTY that outruns the renderer. */
    ack: (id, chars) => ipcRenderer.send("terminal:ack", id, chars),
    /** This terminal view is going away; stop waiting for acknowledgements. */
    detach: (id) => ipcRenderer.send("terminal:detach", id),
    list: () => ipcRenderer.invoke("terminal:list"),
    onData: (callback) => {
      const listener = (_event, id, data) => callback(id, data);
      ipcRenderer.on("terminal:data", listener);
      return () => {
        ipcRenderer.removeListener("terminal:data", listener);
      };
    },
    onExit: (callback) => {
      const listener = (_event, id, exitCode, signal) => callback(id, exitCode, signal);
      ipcRenderer.on("terminal:exit", listener);
      return () => {
        ipcRenderer.removeListener("terminal:exit", listener);
      };
    }
  }
});
