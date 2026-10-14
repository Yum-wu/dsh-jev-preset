// runtime-path.mjs
//
// 运行时路径的**唯一真相** = `~/.dsh/start-dsh.ps1` 的 `$dshEntry`(仓库硬规则)。
//
// 为什么不能写死版本号:这些脚本按包名 import 运行时的产物(如 dsh-subagent)。
// 写死 `dsh-0.1.7-rc.2` 之后,一旦切到 0.2.0,脚本会**继续在旧运行时上跑**,
// 既不报错也不提示 —— 验证结论全部作废(与 2026-09-27 的
// "删运行时目录前先扫引用" 同源:指针留在旧目录,测试静默测错对象)。
//
// 允许用 `DSH_RUNTIME_NODE_MODULES` 覆盖,便于在隔离目录里跑。
//
// 返回值一律用正斜杠:调用方普遍拼进 `file:///${RUNTIME}/...`,
// Windows 的反斜杠会让 file URL 解析失败。

import { existsSync, readFileSync } from 'node:fs'
import { homedir } from 'node:os'
import path from 'node:path'

const START_PS1 = path.join(homedir(), '.dsh', 'start-dsh.ps1')

/**
 * BOM 感知读取。
 *
 * ⚠ `~/.dsh/start-dsh.ps1` 实测是 **UTF-16LE(`FF FE` BOM)**。按 utf8 读会得到满屏
 *   U+FFFD,下面的正则一条都匹配不上,本模块直接抛 `cannot parse $dshEntry` ——
 *   而这条报错看起来像「脚本格式变了」,实际是读法错了,排障方向被带偏。
 *
 *   同一个坑在本仓/本机已踩三次:codemode 的 bundle-declaration 测试、
 *   prompt-editor 的 schemastery junction 守卫、以及这里。
 *   凡是读 `~/.dsh/*.ps1` 的地方都必须走这个函数。
 */
function readTextAuto(file) {
  const buf = readFileSync(file)
  if (buf.length >= 2 && buf[0] === 0xff && buf[1] === 0xfe) return buf.toString('utf16le')
  if (buf.length >= 2 && buf[0] === 0xfe && buf[1] === 0xff) {
    const swapped = Buffer.from(buf.subarray(2))
    swapped.swap16()
    return swapped.toString('utf16le')
  }
  return buf.toString('utf8').replace(/^\uFEFF/, '')
}

/** 从 start-dsh.ps1 解析 $dshEntry,返回其绝对路径(原生分隔符)。 */
function dshEntryFromScript() {
  const script = readTextAuto(START_PS1)
  const matched = script.match(/\$dshEntry\s*=\s*Join-Path\s+\$env:USERPROFILE\s+'([^']+)'/i)
  if (!matched) throw new Error(`cannot parse $dshEntry from ${START_PS1}`)
  return path.join(homedir(), matched[1].replace(/\\/g, path.sep))
}

/** 当前活跃运行时的 `node_modules` 目录(正斜杠)。 */
export function runtimeNodeModules() {
  const override = process.env.DSH_RUNTIME_NODE_MODULES
  if (override) return override.replace(/\\/g, '/')
  let dir = path.dirname(dshEntryFromScript())
  for (;;) {
    if (path.basename(dir).toLowerCase() === 'node_modules') break
    const up = path.dirname(dir)
    if (up === dir) throw new Error(`no node_modules above $dshEntry (${dshEntryFromScript()})`)
    dir = up
  }
  return dir.replace(/\\/g, '/')
}

/** 当前活跃运行时的 `@deepseek-ai` 基目录(正斜杠)。 */
export function runtimeAiBase() {
  return `${runtimeNodeModules()}/@deepseek-ai`
}

/** 解析后的运行时目录是否存在;不存在时给出可执行的修复提示而不是玄学 ENOENT。 */
export function assertRuntimeExists() {
  const base = runtimeNodeModules()
  if (!existsSync(base)) {
    throw new Error(
      `runtime node_modules not found: ${base}\n` +
      `该路径由 ~/.dsh/start-dsh.ps1 的 $dshEntry 派生;若刚切换过运行时,` +
      `确认新目录已 npm install 完成,或设置 DSH_RUNTIME_NODE_MODULES 覆盖。`,
    )
  }
  return base
}
