import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const backend =
    loadEnv(mode, ".", "").EASYDESIGN_WEB_BACKEND || "http://127.0.0.1:8765";
  return {
    plugins: [react()],
    build: {
      outDir: "../../src/easydesign/ui/static",
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
