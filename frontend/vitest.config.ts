import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import { markdownFrontmatter } from './build/markdownFrontmatter.ts';

export default defineConfig({
  plugins: [react(), markdownFrontmatter()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test-setup.ts'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      exclude: [
        'node_modules/',
        'src/test-setup.ts',
        '**/*.d.ts',
        '**/*.config.*',
        '**/index.ts',
      ],
    },
  },
});
