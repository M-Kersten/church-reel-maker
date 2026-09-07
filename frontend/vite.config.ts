import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The API runs on port 8000 (uvicorn backend.main:app); the dev server proxies to it.
const backend = 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/projects': backend,
      '/church': backend,
      '/templates': backend,
    },
  },
})
