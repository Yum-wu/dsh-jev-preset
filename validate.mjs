// 静态校验:用 DSH 官方同款的 YAML schema + 真实解析器校验 JEV bundle。
// 1) YAML 用 entryListSchema(与 cordis-plugin-include 读取 profile 时完全一致)
// 2) 结构用 dsh-agent-preset-registry 自己的 entryListProblem 规则复刻
// 3) 子插件名对照 shipped preset 已成功挂载的名字集合(同层解析环境)
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { pathToFileURL, fileURLToPath } from 'node:url'

import { runtimeNodeModules } from './runtime-path.mjs'

const RUNTIME = runtimeNodeModules()
// 本包根目录 = 本模块所在目录,**不写死绝对路径**。
// 写死会让 clone / 移动后的副本继续校验原树 ⇒ 守卫对着旧树打绿(同 runtime-path.mjs
// 里「指针留在旧目录、静默测错对象」一类病),也让判别性测试无法在临时目录跑。
const BUNDLE = fileURLToPath(new URL('.', import.meta.url)).replace(/\\/g, '/').replace(/\/$/, '')

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
// 2026-10-05 起本组有多条声明行：agent preset 声明 + 运行时半区。
// ⚠ 2026-10-13 合体：运行时半区由 `plugin-auto-reasoning`（引用外部包
//   `dsh-auto-reasoning`）改为 `plugin-yum-runtime`（自挂本包，代码在 lib/）。
// ⚠ 2026-10-17（运行时 0.2.1-rc.2）：子代理身份迁移为**独立 preset**
//   `preset-jev-executor` / config.id `jev-executor`（`dsh-tool-subagent` 不再接受
//   `persona` / `toolFilter` 键）。⚠ config.id 这里**必须**留 `jev-executor`：它是
//   会话外键（见 PERSISTED_PRESET_IDS 一节），2026-10-19 一度改成 yum-executor 又撕回。
// 因此**按 id / name 定位**而不是假设 rows[0] —— 顺序一变就静默校验错对象。
if (rows.length < 1) fail('insert 组里没有任何声明行')
else ok(`insert 组内 ${rows.length} 条声明行: ${rows.map((r) => r?.id).join(', ')}`)

const PRESET_PKG = '@deepseek-ai/dsh-agent-preset'
const presetRows = rows.filter((r) => r?.name === PRESET_PKG)
if (presetRows.length < 1) fail(`insert 组里没有 ${PRESET_PKG} 声明行`)
for (const r of presetRows) {
  if (!/^preset-[a-z0-9-]+$/.test(String(r?.id))) fail(`preset 声明行的 Loader 行 id 应为 preset-*,实际 ${r?.id}`)
}
// 按**持久化身份**定位:`config.id` 是会话存进日志的外键(agentPreset.val),
// Loader 行 `id:` 只是可改的命名空间。写死行 id 会让「改显示名/行 id」把校验器
// 一起弄红 —— 2026-10-19 那次 jev→yum 改名正是这样:校验器红 3 项没人跑,
// 而真正的代价是 738 条会话 resume 失败。
const decl = rows.find((r) => r?.name === PRESET_PKG && r?.config?.id === 'jev')
if (!decl) fail('insert 组里找不到 config.id=jev 的 preset 声明行 —— config.id 是会话外键,不可改名')
else ok(`preset 声明行按 config.id 定位成功(Loader 行 id=${decl.id})`)
if (decl && !/^preset-[a-z0-9-]+$/.test(String(decl.id))) fail(`Loader 行 id 应为 preset-*,实际 ${decl.id}`)
else if (decl) ok(`Loader 行 id = ${decl.id}(命名空间,可随包名改)`)

// 同组的非 preset 声明行：只允许已知的插件 id，且名字必须能被 Loader 解析
const extraRows = rows.filter((r) => r?.name !== PRESET_PKG)
const ALLOWED_EXTRA = new Set(['plugin-yum-runtime'])
for (const r of extraRows) {
  if (!ALLOWED_EXTRA.has(r?.id)) fail(`insert 组里出现未登记的非 preset 声明行 id=${r?.id}`)
  else ok(`附属声明行 id=${r.id} name=${r.name}`)
}
const runtimeRow = extraRows.find((r) => r?.id === 'plugin-yum-runtime')
if (runtimeRow !== undefined && decl) {
  // 自挂：name 必须是本包名，否则 Loader 解析到别的包（或解析不到）→ 整条不激活。
  if (runtimeRow.name !== 'dsh-yum-preset') fail(`运行时半区应自挂本包，name 实际 ${runtimeRow.name}`)
  else ok('plugin-yum-runtime 自挂本包（name=dsh-yum-preset）')
  // ⚠ 旧形态必须绝迹：`plugin-auto-reasoning` 指向外部包 `dsh-auto-reasoning`，
  //   它与对方自己的 bundle 层同 id ⇒ 合成层重复、后者胜 ⇒ 本包 config 静默失效。
  if (extraRows.some((r) => r?.id === 'plugin-auto-reasoning')) {
    fail('仍存在旧的 plugin-auto-reasoning 声明行 —— 与 dsh-auto-reasoning 自己的 bundle 层同 id，会静默覆盖本包 config')
  } else {
    ok('已无旧 plugin-auto-reasoning 声明行（同 id 静默覆盖的入口已消除）')
  }
}

// ── 3. config 字段(schemastery 契约:仅这些键被接受)────────────────────────
console.log('\n[3] config 字段契约')
const allowed = new Set(['id', 'name', 'description', 'order', 'plugins'])
for (const p of presetRows) {
  const cfg = p.config ?? {}
  const at = `[${p.id}]`
  for (const k of Object.keys(cfg)) if (!allowed.has(k)) fail(`${at} 未知 config 键: ${k}`)
  if (!/^[a-z0-9-]+$/.test(String(cfg.id))) fail(`${at} config.id 必须匹配 ^[a-z0-9-]+$: ${cfg.id}`)
  if (typeof cfg.order !== 'number') fail(`${at} order 必须是数字`)
  for (const f of ['name', 'description']) {
    if (typeof cfg[f] !== 'string' || cfg[f] === '') fail(`${at} ${f} 必须是非空字符串`)
  }
  if (!Array.isArray(cfg.plugins)) { fail(`${at} plugins 必须是数组`); continue }
  ok(`${at} config 键合法 id=${cfg.id} order=${cfg.order} plugins=${cfg.plugins.length} 行`)
}
const presetIds = presetRows.map((p) => p?.config?.id)
// ⚠ 这两个 config.id 是**会话持久化外键**,不是显示名:改了就是让存量会话 resume 报错
//   (`Unknown agent preset: <id>`)。本包必须同时暴露这两个,一个都不能少。
//   实测存量(2026-10-19,~/.dsh/storages/session_projcache/sessions/,1868 份投影):
//     agentPreset 有值 1802 = jev 738 + standard 988 + ptc 48 + cordis 21 + liangshen 4
//                         + jev-executor 3;另有 66 份根本不带 agentPreset 键(合计 1868)。
//     **yum / yum-executor 命中 0** —— 一次改名都没留下任何存量,改名纯属自找。
//   「这 3 条 jev-executor 是不是可丢弃的子代理子会话」——不能按"带 subagent 行"判:
//     该键在 1868 份里 646 份都有 mode(continuable 578 / one-shot 68),父会话照样带,
//     **是个恒真判据**(2026-10-19 我在这上面错判过一次,已撕回)。
//   可用的实判据 = `record.rows.subagent.val.identity.mode`:这 3 条**全是 continuable**
//     (不是 one-shot 一次性子会话),所以"可承受"的依据不是"它们是子会话",而是
//     实测在 ~/.dsh/storages/{schedule,workspace,dispatch}.json 里**零引用**。
//   要改名的正确顺序:先按上面两条取证,再**同一批**改掉声明行的 config.id 与父 preset
//   里的 `agentPreset:` 指认 —— 两者不一致会让子代理静默起不来。只改一边 = 静默断链。
//   旧写法 `if (decl && ...) fail() else ok()` 在 decl 为 undefined 时会打 OK —— 恒绿判据,已废。
const PERSISTED_PRESET_IDS = ['jev', 'jev-executor']
for (const pid of PERSISTED_PRESET_IDS) {
  const n = presetIds.filter((x) => x === pid).length
  if (n === 1) ok(`持久化 preset 外键 ${pid} 恰好注册 1 次`)
  else fail(`持久化 preset 外键 ${pid} 注册了 ${n} 次(应为 1 次;0 次=被改名或删除,存量会话会 resume 失败)`)
}
// registry:`Duplicate agent preset: <id>` 会让声明加载失败
const dupPresetIds = presetIds.filter((v, i) => presetIds.indexOf(v) !== i)
if (dupPresetIds.length) fail(`preset id 重复: ${[...new Set(dupPresetIds)].join(', ')}`)
else ok(`preset id 唯一(${presetIds.join(', ')})`)

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
for (const p of presetRows) {
  const at = `[${p.id}]`
  const problem = entryListProblem(p.config?.plugins)
  if (problem !== undefined) fail(`${at} entryListProblem: ${problem}`)
  else ok(`${at} entryListProblem 通过(递归含 group)`)

  // 重复行 id 检查
  const ids = []
  const collect = (rs) => { for (const r of rs) { if (r.id) ids.push(r.id); if (r.group === true) collect(r.config) } }
  collect(p.config?.plugins ?? [])
  const dup = ids.filter((v, i) => ids.indexOf(v) !== i)
  if (dup.length) fail(`${at} 重复行 id: ${[...new Set(dup)].join(', ')}`)
  else ok(`${at} 行 id 唯一(${ids.length} 个)`)
}

// ── 5. isolate 私有域 ───────────────────────────────────────────────────────
console.log('\n[5] isolate 私有隔离域')
for (const p of presetRows) {
  const at = `[${p.id}]`
  const groups = (p.config?.plugins ?? []).filter((r) => r.group === true)
  if (groups.length === 0) { fail(`${at} 未发现 group 行`); continue }
  for (const g of groups) {
    const iso = g.isolate
    const hasIso = iso && typeof iso === 'object' && Object.keys(iso).length > 0
    console.log(`  ${hasIso ? 'OK   ' : 'FAIL '} ${at} group "${g.id}" isolate = ${JSON.stringify(iso ?? null)}`)
    if (!hasIso) fails.push(`${at} group ${g.id} 缺少 isolate`)
    else if (Object.values(iso).some((v) => v !== true && typeof v !== 'string')) fail(`${at} group ${g.id} isolate 值必须是 true 或字符串`)
  }
  ok(`${at} 服务组 isolate 检查完毕(${groups.length} 个 group)`)
}

// ── 6. 子插件名解析(runtime 锚点 = 声明行插件的真实位置)────────────────────
console.log('\n[6] 子插件名可解析性(runtime 锚点)')
const anchorReq = createRequire(pathToFileURL(`${RUNTIME}/@deepseek-ai/dsh-agent-preset/lib/index.js`))
let resolvableTotal = 0
let bareTotal = 0
for (const p of presetRows) {
  const at = `[${p.id}]`
  const names = []
  const collectNames = (rs) => { for (const r of rs) { names.push(r.name); if (r.group === true) collectNames(r.config) } }
  collectNames(p.config?.plugins ?? [])
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
        warns.push(`${at} ${n} 的入口不可解析(${e.code}),但包本体 ${pkgName} 存在`)
      } catch (e2) {
        fail(`${at} 无法解析 ${n} (${e.code} / 包 ${pkgName}: ${e2.code})`)
      }
    }
  }
  resolvableTotal += resolvable
  bareTotal += bare.length
  ok(`${at} ${resolvable}/${bare.length} 个子插件名可解析`)
}
ok(`两份 preset 合计 ${resolvableTotal}/${bareTotal} 个子插件名可解析`)
const builtins = [...new Set((patch[0]?.insert ?? []).flatMap((p) => {
  const names = []
  const walk = (rs) => { for (const r of rs ?? []) { if (r?.name) names.push(r.name); if (r?.group === true) walk(r.config) } }
  walk(p?.config?.plugins ?? [])
  return names
}).filter((n) => typeof n === 'string' && n.startsWith('cordis:')))]
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

// ── 8. persona 变量白名单(未注册变量 = 组装期硬错,该 preset 每一轮都起不来)──
console.log('\n[8] persona 变量白名单')
// 运行时 `dsh-system-prompt` 的 interpolate 只认**已注册**变量:0.2.1 实测只注册
// provider / model。其余(如 0.2.0 时代可用的 `{{cwd}}`)会抛
//   unknown prompt variable "{{cwd}}" in section "deployment:persona-suffix"
// 抛点在 persona 组装期 ⇒ 该 preset 的**每一轮**都失败,且只在真实会话里暴露
// (2026-10-17 实测)。上游 README 的迁移条目点名要求删掉这句子句,工作目录改由
// working-directory 服务以字面用户上下文提供。
const REGISTERED_VARIABLES = new Set(['model', 'provider'])
let personaRefs = 0
for (const p of presetRows) {
  const at = `[${p.id}]`
  for (const row of p.config?.plugins ?? []) {
    if (row?.name !== '@deepseek-ai/dsh-persona') continue
    for (const key of ['prefix', 'suffix']) {
      const text = row.config?.[key]
      if (typeof text !== 'string') continue
      for (const m of text.matchAll(/\{\{([^{}]*)\}\}/g)) {
        personaRefs++
        if (!REGISTERED_VARIABLES.has(m[1])) {
          fail(`${at} persona.${key} 引用未注册变量 {{${m[1]}}} —— 组装期抛错,该 preset 每一轮都起不来`)
        }
      }
    }
  }
}
ok(`persona 变量引用 ${personaRefs} 处,全部在白名单(${[...REGISTERED_VARIABLES].sort().join(', ')})内`)

// ── 汇总 ────────────────────────────────────────────────────────────────────
console.log('\n' + '='.repeat(60))
if (warns.length) { console.log('警告:'); warns.forEach((w) => console.log(`  - ${w}`)) }
if (fails.length) {
  console.log(`静态校验失败:${fails.length} 项`)
  fails.forEach((f) => console.log(`  - ${f}`))
  process.exit(1)
}
console.log('静态校验全部通过')
