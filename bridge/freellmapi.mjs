/**
 * JARVIS bridge for FreeLLMAPI.
 *
 * The browser keeps the same WebSocket protocol used by the upstream bridge,
 * while this process talks to an OpenAI-compatible /v1/chat/completions
 * endpoint. It is built for a local FreeLLMAPI router at localhost:3001, but
 * any compatible endpoint works with the same environment variables.
 */

import http from 'node:http'
import { WebSocketServer } from 'ws'

const PORT = Number(process.env.JARVIS_BRIDGE_PORT ?? 8787)
const BASE_URL = stripSlash(process.env.JARVIS_LLM_BASE_URL ?? 'http://localhost:3001/v1')
const API_KEY = process.env.JARVIS_LLM_API_KEY ?? process.env.OPENAI_API_KEY ?? ''
const MODEL = process.env.JARVIS_MODEL ?? 'auto:balanced'
const MAX_HISTORY = Number(process.env.JARVIS_HISTORY_TURNS ?? 12)

const SYSTEM_PROMPT =
  process.env.JARVIS_SYSTEM_PROMPT ??
  [
    'You are J.A.R.V.I.S., a calm, concise, capable voice assistant.',
    'Answer in Brazilian Portuguese by default. If the user speaks another language, answer in that same language.',
    'Keep spoken answers brief and useful. Ask one clear follow-up when needed.',
    'You are running through FreeLLMAPI, so do not claim to have Claude Code tools.',
  ].join(' ')

const EXTRA_ORIGINS = new Set(
  (process.env.JARVIS_ALLOWED_ORIGINS ?? '')
    .split(',')
    .map((s) => s.trim().replace(/\/+$/, ''))
    .filter(Boolean),
)
const ALLOW_NO_ORIGIN = process.env.JARVIS_ALLOW_NO_ORIGIN === '1'
const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]'])
const isDevPort = (port) =>
  (port >= 5173 && port <= 5199) || (port >= 4173 && port <= 4199)

function stripSlash(value) {
  return value.replace(/\/+$/, '')
}

function originAllowed(origin) {
  if (!origin) return ALLOW_NO_ORIGIN
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

function sendFrame(ws, payload) {
  if (ws.readyState === ws.OPEN) {
    ws.send(JSON.stringify(payload))
  }
}

function authHeaders() {
  return API_KEY ? { Authorization: `Bearer ${API_KEY}` } : {}
}

function errorMessage(err) {
  return err instanceof Error ? err.message : String(err)
}

async function health() {
  try {
    const res = await fetch(`${BASE_URL}/models?available=true`, {
      headers: authHeaders(),
      signal: AbortSignal.timeout(3000),
    })
    return { ok: res.ok, status: res.status }
  } catch (err) {
    return { ok: false, error: errorMessage(err) }
  }
}

function trimHistory(history) {
  const max = Math.max(2, MAX_HISTORY * 2)
  if (history.length > max) history.splice(0, history.length - max)
}

async function readStream(res, ws, ask) {
  const reader = res.body?.getReader()
  if (!reader) throw new Error('FreeLLMAPI returned an empty stream.')

  const decoder = new TextDecoder()
  let buffer = ''
  let full = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    let index
    while ((index = buffer.indexOf('\n\n')) >= 0) {
      const raw = buffer.slice(0, index)
      buffer = buffer.slice(index + 2)
      for (const line of raw.split('\n')) {
        const clean = line.trim()
        if (!clean.startsWith('data:')) continue
        const data = clean.slice(5).trim()
        if (!data || data === '[DONE]') continue

        let frame
        try {
          frame = JSON.parse(data)
        } catch {
          continue
        }
        const delta = frame.choices?.[0]?.delta?.content ?? ''
        if (delta) {
          full += delta
          sendFrame(ws, { type: 'text', ask, delta })
        }
      }
    }
  }

  return full
}

async function complete(prompt, history, ws, ask) {
  const messages = [
    { role: 'system', content: SYSTEM_PROMPT },
    ...history,
    { role: 'user', content: prompt },
  ]

  const res = await fetch(`${BASE_URL}/chat/completions`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(),
    },
    body: JSON.stringify({
      model: MODEL,
      messages,
      stream: true,
      temperature: 0.6,
    }),
    signal: AbortSignal.timeout(180_000),
  })

  if (!res.ok) {
    const text = await res.text().catch(() => '')
    const detail = text ? `: ${text.slice(0, 500)}` : ''
    throw new Error(`FreeLLMAPI request failed (${res.status})${detail}`)
  }

  const answer = await readStream(res, ws, ask)
  return answer.trim()
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url ?? '/', `http://${req.headers.host ?? 'localhost'}`)

  if (url.pathname === '/health') {
    const upstream = await health()
    res.writeHead(200, {
      'content-type': 'application/json; charset=utf-8',
      'access-control-allow-origin': '*',
    })
    res.end(
      JSON.stringify({
        ok: upstream.ok,
        backend: 'freellmapi',
        baseUrl: BASE_URL,
        model: MODEL,
        hasKey: Boolean(API_KEY),
        upstream,
        stt: false,
        tts: false,
      }),
    )
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
  const history = []
  sendFrame(ws, {
    type: 'ready',
    servers: [
      { name: 'FreeLLMAPI' },
      { name: MODEL },
      { name: API_KEY ? 'unified key' : 'missing key' },
    ],
  })

  ws.on('message', async (raw) => {
    let msg
    try {
      msg = JSON.parse(raw.toString())
    } catch {
      sendFrame(ws, { type: 'error', message: 'Invalid JSON frame.' })
      return
    }

    if (msg.type === 'interrupt') return
    if (msg.type !== 'ask') return

    const ask = String(msg.id ?? '')
    const prompt = String(msg.text ?? '').trim()
    if (!prompt) {
      sendFrame(ws, { type: 'done', ask, text: '' })
      return
    }

    if (!API_KEY) {
      sendFrame(ws, {
        type: 'error',
        ask,
        message:
          'FreeLLMAPI is selected but JARVIS_LLM_API_KEY is not set. Open the FreeLLMAPI dashboard, copy the unified key, and export it before starting Jarvis.',
      })
      return
    }

    sendFrame(ws, { type: 'tool', ask, name: `freellmapi · ${MODEL}` })
    try {
      const answer = await complete(prompt, history, ws, ask)
      history.push({ role: 'user', content: prompt })
      history.push({ role: 'assistant', content: answer })
      trimHistory(history)
      sendFrame(ws, { type: 'done', ask, text: answer })
    } catch (err) {
      sendFrame(ws, { type: 'error', ask, message: errorMessage(err) })
    }
  })
})

server.listen(PORT, '127.0.0.1', () => {
  console.log(`[jarvis] FreeLLMAPI bridge listening on ws://localhost:${PORT}`)
  console.log(`[jarvis] upstream ${BASE_URL} · model ${MODEL}`)
  console.log(
    API_KEY
      ? '[jarvis] unified key loaded from environment'
      : '[jarvis] missing JARVIS_LLM_API_KEY; copy it from the FreeLLMAPI dashboard',
  )
})
