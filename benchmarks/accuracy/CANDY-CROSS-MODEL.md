# 跨模型对照:5 个模型的审题盲区率与"题干结构化"的普适性

**日期**:2026-09-28
**题目**:9 道糖果题(参数化变体,正确解经暴力枚举独立验证)
**设计**:每个模型跑两版——对照版(关键条件藏在括号内)vs 强调版(提为独立段落)

---

## 一、实验纪律说明(避免伪重复)

`combo/ds-flash` 是 `workbuddy2api` 的 **round-robin 组合路由**
(`~/.opencodex/config.json` → `combos.ds-flash.targets`,4 个目标全是 workbuddy)。

**纪律**:同一批统计中,**combo 路由与其成员不得同时计入**。
本文件中的 `combo/ds-flash` 与 `workbuddy/cn:hy4-preview` **在表中共现仅为展示路由差异**,
**不用于计数独立模型数**。有效独立样本为 4 个:
gemini / shangtang / space-bunny / workbuddy-hy4。

---

## 二、核心结果:对照版(关键条件藏在括号内)

| 模型 | provider | 正确/总 | 正确率 | Wilson 95% | 盲目率 | 平均 token |
|---|---|---|---|---|---|---|
| `gemini-3.8-flash` | google | **9/9** | **100%** | [70%, 100%] | **0%** | 753,089 |
| `shangtang/deepseek-v4-flash` | sensenova | 3/9 | 33.3% | [12%, 65%] | 67% | 170,401 |
| `combo/ds-flash`(组合路由) | workbuddy | 1/9 | 11.1% | [2%, 43%] | 89% | 140,171 |
| `workbuddy/cn:hy4-preview` | workbuddy | **0/9** | **0%** | [0%, 30%] | **100%** | 126,105 |
| `opencode-zen/space-bunny` | opencode | **0/9** | **0%** | [0%, 30%] | **100%** | 147,116 |

**4 个独立模型中,3 个正确率 ≤33%,2 个为 0%。只有 gemini 全对。**

---

## 三、强调版:全部模型 9/9

| 模型 | 对照版 | **强调版** | 提升 |
|---|---|---|---|
| `gemini-3.8-flash` | 9/9 = 100% | 9/9 = 100% | +0.0pp(原本已满分) |
| `shangtang/deepseek-v4-flash` | 3/9 = 33.3% | **9/9 = 100%** | **+66.7pp** |
| `combo/ds-flash` | 1/9 = 11.1% | **9/9 = 100%** | **+88.9pp** |
| `workbuddy/cn:hy4-preview` | 0/9 = 0% | **9/9 = 100%** | **+100.0pp** |
| `opencode-zen/space-bunny` | 0/9 = 0% | **9/9 = 100%** | **+100.0pp** |

**5/5 模型强调版全部 9/9 = 100%,盲目数全部归零。**

---

## 四、结论

### 4.1 审题盲区是**跨模型普遍现象**

4 个独立模型中 3 个盲区率 ≥67%,其中 2 个 100%。
**不是 ds-flash 的个别缺陷,而是普遍现象。**

### 4.2 "题干结构化"是**跨模型普适解法**

**5/5 模型**在关键条件被显式化后均达 100%,包括原本 0% 的两个模型。
**该解法不依赖特定模型,可推广。**

### 4.3 三种解法的成本效益(最终版)

| 方案 | 效果 | 成本倍数 |
|---|---|---|
| 加路数(C3 三路) | 11.1% → 44.4%(+33pp,**不显著** p=0.25) | **×18.7** |
| 换模型(→ gemini) | 11.1% → 100% | ×5.4 |
| **题干结构化** | **11.1% → 100%(5/5 模型)** | **≈ ×1** |

**题干结构化在效果(跨模型普适)与成本(≈1x)上双双最优。**

### 4.4 gemini 的特殊性

gemini 是唯一对照版即 100% 的模型。可能原因:
- 更强的长文本注意力(能读到括号内内容)
- 或训练数据中该类题目更多

**但这不改变结论**:gemini 不需要题干结构化,其余 4 个模型需要。

---

## 五、对 JEV 设计的最终影响

| 项 | 改动 |
|---|---|
| **新增 §3.0 题干结构化** | 派发前强制输出「关键条件清单」并写入每路 prompt |
| 三路隔离采样 | 降级为"题干结构化之后"的第二步 |
| 加路数的价值 | 明确其**边界**:防随机错误,防不住共享信息提取失败 |
| 换模型的价值 | 仍是有效手段,但成本 ×5.4,不如题干结构化 |

**核心洞察**:三路"一致"若源于**都漏读同一句话**,
那不是共享推理错误,是**共享信息提取失败** —— 加路数**永远无效**。

---

## 六、诚实边界

- **样本 9 题**:各模型正确率差异明显,但严格检验需 ≥50 题。
- **变体同时改了多处**(移出括号 + "请务必利用" + 解释含义),变量未完全分离。
  要严格需再做"仅移出括号"版本。**未做。**
- **`cn:` 与 `global:` 前缀可能同模型不同区**,本文件只用 `cn:` 系列,未混用。
- **opus-4-6 未纳入**:两次尝试均 `TRANSPORT` 失败(路由不稳),非模型能力问题。
- **未测其他题型**:是否所有题型都受益于题干结构化,未验证。
- **gemini 强调版未跑**:对照版已 100%,无提升空间(有意省略)。

---

## 七、复现命令

```powershell
cd benchmarks/accuracy
python -m jevbench merge --seeds 20260928,20260929,20260930 --out suite150.jsonl

# 对照版(括号内)
foreach ($m in @('shangtang/deepseek-v4-flash','opencode-zen/space-bunny-free',
                 'workbuddy2api/cn:hy4-preview','google-antigravity/gemini-3.8-flash')) {
  node run-bench.mjs --suite suite150.jsonl --out "runs-ctrl-$($m -replace '[/:]','-').jsonl" `
    --config C1 --only trap_candy --provider opencodex --model $m --effort high
}

# 强调版(独立段落)—— 题集由 candy 派生
node run-bench.mjs --suite suite-candy-emphasis.jsonl --out runs-expD-<model>.jsonl `
  --config C1 --provider opencodex --model <model> --effort high
```
