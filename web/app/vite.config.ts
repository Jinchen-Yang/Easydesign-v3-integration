import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  // The unified app is served under /app/ next to the legacy /easy/ surface
  // during the compatibility window; Hash Router keeps every deep link on one
  // static document, so no backend route changes are required.
  base: '/app/',
  plugins: [react()],
  test: {
    environment: 'jsdom',
    include: ['tests/**/*.test.ts', 'tests/**/*.test.tsx'],
  },
  server: { port: 13200, strictPort: true },
  build: { chunkSizeWarningLimit: 2200 },
});
