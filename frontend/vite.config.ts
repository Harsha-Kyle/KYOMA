import path from "path"
import fs from "fs"
import http from "http"
import tailwindcss from "@tailwindcss/vite"
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Resolve single shared status file path
const sharedStatusFilePath = process.env.KYOMA_STATUS_FILE
  ? path.resolve(process.env.KYOMA_STATUS_FILE)
  : path.resolve(__dirname, '..', 'startup_status.json');

// Helper to check if backend port 8000 is listening and responds
function probeBackendListening(port = 8000, host = '127.0.0.1', timeoutMs = 250): Promise<boolean> {
  return new Promise((resolve) => {
    const req = http.request(
      {
        hostname: host,
        port,
        path: '/api/startup/status',
        method: 'GET',
        timeout: timeoutMs,
      },
      (res) => {
        resolve(res.statusCode === 200 || res.statusCode === 503);
        res.resume();
      }
    );
    req.on('error', () => resolve(false));
    req.on('timeout', () => {
      req.destroy();
      resolve(false);
    });
    req.end();
  });
}

function startupStatusFallbackPlugin() {
  return {
    name: 'startup-status-fallback',
    configureServer(server: any) {
      server.middlewares.use(async (req: any, res: any, next: any) => {
        const url = req.url || '';
        if (url === '/api/startup/status' || url.startsWith('/api/startup/status?')) {
          // If backend is available, pass through to Vite proxy
          const backendUp = await probeBackendListening(8000, '127.0.0.1', 250);
          if (backendUp) {
            return next();
          }

          // Backend unreachable: read shared status file if valid and not stale
          res.setHeader('Content-Type', 'application/json');
          res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, proxy-revalidate');
          res.setHeader('Pragma', 'no-cache');
          res.setHeader('Expires', '0');

          try {
            if (fs.existsSync(sharedStatusFilePath)) {
              const raw = fs.readFileSync(sharedStatusFilePath, 'utf-8');
              const data = JSON.parse(raw);
              const now = Date.now() / 1000;
              const isStale = (now - (data.updated_at || 0)) > 120;

              let isPidAlive = true;
              if (data.pid) {
                try {
                  process.kill(data.pid, 0);
                } catch (e: any) {
                  if (e.code === 'ESRCH') {
                    isPidAlive = false;
                  }
                }
              }

              if (!isStale && isPidAlive) {
                return res.end(JSON.stringify(data));
              }
            }
          } catch (err) {
            // Ignore parse/read race errors and fall back to safe starting payload
          }

          // Safe starting state
          const safeStartingState = {
            stage: 'imports',
            percent: 5,
            percentage: 5,
            ready: false,
            error: null,
            updated_at: Date.now() / 1000,
            pid: null,
            elapsed_s: 0,
            message: 'Starting Python environment...',
            current_message: 'Starting Python environment...',
            subsystems: {
              imports: {
                key: 'imports',
                name: 'Python Modules',
                status: 'initializing',
                elapsed_s: 0,
                detail: 'Loading modules...',
                error: null
              }
            }
          };
          return res.end(JSON.stringify(safeStartingState));
        }
        return next();
      });
    }
  };
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss(), startupStatusFallbackPlugin()],
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
        configure: (proxy) => {
          proxy.on('error', (err, _req, _res) => {
            // Suppress ECONNREFUSED during backend startup — avoid log spam
            const code = (err as any)?.code;
            if (code === 'ECONNREFUSED' || code === 'ECONNRESET' || code === 'EPIPE') {
              return;
            }
            console.warn('[Vite API Proxy Error]', err.message);
          });
        },
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
