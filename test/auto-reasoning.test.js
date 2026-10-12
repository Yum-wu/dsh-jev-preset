// dsh-auto-reasoning 单元测试（node --test）
//   node --test plugins/dsh-auto-reasoning/test/*.test.js
import test from 'node:test';
import assert from 'node:assert/strict';

import {
  AUTO_EFFORT_SENTINEL,
  SKIP_NONE,
  SKIP_NO_LADDER,
  SKIP_ERROR,
  SKIP_NO_PROMPT,
  createAutoEffortDecision,
  shouldTakeOver,
  promptFromInbox,
  promptFromEvents,
  promptFromFrozenMessages,
  textOfContent,
} from '../lib/index.js';
import { scoreTaskComplexity, projectEffortOntoLadder, decideReasoningEffort } from '../lib/auto-reasoning.js';
import {
  hashPrompt,
  buildCacheKey,
  EFFORT_CRITERIA,
  DEFAULT_ENDPOINT,
  DEFAULT_MODEL,
  FALLBACK_ENDPOINT,
  FALLBACK_MODEL,
  pickFallbackKey,
  parseRegQueryValue,
} from '../lib/jev-client.js';

test('哨兵值是 auto，且不属 cordis 合法档位', () => {
  assert.equal(AUTO_EFFORT_SENTINEL, 'auto');
  const legal = ['off', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max'];
  assert.ok(!legal.includes(AUTO_EFFORT_SENTINEL));
});

test('接管判据:哨兵 / 自己回音 / undefined(换模型子代理) 三条都接管', () => {
  assert.equal(shouldTakeOver({ reasoningEffort: 'auto' }, undefined).via, 'sentinel');
  assert.equal(shouldTakeOver({ reasoningEffort: 'high' }, 'high').via, 'echo');
  assert.equal(shouldTakeOver({ reasoningEffort: undefined }, 'high').via, 'orphan');
});

test('接管判据:用户手选档位(≠我上次写的)一律放行', () => {
  const r = shouldTakeOver({ reasoningEffort: 'low' }, 'high');
  assert.equal(r.take, false);
  // 2026-10-05 语义反转后，这里从 'none' 改名为 'handpicked' ——
  // 放行结论不变，但胶囊要靠这个名字显示「已让位给你手选的档位」，不再静默。
  assert.equal(r.via, 'handpicked');
});

test('接管判据:本插件从未写过(previousMine=undefined)时,具体档位不接管', () => {
  assert.equal(shouldTakeOver({ reasoningEffort: 'medium' }, undefined).take, false);
});

// ── 严格接管(UI 点击授权)────────────────────────────────────────────────
test('严格模式:strict=true 时任何 incoming 都接管,含用户手选档位', () => {
  assert.equal(shouldTakeOver({ reasoningEffort: 'low' }, undefined, true).via, 'forced');
  assert.equal(shouldTakeOver({ reasoningEffort: 'high' }, 'high', true).via, 'forced');
  assert.equal(shouldTakeOver({ reasoningEffort: 'auto' }, undefined, true).via, 'forced');
});

test('严格模式:strict 优先于其它判据(via 恒为 forced)', () => {
  assert.equal(shouldTakeOver({ reasoningEffort: 'auto' }, 'auto', true).via, 'forced');
  assert.equal(shouldTakeOver({ reasoningEffort: undefined }, undefined, true).via, 'forced');
});

// ── 默认接管 + 手选让位(2026-10-05 语义反转)─────────────────────────────
test('默认(非严格):哨兵 / 回音 / 孤儿 三条仍接管', () => {
  assert.equal(shouldTakeOver({ reasoningEffort: 'auto' }, undefined, false).take, true);
  assert.equal(shouldTakeOver({ reasoningEffort: 'high' }, 'high', false).via, 'echo');
  assert.equal(shouldTakeOver({ reasoningEffort: undefined }, 'high', false).via, 'orphan');
});

test('默认(非严格):incoming 是本插件没写过的具体档位 = 用户手选 → 让位', () => {
  // 「默认接管、遇手选中断」的全部实现就在这里，不依赖任何额外状态：
  // auto 接管后把自己选的档位写进 header，下一轮 incoming === 上次写的 → isMyEcho → 继续接管；
  // 用户一旦手选，incoming 变成别的档位 → 三条都不命中 → 让位。
  assert.deepEqual(shouldTakeOver({ reasoningEffort: 'low' }, undefined, false), { take: false, via: 'handpicked' });
  assert.deepEqual(shouldTakeOver({ reasoningEffort: 'high' }, 'low', false), { take: false, via: 'handpicked' });
  assert.deepEqual(shouldTakeOver({ reasoningEffort: 'medium' }, 'high', false), { take: false, via: 'handpicked' });
});

test('严格模式:能压过手选 —— 手选期间回到 auto 的唯一出口', () => {
  assert.equal(shouldTakeOver({ reasoningEffort: 'low' }, 'high', true).take, true);
});

test('严格模式:只有显式 true 才算开启,不接受 truthy 值', () => {
  // 严格模式会覆盖用户显式选择，宁可漏开不可误开。
  for (const v of ['true', 1, {}, 'yes', []]) {
    assert.equal(shouldTakeOver({ reasoningEffort: 'low' }, undefined, v).take, false, `不应因 ${JSON.stringify(v)} 开启`);
  }
});

test('阶梯投影:想要 high 时给 high 而不是 medium', () => {
  assert.equal(projectEffortOntoLadder(8, ['low', 'medium', 'high']).target, 'high');
  assert.equal(projectEffortOntoLadder(9, ['low', 'medium', 'high']).target, 'high');
});

test('阶梯投影:模型没有 high 就向下退,绝不报错档', () => {
  assert.equal(projectEffortOntoLadder(9, ['low', 'medium']).target, 'medium');
  assert.equal(projectEffortOntoLadder(9, ['minimal', 'low']).target, 'low');
});

test('阶梯投影:支持 xhigh/max 的模型按意图给满', () => {
  assert.equal(projectEffortOntoLadder(9, ['off', 'low', 'medium', 'high', 'xhigh', 'max']).target, 'max');
  assert.equal(projectEffortOntoLadder(7, ['off', 'low', 'medium', 'high', 'xhigh', 'max']).target, 'high');
});

test('阶梯投影:空阶梯 / 单档阶梯', () => {
  assert.equal(projectEffortOntoLadder(5, []).target, 'medium');
  assert.equal(projectEffortOntoLadder(5, ['high']).target, 'high');
});

test('规则评分:资金/并发高危得 9,已识别的日常工具型得 2', () => {
  assert.equal(scoreTaskComplexity('帮我查一下资金风控死锁状态机').score, 9);
  assert.equal(scoreTaskComplexity('帮我 grep 一下所有 TODO 的位置').score, 2);
});

// ── 默认档策略:2026-10-06 定案为 low（此前在 low/medium 之间反复过两次）──────
test('未命中任何特征时默认给 low —— 依据是真实 prompt 分布，不是直觉', () => {
  // 定案依据（120 条真实 prompt + SystemOne 打标，见 lib/auto-reasoning.js 注释）：
  //   未命中批 n=39，SystemOne 判 low 占 71.8%；默认 medium 只对 23.1%。
  //   未命中批长度中位 17 字符 —— 几乎全是短对话式追问，本就不需要深推理。
  const r = scoreTaskComplexity('帮我看看这个东西行不行');
  assert.equal(r.score, 2);
  assert.equal(r.reason, 'unmatched_default_low');

  // 反例守卫：真正的高危特征仍必须先被前面的分支拦下，不能被默认档吃掉
  assert.equal(scoreTaskComplexity('这个我不确定，可能是死锁').score, 9);
  // 反例守卫：常规开发特征也不得掉到默认档
  assert.equal(scoreTaskComplexity('帮我实现一个分页接口').score, 5);
});

test('低危过滤只收「读取已有内容」的意图,不收「产出新东西」的意图', () => {
  // `输出` / `显示` / `打印` 单独出现时两种意图都可能，所以只收带补语的形态。
  assert.equal(scoreTaskComplexity('把这个文件的第 42 行打印出来').score, 2);
  assert.equal(scoreTaskComplexity('README 里「快速开始」这一节讲了什么？').score, 2);
  // 「打印日志到文件」是开发任务，不该被 low 捞走
  assert.notEqual(scoreTaskComplexity('实现一个把日志打印到文件的模块').score, 2);
});

// ── 缓存键:2026-10-05 修的串味缺陷 ──────────────────────────────────────
test('hashPrompt:确定性,同输入必同输出', () => {
  assert.equal(hashPrompt('abc'), hashPrompt('abc'));
  assert.notEqual(hashPrompt('abc'), hashPrompt('abd'));
});

test('缓存键:前 300 字符相同但后面不同 → 必须不同键(原缺陷)', () => {
  // 原实现是 prompt.slice(0,300) 做键 —— 下面两条会共用同一条决策，
  // 而那条决策恰恰是「思考档位」：把资金死锁排查当成今天天气来定档，代价实且完全静默。
  const prefix = '先看一下这个项目的结构，然后'.padEnd(300, '。');
  const A = `${prefix}\n【任务A】今天天气怎么样？`;
  const B = `${prefix}\n【任务B】排查分布式死锁：爆仓清算并发写账户导致资金状态机卡死。`;
  assert.equal(A.slice(0, 300), B.slice(0, 300), '前置条件:前 300 字符确实完全相同');
  assert.notEqual(buildCacheKey('e', 'm', A), buildCacheKey('e', 'm', B), '★修复:两者不得共用缓存键');
});

test('缓存键:完全相同的 prompt 仍然命中缓存(别把缓存改没了)', () => {
  const P = '把这个函数改成 O(n) 并说明为什么正确。';
  assert.equal(buildCacheKey('e', 'm', P), buildCacheKey('e', 'm', P));
});

test('缓存键:endpoint / model 不同则键不同', () => {
  const P = '同样的任务描述';
  assert.notEqual(buildCacheKey('e1', 'm', P), buildCacheKey('e2', 'm', P));
  assert.notEqual(buildCacheKey('e', 'm1', P), buildCacheKey('e', 'm2', P));
});

test('缓存键:长度参与哈希,不同长度即使碰撞前缀也不混', () => {
  const P = 'x'.repeat(500);
  assert.notEqual(buildCacheKey('e', 'm', P), buildCacheKey('e', 'm', P + 'y'));
});

// ── criteria 覆盖度(2026-10-05 对齐官方分类法)──────────────────────────
test('criteria:五档齐全且都非空', () => {
  for (const k of ['low', 'medium', 'high', 'xhigh', 'max']) {
    assert.ok(EFFORT_CRITERIA[k]?.length > 10, `${k} 的描述缺失或过短`);
  }
});

test('criteria:low 必须覆盖 tool-use/planning/search(旧版漏了整类)', () => {
  const low = EFFORT_CRITERIA.low;
  for (const kw of ['工具', '规划', '搜索', '执行']) {
    assert.ok(low.includes(kw), `low 描述缺「${kw}」—— 这类日常会话会被误抬到 medium`);
  }
});

test('criteria:max 必须覆盖创造性深度工作(用户 2026-10-05 指出旧版只写资金场景)', () => {
  const max = EFFORT_CRITERIA.max;
  for (const kw of ['死锁', '爆仓', '算法重新设计', '边界']) {
    assert.ok(max.includes(kw), `max 描述缺「${kw}」`);
  }
});

test('criteria:xhigh 必须写明需要实测评估才用(官方原文门槛)', () => {
  assert.ok(EFFORT_CRITERIA.xhigh.includes('评估') || EFFORT_CRITERIA.xhigh.includes('实测'),
    '官方要求 xhigh「only use when your evals show a clear benefit」');
});

test('端到端规则决策产出合法档位', () => {
  const d = decideReasoningEffort('重构回测滑点模型', ['low', 'medium', 'high']);
  assert.ok(['low', 'medium', 'high'].includes(d.matchedEffort));
  assert.equal(typeof d.score, 'number');
});

test('取数:只认 source.kind===user,不把 AGENTS.md/技能目录当提示词', () => {
  const msgs = [
    { role: 'user', source: { kind: 'user' }, content: [{ type: 'text', text: '真实问题' }] },
    { role: 'user', source: { kind: 'skill-catalog' }, content: [{ type: 'text', text: '技能目录' }] },
  ];
  assert.equal(promptFromFrozenMessages({ frozenMessages: msgs }), '真实问题');
});

test('取数:inbox 与 events 两条路都能拿到文本', () => {
  const inbox = { nextTurn: [{ role: 'user', source: { kind: 'user' }, content: [{ type: 'text', text: '来自 inbox' }] }] };
  assert.equal(promptFromInbox({ inbox }), '来自 inbox');

  const session = {
    snapshotEvents: () => [
      { type: 'user/message', data: { source: { kind: 'user' }, content: [{ type: 'text', text: '来自 events' }] } },
    ],
  };
  assert.equal(promptFromEvents(session), '来自 events');
});

test('取数:空/脏输入不抛', () => {
  assert.equal(textOfContent(undefined), '');
  assert.equal(promptFromInbox(undefined), '');
  assert.equal(promptFromEvents(undefined), '');
  assert.equal(promptFromFrozenMessages({}), '');
});

// ── 「接管所有模型」的显式退出去向 ────────────────────────────────────────
// 静默回落是排障灾难：看到「auto 没生效」时分不清是插件没挂、模型没档、还是决策崩了。
test('退出去向是插件固有行为,三条都进决策对象(不是可选补丁)', () => {
  assert.equal(SKIP_NONE, null);
  assert.equal(SKIP_NO_LADDER, 'no-ladder');
  assert.equal(SKIP_ERROR, 'error');
  assert.equal(SKIP_NO_PROMPT, 'no-prompt');
});

test('无档位模型:决策对象带 skipped=no-ladder 且 effort 为 null', () => {
  const d = createAutoEffortDecision({
    sessionId: 's1',
    effort: null,
    skipped: SKIP_NO_LADDER,
    skippedDetail: 'adapter 未返回 reasoning.efforts',
    model: 'workbuddy2api/global:no-effort',
    ladder: [],
    via: 'sentinel',
  });
  assert.equal(d.effort, null);
  assert.equal(d.skipped, 'no-ladder');
  assert.ok(d.skippedDetail.includes('reasoning.efforts'));
});

test('成功决策默认 skipped=null;带 no-prompt 时仍出档但留痕', () => {
  const ok = createAutoEffortDecision({ sessionId: 's', effort: 'high', score: 8, model: 'm', ladder: ['high'] });
  assert.equal(ok.skipped, null);
  const degraded = createAutoEffortDecision({
    sessionId: 's',
    effort: 'low',
    score: 2,
    skipped: SKIP_NO_PROMPT,
    model: 'm',
    ladder: ['low', 'high'],
  });
  assert.equal(degraded.effort, 'low');
  assert.equal(degraded.skipped, 'no-prompt');
});

test('决策异常去向:error 带 detail,不留半成品 effort', () => {
  const d = createAutoEffortDecision({ sessionId: 's', skipped: SKIP_ERROR, skippedDetail: 'LlmError: INVALID_MODEL_REASONING', model: 'm' });
  assert.equal(d.skipped, 'error');
  assert.equal(d.effort, null);
  assert.match(d.skippedDetail, /INVALID_MODEL_REASONING/);
});

test('每条决策都带 model 与 at,便于排障对账', () => {
  const d = createAutoEffortDecision({ sessionId: 's', effort: 'medium', model: 'opencodex/x' });
  assert.equal(d.model, 'opencodex/x');
  assert.ok(Date.parse(d.at) > 0);
  assert.equal(d.depth, 0);
});

test('单档模型标记:ladder 为 1 时自动标记 singleTier=true, 多档或空阶梯为 false', () => {
  const single = createAutoEffortDecision({ sessionId: 's', effort: 'high', model: 'combo/ds-flash', ladder: ['high'] });
  assert.equal(single.singleTier, true);

  const multi = createAutoEffortDecision({ sessionId: 's', effort: 'high', model: 'm', ladder: ['low', 'high'] });
  assert.equal(multi.singleTier, false);

  const noLadder = createAutoEffortDecision({ sessionId: 's', effort: null, model: 'm', ladder: [] });
  assert.equal(noLadder.singleTier, false);
});

test('备用通道常数对齐 tools/jev_suite/core/client.py 的双通道设计', () => {
  assert.equal(FALLBACK_ENDPOINT, 'https://openrouter.ai/api/v1/systemone');
  assert.equal(FALLBACK_MODEL, 'typesafe/jev-1.13');
  // 备用端点必须与主端点不同，否则「切换」是空转（Python 侧同样以 endpoint 不等为前提）
  assert.notEqual(FALLBACK_ENDPOINT, DEFAULT_ENDPOINT);
  assert.notEqual(FALLBACK_MODEL, DEFAULT_MODEL);
});

test('备用密钥解析:专用变量优先于通用变量', () => {
  assert.equal(
    pickFallbackKey({ env: { JEV_FALLBACK_API_KEY: 'dedicated', OPENROUTER_API_KEY: 'generic' } }),
    'dedicated',
  );
  assert.equal(pickFallbackKey({ env: { OPENROUTER_API_KEY: 'generic' } }), 'generic');
});

test('备用密钥解析:无 env 时 Windows 走注册表, 非 Windows 直接放弃', () => {
  const reg = () =>
    '\r\nHKEY_CURRENT_USER\\Environment\r\n    OPENROUTER_API_KEY    REG_SZ    sk-or-v1-abc\r\n\r\n';
  assert.equal(pickFallbackKey({ env: {}, platform: 'win32', readRegistry: reg }), 'sk-or-v1-abc');

  // 非 Windows 没有这个机制 —— 不能假装探测到了什么
  let called = false;
  assert.equal(
    pickFallbackKey({ env: {}, platform: 'linux', readRegistry: () => { called = true; return reg(); } }),
    '',
  );
  assert.equal(called, false, '非 Windows 不该执行注册表读取');
});

test('备用密钥解析:注册表读取抛错时降级为空串,不把异常抛给调用方', () => {
  assert.equal(
    pickFallbackKey({ env: {}, platform: 'win32', readRegistry: () => { throw new Error('reg not found'); } }),
    '',
  );
});

test('reg query 输出解析:命中取值, 未命中/脏输入返回空串', () => {
  assert.equal(
    parseRegQueryValue('    OPENROUTER_API_KEY    REG_SZ    sk-or-v1-x\r\n'),
    'sk-or-v1-x',
  );
  assert.equal(parseRegQueryValue('ERROR: The system was unable to find the specified registry key'), '');
  assert.equal(parseRegQueryValue(''), '');
  assert.equal(parseRegQueryValue(null), '');
});
