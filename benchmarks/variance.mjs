/**
 * SystemOne 判定的**运行间方差**测量（2026-10-06 新增）。
 *
 * ## 为什么需要它
 *
 * 2026-10-06 同通道、同样本、连跑三轮，对齐率得到 **91.2% / 94.1% / 94.1%**。
 * 也就是说 SystemOne **本身不是确定性的** —— 同一个 prompt 在不同轮次可能给出不同档位。
 *
 * 这件事直接决定了 90% 门禁怎么解读：34 条样本里 1 条 = 2.9pp，
 * 所以「91.2%」与「88.2%」之间只隔一条样本的抖动。
 * **不把这个方差量出来，就无法判断门禁的红灯是真回归还是噪声。**
 *
 * 它还顺带回答一个更有用的问题：**哪些样本的判定是不稳定的** ——
 * 那批样本不适合当门禁样本（它们的「对错」本身就在抖）。
 *
 * 用法：
 *   node benchmarks/variance.mjs        # 默认 6 轮
 *   node benchmarks/variance.mjs 12     # 指定轮数（每轮约 1~2 分钟，含 59 次网络调用）
 */
import { runAlignment } from './effort-alignment.mjs';

const ROUNDS = Number(process.argv[2] ?? 6);
if (!Number.isInteger(ROUNDS) || ROUNDS < 2) {
  console.error('轮数必须是 ≥2 的整数（1 轮量不出方差）');
  process.exit(2);
}

const accs = [];
const perSample = new Map();

for (let i = 1; i <= ROUNDS; i++) {
  const r = await runAlignment({ offline: false });
  accs.push(r.accuracy);
  console.log(
    `R${i}: ${(r.accuracy * 100).toFixed(1)}% (${r.passed}/${r.gateTotal})  sources=${JSON.stringify(r.sources)}`,
  );
  for (const row of r.rows) {
    if (row.debatable) continue;
    if (!perSample.has(row.p)) perSample.set(row.p, []);
    perSample.get(row.p).push(row.got);
  }
}

const min = Math.min(...accs);
const max = Math.max(...accs);
const mean = accs.reduce((a, b) => a + b, 0) / accs.length;
const n = perSample.size;

console.log('\n=== 汇总 ===');
console.log(`轮数 ${ROUNDS}  最低 ${(min * 100).toFixed(1)}%  最高 ${(max * 100).toFixed(1)}%  均值 ${(mean * 100).toFixed(1)}%`);
console.log(`摆幅 ${((max - min) * 100).toFixed(1)}pp（≈ ${Math.round((max - min) * n)} 条样本）`);
console.log(`→ 门禁余量提示：样本量 ${n} 条时，1 条样本 = ${(100 / n).toFixed(1)}pp`);

// 判定在不同轮次给出不同档位的样本 —— 这些不适合当门禁样本
const unstable = [...perSample.entries()].filter(([, v]) => new Set(v).size > 1);
console.log(`\n判定不稳定的样本: ${unstable.length}/${n}`);
for (const [p, v] of unstable) {
  console.log(`  ${p.slice(0, 30)}  ->  ${[...new Set(v)].join(' / ')}`);
}
if (unstable.length === 0) {
  console.log('  （本轮全部稳定 —— 但注意轮数越多越容易暴露不稳定，别据此断言 SystemOne 是确定性的）');
}
