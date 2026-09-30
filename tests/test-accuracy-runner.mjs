import { test } from 'node:test'
import assert from 'node:assert/strict'
import { CONFIG_PREFIX, converged, doneKeys, hasAnswerBlock, lastTurn, parseArgs, runningChildren } from '../benchmarks/accuracy/runner-lib.mjs'

const ev = (type, turn, extra = {}) => ({ type: 'event', event: { type, seq: 0, data: { turn, ...extra } } })
const msg = (turn, text) => ev('assistant/message', turn, { message: { content: [{ type: 'text', text }] } })

test('lastTurn 只取最大 turn 的文本,并识别 turn/end 原因', () => {
  const r = lastTurn([msg(1, '旧'), ev('turn/end', 1, { reason: { kind: 'completed' } }),
    msg(2, 'A'), ev('tool/call', 2), msg(2, 'B'), ev('turn/end', 2, { reason: { kind: 'error' } })])
  assert.deepEqual(r, { turn: 2, text: 'A\nB', ended: true, endReason: 'error' })
})

test('lastTurn 未结束 / 空记录', () => {
  assert.equal(lastTurn([msg(1, 'x')]).ended, false)
  assert.deepEqual(lastTurn([]), { turn: null, text: '', ended: false, endReason: null })
})

test('doneKeys 跳过失败行,使其重跑', () => {
  const d = doneKeys([
    JSON.stringify({ case_id: 'a', config: 'C1', rep: 0, text: 'ok' }),
    JSON.stringify({ case_id: 'b', config: 'C1', rep: 0, error: 'timeout' }),
    '',
  ])
  assert.ok(d.has('a|C1|0'))
  assert.ok(!d.has('b|C1|0'))
})

test('parseArgs 支持可重复键与布尔开关', () => {
  assert.deepEqual(parseArgs(['--config', 'C1', '--config', 'C3', '--dry-run', '--reps', '2'], ['config']),
    { config: ['C1', 'C3'], 'dry-run': true, reps: '2' })
  assert.throws(() => parseArgs(['oops']))
})

test('C3 不加约束前缀(被测对象由 persona 自行门控);基线前缀禁止派生子代理', () => {
  assert.equal(CONFIG_PREFIX.C3, '')
  assert.match(CONFIG_PREFIX.C0, /不要派生子代理/)
  assert.match(CONFIG_PREFIX.C1, /不要派生子代理/)
})

test('执行断言专项 A1/A2 两臂唯一差别 = 是否强制跑代码', () => {
  assert.match(CONFIG_PREFIX.A1, /禁止执行任何代码/)
  assert.match(CONFIG_PREFIX.A2, /必须真跑一次代码复算/)
  // 两臂都必须禁子代理,否则会混入「多路采样」这个额外变量
  assert.match(CONFIG_PREFIX.A1, /不要派生子代理/)
  assert.match(CONFIG_PREFIX.A2, /不要派生子代理/)
})

// ── 收敛判据(2026-09-30 修复的回归守卫)────────────────────────────────
// 历史缺陷:只等 `last.ended` 就收工。而 JEV 用 backgroundMode=continuable,
// 派发三路后父会话 turn **立即** completed(子代理仍在后台跑),导致
// runs-c30-c3-sb.jsonl 有 18/30 条停在「等结算」被误判为答错。
test('runningChildren 只数 running=true 的直接子会话', () => {
  const list = [
    { sessionId: 'p', parentSessionId: null, running: true },
    { sessionId: 'c1', parentSessionId: 'p', running: true },
    { sessionId: 'c2', parentSessionId: 'p', running: false },
    { sessionId: 'g1', parentSessionId: 'c1', running: true },   // 孙会话:不算
    { sessionId: 'x', parentSessionId: 'other', running: true }, // 别家的:不算
  ]
  assert.equal(runningChildren(list, 'p'), 1)
  assert.equal(runningChildren(list, 'c1'), 1)
  assert.equal(runningChildren([], 'p'), 0)
  assert.equal(runningChildren(undefined, 'p'), 0)
})

test('hasAnswerBlock 识别 ```json 答案块', () => {
  assert.equal(hasAnswerBlock('前言\n```json\n{"min_candies": "14"}\n```\n后记'), true)
  assert.equal(hasAnswerBlock('```json\n{"a":1}\n```'), true)
  assert.equal(hasAnswerBlock('只有文字,没有块'), false)
  assert.equal(hasAnswerBlock('```python\nprint(1)\n```'), false)
  assert.equal(hasAnswerBlock(''), false)
  assert.equal(hasAnswerBlock(undefined), false)
})

test('converged:子会话未停 / 本轮未结束 → 一律不收敛', () => {
  const base = { ended: true, runningKids: 0, hasAnswer: true, idleMs: 999999, settleMs: 120000 }
  assert.equal(converged(base), true)
  // 子代理仍在后台跑 —— 这正是历史误判的现场
  assert.equal(converged({ ...base, runningKids: 3 }), false)
  // turn 还没结束
  assert.equal(converged({ ...base, ended: false }), false)
})

test('converged:已出答案块可提前收工,否则须等静默达标', () => {
  const s = { ended: true, runningKids: 0, settleMs: 120000 }
  assert.equal(converged({ ...s, hasAnswer: true, idleMs: 0 }), true)      // 有答案立刻收
  assert.equal(converged({ ...s, hasAnswer: false, idleMs: 119999 }), false) // 无答案且未静默够
  assert.equal(converged({ ...s, hasAnswer: false, idleMs: 120000 }), true)  // 静默达标收
})
