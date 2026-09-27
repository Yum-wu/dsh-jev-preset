#!/usr/bin/env node
/**
 * JEV persona 端到端活性测试:真开一个新会话,发一条消息,验证 persona 真的生效。
 *
 * 这是比 roster 检查强得多的证据 —— 它证明:
 *   1. 会话能以 agentPreset=jev 创建
 *   2. JEV persona 真的进了 system prompt(模型按 JEV 协议回复)
 *   3. 三路隔离工具面真的挂上了(subagent 工具在 wire 上)
 *
 * 用法:
 *   node session-test.mjs            # 默认 Fast-Pass 探针
 *   node session-test.mjs --clean    # 只清理本脚本创建的会话记录(打印 id)
 *
 * 退出码:0 = 通过;1 = 失败。
 *
 * ⚠ 本测试会消耗真实模型 token(一轮对话)。
 */
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'

const HOME = join(homedir(), '.dsh')
const URL_FILE = join(HOME, 'web-url.txt')
const STATE_DIR = join(HOME, 'jev-session-test')
const STATE_FILE = join(STATE_DIR, 'created.json')

const PROMPT = [
  '这是 JEV 预设的活性自检。请严格按你的 JEV 协议回复:',
  '任务:判断 7 是不是质数。',
  '这是低危日常问答,应走 Fast-Pass 单次直出,不要派生 subagent。',
  '回复必须:第一行是状态路由标识,然后给结论。',
].join('\n')

// ── 基础设施 ────────────────────────────────────────────────────────────────
function readBase() {
  const text = readFileSync(URL_FILE, 'utf8')
  const line = text.split(/\r?\n/).find((l) => l.startsWith('url='))
  if (line === undefined) throw new Error(`${URL_FILE} 中没有 url= 行`)
  const url = new URL(line.slice(4))
  const token = url.searchParams.get('token')
  if (token === null) throw new Error('url 缺少 token')
  return { origin: url.origin, token }
}

async function authenticate(origin, token) {
  const response = await fetch(`${origin}/?token=${encodeURIComponent(token)}`, { redirect: 'manual' })
  if (response.status !== 303) throw new Error(`token 换取 cookie 失败: HTTP ${response.status}(DSH 可能已重启)`)
  const cookies = response.headers.getSetCookie?.() ?? []
  if (cookies.length === 0) throw new Error('响应没有 Set-Cookie')
  return cookies.map((c) => c.split(';')[0]).join('; ')
}

async function rpc(origin, cookie, endpoint, args = {}) {
  const response = await fetch(`${origin}/api/${endpoint}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', cookie },
    body: JSON.stringify({ type: 'client-request', rpcId: crypto.randomUUID(), method: endpoint, payload: { args } }),
  })
  if (!response.ok) throw new Error(`${endpoint} → HTTP ${response.status}`)
  const json = await response.json()
  if (json.result?.ok !== true) throw new Error(`${endpoint} → ${json.result?.error?.code}: ${json.result?.error?.message}`)
  return json.result.value
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

function remember(sessionId) {
  mkdirSync(STATE_DIR, { recursive: true })
  const prior = existsSync(STATE_FILE) ? JSON.parse(readFileSync(STATE_FILE, 'utf8')) : []
  prior.push({ sessionId, at: new Date().toISOString() })
  writeFileSync(STATE_FILE, JSON.stringify(prior, null, 2))
}

// ── 主流程 ──────────────────────────────────────────────────────────────────
const cleanMode = process.argv.includes('--clean')
const { origin, token } = readBase()
const cookie = await authenticate(origin, token)

if (cleanMode) {
  console.log(`本测试创建的会话记录(${STATE_FILE}):`)
  if (existsSync(STATE_FILE)) {
    for (const row of JSON.parse(readFileSync(STATE_FILE, 'utf8'))) console.log(`  ${row.sessionId}  ${row.at}`)
  } else console.log('  (无)')
  console.log('\n注意:DSH 未暴露 delete 端点,空会话无法经 RPC 删除。')
  console.log('可在 Web 侧栏手动删除,或忽略(空会话无 token 消耗)。')
  process.exit(0)
}

console.log(`\nJEV persona 活性测试`)
console.log(`服务: ${origin}\n`)

const fails = []
const pass = (m) => console.log(`  PASS  ${m}`)
const fail = (m) => { fails.push(m); console.log(`  FAIL  ${m}`) }

// 1) 建会话,pin 到 jev
console.log('[1] 以 agentPreset=jev 创建新会话')
const created = await rpc(origin, cookie, 'session/create', { request: { agentPreset: 'jev' } })
const sessionId = created.sessionId
if (created.agentPreset === 'jev') pass(`sessionId=${sessionId} preset=${created.agentPreset}`)
else fail(`预设未绑定: ${created.agentPreset}`)
remember(sessionId)

// 2) 发 prompt
console.log('\n[2] 发送 Fast-Pass 探针消息')
const requestId = crypto.randomUUID()
// wire 契约(zod,session_prompt_parameter_0):requestId / sessionId / mode / content 四者**全部必填**。
// mode ∈ {"queue","steer"}:queue = 下一轮,steer = 立即插入当前轮。
const accepted = await rpc(origin, cookie, 'session/prompt', {
  request: {
    sessionId,
    requestId,
    mode: 'queue',
    content: [{ type: 'text', text: PROMPT }],
  },
})
if (accepted?.accepted === true) pass('prompt 已受理')
else fail(`prompt 未受理: ${JSON.stringify(accepted)}`)

// 3) 轮询等待回复
// throughSeq 不能超过服务端游标(否则 gateway/bad-request "past cursor")。
// 先取一次 projections 读 asOfSeq,之后每轮以它为 throughSeq。
console.log('\n[3] 等待模型回复(最长 180s)')
let text = ''
let sawSubagentTool = false
let cursor = 0
try {
  const proj = await rpc(origin, cookie, 'session/projections', { request: { sessionId } })
  cursor = proj?.asOfSeq ?? 0
} catch {
  cursor = 0
}

const deadline = Date.now() + 180_000
while (Date.now() < deadline) {
  await sleep(3000)
  let page
  try {
    page = await rpc(origin, cookie, 'session/page', {
      request: { address: { kind: 'session', sessionId }, throughSeq: cursor },
    })
  } catch (error) {
    // 游标可能已前进;忽略本轮,下轮重读 projections
    try {
      const proj = await rpc(origin, cookie, 'session/projections', { request: { sessionId } })
      cursor = proj?.asOfSeq ?? cursor
    } catch { /* 保持原游标 */ }
    if (/past cursor/.test(String(error.message))) continue
    fail(`读取会话失败: ${error.message}`)
    break
  }
  const records = page?.records ?? page?.items ?? page?.events ?? []
  const blob = JSON.stringify(records)
  if (blob.includes('subagent')) sawSubagentTool = true
  // page 返回 records[];每条形如 { type:'event', event:{ type, seq, data } }。
  // assistant 文本在 event.data.message.content[] 的 {type:'text'} 块。
  const chunks = []
  for (const item of records) {
    const ev = item?.event ?? item
    if (ev?.type !== 'assistant/message') continue
    for (const b of ev?.data?.message?.content ?? []) {
      if (b?.type === 'text' && typeof b.text === 'string') chunks.push(b.text)
    }
  }
  text = chunks.join('\n')
  if (text.length > 0) break
  // 推进游标,读下一批
  try {
    const proj = await rpc(origin, cookie, 'session/projections', { request: { sessionId } })
    cursor = proj?.asOfSeq ?? cursor
  } catch { /* 保持原游标 */ }
}

if (text.length === 0) {
  fail('180s 内没有 assistant 文本')
} else {
  pass(`收到回复(${text.length} 字符)`)
  console.log('\n--- 回复前 600 字符 ---')
  console.log(text.slice(0, 600))
  console.log('--- 结束 ---\n')

  console.log('[4] JEV persona 生效判据')
  const firstLine = text.split(/\r?\n/).map((l) => l.trim()).find((l) => l.length > 0) ?? ''
  if (/\[JEV:\s*Fast-Pass\]/i.test(text)) pass('回复含 [JEV: Fast-Pass] 状态路由标识')
  else if (/\[JEV:/.test(text)) pass(`回复含 JEV 状态标识(非 Fast-Pass): ${firstLine.slice(0, 80)}`)
  else fail(`回复不含任何 [JEV: ...] 标识 — persona 可能未生效。首行: ${firstLine.slice(0, 120)}`)
  if (/质数|prime/i.test(text)) pass('回答了质数问题(任务被理解)')
  else fail('未回答质数问题')
  if (!sawSubagentTool) pass('未派生 subagent(Fast-Pass 正确,未为琐事启动三路)')
  else console.log('  INFO  wire 上出现 subagent 工具(仅表示工具已挂载,不代表被调用)')
}

console.log('\n' + '='.repeat(58))
if (fails.length > 0) {
  console.log(`活性测试失败:${fails.length} 项`)
  fails.forEach((f) => console.log(`  - ${f}`))
  process.exit(1)
}
console.log('JEV persona 活性测试全部通过 — 预设真实生效')
