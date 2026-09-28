#!/usr/bin/env node
/**
 * audit-subagent-cost.mjs
 *
 * 统计 JEV 三路子会话的成本与耗时,按路由(provider/model)聚合。
 *
 * 动机(2026-09-28):引入异构模型路由后,三路跑在不同模型上,单价与延迟都不同。
 * 「三路成本高」是 persona 里的既有判断,但没有量化依据 —— 本工具把它变成数字,
 * 使路由分配策略(哪一路该用贵模型)可被数据检验,而非凭感觉。
 *
 * 用法:
 *   node tools/audit-subagent-cost.mjs [--limit N] [--json]
 *
 * 数据来源:session/list 的 projections.values
 *   - tokenUsage.{uncachedInputTokens, outputTokens, cacheReadTokens}
 *   - sessionStats.{turns, steps, llmMs, toolMs, decodeTokens}
 *   - modelSelection.lastUsed.{provider, model}
 * 退出码:恒为 0(纯审计,不做门禁)。
 */
import { readFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'

const HOME = join(homedir(), '.dsh')
const URL_FILE = join(HOME, 'web-url.txt')

const argv = process.argv.slice(2)
const LIMIT = (() => {
  const i = argv.indexOf('--limit')
  return i >= 0 ? Number(argv[i + 1]) || 30 : 30
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

const fmt = (n) => (n ?? 0).toLocaleString('en-US')

function main() {
  return (async () => {
    const { origin, token } = readBase()
    const cookie = await authenticate(origin, token)
    const list = await rpc(origin, cookie, 'session/list', { _request: {} })
    const kids = (list.items ?? [])
      .filter((s) => s.origin === 'subagent')
      .sort((a, b) => (b.updatedAt ?? 0) - (a.updatedAt ?? 0))
      .slice(0, LIMIT)

    const rows = kids.map((s) => {
      const v = s.projections?.values ?? {}
      const tu = v.tokenUsage ?? {}
      const st = v.sessionStats ?? {}
      const route = v.modelSelection?.lastUsed ?? {}
      return {
        sessionId: s.sessionId,
        route: route.provider && route.model ? `${route.provider}/${route.model}` : '(未记录)',
        effort: route.reasoningEffort ?? '-',
        inTok: tu.uncachedInputTokens ?? 0,
        outTok: tu.outputTokens ?? 0,
        cacheTok: tu.cacheReadTokens ?? 0,
        llmMs: st.llmMs ?? 0,
        toolMs: st.toolMs ?? 0,
        turns: st.turns ?? 0,
        steps: st.steps ?? 0,
        title: (v.title ?? '').slice(0, 34),
      }
    })

    // 按路由聚合
    const byRoute = new Map()
    for (const r of rows) {
      const a = byRoute.get(r.route) ?? { route: r.route, count: 0, inTok: 0, outTok: 0, cacheTok: 0, llmMs: 0, toolMs: 0, steps: 0 }
      a.count++
      a.inTok += r.inTok; a.outTok += r.outTok; a.cacheTok += r.cacheTok
      a.llmMs += r.llmMs; a.toolMs += r.toolMs; a.steps += r.steps
      byRoute.set(r.route, a)
    }
    const agg = [...byRoute.values()].sort((a, b) => b.count - a.count)

    const total = rows.reduce((a, r) => ({
      inTok: a.inTok + r.inTok, outTok: a.outTok + r.outTok, cacheTok: a.cacheTok + r.cacheTok,
      llmMs: a.llmMs + r.llmMs, steps: a.steps + r.steps,
    }), { inTok: 0, outTok: 0, cacheTok: 0, llmMs: 0, steps: 0 })

    if (AS_JSON) {
      console.log(JSON.stringify({ sampled: rows.length, total, byRoute: agg, rows }, null, 2))
      return
    }

    console.log(`\n=== 子代理成本审计(最近 ${rows.length} 个)===`)
    console.log('\n[按路由聚合]')
    console.log('  路由                                        会话  输入tok    输出tok    缓存tok     LLM秒   步骤')
    for (const a of agg) {
      console.log(`  ${a.route.padEnd(42)} ${String(a.count).padStart(4)}  ${fmt(a.inTok).padStart(9)}  ${fmt(a.outTok).padStart(9)}  ${fmt(a.cacheTok).padStart(10)}  ${(a.llmMs / 1000).toFixed(1).padStart(7)}  ${String(a.steps).padStart(5)}`)
    }
    console.log(`  ${'合计'.padEnd(42)} ${String(rows.length).padStart(4)}  ${fmt(total.inTok).padStart(9)}  ${fmt(total.outTok).padStart(9)}  ${fmt(total.cacheTok).padStart(10)}  ${(total.llmMs / 1000).toFixed(1).padStart(7)}  ${String(total.steps).padStart(5)}`)

    console.log('\n[逐会话明细]')
    for (const r of rows.slice(0, 15)) {
      console.log(`  ${r.sessionId.slice(0, 20)}  ${r.route.padEnd(34)} in=${fmt(r.inTok).padStart(7)} out=${fmt(r.outTok).padStart(6)} llm=${(r.llmMs / 1000).toFixed(1).padStart(6)}s  ${r.title}`)
    }

    console.log('\n[路由分布]')
    for (const a of agg) {
      const pct = ((a.count / rows.length) * 100).toFixed(0)
      console.log(`  ${a.route}  ${a.count}/${rows.length} (${pct}%)`)
    }
    if (agg.length === 1 && rows.length >= 3) {
      console.log('\n提示: 全部子会话走同一路由 → 未启用异构路由(见 cordis.patch.yml §3.3),存在并发限流风险。')
    }
  })()
}

main().catch((e) => { console.error('审计失败:', e.message); process.exit(2) })
