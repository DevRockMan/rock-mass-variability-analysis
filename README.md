# Rock Mass Variability Analysis — Desktop Packaging

Turn the Streamlit app into a native desktop application on **Windows, macOS, and Linux**
using either **Electron** (JavaScript, works now) or **Tauri** (Rust, smaller binaries).

```
rmva-electron/
├── src/
│   ├── main.js          ← Electron main process (spawns Streamlit, manages lifecycle)
│   ├── preload.js       ← Secure context bridge
│   └── loading.html     ← Splash screen shown while Python starts
├── src-tauri/
│   ├── src/main.rs      ← Tauri/Rust alternative entry point
│   ├── Cargo.toml
│   └── build.rs
├── scripts/
│   ├── setup-python.js  ← Creates bundled venv + copies app script
│   ├── generate-icons.js← SVG → .png/.ico/.icns
│   └── installer.nsh    ← Custom NSIS Windows installer script
├── assets/
│   ├── icon.svg         ← Master icon (source of truth)
│   ├── icon.png         ← Linux (512×512) — generated
│   ├── icon.ico         ← Windows — generated
│   ├── icon.icns        ← macOS — generated
│   └── entitlements.mac.plist
├── app/                 ← Created by setup-python.js (gitignored)
│   ├── rock_mass_variability_analysis.py  ← Copied from parent directory
│   └── venv/                       ← Bundled Python environment
├── .github/workflows/build.yml     ← CI/CD for all 3 platforms
├── package.json         ← Electron build config (electron-builder)
└── tauri.conf.json      ← Tauri v2 config (alternative)
```

---

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| **Node.js** | ≥ 18 | Electron toolchain |
| **Python 3** | ≥ 3.10 | Runs Streamlit (bundled into venv by setup script) |
| **Rust + Cargo** | stable | Tauri only — `rustup.rs` |
| **Xcode CLI tools** | latest | macOS signing/icns |

---

## Quick Start — Electron

### 1. Place the app file

```
project-root/
├── rock_mass_variability_analysis.py   ← your Streamlit app
└── rmva-electron/               ← this folder
```

### 2. Install dependencies

```bash
cd rmva-electron
npm install
```

### 3. Generate icons (optional but recommended)

```bash
npm install --save-dev sharp png-to-ico   # one-time
node scripts/generate-icons.js
```

Placeholder icons (`icon.png`, `icon.ico`, `icon.icns`) are expected in `assets/`.
You can also drop in your own 512×512 files.

### 4. Create bundled Python environment

```bash
npm run setup-python
```

This creates `app/venv/` with streamlit, numpy, pandas, scipy, and openpyxl,
and copies `rock_mass_variability_analysis.py` into `app/`.

### 5. Run in development mode

```bash
npm start
# or with DevTools open:
npm run dev
```

### 6. Build distributable packages

```bash
# Current platform only
npm run dist

# Specific platforms
npm run dist:win    # → dist/*.exe, dist/*.zip
npm run dist:mac    # → dist/*.dmg, dist/*.zip
npm run dist:linux  # → dist/*.AppImage, dist/*.deb, dist/*.rpm
```

Output lands in `dist/`.

---

## Quick Start — Tauri (smaller binaries, optional)

Tauri produces ~5–15 MB installers vs Electron's ~150–200 MB.
It requires the Rust toolchain.

```bash
# Install Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# Install Tauri CLI
cargo install tauri-cli --version "^2.0.0-rc"

# Create bundled Python env (same as Electron)
node scripts/setup-python.js

# Development
cargo tauri dev

# Build
cargo tauri build
```

Outputs in `src-tauri/target/release/bundle/`.

---

## How It Works

```
User launches app
       │
       ▼
  Electron / Tauri
  ┌─────────────────────────────────────────┐
  │  1. Pick free port (8501–8599)          │
  │  2. Locate Python                       │
  │     → bundled venv (app/venv/)          │
  │     → or system Python 3                │
  │  3. Spawn subprocess:                   │
  │     python -m streamlit run app.py      │
  │     --server.headless true              │
  │     --server.port <port>                │
  │  4. Poll GET /healthz until ready       │
  │  5. Open BrowserWindow → localhost:port │
  └─────────────────────────────────────────┘
       │
       ▼
  Streamlit App (full Python engine)
  ─ All computation happens in Python
  ─ All I/O (Excel export, JSON projects) via Python
  ─ Browser window = just a chromium frame
```

No data ever leaves the machine. The Streamlit server only binds to `127.0.0.1`.

---

## Bundled vs System Python Strategy

| Scenario | Behavior |
|---|---|
| `app/venv/` present (post-setup) | Always used — reproducible, isolated |
| No venv, system Python found | Used; pip-installs missing packages on first launch |
| No Python at all | Error dialog with link to python.org |

For distribution, always run `npm run setup-python` before `npm run dist`
so end-users don't need Python installed at all.

---

## Environment Variables Passed to Streamlit

| Variable | Value |
|---|---|
| `STREAMLIT_SERVER_PORT` | Auto-selected free port |
| `STREAMLIT_SERVER_ADDRESS` | `127.0.0.1` (localhost only) |
| `STREAMLIT_SERVER_HEADLESS` | `true` |
| `STREAMLIT_THEME_BASE` | `dark` |
| `STREAMLIT_THEME_PRIMARY_COLOR` | `#e8a020` (amber) |
| `STREAMLIT_THEME_BACKGROUND_COLOR` | `#080c10` |
| `STREAMLIT_THEME_FONT` | `monospace` |
| `STREAMLIT_BROWSER_GATHER_USAGE_STATS` | `false` |

---

## CI/CD

`.github/workflows/build.yml` builds all three platforms in parallel on push to a version tag:

```bash
git tag v1.0.0
git push origin v1.0.0
# → triggers Windows + macOS + Linux builds
# → creates GitHub Release with all installers attached
```

---

## Icon Requirements

Place these in `assets/` before building:

| File | Size | Platform |
|------|------|----------|
| `icon.png`  | 512×512 | Linux |
| `icon.ico`  | multi-size | Windows |
| `icon.icns` | multi-size | macOS |

Run `node scripts/generate-icons.js` to auto-generate all three from `icon.svg`.

---

## Troubleshooting

### App opens a blank window
Streamlit is still starting. Wait 5–10 seconds; it will reload automatically.
If it persists: `View → Hard Reload (Restart Server)`.

### "Python Not Found" on launch
- Install Python 3.10+ from https://www.python.org
- Ensure `python3` is on your PATH
- Or run `npm run setup-python` to create the bundled venv

### "Module not found: streamlit" on first launch without venv
The app will try to `pip install` missing packages automatically.
This requires internet access on first launch.

### Windows: missing DLLs
The NSIS installer bundles all Electron dependencies. If you get DLL errors,
install the [Visual C++ Redistributable](https://aka.ms/vs/17/release/vc_redist.x64.exe).

### macOS: "App is damaged and can't be opened"
Run: `xattr -cr /Applications/Rock\ Mass\ Risk\ Analysis.app`
This clears the quarantine flag for unsigned apps.

### Logs
- Electron: `Help → View Logs` (or `electron-log` file in app data folder)
- Streamlit stdout/stderr are piped into the Electron log

---

## Packaging Size Estimates

| Platform | Electron | Tauri |
|---|---|---|
| Windows installer | ~180 MB | ~8 MB |
| macOS DMG | ~190 MB | ~12 MB |
| Linux AppImage | ~185 MB | ~10 MB |

*Tauri binaries are smaller because they use the OS WebView (Edge/WebKit/WebKitGTK)
instead of bundling Chromium. The Python venv (~120 MB) adds to both.*

---

## License

MIT
