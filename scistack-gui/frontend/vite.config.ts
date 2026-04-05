import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Build target is controlled by the VITE_BUILD_TARGET env var:
//   "standalone" (default) → ../scistack_gui/static/ (served by FastAPI)
//   "webview"              → ../extension/dist/webview/ (loaded by VS Code Webview)
const target = process.env.VITE_BUILD_TARGET ?? 'standalone'

const buildConfigs = {
  standalone: {
    outDir: '../scistack_gui/static',
    emptyOutDir: true,
  },
  webview: {
    outDir: '../extension/dist/webview',
    emptyOutDir: true,
    // Webview must be a single bundle (no code splitting) because VS Code
    // Webviews can only load scripts with a nonce from the extension's directory.
    rollupOptions: {
      output: {
        entryFileNames: 'index.js',
        chunkFileNames: 'index.js',
        assetFileNames: 'index.[ext]',
        // Disable code splitting — everything in one chunk
        manualChunks: undefined,
      },
    },
  },
}

// During development, the Vite dev server runs on port 5173 and the FastAPI
// backend runs on port 8765. The proxy below forwards any request starting
// with /api to the backend, so the frontend code can just call "/api/pipeline"
// without worrying about the different port.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8765',
    },
  },
  build: buildConfigs[target as keyof typeof buildConfigs],
})
