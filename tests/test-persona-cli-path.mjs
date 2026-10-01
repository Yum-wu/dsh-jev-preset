// A1:persona(§五)给出的断言 CLI 路径在**默认会话 cwd**(仓库根)下必须可执行。
//
// 缺陷背景:persona 原文写死相对路径 `packages/assertions/python/jev_assertions/cli.py`,
// 该路径只在 `plugins/dsh-jev-preset/` 下成立;而默认会话 cwd 是仓库根,
// 实测 `can't open file '...\\DeepSeekHarness\\packages\\...': [Errno 2]` exit 2。
//
// 本测试不检查「文本长什么样」,而是**真跑**从 persona 文本里解析出的命令 ——
// 因为 A1 的本质是「承诺与实际行为不一致」,只有执行能证伪。
//
// 判据(预注册,R9):
//   T1 persona §五 至少含一条 `python ...cli.py --func` 命令
//   T2 该命令在仓库根 cwd 下 exit 0,且 stdout 可 JSON 解析、status=pass
//   T3 persona 给出的路径**不得是**裸相对路径 `packages/assertions/...`(必须先定位)
//   T4 同一命令在插件目录 cwd 下同样 exit 0(不得只修一边)

import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { execFileSync, spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

const PLUGIN_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const REPO_ROOT = path.resolve(PLUGIN_ROOT, '..', '..')

function readPersonaPrefix() {
  const text = readFileSync(path.join(PLUGIN_ROOT, 'cordis.patch.yml'), 'utf8')
  const start = text.indexOf('prefix: |-')
  assert.ok(start > 0, 'cordis.patch.yml 里找不到 persona prefix 段')
  return text.slice(start)
}

/**
 * 从 persona 文本里抽出「定位 + 执行」两行,拼成一段可直接喂给 pwsh 的脚本。
 * 只抽原文,不重写 —— 否则测的是测试自己,不是 persona 的承诺。
 */
function extractRecipe(personaText) {
  const lines = personaText.split('\n').map((l) => l.trim())
  // 去掉行首中文/英文引导词(定位:/执行:),只留反引号里的可执行命令。
  const bare = (l) => l.replace(/^[^`]*`/, '').replace(/`$/, '')
  // 执行行现在带 Test-Path 守卫,匹配放宽到「含 $JEV 且含 python」。
  const resolveRaw = lines.find((l) => /\$JEV\s*=.*Resolve-Path/.test(l))
  const runRaw = lines.find((l) => /\$JEV/.test(l) && /python\s+\$JEV/.test(l))
  // 先断言再剥壳:否则 bare(undefined) 抛 TypeError,把「persona 缺命令」报成无关错误。
  assert.ok(resolveRaw, 'persona 里找不到含 `$JEV = ... Resolve-Path ...` 的定位命令')
  assert.ok(runRaw, 'persona 里找不到 `python $JEV --func ...` 执行命令')
  return [bare(resolveRaw), bare(runRaw)].join('\n')
}

/** 把 persona 命令里的 <断言名>/<json参数> 占位符换成真实值。 */
function materialize(script) {
  return script
    .replace(/--func\s+\S+/, '--func tick_floor')
    // 非贪婪 + 引号感知:上一版 `/--args\s+.*$/` 贪婪,会吞掉 args 之后的所有内容
    // (红队 40ce7816 次要发现 4)。这里只吃掉紧跟 --args 的那一个参数。
    .replace(/--args\s+("[^"]*"|'[^']*'|\S+)/,
      `--args '{"raw_price":100.12,"tick_size":0.01,"expected":100.12}'`)
}

/**
 * persona 不得给出**可执行形式**的裸相对路径。
 *
 * 判据修正 1(红队前自纠):初版「文本中不得出现 `packages/assertions`」过宽 ——
 * persona 里用作反例说明的同一字面量也会命中,导致修复后仍报红。
 *
 * 判据修正 2(红队 99af2984 实测):初版正则只挡字面 `python packages/...` 一种写法,
 * 15 种等价写法里**漏检 9 种**。本版改为「任意解释器调用形态 + 任意相对前缀 + 可选引号」。
 */
function hasExecutableBareRelativePath(personaText) {
  // 解释器调用:python / py / python3 / python.exe / python3.12 / pwsh,以及变量形式的 & $py
  const interpreter = '(?:python(?:\\.exe|3(?:\\.\\d+)?)?|py(?:\\.exe)?|pwsh|powershell|\\$\\w+)'
  // 路径前缀:允许 ./ ../ .\ 与引号包裹,只要最终落到 packages/assertions
  const relPrefix = '(?:["\']?)(?:\\.{0,2}[/\\\\])*'
  return new RegExp(`${interpreter}\\s+${relPrefix}["']?packages[/\\\\]assertions`, 'i').test(personaText)
}

test('A1-T1/T2: persona 给出的断言 CLI 配方在仓库根(默认会话 cwd)下真跑 exit 0', () => {
  const script = materialize(extractRecipe(readPersonaPrefix()))
  const r = spawnSync('pwsh', ['-NoProfile', '-Command', script], {
    cwd: REPO_ROOT,
    encoding: 'utf8',
    env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
  })
  assert.equal(r.status, 0, `配方在仓库根下失败:\n${script}\nstdout=${r.stdout}\nstderr=${r.stderr}`)
  const out = JSON.parse(r.stdout.trim().split('\n').filter(Boolean).pop())
  assert.equal(out.status, 'pass')
  assert.equal(out.assertion, 'tick_floor')
})

test('A1-T3: persona 不得给出裸相对路径 packages/assertions/...', () => {
  const persona = readPersonaPrefix()
  assert.equal(hasExecutableBareRelativePath(persona), false,
    'persona 仍出现可照抄执行的裸相对路径(python packages/assertions/...);在默认会话 cwd(仓库根)下必然 [Errno 2]')
})

test('A1-T4: 同一配方在插件目录 cwd 下同样 exit 0(不得只修一边)', () => {
  const script = materialize(extractRecipe(readPersonaPrefix()))
  const r = spawnSync('pwsh', ['-NoProfile', '-Command', script], {
    cwd: PLUGIN_ROOT,
    encoding: 'utf8',
    env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
  })
  assert.equal(r.status, 0, `配方在插件目录下失败:\n${script}\nstdout=${r.stdout}\nstderr=${r.stderr}`)
})

test('A1 回归: 缺陷原状(裸相对路径)在仓库根下必 exit 2 —— 证明测试真的能抓到这个 bug', () => {
  // 反向自检:若哪天 persona 又退回裸相对路径,本断言会先于 T2 报红。
  // 这里显式确认「裸相对路径确实是坏的」,避免测试变成永绿空壳。
  const r = spawnSync('python', ['packages/assertions/python/jev_assertions/cli.py', '--func', 'tick_floor',
    '--args', '{"raw_price":100.12,"tick_size":0.01,"expected":100.12}'], {
    cwd: REPO_ROOT,
    encoding: 'utf8',
  })
  assert.notEqual(r.status, 0, '裸相对路径竟在仓库根下通过 —— 环境已变,需重新评估 A1 判据')
  assert.match(r.stderr, /can't open file|Errno 2/)
})

test('A1-T5: $JEV 为空时必须 fail-loud,不得退化成 `python --func`(假信号)', () => {
  // 红队 40ce7816 发现:无守卫时 `python $JEV --func ...` 在 $JEV=$null 下退化成
  // `python --func ...`,报 "unknown option --func" —— 极易被误读成「跑过了」。
  //
  // 红队 99af2984 的**致命反证**:本测试初版漏调 materialize(),把 persona 原文
  // (含 `<断言名>` 占位符)直接喂给 pwsh,`<` 触发 ParserError 让两条断言白满足 ——
  // 即「删掉守卫」这个变体也全绿,守卫等于零覆盖。已修:必须先 materialize。
  const runLine = materialize(extractRecipe(readPersonaPrefix())).split('\n')[1]
  assert.doesNotMatch(runLine, /[<>]/, '执行行仍含占位符,materialize 未生效 —— T5 会退化成空壳')

  const r = spawnSync('pwsh', ['-NoProfile', '-Command', `$JEV = $null\n${runLine}`], {
    cwd: PLUGIN_ROOT,
    encoding: 'utf8',
  })
  assert.notEqual(r.status, 0, '$JEV 为空时竟然 exit 0 —— 存在「假装跑过」路径')
  assert.doesNotMatch(r.stdout + r.stderr, /unknown option --func/,
    '$JEV 为空时退化成了 `python --func`,这是会被误读为「已执行」的假信号')
  // 必须是「自己知道找不到」而不是「碰巧失败」:ParserError / 语法错误同样满足上面的断言。
  assert.match(r.stdout + r.stderr, /断言库未找到/, '失败原因不是「断言库未找到」,守卫可能已被删')
})

test('A1-T6: 删掉执行行守卫后 T5 必须报红(证明 T5 不是空壳)', () => {
  // 自检:构造一个**无守卫**的等价执行行,跑同样的断言,确认它会被判红。
  // 若此测试自身失效,说明 T5 的判据已退化为「任何非 0 退出都算过」。
  const unguarded = `python $JEV --func tick_floor --args '{"raw_price":100.12,"tick_size":0.01,"expected":100.12}'`
  const r = spawnSync('pwsh', ['-NoProfile', '-Command', `$JEV = $null\n${unguarded}`], {
    cwd: PLUGIN_ROOT, encoding: 'utf8',
  })
  const output = r.stdout + r.stderr
  // 无守卫时会命中「假信号」特征,或至少不会给出「断言库未找到」。
  assert.match(output, /unknown option --func/,
    '无守卫版本竟未产生假信号特征 —— T5 的判据可能已不足以区分有无守卫')
  assert.doesNotMatch(output, /断言库未找到/,
    '无守卫版本竟自称「断言库未找到」—— 守卫逻辑可能被误写进了裸命令里')
})

test('A1-T7: 主定位路径必须是 profile glob,不能被 fallback 掩盖成相对路径', () => {
  // 红队 99af2984 变体2 的盲区:把 Resolve-Path 的 glob 改成裸相对路径后,
  // T1/T2/T4 **仍然全绿** —— 因为 fallback 分支在仓库根恰好能救回,
  // 测试只验「配方能跑通」,验不出「主路径已写错」。
  // 这里直接静态断言主定位行含 profile glob 形态。
  const persona = readPersonaPrefix()
  const resolveRaw = persona.split('\n').map((l) => l.trim())
    .find((l) => /\$JEV\s*=.*Resolve-Path/.test(l))
  assert.ok(resolveRaw, '找不到主定位行')
  assert.match(resolveRaw, /\.dsh[\\/]profiles[\\/]\*[\\/]node_modules[\\/]dsh-jev-preset/,
    `主定位行必须用 profile junction 的 glob,当前: ${resolveRaw}`)
})

test('A1 辅证: 断言库经 profile junction 也可解析(换路不掉链)', () => {
  const junction = path.join(process.env.USERPROFILE ?? '', '.dsh', 'profiles', 'web',
    'node_modules', 'dsh-jev-preset', 'packages', 'assertions', 'python', 'jev_assertions', 'cli.py')
  let resolved
  try {
    resolved = execFileSync('pwsh', ['-NoProfile', '-Command',
      `(Resolve-Path ${JSON.stringify(junction)} -ErrorAction SilentlyContinue | Select-Object -First 1).Path`],
      { encoding: 'utf8' }).trim()
  } catch {
    resolved = ''
  }
  // 环境相关:没装 profile junction 时跳过,不做硬失败(非缺陷本身)。
  if (!resolved) {
    assert.ok(true, 'profile junction 不存在,跳过')
    return
  }
  const out = JSON.parse(execFileSync('python', [resolved, '--func', 'tick_floor',
    '--args', '{"raw_price":100.12,"tick_size":0.01,"expected":100.12}'],
    { encoding: 'utf8', env: { ...process.env, PYTHONIOENCODING: 'utf-8' } }))
  assert.equal(out.status, 'pass')
})
