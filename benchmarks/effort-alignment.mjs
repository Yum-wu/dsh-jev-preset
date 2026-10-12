/**
 * 自动思考档位的**校准闭环** —— 2026-10-05 依据两家官方文档建立。
 *
 * ## 为什么需要它
 *
 * Anthropic 官方文档对「steering」这类改动的态度原话是：
 *   "Prompt-based steering changes model behavior, so treat it like any other prompt change:
 *    **measure before you ship.**"
 *
 * 而在这之前，本插件的 `EFFORT_CRITERIA` 改过至少三次 —— 每一次都是**拍脑袋**，
 * 没有任何办法回答「改完是变好还是变坏」。本文件补上这个闭环：
 * 一组标注了期望档位的真实 prompt，跑判定，算对齐率，并作为回归门禁。
 *
 * ## 校准的诚实边界（别把它当成真值）
 *
 * `expected` 是**人工标注的意图**，不是「模型实际思考了多少」。
 * 它衡量的是「criteria 的描述与我们的意图是否一致」，**不衡量模型是否真的照做** ——
 * 因为 effort 在两家官方口径下都是 soft guidance，模型仍会逐请求自适应。
 *
 * 想要第二类证据（模型是否真照做），只能量测 reasoning token / 思考块出现率，
 * 那要花钱跑真实流量，见 README「校准」一节。
 *
 * 用法：
 *   node benchmarks/effort-alignment.mjs              # 跑一遍并打印对齐率
 *   node benchmarks/effort-alignment.mjs --offline    # 只跑规则引擎，不调网络
 *   node benchmarks/effort-alignment.mjs --json       # 输出 JSON，供 CI 消费
 */

import { decideReasoningEffort, decideReasoningEffortAsync } from '../lib/auto-reasoning.js';
import { pathToFileURL } from 'node:url';

/**
 * 门禁阈值 —— **在线与离线必须分开设**，否则离线必然永远红。
 *
 * 理由：在线走 SystemOne 语义判定，它才是真实路径，理应达到高对齐率。
 * 离线是规则兜底引擎（关键词表），它的职责是「网络挂时链路不断、能给出合理默认」，
 * **不是「精确分类」** —— 拿 90% 卡它等于逼着关键词表无限膨胀去拟合 SystemOne。
 *
 * ## 在线阈值为什么是 85% 而不是 90%（2026-10-06 按实测改）
 *
 * 34 条门禁样本里 **1 条 = 2.9pp**，所以：
 *   90% 需要 ≥31/34，而实测最低就是 **31/34（91.2%）** —— **余量为零**，
 *   再抖一条就掉到 88.2% 触发红灯。
 *
 * 实测分布（`node benchmarks/variance.mjs`，9 轮）：8 轮 94.1% + 1 轮 91.2%，
 * 门禁 9/9 都过了（91.2% > 90%），所以**当前没有误报**；但零余量意味着
 * 一次正常的模型抖动就会误报，而**会喊狼来了的门禁比稍松的门禁更糟** ——
 * 它训练人忽略红灯。
 *
 * 85% 需要 ≥29/34，买到 2 条样本的余量；而真实的 criteria 退化会掉得多得多
 * （2026-10-06 前一轮坏掉的 criteria 实测只有 64.7%），**检测力不受影响**。
 */
export const GATE_ONLINE = 0.85;
export const GATE_OFFLINE = 0.6;
export const GATE = GATE_ONLINE; // 向后兼容：默认指在线阈值

/**
 * 标注样本集。
 *
 * 构造原则（刻意覆盖三类最容易判错的情况）：
 *  1. **日常工具型** —— 按 OpenAI 的 Best for，`low` 必须包含 tool-use / planning /
 *     search / 执行导向编码。旧版 criteria 把这类判成 medium，是最大的对齐缺口。
 *  2. **创造性深度工作** —— 跨模块算法重设计与边界重划。用户 2026-10-05 指出
 *     「优化插件算法」应是 max 而非 high，旧版 max 只写了资金/并发场景。
 *  3. **高危不可逆** —— 资金/死锁/爆仓，归 max。
 *
 * allowed 列出该样本**可接受**的档位集合（相邻档常可接受，硬判会让指标噪声爆炸）。
 *
 * `debatable: true` 表示**这一条是我们和模型的分歧，且我们选择相信模型**。
 * 保留它而不是删掉或强行改标注 —— 删掉等于藏起分歧，改标注等于用结果拟合期望，
 * 两者都会让这个指标失去它唯一的作用：诚实地暴露判定与意图的距离。
 * 它们命中与否【不影响门禁】（judge 时把实际档位并入 allowed）。
 */
export const SAMPLES = [
  // ── low：问答、查看、以及以工具调用为主的工作 ──────────────────────────
  { p: 'README 里「快速开始」这一节讲了什么？', expected: ['low'] },
  { p: '帮我 grep 一下这个仓库里所有 TODO 的位置', expected: ['low'] },
  { p: '跑一下 npm test，把失败的用例列出来', expected: ['low'] },
  { p: '读一下 config.ts，把默认超时改成 30 秒', expected: ['low', 'medium'] },
  { p: '这个函数的参数类型是什么？看一下签名就行', expected: ['low'] },
  { p: '把 README 里错别字改掉', expected: ['low', 'medium'] },
  { p: '搜索项目里用到 deprecated API 的地方并列出清单', expected: ['low'] },
  { p: '帮我写一段 bash 脚本把当前目录的 log 按日期归档', expected: ['low', 'medium'] },
  { p: '列出这个目录下所有 .ts 文件', expected: ['low'] },
  { p: '把 package.json 里的 version 改成 2.0.0', expected: ['low', 'medium'] },
  { p: 'git status 看一下现在工作区干不干净', expected: ['low'] },
  { p: '把这个文件的第 42 行打印出来', expected: ['low'] },

  // ── medium：常规开发，需要规划与判断 ──────────────────────────────────
  { p: '给判断字符串是否为回文的函数写单元测试，覆盖空串与大小写边界', expected: ['medium'] },
  { p: '实现一个 LRU 缓存类，要求线程安全', expected: ['medium', 'high'] },
  { p: '这个 bug 你先定位一下根因，看看是哪里写错了', expected: ['medium', 'high'] },
  { p: '帮我实现一个分页接口', expected: ['medium'] },
  { p: '把这个 JSON schema 校验加上，缺字段要报明确错误', expected: ['medium'] },
  { p: '写一个脚本把这些测试结果汇总成一张表', expected: ['medium'] },
  { p: '帮我给这个模块补上输入校验', expected: ['medium'] },

  // ── high：困难调试、算法调优、架构重构 ────────────────────────────────
  { p: '把 O(n²) 的两数求和重构成 O(n)，并推导哈希法为什么正确、会不会碰撞', expected: ['high'] },
  { p: '这个服务上线后内存持续增长，帮我做根因排查', expected: ['high'] },
  { p: '重构这个模块的分层结构，梳理依赖方向', expected: ['high'] },
  { p: '这个并发问题偶发复现，帮我分析竞态条件和时序', expected: ['high'] },
  { p: '把这段同步 IO 改成异步但要保证顺序，推导一下实现方式', expected: ['high'] },
  { p: '帮忙做一次完整的性能剖析并给出优化方案', expected: ['high'] },

  // ── xhigh：深度研究、代码审查、长跑 agentic ────────────────────────────
  { p: '对整个支付模块做一次安全审查，找出越权与注入风险', expected: ['xhigh', 'high', 'max'] },
  { p: '系统性调研业界做 LLM 难度路由的主流方案并给出选型建议', expected: ['xhigh', 'high', 'max'] },
  { p: '对整个仓库做一次全面 code review，逐文件给出问题清单', expected: ['xhigh', 'high', 'max'] },
  { p: '系统性分析这个系统的全部技术债，按风险和改造成本排序', expected: ['xhigh', 'high', 'max'] },
  { p: '深入研究这几个竞态方案的本质差异，给出架构级取舍论证', expected: ['xhigh', 'high', 'max'] },
  { p: '写一个需要跨多个模块长程推进的迁移方案，每步都要可回滚', expected: ['xhigh', 'high', 'max'] },

  // ── max：高危不可逆 + 创造性深度工作 ──────────────────────────────────
  { p: '排查分布式死锁：爆仓清算并发写资金账户导致状态机卡死，给出根因与并发安全改造方案', expected: ['max'] },
  { p: '优化三个插件的算法和边界情况', expected: ['max', 'high'], debatable: true },
  { p: '重新设计整个调度器的状态机与并发边界，覆盖所有竞态', expected: ['max'] },
  { p: '推导一下这个永续合约维持保证金的分段累进算法并验证边界情形', expected: ['max', 'high'], debatable: true },
  { p: '把整个认证鉴权链路重新设计一遍，要覆盖所有越权路径', expected: ['max'] },

  // ── 分歧样本：选择相信模型，命中与否不影响门禁 ──────────────────────────
  { p: '把这张表的数据导成 CSV，注意字段里的逗号要转义', expected: ['medium'], debatable: true },
];

/**
 * 留出集（held-out）—— 2026-10-06 新增，**因为上面那 34 条已经被污染了**。
 *
 * ## 为什么要单独分一组
 *
 * 2026-10-06 我把规则兜底引擎的离线对齐率从 64.7% 调到 100% —— 但那是**看着上面那 34 条
 * 的失败清单改正则**改出来的。**这是训练分，不是泛化分。** 拿它当质量证据是自欺。
 *
 * 所以这一组按下面的纪律单独维护：
 *   1. **先按官方 Best-for 表标注，再跑**。标完不回头看正则命中了什么。
 *   2. **只读不调**。这一组跑出什么就是什么；要调 criteria 只能动 SAMPLES 那边，
 *      然后回来**重新观测**这一组的变化 —— 而不是回去改这一组的标注。
 *   3. 一旦发现自己在「改到留出集也全绿」，这一组就作废了，必须重写一批新的。
 *
 * ## 批次台账（这条纪律必须留痕，否则「留出集」会悄悄退化成第二个训练集）
 *
 * | 批次 | 结果 | 状态 |
 * |---|---|---|
 * | v1（24 条） | 50.0% → 改默认档后 66.7% | **已消耗** —— 我先看了它的失败清单，才去改「未命中默认 medium」 |
 * | v2（22 条，当前） | 见下方实测 | **干净**（截至 2026-10-06 写入时） |
 *
 * ⚠ v1 被消耗这件事**不影响它的价值**：正是它把「100% 其实是过拟合」这件事揭出来的，
 * 而那次改动依据的是官方文档（`medium` = "the default for most workloads"）而非样本本身。
 * 但读者要知道这个先后顺序 —— 所以写在这里，不藏。
 *
 * 标注依据与 SAMPLES 相同（OpenAI reasoning.effort 的 Best for 表 + Anthropic 档位表），
 * 措辞刻意与 SAMPLES 不重合，避免靠关键词记忆过关。
 */
export const HELDOUT_SAMPLES = [
  // ── low：读取已有内容 / 查参数 / 格式化（OpenAI: tool-use, search）──
  { p: '这条命令里的 -Force 参数是干什么的', expected: ['low'] },
  { p: '把这个目录下的图片按拍摄日期重命名', expected: ['low', 'medium'] },
  { p: '配置里这个 timeout 字段单位是秒还是毫秒', expected: ['low'] },
  { p: '帮我把这个 JSON 格式化一下', expected: ['low'] },
  { p: '这行代码为什么要加 try 包起来', expected: ['low', 'medium'] },

  // ── medium：常规实现与改造（OpenAI: default for most workloads）──
  { p: '给这个表单加必填校验，空值要拦下来', expected: ['medium'] },
  { p: '写个脚本把 CSV 里的空行删掉再排序', expected: ['low', 'medium'] },
  { p: '把这个同步接口改成批量查询，减少调用次数', expected: ['medium'] },
  { p: '给这个模块补一套集成测试，覆盖失败重试路径', expected: ['medium'] },
  { p: '这段代码的圈复杂度有点高，帮我拆分一下', expected: ['medium'] },
  { p: '把用户表的手机号字段加个唯一索引', expected: ['medium'] },

  // ── high：根因排查 / 算法与空间复杂度 / 容量估算 ──
  { p: '这个接口偶发返回 500，日志里只有一行 stack，帮我追根因', expected: ['high'] },
  { p: '把这段 O(n log n) 的排序换成更省内存的实现，并给出空间复杂度', expected: ['high'] },
  { p: '分析这个连接池耗尽的原因，给出容量估算', expected: ['high'] },
  { p: '把这份配置从单体拆成按环境分层，保证零停机切换', expected: ['high', 'xhigh'] },
  { p: '这个内存快照里有个对象一直涨，帮我找出持有链', expected: ['high'] },

  // ── high/xhigh：审计 / 依赖梳理 / 渐进拆分 ──
  { p: '梳理这个服务的全部外部依赖，评估单点故障', expected: ['high', 'xhigh'] },
  { p: '给这个对外开放的 API 做一次权限矩阵审计', expected: ['high', 'xhigh'] },
  { p: '设计一套从单体到微服务的渐进拆分路线，含回滚点', expected: ['high', 'xhigh'] },

  // ── max：高危并发正确性 / 记账模型 / 安全重设计 ──
  { p: '这个撮合引擎在高并发下偶尔丢单，帮我查并发正确性', expected: ['max', 'high'] },
  { p: '重新设计账户余额的记账模型，要求支持并发冲正且不重不漏', expected: ['max'] },
  { p: '把这个系统的鉴权、限流、审计三层重新设计，覆盖所有绕过路径', expected: ['max', 'high'] },
];

const LADDER = ['low', 'medium', 'high', 'xhigh', 'max'];
const rank = (t) => LADDER.indexOf(t);

/** 单条样本的判定结果。 */
export async function judge(sample, { offline = false } = {}) {
  const decision = offline
    ? decideReasoningEffort(sample.p, LADDER)
    : await decideReasoningEffortAsync(sample.p, LADDER);
  const got = decision.matchedEffort;
  // debatable 样本：实际档位一律视为可接受（我们选择相信模型），但仍记录偏差供观察。
  const accepted = sample.debatable === true ? [...sample.expected, got] : sample.expected;
  const ok = accepted.includes(got);
  const nearest = sample.expected
    .map((e) => ({ e, d: Math.abs(rank(e) - rank(got)) }))
    .sort((a, b) => a.d - b.d)[0];
  return { ok, got, score: decision.score, source: decision.source, offBy: nearest.d, debatable: sample.debatable === true };
}

/**
 * 跑完整样本集。
 *
 * 对齐率**只统计非 debatable 样本**（GATE_SAMPLES）—— 否则「相信模型」的样本
 * 永远命中，门禁就失去了发现退化的能力。可疑样本在 `rows` 里仍可见。
 */
export async function runAlignment({ offline = false } = {}) {
  const rows = [];
  for (const s of SAMPLES) rows.push({ p: s.p, expected: s.expected, ...(await judge(s, { offline })) });
  const gateRows = rows.filter((r) => !r.debatable);
  const passed = gateRows.filter((r) => r.ok).length;
  const gate = offline ? GATE_OFFLINE : GATE_ONLINE;
  const meanOffBy = rows.reduce((n, r) => n + r.offBy, 0) / rows.length;

  // ── 留出集：**不参与门禁**，只作为泛化估计打印。
  // 理由见 HELDOUT_SAMPLES 的注释 —— 它一旦被拿去做门禁，下一步就是照着它调参，
  // 然后它就变成第二个训练集，失去全部意义。
  const heldoutRows = [];
  for (const s of HELDOUT_SAMPLES) heldoutRows.push({ p: s.p, expected: s.expected, ...(await judge(s, { offline })) });
  const heldoutPassed = heldoutRows.filter((r) => r.ok).length;

  // ── 谁真的答了这些题？── 不记这个数，指标就没法解读。
  // 2026-10-06 实证：主通道 429 时 `decideReasoningEffortAsync` 会**静默降级到规则引擎**，
  // 此时 CLI 仍打印「SystemOne 在线判定」，把规则引擎的 64.7% 冒充成在线成绩
  // —— 我本人据此误判过一次。所以在线模式下必须把「实际有没有打到 SystemOne」显式暴露。
  const sources = {};
  for (const r of rows) sources[r.source] = (sources[r.source] ?? 0) + 1;
  const remoteHits = (sources['jev-model'] ?? 0) + (sources['jev-model-fallback'] ?? 0);
  const remoteDegraded = !offline && remoteHits === 0;
  // 分档召回：每档期望命中该档的样本里，实际判中该档的比例（同样只算 gate 样本）
  const perTier = {};
  for (const tier of LADDER) {
    const want = gateRows.filter((r) => r.expected.includes(tier));
    if (want.length === 0) continue;
    perTier[tier] = {
      n: want.length,
      hit: want.filter((r) => r.got === tier).length,
      recall: Number((want.filter((r) => r.got === tier).length / want.length).toFixed(3)),
    };
  }
  return {
    total: rows.length,
    gateTotal: gateRows.length,
    passed,
    accuracy: Number((passed / gateRows.length).toFixed(4)),
    gate,
    gatePassed: passed / gateRows.length >= gate,
    meanOffBy: Number(meanOffBy.toFixed(3)),
    perTier,
    sources,
    remoteDegraded,
    heldout: {
      total: heldoutRows.length,
      passed: heldoutPassed,
      accuracy: Number((heldoutPassed / heldoutRows.length).toFixed(4)),
      rows: heldoutRows,
    },
    rows,
  };
}

// ── CLI ───────────────────────────────────────────────────────────────────
// ⚠ Windows 下不能用 `file://${argv[1].replace(/\\/g,'/')}` 拼路径：
//   import.meta.url 是 `file:///C:/…`（三斜杠），手拼出来是 `file://C:/…`（两斜杠），
//   永不匹配 → CLI 块整段不执行，且**不报任何错**（首版就栽在这，只看到「无输出」）。
const isMain = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (isMain) {
  const offline = process.argv.includes('--offline');
  const asJson = process.argv.includes('--json');
  const report = await runAlignment({ offline });

  if (asJson) {
    console.log(JSON.stringify({ offline, ...report, rows: undefined, heldout: { ...report.heldout, rows: undefined } }, null, 2));
  } else {
    console.log(`\n档位对齐率  (${offline ? '离线规则引擎' : 'SystemOne 在线判定'})`);
    console.log('='.repeat(78));
    for (const r of report.rows) {
      const mark = r.ok ? '✔' : '✖';
      const arrow = r.ok ? '' : r.offBy === 0 ? '' : ` (偏 ${r.offBy} 档)`;
      const tag = r.debatable ? ' [分歧样本·不计门禁]' : '';
      console.log(`${mark} ${String(r.got).padEnd(6)} ← 期望 ${r.expected.join('/')}  ${r.p.slice(0, 34)}${tag}`);
    }
    console.log('-'.repeat(78));
    console.log(`对齐率: ${report.passed}/${report.gateTotal} = ${(report.accuracy * 100).toFixed(1)}%  (门禁阈值 ${(report.gate * 100).toFixed(0)}% → ${report.gatePassed ? '通过' : '★不通过'})`);
    console.log(`平均偏差 ${report.meanOffBy} 档   总样本 ${report.total}（其中 ${report.total - report.gateTotal} 条为分歧样本，不计入门禁）`);
    console.log('\n分档召回:');
    for (const [tier, v] of Object.entries(report.perTier)) {
      console.log(`  ${tier.padEnd(6)} ${v.hit}/${v.n} = ${(v.recall * 100).toFixed(0)}%`);
    }

    // ── 留出集：这才是泛化估计，门禁那组是训练集 ──
    console.log(`\n留出集（未参与调参，泛化估计，不计门禁）: ${report.heldout.passed}/${report.heldout.total} = ${(report.heldout.accuracy * 100).toFixed(1)}%`);
    for (const r of report.heldout.rows) {
      if (r.ok) continue;
      console.log(`  ✖ ${String(r.got).padEnd(6)} ← 期望 ${r.expected.join('/')}  ${r.p.slice(0, 34)}`);
    }

    // 谁真的答了这些题 —— 不打印这个，上面的百分比无法解读
    if (!offline) {
      const SRC_LABEL = {
        'jev-model': 'SystemOne 主通道(opencode/zen)',
        'jev-model-fallback': 'SystemOne 备用通道(openrouter)',
        rule: '★规则兜底引擎',
      };
      console.log('\n判定来源:');
      for (const [src, n] of Object.entries(report.sources)) {
        console.log(`  ${String(n).padStart(3)} 条  ${SRC_LABEL[src] ?? src}`);
      }
    }

    console.log(`\n注意: expected 是人工标注的【意图】，不是模型实际思考量。`);
    console.log('      effort 在官方口径下是 soft guidance，模型仍会逐请求自适应。');

    if (report.remoteDegraded) {
      console.log('\n★★★ 本次【完全没有打到 SystemOne】，上面这个数字是规则兜底引擎的成绩，');
      console.log('    不是在线语义判定的成绩 —— 别拿它当在线指标看。');
      console.log('    主通道 429 时 `retry-after` 实测可达 4.2 小时；检查备用通道密钥是否可用。');
    }
    if (!report.gatePassed) {
      console.log('\n★ 门禁未通过：本次 criteria 改动把判定改坏了。改动前请先跑 --offline 对照，');
      console.log('  确认不是网络抖动导致的假阴性。');
    }
  }
}