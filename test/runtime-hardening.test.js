// auto-reasoning 运行时加固回归(2026-10-14 审计修复)
//
// 本文件钉的是 2026-10-14 只读审计发现的、**当时可复现**的缺陷。每条用例的注释里
// 写明「修复前的行为」,以便将来有人重构时知道这条在守什么。
//
// 不 mock 模块:给 apply() 一个最小假 ctx,捕获它注册的**真实**监听器再驱动,
// 测的是插件代码本身而不是测试重写的副本。
//
//   node --test test/*.test.js
import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';

import { apply, AUTO_EFFORT_SENTINEL } from '../lib/index.js';
import {
  projectEffortOntoLadder,
  decideReasoningEffort,
  decideReasoningEffortAsync,
} from '../lib/auto-reasoning.js';
import { queryJevReasoningEffort } from '../lib/jev-client.js';

const LADDER = ['low', 'medium', 'high'];

// ── 夹具 ────────────────────────────────────────────────────────────────────

function makeCtx() {
  const handlers = [];
  const routes = new Map();
  const logs = [];
  const ctx = {
    on(name, fn, opts) {
      handlers.push({ name, fn, opts });
    },
    logger: {
      info: (line) => logs.push(['info', String(line)]),
      warn: (line) => logs.push(['warn', String(line)]),
    },
    llm: {
      resolveModelInfo: async () => ({ reasoning: { efforts: LADDER.map((id) => ({ id })) } }),
    },
    connection: {
      fetch: {
        register({ path, fetch }) {
          routes.set(path, fetch);
        },
      },
    },
  };
  return {
    ctx,
    logs,
    routes,
    handlers,
    get agentRequest() {
      return handlers.filter((h) => h.name === 'agent/request');
    },
    get postExecute() {
      return handlers.filter((h) => h.name === 'tools/post-execute');
    },
    get sessionEvent() {
      return handlers.filter((h) => h.name === 'session/event');
    },
  };
}

/** 按 cordis waterfall 形状驱动 agent/request:(payload, next)。 */
function fireRequest(harness, sessionId, resolved) {
  const handler = harness.agentRequest[0];
  assert.ok(handler, '未注册 agent/request 监听器');
  return handler.fn({ agent: { id: sessionId, session: { id: sessionId } } }, () =>
    Promise.resolve(resolved),
  );
}

function fireNewUserMessage(harness, sessionId, text) {
  const handler = harness.sessionEvent[0];
  assert.ok(handler, '未注册 session/event 监听器');
  handler.fn({ id: sessionId }, {
    type: 'agent/inbox/spliced',
    data: {
      target: 'next-turn',
      inserted: [{ role: 'user', source: { kind: 'user' }, content: [{ type: 'text', text }] }],
    },
  });
}

async function readEffort(harness, sessionId = '') {
  const route = harness.routes.get('/api/auto-reasoning.effort');
  assert.ok(route, '未注册 /api/auto-reasoning.effort');
  const res = await route({ url: `http://x/api/auto-reasoning.effort?sessionId=${sessionId}` });
  return res.json();
}

/** 起一个本地假 SystemOne(不出网),按需返回响应体。 */
async function withStubSystemOne(bodyFn, fn) {
  const server = http.createServer((req, res) => {
    let body = '';
    req.on('data', (chunk) => {
      body += chunk;
    });
    req.on('end', () => {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(bodyFn()));
    });
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const { port } = server.address();

  const savedEnv = process.env.NODE_ENV;
  const savedDisable = process.env.DISABLE_JEV_REMOTE;
  delete process.env.NODE_ENV;
  delete process.env.DISABLE_JEV_REMOTE;
  try {
    return await fn({ endpoint: `http://127.0.0.1:${port}/v1/systemone` });
  } finally {
    if (savedEnv !== undefined) process.env.NODE_ENV = savedEnv;
    if (savedDisable !== undefined) process.env.DISABLE_JEV_REMOTE = savedDisable;
    await new Promise((resolve) => server.close(resolve));
  }
}

// ── D3:投影层不得吐出哨兵 ──────────────────────────────────────────────────

test('[D3] projectEffortOntoLadder 任何输入都不得吐出哨兵 auto', () => {
  // 修复前:projectEffortOntoLadder(8, ['off','auto']).target === 'auto'
  //   —— 插值分支把阶梯里任意元素原样吐出,包括哨兵。
  // 吐出去就会被 index.js 写回宿主,dsh-llm 的档位枚举随即抛
  // UNSUPPORTED_REASONING_EFFORT。
  assert.notEqual(projectEffortOntoLadder(8, ['off', 'auto']).target, AUTO_EFFORT_SENTINEL);
  assert.notEqual(projectEffortOntoLadder(1, ['auto']).target, AUTO_EFFORT_SENTINEL);

  const legal = ['off', 'minimal', 'low', 'medium', 'high', 'xhigh', 'max'];
  const ladders = [legal, legal.slice(0, 3), LADDER, ['high'], ['low', 'high', 'xhigh']];
  for (const ladder of ladders) {
    for (let score = 1; score <= 10; score += 1) {
      const { target } = projectEffortOntoLadder(score, ladder);
      assert.notEqual(target, AUTO_EFFORT_SENTINEL, `ladder=${ladder} score=${score} 吐出了哨兵`);
      assert.ok(ladder.includes(target), `ladder=${ladder} score=${score} 投影出阶梯外的 ${target}`);
    }
  }
});

test('[D3] 决策链路的输出档位恒为合法值(含哨兵混入的阶梯)', () => {
  for (const ladder of [['off', 'auto'], ['auto', 'low', 'auto'], ['auto']]) {
    for (const prompt of ['改吧', '实现一个分页组件', '重新设计整个并发状态机,防止死锁']) {
      const { matchedEffort } = decideReasoningEffort(prompt, ladder);
      assert.notEqual(matchedEffort, AUTO_EFFORT_SENTINEL, `ladder=${ladder} 输出哨兵`);
    }
  }
});

// ── D2:passthrough 出口也必须剥离哨兵 ──────────────────────────────────────

test('[D2] enabled:false 时 passthrough 必须剥离 auto 哨兵,不得原样交回宿主', async () => {
  // 修复前:returned.reasoningEffort === 'auto' —— 禁用插件本是为了排障,
  // 结果宿主抛 UNSUPPORTED_REASONING_EFFORT,直接把会话打死。
  const harness = makeCtx();
  apply(harness.ctx, { enabled: false });

  const returned = await fireRequest(harness, 'M1', {
    provider: 'p',
    model: 'm',
    reasoningEffort: AUTO_EFFORT_SENTINEL,
  });

  assert.ok(!('reasoningEffort' in returned), `哨兵必须被剥离,实得 ${JSON.stringify(returned)}`);
  assert.equal(returned.model, 'm', '其余字段必须逐字保留');
});

test('[D2] enabled:false 时非哨兵档位原样放行(剥离只针对哨兵)', async () => {
  const harness = makeCtx();
  apply(harness.ctx, { enabled: false });

  const returned = await fireRequest(harness, 'M1', { model: 'm', reasoningEffort: 'high' });
  assert.equal(returned.reasoningEffort, 'high');
});

// ── D1:回声记忆必须活得比决策缓存久 ────────────────────────────────────────

test('[D1] 决策缓存被挤出后,宿主回传的自家档位仍判 echo,不得误判成用户手选', async () => {
  // 修复前:autoDecisions 同时当「胶囊展示缓存」与「回声记忆」用,按 decisionCap 淘汰。
  // 在「每个子代理都是独立会话」的工作区里,主会话记录被挤掉 ⇒ 宿主回传的、
  // 我自己上轮写的档位被判 handpicked ⇒ 该会话 auto 静默失效,胶囊还把责任栽给用户。
  const harness = makeCtx();
  apply(harness.ctx, { decisionCap: 2 }); // 极小 cap,把「被挤掉」变成确定性事件

  // 第一轮:哨兵 → 接管,写下本轮档位
  fireNewUserMessage(harness, 'M1', '改吧');
  const first = await fireRequest(harness, 'M1', { model: 'm', reasoningEffort: AUTO_EFFORT_SENTINEL });
  const written = first.reasoningEffort;
  assert.ok(LADDER.includes(written), `插件应写出合法档位,实得 ${written}`);

  // 三个其它会话各走一轮,把 decisionCap=2 的缓存彻底挤掉
  for (const other of ['X1', 'X2', 'X3']) {
    await fireRequest(harness, other, { model: 'm', reasoningEffort: AUTO_EFFORT_SENTINEL });
  }

  // 主会话下一轮:宿主回传的正是**我自己上轮写的**档位
  await fireRequest(harness, 'M1', { model: 'm', reasoningEffort: written });

  const stats = await readEffort(harness, 'M1');
  assert.equal(
    stats.lastTakeoverVia,
    'echo',
    '宿主回传自家档位必须判 echo;判成 handpicked 说明回声记忆被挤掉了',
  );
});

// ── D6:lastHandpickedEffort 必须带上限 ─────────────────────────────────────

test('[D6] 手选记录按 decisionCap 淘汰,不再无界增长', async () => {
  // 修复前:这是全插件唯一没有 cap 的 Map,每个手选过的会话留一条,永不回收。
  const harness = makeCtx();
  apply(harness.ctx, { decisionCap: 2 });

  for (const id of ['H1', 'H2', 'H3']) {
    // 具体档位 + 无我方记录 → handpicked(用户手选)
    await fireRequest(harness, id, { model: 'm', reasoningEffort: 'high' });
  }

  assert.equal((await readEffort(harness, 'H1')).handpickedEffort, null, '最旧的应被淘汰');
  assert.equal((await readEffort(harness, 'H3')).handpickedEffort, 'high', '最新的应保留');
});

// ── D7/D8:confidence 缺省与后端身份 ────────────────────────────────────────

test('[D7] 后端没给 confidence 时不得伪造 1.0', async () => {
  await withStubSystemOne(
    () => ({ model: 'stub', answers: { effort: { type: 'choice', choice: 'high' } } }),
    async ({ endpoint }) => {
      const res = await queryJevReasoningEffort('列一下仓库里都有哪些插件目录', {
        endpoint,
        fallbackEndpoint: '',
      });
      assert.equal(res.tier, 'high');
      assert.equal(res.confidence, null, '缺省必须是 null(未知),不能是 1.0(100% 确信)');
    },
  );
});

test('[D7] 后端给了 confidence 时原样透传', async () => {
  await withStubSystemOne(
    () => ({ model: 'stub', answers: { effort: { type: 'choice', choice: 'low', confidence: 0.42 } } }),
    async ({ endpoint }) => {
      const res = await queryJevReasoningEffort('把 README 里的命令全跑一遍看看', {
        endpoint,
        fallbackEndpoint: '',
      });
      assert.equal(res.confidence, 0.42);
    },
  );
});

test('[D8] 决策对象带 backend 列,能看出走了主通道还是备用通道', async () => {
  await withStubSystemOne(
    () => ({ model: 'stub', answers: { effort: { type: 'choice', choice: 'high', confidence: 0.9 } } }),
    async ({ endpoint }) => {
      const decision = await decideReasoningEffortAsync('实现一个分页组件', LADDER, {
        endpoint,
        fallbackEndpoint: '',
      });
      assert.equal(decision.source, 'jev-model', 'source 是既有公开契约,不改');
      assert.equal(decision.backend, 'jev-model', 'backend 必须暴露后端身份');
    },
  );
});

// ── D5:降级路径必须留痕 ────────────────────────────────────────────────────

test('[D5] 决策链路抛异常时留痕,不再与「没开远程」逐字相同', async () => {
  const savedEnv = process.env.NODE_ENV;
  const savedDisable = process.env.DISABLE_JEV_REMOTE;
  delete process.env.NODE_ENV;
  delete process.env.DISABLE_JEV_REMOTE;
  try {
    // model 的 toString 抛错 → queryJevReasoningEffort 在构造缓存键时抛出,
    // 该抛出点在它自己的 try 之外,故会传播到 decideReasoningEffortAsync 的 catch。
    const boom = {
      toString() {
        throw new Error('boom-from-model');
      },
    };
    const decision = await decideReasoningEffortAsync('实现一个分页组件', LADDER, {
      model: boom,
      fallbackEndpoint: '',
    });
    assert.equal(decision.source, 'jev-error-rule', '抛异常必须与「没开远程」区分开');
    assert.ok(decision.reason.includes('jev_error'), `reason 要留痕,实得 ${decision.reason}`);
    assert.ok(LADDER.includes(decision.matchedEffort), '仍要给出合法档位');
    assert.ok(String(decision.error).includes('boom-from-model'), '原始错误要带上');
  } finally {
    if (savedEnv !== undefined) process.env.NODE_ENV = savedEnv;
    if (savedDisable !== undefined) process.env.DISABLE_JEV_REMOTE = savedDisable;
  }
});

// ── D9:发射台账不得退化成共享常量 ──────────────────────────────────────────

test('[D9] 拿不到会话 id 时不计数 —— 记到共享常量上会跨轮永久累积', async () => {
  const harness = makeCtx();
  apply(harness.ctx, {});
  const handler = harness.postExecute[0];
  assert.ok(handler, '未注册 tools/post-execute 监听器');

  // exec 不带 agent → 归属不到会话
  const decision = await handler.fn({ name: 'subagent' }, { content: [{ type: 'text', text: 'r' }] }, () =>
    Promise.resolve({ kind: 'accept' }),
  );

  assert.deepEqual(decision, { kind: 'accept' }, '无归属时必须原样放行,一个字符都不加');
});

test('[D9] 有会话 id 时照常计数,且按会话隔离', async () => {
  const harness = makeCtx();
  apply(harness.ctx, {});
  const handler = harness.postExecute[0];
  const exec = { name: 'subagent', agent: { id: 'a1', session: { id: 's1' } } };
  // 下游只回 {kind:'accept'} 时基线退回原始 result.content —— 那是**块数组**,
  // 台账作为第二个 text 块追加,故要拼全部块而不是只看第 0 块。
  const textOf = (content) => content.map((b) => String(b.text ?? '')).join('\n');

  const first = await handler.fn(exec, { content: [{ type: 'text', text: 'r' }] }, () =>
    Promise.resolve({ kind: 'accept' }),
  );
  assert.ok(textOf(first.content).includes('本轮实际发射 1 路'), JSON.stringify(first));

  // 另一个会话不共享计数
  const other = await handler.fn({ ...exec, agent: { id: 'a2', session: { id: 's2' } } }, { content: [{ type: 'text', text: 'r' }] }, () =>
    Promise.resolve({ kind: 'accept' }),
  );
  assert.ok(textOf(other.content).includes('本轮实际发射 1 路'), '不得串味');
});

// ── D4:同会话并发写入不得让回声记忆判错 ────────────────────────────────────

test('[D4] 同会话先后写入两个档位,宿主回传任一都判 echo,不得误判成用户手选', async () => {
  // 修复前:myWrittenEffort 存**单值**,后写者胜。同会话并发时宿主持久化的
  //   可能是先写者那个值 ⇒ 下一轮回传它与单值记忆不等 ⇒ 判 handpicked ⇒
  //   该会话 auto 静默失效。A/B 谁被持久化取决于时序,不是「最后一次决策」。
  const harness = makeCtx();
  apply(harness.ctx, {});

  fireNewUserMessage(harness, 'C1', '改吧');
  const first = await fireRequest(harness, 'C1', { model: 'm', reasoningEffort: AUTO_EFFORT_SENTINEL });

  fireNewUserMessage(harness, 'C1', '重新设计整个并发状态机,防止死锁');
  const second = await fireRequest(harness, 'C1', { model: 'm', reasoningEffort: AUTO_EFFORT_SENTINEL });

  assert.notEqual(
    first.reasoningEffort,
    second.reasoningEffort,
    `两个提示词必须投影出不同档位,否则本用例无意义(实得 ${first.reasoningEffort})`,
  );

  await fireRequest(harness, 'C1', { model: 'm', reasoningEffort: first.reasoningEffort });
  assert.equal((await readEffort(harness, 'C1')).lastTakeoverVia, 'echo', '先写者的值必须判 echo');

  await fireRequest(harness, 'C1', { model: 'm', reasoningEffort: second.reasoningEffort });
  assert.equal((await readEffort(harness, 'C1')).lastTakeoverVia, 'echo', '后写者的值必须判 echo');
});

// ── D10:echo 与手选的不可分辨性必须可观测 ──────────────────────────────────

test('[D10] echo 判定必须留痕 —— 协议层不可分辨,但不得静默', async () => {
  // 用户手选的档位**恰好等于**我上轮写进去的值时,echo 与 handpicked 是同一个状态,
  // 协议层无法区分。本插件不猜(误判 handpicked 会让 auto 永久失效,代价更大),
  // 但必须可观测 —— 否则「auto 怎么没让位」永远查不出是判了 echo。
  const harness = makeCtx();
  apply(harness.ctx, {});

  fireNewUserMessage(harness, 'A1', '改吧');
  const written = (await fireRequest(harness, 'A1', { model: 'm', reasoningEffort: AUTO_EFFORT_SENTINEL }))
    .reasoningEffort;

  const before = (await readEffort(harness, 'A1')).ambiguousEchoes;
  await fireRequest(harness, 'A1', { model: 'm', reasoningEffort: written });
  const after = await readEffort(harness, 'A1');

  assert.equal(after.lastTakeoverVia, 'echo');
  assert.equal(after.lastTakeoverAmbiguous, true, 'echo 必须标 ambiguous');
  assert.equal(after.ambiguousEchoes, before + 1, '计数必须递增');
});

// ── D11:RPC 回显面不得跨会话泄漏 ────────────────────────────────────────────

test('[D11] 未显式传 sessionId 时不回显跨会话内容', async () => {
  // 原实现:sessionId === '' 时回退返回全库最后一条决策,并连带回显
  //   lastPromptText(用户真实提示词前 80 字符)、sessions(全部会话 id)、
  //   forcedSessions。三者都是跨会话的,而「没传 sessionId」的调用者未必是那个会话。
  const harness = makeCtx();
  apply(harness.ctx, {});

  fireNewUserMessage(harness, 'S1', '这是我的私密提示词');
  await fireRequest(harness, 'S1', { model: 'm', reasoningEffort: AUTO_EFFORT_SENTINEL });

  const anon = await readEffort(harness, '');
  assert.equal(anon.lastPromptText, undefined, '匿名查询不得回显最近提示词');
  assert.equal(anon.sessions, undefined, '匿名查询不得枚举会话 id');
  assert.equal(anon.forcedSessions, undefined, '匿名查询不得枚举强制接管会话');

  const explicit = await readEffort(harness, 'S1');
  assert.ok(
    typeof explicit.lastPromptText === 'string' && explicit.lastPromptText !== '',
    '显式指定会话时仍应拿得到(调试需要)',
  );
  assert.deepEqual(explicit.sessions, ['S1'], '显式指定时只应看到该会话');
});

// ── D12:alwaysTakeOver —— UI 固化值不得让 auto 空转 ─────────────────────────

test('[D12] alwaysTakeOver=false(默认)时,具体档位仍判 handpicked —— 保留手选语义', async () => {
  const harness = makeCtx();
  apply(harness.ctx, {});
  await fireRequest(harness, 'P1', { model: 'm', reasoningEffort: 'high' });
  assert.equal((await readEffort(harness, 'P1')).lastTakeoverVia, 'handpicked');
});

test('[D12] alwaysTakeOver=true 时 UI 固化档位必须被接管 —— 否则 auto 对历史会话全空转', async () => {
  // 实测背景(2026-10-14):958 个会话 projcache 里 906 个带 reasoningEffort,
  //   本会话那条还停在旧模型 global 版 + high。宿主每轮回传那个固化值,
  //   不打开本开关时插件每轮都判 handpicked 让位 —— 实测 seen=5 / takenOver=0。
  const harness = makeCtx();
  apply(harness.ctx, { alwaysTakeOver: true });

  fireNewUserMessage(harness, 'P2', '重新设计整个并发状态机,防止死锁');
  const returned = await fireRequest(harness, 'P2', { model: 'm', reasoningEffort: 'high' });
  const stats = await readEffort(harness, 'P2');

  assert.equal(stats.lastTakeoverVia, 'always');
  assert.equal(stats.takenOver, 1);
  assert.ok(
    LADDER.includes(returned.reasoningEffort),
    `必须换成插件算出的档位,实得 ${returned.reasoningEffort}`,
  );
});

test('[D12] alwaysTakeOver=true 也不得把哨兵漏给宿主', async () => {
  const harness = makeCtx();
  apply(harness.ctx, { alwaysTakeOver: true });
  const returned = await fireRequest(harness, 'P3', { model: 'm', reasoningEffort: AUTO_EFFORT_SENTINEL });
  assert.notEqual(returned.reasoningEffort, AUTO_EFFORT_SENTINEL);
  assert.ok(LADDER.includes(returned.reasoningEffort));
});
