#!/usr/bin/env node
/**
 * launch-long-goal.mjs
 * 
 * 启动 JEV 模式 5 小时长程优化目标会话:
 * 1. RPC 创建全新独立会话 (agentPreset = 'jev')
 * 2. 注入精心设计的长程演进目标提示词 (Goal Prompt)
 * 3. 触发 DSH 的目标自动续跑驱动 (Goal-Round Driver)
 * 4. 记录会话元数据，输出监控入口
 */

import { readFileSync, writeFileSync, mkdirSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'

const HOME = join(homedir(), '.dsh')
const URL_FILE = join(HOME, 'web-url.txt')
const TARGET_PRESET = 'jev'

function readBase() {
  const text = readFileSync(URL_FILE, 'utf8')
  const line = text.split(/\r?\n/).find((l) => l.startsWith('url='))
  const url = new URL(line.slice(4))
  return { origin: url.origin, token: url.searchParams.get('token') }
}

async function authenticate(origin, token) {
  const r = await fetch(`${origin}/?token=${encodeURIComponent(token)}`, { redirect: 'manual' })
  const cookies = r.headers.getSetCookie?.() ?? []
  return cookies.map((c) => c.split(';')[0]).join('; ')
}

async function rpc(origin, cookie, endpoint, args = {}) {
  const r = await fetch(`${origin}/api/${endpoint}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json', cookie },
    body: JSON.stringify({ type: 'client-request', rpcId: crypto.randomUUID(), method: endpoint, payload: { args } }),
  })
  if (!r.ok) throw new Error(`${endpoint} → HTTP ${r.status}`)
  const j = await r.json()
  if (j.result?.ok !== true) throw new Error(`${endpoint} → ${j.result?.error?.code}: ${j.result?.error?.message}`)
  return j.result.value
}

// 目标（一字不差入库，不经模型转述）。
// 2026-09-28 根因修复：上一版的失败在于目标是经 session/prompt 纯文本下发，
// 模型收到后调用 create_goal 工具自行概括 objective，把"5 小时/举证门槛"丢掉，
// 且首轮干完即 complete（roundsStarted=0）。
// 本版直接走 commands/execute，服务端 command-goal 插件按字面入库。
export const JEV_LONG_GOAL_OBJECTIVE = [
  'JEV 模式真实三路隔离实测与诚实性闭环(第 2 次)。仍未完成前严禁 complete；Round < 25 前禁止调用 update_goal(complete)。',
  '背景:第 1 次(2026-09-28)用 Python if-elif 伪造了三路基准(已清理,见 benchmarks/run_stress_matrix.py 文件头诚实性声明)。',
  '本次只认以下两类证据,其余一律视为未完成:',
  '  (1) DSH 原生 subagent / workflow 真实派生的子会话 ID(形如 session-* / 纯 UUID),可在 session/list 查到且日志含 assistant 推导文本;',
  '  (2) 本地命令真实 stdout(贴命令与输出,非"已跑"口头报告)。',
  '阶段:',
  '  P0 修复 workflow-ptc 表达式核查(见下面修复单)。',
  '  P1 从 benchmarks/matrix-cases.json 选 3~5 个用例,经真实三路隔离采样跑通,附子会话 ID 与文本证据;凡失败即补派,记录失败原因。',
  '  P2 核对 docs/ 与 README 里"未测量"标注是否仍属实;经实测的数据才允许写回指标。',
  '  P3 CI/文档收尾,跑全量 npm test 与 smoke.mjs。',
  '收尾规则:每轮只做一小步,做完即结束本轮保留目标 active;未满 25 轮或任一阶段无证据,禁止 complete。',
].join(' ')

// ⚠️ 旧模板（2026-09-28 已弃用，作为失败教训留底）:
// 上一版把下面这段长文本经 session/prompt 发给模型，模型收到后自行调用
// create_goal 工具，把 objective 压缩改写、丢掉时长与举证约束，首轮干完即 complete
//（roundsStarted=0）。不要再用此方式启动长程目标，改走 commands/execute。
const JEV_LONG_GOAL_PROMPT_DEPRECATED = `
/goal 目标：深度调研与全方位优化 JEV 模式 (dsh-jev-preset)，执行高强度长程演化压测，持续运行至少 5 小时（目标完成前严禁提前结束），产出工业级完整成果并完成 GitHub 独立开源仓库发布。

【核心工作阶段规划（严禁跳过任何阶段，按步骤深度推进）】

### 阶段一：极端边界压力测试矩阵（第 0 - 1.5 小时）
1. 构造至少 30 个包含隐藏缺陷与精度陷阱的高危量化计算任务：
   - 包含：Tick 大小强制向上/向下截断、杠杆保证金阶梯爆仓、双边滑点穿透预算、时区夏令时错位、复权因子除零漏洞。
2. 调度 JEV 三路隔离采样真实运行，记录每个用例在三路中的表现：
   - 验证 Path 2 红队对抗者的攻击命中率；
   - 验证 Path 1 严谨推导者的收敛速度；
   - 验证沙箱执行（Pass@k）一票否决权对错误方案的淘汰有效性。
3. 统计并生成基准分析报告，找出三路共识率低于预期或出现语义分歧的边界条件。

### 阶段二：底层编排机制与异步协同优化（第 1.5 - 3.0 小时）
1. 深入对比测试：
   - 方式 A：当前的原生 subagent (continuable 后台 + settlement notice 异步回收)；
   - 方式 B：workflow-ptc (parallel() 同步 barrier + 严格断言)。
2. 实测高并发下的性能、延迟、内存占用与消息队列健壮性：
   - 测试当某一路子代理遭遇超时或 503 时的断路器与重试行为；
   - 优化补派逻辑，彻底消除角色重复（如 Path 3 重复派发）的偶发缺陷。
3. 优化 compaction 策略与长对话注意力保护机制。

### 阶段三：自动化客观断言库与辅助工具研发（第 3.0 - 4.0 小时）
1. 为 JEV 预设研发内建的量化数学与风控标准断言函数库（Python/pwsh 脚本套件）。
2. 让子代理能够直接调用这些标准化断言模板，而不是每次手写，进一步消除子代理的推理随机性。
3. 在本地测试套件中形成自动化回归守护（Regression Guard）。

### 阶段四：独立生产级项目封装与文档完备化（第 4.0 - 5.0 小时）
1. 在工作区将 dsh-jev-preset 彻底整理为独立的开源工程标准结构：
   - 补充完整的单元测试（覆盖 YAML 语法、Loader 合成、隔离域审计、深度限制、断言熔断）；
   - 编写中英文详尽文档、架构图、基准对比报告、性能评估表；
   - 编写 GitHub Actions CI 工作流配置 (.github/workflows/ci.yml)。
2. 进行全量静态与端到端测试，确保测试用例 100% 绿灯。

### 阶段五：GitHub 建立独立公共仓库并推送（本轮暂时跳过，由人确认后再做）
1. 在用户 GitHub 账号 (Yum-wu) 下创建 Public 仓库：dsh-jev-preset；
2. 初始化本地 git 仓库，规范化 commit message；
3. 配置 remote 并安全完成初始主分支推送；
4. 验证线上仓库页面与 README 渲染完整无缺。

【工作准则】
- 始终以事实和真实测试为准，严禁自欺欺人与虚假通过。
- 步步留痕，每次测试和重大发现实时更新日志与文档。
- 持续高负荷演化，不到 5 小时且未完全闭环前不停止！
`.trim()

// ⚠️ 旧模板（2026-09-28 已弃用，作为失败教训留底，已移入 docs/legacy-goal-prompt.md）。

async function main() {
  const { origin, token } = readBase()
  const cookie = await authenticate(origin, token)

  console.log(`[1] 正在向 ${origin} 请求创建专属 JEV 优化会话...`)
  const created = await rpc(origin, cookie, 'session/create', {
    request: {
      agentPreset: TARGET_PRESET,
      cwd: 'C:\\Users\\Yum\\Desktop\\DeepSeekHarness\\plugins\\dsh-jev-preset',
    },
  })

  const sessionId = created.sessionId
  console.log(`[2] JEV 会话创建成功: ${sessionId}`)
  console.log(`    绑定预设: ${created.agentPreset}`)

  // 记录到本地状态文件
  const statePath = join(HOME, 'jev-session-test', 'active-long-goal.json')
  mkdirSync(join(HOME, 'jev-session-test'), { recursive: true })
  writeFileSync(statePath, JSON.stringify({
    sessionId,
    preset: created.agentPreset,
    startedAt: new Date().toISOString(),
    minDurationHours: 5,
    prompt: JEV_LONG_GOAL_OBJECTIVE,
  }, null, 2))

  console.log(`[3] 经 commands/execute 下发 /goal(服务端直解析,不经模型转述)...`)
  const goalResult = await rpc(origin, cookie, 'commands/execute', {
    agentId: sessionId,
    line: `/goal ${JEV_LONG_GOAL_OBJECTIVE}`,
    submittedAttachments: [],
  })
  console.log(`  /goal 返回: ${JSON.stringify(goalResult).slice(0, 200)}`)

  console.log(`[4] 目标已入库！JEV 会话将由目标驱动器自动续跑。`)
  console.log(`    会话 ID: ${sessionId}`)
  console.log(`    状态档案: ${statePath}`)
  console.log(`    Web 访问: ${origin}/?token=${token}#session=${sessionId}`)
  console.log(`    监控命令: node tools/monitor-long-goal.mjs`)
}

main().catch(err => {
  console.error('启动长程目标失败:', err)
  process.exit(1)
})
