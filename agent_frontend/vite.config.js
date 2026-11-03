import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },
  build: {
    outDir: 'dist',
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['vue', 'vue-router'],
          markdown: ['markdown-it', 'dompurify'],
        },
      },
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/chat': { target: 'http://localhost:8001', changeOrigin: true },
      '/api': { target: 'http://localhost:8001', changeOrigin: true },
      '/health': { target: 'http://localhost:8001', changeOrigin: true },
      '/static': { target: 'http://localhost:8001', changeOrigin: true },
    },
  },
})
