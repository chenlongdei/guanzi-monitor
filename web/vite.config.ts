import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: { outDir: '../backend/guanzi_monitor/web', emptyOutDir: true },
  server: { port: 5178, proxy: { '/api': 'http://127.0.0.1:8765' } },
})
