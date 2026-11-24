import { spawn } from 'node:child_process'
import net from 'node:net'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const BACKEND_PORT = 8000
const BACKEND_URL = `http://localhost:${BACKEND_PORT}`

function wait(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms)
  })
}

function isPortOpen(port, host = '127.0.0.1') {
  return new Promise((resolve) => {
    const socket = new net.Socket()

    const finish = (value) => {
      socket.destroy()
      resolve(value)
    }

    socket.setTimeout(500)
    socket.once('connect', () => finish(true))
    socket.once('timeout', () => finish(false))
    socket.once('error', () => finish(false))
    socket.connect(port, host)
  })
}

function stopBackendProcess(backendProcess) {
  if (!backendProcess || backendProcess.killed) {
    return
  }

  if (process.platform === 'win32') {
    spawn('taskkill', ['/pid', String(backendProcess.pid), '/T', '/F'], {
      stdio: 'ignore',
      shell: true,
    })
    return
  }

  backendProcess.kill('SIGTERM')
}

function backendAutostartPlugin() {
  let backendProcess
  let startPromise

  return {
    name: 'backend-autostart',
    apply: 'serve',
    async configureServer(server) {
      if (startPromise) {
        await startPromise
        return
      }

      startPromise = (async () => {
        if (await isPortOpen(BACKEND_PORT)) {
          server.config.logger.info(`[backend] Ya hay un backend escuchando en ${BACKEND_URL}`, {
            timestamp: true,
          })
          return
        }

        const backendRoot = path.resolve(__dirname, '..')
        const pythonCommand = process.env.PYTHON_BIN || 'python'

        server.config.logger.info(`[backend] Iniciando ${pythonCommand} server.py en ${BACKEND_URL}`, {
          timestamp: true,
        })

        backendProcess = spawn(pythonCommand, ['server.py'], {
          cwd: backendRoot,
          stdio: 'inherit',
          shell: process.platform === 'win32',
        })

        backendProcess.on('exit', (code) => {
          if (code && code !== 0) {
            server.config.logger.error(`[backend] server.py termino con codigo ${code}.`, {
              timestamp: true,
            })
          }
        })

        for (let attempt = 0; attempt < 20; attempt += 1) {
          if (await isPortOpen(BACKEND_PORT)) {
            server.config.logger.info(`[backend] Backend listo en ${BACKEND_URL}`, {
              timestamp: true,
            })
            return
          }
          await wait(500)
        }

        server.config.logger.warn(
          `[backend] No respondio en ${BACKEND_URL}. Revisa la consola de Python si hubo error al arrancar.`,
          {
            timestamp: true,
          },
        )
      })()

      server.httpServer?.once('close', () => {
        stopBackendProcess(backendProcess)
      })

      await startPromise
    },
  }
}

export default defineConfig({
  plugins: [react(), backendAutostartPlugin()],
  server: {
    proxy: {
      '/api': {
        target: BACKEND_URL,
        changeOrigin: true,
      },
    },
  },
})
