// 发射台账（emissionLedger）单元测试
//   node --test plugins/dsh-jev-preset/test/*.test.js
//
// 不 mock 模块：给 `apply()` 一个最小假 ctx，捕获它注册的**真实**监听器，
// 再按 dsh-tools 的调用形状（waterfall: (exec, result, next)）驱动它们。
// 这样测的是插件的真实代码路径，而不是测试自己重写的副本。
import test from 'node:test';
import assert from 'node:assert/strict';

import { apply } from '../lib/index.js';

/** 起一个最小假 ctx：捕获 ctx.on 与 ctx.connection.fetch.register。 */
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
    // ⚠ 必须是 getter：filter 快照会在 apply() 之前求值，永远是空数组。
    get postExecute() {
      return handlers.filter((h) => h.name === 'tools/post-execute');
    },
    get sessionEvent() {
      return handlers.filter((h) => h.name === 'session/event');
    },
  };
}

/** 按 dsh-tools postExecute 的形状调用：监听器拿 (exec, result, next)。 */
function firePostExecute(harness, exec, result, downstream = { kind: 'accept' }) {
  const handler = harness.postExecute[0];
  assert.ok(handler, '未注册 tools/post-execute 监听器');
  return handler.fn(exec, result, () => Promise.resolve(downstream));
}

const subagentExec = (sessionId = 's1') => ({
  name: 'subagent',
  agent: { id: 'a1', session: { id: sessionId } },
});

/** 一轮新的人类输入 —— 台账应在此重置。 */
function fireNewUserMessage(harness, sessionId = 's1', text = '新任务') {
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

test('默认注册台账监听器，且是非阻塞的 global 监听', () => {
  const harness = makeCtx();
  apply(harness.ctx, {});
  assert.equal(harness.postExecute.length, 1, '默认应注册一条 tools/post-execute');
  assert.equal(harness.postExecute[0].opts?.global, true, '必须是 global，否则子作用域看不到');
});

test('emissionLedger=false 时完全不注册 —— 关掉不留半个监听器', () => {
  const harness = makeCtx();
  apply(harness.ctx, { emissionLedger: false });
  assert.equal(harness.postExecute.length, 0);
});

test('非 delegation 工具：原样放行，一个字符都不加', async () => {
  const harness = makeCtx();
  apply(harness.ctx, {});
  const result = { content: 'pwsh 输出' };
  const decision = await firePostExecute(harness, { name: 'pwsh', agent: { id: 'a1' } }, result);
  assert.deepEqual(decision, { kind: 'accept' });
  assert.equal(result.content, 'pwsh 输出', '不得就地改 result');
});

test('第一次发射：台账追加在结果尾部，计数 1、预算剩 2', async () => {
  const harness = makeCtx();
  apply(harness.ctx, {});
  const decision = await firePostExecute(harness, subagentExec(), { content: 'started subagent p1' });
  assert.equal(decision.kind, 'accept');
  assert.ok(decision.content.startsWith('started subagent p1'), '原文必须完整保留在前面');
  assert.ok(decision.content.includes('[JEV 发射台账] 本轮实际发射 1 路'), decision.content);
  assert.ok(decision.content.includes('subagent×1'), '要给出工具分布');
  assert.ok(decision.content.includes('预算剩 2'), decision.content);
});

test('第三次发射：预算用尽文案；第四次：超预算必须警告不得写满额标识', async () => {
  const harness = makeCtx();
  apply(harness.ctx, {});
  const exec = subagentExec();
  let last;
  for (let i = 0; i < 4; i += 1) last = await firePostExecute(harness, exec, { content: `r${i}` });
  assert.ok(last.content.includes('本轮实际发射 4 路'), last.content);
  assert.ok(last.content.includes('已超预算 3'), last.content);
  assert.ok(last.content.includes('不得写满额标识'), last.content);

  // 第三次单独验「用尽」那一档文案
  const fresh = makeCtx();
  apply(fresh.ctx, {});
  await firePostExecute(fresh, exec, { content: 'a' });
  await firePostExecute(fresh, exec, { content: 'b' });
  const third = await firePostExecute(fresh, exec, { content: 'c' });
  assert.ok(third.content.includes('预算用尽(3)'), third.content);
});

test('下游已改写 content 时在其上追加，不丢下游内容', async () => {
  const harness = makeCtx();
  apply(harness.ctx, {});
  const decision = await firePostExecute(harness, subagentExec(), { content: '原始' }, {
    kind: 'accept',
    content: '下游改写后的内容',
  });
  assert.ok(decision.content.startsWith('下游改写后的内容'), decision.content);
  assert.ok(decision.content.includes('[JEV 发射台账]'), '台账仍要追加');
});

test('新一轮人类输入把台账清零 —— 预算按轮算，不跨轮累积', async () => {
  const harness = makeCtx();
  apply(harness.ctx, {});
  const exec = subagentExec();
  await firePostExecute(harness, exec, { content: 'a' });
  await firePostExecute(harness, exec, { content: 'b' });
  fireNewUserMessage(harness, 's1');
  const after = await firePostExecute(harness, exec, { content: 'c' });
  assert.ok(after.content.includes('本轮实际发射 1 路'), after.content);
});

test('台账按会话隔离：另一个会话不共享计数', async () => {
  const harness = makeCtx();
  apply(harness.ctx, {});
  await firePostExecute(harness, subagentExec('s1'), { content: 'a' });
  await firePostExecute(harness, subagentExec('s1'), { content: 'b' });
  const other = await firePostExecute(harness, subagentExec('s2'), { content: 'c' });
  assert.ok(other.content.includes('本轮实际发射 1 路'), other.content);
});

test('content 不是字符串时不追加，也不抛（result 形状不受插件假定）', async () => {
  const harness = makeCtx();
  apply(harness.ctx, {});
  const decision = await firePostExecute(harness, subagentExec(), { content: { blocks: [] } });
  assert.deepEqual(decision, { kind: 'accept' });
  assert.ok(
    !harness.logs.some(([, line]) => line.includes('台账追加失败')),
    '这不是异常路径，不该走 warn',
  );
});

test('监听器内部抛错不得变成工具失败：捕获后原样放行', async () => {
  const harness = makeCtx();
  apply(harness.ctx, {});
  // 让 emissionKey 的读取抛错：session 是 getter。
  const exec = { name: 'subagent', agent: {} };
  Object.defineProperty(exec.agent, 'session', {
    get() {
      throw new Error('boom');
    },
  });
  const decision = await firePostExecute(harness, exec, { content: 'x' });
  assert.deepEqual(decision, { kind: 'accept' }, '必须放行，不得把工具调用变成 isError');
  assert.ok(
    harness.logs.some(([level, line]) => level === 'warn' && line.includes('台账追加失败')),
    '吞掉也要留痕，否则排障无从下手',
  );
});

test('每次发射写一条 info 日志（事后审计入口之一）', async () => {
  const harness = makeCtx();
  apply(harness.ctx, {});
  await firePostExecute(harness, subagentExec('s9'), { content: 'a' });
  const line = harness.logs.find(([, text]) => text.includes('jev-emission:'));
  assert.ok(line, '缺 jev-emission 日志行');
  assert.ok(line[1].includes('s9'), line[1]);
  assert.ok(line[1].includes('本轮第 1 路'), line[1]);
});

test('GET 端点暴露 emissions，供外部核对标识路数', async () => {
  const harness = makeCtx();
  apply(harness.ctx, {});
  const route = harness.routes.get('/api/auto-reasoning.effort');
  assert.equal(typeof route, 'function', '缺 /api/auto-reasoning.effort 路由');
  await firePostExecute(harness, subagentExec('s1'), { content: 'a' });

  const response = await route(new Request('http://localhost/api/auto-reasoning.effort?sessionId=s1'));
  const body = await response.json();
  assert.equal(body.emissionLedger, true);
  assert.equal(body.emissionBudget, 3);
  assert.equal(body.emissions.count, 1);
  assert.deepEqual(body.emissions.byTool, { subagent: 1 });
});
