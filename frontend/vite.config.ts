import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The API runs on port 8000 (uvicorn backend.main:app); the dev server proxies to it.
const backend = 'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    // Everything the API answers on. A route missing here fails in dev only, as index.html
    // coming back where JSON was expected, so the list is kept complete on purpose.
    proxy: Object.fromEntries(
      ['/brands', '/church', '/fonts', '/health', '/logos', '/music', '/outro', '/projects',
       '/services', '/storage', '/templates'].map((path) => [path, backend]),
    ),
  },
})
