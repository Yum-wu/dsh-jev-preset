#!/usr/bin/env node
/**
 * 门控验证:改版后,计算类任务是否走「单路 + 断言」(新首选)而非三路。
 *
 * 判据(三选一,都看):
 *   1. 首行是否出现 [JEV: 断言通过]
 *   2. subagent 派生数是否为 0(不应启三路)
 *   3. token 量级(断言 ~120k,三路 ~1.4M)
 *
 * 用法: node _verify_gate.mjs
 */
import { readFileSync, mkdirSync } from 'node:fs'
import { homedir, tmpdir } from 'node:os'
import { join } from 'node:path'

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

// 一道典型「量化计算」题:命中旧版「强制三路」,新版应走「断言优先」
const QUESTION = `某永续合约维持保证金按名义价值分段超额累进计算(类似个税),分档上限与费率:(50000]以内 MMR=0.004;(250000]以内 MMR=0.005;(1000000]以内 MMR=0.01;(5000000]以内 MMR=0.025;(∞]以内 MMR=0.05(第一档从 0 起)。持仓名义价值 5915950.33 USDT。求维持保证金 MM,以及所在档的速算扣除数 D(满足 MM = 名义价值×所在档MMR − D)。均四舍五入到 0.01。

【作答格式】回复最后必须给出一个 \`\`\`json 代码块:{"mm": "<维持保证金>", "deduction": "<速算扣除数>"}`

const cwd = join(tmpdir(), 'jevbench', 'gate-verify')
mkdirSync(cwd, { recursive: true })

const created = await rpc('session/create', { request: { agentPreset: 'jev', cwd } })
const sid = created.sessionId
console.log(`session=${sid} preset=${created.agentPreset}`)
await rpc('session/selectModel', { request: { sessionId: sid, provider: 'opencodex', model: 'opencode-zen/space-bunny-free', reasoningEffort: 'high' } })
await rpc('session/prompt', { request: { sessionId: sid, requestId: crypto.randomUUID(), mode: 'queue', content: [{ type: 'text', text: QUESTION }] } })

const started = Date.now()
let last = { ended: false, text: '' }
while (Date.now() - started < 900000) {
  await sleep(5000)
  const proj = await rpc('session/projections', { request: { sessionId: sid } })
  const page = await rpc('session/page', { request: { address: { kind: 'session', sessionId: sid }, throughSeq: proj.asOfSeq } })
  const events = (page.records ?? []).map((r) => r?.event ?? r).filter(Boolean)
  const turns = events.map((e) => e?.data?.turn).filter((t) => typeof t === 'number')
  const turn = turns.length ? Math.max(...turns) : null
  const texts = []
  let ended = false
  for (const e of events) {
    if (e?.data?.turn !== turn) continue
    if (e.type === 'assistant/message')
      for (const b of e.data?.message?.content ?? []) if (b?.type === 'text') texts.push(b.text)
    if (e.type === 'turn/end') ended = true
  }
  last = { ended, text: texts.join('\n') }
  const list = await rpc('session/list', { _request: {} })
  const kids = (list.items ?? []).filter((s) => s.parentSessionId === sid)
  const runningKids = kids.filter((s) => s.running === true).length
  if (ended && runningKids === 0 && (last.text.includes('```json') || Date.now() - started > 300000)) {
    const tu = (list.items ?? []).find((s) => s.sessionId === sid)?.projections?.values?.tokenUsage ?? {}
    console.log(`\n收敛: ${((Date.now() - started) / 1000).toFixed(0)}s`)
    console.log(`子会话 ${kids.length} 个(运行中的 ${runningKids} 个)`)
    console.log(`token: ${(tu.uncachedInputTokens ?? 0) + (tu.cacheReadTokens ?? 0) + (tu.outputTokens ?? 0)}`)
    break
  }
}

console.log('\n=== 最终回复 ===')
console.log(last.text)

console.log('\n=== 判据 ===')
const firstLine = (last.text.split('\n').find((l) => l.trim()) ?? '')
console.log(`1. 首行: ${firstLine.slice(0, 80)}`)
console.log(`   含 [JEV: 断言通过]? ${last.text.includes('断言通过')}`)
console.log(`   含 [JEV: 3/3 或 2/3]? ${/\[JEV:\s*[23]\/3/.test(last.text)}`)
console.log(`   含 [JEV: Fast-Pass]? ${last.text.includes('Fast-Pass')}`)
