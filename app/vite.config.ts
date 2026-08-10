import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { VitePWA } from 'vite-plugin-pwa';

export default defineConfig({
  // بیلد انتشار با مسیر نسبی (GH_PAGES=1) — روی هر زیرمسیری کار می‌کند (GitHub Pages / CDN)
  base: process.env.GH_PAGES ? './' : '/',
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['icons/icon-192.png', 'icons/icon-512.png'],
      manifest: {
        name: 'روزنما — برنامه‌ریز و ردیاب رشد',
        short_name: 'روزنما',
        description:
          'برنامه‌ریز زندگی، ردیاب عادت و حالت تمرکز — کاملاً آفلاین و خصوصی',
        lang: 'fa',
        dir: 'rtl',
        display: 'standalone',
        orientation: 'portrait',
        theme_color: '#0e1120',
        background_color: '#0e1120',
        start_url: './',
        scope: './',
        icons: [
          { src: 'icons/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any maskable' },
          { src: 'icons/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any maskable' },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,png,woff2,svg}'],
      },
    }),
  ],
});
