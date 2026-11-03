"use strict";

// electron/file-preload.ts
var { contextBridge, ipcRenderer } = require("electron");
contextBridge.exposeInMainWorld("electronAPI", {
  platform: process.platform,
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
  externalFiles: {
    browse: (id, directory, query, offset) => ipcRenderer.invoke("external-files:browse", id, directory, query, offset),
    openRelated: (id, path) => ipcRenderer.invoke("external-files:open-related", id, path),
    pick: () => ipcRenderer.invoke("external-files:action", "pick"),
    snapshot: () => ipcRenderer.invoke("external-files:snapshot"),
    subscribe: (callback) => {
      const listener = (_event, snapshot) => callback(snapshot);
      ipcRenderer.on("external-files:changed", listener);
      return () => ipcRenderer.removeListener("external-files:changed", listener);
    },
    select: (id) => ipcRenderer.invoke("external-files:action", "select", id),
    close: (id) => ipcRenderer.invoke("external-files:action", "close", id),
    retry: (id) => ipcRenderer.invoke("external-files:action", "retry", id),
    reveal: (id) => ipcRenderer.invoke("external-files:action", "reveal", id),
    openWorkspace: () => ipcRenderer.invoke("external-files:action", "workspace")
  }
});
