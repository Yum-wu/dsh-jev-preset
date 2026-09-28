/**
 * 运行器纯逻辑(无网络,可单测)。
 */

/** 各配置的作答约束前缀。C3 不加前缀:让 JEV persona 自己门控,这正是被测对象。 */
export const CONFIG_PREFIX = {
  C0: '【评测约束】单次直答:不要调用任何工具、不要执行代码、不要派生子代理,直接推理给出答案。\n\n',
  C1: '【评测约束】单路作答:可以写代码并执行来计算和自检,但不要派生子代理(不要调用 subagent/workflow)。\n\n',
  C3: '',
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
