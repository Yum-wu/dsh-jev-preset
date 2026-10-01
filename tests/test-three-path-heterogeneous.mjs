// A9:三路隔离采样必须**异构**,而现状是三路同模型(继承父会话)。
//
// 缺陷背景(附录 A9,严重度高):
//   `cordis.patch.yml` 的 `tool-subagent` 配置块**没有任何模型路由字段**
//   (无 agentOptions / reasoningEffort / model),故三路子代理全部继承父会话模型
//   —— 即「同模型三路」。而本仓自身的结论是:
//   「同模型多路共享盲区(5/9 题收敛到同一错值)」,与 repo 已有研究
//   (arXiv:2604.07650 异构模型存在行为纠缠)一致。
//   换言之:persona 承诺的「3 路独立验证」在实现上是**同一个模型跑三遍**,
//   独立性的前提不存在。这是本目标最典型的「验证剧场」。
//
// 为什么修法在 persona 而不是 config(实测 DSH 运行时 schema,2026-10-01):
//   `dsh-tool-subagent` 的 Config.agentOptions 是**单个静态对象**(一个 provider/model),
//   无法表达「三路三个不同模型」;而单次调用可通过**顶层** `provider`/`model` 覆盖,
//   且 `modelSelectionSettings: true` 已开启。
//   → 正确修法是 **persona 纪律**要求每路显式指定不同 model,
//     并在 config 里写明「不钉死单个模型」的理由,避免下一个人又去硬编码。
//
// 判据(预注册,R9):
//   T1 persona §三 3.3 必须显式要求三路使用**不同**模型(不能只说「调 list_subagent_models」)
//   T2 persona 必须写明「不配 agentOptions」是**有意的**,并给出理由与替代机制
//      (否则下一个维护者会当成漏配去「修」它 —— 那正是本缺陷的成因)
//   T3 `tool-subagent` 配置块不得钉死单个 model(provider/model 不出现),
//      且 `modelSelectionSettings` 必须为 true(单次覆盖的前置条件)
//   T4 运行时 schema 确实支持单次覆盖 —— 直接读本机 DSH 运行时的源码断言,
//      防止「persona 要求的能力其实不存在」,那就是新的 A1(承诺代码做不到的事)

import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, existsSync } from 'node:fs'
import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'

import { runtimeNodeModules } from '../runtime-path.mjs'

const RUNTIME = runtimeNodeModules()
const req = createRequire(pathToFileURL(`${RUNTIME}/@deepseek-ai/cordis-plugin-include/lib/index.js`))
const yaml = req('js-yaml')

const JsExpr = new yaml.Type('tag:yaml.org,2002:js', {
  kind: 'scalar',
  resolve: (data) => typeof data === 'string',
  construct: (data) => ({ __jsExpr: data }),
  predicate: (v) => v instanceof Object && '__jsExpr' in v,
  represent: (v) => v['__jsExpr'],
})

function personaPrefix() {
  // ⚠ 必须按 YAML **块标量的缩进边界**截断,不能 slice 到文件末尾。
  //   红队 55ce6d3a 的决定性反证 v8b:用 `text.slice(start)` 时,
  //   persona 文本里混进了 §二 的句子、§三 3.3 之外的解释性从句、
  //   以及 tool-subagent 的 YAML 配置注释 —— T1 的正则因此被 4 条
  //   **与纪律无关**的文本满足,把核心要求整句删掉/改写后测试仍全绿。
  //   块标量 `|-` 的内容必须与 `prefix:` 键**同缩进**,超出即为块结束。
  const lines = readFileSync('cordis.patch.yml', 'utf8').split('\n')
  // `prefix:` 自身有前导缩进(在 persona 行内),故锚点必须允许缩进。
  // (初版用 /^prefix:/ 无缩进锚定 → findIndex 返回 -1 → 测试报的是锚点错,不是判据红)
  const startIdx = lines.findIndex((l) => /^\s*prefix: \|-\s*$/.test(l))
  assert.ok(startIdx >= 0, 'cordis.patch.yml 里找不到 `prefix: |-` 行')
  const indent = lines[startIdx].search(/\S/)
  const out = []
  for (let i = startIdx + 1; i < lines.length; i++) {
    const line = lines[i]
    if (line.trim() === '') { out.push(line); continue }
    if (line.search(/\S/) < indent) break  // 缩进回退 = 块标量结束
    out.push(line)
  }
  const persona = out.join('\n')
  // 自证:截断后不得再含 delegation 组或 YAML 键(那些属于 preset 配置,不是 persona)
  assert.doesNotMatch(persona, /^\s*-\s+id:\s+delegation/m,
    'personaPrefix() 截断越界,把 preset 的配置行吞进来了')
  assert.doesNotMatch(persona, /^#\s{2,}/m,
    'personaPrefix() 截断越界,把 YAML 注释吞进来了')
  return persona
}

function subagentConfig() {
  const patch = yaml.load(readFileSync('cordis.patch.yml', 'utf8'), { schema: yaml.JSON_SCHEMA.extend(JsExpr) })
  const decl = patch[0].insert[0]
  const delegation = decl.config.plugins.find((p) => p.id === 'delegation')
  assert.ok(delegation, '找不到 delegation 组')
  const row = delegation.config.find((r) => r.id === 'tool-subagent')
  assert.ok(row, 'delegation 组里找不到 tool-subagent 行')
  return row.config
}

test('A9-T1: persona 要求三路使用不同模型(异构),不只是「调 list_subagent_models」', () => {
  const persona = personaPrefix()
  // 正则必须能**跨行**匹配:persona 的实际措辞是
  // 「**三路必须使用不同模型**。同模型三路 = ...」后续解释另起一行。
  // (初版用 `[^\n]*模型`,行内匹配不到,属判据过严而非 persona 缺失)
  assert.match(persona, /三路[^。\n]{0,20}(?:必须使用不同模型|使用不同模型|模型不同|异构模型)/,
    'persona §三 3.3 未要求三路使用不同模型 —— 同模型三路共享盲区,独立性的前提不存在')
  // 「异构」不能只是形容词,必须可执行:要求每路显式指定 model
  assert.match(persona, /每路[^。\n]{0,40}(?:显式|分别|各自)[^。\n]{0,20}(?:指定|设置|传|给)/,
    'persona 未要求每路显式指定 model —— 不指定就等于全继承父会话 = 同模型三路')
  // 还要点名「同模型 = 假独立」这一后果,否则 agent 可能照三路同款跑
  assert.match(persona, /同模型[^。\n]{0,30}(?:盲区|假独立|共享)/,
    'persona 未说明同模型三路的后果(共享盲区/假独立) —— 纪律失去约束力')
})

test('A9-T2: persona 写明「不配 agentOptions」是有意的(否则会被当成漏配去修)', () => {
  const persona = personaPrefix()
  assert.match(persona, /agentOptions/,
    'persona 未提及 agentOptions —— 下个维护者会把「没配模型路由」当成漏配去补,'
    + '而补一个静态 agentOptions 只会把三路钉成**同一个**指定模型,缺陷原地不动')
  // 必须给出替代机制,否则等于让 agent 自生自灭。
  // 判据按**真实字段名**写:dsh-tool-subagent 的 hasDelegationModelRequest 读的是
  // 顶层 `provider` / `model` / `reasoning_effort`,不是某个嵌套对象。
  // (初版这里写的是 `model_selection`,与运行时实际字段名不符 —— 属新的 A1,已改)
  assert.match(persona, /单次调用覆盖/,
    'persona 只说了不配 agentOptions,却没给替代机制 —— 应指向单次调用顶层的 provider/model 覆盖')
  assert.match(persona, /顶层参数/,
    'persona 未点明覆盖发生在**顶层参数** —— 运行时读的就是顶层字段,不是嵌套对象')
  // provider 与 model 必须成对 —— 这是运行时的硬约束,persona 必须知道
  assert.match(persona, /成对/,
    'persona 未说明 provider 与 model 必须成对给出,而运行时会直接抛错')
})

test('A9-T3: tool-subagent 不钉死单个模型,且开启单次覆盖', () => {
  const cfg = subagentConfig()
  assert.equal(cfg.modelSelectionSettings, true,
    'modelSelectionSettings 必须为 true,否则单次调用的 provider/model 覆盖会抛 '
    + '"child model selection is disabled for this tool instance"')
  assert.equal(cfg.model, undefined,
    'tool-subagent 不得钉死 model:单个静态 model 会让三路**全部**变成同一个模型,'
    + '把同模型三路从「意外」变成「设计」')
  assert.equal(cfg.provider, 'spawn',
    'provider 应保持 spawn(进程级隔离);改成 fork 会退回同进程共享上下文')
  assert.equal(cfg.agentOptions, undefined,
    'Config.agentOptions 是单个静态对象,表达不了「三路三个模型」;'
    + '若要设,必须先确认三路确实需要不同模型而不是同一模型的三次重跑')
})

test('A9-T4: 运行时确实支持单次覆盖(persona 不能承诺代码做不到的事)', () => {
  // 直接读本机 DSH 运行时的实现 —— 证明「单次覆盖」不是空头承诺。
  // 若这段断言失败,说明 persona 的 T1/T2 要求指向了不存在的能力(即新的 A1)。
  const p = `${RUNTIME}/@deepseek-ai/dsh-tool-subagent/lib/index.js`
  assert.ok(existsSync(p), `找不到 subagent 工具实现:${p}`)
  const src = readFileSync(p, 'utf8')
  assert.match(src, /modelSelectionSettings/,
    '运行时 schema 里没有 modelSelectionSettings —— persona 关于单次覆盖的要求无依据')
  assert.match(src, /requestedAgentOptions/,
    '运行时没有 requestedAgentOptions 合并逻辑 —— 单次覆盖机制不存在或已改名,判据需重估')
  assert.match(src, /child model selection is disabled/,
    '未找到「单次覆盖被禁用」的报错文案 —— modelSelectionSettings 的作用需重新核实')
})
