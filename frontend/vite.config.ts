import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  build: {
    rollupOptions: {
      input: {
        main: path.resolve(__dirname, 'index.html'),
        mobile: path.resolve(__dirname, 'mobile.html'),
      },
    },
  },
  server: {
    port: 5174,
    proxy: {
      '/v1': { target: 'http://127.0.0.1:9099', changeOrigin: true },
      '/api': { target: 'http://127.0.0.1:9099', changeOrigin: true },
      '/operations': { target: 'http://127.0.0.1:9099', changeOrigin: true },
      '/drafts': { target: 'http://127.0.0.1:9099', changeOrigin: true },
      '/health': { target: 'http://127.0.0.1:9099', changeOrigin: true },
    }
  }
});
