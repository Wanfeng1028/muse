// Shared config loader for the caption/hook generators + bash scripts.
// Reads <skill-root>/config.json, applies defaults, exposes hex->ASS colour.
// CLI:  node lib_config.cjs <key>   -> prints one resolved value (for bash)
//       node lib_config.cjs         -> prints the whole resolved config as JSON
const fs = require('fs'), path = require('path');
const ROOT = path.resolve(__dirname, '..');

function load() {
  let raw = {};
  try { raw = JSON.parse(fs.readFileSync(path.join(ROOT, 'config.json'), 'utf8')); } catch (e) {}
  const safe = Object.assign({ top: 120, bottom: 320, left: 70, right: 130 }, raw.safe_zone || {});
  const font_path = raw.font || 'assets/fonts/DejaVuSans-Bold.ttf';
  const cfg = {
    caption_style:   raw.caption_style   || 'word-pop',
    accent_color:    raw.accent_color    || '#FFFF00',
    hook_accent_color: raw.hook_accent_color || raw.accent_color || '#FFFF00',
    font_path,
    font_abs:        path.resolve(ROOT, font_path),
    font_family:     raw.font_family     || 'DejaVu Sans',
    caption_max_chars: raw.caption_max_chars || 16,
    caption_pos_y:   raw.caption_pos_y   || 1360,
    hook_seconds:    raw.hook_seconds    || 4,
    hook_pos_y:      raw.hook_pos_y      || 175,
    max_download_height: raw.max_download_height || 1080,
    safe,
  };
  // clamp caption/hook vertical positions inside the safe zone
  cfg.caption_pos_y = Math.min(Math.max(cfg.caption_pos_y, safe.top + 100), 1920 - safe.bottom);
  cfg.hook_pos_y    = Math.min(Math.max(cfg.hook_pos_y, safe.top), 1920 - safe.bottom - 200);
  return cfg;
}

// "#RRGGBB" -> ASS "&H00BBGGRR"
function assColor(hex) {
  const h = String(hex).replace('#', '').padStart(6, '0');
  const r = h.slice(0, 2), g = h.slice(2, 4), b = h.slice(4, 6);
  return ('&H00' + b + g + r).toUpperCase();
}

module.exports = { ROOT, load, assColor };

if (require.main === module) {
  const key = process.argv[2];
  const cfg = load();
  if (!key) { console.log(JSON.stringify(cfg)); }
  else { const v = cfg[key]; console.log(typeof v === 'object' ? JSON.stringify(v) : v); }
}
