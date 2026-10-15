import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react-swc';
import tailwindcss from '@tailwindcss/vite';
import { markdownFrontmatter } from './build/markdownFrontmatter.ts';

export default defineConfig(({ mode }) => ({
  plugins: [react(), tailwindcss(), markdownFrontmatter()],
  server: {
    port: 5173,
    host: true,
    ...(mode === 'development'
      ? {
          proxy: {
            '/api': {
              target: 'http://localhost:8000',
              changeOrigin: true,
              secure: false,
            },
          },
        }
      : {}),
  },
}));
