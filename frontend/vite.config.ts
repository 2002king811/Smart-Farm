/// <reference types="vitest" />
import react from '@vitejs/plugin-react';
import { fileURLToPath, URL } from 'node:url';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
  server: {
    host: true,
    port: 5173,
    strictPort: true, // fail loudly instead of silently moving to another port
    proxy: {
      '/api': { target: process.env.VITE_PROXY_TARGET ?? 'http://localhost:8000', changeOrigin: true },
      '/ws': { target: process.env.VITE_WS_PROXY_TARGET ?? 'http://localhost:8001', ws: true },
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
  },
});
