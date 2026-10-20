export type FontSpec = {family: string; file: string; weight?: string};

export const theme = {
  color: {
    bg: '#0B0D12',
    fg: '#EEF1F5',
    muted: '#7D8594',
    accent: '#FF8A3D',
    warmBg: '#140C08',
  },
  font: {
    display: '"Noto Serif SC", "Source Han Serif SC", "Songti SC", "SimSun", serif',
    body: '"Noto Sans SC", "Source Han Sans SC", "Microsoft YaHei", "PingFang SC", sans-serif',
    mono: '"JetBrains Mono", "Cascadia Mono", Consolas, "Microsoft YaHei", monospace',
  },
  // 字体文件放在 public/fonts/，缺失时会回退到系统字体（见 public/fonts/README.md）
  fonts: [
    {family: 'Noto Serif SC', file: 'fonts/NotoSerifSC-Regular.otf', weight: '400'},
    {family: 'Noto Sans SC', file: 'fonts/NotoSansSC-Regular.otf', weight: '400'},
    {family: 'JetBrains Mono', file: 'fonts/JetBrainsMono-Regular.woff2', weight: '400'},
  ] as FontSpec[],
  size: {display: 200, title: 112, body: 56, caption: 32},
  motion: {enter: 16, exit: 10, overlap: 4, stagger: 3},
  texture: {grain: 0.07, vignette: 0.35},
  safe: {x: 0.06, y: 0.08},
};
