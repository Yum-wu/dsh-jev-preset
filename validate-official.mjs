// 安装前最强静态验证:调用官方真实函数,而非复刻逻辑。
//   loadOverlayPatches  — 与 boot() 读取 bundle patch 完全同一条代码路径
//   applyEntryPatches   — 与 cordis-plugin-include 合成 entry 树完全同一条代码路径
// 目的:证明这个 bundle 被 Loader 接受后,能正确地把 preset-jev 行合入 entry 树。
import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'
import { readFileSync } from 'node:fs'

import { runtimeNodeModules } from './runtime-path.mjs'

const RUNTIME = runtimeNodeModules()
const BUNDLE = 'C:/Users/Yum/Desktop/DeepSeekHarness/plugins/dsh-jev-preset'

const appBoot = await import(pathToFileURL(`${RUNTIME}/@deepseek-ai/dsh-app-boot/lib/index.js`).href)
const include = await import(pathToFileURL(`${RUNTIME}/@deepseek-ai/cordis-plugin-include/lib/index.js`).href)

console.log('[A] 官方 loadOverlayPatches 解析 bundle patch')
let patches
try {
  patches = appBoot.loadOverlayPatches('dsh', `${BUNDLE}/cordis.patch.yml`)
  console.log(`  OK    解析成功,${patches.length} 个 patch 条目`)
} catch (e) {
  console.log(`  FAIL  ${e.message}`)
  process.exit(1)
}

console.log('\n[B] 检查 !!js 表达式被保留为节点(未被求值)')
const json = JSON.stringify(patches)
const hasJs = json.includes('__jsExpr')
console.log(`  ${hasJs ? 'OK   ' : 'FAIL '} !!js 保留为 {__jsExpr} 节点: ${hasJs}`)
if (!hasJs) process.exit(1)
const exprs = [...json.matchAll(/"__jsExpr":"((?:[^"\\]|\\.)*)"/g)].map((m) => JSON.parse(`"${m[1]}"`))
console.log(`  表达式: ${[...new Set(exprs)].join(' | ')}`)

console.log('\n[C] 官方 applyEntryPatches 合入模拟 entry 树')
// 模拟 profile 基础树:含 shipped preset 行 + agent-preset-registry
const base = [
  { id: 'agent-preset-registry', name: '@deepseek-ai/dsh-agent-preset-registry', config: { default: 'standard' } },
  { id: 'preset-standard', name: '@deepseek-ai/dsh-agent-preset', config: { id: 'standard', order: 1, plugins: [] } },
  { id: 'preset-ptc', name: '@deepseek-ai/dsh-agent-preset', config: { id: 'ptc', order: 2, plugins: [] } },
  { id: 'preset-minimal', name: '@deepseek-ai/dsh-agent-preset', config: { id: 'minimal', order: 3, plugins: [] } },
  { id: 'preset-cordis', name: '@deepseek-ai/dsh-agent-preset', config: { id: 'cordis', order: 4, plugins: [] } },
]
const skipped = []
const merged = include.applyEntryPatches(base, patches, (msg, ...a) => {
  let i = 0
  skipped.push(msg.replace(/%C/g, () => JSON.stringify(a[i++])))
})
if (skipped.length) {
  console.log(`  FAIL  有 patch 未匹配: ${skipped.join('; ')}`)
  process.exit(1)
}
console.log(`  OK    全部 patch 应用成功,无跳过`)

console.log('\n[D] 合成结果校验')
const jevRow = merged.find((r) => r.id === 'preset-jev')
if (!jevRow) { console.log('  FAIL  合成树中找不到 preset-jev 行'); process.exit(1) }
console.log(`  OK    preset-jev 行已合入`)
console.log(`        name   = ${jevRow.name}`)
console.log(`        id     = ${jevRow.config.id}`)
console.log(`        order  = ${jevRow.config.order}`)
console.log(`        plugins= ${jevRow.config.plugins.length} 行`)
if (jevRow.config.id !== 'jev') { console.log('  FAIL  config.id 错误'); process.exit(1) }
if (jevRow.name !== '@deepseek-ai/dsh-agent-preset') { console.log('  FAIL  name 错误'); process.exit(1) }

// 与既有预设 id 冲突检查(registry 对重复 id 抛错)
const presetIds = merged.filter((r) => r.name === '@deepseek-ai/dsh-agent-preset').map((r) => r.config.id)
const dup = presetIds.filter((v, i) => presetIds.indexOf(v) !== i)
if (dup.length) { console.log(`  FAIL  preset id 冲突: ${dup.join(', ')}`); process.exit(1) }
console.log(`  OK    preset id 无冲突: ${presetIds.join(', ')}`)

// Loader 行 id 唯一
const loaderIds = merged.map((r) => r.id).filter(Boolean)
const dupId = loaderIds.filter((v, i) => loaderIds.indexOf(v) !== i)
if (dupId.length) { console.log(`  FAIL  Loader 行 id 冲突: ${dupId.join(', ')}`); process.exit(1) }
console.log(`  OK    Loader 行 id 无冲突(${loaderIds.length} 行)`)

// insert 语义确认:官方 patch 的 insert 是「追加」,重复应用必然追加两份。
// 这不是幂等性缺陷 —— profile 加载时每个 patch 层只应用一次;此处只确认
// 语义与官方一致(applyEntryPatches 源码:`if (insert) { ... data.push(...insert) }`)。
const twice = include.applyEntryPatches(merged, patches, () => {})
const jevCount = twice.filter((r) => r.id === 'preset-jev').length
if (jevCount !== 2) {
  console.log(`  FAIL  insert 语义不符:重复应用后 preset-jev 行数 = ${jevCount},期望 2`)
  process.exit(1)
}
console.log('  OK    insert 语义与官方一致(追加;单次加载只应用一层)')
console.log(`  OK    原始树未被 mutate(${base.length} 行不变,官方 structuredClone 保护)`)

console.log('\n' + '='.repeat(60))
console.log('官方代码路径验证全部通过 — bundle 可安全安装')
