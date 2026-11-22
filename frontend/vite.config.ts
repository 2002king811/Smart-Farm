/// <reference types="vitest" />
import react from '@vitejs/plugin-react';
import { fileURLToPath, URL } from 'node:url';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: {
    host: true,
    port: Number(process.env.VITE_PORT ?? 5180),
    strictPort: true, // fail loudly instead of silently moving to another port
    // Codespaces forwards the dev server through *.app.github.dev; allow that host.
    allowedHosts: ['.app.github.dev'],
    proxy: {
      '/api': { target: process.env.VITE_PROXY_TARGET ?? 'http://localhost:8010', changeOrigin: true },
      '/media': { target: process.env.VITE_PROXY_TARGET ?? 'http://localhost:8010', changeOrigin: true },
      // Docker runs a separate WebSocket server (VITE_WS_PROXY_TARGET); the simple local mode serves it
      // from the API on 8010.
      '/ws': { target: process.env.VITE_WS_PROXY_TARGET ?? 'http://localhost:8010', ws: true },
    },
  },
  build: {
    sourcemap: true,
    rollupOptions: {
      output: {
        manualChunks: {
          react: ['react', 'react-dom', 'react-router-dom'],
          query: ['@tanstack/react-query'],
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    exclude: ['e2e/**', 'node_modules/**'],
  },
});
