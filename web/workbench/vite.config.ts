import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const environment = loadEnv(mode, ".", "");
  const backend =
    environment.EASYDESIGN_WEB_BACKEND || "http://127.0.0.1:18769";
  const outputDirectory =
    environment.EASYDESIGN_UI_OUT_DIR ||
    "../../src/easydesign/ui/static";
  const proxy = {
    "/api": backend,
    "/molstar": backend,
    "/pyodide": backend,
    "/pymol-wasm": backend,
  };
  return {
    plugins: [react()],
    build: {
      outDir: outputDirectory,
      // Published UI assets are content-addressed. Keep prior hashes so a
      // running server or an already-open page never loses its referenced
      // bundle during a new build.
      emptyOutDir: false,
      sourcemap: false,
    },
    server: {
      host: "127.0.0.1",
      port: 4174,
      strictPort: true,
      proxy,
    },
    preview: {
      host: "127.0.0.1",
      port: 4174,
      strictPort: true,
      proxy,
    },
  };
});
