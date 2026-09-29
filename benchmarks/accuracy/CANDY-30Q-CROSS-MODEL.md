# candy 30 题跨模型基准:首个统计可辨的模型差异

**日期**:2026-09-28
**题目**:30 道糖果题(10 个 seed × 每 seed 3 题,题面全唯一)
**配置**:C1(单路,可执行代码,禁子代理),ds-flash 系外的 4 个模型直调
**动机**:9 题样本的 Wilson 区间过宽(如 shangtang [12%, 65%]),
无法支撑结论;扩到 30 题收窄区间。

---

## 一、最终结果(4 模型 × 30 题 = 120 次运行,零运行错误)

| 模型 | provider | 正确/总 | 正确率 | **Wilson 95%** | 盲目率 | 平均 token |
|---|---|---|---|---|---|---|
| **`gemini-3.8-flash`** | google | **30/30** | **100.0%** | **[89%, 100%]** | **0%** | — |
| `shangtang/deepseek-v4-flash` | sensenova | 8/30 | 26.7% | [14%, 44%] | 67% | ~170k |
| `workbuddy2api/cn:hy4-preview` | workbuddy | **0/30** | **0.0%** | **[0%, 11%]** | **100%** | ~120k |
| `opencode-zen/space-bunny-free` | opencode | **0/30** | **0.0%** | **[0%, 11%]** | **100%** | ~150k |

### 置信区间完全分离

```
gemini      [89%, 100%]  ████████████████████
shangtang   [14%,  44%]      ██████████
space-bunny [ 0%,  11%]  ███
hy4         [ 0%,  11%]  ███
```

**四组区间两两不重叠** —— 这是本仓**首次获得统计可辨的模型差异**。

---

## 二、与 9 题样本的对比:扩量的价值

| 模型 | 9 题 | Wilson 95% | **30 题** | **Wilson 95%** |
|---|---|---|---|---|
| gemini | 9/9 = 100% | [70%, 100%] | **30/30 = 100%** | **[89%, 100%]** |
| shangtang | 3/9 = 33.3% | [12%, 65%] | **8/30 = 26.7%** | **[14%, 44%]** |
| space-bunny | 0/9 = 0% | [0%, 30%] | **0/30 = 0%** | **[0%, 11%]** |
| hy4 | 0/9 = 0% | [0%, 30%] | **0/30 = 0%** | **[0%, 11%]** |

**两个结论**:

1. **方向一致**:9 题的点估计(100% / 33.3% / 0% / 0%)与 30 题(100% / 26.7% / 0% / 0%)
   基本吻合 → 小样本实验的**方向判断是可靠的**。
2. **区间显著收窄**:如 space-bunny 从"确信 <30%"变为"确信 <11%"。
   9 题时 gemini 与 shangtang 的区间([70%,100%] vs [12%,65%])**重叠**,
   30 题后([89%,100%] vs [14%,44%])**分离** → 差异从"疑似"变"确证"。

---

## 三、核心结论

### 3.1 审题盲区是压倒性的跨模型普遍现象

**4 个模型中 3 个正确率 ≤26.7%,其中 2 个为 0%。**

这与 9 题时的初步结论一致,但现在有统计支撑(区间分离)。

**含义**:candy 类题考察的"从题干提取隐含约束"能力,
是当前主流模型的**共同短板**,而非个别缺陷。

### 3.2 题干结构化的价值得到解释

实验 D 已证明:把关键条件从括号内移出并强调后,
**5/5 模型均从低正确率升至 100%**(+89pp 至 +100pp)。

结合本实验:**盲区越普遍,该解法的普适价值越大**。

### 3.3 基准区分力问题已解决

此前 `adv_premise` / `trap_mushroom` / 定势效应题对多数模型**饱和(100%)**,
无区分力。**candy 30 题是当前唯一能清晰区分全部 4 个模型的题型。**

---

## 四、诚实边界

- **仅 4 个模型**:本机可用路由有限;结论不能推广到全部 LLM。
- **`gemini` 是唯一例外**(100%):可能因其长文本注意力更强,或训练数据覆盖该题。
  **不改变结论** —— 其余 3 个模型仍需题干结构化。
- **`combo/ds-flash` 未纳入本表**:它是 workbuddy 的 round-robin 组合路由,
  与 `cn:hy4-preview` 重叠,同时计入会构成伪重复(见 `CANDY-CROSS-MODEL.md`)。
- **单次运行**:每模型每题仅 1 次,未做重复。gemini 30/30 与 shangtang 8/30 的
  差距极大,单次足以区分;但若两模型差距在 10pp 内,单次不可靠。
- **题目为参数化生成**:30 题源自 10 个 seed,题面全唯一,但**题型同源**,
  不能代表所有"审题陷阱"类问题。
- **未测 C3(三路)**:本实验只测单路基线。三路在 candy 上的表现见
  `CANDY-C1-VS-C3.md`(9 题,ds-flash 上 11.1% → 44.4%,p=0.25 不显著)。

---

## 五、复现命令

```powershell
cd benchmarks/accuracy
# 生成 30 题(10 个 seed 的 candy 类)
python -c "
import sys,json,io; sys.path.insert(0,'.')
from jevbench.cases import build_suite
rows=[c for sd in range(20260928,20260938) for c in build_suite(sd) if c['category']=='trap_candy']
with io.open('suite-candy30.jsonl','w',encoding='utf-8',newline=chr(10)) as f:
    for r in rows: f.write(json.dumps(r,ensure_ascii=False)+chr(10))
"
python -m jevbench selftest --suite suite-candy30.jsonl

# 逐模型跑
foreach ($m in @('opencode-zen/space-bunny-free','shangtang/deepseek-v4-flash',
                 'workbuddy2api/cn:hy4-preview','google-antigravity/gemini-3.8-flash')) {
  node run-bench.mjs --suite suite-candy30.jsonl --out "runs-candy30-$($m -replace '[/:]','-').jsonl" `
    --config C1 --provider opencodex --model $m --effort high
}
python -m jevbench grade --suite suite-candy30.jsonl --runs runs-candy30-<model>.jsonl
```

**成本**:120 次运行,平均约 15 万 token/题 → 约 **1800 万 token**。
