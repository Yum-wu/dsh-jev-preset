#!/usr/bin/env node
/**
 * JEV 准确率基准运行器:对题集逐题开真实 DSH 会话,把最终回复写入 runs.jsonl,供 jevbench 判分。
 *
 * 用法:
 *   node benchmarks/accuracy/run-bench.mjs --suite suite.jsonl --out runs.jsonl \
 *        --config C1 --config C3 [--reps 1] [--limit N] [--only tick,vwap] \
 *        [--provider opencodex --model combo/ds-flash --effort high] [--timeout 900] [--dry-run]
 *
 * 配置:
 *   C0 = standard 预设 + 「单次直答」约束       (纯推理基线)
 *   C1 = standard 预设 + 「单路可执行代码」约束  (PAL 式基线,最关键的对照)
 *   C3 = jev 预设,无额外约束                    (被测对象)
 *
 * 可验证性:
 *   - 每行记录 session_id,可在 Web 侧栏或 tools/dump-three-path.mjs 复查原始对话
 *   - 断点续跑:已无错完成的 (case,config,rep) 跳过;失败行保留并重跑
 *   - 运行失败(RATE_LIMIT/超时)写 error 字段,判分时计为错并单列,不静默丢弃
 *
 * ⚠ 消耗真实 token。先 --dry-run 看计划,再 --limit 3 小跑。
 */
import { appendFileSync, existsSync, mkdirSync, readFileSync } from 'node:fs'
import { homedir, tmpdir } from 'node:os'
import { join } from 'node:path'
import { CONFIG_PREFIX, doneKeys, lastTurn, parseArgs } from './runner-lib.mjs'

const args = parseArgs(process.argv.slice(2), ['config'])
const SUITE = args.suite
const OUT = args.out
const CONFIGS = args.config ?? ['C1', 'C3']
const REPS = Number(args.reps ?? 1)
const TIMEOUT_MS = Number(args.timeout ?? 900) * 1000
const PRESET = { C0: 'standard', C1: 'standard', C3: 'jev' }

if (!SUITE || !OUT) {
  console.error('必须提供 --suite 与 --out')
  process.exit(2)
}
for (const c of CONFIGS) if (!(c in PRESET)) { console.error(`未知配置 ${c},可选 ${Object.keys(PRESET)}`); process.exit(2) }
if ((args.provider === undefined) !== (args.model === undefined)) { console.error('--provider 与 --model 必须同时给出'); process.exit(2) }

let suite = readFileSync(SUITE, 'utf8').split(/\r?\n/).filter(Boolean).map((l) => JSON.parse(l))
if (args.only) { const keep = new Set(String(args.only).split(',')); suite = suite.filter((c) => keep.has(c.category)) }
if (args.limit) suite = suite.slice(0, Number(args.limit))
const done = existsSync(OUT) ? doneKeys(readFileSync(OUT, 'utf8').split(/\r?\n/)) : new Set()
const plan = []
for (const c of suite) for (const cfg of CONFIGS) for (let rep = 0; rep < REPS; rep++) {
  if (!done.has(`${c.id}|${cfg}|${rep}`)) plan.push({ c, cfg, rep })
}
console.log(`题 ${suite.length} × 配置 ${CONFIGS.join('/')} × 重复 ${REPS};已完成 ${done.size},待跑 ${plan.length}`)
if (args['dry-run']) { plan.slice(0, 10).forEach((p) => console.log(`  ${p.cfg} ${p.c.id} rep${p.rep}`)); process.exit(0) }

// ── DSH RPC(与 session-test.mjs 同一套 wire 契约)──────────────────────────
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

/** 会话及其全部子代理会话的 token 合计(三路成本必须算上子代理)。 */
async function sumTokens(sessionId) {
  const list = await rpc('session/list', { _request: {} })
  let total = 0
  let children = 0
  for (const s of list.items ?? []) {
    if (s.sessionId !== sessionId && s.parentSessionId !== sessionId) continue
    const tu = s.projections?.values?.tokenUsage ?? {}
    total += (tu.uncachedInputTokens ?? 0) + (tu.cacheReadTokens ?? 0) + (tu.outputTokens ?? 0)
    if (s.parentSessionId === sessionId) children++
  }
  return { total, children }
}

async function runOne({ c, cfg, rep }) {
  const started = Date.now()
  const cwd = join(tmpdir(), 'jevbench', `${c.id}-${cfg}-${rep}`)
  mkdirSync(cwd, { recursive: true })
  const row = { case_id: c.id, config: cfg, rep, session_id: null }
  try {
    const created = await rpc('session/create', { request: { agentPreset: PRESET[cfg], cwd } })
    row.session_id = created.sessionId
    if (created.agentPreset !== PRESET[cfg]) throw new Error(`预设未绑定: ${created.agentPreset}`)
    if (args.provider) {
      await rpc('session/selectModel', { request: { sessionId: row.session_id, provider: args.provider, model: args.model,
        ...(args.effort ? { reasoningEffort: args.effort } : {}) } })
    }
    await rpc('session/prompt', { request: { sessionId: row.session_id, requestId: crypto.randomUUID(), mode: 'queue',
      content: [{ type: 'text', text: CONFIG_PREFIX[cfg] + c.question }] } })
    let last = { ended: false }
    while (Date.now() - started < TIMEOUT_MS) {
      await sleep(5000)
      const proj = await rpc('session/projections', { request: { sessionId: row.session_id } })
      const page = await rpc('session/page', { request: { address: { kind: 'session', sessionId: row.session_id }, throughSeq: proj.asOfSeq } })
      last = lastTurn(page.records ?? [])
      if (last.ended) {
        row.route_model = proj.values?.modelSelection?.lastUsed ?? null
        break
      }
    }
    row.text = last.text ?? ''
    row.end_reason = last.endReason ?? null
    if (!last.ended) row.error = `timeout ${TIMEOUT_MS / 1000}s`
    else if (last.endReason !== 'completed') row.error = `turn/end ${last.endReason}`
    const t = await sumTokens(row.session_id)
    row.tokens = t.total
    row.subagents = t.children
  } catch (e) {
    row.error = String(e.message ?? e)
  }
  row.elapsed_ms = Date.now() - started
  appendFileSync(OUT, JSON.stringify(row) + '\n')
  return row
}

for (const [i, p] of plan.entries()) {
  const r = await runOne(p)
  console.log(`[${i + 1}/${plan.length}] ${p.cfg} ${p.c.id} rep${p.rep} ${r.error ? 'ERR ' + r.error : 'ok'} ` +
    `${(r.elapsed_ms / 1000).toFixed(0)}s tok=${r.tokens ?? '-'} sub=${r.subagents ?? '-'} sid=${r.session_id}`)
}
console.log(`完成。判分:cd benchmarks/accuracy && python -m jevbench grade --suite <suite> --runs <runs>`)
