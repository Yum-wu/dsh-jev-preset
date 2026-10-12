// 「不适用」出口（declineOption）单元测试
//   node --test plugins/dsh-auto-reasoning/test/*.test.js
//
// 不 mock 模块：起一个本地假 SystemOne，让**真实链路**跑一遍，
// 既能断言「送给模型的 criteria 长什么样」，也能断言「模型答回来之后插件怎么处置」。
import test from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';

import {
  EFFORT_CRITERIA,
  EFFORT_CRITERIA_WITH_DECLINE,
  EFFORT_NOT_APPLICABLE,
  buildCacheKey,
  hashPrompt,
} from '../lib/jev-client.js';
import { decideReasoningEffortAsync } from '../lib/auto-reasoning.js';

/**
 * 起一个假 SystemOne，记录收到的 payload，固定返回 `choice`。
 *
 * 期间摘掉 `NODE_ENV=test` 与 `DISABLE_JEV_REMOTE` —— `decideReasoningEffortAsync`
 * 见到这两个会直接走规则引擎，那就测不到 Jev 分支了。测试结束原样还原。
 * `fallbackEndpoint: ''` 显式关掉备用通道，保证不出网。
 */
async function withStubSystemOne(choice, fn) {
  const seen = [];
  const server = http.createServer((req, res) => {
    let body = '';
    req.on('data', (chunk) => {
      body += chunk;
    });
    req.on('end', () => {
      try {
        seen.push(JSON.parse(body));
      } catch {
        seen.push(null);
      }
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(
        JSON.stringify({
          model: 'stub',
          answers: {
            effort: { type: 'choice', choice, confidence: 0.87, probabilities: { [choice]: 0.87 } },
          },
          usage: { input_tokens: 1, output_tokens: 1 },
        }),
      );
    });
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const { port } = server.address();

  const savedNodeEnv = process.env.NODE_ENV;
  const savedDisable = process.env.DISABLE_JEV_REMOTE;
  delete process.env.NODE_ENV;
  delete process.env.DISABLE_JEV_REMOTE;
  try {
    return await fn({ endpoint: `http://127.0.0.1:${port}/v1/systemone`, seen });
  } finally {
    if (savedNodeEnv !== undefined) process.env.NODE_ENV = savedNodeEnv;
    if (savedDisable !== undefined) process.env.DISABLE_JEV_REMOTE = savedDisable;
    await new Promise((resolve) => server.close(resolve));
  }
}

test('默认 criteria 不含「不适用」出口;开启版只多这一档,原 5 档逐字不变', () => {
  assert.equal(EFFORT_NOT_APPLICABLE, 'not_applicable');

  assert.ok(!(EFFORT_NOT_APPLICABLE in EFFORT_CRITERIA), '默认 criteria 不得含出口档');
  assert.deepEqual(Object.keys(EFFORT_CRITERIA), ['low', 'medium', 'high', 'xhigh', 'max']);

  for (const key of Object.keys(EFFORT_CRITERIA)) {
    assert.equal(
      EFFORT_CRITERIA_WITH_DECLINE[key],
      EFFORT_CRITERIA[key],
      `${key} 档措辞不得被改动`,
    );
  }
  assert.equal(Object.keys(EFFORT_CRITERIA_WITH_DECLINE).length, 6);
  assert.equal(typeof EFFORT_CRITERIA_WITH_DECLINE[EFFORT_NOT_APPLICABLE], 'string');
});

test('缓存键:不带 variant 时与历史键逐字相同,带 variant 时不同', () => {
  const base = buildCacheKey('http://e', 'm', 'hello');
  assert.equal(base, `http://e:m:${hashPrompt('hello')}`);
  assert.equal(buildCacheKey('http://e', 'm', 'hello', ''), base, '空 variant 不得改变历史键');
  assert.notEqual(buildCacheKey('http://e', 'm', 'hello', 'decline'), base);
});

test('默认:送给 SystemOne 的 criteria 不含「不适用」档', async () => {
  await withStubSystemOne('low', async ({ endpoint, seen }) => {
    await decideReasoningEffortAsync('列一下当前目录的文件', ['low', 'medium', 'high'], {
      endpoint,
      fallbackEndpoint: '',
    });
    assert.equal(seen.length, 1, '应恰好打一次 SystemOne');
    assert.ok(
      !(EFFORT_NOT_APPLICABLE in seen[0].questions.effort.criteria),
      '默认不得把出口档发给模型',
    );
  });
});

test('declineOption=true:criteria 才带上「不适用」档', async () => {
  await withStubSystemOne('low', async ({ endpoint, seen }) => {
    await decideReasoningEffortAsync('列一下仓库里都有哪些插件目录', ['low', 'medium', 'high'], {
      endpoint,
      fallbackEndpoint: '',
      declineOption: true,
    });
    assert.ok(EFFORT_NOT_APPLICABLE in seen[0].questions.effort.criteria, '出口档应随开关发出');
  });
});

test('模型答「不适用」:交回规则引擎,source 显式标 jev-declined-rule', async () => {
  await withStubSystemOne(EFFORT_NOT_APPLICABLE, async ({ endpoint }) => {
    const decision = await decideReasoningEffortAsync('好的,继续', ['low', 'medium', 'high'], {
      endpoint,
      fallbackEndpoint: '',
      declineOption: true,
    });
    assert.equal(decision.source, 'jev-declined-rule');
    assert.ok(decision.reason.includes('jev_not_applicable'), '原因里要留痕');
    assert.ok(['low', 'medium', 'high'].includes(decision.matchedEffort));
  });
});

test('模型答认不出的档位:回落规则并留痕,不再静默当 medium', async () => {
  await withStubSystemOne('gigantic', async ({ endpoint }) => {
    const decision = await decideReasoningEffortAsync('把 README 里的命令全跑一遍', ['low', 'medium', 'high'], {
      endpoint,
      fallbackEndpoint: '',
    });
    assert.equal(decision.source, 'jev-unknown-tier-rule');
    assert.ok(decision.reason.includes('jev_gigantic'), '未知档位要写进 reason');
  });
});

test('state 已按头尾拼接送出(与 ③ 的集成回归)', async () => {
  const tail = '只输出 JSON,不要解释。';
  const long = `${'a'.repeat(4000)}${tail}`;
  await withStubSystemOne('low', async ({ endpoint, seen }) => {
    await decideReasoningEffortAsync(long, ['low', 'medium', 'high'], {
      endpoint,
      fallbackEndpoint: '',
    });
    const { state } = seen[0];
    assert.ok(state.length <= 1500, '不得超过预算');
    assert.ok(state.endsWith(tail), '尾部约束必须真的到达 SystemOne');
  });
});
