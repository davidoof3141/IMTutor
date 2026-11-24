import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // Dev only: lets the frontend call the backend same-origin as /api when
  // VITE_API_URL is set to an empty string (see .env.development.local).
  // The default target is the `backend` service of docker-compose.yml; set
  // API_PROXY_TARGET=http://localhost:8000 when running Vite on the host.
  server: {
    proxy: {
      '/api': process.env.API_PROXY_TARGET ?? 'http://backend:8000',
    },
  },
})
