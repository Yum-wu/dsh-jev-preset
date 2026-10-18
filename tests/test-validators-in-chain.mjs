// 把两份静态校验器挂进测试链。
//
// 根因(2026-10-19 同模式二次发生):`validate.mjs` 与 `validate-official.mjs`
// **不在** `package.json` 的 `scripts.test` 长链里 —— 前者只有 `npm run validate`,
// 后者连 script 都没有。于是改名事故可以把校验器红着提交、推上去、没人发现。
//
// 修法刻意**不动 `scripts.test`**:那条链的 python 套件数被 `tests/pre_registered.py`
// 的棘轮与 `tools/g_check.py` 的 `g1()` 形状门盯着(期望值 vs 计数同源共变异的坑,
// 该文件 docstring 里红队 R80/R81/R82 打过穿三次)。加一条 `&&` 段会牵动形状判据。
// 改成**测试文件**,落在已有的 `node --test tests/test-*.mjs` 段里 ⇒ 零形状变更。
//
// 判别性(实测,不是声称):
//   - 临时副本里把子 preset 的 `config.id: jev-executor` 改成 `yum-executor`
//     ⇒ validate.mjs 报「持久化 preset 外键 jev-executor 注册了 0 次」并以 1 退出
//     ⇒ 本文件 T1 随之转红。
//   - 只改声明行、不改父 preset 的 `agentPreset:` 指认 ⇒ tests/
//     test-subagent-preset-migration.mjs 的 loadPatch() 抛「只改一边会让子代理静默起不来」。

import test from 'node:test'
import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const BUNDLE = fileURLToPath(new URL('..', import.meta.url))

function runValidator(script) {
  const r = spawnSync(process.execPath, [script], { cwd: BUNDLE, encoding: 'utf8' })
  const out = `${r.stdout ?? ''}${r.stderr ?? ''}`
  return { code: r.status, out }
}

// 两个校验器:失败明细在末尾「静态校验失败:N 项」/「官方代码路径验证失败」段里,
// 断言消息必须把它带上,否则红了也只知道红了。
const FAIL_MARK = /静态校验失败|官方代码路径验证失败|验证不通过/

for (const script of ['validate.mjs', 'validate-official.mjs']) {
  test(`V: ${script} 必须以 0 退出(校验器红了不许继续打绿)`, () => {
    const { code, out } = runValidator(script)
    assert.match(out, /OK/, `${script} 没有任何 OK 输出 —— 它多半根本没跑到断言`)
    assert.equal(code, 0,
      `${script} 退出码 ${code}(校验失败明细如下)\n${out.split('\n').filter((l) => /^ {2}- |^={5,}|失败/.test(l)).join('\n')}\n`)
    assert.doesNotMatch(out, FAIL_MARK, `${script} 打印了失败汇总但退出码为 0 —— 这是恒绿判据,需修校验器本身`)
  })
}
