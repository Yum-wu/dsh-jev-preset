import test from 'node:test'
import assert from 'node:assert/strict'

const RUNTIME = 'C:/Users/Yum/.dsh/runtime/dsh-0.1.7-rc.2/node_modules/@deepseek-ai'

test('DSH 子代理递归阻断与深度限制 (maxDepth=1)', async () => {
  const { resolveChildDepth, SubagentDepthError } = await import(
    `file:///${RUNTIME}/dsh-subagent/lib/index.js`
  )

  // 1. 顶层 (depth 0) 派生子代理 (允许)
  const topParent = { options: {}, session: { header: { delegationDepth: 0 } } }
  const childDepth = resolveChildDepth(topParent, 1)
  assert.equal(childDepth, 1, '顶层派生 depth 必须等于 1')

  // 2. 子代理 (depth 1) 再次尝试派生 (阻断抛出 SubagentDepthError)
  const childParent = { options: {}, session: { header: { delegationDepth: 1 } } }
  assert.throws(
    () => resolveChildDepth(childParent, 1),
    (err) => {
      return err instanceof SubagentDepthError && err.message.includes('subagent depth 2 exceeds maxDepth 1')
    },
    'depth=1 尝试派生 depth=2 必须抛出 SubagentDepthError'
  )
})
