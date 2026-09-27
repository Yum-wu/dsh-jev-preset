#!/usr/bin/env node
/**
 * monitor-long-goal.mjs
 * 
 * 巡检长程 JEV 优化目标会话状态:
 * 读取当前会话的轮次、步骤、运行时间与最新输出。
 */

import { readFileSync, existsSync } from 'node:fs'
import { homedir } from 'node:os'
import { join } from 'node:path'

const HOME = join(homedir(), '.dsh')
const URL_FILE = join(HOME, 'web-url.txt')
const STATE_FILE = join(HOME, 'jev-session-test', 'active-long-goal.json')

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

async function main() {
  if (!existsSync(STATE_FILE)) {
    console.log('未找到活跃的长程任务记录。')
    return
  }
  const meta = JSON.parse(readFileSync(STATE_FILE, 'utf8'))
  const { origin, token } = readBase()
  const cookie = await authenticate(origin, token)

  const sessionId = meta.sessionId
  const startTime = new Date(meta.startedAt).getTime()
  const elapsedMinutes = ((Date.now() - startTime) / 60000).toFixed(1)

  console.log(`\n=== JEV 长程会话巡检 [${new Date().toLocaleTimeString()}] ===`)
  console.log(`会话 ID: ${sessionId}`)
  console.log(`运行预设: ${meta.preset}`)
  console.log(`开始时间: ${meta.startedAt} (已运行 ${elapsedMinutes} 分钟，设定下限: ${meta.minDurationHours} 小时)`)

  const proj = await rpc(origin, cookie, 'session/projections', { request: { sessionId } })
  const stats = proj?.values?.sessionStats
  const running = proj?.values?.inbox ? true : false
  console.log(`会话状态: asOfSeq=${proj?.asOfSeq}, turns=${stats?.turns ?? 0}, steps=${stats?.steps ?? 0}, decodeTokens=${stats?.decodeTokens ?? 0}`)

  const page = await rpc(origin, cookie, 'session/page', {
    request: { address: { kind: 'session', sessionId }, throughSeq: proj?.asOfSeq ?? 0 }
  })
  const records = page?.records ?? []
  const textEvents = records
    .map(r => r?.event ?? r)
    .filter(e => e?.type === 'assistant/message')
    .flatMap(e => e?.data?.message?.content ?? [])
    .filter(b => b?.type === 'text')
    .map(b => b.text)

  if (textEvents.length > 0) {
    const latestText = textEvents[textEvents.length - 1]
    console.log(`\n--- 最新输出摘要 (第 ${textEvents.length} 条助手消息) ---`)
    console.log(latestText.slice(0, 800) + (latestText.length > 800 ? '\n...(略)...' : ''))
  } else {
    console.log('当前首轮正在思考与工具执行中，暂未沉淀最终助手消息。')
  }
}

main().catch(err => console.error('巡检出错:', err.message))
