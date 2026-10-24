import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The FastAPI backend (api.py) runs on 8432; the dev server proxies /api to it.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8432',
    },
  },
})
