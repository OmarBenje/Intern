import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_')
  const apiRoot = (env.VITE_API_ROOT || '/api/v1').replace(/\/$/, '')
  return {
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      // Preserve the browser's Host so Django can validate the CSRF Origin.
      [apiRoot]: { target: 'http://127.0.0.1:8000', changeOrigin: false, rewrite: path => path.replace(apiRoot, '/api/v1') },
      '/health': { target: 'http://127.0.0.1:8000', changeOrigin: false },
    },
  },
  }
})
