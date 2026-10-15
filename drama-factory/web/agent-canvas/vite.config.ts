import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

/**
 * 构建约定：
 * - 库模式，单入口 src/index.ts，输出 IIFE，全局变量名 AgentCanvas。
 * - 所有依赖（react / react-dom / @xyflow/react / zustand）全部打进 bundle，
 *   因为宿主是 Spring Boot 直出的 vanilla 静态页，没有构建链，无法解析外部依赖。
 * - CSS 不走独立产物：cssCodeSplit 关闭，且要求样式以 `?inline` 方式导入，
 *   由 src/element.ts 在运行时把字符串注入 <style>，保证 dist 只有单个 js 文件。
 */
export default defineConfig({
  plugins: [react()],
  define: {
    'process.env.NODE_ENV': '"production"',
    process: '{ "env": {} }',
  },
  build: {
    lib: {
      entry: 'src/index.ts',
      name: 'AgentCanvas',
      formats: ['iife'],
      fileName: () => 'agent-canvas.js',
    },
    cssCodeSplit: false,
    outDir: 'dist',
    emptyOutDir: true,
    sourcemap: false,
    rollupOptions: {
      output: {
        inlineDynamicImports: true,
      },
    },
  },
});
