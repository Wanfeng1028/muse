// One-off generator for src/components/icons.tsx (import map over the
// rasterized Lucide PNGs). Re-run after adding icons to ICONS.
const fs = require('node:fs');
const path = require('node:path');
const ICONS = ['home', 'message-circle', 'book-open', 'user', 'users', 'user-plus', 'crown', 'coins', 'history', 'layers', 'share-2', 'clipboard-list', 'settings', 'message-square', 'info', 'layout-grid', 'log-in', 'log-out', 'refresh-cw', 'chevron-right', 'chevron-left', 'copy', 'check', 'trash-2', 'maximize-2', 'x', 'eye', 'eye-off', 'mail', 'lock', 'chrome', 'apple', 'calendar', 'map-pin', 'clock', 'sparkles', 'arrow-up', 'arrow-right', 'moon', 'sun', 'inbox', 'star', 'gift', 'pen-line', 'zap', 'save', 'search', 'plus', 'minus'];
const TONES = ['blue', 'sky', 'gray', 'white'];
const imps = [];
const map = [];
for (const n of ICONS) {
  const v = 'ic_' + n.replace(/-/g, '_');
  for (const t of TONES) imps.push("import " + v + "_" + t + " from '../assets/lucide/png/" + n + "-" + t + ".png';");
  map.push("  '" + n + "': { blue: " + v + "_blue, sky: " + v + "_sky, gray: " + v + "_gray, white: " + v + "_white },");
}
const out = "import { View, Image } from '@tarojs/components';\nimport './icons.scss';\n\n// Lucide icons as rasterized PNGs (see scripts/lucide-rasterize.cjs).\n// WeChat <image> cannot render SVG, so the official Lucide paths\n// (lucide-static v1.66.0, ISC, under src/assets/lucide/svg/) are baked\n// to transparent 144px PNGs in four stroke tones. Tones: blue = light\n// primary #346bf0, sky = dark primary #8db4ff, gray = inactive\n// #9a9ba2, white = on-gradient #ffffff. config/index.ts forces file\n// emission (imageUrlLoaderOption.limit = true) so no icon is inlined\n// as base64, which <image> cannot display.\n" + imps.join("\n") + "\n\nexport const ICON_NAMES = [" + ICONS.map((n) => "'" + n + "'").join(", ") + "] as const;\nexport type IconName = typeof ICON_NAMES[number];\nexport type IconTone = 'blue' | 'sky' | 'gray' | 'white';\nconst SRC: Record<IconName, Record<IconTone, string>> = {\n" + map.join("\n") + "\n};\n\nexport function Icon({ name, tone, size }: { name: IconName; tone: IconTone; size?: string }) {\n  return <Image className='lucide-icon' style={{ width: size || '40px', height: size || '40px' }} src={SRC[name][tone]} mode='aspectFit' />;\n}\n\n// Service-row badge: soft blue rounded square + blue glyph (light) or\n// soft dark-blue square + sky glyph (dark). Replaces the old colored\n// dot placeholders, which carried no glyph at all.\nexport function IconBadge({ name, dark }: { name: IconName; dark?: boolean }) {\n  return (\n    <View className={dark ? 'icon-badge icon-badge-dark' : 'icon-badge'}>\n      <Icon name={name} tone={dark ? 'sky' : 'blue'} size='40px' />\n    </View>\n  );\n}\n";
fs.writeFileSync(path.join(__dirname, '..', 'src', 'components', 'icons.tsx'), out);
console.log('icons.tsx written, imports:', imps.length);
