const { execFileSync } = require("node:child_process");
const { copyFileSync, mkdirSync, mkdtempSync, rmSync } = require("node:fs");
const os = require("node:os");
const path = require("node:path");

function main() {
  const assets = path.resolve(__dirname, "../apps/desktop/assets");
  const set = path.join(assets, "icon.iconset");
  mkdirSync(set, { recursive: true });
  const source = path.join(assets, "app-icon-source.png");
  const temporary = mkdtempSync(path.join(os.tmpdir(), "one-memory-icon-"));
  const raster = path.join(temporary, "icon.png");
  try {
    copyFileSync(source, raster);
    // The approved source bitmap includes the authored drop shadow in a
    // 1312 x 1376 export canvas. Crop only transparent overflow before resizing.
    // Center-crop the transparent overflow before producing the square app icon.
    execFileSync("sips", ["-c", "1312", "1312", raster]);
    execFileSync("sips", ["-z", "1024", "1024", raster]);
    copyFileSync(raster, path.join(assets, "icon.png"));
    for (const size of [16, 32, 128, 256, 512]) {
      execFileSync("sips", [
        "-z",
        String(size),
        String(size),
        raster,
        "--out",
        path.join(set, `icon_${size}x${size}.png`),
      ]);
      execFileSync("sips", [
        "-z",
        String(size * 2),
        String(size * 2),
        raster,
        "--out",
        path.join(set, `icon_${size}x${size}@2x.png`),
      ]);
    }
  } finally {
    rmSync(temporary, { recursive: true, force: true });
  }
  execFileSync("iconutil", [
    "-c",
    "icns",
    set,
    "-o",
    path.join(assets, "icon.icns"),
  ]);
  console.log("Built desktop icon from the approved source artwork.");
}
try {
  main();
} catch (error) {
  console.error(error);
  process.exitCode = 1;
}
