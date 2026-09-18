import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import tailwindcss from '@tailwindcss/vite'
import { spawn } from 'node:child_process'
import { createConnection } from 'node:net'
import { existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// 托管 Python(装有 lancedb/fastembed 的解释器),优先用它启动后端
const VENV_PY =
  '/Users/csw/Library/Application Support/kimi-desktop/daimon-share/daimon/runtime/python/.venv/bin/python3'

function portBusy(port) {
  return new Promise((resolve) => {
    const sock = createConnection({ host: '127.0.0.1', port }, () => {
      sock.end()
      resolve(true)
    })
    sock.on('error', () => resolve(false))
    sock.setTimeout(1500, () => {
      sock.destroy()
      resolve(false)
    })
  })
}

function apiServerPlugin() {
  let proc = null
  return {
    name: 'mtg-api-server',
    async configureServer(server) {
      const script = path.resolve(__dirname, 'serve.py')
      if (await portBusy(8103)) {
        console.log('[mtg-api] 8103 已被占用,沿用现有后端')
        return
      }
      const py = existsSync(VENV_PY) ? VENV_PY : 'python3'
      console.log('[mtg-api] 启动后端 API (8103)...')
      proc = spawn(py, [script, '--port', '8103'], {
        stdio: 'inherit',
        cwd: path.resolve(__dirname, '..'),
      })
      proc.on('error', (e) => console.error('[mtg-api] 后端启动失败:', e.message))
      const stop = () => {
        if (proc && !proc.killed) {
          console.log('[mtg-api] 关闭后端 API')
          proc.kill('SIGTERM')
          proc = null
        }
      }
      server.httpServer?.on('close', stop)
      process.on('SIGTERM', stop)
      process.on('SIGINT', stop)
    },
  }
}

export default defineConfig({
  plugins: [vue(), tailwindcss(), apiServerPlugin()],
  server: {
    proxy: {
      '/api': { target: 'http://127.0.0.1:8103', changeOrigin: true },
    },
  },
})
