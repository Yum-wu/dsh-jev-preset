/**
 * 档位效果配对检验（2026-10-06 新增）。
 *
 * ## 为什么需要它
 *
 * profile 里给某模型声明几个档位，前提是**这些档位真的会改变模型行为**。
 * 网关 `/v1/models` 的声明**不可信**（实测 shangtang 声明的 `max` 会被上游 400 拒掉），
 * 而且「HTTP 200」也不能证明档位生效 —— 网关对多数模型根本不校验。
 *
 * ## 设计要点（踩过的坑，别改回去）
 *
 * 1. **必须配对**。low/max 背靠背交替发，共同波动（上游负载、时段）被消掉。
 *    第一版用了非配对 t 检验，|t|=1.52 差一步显著 —— 那是检验选错了，不是没效果。
 * 2. **必须用难题**。简单题上 low 和 max 都只花几十到几百 token，差异被压平；
 *    实测简单题上 4 个模型全部「未检出」，而难题上 6/6 同向。
 * 3. **max_tokens 要够大**，否则 max 被截断到上限，差值失真。
 * 4. **判据用符号检验**（不依赖正态）+ 配对 t。符号检验对「方向一致性」敏感，
 *    这正是我们要的：档位越高，推理量应越大。
 *
 * ## 用法
 *
 *   node benchmarks/tier-effect.mjs <model> [reps]
 *   node benchmarks/tier-effect.mjs workbuddy2api/global:deepseek-v4.1-flash 6
 */
const BASE = process.env.OCX_BASE ?? 'http://127.0.0.1:10100/v1/chat/completions';
const KEY = process.env.OCX_KEY ?? 'ocx_data_dsh';

const model = process.argv[2] ?? 'workbuddy2api/global:deepseek-v4.1-flash';
const REPS = Number(process.argv[3] ?? 6);
const LOW = process.argv[4] ?? 'low';
const HIGH = process.argv[5] ?? 'max';

// 难题：需要多步推理，才能把 low 与 max 拉开
const PROMPT = [
  '证明或推翻：对任意正整数 n，n^5 - n 一定能被 30 整除。',
  '要求：(1) 给出完整证明；(2) 用 n=7 和 n=11 两个具体值手工验算；',
  '(3) 说明 30 = 2*3*5 这三个因子各自是怎么被保证的，哪一步最容易出错。',
].join('\n');

async function run(effort) {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), 300000);
  try {
    const resp = await fetch(BASE, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${KEY}` },
      body: JSON.stringify({
        model,
        messages: [{ role: 'user', content: PROMPT }],
        max_tokens: 8000,
        reasoning_effort: effort,
      }),
      signal: ctrl.signal,
    });
    const text = await resp.text();
    if (!resp.ok) return { err: `[${resp.status}]` };
    const j = JSON.parse(text);
    const u = j.usage ?? {};
    return { r: u.completion_tokens_details?.reasoning_tokens ?? u.reasoning_tokens ?? 0 };
  } catch (e) {
    return { err: String(e).slice(0, 60) };
  } finally {
    clearTimeout(t);
  }
}

function binom(n, k) {
  let r = 1;
  for (let i = 0; i < k; i++) r = (r * (n - i)) / (i + 1);
  return r;
}

console.log(`模型: ${model}   对比: ${LOW} vs ${HIGH}   重复 ${REPS} 轮（背靠背 + 顺序反平衡）\n`);
// ⚠ 顺序反平衡是**必须的**，不是讲究。
// 2026-10-06 发现本基准此前恒定「先 LOW 后 HIGH」，于是任何**顺序效应**
// （预热、缓存命中、上游负载随时间漂移）都会被记成「HIGH 更大」，
// 与档位效应完全混淆 —— 那一轮 6/6 同向的「p=0.016」因此不可信。
// 现在奇偶轮换顺序，顺序效应在配对差值里对称抵消。
const diffs = [];
for (let i = 0; i < REPS; i++) {
  const lowFirst = i % 2 === 0;
  const first = await run(lowFirst ? LOW : HIGH);
  const second = await run(lowFirst ? HIGH : LOW);
  const l = lowFirst ? first : second;
  const h = lowFirst ? second : first;
  if (l.err || h.err) {
    console.log(`  #${i + 1} 出错 ${LOW}=${l.err ?? l.r} ${HIGH}=${h.err ?? h.r}`);
    continue;
  }
  diffs.push(h.r - l.r);
  console.log(
    `  #${i + 1} 顺序=${lowFirst ? `${LOW}→${HIGH}` : `${HIGH}→${LOW}`}  ` +
      `${LOW}=${l.r}  ${HIGH}=${h.r}  Δ=${h.r - l.r}`,
  );
}

if (diffs.length < 3) {
  console.log('\n有效配对不足 3 对，无法判定');
  process.exit(1);
}

const n = diffs.length;
const mean = diffs.reduce((a, b) => a + b, 0) / n;
const sd = Math.sqrt(diffs.reduce((a, b) => a + (b - mean) ** 2, 0) / (n - 1));
const se = sd / Math.sqrt(n);
const t = se === 0 ? Infinity : mean / se;
const pos = diffs.filter((d) => d > 0).length;
let signP = 0;
for (let k = pos; k <= n; k++) signP += binom(n, k);
signP /= 2 ** n;

console.log(`\n  差值 Δ(${HIGH} − ${LOW}) = [${diffs.join(', ')}]`);
console.log(`  n=${n}  均值=${mean.toFixed(1)}  sd=${sd.toFixed(1)}  配对 t=${t.toFixed(2)} (df=${n - 1})`);
console.log(`  方向一致 ${pos}/${n}  符号检验单尾 p=${signP.toFixed(3)}`);
console.log(
  '\n  ⚠ effort 是**软引导**（见 AGENTS.md）：模型逐请求自适应，推理长度不是档位的单调函数。\n' +
    '    本基准只能检出**大效应**，检不出 ≠ 无效应。要判「档位是否真的透传到上游」，\n' +
    '    更硬的判据是上游的 `reasoning_supported_efforts` 声明（wb2api /v1/models）。',
);
console.log(
  signP <= 0.05
    ? '\n  ✔ 档位有可检出效果 —— 有扩档依据'
    : t >= 2.571
      ? '\n  ✔ 配对 t 显著 —— 有扩档依据'
      : '\n  ★ 未检出效果。不能断言无效 —— 但**也没有扩档依据**，别把「没测出来」当「没效果」。',
);
