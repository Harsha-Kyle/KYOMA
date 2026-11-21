import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import ErrorBoundary from './components/error-boundary'

// Global fallback to capture early module/script errors on the page
window.addEventListener('error', (event) => {
  const root = document.getElementById('root');
  if (root && (!root.childNodes.length || root.innerHTML === '')) {
    root.innerHTML = `
      <div style="background-color: #030712; color: #f87171; font-family: monospace; padding: 32px; height: 100vh; overflow: auto;">
        <h2 style="font-size: 20px; font-weight: bold; margin-bottom: 12px;">[Kyoma Startup / Script Error]</h2>
        <pre style="background-color: #111827; padding: 16px; border-radius: 8px; white-space: pre-wrap;">${event.error?.stack || event.message || String(event)}</pre>
        <button onclick="window.location.reload()" style="margin-top: 16px; padding: 8px 16px; background-color: #1f2937; color: #e5e7eb; border: 1px solid #374151; border-radius: 4px; cursor: pointer;">Reload UI</button>
      </div>
    `;
  }
});

createRoot(document.getElementById('root')!).render(
  <ErrorBoundary>
      <App />
    </ErrorBoundary>,
)
