# JEV 断言失败包(failure bundle)规范 v1

> 状态:v1(实现:断言 CLI 的 `--bundle-dir`;首个真实消费方见第八节)
> 定位:断言 CLI 的**失败证据载体**。不改退出码契约,不改断言算法,不默认落盘。
> 为什么单独一份:退出码契约(`0`/`1`/`2`/`3`)回答「**该做什么动作**」,
> 失败包回答「**到底发生了什么**」。两者正交,前者已在 persona 与两份 README 里,
> 后者此前不存在 —— 调用方拿到 `exit 1` 后,除了 stdout 的一行 JSON 之外无迹可查。

## 一、缺口

现状(stdout,已有):`{"status": ..., "assertion": ..., "result" 或 "error", "hint"?}`。

| 缺口 | 后果 |
|---|---|
| 输入 payload 不回显 | 看到失败却**无法复现**——`args` 只存在于调用方的命令行里 |
| 无 `repro_cmd` | 复现要手拼命令,拼错就变成一次**假复现** |
| 无时间戳与环境快照 | 无法区分「换了数据」与「换了环境」 |
| 只落 stdout,不落盘 | 跨会话/跨进程无留存;终端一滚就没了 |
| 无关联键 | 重跑通过后,**无法证明修的是同一个失败** |

最后一条是本规范的核心动机:一次「先红后绿」若不能证明两次运行针对同一输入,
那它与「直接跑一次绿的」在证据力上没有区别。

## 二、字段

| 字段 | 类型 | 来源 | 说明 |
|---|---|---|---|
| `schema_version` | string | 常量 | 固定 `jev.failure/1` |
| `bundle_id` | string | 计算 | `sha256(assertion + 规范化 args + ts)` 前 12 位 |
| `ts` | string | 运行时刻 | ISO 8601,UTC |
| `assertion` | string | CLI 入参 | 断言名 |
| `args` | object | **新增回显** | 解析后的 payload,键排序 |
| `status` | string | CLI | `fail` / `insufficient_data` / `error` |
| `exit_code` | integer | CLI | `1` / `3` / `2` |
| `error` | string | CLI | 断言文本或异常文本 |
| `hint` | string 或 null | CLI | 仅算术类输入错时存在 |
| `repro_cmd` | string | 组装 | 可直接粘贴执行的完整命令 |
| `env` | object | 计算 | `python` 版本 + `cli_sha256` |
| `resolved_by` | object 或 null | **回填** | 见第五节 |

成功(`status=pass`)默认**不写包** —— 本机制只承载失败证据。
若传了 `--resolves`,成功时才写一条解析记录(见第五节)。

## 三、落盘

```text
<bundle-dir>/<bundle_id>.json      # 每次失败一个文件,不覆盖
<bundle-dir>/latest.json           # 指向最近一次失败包的副本
```

`bundle_id` 的计算口径固定为 `sha256` 前 12 位十六进制,
输入为 `assertion`、`json.dumps(args, sort_keys=True, separators=(",", ":"))`、`ts` 三者拼接。
`ts` 参与哈希 ⇒ 同一断言同一输入的**多次失败各得一个 id**,不被静默去重 ——
「同一失败复发了几次」本身是信息。

落盘为**显式 opt-in**:不传 `--bundle-dir` 时行为与改动前完全一致。

## 四、消费契约

调用方读包后按 `exit_code` 分派动作,与 persona 的四值契约一致:

| exit | status | 动作 | 禁止 |
|---|---|---|---|
| `1` | `fail` | 重算或升级三路;`hint` 提示输入非法时先换数据 | 当作「环境问题」跳过 |
| `2` | `error` | 先修命令,不存在任何数值结论 | 当成「断言否定结论」——那是伪造验证 |
| `3` | `insufficient_data` | 补数据再跑 | 重算(不是算错) |

`repro_cmd` 是复现的唯一入口:重跑必须用它,不要手写命令。

## 五、关联

解析在**成功侧**发生。跑通时传 `--resolves <bundle_id>`,
CLI 把该包就地更新为:

```json
{"resolved_by": {"bundle_id": "<本次记录 id>", "ts": "<本次时刻>"}}
```

两个约束:

- 被解析的 `bundle_id` 必须**已存在**,否则不写、并在 stdout 加 `resolve_warning` 字段(不改变退出码)
- 只允许 `status=pass` 的调用解析失败包;失败调用传 `--resolves` 一律忽略

⇒ 「这次绿,修的是那次红」由 `resolved_by` 一条边承载,可机器校验。

## 六、非目标

- **不改退出码**:`0`/`1`/`2`/`3` 语义与 persona、两份 README 的三行表保持逐字一致
- **不默认落盘**:避免给不关心证据链的调用方制造文件
- **不替代 `benchmarks/accuracy/_runs-*.jsonl`**:那份记的是**会话级**结果
  (`case_id`/`session_id`/`tokens`/`converged`),本规范记的是**断言级**上下文,层次不同
- **不做自动清理**:包是证据,不由工具决定何时丢弃

## 七、未验证

- 消费方仅门禁一处(见第八节);断言 CLI 侧的 `--resolves` **仍无真实接入** ——
  落盘与解析已实现并由 `tests/test_failure_bundle.py` 覆盖,
  但「真实工作流里是否真的用 `--resolves`」未经验证
- `bundle_id` 的 12 位截断在**单目录**内的碰撞概率未实测(按 2^48 空间估算可忽略,未跑实验)
- 未定义包的保留策略与体量上限;门禁包体量随 `unmatched` 线性增长
  (g0 源实测 10 条不可判样本 → 包 2322 字节),上限未定

## 八、消费方:门禁 `gate_v2`

首个真实消费方是量化仓的门禁脚本 `nautilus-okx/scripts/v1_gate_v2.py`
(2026-10-09 接入)。它复用同一份 schema,但有**两处必须显式说明的差异**。

### 8.1 退出码契约不同(最重要)

门禁有自己的四档,与断言 CLI **不是同一套**:

| 判定 | 门禁 exit | 断言 CLI 对应 status | 断言 CLI exit |
|---|---|---|---|
| `PASS` | `0` | `pass` | `0` |
| `FAIL` | `1` | `fail` | `1` |
| `CONDITIONAL` | `1` | (无此档) | — |
| `INSUFFICIENT` | **`2`** | `insufficient_data` | **`3`** |

唯一冲突在 `INSUFFICIENT`(门禁 `2` / CLI `3`);`CONDITIONAL` 是门禁独有档,
CLI 词汇表里没有对应项。

⇒ 包**如实记录产生方的退出码**,不做归一化 —— 归一化会抹掉「这个码是谁定的」,
而消费方的动作表恰好依赖它。包同时给出:

- `verdict`:产生方的原生判定(四档之一)
- `status`:映射到 JEV 词汇的结果
- `exit_code_contract`:产生方契约的字符串快照

**消费方按 `verdict` 分派,不要拿 `exit_code` 去套第四节的动作表。**

### 8.2 附加字段

门禁包在第二节的 12 字段之外,额外带:

| 字段 | 说明 |
|---|---|
| `verdict` | 产生方原生判定 |
| `exit_code_contract` | 产生方退出码契约快照 |
| `stats` | 判定统计量(点估计 / CI / 事件数 / 方案) |
| `mechanism` | 机制层证据状态 |
| `unmatched` | 被判为不可用的样本及原因 |
| `sample_meta` | 样本来源与过滤计数 |

### 8.3 `error` 必须是真因

`error` 承载的是**判定未通过的原因**,不是产生方内部的任意 reason 串。

实测反例(施工中已修):门禁初版把机制层的 `reason` 填进 `error`,
而 `FAIL` 时机制层恰恰是「全部通过」—— 包里出现 `verdict=FAIL` 配
`error="全部通过"` 的自相矛盾,会把消费方引去查机制层,而真因在统计门。
现按门条件拼接(样本门 / 统计门 / 机制门),由
`tests/unit/scripts/test_v1_gate_v2.py` 的
`test_bundle_error_is_real_reason_not_mechanism` 守。

### 8.4 复现的边界

`repro_cmd` 复现的是**判定**,不是**逐字节输出**:门禁的 `mechanism.age_days`
随运行时刻变化,故 `verdict.json` 不逐字节可复现。
bootstrap 本身有固定种子(`random.Random(20260912)`),统计量确定。

### 8.5 接入方式

门禁新增两个 opt-in 参数,不传时行为与改动前逐字节一致:

| 参数 | 作用 |
|---|---|
| `--out-dir <path>` | 覆盖 `verdict.json` 输出目录(试算/测试用) |
| `--bundle-dir <path>` | 落失败包;`PASS` 不落 |

`--out-dir` 的存在使**测试可以完全不触碰生产 `results/`** —— 接入时的实测
就是靠它把输出与包都指向临时目录完成的。
