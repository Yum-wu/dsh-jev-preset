#!/usr/bin/env node
/**
 * dsh-jev-preset 端到端冒烟测试
 *
 * 验证 JEV 预设已在运行中的 DSH 里成功注册、可被 roster 读取、且可无缝切换。
 * 独立运行,零依赖(只用 node: 内置模块 + 全局 fetch)。
 *
 * 用法:
 *   node smoke.mjs
 *
 * 退出码:0 = 全部通过;1 = 有失败项。
 *
 * 前置:DSH web 正在运行(~/.dsh/web-url.txt 存在且未过期)。
 * 说明:本脚本只读 roster + 短暂切换默认预设后恢复原值,不写任何持久配置以外的东西。
 */
import { readFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'

const PRESET_ID = 'jev'
const PRESET_NAME = 'JEV 自适应交叉验证'
const HOME = join(homedir(), '.dsh')
const URL_FILE = join(HOME, 'web-url.txt')

const fails = []
const pass = (m) => console.log(`  PASS  ${m}`)
const fail = (m) => { fails.push(m); console.log(`  FAIL  ${m}`) }

// ── 读取运行中的服务地址与 token ────────────────────────────────────────────
function readBase() {
  let text
  try {
    text = readFileSync(URL_FILE, 'utf8')
  } catch {
    throw new Error(`找不到 ${URL_FILE} — DSH web 未在运行?`)
  }
  const line = text.split(/\r?\n/).find((l) => l.startsWith('url='))
  if (line === undefined) throw new Error(`${URL_FILE} 中没有 url= 行`)
  const url = new URL(line.slice(4))
  const token = url.searchParams.get('token')
  if (token === null) throw new Error(`${URL_FILE} 的 url 缺少 token 参数`)
  return { origin: url.origin, token }
}

// ── 用启动 token 换取签名会话 cookie ────────────────────────────────────────
async function authenticate(origin, token) {
  const response = await fetch(`${origin}/?token=${encodeURIComponent(token)}`, { redirect: 'manual' })
  if (response.status !== 303) throw new Error(`token 换取 cookie 失败: HTTP ${response.status}(DSH 可能已重启,token 已轮换)`)
  const setCookie = response.headers.getSetCookie?.() ?? []
  if (setCookie.length === 0) throw new Error('token 换取 cookie 失败: 响应没有 Set-Cookie')
  return setCookie.map((c) => c.split(';')[0]).join('; ')
}

// ── 调用 typert Remote 端点 ─────────────────────────────────────────────────
async function callRpc(origin, cookie, endpoint, args = {}) {
  const body = JSON.stringify({
    type: 'client-request',
    rpcId: crypto.randomUUID(),
    method: endpoint,
    payload: { args },
  })
  const response = await fetch(`${origin}/api/${endpoint}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', cookie },
    body,
  })
  if (!response.ok) throw new Error(`${endpoint} → HTTP ${response.status}`)
  const json = await response.json()
  if (json.result?.ok !== true) {
    throw new Error(`${endpoint} → ${json.result?.error?.code}: ${json.result?.error?.message}`)
  }
  return json.result.value
}

// ── 主流程 ──────────────────────────────────────────────────────────────────
const { origin, token } = readBase()
console.log(`\nJEV 预设冒烟测试`)
console.log(`服务: ${origin}`)

const cookie = await authenticate(origin, token)
console.log(`鉴权: 签名 cookie 已获取\n`)

console.log('[1] roster 中出现 jev')
const roster = await callRpc(origin, cookie, 'agentPresets/list')
const presets = roster.presets ?? []
const jev = presets.find((p) => p.id === PRESET_ID)
if (jev === undefined) {
  fail(`roster 中没有 id=${PRESET_ID};当前: ${presets.map((p) => p.id).join(', ')}`)
} else {
  pass(`id=${jev.id} 在册`)
  if (jev.name === PRESET_NAME) pass(`显示名 = ${jev.name}`)
  else fail(`显示名不符: 期望 "${PRESET_NAME}",实际 "${jev.name}"`)
  if (typeof jev.description === 'string' && jev.description.length > 0) pass('description 非空')
  else fail('description 为空')
  if (jev.order === 5) pass(`order = ${jev.order}`)
  else fail(`order 不符: 期望 5,实际 ${jev.order}`)
}

console.log('\n[2] 激活无诊断错误(broken 字段必须不存在)')
if (jev === undefined) {
  fail('无法检查:jev 不在册')
} else if (Object.hasOwn(jev, 'broken')) {
  fail(`激活报错: ${jev.broken}`)
} else {
  pass('broken 字段不存在 — 全部行激活成功')
}

console.log('\n[3] 声明文档可读(read 端点)')
try {
  const doc = await callRpc(origin, cookie, 'agentPresets/read', { agentPreset: PRESET_ID })
  if (typeof doc.content !== 'string' || doc.content.length === 0) fail('read 返回空 content')
  else pass(`content 可读(${doc.content.length} 字符)`)
  const rows = (doc.content.match(/^\s*-\s+id:/gm) ?? []).length
  if (rows > 0) pass(`声明含 ${rows} 个顶层插件行`)
  else fail('声明文档中没有插件行')
  for (const needle of ['dsh-persona', 'dsh-tool-subagent']) {
    if (doc.content.includes(needle)) pass(`声明含 ${needle}(三路隔离能力)`)
    else fail(`声明缺少 ${needle}`)
  }
} catch (error) {
  fail(`read 失败: ${error.message}`)
}

console.log('\n[4] 可无缝切换(切换后 isDefault 变化,再恢复)')
let original = null
try {
  original = (presets.find((p) => p.isDefault) ?? {}).id ?? null
  if (original === null) fail('无法确定切换前的默认预设')
  else {
    if (original === PRESET_ID) {
      // 已经是默认:切到 standard 再切回,验证双向
      await callRpc(origin, cookie, 'settings/update', {
        ns: 'agent-preset-registry',
        patch: { selectedDefault: 'standard' },
      })
    }
    await callRpc(origin, cookie, 'settings/update', {
      ns: 'agent-preset-registry',
      patch: { selectedDefault: PRESET_ID },
    })
    const after = await callRpc(origin, cookie, 'agentPresets/list')
    const active = (after.presets ?? []).find((p) => p.isDefault)
    if (active?.id === PRESET_ID) pass(`已切换到 ${PRESET_ID}`)
    else fail(`切换未生效: 当前默认 = ${active?.id}`)
  }
} catch (error) {
  fail(`切换失败: ${error.message}`)
} finally {
  if (original !== null) {
    try {
      await callRpc(origin, cookie, 'settings/update', {
        ns: 'agent-preset-registry',
        patch: { selectedDefault: original },
      })
      const restored = await callRpc(origin, cookie, 'agentPresets/list')
      const now = (restored.presets ?? []).find((p) => p.isDefault)
      if (now?.id === original) pass(`已恢复原默认预设 ${original}`)
      else fail(`恢复失败: 期望 ${original},实际 ${now?.id}`)
    } catch (error) {
      fail(`恢复原默认预设失败: ${error.message}`)
    }
  }
}

// ── 汇总 ────────────────────────────────────────────────────────────────────
console.log('\n' + '='.repeat(58))
if (fails.length > 0) {
  console.log(`冒烟测试失败:${fails.length} 项`)
  fails.forEach((f) => console.log(`  - ${f}`))
  process.exit(1)
}
console.log('冒烟测试全部通过 — JEV 预设已在 Web「设置 → Agent 预设」中展示且可无缝切换')
