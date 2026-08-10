import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      includeAssets: ['favicon.svg', 'app-icon.svg'],
      manifest: {
        name: 'رشدیار',
        short_name: 'رشدیار',
        description: 'برنامه‌ریز سبک برای رشد فردی، عبادت، تمرکز و پیگیری پیشرفت',
        theme_color: '#7c3aed',
        background_color: '#fffaf6',
        display: 'standalone',
        lang: 'fa',
        dir: 'rtl',
        start_url: '/',
        icons: [
          {
            src: '/app-icon.svg',
            sizes: '512x512',
            type: 'image/svg+xml',
            purpose: 'any maskable',
          },
        ],
      },
      devOptions: {
        enabled: true,
      },
    }),
  ],
})
