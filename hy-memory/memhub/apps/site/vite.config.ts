import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

/** The marketing site is a static artifact: it never talks to the Core.
 *
 * There is no proxy and no API base here on purpose. The site describes the
 * product; the moment it can read a live memory library it stops being safe
 * to host anywhere, so the absence of a backend is a property to keep rather
 * than a thing not built yet.
 */
export default defineConfig({
  plugins: [react()],
  server: { port: 4321, strictPort: true },
  build: { outDir: "dist", assetsDir: "assets" },
});
