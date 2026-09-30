#!/usr/bin/env node
/**
 * Import provider API keys into the local FreeLLMAPI dashboard without printing
 * any secret material. The script reads local env files, registers supported
 * keys through the dashboard API, keeps keyless providers enabled, and reports
 * only platform/status counts.
 */

import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

const DEFAULT_BASE_URL = process.env.FREELLMAPI_URL ?? 'http://127.0.0.1:3001'
const DASHBOARD_ENV = process.env.FREELLMAPI_DASHBOARD_ENV ?? path.join(os.homedir(), 'freellmapi/.dashboard.env')
const DEFAULT_KEY_FILES = [
  path.join(os.homedir(), '.config/freellmapi/provider-keys.env'),
  path.join(os.homedir(), '.config/lambdaws-jarvis/provider-keys.env'),
  path.join(os.homedir(), '.config/lambdaws-jarvis/secrets.env'),
]

const KEYLESS_PLATFORMS = ['kilo', 'ovh', 'aihorde']

const PROVIDER_KEYS = {
  aclide: ['ACLIDE_API_KEY'],
  agnes: ['AGNES_API_KEY'],
  ainative: ['AINATIVE_API_KEY', 'AI_NATIVE_API_KEY'],
  aion: ['AION_API_KEY', 'AIONLABS_API_KEY'],
  airforce: ['AIRFORCE_API_KEY'],
  anyapi: ['ANYAPI_API_KEY'],
  bai: ['BAI_API_KEY', 'B_AI_API_KEY'],
  bazaarlink: ['BAZAARLINK_API_KEY'],
  blaze: ['BLAZE_API_KEY', 'BLAZEAPI_API_KEY'],
  cerebras: ['CEREBRAS_API_KEY'],
  clod: ['CLOD_API_KEY'],
  cohere: ['COHERE_API_KEY'],
  dreamprompting: ['DREAMPROMPTING_API_KEY'],
  electronhub: ['ELECTRONHUB_API_KEY', 'ELECTRON_HUB_API_KEY'],
  experiential: ['EXPERIENTIAL_API_KEY', 'EXPERIENTIALLABS_API_KEY', 'EXPERIENTIAL_LABS_API_KEY', 'EXPLABS_API_KEY'],
  github: ['GITHUB_MODELS_API_KEY', 'GITHUB_TOKEN', 'GH_TOKEN'],
  google: ['GOOGLE_API_KEY', 'GEMINI_API_KEY'],
  groq: ['GROQ_API_KEY'],
  huggingface: ['HUGGINGFACE_API_KEY', 'HF_TOKEN', 'HUGGING_FACE_HUB_TOKEN'],
  llm7: ['LLM7_API_KEY'],
  llmtr: ['LLMTR_API_KEY'],
  logfare: ['LOGFARE_API_KEY'],
  longcat: ['LONGCAT_API_KEY'],
  lucidity: ['LUCIDITY_API_KEY'],
  mistral: ['MISTRAL_API_KEY'],
  modelscope: ['MODELSCOPE_API_KEY', 'MODELSCOPE_TOKEN'],
  moondream: ['MOONDREAM_API_KEY'],
  nara: ['NARA_API_KEY', 'NARAROUTER_API_KEY'],
  navy: ['NAVY_API_KEY', 'NAVYAI_API_KEY'],
  nvidia: ['NVIDIA_API_KEY', 'NVIDIA_NIM_API_KEY'],
  ollama: ['OLLAMA_CLOUD_API_KEY', 'OLLAMA_API_KEY'],
  opencode: ['OPENCODE_API_KEY', 'OPENCODE_ZEN_API_KEY'],
  openrouter: ['OPENROUTER_API_KEY'],
  orcarouter: ['ORCAROUTER_API_KEY', 'ORCA_ROUTER_API_KEY'],
  pollinations: ['POLLINATIONS_API_KEY'],
  qianfan: ['QIANFAN_API_KEY', 'BAIDU_QIANFAN_API_KEY'],
  radeon: ['RADEON_API_KEY', 'AMD_RADEON_API_KEY'],
  reka: ['REKA_API_KEY'],
  requesty: ['REQUESTY_API_KEY'],
  routeway: ['ROUTEWAY_API_KEY'],
  router9: ['ROUTER9_API_KEY'],
  sail: ['SAIL_API_KEY', 'SAIL_RESEARCH_API_KEY'],
  sealion: ['SEALION_API_KEY', 'SEA_LION_API_KEY'],
  septor: ['SEPTOR_API_KEY'],
  siliconflow: ['SILICONFLOW_API_KEY'],
  speka: ['SPEKA_API_KEY'],
  speechify: ['SPEECHIFY_API_KEY'],
  unorouter: ['UNOROUTER_API_KEY', 'UNO_ROUTER_API_KEY'],
  volcengine: ['VOLCENGINE_API_KEY', 'ARK_API_KEY'],
  waterfall: ['WATERFALL_API_KEY'],
  xfyun: ['XFYUN_API_KEY', 'IFLYTEK_API_KEY'],
  xkiro: ['XKIRO_API_KEY'],
  zhipu: ['ZHIPU_API_KEY', 'ZAI_API_KEY', 'BIGMODEL_API_KEY'],
}

function parseEnv(text) {
  const out = {}
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim()
    if (!line || line.startsWith('#')) continue
    const idx = line.indexOf('=')
    if (idx < 1) continue
    const key = line.slice(0, idx).trim()
    let value = line.slice(idx + 1).trim()
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1)
    }
    if (key) out[key] = value
  }
  return out
}

function loadEnvFiles(files) {
  const env = { ...process.env }
  const read = []
  for (const file of files) {
    if (!fs.existsSync(file)) continue
    Object.assign(env, parseEnv(fs.readFileSync(file, 'utf8')))
    read.push(file)
  }
  return { env, read }
}

function first(env, names) {
  for (const name of names) {
    const value = env[name]?.trim()
    if (value) return { name, value }
  }
  return null
}

function platformKey(env, platform) {
  if (platform === 'cloudflare') {
    const compound = first(env, ['CLOUDFLARE_WORKERS_AI_KEY', 'CLOUDFLARE_AI_KEY'])
    if (compound) return compound
    const account = first(env, ['CLOUDFLARE_ACCOUNT_ID'])
    const token = first(env, ['CLOUDFLARE_API_TOKEN', 'CLOUDFLARE_WORKERS_AI_TOKEN'])
    if (account && token) return { name: `${account.name}+${token.name}`, value: `${account.value}:${token.value}` }
    return null
  }
  const names = PROVIDER_KEYS[platform]
  return names ? first(env, names) : null
}

async function request(pathname, init = {}) {
  const res = await fetch(`${DEFAULT_BASE_URL}${pathname}`, init)
  const text = await res.text()
  let body = null
  try { body = text ? JSON.parse(text) : null } catch { body = { raw: text.slice(0, 500) } }
  if (!res.ok) {
    const message = body?.error?.message || body?.message || res.statusText
    throw new Error(`${init.method ?? 'GET'} ${pathname} failed (${res.status}): ${message}`)
  }
  return body
}

function dashboardToken() {
  if (process.env.FREELLMAPI_DASHBOARD_TOKEN) return process.env.FREELLMAPI_DASHBOARD_TOKEN
  if (!fs.existsSync(DASHBOARD_ENV)) throw new Error(`Dashboard env not found: ${DASHBOARD_ENV}`)
  const env = parseEnv(fs.readFileSync(DASHBOARD_ENV, 'utf8'))
  if (!env.FREELLMAPI_DASHBOARD_TOKEN) throw new Error(`FREELLMAPI_DASHBOARD_TOKEN missing in ${DASHBOARD_ENV}`)
  return env.FREELLMAPI_DASHBOARD_TOKEN
}

function argFiles() {
  const idx = process.argv.indexOf('--env-file')
  if (idx >= 0) {
    const value = process.argv[idx + 1]
    if (!value) throw new Error('--env-file needs a path')
    return [path.resolve(value)]
  }
  return DEFAULT_KEY_FILES
}

async function main() {
  const files = argFiles()
  const { env, read } = loadEnvFiles(files)
  const token = dashboardToken()
  const headers = { authorization: `Bearer ${token}`, 'content-type': 'application/json' }
  const providersPayload = await request('/api/keys/providers', { headers })
  const providers = providersPayload.providers ?? []

  const configured = new Set(providers.filter((p) => p.enabledKeyCount > 0).map((p) => p.platform))
  const supported = new Set(providers.map((p) => p.platform))
  const added = []
  const skipped = []
  const missing = []

  for (const platform of KEYLESS_PLATFORMS) {
    if (!supported.has(platform)) continue
    if (configured.has(platform)) {
      skipped.push({ platform, reason: 'already configured' })
      continue
    }
    const body = await request('/api/keys', {
      method: 'POST', headers,
      body: JSON.stringify({ platform, label: `Jarvis ${platform} anonymous` }),
    })
    added.push({ platform, id: body.id, source: 'keyless' })
    configured.add(platform)
  }

  for (const platform of Object.keys(PROVIDER_KEYS).sort()) {
    if (!supported.has(platform)) continue
    const key = platformKey(env, platform)
    if (!key) {
      missing.push(platform)
      continue
    }
    if (configured.has(platform) && !process.argv.includes('--add-duplicates')) {
      skipped.push({ platform, reason: 'already configured' })
      continue
    }
    const body = await request('/api/keys', {
      method: 'POST', headers,
      body: JSON.stringify({ platform, key: key.value, label: `Jarvis ${platform} (${key.name})` }),
    })
    added.push({ platform, id: body.id, source: key.name })
    configured.add(platform)
  }

  const local = parseEnv(fs.readFileSync(path.join(process.cwd(), '.env.local'), 'utf8'))
  const unified = local.JARVIS_LLM_API_KEY || process.env.JARVIS_LLM_API_KEY
  let availableModels = null
  if (unified) {
    const res = await fetch(`${DEFAULT_BASE_URL}/v1/models?available=true`, {
      headers: { authorization: `Bearer ${unified}` },
    })
    if (res.ok) {
      const json = await res.json()
      availableModels = Array.isArray(json.data) ? json.data.length : null
    }
  }

  console.log(JSON.stringify({
    envFilesRead: read,
    added,
    skipped,
    missingKeyCount: missing.length,
    missingProviders: missing,
    availableModels,
  }, null, 2))
}

main().catch((err) => {
  console.error(err.message)
  process.exit(1)
})
