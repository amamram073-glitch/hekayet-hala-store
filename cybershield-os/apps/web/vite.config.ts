import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const allowedHosts = process.env.VITE_ALLOWED_HOSTS?.split(',').map((host) => host.trim()).filter(Boolean);

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    allowedHosts,
    proxy: Object.fromEntries(['/api', '/docs', '/redoc', '/openapi.json'].map((path) => [
      path, { target: 'http://127.0.0.1:8000', changeOrigin: true },
    ])),
  },
});
