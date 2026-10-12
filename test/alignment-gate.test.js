// 门禁测试：把「档位对齐率」挂进 npm test。
//
// 为什么值得单独一个文件：Anthropic 官方对这类改动的原话是
//   "treat it like any other prompt change: **measure before you ship**"。
// 而在此之前，本插件的 criteria 改过多次却**没有任何办法回答「改完是变好还是变坏」**。
// 这个文件就是那个办法。
//
// ⚠ 默认走【在线】判定（真实 SystemOne 路径）。它会发网络请求，CI 无网时会失败。
//   无网环境请跑 `npm run test:offline`（只测规则兜底引擎，不打网络）。
import test from 'node:test';
import assert from 'node:assert/strict';
import { GATE_ONLINE, GATE_OFFLINE, runAlignment } from '../benchmarks/effort-alignment.mjs';

const OFFLINE = process.argv.includes('--offline') || process.env.DISABLE_JEV_REMOTE === '1';

/**
 * 留出集基线（棘轮）—— 2026-10-06 首次实测。
 *
 * ⚠ **这个数很低，而它才是诚实的那个。**
 *
 * 上面那 34 条训练集跑出 100%，是因为我**照着它们的失败清单改正则**改出来的；
 * 换一批没见过的措辞（留出集 v2，22 条），规则引擎只有 **36.4%**。
 *
 * 为什么留出集**不做硬门禁**、只做棘轮：
 *   · 拿它当硬门禁，下一步必然是照着它的失败清单调参 —— 然后它就变成第二个训练集，
 *     「留出集」三个字失去全部意义（`HELDOUT_SAMPLES` 注释里有完整纪律）；
 *   · 但完全不卡它，这个数就会悄悄腐烂。
 *   棘轮是两者的折中：**只禁止变差，不要求变好**。
 *
 * 容差 0.05 来自实测的运行间方差（同输入连跑，SystemOne 本身会给出不同档位）。
 */
const HELDOUT_BASELINE = 0.364;
const HELDOUT_TOLERANCE = 0.05;

test('档位对齐率不低于门禁阈值', { skip: false }, async () => {
  const report = await runAlignment({ offline: OFFLINE });
  // 阈值按运行模式取：**离线阈值更低是刻意的**，因为规则兜底引擎的职责是
  // 「网络挂时链路不断」而不是「精确分类」。用在线阈值卡它等于逼关键词表去拟合 SystemOne。
  const gate = OFFLINE ? GATE_OFFLINE : GATE_ONLINE;
  const mode = OFFLINE ? '离线规则引擎' : 'SystemOne 在线判定';
  const detail =
    `${mode}：${report.passed}/${report.gateTotal} = ${(report.accuracy * 100).toFixed(1)}%` +
    `（本模式阈值 ${(gate * 100).toFixed(0)}%，平均偏差 ${report.meanOffBy} 档）`;
  const misses = report.rows.filter((r) => !r.ok && !r.debatable)
    .map((r) => `${r.got}←期望${r.expected.join('/')}「${r.p.slice(0, 24)}」`);
  assert.ok(
    report.accuracy >= gate,
    `${detail}\n未命中：\n  ${misses.join('\n  ') || '无'}\n` +
      (OFFLINE
        ? '  离线门禁没过：规则引擎退化。若网络正常，请跑 `npm test`（在线）确认真实路径。\n'
        : '★ 若你刚改了 EFFORT_CRITERIA，请先跑 `npm run bench` 与 `npm run bench:offline` 对照，\n' +
          '  确认不是网络抖动导致的假阴性。\n'),
  );
  assert.ok(report.accuracy > 0, detail);
});

test('在线阈值必须显著高于离线阈值(否则等于没卡)', () => {
  assert.ok(GATE_ONLINE > GATE_OFFLINE, '在线(语义判定)与离线(关键词兜底)不该用同一个阈值');
  assert.ok(GATE_ONLINE >= 0.85, '在线门禁不应宽松到失去意义');
  assert.ok(GATE_OFFLINE >= 0.5, '离线门禁过低会连兜底都失效');
});

test('样本集覆盖每一档，且每档至少 5 条(样本太少时指标没有统计意义)', async () => {
  const report = await runAlignment({ offline: true });
  for (const [tier, v] of Object.entries(report.perTier)) {
    assert.ok(v.n >= 5, `${tier} 只有 ${v.n} 条样本 —— 这个档位的召回率不可信，先补样本再谈调优`);
  }
});

test('门禁只统计非分歧样本(否则「相信模型」的样本永远命中,门禁失效)', async () => {
  const report = await runAlignment({ offline: true });
  const debatable = report.rows.filter((r) => r.debatable);
  assert.ok(debatable.length >= 3, '分歧样本应保留若干条，否则指标会粉饰太平');
  assert.equal(report.gateTotal, report.total - debatable.length);
});

test('低风险日常(读/查/跑命令)不得被判到 medium 以上 —— 这是省 token 的底线', async () => {
  // ⚠ 这里**只断言 SystemOne 在线判定**，不碰规则引擎。
  // 规则引擎靠关键词表，天生覆盖不全 —— 「跑一下 npm test」里的 `test` 会被它的
  // standard_development_task 分支捞成 medium，属预期缺陷。
  // 真实路径（SystemOne）已实测判 low，规则引擎只是网络失败时的兜底，
  // 用它做底线断言会逼着关键词表无限膨胀，反而制造新的误判。
  if (process.env.DISABLE_JEV_REMOTE === '1') {
    return; // 显式禁用远程时跳过
  }
  const { SAMPLES, judge } = await import('../benchmarks/effort-alignment.mjs');
  for (const p of ['帮我 grep 一下所有 TODO 的位置', '跑一下 npm test，把失败的用例列出来', 'git status 看一下', '列出这个目录下所有 .ts 文件']) {
    const r = await judge({ p, expected: ['low'] }, { offline: false });
    assert.equal(r.got, 'low', `「${p}」应判 low，实际 ${r.got} —— 日常工具型工作被抬高即在烧 token`);
  }
  assert.ok(SAMPLES.length >= 30, '样本集应持续扩充');
});

test('留出集必须存在且不得比基线更差(棘轮,只禁变差不求变好)', async () => {
  const report = await runAlignment({ offline: true });
  const h = report.heldout;

  assert.ok(h.total >= 15, `留出集只有 ${h.total} 条，样本太少则泛化估计没有意义`);
  // 反空转：留出集必须真的被跑过，而不是被某次改动静默清空
  assert.equal(h.rows.length, h.total, '留出集行数与声明数不一致 —— 有样本没被执行');

  const floor = HELDOUT_BASELINE - HELDOUT_TOLERANCE;
  assert.ok(
    h.accuracy >= floor,
    `留出集泛化估计 ${(h.accuracy * 100).toFixed(1)}% 低于棘轮下限 ${(floor * 100).toFixed(1)}%\n` +
      `（基线 ${(HELDOUT_BASELINE * 100).toFixed(1)}% + 容差 ${(HELDOUT_TOLERANCE * 100).toFixed(0)}%）\n` +
      `未命中：\n  ${h.rows.filter((r) => !r.ok).map((r) => `${r.got}←期望${r.expected.join('/')}「${r.p.slice(0, 24)}」`).join('\n  ')}\n` +
      '⚠ 若你正想「照着上面这份清单改正则」—— 停手，那会把留出集变成第二个训练集。\n' +
      '  正确做法：改 SAMPLES 那边的判定逻辑，或重写一批新的留出样本并更新 HELDOUT_BASELINE。',
  );
});

test('留出集与训练集不得有重复样本(否则等于自己考自己)', async () => {
  const { SAMPLES, HELDOUT_SAMPLES } = await import('../benchmarks/effort-alignment.mjs');
  const train = new Set(SAMPLES.map((s) => s.p));
  const dup = HELDOUT_SAMPLES.filter((s) => train.has(s.p));
  assert.deepEqual(dup, [], `留出集里出现了训练集已有的 prompt：${dup.map((d) => d.p).join(' / ')}`);
});