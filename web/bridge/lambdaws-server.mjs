/**
 * LambdaWS Jarvis web bridge.
 *
 * This keeps the open-source holographic browser interface while using the
 * existing Python daemon as the brain. The browser speaks the same lightweight
 * WebSocket protocol as adewaskar/jarvis; this bridge translates each turn to
 * the local Unix-socket IPC used by jarvisd.
 */

import http from 'node:http'
import net from 'node:net'
import os from 'node:os'
import { WebSocketServer } from 'ws'

const PORT = Number(process.env.JARVIS_BRIDGE_PORT ?? 8787)
const PROTOCOL_VERSION = 1
const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]'])

const EXTRA_ORIGINS = new Set(
  (process.env.JARVIS_ALLOWED_ORIGINS ?? '')
    .split(',')
    .map((s) => s.trim().replace(/\/+$/, ''))
    .filter(Boolean),
)

const isDevPort = (port) =>
  (port >= 5173 && port <= 5199) || (port >= 4173 && port <= 4199)

function originAllowed(origin) {
  if (!origin) return process.env.JARVIS_ALLOW_NO_ORIGIN === '1'
  const clean = origin.replace(/\/+$/, '')
  if (EXTRA_ORIGINS.has(clean)) return true
  let url
  try {
    url = new URL(clean)
  } catch {
    return false
  }
  if (url.protocol !== 'http:') return false
  if (!LOCAL_HOSTS.has(url.hostname)) return false
  return isDevPort(Number(url.port))
}

function socketPath() {
  if (process.env.XDG_RUNTIME_DIR) {
    return `${process.env.XDG_RUNTIME_DIR}/lambdaws-jarvis.sock`
  }
  return `${os.tmpdir()}/lambdaws-jarvis-${process.getuid()}/lambdaws-jarvis.sock`
}

function writeLine(socket, payload) {
  socket.write(`${JSON.stringify(payload)}\n`)
}

function sendFrame(ws, payload) {
  if (ws.readyState === ws.OPEN) {
    ws.send(JSON.stringify(payload))
  }
}

function callJarvis(method, payload = {}) {
  return new Promise((resolve, reject) => {
    const sock = net.createConnection(socketPath())
    let buffer = ''
    let settled = false

    const finish = (err, value) => {
      if (settled) return
      settled = true
      sock.destroy()
      if (err) reject(err)
      else resolve(value)
    }

    sock.setTimeout(190_000)
    sock.on('connect', () => {
      writeLine(sock, {
        protocol: PROTOCOL_VERSION,
        method,
        ...payload,
      })
    })
    sock.on('timeout', () => finish(new Error('Tempo esgotado aguardando jarvisd.')))
    sock.on('error', (err) => finish(err))
    sock.on('data', (chunk) => {
      buffer += chunk.toString('utf8')
      let newline = buffer.indexOf('\n')
      while (newline >= 0) {
        const line = buffer.slice(0, newline)
        buffer = buffer.slice(newline + 1)
        newline = buffer.indexOf('\n')
        if (!line.trim()) continue

        let msg
        try {
          msg = JSON.parse(line)
        } catch (err) {
          finish(err)
          return
        }

        if (msg.type === 'confirmation_required') {
          writeLine(sock, { type: 'confirmation_response', allowed: false })
          continue
        }

        if (msg.type !== 'response') {
          finish(new Error('Resposta IPC invalida do jarvisd.'))
          return
        }

        if (!msg.ok) {
          finish(new Error(msg.error || 'Falha no daemon Jarvis.'))
          return
        }

        finish(null, msg.result ?? {})
        return
      }
    })
  })
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url ?? '/', `http://${req.headers.host ?? 'localhost'}`)

  if (url.pathname === '/health') {
    let daemon = false
    try {
      const ping = await callJarvis('ping')
      daemon = ping.status === 'ready'
    } catch {
      daemon = false
    }
    res.writeHead(200, {
      'content-type': 'application/json; charset=utf-8',
      'access-control-allow-origin': '*',
    })
    res.end(JSON.stringify({ ok: daemon, daemon, stt: false, tts: false }))
    return
  }

  res.writeHead(404, { 'content-type': 'application/json; charset=utf-8' })
  res.end(JSON.stringify({ ok: false, error: 'Not found' }))
})

const wss = new WebSocketServer({
  server,
  verifyClient(info, done) {
    done(originAllowed(info.origin), 403, 'Forbidden origin')
  },
})

wss.on('connection', (ws) => {
  sendFrame(ws, { type: 'ready', servers: ['jarvisd', 'groq', 'ollama', 'memory'] })

  ws.on('message', async (raw) => {
    let msg
    try {
      msg = JSON.parse(raw.toString())
    } catch {
      sendFrame(ws, { type: 'error', message: 'Invalid JSON frame.' })
      return
    }

    if (msg.type === 'interrupt') {
      sendFrame(ws, { type: 'done', ask: msg.id, text: '' })
      return
    }

    if (msg.type !== 'ask') return

    const ask = String(msg.id ?? '')
    const text = String(msg.text ?? '').trim()
    if (!text) {
      sendFrame(ws, { type: 'done', ask, text: '' })
      return
    }

    sendFrame(ws, { type: 'tool', ask, name: 'jarvisd' })
    try {
      const result = await callJarvis('ask', { prompt: text })
      const answer = String(result.answer ?? '')
      sendFrame(ws, { type: 'text', ask, delta: answer })
      sendFrame(ws, { type: 'done', ask, text: answer })
    } catch (err) {
      sendFrame(ws, {
        type: 'error',
        ask,
        message:
          err instanceof Error
            ? err.message
            : 'Nao foi possivel falar com o daemon Jarvis.',
      })
    }
  })
})

server.listen(PORT, '127.0.0.1', () => {
  console.log(`[jarvis] LambdaWS bridge ready on http://127.0.0.1:${PORT}`)
  console.log(`[jarvis] IPC socket: ${socketPath()}`)
})
