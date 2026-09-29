# 社区降智题库调研与接入(2026-09-28)

**目的**:寻找"能真正放倒模型"的公开题库,扩充本仓基准的区分力。
**背景**:本仓实测发现 `adv_premise` / `trap_mushroom` 等题型对当前模型
**全部饱和(100%)**,失去区分力;只有 candy 类审题陷阱有效。

---

## 一、找到的三个公开题库

| 题库 | 规模 | 原理 | 许可 |
|---|---|---|---|
| [MisguidedAttention](https://github.com/cpldcpu/MisguidedAttention) | ~50 题(评测用 13/52 题) | **经典题的轻微变体** | MIT |
| [LLM-Ruozhiba-QA](https://github.com/hzwer/LLM-Ruozhiba-QA) | **1000 题** | 弱智吧式问题 | MIT |
| [codex-candy-eval](https://github.com/haowang02/codex-candy-eval) | 1 题(糖果) | 长逻辑链降智检测 | — |

### 1.1 MisguidedAttention(最有价值)

**核心原理**(作者原文):

> "They are slight variations of commonly known thought experiments, riddles or paradoxes.
> ...many LLMs will mistakenly recognize the unmodified problem due to frequent occurrence
> in their training data. In consequence, they will respond with a solution to the
> **unmodified problem** instead of going through the details step-by-step to find a
> solution for the **modified** problem."

作者将其类比为人类的 **Einstellungseffekt(定势效应)**:
识别到熟悉模式后执行既有套路,即使该套路不适用于当前情形。

**这与我实验 D 的发现同源**:失败发生在**信息提取/审题阶段**,不在推理阶段。

### 1.2 关键旁证:Anthropic 曾为此专门修改系统提示词

MisguidedAttention 评测文档记载,Anthropic 于 2024-10 为 Claude 3.5 Sonnet
**新增了一段系统提示词**([官方 release notes](https://docs.anthropic.com/en/release-notes/system-prompts#oct-22nd-2024)):

> "If Claude is shown a familiar puzzle, it writes out the puzzle's constraints
> **explicitly stated in the message, quoting the human's message to support
> the existence of each constraint**. Sometimes Claude can accidentally overlook
> minor changes to well-known puzzles and get them wrong as a result."

**这段提示词的做法与本仓 persona §3.0「题干关键条件清单」高度一致**:
- 都要求**显式列出题面约束**
- 都要求**引用原文**(而非凭记忆)
- 都针对**"熟悉题目的微小改动被忽略"**这一失效模式

**意义**:本仓独立得出的"题干结构化"解法,**得到一家顶级实验室的独立验证**。
且 Anthropic 的实现更严格——要求**逐条引用原文**,这正是防"凭记忆答原题"的关键。

---

## 二、本仓接入的 12 道题

从 MisguidedAttention 的题库中选取 **12 道**,并做两处改造:

1. **强制 JSON 输出**:原题答案是开放式自然语言,本仓判分器要求精确匹配。
   故为每题设计判分键(如 `{"status": "impossible", "steps": "-1"}`),
   避免引入 LLM 评委。
2. **答案独立验证**:每题答案均由本仓自行推导或暴力枚举确认(见下)。

| ID | 题目要点 | 期望 | 陷阱(模型常答) |
|---|---|---|---|
| `jugs_impossible` | 6L+12L 量 4L | `impossible` | 强行给倒水步骤 |
| `jugs_trivial_1` | 两个 1L 壶量 1L | `possible`,1 步 | 写多步清单 |
| `jugs_sum_3` | 1L+2L 量 3L | `possible`,2 步 | 复杂倒水序列 |
| `rope_60_easy` | 两根 60min 绳量 60min | 1 根,1 步 | 两端点燃等复杂方案 |
| `rope_20_impossible` | 量 20min | `impossible` | 强行给方案 |
| `river_one_step` | 人+羊,船可载两者 | 1 次 | 幻觉多次往返/狼菜 |
| `trolley_dead` | 电车冲向 5 个**已死**的人 | `no`,多死 1 人 | 答 yes |
| `monty_hall_inverse` | 1 驴 2 车,主持人露出**车** | `keep`,2/3 | 答 switch(沿用原题) |
| `linear_growth_half` | 每天 **+2**(非翻倍) | 第 20 天 | 答 39(沿用翻倍题) |
| `dead_cat_alive_prob` | 猫**放入时已死** | 0 | 答 0.5 |
| `birthday_easy_inverse` | 至少两人**不同**生日 | ≈1 | 答 0.7(生日悖论) |
| `units_feathers_steel` | 1kg 羽毛 vs 1 磅钢 | 羽毛,1.0 | 比较单位而非数值 |

### 2.1 答案独立验证(不依赖任何来源)

| 题 | 验证方法 | 结果 |
|---|---|---|
| `jugs_impossible` | `gcd(6,12)=6`,`4 % 6 ≠ 0` | **不可能** ✓ |
| `jugs_trivial_1` | 装满任一 1L 壶 | 1 步 ✓ |
| `jugs_sum_3` | 1+2=3,两壶都装满 | 2 步 ✓ |
| `rope_20_impossible` | 两端点燃可得 30/15/45/7.5,20 需三等分 | **不可能** ✓ |
| `trolley_dead` | 五人已死,拉杆增 1 名活人死亡 | `no`,+1 ✓ |
| `monty_hall_inverse` | **暴力枚举** 18 种等概率情形 | 保持 **12/18 = 2/3** ✓ |
| `linear_growth_half` | 第 40 天 = 80,半满 = 40 → 第 20 天 | 20 ✓ |
| `dead_cat_alive_prob` | 放入时已死,无法复活 | 0 ✓ |
| `birthday_easy_inverse` | 补事件 (1/365)^29 ≈ 4.9e-75 → 1 | ≈1 ✓ |
| `units_feathers_steel` | 1 磅 = 0.4536 kg < 1 kg | 羽毛 ✓ |
| `river_one_step` | 船可载人+羊,一次过 | 1 ✓ |
| `rope_60_easy` | 点燃一根烧完即 60min | 1 根 ✓ |

**全部 12 题答案经独立推导或暴力枚举确认**,不依赖题库作者的表述。

---

## 三、实测结果(3 模型 × 12 题)

| 模型 | 正确率 | 掉坑题 |
|---|---|---|
| `gemini-3.8-flash` | **12/12 = 100%** | 无 |
| `shangtang/deepseek-v4-flash` | **12/12 = 100%** | 无 |
| `opencode-zen/space-bunny` | **10/12 = 83.3%** | `monty_hall_inverse`、`rope_60_easy` |

**只有 space-bunny 掉坑,且掉的两题正是定势效应的经典案例**:

| 题 | 期望 | space-bunny 答 | 失效模式 |
|---|---|---|---|
| `monty_hall_inverse` | keep, 0.6667 | **switch, 0.3333** | 沿用原 Monty Hall 的"换门"套路 |
| `rope_60_easy` | 1 根 1 步 | **2 根 3 步** | 过度复杂化(套用两端点燃) |

**结论**:这批题对 **gemini 与 shangtang 仍然饱和**。
与 `adv_premise`/`trap_mushroom` 一样,**未能解决"非 candy 题型饱和"的问题**。

### 3.1 由此确认的一个规律

| 模型 | candy 题 | 降智题(12) | 其他题型 |
|---|---|---|---|
| gemini | 100% | 100% | 100% |
| shangtang | 33.3% | **100%** | 100% |
| space-bunny | 0% | 83.3% | ~90% |

**shangtang 在 candy 题上 33.3%,却在降智题上 100%** —— 说明这两类题
考察的是**不同能力**:
- candy 题:需要从题干**提取隐含约束**(形状可分辨)
- 降智题:需要**抑制对原题的套用**(定势效应)

**gemini 两类都满分,是唯一在审题类题上全面可靠的模型。**

### 3.2 判分过严风险(已修)

实测发现判分器对精度敏感:

| 期望 | 模型答 | 判对? |
|---|---|---|
| `0.6667` | `0.667` / `0.666666` / `2/3` | ❌(都正确但判错) |
| `1.0000` | `0.9999` | ❌(真实值略小于 1) |

**修法**:在题面明确要求"保留 4 位小数并四舍五入"。
已在 v2 题集中修正,并自检通过(参考答案 12/12 判对)。

---

## 四、可选的后续题库

[LLM-Ruozhiba-QA](https://github.com/hzwer/LLM-Ruozhiba-QA) 有 **1000 道**中文弱智题,
但多为语言歧义/幽默类,**答案是开放式的**(如"只剩一个心脏了还能活吗"),
难以程序化判分。若要接入需:
- 逐题人工标注期望答案(成本高),或
- 引入 LLM 评委(本仓已明确避免)

**暂不接入**,记录备选。

---

## 五、诚实边界

- 本仓的 12 题**改写了原题**(加 JSON 格式要求),与原题库**不完全等同**,
  不可直接与 MisguidedAttention 的评测分数对比。
- 部分题的期望答案**存在解释空间**(如 `rope_20_impossible` 依赖
  "不能对折"这一前提,已在题面明确写出)。
- `birthday_easy_inverse` 期望 `1.0000` 是**四舍五入结果**,
  真实值略小于 1;若模型答 `0.9999` 会被判错,属**判分过严**风险,已记录。
- MisguidedAttention 的 52 题源文件是**加密的**(`misguided_attention_v4_long.scr`),
  本仓题目取自其 README 公开文本,未使用加密文件。
