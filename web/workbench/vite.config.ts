import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import { loadEnv } from 'vite';
import { computePlugin } from './server/compute';
export default defineConfig(({ mode }) => ({
  plugins: [
    react(),
    computePlugin(
      mode === 'test'
        ? ''
        : (process.env.WORKBENCH_COMPUTE_SSH_HOST ??
            loadEnv(mode, process.cwd(), 'WORKBENCH_').WORKBENCH_COMPUTE_SSH_HOST ??
            ''),
    ),
  ],
  test: { include: ['tests/**/*.test.ts'] },
  build: { chunkSizeWarningLimit: 2200 },
}));
