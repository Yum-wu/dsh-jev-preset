#!/usr/bin/env node
/**
 * launch-long-goal.mjs
 *
 * 启动 JEV 模式长程自优化目标会话:
 * 1. RPC 创建全新独立会话 (agentPreset = 'jev')
 * 2. 从 docs/ 的正典提示词文件读出 objective(单一真源,不在脚本里重复)
 * 3. 经 commands/execute 字面下发 /goal(服务端直解析,不经模型转述)
 * 4. 记录会话元数据,输出监控入口
 *
 * 用法:
 *   node tools/launch-long-goal.mjs --dry-run    # 只打印将要下发的 objective 与校验结果
 *   node tools/launch-long-goal.mjs              # 真实创建会话并下发
 */

import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'node:fs'
import { homedir } from 'node:os'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const HOME = join(homedir(), '.dsh')
const URL_FILE = join(HOME, 'web-url.txt')
const TARGET_PRESET = 'jev'
const HERE = dirname(fileURLToPath(import.meta.url))
const PLUGIN_ROOT = join(HERE, '..')

// ── objective 的唯一真源 ───────────────────────────────────────────────────
// 提示词正文维护在 docs/ 下的 Markdown 里(带设计依据与附录),脚本只负责取正文。
// 历史教训(2026-09-28):上一版把 objective 硬编码在脚本里、且经 session/prompt
// 纯文本下发,模型收到后自行概括、丢掉时长与举证约束,首轮干完即 complete
// (roundsStarted=0)。本版两条都修:①单一真源 ②走 commands/execute 字面入库。
export const OBJECTIVE_DOC = join(PLUGIN_ROOT, 'docs', 'goal-prompt-self-optimize-20261001.md')
export const OBJECTIVE_ANCHOR = '## 一、提示词正文'

/** 从正典 Markdown 中抽出第一个 ``` 围栏代码块作为 objective。 */
export function loadObjective(docPath = OBJECTIVE_DOC) {
  if (!existsSync(docPath)) throw new Error(`找不到正典提示词文件: ${docPath}`)
  const text = readFileSync(docPath, 'utf8')
  const anchorAt = text.indexOf(OBJECTIVE_ANCHOR)
  if (anchorAt < 0) throw new Error(`提示词文件缺少锚点 "${OBJECTIVE_ANCHOR}"`)
  const fenceAt = text.indexOf('```', anchorAt)
  if (fenceAt < 0) throw new Error('锚点之后没有找到 ``` 代码块')
  const bodyAt = text.indexOf('\n', fenceAt) + 1
  const endAt = text.indexOf('```', bodyAt)
  if (endAt < 0) throw new Error('代码块未闭合')
  return text.slice(bodyAt, endAt).trim()
}

/** 下发前的自检:objective 必须带齐关键约束,否则拒绝下发(防止再次被压缩丢约束)。 */
export function checkObjective(objective) {
  const required = [
    ['禁止提前 complete', /严禁\s*complete|禁止调用\s*update_goal\(complete\)/],
    ['轮次下限', /Round\s*<\s*20/],
    ['红线(R15)', /R15/],
    ['验证者外置(R12)', /R12/],
    ['指标外置(R13)', /R13/],
    ['每轮状态行', /ROUND\s*n\s*\|/],
    ['停止条件', /停止条件/],
    ['附录 A', /附录\s*A/],
  ]
  return required.map(([label, re]) => ({ label, ok: re.test(objective) }))
}

function readBase() {
  const text = readFileSync(URL_FILE, 'utf8')
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

// ⚠️ 旧模板（2026-09-28 已弃用，作为失败教训留底，正文已移入
// plugins/dsh-jev-preset/docs/legacy-goal-prompt.md）。要点：经 session/prompt
// 下发 → 模型自行 create_goal 概括 → 丢失时长与举证约束 → roundsStarted=0。

async function main() {
  const dryRun = process.argv.includes('--dry-run')
  const objective = loadObjective()

  console.log(`[0] objective 来源: ${OBJECTIVE_DOC}`)
  console.log(`    长度: ${objective.length} 字符 / ${objective.split(/\r?\n/).length} 行`)

  const checks = checkObjective(objective)
  for (const c of checks) console.log(`    ${c.ok ? '✅' : '❌'} ${c.label}`)
  const failed = checks.filter((c) => !c.ok)
  if (failed.length > 0) {
    console.error(`\n下发前自检未通过: ${failed.map((c) => c.label).join(', ')}`)
    process.exit(2)
  }

  if (dryRun) {
    console.log('\n--- objective 全文(将字面下发,不经模型转述)---')
    console.log(objective)
    console.log('--- 全文结束 ---')
    console.log('\n[dry-run] 未创建会话、未下发 goal。去掉 --dry-run 即真实执行。')
    return
  }

  const { origin, token } = readBase()
  const cookie = await authenticate(origin, token)

  console.log(`\n[1] 向 ${origin} 请求创建专属 JEV 自优化会话...`)
  const created = await rpc(origin, cookie, 'session/create', {
    request: {
      agentPreset: TARGET_PRESET,
      cwd: PLUGIN_ROOT,
    },
  })

  const sessionId = created.sessionId
  console.log(`[2] 会话创建成功: ${sessionId}`)
  console.log(`    绑定预设: ${created.agentPreset}`)

  const stateDir = join(HOME, 'jev-session-test')
  mkdirSync(stateDir, { recursive: true })
  const statePath = join(stateDir, 'active-self-optimize-goal.json')
  writeFileSync(statePath, JSON.stringify({
    sessionId,
    preset: created.agentPreset,
    startedAt: new Date().toISOString(),
    objectiveDoc: OBJECTIVE_DOC,
    objectiveChars: objective.length,
    prompt: objective,
  }, null, 2))

  console.log('[3] 经 commands/execute 下发 /goal(服务端直解析,不经模型转述)...')
  const goalResult = await rpc(origin, cookie, 'commands/execute', {
    agentId: sessionId,
    line: `/goal ${objective}`,
    submittedAttachments: [],
  })
  console.log(`  /goal 返回: ${JSON.stringify(goalResult).slice(0, 240)}`)

  console.log('\n[4] 目标已入库,将由 goal 轮次驱动器自动续跑。')
  console.log(`    会话 ID: ${sessionId}`)
  console.log(`    状态档案: ${statePath}`)
  console.log(`    Web 访问: ${origin}/?token=${token}#session=${sessionId}`)
  console.log('    监控命令: node tools/monitor-long-goal.mjs')
}

// 仅在被直接执行时运行 main(便于单测 import 上面的纯函数)。
if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  main().catch(err => {
    console.error('启动长程目标失败:', err)
    process.exit(1)
  })
}
