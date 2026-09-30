# 测量 bug:C3 组 60% 样本从未等到裁决(2026-09-30)

**性质**:本仓**最严重**的一次方法论事故 —— 不是"解读错了",是"**根本没测到**"。
**影响范围**:**仅 30 题批** `runs-c30-c3-sb.jsonl`。其推论
(3.3% / p=1.0 / 盲目率 33% / ×6.3 / "三路对推理层无效")均为**测量伪影,已作废**。

> ⚠️ **注意区分**:`×18.7` 出自 **9 题批** `runs-candy.jsonl`,**未受影响、依然有效**
> (逐文件审计见第八节)。早期版本的本文误将 9 题批一并列入作废,已修正。

**闭环状态(2026-09-30 全部完成)**:修复 → 重测 → 改版 → 文档对齐。

---

## 一、症状

`runs-c30-c3-sb.jsonl`(30 题 C3,space-bunny)判分后:

| 判分理由 | 条数 |
|---|---|
| **`无可解析的 ```json 答案块`** | **18 / 30** |
| `min_candies: 得到 X,期望 Y`(真答错) | 11 |
| `ok` | 1 |

看那 18 条的 `text`,**全部停在等待态**:

```
三路运行中,等结算。
三路仍在跑,等结算通知后再出最终裁决。
等 3 条结算通知齐备再裁决。
仍等 Path 3(执行脚本路)。
```

`end_reason` 全是 `completed`,`elapsed_ms` 中位 **97s**(超时上限 1800s)。

**即:不是超时,是主会话正常结束了回合,但裁决还没发生 —— 而运行器已经收工了。**

---

## 二、根因

`run-bench.mjs` 旧循环:

```js
while (Date.now() - started < TIMEOUT_MS) {
  await sleep(5000)
  last = lastTurn(page.records ?? [])
  if (last.ended) { ...; break }   // ← 本轮结束就收工
}
```

而 `cordis.patch.yml:459` 配置 `backgroundMode: continuable`。官方
`@deepseek-ai/dsh-tool-subagent` [README.zh.md](../README.zh.md) 明确:

> `continuable` 策略下,省略或为 `true` 的 `run_in_background` 会启动一个持久化子 agent,
> 并返回 `started subagent <childId>`,**不等待结果**;子 agent 的 Activation 结束时,
> 运行时投递一条结算通知……把 `run_in_background` 设为 `false` **可在前台等待结果**。

**所以 JEV 的回合结构天生是**:派发三路 → 父会话 turn **立即** `completed` →
(子代理在后台跑)→ 结算通知注入 → **新 turn** 才做裁决。

`last.ended` 在**第一步就为真**。运行器永远只看到"等结算"那一轮。

**这不是 persona 缺陷** —— persona §3.1 已经写了"必须等 3 条结算通知齐备"。
是**运行器没给模型机会**。

---

## 三、修复

收敛判据改为客观状态,不再依赖文本猜测(`runner-lib.mjs`):

```js
converged({ ended, runningKids, hasAnswer, idleMs, settleMs })
// = 本轮已结束 AND 无 running 子会话 AND (已出答案块 OR 静默达 settleMs)
```

| 新增 | 作用 |
|---|---|
| `runningChildren(list, sid)` | 数 `parentSessionId===sid && running===true` 的会话(`session/list` 有 `running` 字段) |
| `hasAnswerBlock(text)` | 是否已出现 ```json 块 → 可提前收工,不必空等 |
| `row.peak_subagents` / `row.saw_running_child` | 留证:这题到底派了几路 |
| `row.error = '未收敛...'` | 真没收敛时**明确标错**,不再静默记 0 分 |

回归测试:`tests/test-accuracy-runner.mjs` 新增 4 条(`runningChildren` /
`hasAnswerBlock` / `converged` ×2),9/9 绿。

---

## 四、修复前后对照(同批 3 题,唯一变量=是否等够)

| 题 | 修复前 | 修复后 |
|---|---|---|
| `trap_candy-20260928-00` | ❌ 无可解析 json | ✅ **正确**(14) |
| `trap_candy-20260928-01` | ❌ 无可解析 json | ✅ **正确**(20) |
| `trap_candy-20260928-02` | ❌ 无可解析 json | ❌ 错(27 vs 19) |

**修复后 2/3,修复前 0/3。**

耗时对比也印证:修复前这 3 题 48s / 168s / 52s(收工太早);
修复后 482s / 355s / 159s(真的等到了三路跑完)。

---

## 五、连带影响(必须一并重测)

### 5.1 「盲目率 100%→33%」同样是伪影(已证实)

旧口径下"无答案"被算成**非盲目**(因为 `None != blind值` 恒成立),
于是 18 条没出答案的样本把**分母**撑大,盲目率被机械压低:

| 口径 | C3 盲目率 | 算法 |
|---|---|---|
| **旧口径**(文档里那个 33%) | **33.3%** | 盲目 10 / 全 30 ← 无答案 18 条被算成"非盲目" |
| **真实口径**(只看出答案的) | **83.3%** | 盲目 10 / 出答案 12 |
| C1 对照 | 100.0% | 盲目 30 / 30 |

**分子(盲目 10)完全没变,变的只是分母。**
故"三路把盲目率打到 33%、改善信息提取"**是纯算术伪影** ——
JEV 此前**唯一**的正面证据也已作废。

脚本:`_analyze_blindrate.py`(可复现)。

### 5.2 小样本重测(修复后 7 题,先出部分结果)

| 组 | 正确 | 无答案 | 正确率 |
|---|---|---|---|
| C1 单路(历史,可信) | 0/7 | 0 | 0.0% |
| C3 三路(修复前) | 0/7 | **5** | 0.0% |
| **C3 三路(修复后)** | **3/7** | 0 | **42.9%** |

配对比较:修复前 `only_C3=0, p=1.0` → 修复后 `only_C3=3, p=0.25`。

**更关键:错答的性质**。逐题对照"盲目值"(忽略形状可分辨条件的答案):

| 题 | 期望(读到条件) | 盲目值(漏读) | C3 得到 | 判定 |
|---|---|---|---|---|
| 20260928-00 | 14 | 24 | 14 | ✅ 正确 |
| 20260928-01 | 20 | 26 | **26** | ❌ **盲目** |
| 20260928-02 | 19 | 27 | **27** | ❌ **盲目** |
| 20260929-00 | 20 | 28 | **28** | ❌ **盲目** |
| 20260929-01 | 19 | 25 | 19 | ✅ 正确 |
| 20260929-02 | 15 | 23 | 15 | ✅ 正确 |
| 20260930-00 | 17 | 20 | **20** | ❌ **盲目** |

**4 个错答 100% 精确等于盲目值** —— 即失败**全部**发生在"漏读关键条件"这一层,
**没有一例是"读到了但算错"**。

**推论**:三路并未消除审题盲区,只是**部分题碰巧读到了**。糖果题无可执行断言,
故这组实验**只覆盖了"三路 vs 审题盲区"**,没覆盖执行断言。

> ✅ **后续已补测(见 `EXP-F` / `EXP-G`)**:
> - **执行断言对可跑断言的题有效**:30 题 **24/30 → 30/30**,p=0.0312,成本 ×2.0
> - **三路在断言之上增益为 0**:30 题 **30/30 vs 30/30**,p=1.0,成本 ×15.3

### 5.3 其它受影响结论

| 结论 | 出处 | 状态 |
|---|---|---|
| C3 正确率 3.3% | `CANDY-30Q-C1-VS-C3.md` | ❌ **已作废** |
| McNemar p=1.0 | 同上 | ❌ **已作废** |
| **盲目率 100%→33%** | 同上 | ❌ **已证实为伪影**(见 5.1),真实 83.3% |
| 成本 ×6.3(30 题批) | 同上 | ❌ **已作废**(分母虚低:提前收工→token 少算) |
| "三路对推理层无效" | `FINAL-CONCLUSIONS.md` | ❌ **已作废** |
| **"三路改善信息提取"** | `capability-boundary.md` | ❌ **已证伪**(见 5.1) |
| 成本 ×18.7(9 题批) | `CANDY-C1-VS-C3.md` | ✅ **有效**(该批未受影响,见第八节) |
| 11.1%→44.4%(9 题批) | 同上 | ✅ **有效** |
| "换模型优于加路数" | `capability-boundary.md` 3.1 | ✅ **仍成立**(依据 9 题批) |

**C1 组不受影响**:`CONFIG_PREFIX.C1` 明令"不要派生子代理",无子会话 → 单 turn 即终结。

---

## 六、教训(沉淀为纪律)

| # | 教训 |
|---|---|
| 1 | **测量工具的失效模式,必须与结论同等验证。** 本仓前三次方法论错误都是"解读错了",这次是"**根本没测到**" —— 后者更隐蔽,因为它产生的数字看起来完全正常(有 Wilson 区间、有 p 值)。 |
| 2 | **"无答案"与"答错"必须分开统计。** 18/30 的 `无可解析 json` 本应是刺眼的红旗,却被混进 `correct=False` 一起算进正确率。 |
| 3 | **异步/后台执行的收敛判据必须用客观状态(子会话 `running`),不能用"文本看起来说完了"。** |
| 4 | 対称验证:跑完先看**错误理由分布**,再信正确率。理由里出现大量同类"格式/缺失"项时,先查测量链路。 |

---

## 七、复现

```powershell
cd benchmarks/accuracy
# 修复后跑 3 题
node run-bench.mjs --suite suite-candy30.jsonl --out _runs-verify-fix.jsonl `
  --config C3 --provider opencodex --model opencode-zen/space-bunny-free --effort high `
  --timeout 1800 --settle 120 --limit 3
python -X utf8 _probe_compare.py     # 修复前后对照
node --test ../../tests/test-accuracy-runner.mjs
```

---

## 八、影响范围审计(逐文件,2026-09-30)

**作废范围不能靠推断,必须逐文件查。** 审计脚本 `_audit_measurement.py`
(对每个 `runs-*.jsonl` 统计 C3 行的「无答案」与「运行失败」数):

| 数据源 | 配置 | 无答案 | 运行失败 | 判定 |
|---|---|---|---|---|
| **`runs-candy.jsonl`(9 题)** | C1 | 0/9 | 0 | ✅ **可信** |
| | **C3** | **0/9** | **0** | ✅ **可信** |
| **`runs-c30-c3-sb.jsonl`(30 题)** | C3 | **18/30** | 0 | ❌ **失效** |
| `runs-c0-40q-dsflash.jsonl` | C0 | 0/40 | 0 | ✅ 可信(无子代理) |
| `runs-c0-opus-archived.jsonl` | C0 | 0/30 | 7 | ⚠️ 部分失败,非本 bug |
| `runs-candy30-*`(4 个模型) | C1 | 0/30 | 0–1 | ✅ 可信(无子代理) |
| 其余 C1/C0 批 | — | 0 | 0–2 | ✅ 可信(无子代理) |

**关键结论**:

> **只有 30 题批受本 bug 影响。9 题批(11.1%→44.4% / ×18.7)完全有效。**

原因:9 题批跑得早,恰好每道题的裁决都赶在运行器收工之前完成;
而 30 题批里 60% 的题裁决慢于收工点。**同一 bug 在不同批次上的表现不同**,
所以必须逐批审计,不能"一处发现、全批作废"。

**已据此修正的文档**:
- `docs/capability-boundary.md` 顶部更正框改为区分 9 题/30 题
- `docs/FINAL-CONCLUSIONS.md` 顶部与 2.6 节改用重测数据
- `cordis.patch.yml` persona §3.0 的"盲目率 100%→33%"改为"部分有效但不显著"

---

## 九、复现

```powershell
cd benchmarks/accuracy
# 修复后跑 3 题
node run-bench.mjs --suite suite-candy30.jsonl --out _runs-verify-fix.jsonl `
  --config C3 --provider opencodex --model opencode-zen/space-bunny-free --effort high `
  --timeout 1800 --settle 120 --limit 3
python -X utf8 _probe_compare.py         # 修复前后对照
python -X utf8 _audit_measurement.py     # 逐文件可信度审计
python -X utf8 _audit_9q.py              # 核实 9 题批未受影响
node --test ../../tests/test-accuracy-runner.mjs
```

---

## 十、待办

- [x] 30 题 C1/C3 全量重跑(已完成:A1/A2、C3F、强模型对照)
- [x] 重跑后回填 `CANDY-30Q-C1-VS-C3.md`、`capability-boundary.md`、`FINAL-CONCLUSIONS.md`
- [x] 逐文件审计确定作废范围(第九节前的审计表)
- [ ] 反思:是否该给 `run-bench` 加 `--require-answer` 断言(无 json 块即判 `error` 而非 0 分)
      —— **部分已实现**:`jevbench grade` 现对无答案率 >20% 硬失败(退出码 3)
