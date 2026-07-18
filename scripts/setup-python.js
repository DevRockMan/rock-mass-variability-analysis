#!/usr/bin/env node
/**
 * scripts/setup-python.js
 * ─────────────────────────────────────────────────────────────────────────
 * Run during `npm run dist` to:
 *   1. Create a Python virtual environment at app/venv/
 *   2. Install all required packages into it
 *   3. Copy the Streamlit app script into app/
 *
 * The bundled venv is then included in the packaged app via
 * extraResources in package.json.
 *
 * Usage:
 *   node scripts/setup-python.js
 *   npm run setup-python
 */

"use strict";

const { execSync, spawnSync } = require("child_process");
const path = require("path");
const fs   = require("fs");

const ROOT    = path.resolve(__dirname, "..");
const APP_DIR = path.join(ROOT, "app");
const VENV    = path.join(APP_DIR, "venv");
const STREAMLIT_APP_SRC = path.join(ROOT, "..", "rock_mass_variability_analysis.py");
const STREAMLIT_APP_DST = path.join(APP_DIR, "rock_mass_variability_analysis.py");

const PACKAGES = [
  "streamlit>=1.34.0",
  "numpy>=1.26.0",
  "pandas>=2.0.0",
  "scipy>=1.12.0",
  "openpyxl>=3.1.0",
  "altair>=5.0.0",
  "watchdog",
  "pyarrow",
];

// ── Helpers ─────────────────────────────────────────────────────────────────
function run(cmd, opts = {}) {
  console.log(`  $ ${cmd}`);
  const result = spawnSync(cmd, { shell: true, stdio: "inherit", ...opts });
  if (result.status !== 0) {
    throw new Error(`Command failed (exit ${result.status}): ${cmd}`);
  }
}

function findSystemPython() {
  const candidates =
    process.platform === "win32"
      ? ["python", "py -3", "python3"]
      : ["python3", "python3.12", "python3.11", "python3.10", "python"];

  for (const cmd of candidates) {
    try {
      const out = execSync(`${cmd} --version`, { stdio: "pipe", timeout: 5000 })
        .toString().trim();
      if (/^Python 3\./.test(out)) {
        console.log(`  Found: ${cmd} → ${out}`);
        return cmd;
      }
    } catch { /* not available */ }
  }
  return null;
}

function getPythonInVenv() {
  return process.platform === "win32"
    ? path.join(VENV, "Scripts", "python.exe")
    : path.join(VENV, "bin", "python3");
}

// ── Main ─────────────────────────────────────────────────────────────────────
(async function main() {
  console.log("\n🐍  RMVA Python Setup Script");
  console.log("─".repeat(50));

  // 1. Ensure app/ dir
  fs.mkdirSync(APP_DIR, { recursive: true });
  console.log(`\n✅ App directory: ${APP_DIR}`);

  // 2. Copy the Streamlit app script
  if (fs.existsSync(STREAMLIT_APP_SRC)) {
    fs.copyFileSync(STREAMLIT_APP_SRC, STREAMLIT_APP_DST);
    console.log(`✅ Copied app script → ${STREAMLIT_APP_DST}`);
  } else {
    // Look one level up if running from project root
    const alt = path.join(ROOT, "rock_mass_variability_analysis.py");
    if (fs.existsSync(alt)) {
      fs.copyFileSync(alt, STREAMLIT_APP_DST);
      console.log(`✅ Copied app script from alt path → ${STREAMLIT_APP_DST}`);
    } else {
      throw new Error(
        `Could not find rock_mass_variability_analysis.py.\n` +
        `Expected at: ${STREAMLIT_APP_SRC}\n` +
        `Please place the file next to the rmva-electron/ directory.`
      );
    }
  }

  // 3. Find Python
  console.log("\n🔍  Locating Python 3…");
  const python = findSystemPython();
  if (!python) {
    throw new Error(
      "Python 3 not found. Install Python 3.10+ from https://www.python.org"
    );
  }

  // 4. Create venv
  if (fs.existsSync(VENV)) {
    console.log(`\n♻️  Removing existing venv: ${VENV}`);
    fs.rmSync(VENV, { recursive: true, force: true });
  }
  console.log(`\n📦  Creating virtual environment at ${VENV}…`);
  run(`${python} -m venv "${VENV}"`);

  // 5. Upgrade pip inside venv
  const venvPy = getPythonInVenv();
  console.log("\n⬆️   Upgrading pip…");
  run(`"${venvPy}" -m pip install --upgrade pip --quiet`);

  // 6. Install packages
  console.log(`\n📥  Installing packages:\n  ${PACKAGES.join("\n  ")}`);
  run(
    `"${venvPy}" -m pip install --quiet ${PACKAGES.map((p) => `"${p}"`).join(" ")}`
  );

  // 7. Verify
  console.log("\n🔬  Verifying installation…");
  run(`"${venvPy}" -c "import streamlit, numpy, pandas, scipy, openpyxl; print('OK')"`);

  // 8. Write a manifest file
  const manifest = {
    createdAt: new Date().toISOString(),
    pythonSource: python,
    packages: PACKAGES,
    platform: process.platform,
    arch: process.arch,
  };
  fs.writeFileSync(
    path.join(APP_DIR, "venv-manifest.json"),
    JSON.stringify(manifest, null, 2)
  );

  console.log("\n✅  Python environment ready!");
  console.log(`   Venv:      ${VENV}`);
  console.log(`   App file:  ${STREAMLIT_APP_DST}`);
  console.log("\n👉  You can now run: npm run dist\n");
})().catch((err) => {
  console.error(`\n❌  Setup failed: ${err.message}`);
  process.exit(1);
});
