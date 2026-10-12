// jev-client state 截断（头尾拼接）单元测试
//   node --test plugins/dsh-auto-reasoning/test/*.test.js
//
// 回归目标：原实现 `state.slice(0, 1500)` 只留头部，长 prompt 的收尾约束
// （「只输出 JSON」「不要解释」）会被整段丢掉 —— 这些用例锁住「尾部必须在」。
import test from 'node:test';
import assert from 'node:assert/strict';

import { trimState, STATE_BUDGET, STATE_HEAD_RATIO } from '../lib/jev-client.js';

test('trimState:不超预算时原样返回,不做任何改写', () => {
  const short = '判断这段任务需要多深的思考';
  assert.equal(trimState(short), short);
  assert.equal(trimState(''), '');
});

test('trimState:恰好等于预算时也原样返回(边界不触发截断)', () => {
  const exact = 'x'.repeat(STATE_BUDGET);
  assert.equal(trimState(exact), exact);
  assert.equal(trimState(exact).length, STATE_BUDGET);
});

test('trimState:超预算时长度【不超过】预算', () => {
  const long = 'y'.repeat(10_000);
  assert.ok(trimState(long).length <= STATE_BUDGET, '截断后不得超出预算');
  assert.equal(trimState(long).length, STATE_BUDGET, '应恰好用满预算');
});

test('trimState:【尾部必须保留】—— 这是本次修复的核心回归', () => {
  const tail = '只输出 JSON,不要解释。';
  const long = `${'a'.repeat(9_000)}${tail}`;
  const out = trimState(long);
  assert.ok(out.endsWith(tail), '收尾约束不得被丢掉');
});

test('trimState:头部也保留(开头交代任务)', () => {
  const head = '你是 JEV 执行体,先判后做。';
  const long = `${head}${'b'.repeat(9_000)}`;
  const out = trimState(long);
  assert.ok(out.startsWith(head), '开头必须保留');
});

test('trimState:中间被省略号替掉,不出现拼接错位', () => {
  const long = `${'h'.repeat(2_000)}${'m'.repeat(2_000)}${'t'.repeat(2_000)}`;
  const out = trimState(long);
  assert.ok(out.includes('…'), '应有省略号标记');
  assert.equal(out.split('…').length, 2, '省略号只应出现一次');
  // 头部保留量 = floor((budget-1) * ratio)
  const expectedHead = Math.floor((STATE_BUDGET - 1) * STATE_HEAD_RATIO);
  assert.equal(out.split('…')[0].length, expectedHead);
  assert.equal(out.split('…')[1].length, STATE_BUDGET - 1 - expectedHead);
});

test('trimState:默认比例是头 3/4、尾 1/4(照 magpie 的 3000/1000)', () => {
  assert.equal(STATE_HEAD_RATIO, 0.75);
  assert.equal(STATE_BUDGET, 1500);
});

test('trimState:自定义预算生效,且极小预算不崩', () => {
  const long = 'z'.repeat(100);
  assert.ok(trimState(long, 20).length <= 20);
  assert.equal(trimState(long, 2).length, 2);
  assert.equal(trimState(long, 1).length, 2, '预算下限为 2(1 字符内容 + 1 省略号)');
  assert.equal(trimState(long, 0).length, 2);
});

test('trimState:非字符串输入按字符串处理,不抛错', () => {
  assert.equal(trimState(null), '');
  assert.equal(trimState(undefined), '');
  assert.equal(trimState(12345), '12345');
});
