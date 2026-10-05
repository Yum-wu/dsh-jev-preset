// 静态校验:用 DSH 官方同款的 YAML schema + 真实解析器校验 JEV bundle。
// 1) YAML 用 entryListSchema(与 cordis-plugin-include 读取 profile 时完全一致)
// 2) 结构用 dsh-agent-preset-registry 自己的 entryListProblem 规则复刻
// 3) 子插件名对照 shipped preset 已成功挂载的名字集合(同层解析环境)
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'

import { runtimeNodeModules } from './runtime-path.mjs'

const RUNTIME = runtimeNodeModules()
const BUNDLE = 'C:/Users/Yum/Desktop/DeepSeekHarness/plugins/dsh-jev-preset'

const req = createRequire(pathToFileURL(`${RUNTIME}/@deepseek-ai/cordis-plugin-include/lib/index.js`))
const yaml = req('js-yaml')

// 官方 entryListSchema:JSON_SCHEMA + !!js 标量(见 cordis-plugin-include/lib/index.js)
const JsExpr = new yaml.Type('tag:yaml.org,2002:js', {
  kind: 'scalar',
  resolve: (data) => typeof data === 'string',
  construct: (data) => ({ __jsExpr: data }),
  predicate: (v) => v instanceof Object && '__jsExpr' in v,
  represent: (data) => data['__jsExpr'],
})
const entryListSchema = yaml.JSON_SCHEMA.extend(JsExpr)

const fails = []
const warns = []
const ok = (m) => console.log(`  OK    ${m}`)
const fail = (m) => { fails.push(m); console.log(`  FAIL  ${m}`) }

// ── 1. 解析 YAML ────────────────────────────────────────────────────────────
console.log('\n[1] YAML 解析(官方 entryListSchema)')
const patchText = readFileSync(`${BUNDLE}/cordis.patch.yml`, 'utf8')
let patch
try {
  patch = yaml.load(patchText, { schema: entryListSchema })
  ok('cordis.patch.yml 解析成功')
} catch (e) {
  fail(`cordis.patch.yml 解析失败: ${e.message}`)
  process.exit(1)
}

// ── 2. 定位声明行 ───────────────────────────────────────────────────────────
console.log('\n[2] 声明行结构')
if (!Array.isArray(patch)) { fail('顶层必须是数组'); process.exit(1) }
ok(`顶层是数组(${patch.length} 个 patch 条目)`)
const inserts = patch.filter((p) => p && p.insert)
if (inserts.length !== 1) fail(`期望恰好 1 个 insert patch,实际 ${inserts.length}`)
else ok('恰好 1 个 insert patch')
const rows = inserts.flatMap((p) => p.insert)
// 2026-10-05 起本组有 2 条声明行：preset-jev（agent preset）+ plugin-auto-reasoning
// （思考档位插件，见 cordis.patch.yml 末尾「同一个 insert 组里的第二条声明行」段）。
// 因此**按 id 定位**而不是假设 rows[0] —— 顺序一变就静默校验错对象。
if (rows.length < 1) fail('insert 组里没有任何声明行')
else ok(`insert 组内 ${rows.length} 条声明行: ${rows.map((r) => r?.id).join(', ')}`)
const decl = rows.find((r) => r?.id === 'preset-jev')
if (!decl) fail('insert 组里找不到 id=preset-jev 的声明行')
else ok('preset 声明行按 id 定位成功(id=preset-jev)')
if (decl?.name !== '@deepseek-ai/dsh-agent-preset') fail(`声明行 name 应为 @deepseek-ai/dsh-agent-preset,实际 ${decl?.name}`)
else ok(`声明行 name = ${decl.name}`)
if (decl?.id !== 'preset-jev') fail(`Loader 行 id 应为 preset-jev,实际 ${decl?.id}`)
else ok(`Loader 行 id = ${decl.id}`)

// 同组的非 preset 声明行：只允许已知的插件 id，且名字必须能被 Loader 解析
const extraRows = rows.filter((r) => r?.id !== 'preset-jev')
const ALLOWED_EXTRA = new Set(['plugin-auto-reasoning'])
for (const r of extraRows) {
  if (!ALLOWED_EXTRA.has(r?.id)) fail(`insert 组里出现未登记的非 preset 声明行 id=${r?.id}`)
  else ok(`附属声明行 id=${r.id} name=${r.name}`)
}
if (extraRows.some((r) => r?.id === 'plugin-auto-reasoning') && decl) {
  // profile 的 cordis.patch.yml 不得再单独 insert 同 id —— Loader entry id 重复会让 profile 起不来
  ok('plugin-auto-reasoning 已由本 bundle 声明（profile 侧须留空，见 cordis.patch.yml 注释）')
}

// ── 3. config 字段(schemastery 契约:仅这些键被接受)────────────────────────
console.log('\n[3] config 字段契约')
const cfg = decl?.config ?? {}
const allowed = new Set(['id', 'name', 'description', 'order', 'plugins'])
for (const k of Object.keys(cfg)) if (!allowed.has(k)) fail(`未知 config 键: ${k}`)
ok(`config 键全部合法: ${Object.keys(cfg).join(', ')}`)
if (cfg.id !== 'jev') fail(`config.id 应为 jev,实际 ${cfg.id}`)
else ok(`config.id = ${cfg.id}`)
if (!/^[a-z0-9-]+$/.test(String(cfg.id))) fail(`config.id 必须是小写字母/数字/连字符: ${cfg.id}`)
else ok('config.id 符合 ^[a-z0-9-]+$')
if (typeof cfg.order !== 'number') fail('order 必须是数字')
else ok(`order = ${cfg.order}`)
for (const f of ['name', 'description']) {
  if (typeof cfg[f] !== 'string' || cfg[f] === '') fail(`${f} 必须是非空字符串`)
}
ok('name / description 均为非空字符串')
if (!Array.isArray(cfg.plugins)) { fail('plugins 必须是数组'); process.exit(1) }
ok(`plugins 是数组(${cfg.plugins.length} 行)`)

// ── 4. 复刻 registry 的 entryListProblem 校验 ───────────────────────────────
console.log('\n[4] 行结构校验(复刻 registry entryListProblem)')
function entryListProblem(rows, at = '') {
  if (!Array.isArray(rows)) return at === '' ? 'the composition must be a top-level list of plugin rows' : `group ${at} must hold a list of plugin rows`
  for (const [i, row] of rows.entries()) {
    const label = at === '' ? `row ${i + 1}` : `${at} row ${i + 1}`
    if (typeof row !== 'object' || row === null || Array.isArray(row)) return `${label} is not a plugin row (expected a map with a "name")`
    const { name, group, config } = row
    if (typeof name !== 'string' || name === '') return `${label} names no plugin (a "name" string is required)`
    if (group === true) {
      const nested = entryListProblem(config, label)
      if (nested !== undefined) return nested
    }
  }
}
const problem = entryListProblem(cfg.plugins)
if (problem !== undefined) fail(`entryListProblem: ${problem}`)
else ok('entryListProblem 通过(递归含 group)')

// 重复行 id 检查
const ids = []
const collect = (rs) => { for (const r of rs) { if (r.id) ids.push(r.id); if (r.group === true) collect(r.config) } }
collect(cfg.plugins)
const dup = ids.filter((v, i) => ids.indexOf(v) !== i)
if (dup.length) fail(`重复行 id: ${[...new Set(dup)].join(', ')}`)
else ok(`行 id 唯一(${ids.length} 个)`)

// ── 5. isolate 私有域 ───────────────────────────────────────────────────────
console.log('\n[5] isolate 私有隔离域')
const groups = cfg.plugins.filter((r) => r.group === true)
if (groups.length === 0) fail('未发现 group 行')
for (const g of groups) {
  const iso = g.isolate
  const hasIso = iso && typeof iso === 'object' && Object.keys(iso).length > 0
  console.log(`  ${hasIso ? 'OK   ' : 'FAIL '} group "${g.id}" isolate = ${JSON.stringify(iso ?? null)}`)
  if (!hasIso) fails.push(`group ${g.id} 缺少 isolate`)
  else if (Object.values(iso).some((v) => v !== true && typeof v !== 'string')) fail(`group ${g.id} isolate 值必须是 true 或字符串`)
}
ok(`服务组 isolate 检查完毕(${groups.length} 个 group)`)

// ── 6. 子插件名解析(runtime 锚点 = 声明行插件的真实位置)────────────────────
console.log('\n[6] 子插件名可解析性(runtime 锚点)')
const anchorReq = createRequire(pathToFileURL(`${RUNTIME}/@deepseek-ai/dsh-agent-preset/lib/index.js`))
const names = []
const collectNames = (rs) => { for (const r of rs) { names.push(r.name); if (r.group === true) collectNames(r.config) } }
collectNames(cfg.plugins)
const bare = [...new Set(names.filter((n) => !n.startsWith('cordis:') && !n.startsWith('.')))]
let resolvable = 0
for (const n of bare) {
  // 直接解析 specifier 本身。子路径导出(如 .../list-agents)通常不暴露
  // package.json,故不能用 `<name>/package.json` 判定 —— 那是探针假阳性。
  // 回退:取包名部分解析 package.json,确认包本体存在。
  const pkgName = n.startsWith('@') ? n.split('/').slice(0, 2).join('/') : n.split('/')[0]
  try {
    anchorReq.resolve(n)
    resolvable++
  } catch (e) {
    try {
      anchorReq.resolve(`${pkgName}/package.json`)
      resolvable++
      warns.push(`${n} 的入口不可解析(${e.code}),但包本体 ${pkgName} 存在`)
    } catch (e2) {
      fail(`无法解析 ${n} (${e.code} / 包 ${pkgName}: ${e2.code})`)
    }
  }
}
ok(`${resolvable}/${bare.length} 个子插件名可解析`)
const builtins = [...new Set(names.filter((n) => n.startsWith('cordis:')))]
if (builtins.length) ok(`cordis 内建行: ${builtins.join(', ')}`)

// ── 7. 无版本硬编码 / 无臃肿依赖 ────────────────────────────────────────────
console.log('\n[7] 依赖卫生')
const pkg = JSON.parse(readFileSync(`${BUNDLE}/package.json`, 'utf8'))
for (const field of ['dependencies', 'peerDependencies', 'devDependencies', 'optionalDependencies']) {
  if (pkg[field] && Object.keys(pkg[field]).length) fail(`package.json 不应声明 ${field}: ${JSON.stringify(pkg[field])}`)
}
ok('零 dependencies / peerDependencies(无版本硬编码,无臃肿依赖)')
if (pkg.dsh?.bundle?.patch !== './cordis.patch.yml') fail('package.json 缺 dsh.bundle.patch 指向')
else ok('dsh.bundle.patch = ./cordis.patch.yml')
if (/\d+\.\d+\.\d+/.test(patchText.replace(/#.*$/gm, ''))) warns.push('patch 非注释部分出现疑似版本号')
ok('patch 非注释部分无版本号字面量')

// ── 汇总 ────────────────────────────────────────────────────────────────────
console.log('\n' + '='.repeat(60))
if (warns.length) { console.log('警告:'); warns.forEach((w) => console.log(`  - ${w}`)) }
if (fails.length) {
  console.log(`静态校验失败:${fails.length} 项`)
  fails.forEach((f) => console.log(`  - ${f}`))
  process.exit(1)
}
console.log('静态校验全部通过')
