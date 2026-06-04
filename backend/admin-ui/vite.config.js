import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import path from 'path';

export default defineConfig({
  plugins: [vue()],
  base: '/admin-static/',
  build: {
    outDir: path.resolve(__dirname, '../static/admin'),
    emptyOutDir: true,
  },
  server: {
    port: 5174,
    proxy: {
      '/v1': { target: 'http://127.0.0.1:9099', changeOrigin: true },
      '/v1/admin': { target: 'http://127.0.0.1:9099', changeOrigin: true },
    },
  },
});
