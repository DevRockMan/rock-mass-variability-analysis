#!/usr/bin/env node
/**
 * scripts/generate-icons.js
 * ─────────────────────────────────────────────────────────────────────────
 * Converts assets/icon.svg → all required platform icon formats:
 *   icon.png  (512×512)  — Linux
 *   icon.ico             — Windows  (16, 32, 48, 64, 128, 256 px)
 *   icon.icns            — macOS    (all required sizes)
 *
 * Requires:
 *   npm install --save-dev sharp png-to-ico
 *   brew install librsvg   (macOS)  # for rsvg-convert
 *   apt install librsvg2-bin        # Linux
 *
 * Run: node scripts/generate-icons.js
 */

"use strict";

const { execSync } = require("child_process");
const path = require("path");
const fs   = require("fs");

const ASSETS = path.join(__dirname, "..", "assets");
const SVG    = path.join(ASSETS, "icon.svg");

// Sizes needed for PNG sources
const PNG_SIZES = [16, 32, 48, 64, 128, 256, 512, 1024];

async function main() {
  console.log("🎨  Generating icons from SVG…\n");

  let sharp;
  try {
    sharp = require("sharp");
  } catch {
    console.warn("  ⚠️  sharp not installed — run: npm install --save-dev sharp png-to-ico");
    process.exit(1);
  }

  // 1. Generate all PNG sizes
  console.log("  Generating PNGs…");
  const pngPaths = {};
  const svgBuf = fs.readFileSync(SVG);

  for (const size of PNG_SIZES) {
    const outPath = path.join(ASSETS, `icon_${size}.png`);
    await sharp(svgBuf).resize(size, size).png().toFile(outPath);
    pngPaths[size] = outPath;
    process.stdout.write(`    ${size}×${size} ✓  `);
  }
  console.log();

  // 2. Copy 512px as icon.png
  fs.copyFileSync(pngPaths[512], path.join(ASSETS, "icon.png"));
  console.log("  ✅  icon.png (512×512)");

  // 3. Generate icon.ico (Windows)
  try {
    const pngToIco = require("png-to-ico");
    const icoBuf = await pngToIco([16, 32, 48, 64, 128, 256].map((s) => pngPaths[s]));
    fs.writeFileSync(path.join(ASSETS, "icon.ico"), icoBuf);
    console.log("  ✅  icon.ico");
  } catch (e) {
    console.warn(`  ⚠️  icon.ico skipped: ${e.message}`);
    console.warn("       Run: npm install --save-dev png-to-ico");
  }

  // 4. Generate icon.icns (macOS) — requires iconutil or png2icns
  try {
    const iconsetDir = path.join(ASSETS, "icon.iconset");
    fs.mkdirSync(iconsetDir, { recursive: true });

    const icnsSizes = [16, 32, 64, 128, 256, 512, 1024];
    for (const s of icnsSizes) {
      const half = s / 2;
      if (pngPaths[s])  fs.copyFileSync(pngPaths[s],    path.join(iconsetDir, `icon_${s}x${s}.png`));
      if (pngPaths[s])  fs.copyFileSync(pngPaths[s],    path.join(iconsetDir, `icon_${half}x${half}@2x.png`));
    }

    // macOS: iconutil
    execSync(`iconutil -c icns "${iconsetDir}" -o "${path.join(ASSETS, "icon.icns")}"`, {
      stdio: "inherit",
    });
    fs.rmSync(iconsetDir, { recursive: true });
    console.log("  ✅  icon.icns (macOS iconutil)");
  } catch {
    // Fallback: png2icns or sips
    try {
      execSync(
        `png2icns "${path.join(ASSETS, "icon.icns")}" ${[16, 32, 128, 256, 512]
          .map((s) => `"${pngPaths[s]}"`)
          .join(" ")}`,
        { stdio: "inherit" }
      );
      console.log("  ✅  icon.icns (png2icns fallback)");
    } catch {
      console.warn("  ⚠️  icon.icns skipped — run on macOS with iconutil, or install png2icns");
    }
  }

  // 5. Clean up temporary per-size PNGs
  for (const p of Object.values(pngPaths)) {
    if (!p.endsWith("icon.png")) fs.unlinkSync(p);
  }

  console.log("\n✅  Icon generation complete!\n");
}

main().catch((e) => {
  console.error("❌", e.message);
  process.exit(1);
});
