import test from 'node:test'
import assert from 'node:assert/strict'

class JevCircuitBreaker {
  constructor(failureThreshold = 3, cooldownMs = 100) {
    this.failureCount = 0
    this.failureThreshold = failureThreshold
    this.cooldownMs = cooldownMs
    this.state = 'CLOSED'
    this.lastFailureTime = 0
  }

  async execute(thunk) {
    const now = Date.now()
    if (this.state === 'OPEN') {
      if (now - this.lastFailureTime > this.cooldownMs) {
        this.state = 'HALF_OPEN'
      } else {
        throw new Error('CIRCUIT_OPEN')
      }
    }

    try {
      const res = await thunk()
      if (this.state === 'HALF_OPEN') {
        this.state = 'CLOSED'
        this.failureCount = 0
      }
      return res
    } catch (err) {
      this.failureCount++
      this.lastFailureTime = Date.now()
      if (this.failureCount >= this.failureThreshold) {
        this.state = 'OPEN'
      }
      throw err
    }
  }
}

test('断路器状态机流转与熔断阻断', async () => {
  const cb = new JevCircuitBreaker(3, 50)
  assert.equal(cb.state, 'CLOSED')

  const failingThunk = async () => { throw new Error('FAIL') }
  const successThunk = async () => 'OK'

  // 1. 触发 3 次失败达到阈值
  await assert.rejects(cb.execute(failingThunk))
  await assert.rejects(cb.execute(failingThunk))
  await assert.rejects(cb.execute(failingThunk))
  assert.equal(cb.state, 'OPEN')

  // 2. 处于 OPEN 时直接被拒
  await assert.rejects(cb.execute(successThunk), /CIRCUIT_OPEN/)

  // 3. 冷却后进入 HALF_OPEN 并自愈
  await new Promise(r => setTimeout(r, 60))
  const res = await cb.execute(successThunk)
  assert.equal(res, 'OK')
  assert.equal(cb.state, 'CLOSED')
})
