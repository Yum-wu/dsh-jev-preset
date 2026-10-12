/**
 * 真实 prompt 基准（2026-10-06 新增）。
 *
 * ## 为什么需要它
 *
 * `effort-alignment.mjs` 里的训练集和留出集**都是我手写的**，
 * 所以它们回答不了唯一重要的问题：**真实用量长什么样**。
 * 2026-10-06 就因此连续两次得出错误结论：
 *
 *   · 留出集说规则引擎比「什么都不做」差 9.1pp → 差点据此删掉 L3
 *   · 换成真实 prompt 后点估计反过来说好 12.5pp → 差点据此宣布 L3 有效
 *   · 配对 McNemar 一算 χ²=0.03 **不显著** → 两个结论都不成立
 *
 * 手写样本集能回答「改了会不会变坏」，**回答不了「真实分布上哪个更好」**。
 *
 * ## 数据源
 *
 * `~/.dsh/sessions` 下的真实会话档。两个必须注意的口径问题：
 *
 * 1. **只认 `source.kind === 'user'`**。DSH 把 AGENTS.md / runtime-context /
 *    skill-catalog 也当 user 消息注入，不排除就会把注入文本当成用户提问。
 * 2. **会话档是多帧 zstd 拼接的**。Node 的 `zstdDecompressSync` 只解第一帧
 *    （拿到的是 220 字节的会话头），流式 API 直接报 `Unknown frame descriptor`。
 *    必须按 zstd 魔数 `28 B5 2F FD` 手工切帧。
 *
 * ## 用法
 *
 *   node benchmarks/real-prompts.mjs              # 只量命中率（离线，不花钱）
 *   node benchmarks/real-prompts.mjs --label 120  # 额外用 SystemOne 打标做策略对比
 */
import { readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { zstdDecompressSync } from 'node:zlib';
import path from 'node:path';
import os from 'node:os';
import { scoreTaskComplexity } from '../lib/auto-reasoning.js';

const MAGIC = Buffer.from([0x28, 0xb5, 0x2f, 0xfd]);
const SESSIONS_ROOT = path.join(os.homedir(), '.dsh', 'sessions');
const MIN_FILE_BYTES = 4000; // 更小的是单行会话头，没有对话内容

/** 按 zstd 帧魔数切帧后逐帧解压（Node 的 zstd API 处理不了拼接帧）。 */
function decompressMultiFrame(buf) {
  const starts = [];
  let i = buf.indexOf(MAGIC);
  while (i !== -1) {
    starts.push(i);
    i = buf.indexOf(MAGIC, i + 4);
  }
  const parts = [];
  for (let k = 0; k < starts.length; k++) {
    const end = k + 1 < starts.length ? starts[k + 1] : buf.length;
    try {
      parts.push(zstdDecompressSync(buf.subarray(starts[k], end)).toString('utf8'));
    } catch {
      /* 单帧坏掉不影响其余 */
    }
  }
  return parts.join('\n');
}

function walk(dir, out = [], depth = 0) {
  if (depth > 4) return out;
  let entries;
  try {
    entries = readdirSync(dir, { withFileTypes: true });
  } catch {
    return out;
  }
  for (const e of entries) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, out, depth + 1);
    else if (e.name.endsWith('.jsonl.zstd')) out.push(p);
  }
  return out;
}

/** 抽取真实用户 prompt（去重）。 */
export function collectRealPrompts({ root = SESSIONS_ROOT, minBytes = MIN_FILE_BYTES } = {}) {
  const files = walk(root)
    .map((f) => ({ f, n: readFileSync(f).length }))
    .filter((x) => x.n > minBytes)
    .sort((a, b) => b.n - a.n);

  const all = [];
  for (const { f } of files) {
    const text = decompressMultiFrame(readFileSync(f));
    for (const line of text.split('\n')) {
      if (!line.trim()) continue;
      let j;
      try {
        j = JSON.parse(line);
      } catch {
        continue;
      }
      if (j.type !== 'user/message' && j.type !== 'message/user') continue;
      const data = j.data ?? {};
      const msg = data.message ?? data;
      if ((msg.role ?? data.role) !== 'user') continue;
      if ((msg.source?.kind ?? data.source?.kind) !== 'user') continue;
      const content = msg.content ?? data.content;
      const s =
        typeof content === 'string'
          ? content
          : Array.isArray(content)
            ? content.filter((c) => c?.type === 'text').map((c) => c.text).join('\n')
            : '';
      const t = (s ?? '').trim();
      if (t) all.push(t);
    }
  }
  return { files: files.length, unique: [...new Set(all)] };
}

const agree = (a, b) => a === b || (b === 'xhigh' && (a === 'high' || a === 'max'));

/** 配对 McNemar（连续校正）。返回 b/c 与卡方。 */
export function mcnemar(okA, okB) {
  let b = 0;
  let c = 0;
  for (let i = 0; i < okA.length; i++) {
    if (okA[i] && !okB[i]) b++;
    else if (!okA[i] && okB[i]) c++;
  }
  const chi2 = b + c === 0 ? 0 : (Math.abs(b - c) - 1) ** 2 / (b + c);
  return { b, c, chi2, significant: chi2 >= 3.84 };
}

// ── CLI ────────────────────────────────────────────────────────────
const labelIdx = process.argv.indexOf('--label');
const LABEL_N = labelIdx === -1 ? 0 : Number(process.argv[labelIdx + 1] ?? 100);
const isMain = process.argv[1] && import.meta.url.endsWith(path.basename(process.argv[1]));

if (isMain) {
  const { files, unique } = collectRealPrompts();
  console.log(`会话档（>${MIN_FILE_BYTES}B）: ${files} 个`);
  console.log(`真实用户 prompt: ${unique.length} 条（去重后）\n`);

  // ── 命中率（免费，不花钱）──
  let defaulted = 0;
  const byReason = {};
  for (const p of unique) {
    const r = scoreTaskComplexity(p);
    if (r.reason === 'unmatched_default_low') defaulted++;
    else byReason[r.reason] = (byReason[r.reason] || 0) + 1;
  }
  console.log('=== 规则兜底引擎在真实 prompt 上的关键词命中率 ===');
  console.log(`  未命中（走默认档）: ${defaulted}/${unique.length}  (${((defaulted / unique.length) * 100).toFixed(1)}%)`);
  console.log(`  命中             : ${unique.length - defaulted}/${unique.length}  (${(((unique.length - defaulted) / unique.length) * 100).toFixed(1)}%)`);
  for (const [k, v] of Object.entries(byReason).sort((a, b) => b[1] - a[1])) {
    console.log(`    ${String(v).padStart(4)}  ${k}`);
  }
  const lens = unique.map((p) => p.length).sort((a, b) => a - b);
  console.log(`\n  prompt 长度: 中位 ${lens[Math.floor((lens.length - 1) * 0.5)]}  最长 ${lens[lens.length - 1]}`);

  if (LABEL_N > 0) {
    const { queryJevReasoningEffort } = await import('../lib/jev-client.js');
    const step = Math.max(1, Math.floor(unique.length / LABEL_N));
    const sample = [];
    for (let i = 0; i < unique.length && sample.length < LABEL_N; i += step) sample.push(unique[i]);
    console.log(`\n=== 用 SystemOne 给 ${sample.length} 条真实 prompt 打标 ===`);

    const rows = [];
    for (const p of sample) {
      let sysTier = null;
      try {
        const r = await queryJevReasoningEffort(p, { timeoutMs: 20000 });
        if (r?.tier) sysTier = r.tier;
      } catch {}
      if (!sysTier) continue;
      const rule = scoreTaskComplexity(p);
      const matched = rule.reason !== 'unmatched_default_low';
      const ruleTier =
        rule.score <= 1 ? 'minimal' : rule.score <= 3 ? 'low' : rule.score <= 6 ? 'medium' : rule.score <= 8 ? 'high' : 'max';
      rows.push({ p, len: p.length, sysTier, ruleScore: rule.score, ruleTier, matched });
      process.stdout.write(`\r  进度 ${rows.length}`);
    }
    console.log('\n');

    const n = rows.length;
    const strategies = {
      '规则引擎（当前）': (r) => r.ruleTier,
      '恒定 low（众数基线）': () => 'low',
      '恒定 high': () => 'high',
      '省略字段（模型默认档）': () => 'high',
    };
    const okMap = {};
    for (const [name, f] of Object.entries(strategies)) {
      okMap[name] = rows.map((r) => agree(f(r), r.sysTier));
      const hits = okMap[name].filter(Boolean).length;
      console.log(`  ${name.padEnd(24)} ${((hits / n) * 100).toFixed(1).padStart(5)}%  (${hits}/${n})`);
    }
    console.log('\n  配对 McNemar（连续校正，df=1，临界 3.84）:');
    for (const [a, b] of [
      ['规则引擎（当前）', '省略字段（模型默认档）'],
      ['规则引擎（当前）', '恒定 low（众数基线）'],
    ]) {
      const m = mcnemar(okMap[a], okMap[b]);
      console.log(`    ${a} vs ${b}: A对B错=${m.b} A错B对=${m.c} χ²=${m.chi2.toFixed(2)} → ${m.significant ? '✔ 显著' : '★ 不显著'}`);
    }

    const outFile = path.join(process.cwd(), '_tmp-real-prompts-labeled.json');
    writeFileSync(outFile, JSON.stringify(rows, null, 1), 'utf8');
    console.log(`\n  打标结果已落盘: ${outFile}（供反事实分析，不必重打网络）`);
  }
}
