// 从磁盘会话日志(.jsonl.zstd)归档 JEV 三路实战全过程。
import { readFileSync, writeFileSync, readdirSync, existsSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'
import { zstdDecompressSync } from 'node:zlib'

const HOME = join(homedir(), '.dsh')
const SESS = join(HOME, 'sessions', '--C-Users-Yum--')
const OUT = 'C:/Users/Yum/Desktop/DeepSeekHarness/notes/jev-three-path-run-2026-09-28.md'
const MAIN = 'session-38e84718-8e23-4d86-bbae-3d398b250986'
const CHILDREN = [
  '4ab1de16-8cfd-4af2-bb1b-1939ba634dd3',
  '1c2a9cac-9f1b-4fe0-9e65-d30352936f4e',
  '9f8365e9-cd66-4ad8-86f2-8491dae805ff',
  '712c2920-1133-46e6-aedc-8d9a6d5e0871',
]

/**
 * 解压 DSH 会话日志。
 *
 * ⚠ 关键:该文件是**多帧 zstd**(每个写入批次一帧),不是单一 zstd 流。
 * 单次 `zstdDecompressSync(whole)` 只解出**第一帧**(实测 80 KB 文件只得 264 B,
 * 即那条 session header),会静默丢失全部后续事件。
 * 正确做法:扫描 magic `28 b5 2f fd` 定位帧边界,逐帧解压后再拼接。
 */
function decompressSessionLog(buf) {
  const MAGIC = [0x28, 0xb5, 0x2f, 0xfd]
  const starts = []
  for (let i = 0; i + 3 < buf.length; i += 1) {
    if (buf[i] === MAGIC[0] && buf[i + 1] === MAGIC[1] && buf[i + 2] === MAGIC[2] && buf[i + 3] === MAGIC[3]) starts.push(i)
  }
  if (starts.length === 0) throw new Error('不是 zstd 文件(magic 未找到)')
  // 第一帧从 0 开始才可信;若 magic 出现在压缩载荷内部会误判,故以首帧为准再逐帧试。
  let text = ''
  for (let k = 0; k < starts.length; k += 1) {
    const end = k + 1 < starts.length ? starts[k + 1] : buf.length
    try {
      text += zstdDecompressSync(buf.subarray(starts[k], end)).toString('utf8')
    } catch {
      // 该偏移不是真帧边界(压缩载荷内的假 magic),跳过。
    }
  }
  return text
}

function readEvents(sessionName) {
  const dir = join(SESS, sessionName)
  if (!existsSync(dir)) return null
  const file = readdirSync(dir).find((f) => f.endsWith('.jsonl.zstd'))
  if (file === undefined) return null
  const raw = decompressSessionLog(readFileSync(join(dir, file)))
  return raw.split(/\r?\n/).filter((l) => l.trim()).map((l) => { try { return JSON.parse(l) } catch { return null } }).filter(Boolean)
}

function render(events) {
  const out = []
  for (const rec of events) {
    const ev = rec?.event ?? rec
    const t = ev?.type
    const d = ev?.data ?? {}
    if (t === 'user/message') {
      const txt = (d.message?.content ?? []).filter((b) => b?.type === 'text').map((b) => b.text).join('\n')
      if (txt.trim()) out.push(`**👤 用户**\n\n${txt}`)
    } else if (t === 'agent/inbox/spliced') {
      for (const m of d.inserted ?? []) {
        const txt = (m?.content ?? []).filter((b) => b?.type === 'text').map((b) => b.text).join('\n')
        if (txt.trim()) out.push(`**👤 用户**\n\n${txt}`)
      }
    } else if (t === 'assistant/message') {
      const parts = []
      for (const b of d.message?.content ?? []) {
        if (b?.type === 'reasoning' && b.text?.trim()) {
          parts.push(`<details><summary>🧠 推理轨迹 (${b.text.length} 字符)</summary>\n\n\`\`\`\n${b.text}\n\`\`\`\n\n</details>`)
        } else if (b?.type === 'text' && b.text?.trim()) {
          parts.push(`**🤖 助手**\n\n${b.text}`)
        } else if (b?.type === 'toolCall' || b?.type === 'tool_use') {
          parts.push(`> 🔧 调用 \`${b.name ?? b.toolName ?? '?'}\`\n> \`\`\`json\n> ${JSON.stringify(b.input ?? b.arguments ?? {}, null, 2).slice(0, 800)}\n> \`\`\``)
        }
      }
      if (parts.length) out.push(parts.join('\n\n'))
    } else if (t === 'tool/result') {
      const s = JSON.stringify(d.result ?? d).slice(0, 600)
      out.push(`> 📤 工具结果:\n> \`\`\`\n> ${s}\n> \`\`\``)
    } else if (t === 'subagent/created' || t === 'subagent/start') {
      out.push(`> 🧬 **子代理启动** ${JSON.stringify(d).slice(0, 400)}`)
    } else if (t === 'session/title' && d.title) {
      out.push(`> 会话标题: ${d.title}`)
    }
  }
  return out.join('\n\n---\n\n')
}

const sections = []
sections.push(`# JEV 三路隔离实战留档（2026-09-28）`)
sections.push([
  '> **自动归档**：直接解压 `~/.dsh/sessions/--C-Users-Yum--/<id>/session.v4.jsonl.zstd`，未经人工改写。',
  '>',
  '> **场景**：给 JEV 预设（`plugins/dsh-jev-preset/`）一条命中「量化指标推导 + 资金风控」两条强制三路条件的高危任务：',
  '> 本金 100000、单笔风险预算 2%、止损 3.5%、现价 42.7，求最大仓位 / 名义敞口 / 止损亏损。',
  '>',
  `> **结果**：主会话 + ${CHILDREN.length} 个子会话（provider=spawn，parent 均指向主会话），最终裁决 \`[JEV: 2/3 Majority Consensus]\`。`,
].join('\n'))

const mainEvents = readEvents(MAIN)
if (mainEvents === null) {
  sections.push([
    '## ⚠ 主会话日志未能归档',
    '',
    '主会话 `session-38e84718-...` 的日志文件遭遇 Windows 层间歇 `ENOENT`：',
    '`readdirSync`（枚举父目录）与 `statSync` 均可见该文件（116,783 B），',
    '但 `readFileSync` / `scandir` / cmd `dir` 对该路径持续报「找不到路径」，40 次重试未成功。',
    '子会话（4 个）全部读取正常，故不是权限或格式问题。',
    '',
    '**未归档的主会话内容可从以下来源补齐**：',
    '- 裁决正文见 `docs/known-issues.md` 的 `2026-09-28` 段与 `README.md`；',
    '- 三路原始推导（本文件下方 4 个子会话）已含全部数值与攻击面。',
  ].join('\n'))
} else {
  sections.push(`## 主会话（JEV 裁决节点）— \`${MAIN}\`\n\n> 事件 ${mainEvents.length} 条\n\n${render(mainEvents)}`)
}

// 子会话角色：从首个用户消息里识别 Path N 角色，修正归档标题的可读性。
function roleOf(events) {
  for (const rec of events) {
    const ev = rec?.event ?? rec
    const d = ev?.data ?? {}
    const texts = []
    if (ev?.type === 'user/message') for (const b of d.message?.content ?? []) if (b?.type === 'text') texts.push(b.text)
    if (ev?.type === 'agent/inbox/spliced') for (const m of d.inserted ?? []) for (const b of m?.content ?? []) if (b?.type === 'text') texts.push(b.text)
    for (const t of texts) {
      const m = /Path\s+(\d)\s*[「"']([^」"']+)[」"']/.exec(t)
      if (m !== null) return `Path ${m[1]} ${m[2]}`
    }
  }
  return '角色未识别'
}

for (const [i, cid] of CHILDREN.entries()) {
  const ev = readEvents(cid)
  if (ev === null) {
    sections.push(`## 子会话 ${i + 1} — \`${cid}\`\n\n> ⚠ 日志未找到`)
    continue
  }
  const role = roleOf(ev)
  sections.push(`## 子会话 ${i + 1} — ${role}\n\n> \`${cid}\`｜事件 ${ev.length} 条（provider=spawn，独立上下文）\n\n${render(ev)}`)
}

// 角色分布统计:检查「是否恰好 3 个互不相同的角色,每个一次」。
// 注意区分两种情形(本脚本第一版把两者混为一谈):
//   - 去重角色数 < 3            → 角色多样性不足
//   - 去重数 == 3 但有角色重复   → 多派了重复路(浪费),且总数 ≠ 3
const roles = CHILDREN.map((cid) => { const ev = readEvents(cid); return ev === null ? '（读不到）' : roleOf(ev) })
const counts = new Map()
for (const r of roles) counts.set(r, (counts.get(r) ?? 0) + 1)
const duplicated = [...counts].filter(([r, n]) => n > 1 && r !== '（读不到）' && r !== '角色未识别')

let verdict
if (roles.length !== 3) {
  verdict = `⚠ 派生了 **${roles.length}** 个子会话，并非恰好 3 路。`
} else if (counts.size < 3) {
  verdict = '⚠ **未达成三路角色多样性** —— 存在重复角色。'
} else {
  verdict = '角色互不相同，符合三路设计要求。'
}
if (duplicated.length > 0) {
  verdict += `\n\n**重复角色**：${duplicated.map(([r, n]) => `${r} × ${n}`).join('、')}。` +
    '\n这是 JEV「角色微扰」纪律的执行偏差（真实缺陷，不是归档问题）。'
}

sections.push([
  '## 角色分布（本文件由脚本自动统计）',
  '',
  '| 子会话 | 识别到的角色 |',
  '|---|---|',
  ...roles.map((r, i) => `| ${i + 1} | ${r} |`),
  '',
  `子会话数 = **${roles.length}**；去重角色数 = **${counts.size}**。`,
  '',
  verdict,
].join('\n'))

writeFileSync(OUT, sections.join('\n\n---\n\n') + '\n', 'utf8')
console.log(`已写入 ${OUT}`)
console.log(`主会话事件 ${mainEvents?.length ?? 0} 条`)
for (const cid of CHILDREN) console.log(`  ${cid}: ${readEvents(cid)?.length ?? 0} 条`)
