// 子代理身份迁移守卫(运行时 0.2.1-rc.2,2026-10-17)。
//
// 背景(实测):`dsh-tool-subagent` 0.2.1-rc.2 的 `apply()` 只要在 config 里看到
//   `persona` / `toolFilter` 键就抛
//     `tool-subagent: <field> is no longer supported; configure persona and tool plugins
//      in an Agent Preset and select it with agentPreset (spawn only)`
// 该 throw 发生在 **preset 挂载时**,不是启动时 ⇒ 任何用 `agentPreset: jev` 建会话的路径
// (含注册表 default)全部失败:
//   POST /api/session/create {agentPreset:"jev"}
//     → {code:"agent-preset/invalid", message:"...persona is no longer supported..."}
// 用户侧看到的是「DSH 更新后起不来了」,而 DSH 进程其实活着(3080 有响应)。
//
// 修法:子代理身份迁到**独立 preset** `preset-yum-executor`,`tool-subagent` 只留
// `agentPreset: yum-executor`。⚠ 上游对独立子 preset **没有**「继承父 preset」机制
// (`dsh-subagent/README.md`:An explicit id mounts the current available revision),
// 所以子 preset 的工具行必须自足 —— 漏一行 = 子代理静默少一件工具。
// 本文件就是那个不变量:两份 plugins 列表逐行一致,差集只允许 delegation 组。

import test from 'node:test'
import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { fileURLToPath, pathToFileURL } from 'node:url'

import { runtimeNodeModules } from '../runtime-path.mjs'

const RUNTIME = runtimeNodeModules()
const PATCH_FILE = fileURLToPath(new URL('../cordis.patch.yml', import.meta.url))

const req = createRequire(pathToFileURL(`${RUNTIME}/@deepseek-ai/cordis-plugin-include/lib/index.js`))
const yaml = req('js-yaml')

const JsExpr = new yaml.Type('tag:yaml.org,2002:js', {
  kind: 'scalar',
  resolve: (data) => typeof data === 'string',
  construct: (data) => ({ __jsExpr: data }),
  predicate: (v) => v instanceof Object && '__jsExpr' in v,
  represent: (data) => data['__jsExpr'],
})

function loadPatch() {
  const patch = yaml.load(readFileSync(PATCH_FILE, 'utf8'), { schema: yaml.JSON_SCHEMA.extend(JsExpr) })
  const rows = patch[0].insert
  // 按 **config.id(会话持久化外键)** 定位,不按 Loader 行 id ——
  //   行 id 是可改的命名空间(2026-10-19 由 preset-jev 改成 preset-yum),
  //   写死行 id 会让改名把整组测试弄红,而真正的不变量在 config.id 上。
  const parent = rows.find((r) => r.config?.id === 'jev')
  assert.ok(parent, '找不到 config.id=jev 的 preset 声明行(会话外键,不可改名)')
  // 子 preset 身份**从父 preset 的指认里读出来**,不写死字面量 ——
  //   写死就查不出「声明行改了名、agentPreset 指认没改」这种单边断链(2026-10-19 实测风险)。
  const spawnId = findAgentPresetRef(parent.config.plugins)
  assert.ok(spawnId, '父 preset 里找不到任何 `agentPreset:` 指认 —— 子代理身份没有落到独立 preset')
  const child = rows.find((r) => r.config?.id === spawnId)
  assert.ok(child, `父 preset 指认子代理挂 "${spawnId}",但 insert 组里没有这条 preset 声明行 —— 只改一边会让子代理静默起不来`)
  return { rows, parent, child }
}

/** 深度优先找第一个 config.agentPreset 字符串(父 preset 的 tool-subagent 指认)。 */
function findAgentPresetRef(node) {
  if (!node || typeof node !== 'object') return null
  if (!Array.isArray(node) && typeof node.config?.agentPreset === 'string') return node.config.agentPreset
  const kids = Array.isArray(node) ? node : Object.values(node)
  for (const k of kids) { const hit = findAgentPresetRef(k); if (hit) return hit }
  return null
}

function subagentRow(preset, rowId) {
  const delegation = preset.config.plugins.find((p) => p.id === 'delegation')
  assert.ok(delegation, `${preset.id} 里找不到 delegation 组`)
  const row = delegation.config.find((r) => r.id === rowId)
  assert.ok(row, `delegation 组里找不到 ${rowId} 行`)
  return row
}

test('T1: 没有任何 tool-subagent 行再带 persona / toolFilter 键(0.2.1 会在挂载时抛错)', () => {
  const { rows } = loadPatch()
  const hits = []
  const walk = (rs, at) => {
    for (const r of rs ?? []) {
      if (r?.name === '@deepseek-ai/dsh-tool-subagent') {
        for (const f of ['persona', 'toolFilter']) {
          if (Object.hasOwn(r.config ?? {}, f)) hits.push(`${at}/${r.id}.config.${f}`)
        }
      }
      if (r?.group === true) walk(r.config, `${at}/${r.id}`)
    }
  }
  for (const row of rows) walk(row.config?.plugins, row.id)
  assert.deepEqual(hits, [], `这些行会让整个 preset 挂载失败(旧写法): ${hits.join(', ')}`)
})

test('T2: spawn 工具声明 agentPreset,且该 id 指向本文档内声明的 preset', () => {
  const { rows, child } = loadPatch()
  const { parent } = loadPatch()
  const spawnRow = subagentRow(parent, 'tool-subagent')
  assert.equal(spawnRow.config.agentPreset, child.config.id,
    'tool-subagent.config.agentPreset 必须等于子 preset 的 config.id')
  assert.equal(spawnRow.config.allowedAgentPresets, undefined,
    '不设 allowedAgentPresets:一旦设了就给模型一个 agent_preset 枚举,子代理身份可被模型改')
  // agentPreset 指向的 preset 必须在同一 insert 组里被**声明**(否则运行时报 id 未知)
  const declared = rows.filter((r) => r.name === '@deepseek-ai/dsh-agent-preset').map((r) => r.config?.id)
  assert.ok(declared.includes(spawnRow.config.agentPreset),
    `agentPreset=${spawnRow.config.agentPreset} 未在同组声明:${declared.join(', ')}`)
  assert.match(String(child.config.id), /^[a-z0-9-]+$/, 'preset id 必须匹配 ^[a-z0-9-]+$')
})

test('T3: 子 preset 的工具面与父 preset 逐行一致(差集只允许 delegation 组)', () => {
  const { parent, child } = loadPatch()
  const strip = (r) => ({ id: r.id, name: r.name, disabled: r.disabled, config: r.config, isolate: r.isolate, group: r.group })
  const parentById = new Map(parent.config.plugins.map((r) => [r.id, strip(r)]))
  const childById = new Map(child.config.plugins.map((r) => [r.id, strip(r)]))

  const missing = [...parentById.keys()].filter((id) => !childById.has(id))
  assert.deepEqual(missing, ['delegation'],
    `子 preset 与父 preset 的行差集必须**恰好**是 delegation 组,实际缺: ${missing.join(', ')}\n`
    + '(独立子 preset 不自足继承任何东西,漏行 = 子代理静默少一件工具)')

  const extra = [...childById.keys()].filter((id) => !parentById.has(id))
  assert.deepEqual(extra, [], `子 preset 多出未登记的行走: ${extra.join(', ')}`)

  for (const [id, row] of childById) {
    if (id === 'persona') continue  // 身份文本本来就不同,单独由 T4 判
    assert.deepEqual(row, parentById.get(id), `行 ${id} 与父 preset 不一致 —— 两份列表漂移了`)
  }
})

test('T4: 子 persona 是执行者身份,且不含裁决标识表(父会话专属)', () => {
  const { parent, child } = loadPatch()
  const parentPersona = parent.config.plugins.find((p) => p.id === 'persona').config
  const childPersona = child.config.plugins.find((p) => p.id === 'persona').config
  const text = String(childPersona.prefix ?? '')

  assert.notEqual(text, parentPersona.prefix, '子 persona 不得与父 persona 相同(身份必须换掉)')
  assert.match(text, /单路执行者/, '子 persona 未声明「单路执行者」身份')
  assert.match(text, /不得派生任何下级子代理/, '子 persona 未禁止再派生(递归阻断的第一道纪律)')
  assert.match(text, /\[Path N/, '子 persona 未要求路标身份 —— 父会话分不清哪路回话')
  assert.match(text, /不要\*\*输出 `\[JEV: \.\.\.\]`|不要\*\*输出 `\[JEV:/,
    '子 persona 未禁止输出 [JEV: ...] 裁决标识(父会话专属)')

  // 裁决标识表(`- \`[JEV: X]\` — 说明`)只属于父 persona;
  // tests/test_route_classification.py 抽的是「全文第一处」,这里防它被复制进子 persona。
  const tableLines = text.split('\n').filter((l) => /^\s*-\s*`\[JEV:\s*[^\]]+\]`\s*—/.test(l))
  assert.deepEqual(tableLines, [], `子 persona 混进了裁决标识表: ${tableLines.slice(0, 3).join(' | ')}`)

  // 门控路由(「命中高危即强制三路」)是父会话的职责,子代理只执行,不该自带
  assert.doesNotMatch(text, /客观门控路由|强制 3 路|强制三路/,
    '子 persona 带上了父会话的门控路由纪律 —— 子代理会自己决定裂变')
})

test('T5: 子 preset 结构上不含 delegation 工具面(递归阻断不靠自律)', () => {
  const { child } = loadPatch()
  const names = []
  const walk = (rs) => { for (const r of rs ?? []) { if (r?.name) names.push(r.name); if (r?.group === true) walk(r.config) } }
  walk(child.config.plugins)
  const delegationish = names.filter((n) => /tool-subagent|workflow/.test(n))
  assert.deepEqual(delegationish, [],
    `子 preset 仍挂了委派/工作流工具: ${delegationish.join(', ')}\n`
    + '(递归裂变会由「prompt 自律」退回到无保障状态)')
  const ids = []
  const walkIds = (rs) => { for (const r of rs ?? []) { if (r?.id) ids.push(r.id); if (r?.group === true) walkIds(r.config) } }
  walkIds(child.config.plugins)
  const badIds = ids.filter((id) => /^tool-subagent|^workflow/.test(id))
  assert.deepEqual(badIds, [], `子 preset 仍有委派类行 id: ${badIds.join(', ')}`)
})

test('T6: 上游确实还有这条硬规则(persona/toolFilter 必被拒)与 agentPreset 字段', () => {
  // 若这条失败,说明运行时改了规则(或改了字段名)—— 迁移的**依据**没了,判据需重估。
  const p = `${RUNTIME}/@deepseek-ai/dsh-tool-subagent/lib/index.js`
  assert.ok(existsSync(p), `找不到 subagent 工具实现:${p}`)
  const src = readFileSync(p, 'utf8')
  assert.match(src, /\["persona", "toolFilter"\]/,
    '运行时不再枚举 persona/toolFilter —— T1 的判据失去依据,需按新规则重估')
  assert.match(src, /is no longer supported/,
    '运行时的迁移报错文案变了 —— 迁移依据需重新核实')
  assert.match(src, /agentPreset: z\.string\(\)/,
    '运行时 Config 里没有 agentPreset 字段 —— 本迁移的替代机制不存在')
})
