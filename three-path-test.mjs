#!/usr/bin/env node
/**
 * JEV 三路隔离能力测试:发一个**先验高危**任务,验证模型真的派生 3 路独立 subagent。
 *
 * 这是 JEV 核心机制的活性证明 —— 光挂载 subagent 工具不算数,
 * 必须观察到 3 个 provider=spawn 的子会话真的被创建。
 *
 * 用法:node three-path-test.mjs
 * 退出码:0 = 通过;1 = 失败。
 *
 * ⚠ 本测试消耗较多 token(主会话 + 最多 3 个子会话)。
 */
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'

const HOME = join(homedir(), '.dsh')
const STATE_DIR = join(HOME, 'jev-session-test')
const STATE_FILE = join(STATE_DIR, 'created.json')

const PROMPT = [
  '高危验证任务(命中「量化指标推导 + 资金风控」两条强制三路条件):',
  '',
  '某策略本金 100000,单笔风险预算 2%,止损幅度 3.5%,标的当前价 42.7。',
  '求:1) 每笔最大可开仓位(数量,向下取整) 2) 该仓位下的最大名义敞口 3) 若止损触发,实际亏损金额与占本金比例。',
  '',
  '要求:按 JEV 协议,先判路由,命中高危则**必须**派生 3 路隔离采样:',
  'Path 1 严谨推导者 / Path 2 红队对抗者 / Path 3 极简执行者,',
  '并给出裁决结论与状态路由标识。',
].join('\n')

function readBase() {
  const text = readFileSync(join(HOME, 'web-url.txt'), 'utf8')
  const line = text.split(/\r?\n/).find((l) => l.startsWith('url='))
  const url = new URL(line.slice(4))
  return { origin: url.origin, token: url.searchParams.get('token') }
}

async function authenticate(origin, token) {
  const r = await fetch(`${origin}/?token=${encodeURIComponent(token)}`, { redirect: 'manual' })
  const cookies = r.headers.getSetCookie?.() ?? []
  return cookies.map((c) => c.split(';')[0]).join('; ')
}

async function rpc(origin, cookie, endpoint, args = {}) {
  const r = await fetch(`${origin}/api/${endpoint}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', cookie },
    body: JSON.stringify({ type: 'client-request', rpcId: crypto.randomUUID(), method: endpoint, payload: { args } }),
  })
  if (!r.ok) throw new Error(`${endpoint} → HTTP ${r.status}`)
  const j = await r.json()
  if (j.result?.ok !== true) throw new Error(`${endpoint} → ${j.result?.error?.code}: ${j.result?.error?.message}`)
  return j.result.value
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

function remember(sessionId) {
  mkdirSync(STATE_DIR, { recursive: true })
  const prior = existsSync(STATE_FILE) ? JSON.parse(readFileSync(STATE_FILE, 'utf8')) : []
  prior.push({ sessionId, at: new Date().toISOString() })
  writeFileSync(STATE_FILE, JSON.stringify(prior, null, 2))
}

const { origin, token } = readBase()
const cookie = await authenticate(origin, token)

console.log(`\nJEV 三路隔离能力测试`)
console.log(`服务: ${origin}\n`)

const fails = []
const pass = (m) => console.log(`  PASS  ${m}`)
const fail = (m) => { fails.push(m); console.log(`  FAIL  ${m}`) }

// 基线:记录测试前的子会话数
const before = await rpc(origin, cookie, 'session/list', { _request: {} })
const beforeIds = new Set((before.items ?? []).map((r) => r.sessionId))

console.log('[1] 以 agentPreset=jev 创建主会话')
const created = await rpc(origin, cookie, 'session/create', { request: { agentPreset: 'jev' } })
const sessionId = created.sessionId
pass(`sessionId=${sessionId} preset=${created.agentPreset}`)
remember(sessionId)

console.log('\n[2] 发送高危任务(强制三路)')
await rpc(origin, cookie, 'session/prompt', {
  request: {
    sessionId,
    requestId: crypto.randomUUID(),
    mode: 'queue',
    content: [{ type: 'text', text: PROMPT }],
  },
})
pass('prompt 已受理')

console.log('\n[3] 等待主会话完成(最长 420s,含最多 3 路子会话)')
let records = []
let done = false
const deadline = Date.now() + 420_000
while (Date.now() < deadline) {
  await sleep(5000)
  try {
    const proj = await rpc(origin, cookie, 'session/projections', { request: { sessionId } })
    const page = await rpc(origin, cookie, 'session/page', {
      request: { address: { kind: 'session', sessionId }, throughSeq: proj?.asOfSeq ?? 0 },
    })
    records = page?.records ?? []
    if (records.some((it) => (it?.event ?? it)?.type === 'turn/end')) { done = true; break }
  } catch { /* 游标竞态,重试 */ }
}
if (done) pass('主会话 turn 已结束')
else fail('420s 内主会话未结束')

// 汇总
const events = records.map((it) => it?.event ?? it)
const text = events
  .filter((e) => e?.type === 'assistant/message')
  .flatMap((e) => e?.data?.message?.content ?? [])
  .filter((b) => b?.type === 'text')
  .map((b) => b.text)
  .join('\n')

console.log('\n[4] 三路派生判据')
// 子会话:测试后新出现、且 parentSessionId === sessionId
const after = await rpc(origin, cookie, 'session/list', { _request: {} })
const children = (after.items ?? []).filter(
  (r) => !beforeIds.has(r.sessionId) && r.parentSessionId === sessionId,
)
const childIds = (after.items ?? []).filter((r) => !beforeIds.has(r.sessionId)).map((r) => r.sessionId)
console.log(`  会话总数 ${beforeIds.size} → ${(after.items ?? []).length};新增 ${childIds.length} 个`)
for (const cid of childIds) {
  const row = (after.items ?? []).find((r) => r.sessionId === cid)
  console.log(`    子会话 ${cid}  parent=${row?.parentSessionId ?? '(无)'}  blank=${row?.blank}`)
}

if (children.length >= 3) pass(`派生了 ${children.length} 个独立子会话(≥3,三路隔离成立)`)
else if (children.length > 0) fail(`只派生了 ${children.length} 个子会话(期望 ≥3)`)
else fail('没有派生任何子会话 — 三路隔离未触发')

// 事件流里 subagent 工具调用证据
const subagentCalls = events.filter((e) => JSON.stringify(e).includes('subagent'))
if (subagentCalls.length > 0) pass(`事件流含 ${subagentCalls.length} 条 subagent 相关记录`)
else console.log('  INFO  事件流无 subagent 记录(可能工具名不同)')

console.log('\n[5] 输出协议判据')
if (/\[JEV:\s*3\/3 Independent Consensus\]/i.test(text)) pass('状态标识 = [JEV: 3/3 Independent Consensus]')
else if (/\[JEV:\s*2\/3 Majority Consensus\]/i.test(text)) pass('状态标识 = [JEV: 2/3 Majority Consensus]')
else if (/\[JEV:\s*Rerank Pick/i.test(text)) pass('状态标识 = [JEV: Rerank Pick ...]')
else if (/\[JEV:\s*Fast-Pass\]/i.test(text)) fail('走了 Fast-Pass — 高危任务未被强制三路(协议违背)')
else if (/\[JEV:/.test(text)) pass('含 JEV 状态标识(未识别具体档位)')
else fail('不含任何 [JEV: ...] 标识')

console.log('\n--- 回复摘录(前 1200 字符)---')
console.log(text.slice(0, 1200))
console.log('--- 结束 ---')

console.log('\n' + '='.repeat(58))
if (fails.length > 0) {
  console.log(`三路隔离测试失败:${fails.length} 项`)
  fails.forEach((f) => console.log(`  - ${f}`))
  process.exit(1)
}
console.log('JEV 三路隔离测试全部通过 — 真·独立上下文派生已确认')
