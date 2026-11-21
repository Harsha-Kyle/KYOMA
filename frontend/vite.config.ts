import path from "path"
import tailwindcss from "@tailwindcss/vite"
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    watch: {
      ignored: [
        '**/dist/**',
        '**/node_modules/**',
        '**/.git/**',
        '**/backend/**',
        '**/Kyoma/**',
        '**/test_logs/**',
        '**/*.db*',
        '**/*.tmp*',
        '**/chat_sessions/**',
      ],
    },
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
        secure: false,
      },
      "/ws": {
        target: "ws://127.0.0.1:8000",
        ws: true,
        changeOrigin: true,
        configure: (proxy) => {
          proxy.on('error', (err, _req, _res) => {
            // Gracefully ignore ECONNRESET / EPIPE on client tab reload or hot-reload
            const code = (err as any)?.code;
            if (code === 'ECONNRESET' || code === 'EPIPE' || code === 'ECONNREFUSED') {
              return;
            }
            console.warn('[Vite WS Proxy Error]', err.message);
          });
        },
      },
    },
  },
})
