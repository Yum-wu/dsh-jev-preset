#!/usr/bin/env node
/**
 * audit-subagent-settlement.mjs
 *
 * 审计子代理结算健康度:统计 RATE_LIMIT / 重试耗尽 / 无 closing message 的比例。
 *
 * 背景(2026-09-28 实测):JEV 三路同模型并发发射 → provider 429 → 6 次重试耗尽
 * → turn/end 以 RATE_LIMIT 收尾 → 三路零产出。本工具把该失败模式机读化,
 * 使"三路是否真跑通"不再依赖人工读会话。
 *
 * 用法:
 *   node tools/audit-subagent-settlement.mjs [--limit N] [--json]
 *
 * 退出码:0 = 采样到的子会话无 RATE_LIMIT 失败;1 = 存在限流失败(提示需异构路由)。
 */
import { readFileSync, existsSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'
import { createRequire } from 'node:module'

const require_ = createRequire(import.meta.url)
const HOME = join(homedir(), '.dsh')
const URL_FILE = join(HOME, 'web-url.txt')
const SESSIONS_DIR = join(HOME, 'sessions')

const argv = process.argv.slice(2)
const LIMIT = (() => {
  const i = argv.indexOf('--limit')
  return i >= 0 ? Number(argv[i + 1]) || 20 : 20
})()
const AS_JSON = argv.includes('--json')

function readBase() {
  const line = readFileSync(URL_FILE, 'utf8').split(/\r?\n/).find((l) => l.startsWith('url='))
  if (!line) throw new Error(`${URL_FILE} 中没有 url= 行`)
  const url = new URL(line.slice(4))
  return { origin: url.origin, token: url.searchParams.get('token') }
}

async function authenticate(origin, token) {
  const r = await fetch(`${origin}/?token=${encodeURIComponent(token)}`, { redirect: 'manual' })
  const cookies = r.headers.getSetCookie?.() ?? []
  if (cookies.length === 0) throw new Error('token 换取 cookie 失败(DSH 可能已重启)')
  return cookies.map((c) => c.split(';')[0]).join('; ')
}

async function rpc(origin, cookie, endpoint, args = {}) {
  const r = await fetch(`${origin}/api/${endpoint}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', cookie },
    body: JSON.stringify({ type: 'client-request', rpcId: crypto.randomUUID(), method: endpoint, payload: { args } }),
  })
  const j = await r.json()
  if (j.result?.ok !== true) throw new Error(`${endpoint} → ${j.result?.error?.code}: ${j.result?.error?.message}`)
  return j.result.value
}

/** 解压多帧 zstd 会话日志(帧魔数 28 b5 2f fd 逐帧解)。 */
function readSessionLog(sessionId) {
  const dirs = require_('node:fs').readdirSync(SESSIONS_DIR, { withFileTypes: true })
  for (const d of dirs) {
    if (!d.isDirectory()) continue
    const f = join(SESSIONS_DIR, d.name, sessionId, 'session.v4.jsonl.zstd')
    if (!existsSync(f)) continue
    const buf = readFileSync(f)
    const MAGIC = Buffer.from([0x28, 0xb5, 0x2f, 0xfd])
    const offs = []
    for (let i = 0; (i = buf.indexOf(MAGIC, i)) !== -1; i += 4) offs.push(i)
    const chunks = []
    for (let k = 0; k < offs.length; k++) {
      const end = k + 1 < offs.length ? offs[k + 1] : buf.length
      try {
        chunks.push(require_('node:zlib').zstdDecompressSync(buf.subarray(offs[k], end)).toString('utf8'))
      } catch { /* 跳过损坏帧 */ }
    }
    return chunks.join('\n')
  }
  return null
}

function analyze(logText) {
  const out = { retryEvents: 0, rateLimitFailures: 0, turnEndError: null, closingText: null, assistantText: '' }
  for (const line of logText.split(/\r?\n/)) {
    if (!line.trim()) continue
    let o
    try { o = JSON.parse(line) } catch { continue }
    if (o.type === 'llm/retry') out.retryEvents++
    if (o.type === 'assistant/attempt') {
      for (const s of o.data?.stream ?? []) {
        // 结构: s.chunk = { type:'finish', reason:{ kind:'error', failure:{ code, message } } }
        const f = s?.chunk?.reason?.failure
        if (f && /RATE_LIMIT|rate_limit/i.test(`${f.code} ${f.message}`)) out.rateLimitFailures++
      }
    }
    if (o.type === 'turn/end' && o.data?.reason?.kind === 'error') {
      out.turnEndError = o.data.reason.error?.code ?? 'ERROR'
    }
    if (o.type === 'assistant/message') {
      for (const c of o.data?.message?.content ?? []) {
        if (c?.type === 'text') out.assistantText += c.text
      }
    }
  }
  const m = out.assistantText.match(/\[Path [123][^\]]*\]/)
  out.closingText = m ? m[0] : null
  return out
}

async function main() {
  const { origin, token } = readBase()
  const cookie = await authenticate(origin, token)
  const list = await rpc(origin, cookie, 'session/list', { _request: {} })
  const kids = (list.items ?? [])
    .filter((s) => s.origin === 'subagent' && (s.projections?.asOfSeq ?? 0) > 20)
    .sort((a, b) => (b.updatedAt ?? 0) - (a.updatedAt ?? 0))
    .slice(0, LIMIT)

  const rows = []
  for (const k of kids) {
    const text = readSessionLog(k.sessionId)
    if (text === null) {
      rows.push({ sessionId: k.sessionId, logMissing: true })
      continue
    }
    rows.push({ sessionId: k.sessionId, ...analyze(text) })
  }

  const rateLimited = rows.filter((r) => (r.rateLimitFailures ?? 0) > 0)
  const noClosing = rows.filter((r) => !r.logMissing && !r.closingText)

  if (AS_JSON) {
    console.log(JSON.stringify({ sampled: rows.length, rateLimited: rateLimited.length, noClosing: noClosing.length, rows }, null, 2))
  } else {
    console.log(`\n=== 子代理结算健康度审计(采样 ${rows.length} 个最近子会话)===`)
    for (const r of rows) {
      if (r.logMissing) { console.log(`  ${r.sessionId}  日志缺失(未落盘或已归档)`); continue }
      const flag = r.rateLimitFailures > 0 ? 'RATE_LIMIT' : 'ok'
      console.log(`  ${r.sessionId}  retries=${r.retryEvents} rateLimit=${r.rateLimitFailures} turnEnd=${r.turnEndError ?? '-'} closing=${r.closingText ?? 'NONE'}  [${flag}]`)
    }
    console.log(`\n汇总: 限流失败 ${rateLimited.length}/${rows.length}，无 closing ${noClosing.length}/${rows.length}`)
    if (rateLimited.length > 0) {
      console.log('提示: 存在限流失败 → 三路应使用异构模型路由(见 cordis.patch.yml §3.3),不要同模型并发。')
    }
  }
  process.exit(rateLimited.length > 0 ? 1 : 0)
}

main().catch((e) => { console.error('审计失败:', e.message); process.exit(2) })
