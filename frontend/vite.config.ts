import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// /api is proxied to the engine in dev and in `vite preview` (the production server behind the tunnel),
// so the site and the API share one origin: no CORS, no extra subdomain.
const proxy = {
  '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true, rewrite: (p: string) => p.replace(/^\/api/, '') },
  '/ws': { target: 'ws://127.0.0.1:8000', ws: true },
};

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy },
  preview: { port: 4173, host: '127.0.0.1', proxy, allowedHosts: ['worldofsports.tech', 'www.worldofsports.tech', 'localhost', '127.0.0.1'] },
  build: { chunkSizeWarningLimit: 1500 },
});
