import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const proxy = {
  '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
  '/healthz': { target: 'http://127.0.0.1:8000', changeOrigin: true },
  '/openapi.json': { target: 'http://127.0.0.1:8000', changeOrigin: true }
}

export default defineConfig({
  plugins: [react()],
  server: { host: '127.0.0.1', port: 5173, proxy },
  preview: { host: '127.0.0.1', port: 4173, proxy },
  build: { outDir: 'dist', sourcemap: true }
})
