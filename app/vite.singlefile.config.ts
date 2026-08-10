import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { viteSingleFile } from 'vite-plugin-singlefile';

/**
 * بیلد «نسخه‌ی قابل‌حمل دسکتاپ»: یک فایل HTML که JS و CSS داخلش است و
 * بدون هیچ سروری، مستقیم با دابل‌کلیک در مرورگر باز می‌شود (file://).
 * فونت‌ها و آیکون‌ها کنارش در پوشه‌های fonts/ و icons/ قرار می‌گیرند.
 */
export default defineConfig({
  base: './',
  plugins: [react(), viteSingleFile({ removeViteModuleLoader: true })],
  build: {
    outDir: 'dist-desktop',
    emptyOutDir: true,
  },
});
