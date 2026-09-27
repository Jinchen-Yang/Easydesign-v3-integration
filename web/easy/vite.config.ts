import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  base: '/easy/',
  // Production uses the canonical same-origin Product API.  The historical
  // SSH preview bridges remain in server/ only as testable provenance; they
  // are deliberately not loaded into the product build.
  plugins: [react()],
  test: { include: ['tests/**/*.test.ts'] },
  build: {
    chunkSizeWarningLimit: 2200,
    rollupOptions: {input: {easy: 'index.html', account: 'account/index.html'}},
  },
});
