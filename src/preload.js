/**
 * Preload script — runs in a privileged context before the renderer.
 * Exposes a minimal, safe API surface to the web page via contextBridge.
 */

"use strict";

const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("rmvaElectron", {
  // App metadata
  getVersion:    () => ipcRenderer.invoke("get-app-version"),
  getPythonInfo: () => ipcRenderer.invoke("get-python-info"),

  // Server control
  restartServer: () => ipcRenderer.invoke("restart-server"),

  // Navigation helpers
  openExternal: (url) => ipcRenderer.invoke("open-external", url),

  // Platform
  platform: process.platform,
});
