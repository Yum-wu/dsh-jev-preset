#!/usr/bin/env node
/**
 * 诊断:JEV 的 C3 会话是否真的跨多轮?
 *
 * 假设:`run-bench.mjs` 在**第一个** turn/end 就 break,而 JEV 用
 * `backgroundMode: continuable` —— 派发后父会话 turn 结束,等子代理结算通知
 * 注入后才开**新 turn** 做裁决。故 run-bench 只看到「等结算」那一轮,
 * 把「未收敛」误记为「答错」。
 *
 * 本探针不 break,持续轮询直到连续 N 秒无新 turn,逐轮打印。
 *
 * 用法:node _probe_turns.mjs [caseIndex] [idleSeconds]
 */
import { readFileSync, mkdirSync } from 'node:fs'
import { homedir, tmpdir } from 'node:os'
import { join } from 'node:path'

const CASE_IDX = Number(process.argv[2] ?? 0)
const IDLE_S = Number(process.argv[3] ?? 90)
const MAX_S = 900

function readBase() {
  const text = readFileSync(join(homedir(), '.dsh', 'web-url.txt'), 'utf8')
  const url = new URL(text.split(/\r?\n/).find((l) => l.startsWith('url=')).slice(4))
  return { origin: url.origin, token: url.searchParams.get('token') }
}
const { origin, token } = readBase()
const auth = await fetch(`${origin}/?token=${encodeURIComponent(token)}`, { redirect: 'manual' })
if (auth.status !== 303) throw new Error(`token 换 cookie 失败 HTTP ${auth.status}`)
const cookie = auth.headers.getSetCookie().map((c) => c.split(';')[0]).join('; ')

async function rpc(method, a) {
  const r = await fetch(`${origin}/api/${method}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', cookie },
    body: JSON.stringify({ type: 'client-request', rpcId: crypto.randomUUID(), method, payload: { args: a } }),
  })
  if (!r.ok) throw new Error(`${method} HTTP ${r.status}`)
  const j = await r.json()
  if (j.result?.ok !== true) throw new Error(`${method} ${j.result?.error?.code}: ${j.result?.error?.message}`)
  return j.result.value
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

const suite = readFileSync('suite-candy30.jsonl', 'utf8').split(/\r?\n/).filter(Boolean).map((l) => JSON.parse(l))
const c = suite[CASE_IDX]
if (!c) throw new Error(`无 case index ${CASE_IDX}`)

const cwd = join(tmpdir(), 'jevbench', `turnprobe-${c.id}`)
mkdirSync(cwd, { recursive: true })

const created = await rpc('session/create', { request: { agentPreset: 'jev', cwd } })
const sid = created.sessionId
console.log(`session=${sid} preset=${created.agentPreset} case=${c.id}`)
await rpc('session/selectModel', { request: { sessionId: sid, provider: 'opencodex', model: 'opencode-zen/space-bunny-free', reasoningEffort: 'high' } })
await rpc('session/prompt', { request: { sessionId: sid, requestId: crypto.randomUUID(), mode: 'queue', content: [{ type: 'text', text: c.question }] } })

/** 按 turn 聚合 assistant 文本 + turn/end 事件。 */
function turnsOf(records) {
  const events = records.map((r) => r?.event ?? r).filter(Boolean)
  const map = new Map()
  for (const e of events) {
    const t = e?.data?.turn
    if (typeof t !== 'number') continue
    if (!map.has(t)) map.set(t, { texts: [], ended: false, endReason: null, tools: [], userMsgs: [] })
    const g = map.get(t)
    if (e.type === 'assistant/message') {
      for (const b of e.data?.message?.content ?? []) {
        if (b?.type === 'text' && typeof b.text === 'string') g.texts.push(b.text)
        if (b?.type === 'toolCall' || b?.type === 'tool_use') g.tools.push(b.name ?? b.toolName ?? '?')
      }
    }
    if (e.type === 'user/message') {
      const txt = (e.data?.message?.content ?? []).filter((b) => b?.type === 'text').map((b) => b.text).join('\n')
      if (txt.trim()) g.userMsgs.push(txt.slice(0, 120))
    }
    if (e.type === 'turn/end') { g.ended = true; g.endReason = e.data?.reason?.kind ?? null }
  }
  return map
}

const started = Date.now()
let lastChange = Date.now()
let seenTurns = 0
let lastSnapshot = ''
const history = []

while (Date.now() - started < MAX_S * 1000) {
  await sleep(5000)
  let proj, page
  try {
    proj = await rpc('session/projections', { request: { sessionId: sid } })
    page = await rpc('session/page', { request: { address: { kind: 'session', sessionId: sid }, throughSeq: proj.asOfSeq } })
  } catch (e) {
    console.log(`  轮询出错(继续): ${e.message}`)
    continue
  }
  const map = turnsOf(page.records ?? [])
  const snap = [...map.entries()].map(([t, g]) => `${t}:${g.ended}:${g.texts.join('').length}:${g.tools.length}`).join('|')
  if (snap !== lastSnapshot) { lastSnapshot = snap; lastChange = Date.now() }
  if (map.size > seenTurns) {
    seenTurns = map.size
    for (const [t, g] of [...map.entries()].sort((a, b) => a[0] - b[0])) {
      if (history.some((h) => h.turn === t && h.len === g.texts.join('').length)) continue
      history.push({ turn: t, len: g.texts.join('').length, ended: g.ended, tools: g.tools.length })
      console.log(`  [t+${((Date.now() - started) / 1000).toFixed(0)}s] turn=${t} ended=${g.ended} reason=${g.endReason} ` +
        `文本=${g.texts.join('').length}字符 工具=${g.tools.length}(${g.tools.slice(0, 4).join(',')}) 注入user=${g.userMsgs.length}`)
    }
  }
  const idle = (Date.now() - lastChange) / 1000
  if (idle > IDLE_S && map.size > 0) {
    const allEnded = [...map.values()].every((g) => g.ended)
    if (allEnded) { console.log(`  连续 ${IDLE_S}s 无变化且全部 turn 已结束 → 停止`); break }
  }
}

const proj = await rpc('session/projections', { request: { sessionId: sid } })
const page = await rpc('session/page', { request: { address: { kind: 'session', sessionId: sid }, throughSeq: proj.asOfSeq } })
const map = turnsOf(page.records ?? [])

console.log(`\n=== 最终:共 ${map.size} 个 turn ===`)
for (const [t, g] of [...map.entries()].sort((a, b) => a[0] - b[0])) {
  const txt = g.texts.join('\n')
  const hasJson = txt.includes('```json')
  console.log(`\n--- turn ${t} | ended=${g.ended} reason=${g.endReason} | ${txt.length}字符 | 含json块=${hasJson}`)
  console.log(`    工具: ${g.tools.join(',') || '(无)'}`)
  if (g.userMsgs.length) console.log(`    注入user: ${g.userMsgs.map((s) => s.replace(/\s+/g, ' ').slice(0, 80)).join(' ／ ')}`)
  console.log(`    文本尾部: ${txt.slice(-400).replace(/\n/g, ' ⏎ ')}`)
}

const list = await rpc('session/list', { _request: {} })
const kids = (list.items ?? []).filter((s) => s.parentSessionId === sid)
console.log(`\n子会话 ${kids.length} 个: ${kids.map((k) => k.sessionId).join(', ')}`)
console.log(`\n复现:node _probe_turns.mjs ${CASE_IDX}`)
