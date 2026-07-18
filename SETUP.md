# Rock Mass Variability Analysis — Desktop Build Setup

## Prerequisites

- Node.js 18 or later
- Python 3.10+ (for the bundled Streamlit app)
- Windows 10/11 (for `.exe` / `.msi` output)

---

## Step 1 — Install dependencies

```bash
npm install
```

This pins to exact working versions:
- `electron-builder@24.13.3` — avoids schema-breaking changes in v25+
- `electron-store@8.0.0` — last CommonJS-compatible release (v9+ is ESM-only)

---

## Step 2 — Generate icons (required before first build)

The repo ships only `assets/icon.svg`. You must convert it to `.ico` and `.png`
before electron-builder can package the app.

```bash
npm run generate-icons
```

This produces:
- `assets/icon.ico` — Windows installer & taskbar
- `assets/icon.png` — Linux
- `assets/icon.icns` — macOS (only works on macOS with `iconutil`)

> **Windows note:** `.icns` generation is skipped automatically on Windows — that's expected.

---

## Step 3 — Python app location

`rock_mass_variability_analysis.py` already ships at the project root (next to
`package.json`). Nothing to copy manually — `npm run setup-python` (Step 4)
picks it up automatically and copies it into `app/`.

---

## Step 4 — (Optional) Bundle Python

To ship Python with the app so users don't need to install it:

```bash
npm run setup-python
```

This creates `app/venv/` with all required packages. Skip this if you're
comfortable requiring Python to be pre-installed on the target machine.

---

## Step 5 — Build the installer

```bash
# Windows installer (.exe) + portable (.exe)
npm run dist:win

# Output is in: release/
```

---

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `configuration.win should be one of these: null` | electron-builder version > 24 installed | Delete `node_modules`, run `npm install` with pinned version |
| `ERR_REQUIRE_ESM` on electron-store | electron-store v9+ is ESM-only | Pinned to `8.0.0` in package.json — reinstall |
| `icon.ico not found` | Icons not generated yet | Run `npm run generate-icons` first |
| `Cannot find module 'sharp'` | devDependencies not installed | Run `npm install` |
