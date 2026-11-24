/// <reference types="vitest" />
import react from '@vitejs/plugin-react';
import { fileURLToPath, URL } from 'node:url';
import { defineConfig } from 'vite';
import { VitePWA } from 'vite-plugin-pwa';

export default defineConfig({
  plugins: [
    react(),
    // Installable app: icon, splash, and the app itself kept on the phone so it opens offline.
    // Data for offline use is kept separately in IndexedDB (src/offline).
    VitePWA({
      registerType: 'autoUpdate',
      injectRegister: false,
      includeAssets: ['favicon.svg', 'icons/apple-touch-icon.png'],
      manifest: {
        name: 'Smart Farm',
        short_name: 'Smart Farm',
        description: 'Livestock health and farm management',
        lang: 'en',
        start_url: '/dashboard',
        scope: '/',
        display: 'standalone',
        orientation: 'portrait',
        background_color: '#1B5E20',
        theme_color: '#1B5E20',
        icons: [
          { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
          { src: '/icons/maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,svg,png,woff2}'],
        globIgnores: ['icons/splash-*.png'],
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api\//, /^\/admin/, /^\/ws\//, /^\/media\//],
        maximumFileSizeToCacheInBytes: 4 * 1024 * 1024,
      },
    }),
  ],
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
