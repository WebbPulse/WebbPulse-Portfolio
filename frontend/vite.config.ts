import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react-swc';

// https://vite.dev/config/
export default defineConfig(({ mode }) => ({
  plugins: [react()],
  server: {
    port: 5173,
    host: true, // Allow external connections
    // The key is spread in rather than set to undefined: production mode wants
    // no proxy at all and uses direct API calls, and an explicit `undefined`
    // is not the same as an absent key under exactOptionalPropertyTypes.
    ...(mode === 'development'
      ? {
          proxy: {
            // Proxy API requests to the local backend in development only.
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
