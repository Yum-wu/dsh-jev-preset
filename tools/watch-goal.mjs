#!/usr/bin/env node
/**
 * watch-goal.mjs — JEV 长程自优化目标的**限流看护**。
 *
 * 做什么:
 *   1. 周期性读目标会话的 `modelSelection` 与子代理结算状态;
 *   2. 检出「限流」(429 / RATE_LIMIT / 重试耗尽)时,按用户指定的降级链换模型:
 *        当前 → opencodex/opencode-zen/space-bunny-free
 *             → opencodex/google-antigravity/gemini-3.8-flash
 *             → opencodex/combo/ds-flash
 *   3. 每次换挡都写日志,换挡后进入冷却期再判定(避免刚换就误判再换)。
 *
 * 设计依据(本机实测,非推测):
 *   - 限流的判据必须来自**客观状态**,不能靠"文本看起来卡住了":
 *     · 子会话日志里的 `llm/retry` / `assistant/attempt` 的 failure.code 含 RATE_LIMIT
 *       (见 audit-subagent-settlement.mjs,该工具曾因结构路径写错产生假阴性,已修);
 *     · 主会话最近一条 `turn/end` 的 reason.kind === 'error' 且 code 含 RATE_LIMIT。
 *   - 「换模型」走官方 `session/selectModel`(schema: {sessionId, provider, model, reasoningEffort?}),
 *     不手动改配置 —— 手动改配置需要重启 DSH,属红线。
 *   - 免费档并发三路必挂(2026-09-28 实测:3/3 全部 429 + 6 次重试耗尽)。
 *
 * 用法:
 *   node tools/watch-goal.mjs --once            # 巡检一次,打表,不换挡
 *   node tools/watch-goal.mjs                   # 常驻看护,默认 60s 一轮,检出即换挡
 *   node tools/watch-goal.mjs --interval 30 --cooldown 180
 *
 * 退出码(仅在 --once 下有意义):
 *   0 = 无限流;1 = 检出限流;2 = 执行出错
 */
import { readFileSync, existsSync, appendFileSync, mkdirSync } from 'node:fs'
import { homedir } from 'node:os'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createRequire } from 'node:module'

const require_ = createRequire(import.meta.url)
const HOME = join(homedir(), '.dsh')
const URL_FILE = join(HOME, 'web-url.txt')
const SESSIONS_DIR = join(HOME, 'sessions')
const HERE = dirname(fileURLToPath(import.meta.url))

const STATE_CANDIDATES = [
  join(HOME, 'jev-session-test', 'active-self-optimize-goal.json'),
  join(HOME, 'jev-session-test', 'active-long-goal.json'),
]
const LOG_DIR = join(HOME, 'jev-session-test')

// ── 降级链(用户 2026-10-01 指定) ────────────────────────────────────────────
// 第一跳是 **openrouter** 通道的太空兔子(`openrouter/stealth/space-bunny-alpha`),
// 与当前默认的 `opencode-zen/space-bunny-free` 是**两个不同 provider 通道** ——
// 不能混为一谈(前者走 openrouter 上游,后者走 zen free-tier,限流域不同)。
// 第三跳 combo/ds-flash 是组合路由(付费档),2026-09-28 实测 9/9 并发无 429。
export const FALLBACK_CHAIN = [
  { provider: 'opencodex', model: 'openrouter/stealth/space-bunny-alpha', note: 'openrouter 太空兔子' },
  { provider: 'opencodex', model: 'google-antigravity/gemini-3.8-flash', note: 'Gemini 3.8' },
  { provider: 'opencodex', model: 'combo/ds-flash', note: 'combo/ds-flash(组合付费)' },
]

/** 链的入口:当前若已是链外模型,第一跳取链首。 */
export function firstHop(current, chain = FALLBACK_CHAIN) {
  if (!current?.model) return chain[0]
  return chain.some(c => c.model === current.model) ? null : chain[0]
}

function parseArgs(argv) {
  const out = {}
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (!a.startsWith('--')) continue
    const key = a.slice(2)
    const next = argv[i + 1]
    if (next !== undefined && !next.startsWith('--')) { out[key] = next; i++ }
    else out[key] = true
  }
  return out
}

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

/** 解压多帧 zstd 会话日志(与 audit-subagent-settlement.mjs 同法)。 */
function readSessionLog(sessionId) {
  try {
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
        try { chunks.push(require_('node:zlib').zstdDecompressSync(buf.subarray(offs[k], end)).toString('utf8')) }
        catch { /* 跳过损坏帧 */ }
      }
      return chunks.join('\n')
    }
  } catch { /* 目录不可读 */ }
  return null
}

/** 从一段会话日志里数限流证据。路径沿用已修对的结构:s.chunk.reason.failure。
 *
 * ⚠️ 2026-10-01 实测修正:不能把「历史上任何一次 429」当作正在限流。
 * 实测遇到的 429 是 `upstream_reset_replay_refused`(上游传输重置),
 * 重试 1 次即恢复、turn 以 `completed` 正常结束 —— 属瞬时抖动,已自愈。
 * 若据此换模型会**误伤正在正常推进的会话**。
 *
 * 故本函数返回「最近一次 turn」的窗口结果:
 *   - lastTurnHadRateLimit:最近一个 turn 内是否出现过 429
 *   - lastTurnEnd:最近一个 turn 的结束原因
 *   - 只有 (最近 turn 出现 429) 或 (最近 turn 以 error+RATE_LIMIT 结束)
 *     才构成"正在限流"的证据。
 */
function analyzeRecentTurn(logText) {
  const out = {
    retries: 0, rateLimit: 0, lastTurnEnd: null, lastTurn: null,
    lastTurnRateLimit: 0, maxTurn: 0, upstreamReset: 0,
  }
  const events = []
  for (const line of (logText ?? '').split(/\r?\n/)) {
    if (!line.trim()) continue
    let o
    try { o = JSON.parse(line) } catch { continue }
    events.push(o)
    const t = o.data?.turn
    if (typeof t === 'number' && t > out.maxTurn) out.maxTurn = t
  }
  for (const o of events) {
    const inLastTurn = o.data?.turn === out.maxTurn
    if (o.type === 'llm/retry' && inLastTurn) out.retries++
    if (o.type === 'assistant/attempt' && inLastTurn) {
      for (const s of o.data?.stream ?? []) {
        const f = s?.chunk?.reason?.failure
        const blob = `${f?.code ?? ''} ${f?.message ?? ''}`
        if (f && /RATE_LIMIT|rate_limit|429/i.test(blob)) {
          out.rateLimit++
          out.lastTurnRateLimit++
          // 上游重置型 429:属传输抖动,不是配额限流
          if (/upstream_reset_replay_refused|upstream exchange did not complete/i.test(blob)) out.upstreamReset++
        }
      }
    }
    if (o.type === 'turn/end') {
      out.lastTurn = o.data?.turn ?? out.lastTurn
      out.lastTurnEnd = o.data?.reason?.kind ?? null
    }
  }
  return out
}

/** 取当前会话在用的模型(modelSelection.next ?? lastUsed)。 */
function currentModel(proj) {
  const ms = proj?.values?.modelSelection
  return ms?.next ?? ms?.lastUsed ?? null
}

/** 在降级链里定位"下一跳"。
 *  - 当前在链上 → 取链中其后第一个不同的;
 *  - 当前不在链上(如默认的 opencode-zen/space-bunny-free)→ 取链首。
 */
export function nextHop(current, chain = FALLBACK_CHAIN) {
  if (!current?.model) return chain[0]
  const idx = chain.findIndex(c => c.model === current.model)
  if (idx < 0) return chain[0]
  for (let i = idx + 1; i < chain.length; i++) {
    if (chain[i].model !== current.model) return chain[i]
  }
  return null
}

async function main() {
  const args = parseArgs(process.argv.slice(2))
  const once = Boolean(args.once)
  const intervalMs = Number(args.interval ?? 60) * 1000
  const cooldownMs = Number(args.cooldown ?? 180) * 1000

  const statePath = STATE_CANDIDATES.find(p => existsSync(p))
  if (!statePath) { console.error('未找到活跃的长程任务记录'); process.exit(2) }
  const meta = JSON.parse(readFileSync(statePath, 'utf8'))
  const sessionId = meta.sessionId

  const { origin, token } = readBase()
  const cookie = await authenticate(origin, token)

  mkdirSync(LOG_DIR, { recursive: true })
  const logPath = join(LOG_DIR, 'watch-goal.log')
  const log = (msg) => {
    const line = `[${new Date().toISOString()}] ${msg}`
    console.log(line)
    try { appendFileSync(logPath, line + '\n', { encoding: 'utf8' }) } catch { /* 日志失败不影响主流程 */ }
  }

  log(`看护启动 session=${sessionId} once=${once} interval=${intervalMs / 1000}s cooldown=${cooldownMs / 1000}s`)
  log(`降级链: ${FALLBACK_CHAIN.map(c => `${c.model}(${c.note})`).join(' → ')}`)

  let lastSwitchAt = 0

  const tick = async () => {
    const proj = await rpc(origin, cookie, 'session/projections', { request: { sessionId } })
    const cur = currentModel(proj)
    const stats = proj?.values?.sessionStats
    // goal 状态走 goals/get(实测它返回完整 GoalView:phase/maxGoalRounds/activation);
    // projections.goal 只有 roundsStarted,字段不全。
    let goal = null
    try { goal = await rpc(origin, cookie, 'goals/get', { agentId: sessionId }) } catch { /* 无 goal */ }

    // 子会话限流证据:只看本会话派生的子代理。
    const list = await rpc(origin, cookie, 'session/list', { _request: {} })
    const kids = (list.items ?? []).filter(s => s.parentSessionId === sessionId)
    let kidRetries = 0, kidRateLimit = 0
    for (const k of kids) {
      const st = analyzeRecentTurn(readSessionLog(k.sessionId))
      kidRetries += st.retries
      kidRateLimit += st.rateLimit
    }
    // 主会话自身限流证据
    const self = analyzeRecentTurn(readSessionLog(sessionId))

    // 判定"正在限流" —— 只看最近一个 turn,且排除自愈的上游抖动。
    // 依据 2026-10-01 实测:`upstream_reset_replay_refused` 重试 1 次即恢复,
    // turn 仍以 completed 结束;把它当限流会误伤正常会话。
    const selfStuck = self.lastTurnEnd === 'error' && self.lastTurnRateLimit > 0
    const kidStuck = kidRateLimit > 0
    const rateLimited = selfStuck || kidStuck

    const line = `轮次=${goal?.roundsStarted ?? '?'}/${goal?.maxGoalRounds ?? '?'} `
      + `phase=${goal?.phase ?? '?'} act=${goal?.activation ?? '?'} `
      + `模型=${cur ? `${cur.provider}/${cur.model}` : '?'} `
      + `主(T${self.maxTurn} end=${self.lastTurnEnd ?? '-'} retry=${self.retries} 429=${self.rateLimit}`
      + `${self.upstreamReset > 0 ? ' [上游抖动×' + self.upstreamReset + ']' : ''}) `
      + `子${kids.length}路(retry=${kidRetries} 429=${kidRateLimit}) steps=${stats?.steps ?? '?'}`

    if (once) {
      console.log(`\n=== 限流巡检(单次)===`)
      console.log(`  会话: ${sessionId}`)
      console.log(`  ${line}`)
      console.log(`  判定: ${rateLimited ? '❌ 正在限流' : '✅ 无限流(历史 429 若已自愈则不计)'}`)
      const hop = nextHop(cur)
      console.log(`  下一跳: ${hop ? `${hop.provider}/${hop.model} (${hop.note})` : '链已到底'}`)
      process.exit(rateLimited ? 1 : 0)
    }

    log(line)

    if (rateLimited) {
      const sinceSwitch = Date.now() - lastSwitchAt
      if (sinceSwitch < cooldownMs) {
        log(`  检出限流,但距上次换挡仅 ${(sinceSwitch / 1000).toFixed(0)}s < 冷却 ${cooldownMs / 1000}s,跳过(让重试机制先跑)。`)
        return
      }
      const hop = nextHop(cur)
      if (!hop) {
        log(`  ⚠️ 检出限流但降级链已到底(${cur?.model}),不再换挡。建议人工介入:/goal pause。`)
        return
      }
      try {
        const res = await rpc(origin, cookie, 'session/selectModel', {
          request: { sessionId, provider: hop.provider, model: hop.model, reasoningEffort: 'high' },
        })
        lastSwitchAt = Date.now()
        log(`  🔁 换挡: ${cur?.model ?? '?'} → ${hop.model} (${hop.note});返回 ${JSON.stringify(res)}`)
      } catch (e) {
        log(`  ❌ 换挡失败: ${e.message}`)
      }
    }
  }

  if (once) { await tick(); return }

  // eslint-disable-next-line no-constant-condition
  while (true) {
    try { await tick() } catch (e) { log(`巡检出错: ${e.message}`) }
    await new Promise(r => setTimeout(r, intervalMs))
  }
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  main().catch(e => { console.error('看护失败:', e); process.exit(2) })
}
