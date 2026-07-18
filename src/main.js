/**
 * Rock Mass Variability Analysis — Electron Main Process
 * ─────────────────────────────────────────────────
 * Responsibilities:
 *   1. Find a free port
 *   2. Locate the bundled Python environment or system Python
 *   3. Spawn the Streamlit server as a child process
 *   4. Poll until the server is ready, then open the BrowserWindow
 *   5. Clean up the subprocess on quit
 */

"use strict";

const {
  app,
  BrowserWindow,
  Menu,
  shell,
  ipcMain,
  dialog,
  nativeTheme,
} = require("electron");
const path   = require("path");
const fs     = require("fs");
const http   = require("http");
const { spawn, execSync } = require("child_process");
const log    = require("electron-log");
const Store  = require("electron-store");
const kill   = require("tree-kill");

// ── Logging ────────────────────────────────────────────────────────────────
log.transports.file.level = "debug";
log.transports.console.level = "debug";

// ── Persistent settings ───────────────────────────────────────────────────
const store = new Store({
  defaults: {
    windowBounds: { width: 1400, height: 900 },
    windowMaximized: false,
  },
});

// ── State ──────────────────────────────────────────────────────────────────
let mainWindow   = null;
let streamlitProc = null;
let streamlitPort = 8501;
let serverReady  = false;
const isDev = process.argv.includes("--dev") || !app.isPackaged;

// ── Resource paths ─────────────────────────────────────────────────────────
function getResourcesDir() {
  return app.isPackaged
    ? path.join(process.resourcesPath, "app")
    : path.join(__dirname, "..", "app");
}

function getAppScript() {
  return path.join(getResourcesDir(), "rock_mass_variability_analysis.py");
}

// ── Python resolver ────────────────────────────────────────────────────────
function findPython() {
  // 1. Bundled venv (populated by scripts/setup-python.js during build)
  const bundledVenvPaths = [
    path.join(getResourcesDir(), "venv", "bin",     "python3"),   // macOS / Linux
    path.join(getResourcesDir(), "venv", "Scripts",  "python.exe"), // Windows
    path.join(getResourcesDir(), "venv", "Scripts",  "python3.exe"),
  ];
  for (const p of bundledVenvPaths) {
    if (fs.existsSync(p)) {
      log.info(`Using bundled Python: ${p}`);
      return p;
    }
  }

  // 2. System Python — try common candidates
  const systemCandidates =
    process.platform === "win32"
      ? ["python", "python3", "py"]
      : ["python3", "python", "python3.12", "python3.11", "python3.10"];

  for (const cmd of systemCandidates) {
    try {
      const result = execSync(`${cmd} --version`, { timeout: 3000, stdio: "pipe" });
      const ver = result.toString().trim();
      if (ver.startsWith("Python 3")) {
        log.info(`Using system Python: ${cmd} (${ver})`);
        return cmd;
      }
    } catch {
      /* not found */
    }
  }

  log.error("No Python 3 found");
  return null;
}

// ── Free port finder ───────────────────────────────────────────────────────
async function findFreePort(start = 8501, end = 8599) {
  for (let port = start; port <= end; port++) {
    const free = await new Promise((resolve) => {
      const srv = require("net").createServer();
      srv.once("error", () => resolve(false));
      srv.once("listening", () => { srv.close(); resolve(true); });
      srv.listen(port, "127.0.0.1");
    });
    if (free) return port;
  }
  throw new Error("No free port found in range 8501–8599");
}

// ── Streamlit health check ─────────────────────────────────────────────────
function checkServerReady(port, retries = 60, interval = 1000) {
  return new Promise((resolve, reject) => {
    let attempts = 0;
    const check = () => {
      http
        .get(`http://127.0.0.1:${port}/healthz`, (res) => {
          if (res.statusCode < 400) {
            resolve();
          } else {
            retry();
          }
        })
        .on("error", retry);
    };
    const retry = () => {
      if (++attempts >= retries) {
        reject(new Error(`Streamlit server did not start after ${retries}s`));
      } else {
        setTimeout(check, interval);
      }
    };
    check();
  });
}

// ── Spawn Streamlit ────────────────────────────────────────────────────────
async function startStreamlit(python, port) {
  const script = getAppScript();
  if (!fs.existsSync(script)) {
    throw new Error(`App script not found: ${script}`);
  }

  // Verify deps are available
  try {
    execSync(`"${python}" -c "import streamlit, numpy, pandas, scipy, openpyxl"`, {
      timeout: 10000,
      stdio: "pipe",
    });
  } catch (err) {
    const errText = err.stderr ? err.stderr.toString() : err.message;
    log.warn("Missing dependencies, attempting pip install…");
    log.warn(errText);
    try {
      execSync(
        `"${python}" -m pip install --quiet streamlit numpy pandas scipy openpyxl`,
        { timeout: 120000, stdio: "inherit" }
      );
    } catch (pipErr) {
      throw new Error(
        "Required Python packages are missing and could not be installed.\n\n" +
        "Please run manually:\n  pip install streamlit numpy pandas scipy openpyxl"
      );
    }
  }

  const env = {
    ...process.env,
    STREAMLIT_SERVER_PORT:         String(port),
    STREAMLIT_SERVER_ADDRESS:      "127.0.0.1",
    STREAMLIT_SERVER_HEADLESS:     "true",
    STREAMLIT_BROWSER_GATHER_USAGE_STATS: "false",
    STREAMLIT_THEME_BASE:          "dark",
    STREAMLIT_THEME_PRIMARY_COLOR: "#e8a020",
    STREAMLIT_THEME_BACKGROUND_COLOR: "#080c10",
    STREAMLIT_THEME_SECONDARY_BACKGROUND_COLOR: "#0e1318",
    STREAMLIT_THEME_TEXT_COLOR:    "#d8e4f0",
    STREAMLIT_THEME_FONT:          "monospace",
    PYTHONUNBUFFERED: "1",
  };

  log.info(`Spawning: ${python} -m streamlit run ${script} --server.port ${port}`);

  const proc = spawn(
    python,
    [
      "-m", "streamlit", "run", script,
      "--server.port",       String(port),
      "--server.address",    "127.0.0.1",
      "--server.headless",   "true",
      "--server.enableCORS", "false",
      "--server.enableXsrfProtection", "false",
      "--browser.gatherUsageStats", "false",
    ],
    { env, detached: false }
  );

  proc.stdout.on("data", (d) => log.info(`[streamlit] ${d.toString().trim()}`));
  proc.stderr.on("data", (d) => log.warn(`[streamlit] ${d.toString().trim()}`));
  proc.on("exit", (code) => log.info(`[streamlit] exited with code ${code}`));

  return proc;
}

// ── Loading window ─────────────────────────────────────────────────────────
function createLoadingWindow() {
  const win = new BrowserWindow({
    width: 480,
    height: 300,
    frame: false,
    resizable: false,
    alwaysOnTop: true,
    skipTaskbar: true,
    webPreferences: { nodeIntegration: true, contextIsolation: false },
    backgroundColor: "#080c10",
    show: false,
  });
  win.loadFile(path.join(__dirname, "loading.html"));
  win.once("ready-to-show", () => win.show());
  return win;
}

// ── Main window ────────────────────────────────────────────────────────────
function createMainWindow(port) {
  const { width, height } = store.get("windowBounds");
  const maximized = store.get("windowMaximized");

  const win = new BrowserWindow({
    width,
    height,
    minWidth: 1024,
    minHeight: 700,
    title: "Rock Mass Variability Analysis",
    backgroundColor: "#080c10",
    show: false,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, "preload.js"),
    },
    titleBarStyle: process.platform === "darwin" ? "hiddenInset" : "default",
    icon: path.join(__dirname, "..", "assets",
      process.platform === "win32"  ? "icon.ico" :
      process.platform === "darwin" ? "icon.icns" : "icon.png"
    ),
  });

  if (maximized) win.maximize();

  // Save window state on resize / move
  ["resize", "move"].forEach((ev) => {
    win.on(ev, () => {
      if (!win.isMaximized() && !win.isMinimized()) {
        store.set("windowBounds", win.getBounds());
      }
    });
  });
  win.on("maximize",   () => store.set("windowMaximized", true));
  win.on("unmaximize", () => store.set("windowMaximized", false));

  win.loadURL(`http://127.0.0.1:${port}`);

  // Intercept external links — open in OS browser, not in-app
  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });
  win.webContents.on("will-navigate", (event, url) => {
    if (!url.startsWith(`http://127.0.0.1:${port}`)) {
      event.preventDefault();
      shell.openExternal(url);
    }
  });

  win.once("ready-to-show", () => {
    win.show();
    if (isDev) win.webContents.openDevTools({ mode: "detach" });
  });

  return win;
}

// ── Application menu ───────────────────────────────────────────────────────
function buildMenu(win, port) {
  const template = [
    ...(process.platform === "darwin" ? [{
      label: app.name,
      submenu: [
        { role: "about" },
        { type: "separator" },
        { role: "services" },
        { type: "separator" },
        { role: "hide" }, { role: "hideOthers" }, { role: "unhide" },
        { type: "separator" },
        { role: "quit" },
      ],
    }] : []),
    {
      label: "File",
      submenu: [
        {
          label: "Open Project…",
          accelerator: "CmdOrCtrl+O",
          click: () => win.webContents.executeJavaScript(
            `window.dispatchEvent(new CustomEvent('rmva:open-project'))`
          ),
        },
        {
          label: "Save Project…",
          accelerator: "CmdOrCtrl+S",
          click: () => win.webContents.executeJavaScript(
            `window.dispatchEvent(new CustomEvent('rmva:save-project'))`
          ),
        },
        { type: "separator" },
        process.platform === "darwin" ? { role: "close" } : { role: "quit" },
      ],
    },
    {
      label: "Edit",
      submenu: [
        { role: "undo" }, { role: "redo" },
        { type: "separator" },
        { role: "cut" }, { role: "copy" }, { role: "paste" },
        { role: "selectAll" },
      ],
    },
    {
      label: "View",
      submenu: [
        {
          label: "Reload App",
          accelerator: "CmdOrCtrl+R",
          click: () => win.loadURL(`http://127.0.0.1:${port}`),
        },
        {
          label: "Hard Reload (Restart Server)",
          accelerator: "CmdOrCtrl+Shift+R",
          click: async () => {
            await restartStreamlit();
            setTimeout(() => win.loadURL(`http://127.0.0.1:${port}`), 2500);
          },
        },
        { type: "separator" },
        { role: "resetZoom" }, { role: "zoomIn" }, { role: "zoomOut" },
        { type: "separator" },
        { role: "togglefullscreen" },
        ...(isDev ? [{ type: "separator" }, { role: "toggleDevTools" }] : []),
      ],
    },
    {
      label: "Window",
      submenu: [
        { role: "minimize" }, { role: "zoom" },
        { type: "separator" },
        { role: "front" },
      ],
    },
    {
      label: "Help",
      submenu: [
        {
          label: "View Logs",
          click: () => shell.openPath(log.transports.file.getFile().path),
        },
        {
          label: "Open App Data Folder",
          click: () => shell.openPath(app.getPath("userData")),
        },
        { type: "separator" },
        {
          label: "About Rock Mass Variability Analysis",
          click: () =>
            dialog.showMessageBox(win, {
              type: "info",
              title: "About",
              message: "Rock Mass Variability Analysis",
              detail:
                "Version 1.0.0\n\n" +
                "Monte Carlo Simulation · RMR · Q-System · Hoek-Brown\n" +
                "Support Pressure · Tunnel CCM · Reliability · ANN\n\n" +
                "References:\n" +
                "• Barton et al. (1974) — Q-System\n" +
                "• Bieniawski (1989) — RMR\n" +
                "• Hoek & Brown (1997) — GSI / HB criterion\n" +
                "• Hoek-Diederichs (2006) — Em formula\n" +
                "• Serafim-Pereira (1983) — Em formula",
            }),
        },
      ],
    },
  ];

  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

// ── Streamlit restart helper ───────────────────────────────────────────────
async function restartStreamlit() {
  if (streamlitProc && !streamlitProc.killed) {
    await new Promise((resolve) => {
      kill(streamlitProc.pid, "SIGTERM", resolve);
    });
    streamlitProc = null;
  }
  const python = findPython();
  streamlitProc = await startStreamlit(python, streamlitPort);
  await checkServerReady(streamlitPort);
}

// ── IPC handlers ───────────────────────────────────────────────────────────
ipcMain.handle("get-app-version", () => app.getVersion());
ipcMain.handle("get-python-info", () => {
  const python = findPython();
  if (!python) return { found: false };
  try {
    const ver = execSync(`"${python}" --version`, { stdio: "pipe" }).toString().trim();
    return { found: true, version: ver, path: python };
  } catch {
    return { found: false };
  }
});
ipcMain.handle("restart-server", restartStreamlit);
ipcMain.handle("open-external", (_, url) => shell.openExternal(url));

// ── App bootstrap ──────────────────────────────────────────────────────────
app.whenReady().then(async () => {
  nativeTheme.themeSource = "dark";

  const loadingWin = createLoadingWindow();

  try {
    // 1. Find free port
    streamlitPort = await findFreePort(8501, 8599);
    log.info(`Selected port: ${streamlitPort}`);

    // 2. Find Python
    const python = findPython();
    if (!python) {
      dialog.showErrorBox(
        "Python Not Found",
        "Python 3 could not be found on your system.\n\n" +
        "Please install Python 3.10 or later from https://www.python.org\n" +
        "and ensure it is on your PATH, then restart the application."
      );
      app.quit();
      return;
    }

    // 3. Spawn Streamlit
    streamlitProc = await startStreamlit(python, streamlitPort);

    // 4. Wait for server to be ready (up to 60s)
    await checkServerReady(streamlitPort, 60, 1000);
    serverReady = true;
    log.info("Streamlit server ready");

    // 5. Open main window
    mainWindow = createMainWindow(streamlitPort);
    buildMenu(mainWindow, streamlitPort);

    mainWindow.once("ready-to-show", () => {
      loadingWin.close();
    });
  } catch (err) {
    log.error("Startup error:", err);
    loadingWin.close();
    dialog.showErrorBox("Startup Error", err.message);
    app.quit();
  }
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0 && serverReady) {
    mainWindow = createMainWindow(streamlitPort);
    buildMenu(mainWindow, streamlitPort);
  }
});

app.on("before-quit", () => {
  log.info("Stopping Streamlit server…");
  if (streamlitProc && !streamlitProc.killed) {
    kill(streamlitProc.pid, "SIGTERM");
  }
});

process.on("uncaughtException", (err) => {
  log.error("Uncaught exception:", err);
});
