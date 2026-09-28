import { test } from 'node:test'
import assert from 'node:assert/strict'
import { CONFIG_PREFIX, doneKeys, lastTurn, parseArgs } from '../benchmarks/accuracy/runner-lib.mjs'

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
