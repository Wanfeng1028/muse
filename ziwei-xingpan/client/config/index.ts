import path from 'node:path';
import type { UserConfigExport } from '@tarojs/cli';

export default {
  alias: { '@': path.resolve(__dirname, '..', 'src') },
  compiler: 'webpack5',
  copy: { patterns: [], options: {} },
  designWidth: 750,
  deviceRatio: { 640: 2.34 / 2, 750: 1, 828: 1.81 / 2 },
  framework: 'react',
  mini: {
    postcss: {
      pxtransform: { config: {}, enable: true },
      url: { config: { limit: 1024 }, enable: true },
    },
  },
  plugins: [],
  projectName: 'ziwei-xingpan',
  outputRoot: 'dist',
  sass: { data: `@import "@/styles/variables.scss";` },
  sourceRoot: 'src',
} satisfies UserConfigExport;
