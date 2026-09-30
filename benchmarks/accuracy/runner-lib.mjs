/**
 * 运行器纯逻辑(无网络,可单测)。
 */

/**
 * 各配置的作答约束前缀。
 * - C3 不加前缀:让 JEV persona 自己门控,这正是被测对象。
 * - C0/C1 是基线:禁子代理,故单 turn 即终结,`last.ended` 对它们有效。
 * - A1/A2 是「执行断言专项」的两臂(单路,禁子代理),差异**只有**是否强制跑断言库。
 */
export const CONFIG_PREFIX = {
  C0: '【评测约束】单次直答:不要调用任何工具、不要执行代码、不要派生子代理,直接推理给出答案。\n\n',
  C1: '【评测约束】单路作答:可以写代码并执行来计算和自检,但不要派生子代理(不要调用 subagent/workflow)。\n\n',
  C3: '',
  // 专项 A 组:两臂唯一差别 = 是否强制用断言库复算,用于隔离「执行断言」的净效应
  A1: '【评测约束】单路作答,**禁止执行任何代码**(不要调 pwsh/python/node,不要跑脚本):'
    + '只用推理算出答案。不要派生子代理。\n\n',
  A2: '【评测约束】单路作答,**必须真跑一次代码复算**(可用 pwsh 或 python):'
    + '把你算出的结果代入复算脚本验证,通过后再给答案。不要派生子代理。\n\n',
  // C3F:显式强制三路,用于复现「三路 vs 断言」实验。
  // 必要性(2026-09-30):persona 门控改为「断言优先」后,裸 C3 在计算类题上
  // **不再派生三路**(实测 sub=0),故无法再用 C3 复现 D 实验。此臂显式指定三路。
  C3F: '【评测约束】本任务必须走三路隔离采样:用 subagent 派生 3 个上下文隔离的'
    + '独立子代理(Path 1 严谨推导者 / Path 2 红队对抗者 / Path 3 极简执行者),'
    + '收齐 3 条结算通知后再裁决,不要走单路或 Fast-Pass。\n\n',
}

/** 从 session/page 的 records 里取最后一轮(最大 turn)的 assistant 文本与 turn/end 原因。 */
export function lastTurn(records) {
  const events = records.map((r) => r?.event ?? r).filter(Boolean)
  const turns = events.map((e) => e?.data?.turn).filter((t) => typeof t === 'number')
  if (turns.length === 0) return { turn: null, text: '', ended: false, endReason: null }
  const turn = Math.max(...turns)
  const texts = []
  let ended = false
  let endReason = null
  for (const e of events) {
    if (e?.data?.turn !== turn) continue
    if (e.type === 'assistant/message') {
      for (const b of e.data?.message?.content ?? []) {
        if (b?.type === 'text' && typeof b.text === 'string') texts.push(b.text)
      }
    }
    if (e.type === 'turn/end') {
      ended = true
      endReason = e.data?.reason?.kind ?? null
    }
  }
  return { turn, text: texts.join('\n'), ended, endReason }
}

/**
 * 仍在运行的子会话数。session/list 的 items 中 parentSessionId 指向本会话且 running=true 者。
 * 这是 JEV 三路是否结算完毕的客观判据(不依赖文本猜测)。
 */
export function runningChildren(list, sessionId) {
  return (list ?? []).filter((s) => s?.parentSessionId === sessionId && s?.running === true).length
}

/**
 * 本轮文本是否已含可判分的答案块(```json ... ```)。
 * 用于在子会话全部停止后立即收敛,避免固定空等。
 */
export function hasAnswerBlock(text) {
  return /```(?:json)?\s*\{[\s\S]*?\}\s*```/.test(text ?? '')
}

/**
 * 收敛判据:主会话本轮已结束,且无子会话在跑,且(已出答案块 或 静默已达阈值)。
 * @returns {boolean}
 */
export function converged({ ended, runningKids, hasAnswer, idleMs, settleMs }) {
  if (!ended || runningKids > 0) return false
  return hasAnswer || idleMs >= settleMs
}

/** 断点续跑:已完成且无错误的 (case_id, config, rep) 集合。 */
export function doneKeys(lines) {
  const done = new Set()
  for (const line of lines) {
    if (!line.trim()) continue
    const r = JSON.parse(line)
    if (!r.error) done.add(`${r.case_id}|${r.config}|${r.rep}`)
  }
  return done
}

/** 解析 argv:--k v / --flag;可重复的键收集为数组。 */
export function parseArgs(argv, repeatable = []) {
  const out = {}
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (!a.startsWith('--')) throw new Error(`无法识别的参数: ${a}`)
    const key = a.slice(2)
    const next = argv[i + 1]
    const val = next === undefined || next.startsWith('--') ? true : (i++, next)
    if (repeatable.includes(key)) (out[key] ??= []).push(val)
    else out[key] = val
  }
  return out
}
