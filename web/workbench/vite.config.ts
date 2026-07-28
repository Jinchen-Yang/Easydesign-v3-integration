import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const environment = loadEnv(mode, ".", "");
  const backend =
    environment.EASYDESIGN_WEB_BACKEND || "http://127.0.0.1:8765";
  const outputDirectory =
    environment.EASYDESIGN_UI_OUT_DIR ||
    "../../src/easydesign/ui/static";
  return {
    plugins: [react()],
    build: {
      outDir: outputDirectory,
      emptyOutDir: true,
      sourcemap: false,
    },
    server: {
      host: "127.0.0.1",
      port: 4174,
      strictPort: true,
      proxy: {
        "/api": backend,
        "/molstar": backend,
      },
    },
  };
});
