import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'

import { runtimeNodeModules } from '../runtime-path.mjs'

const RUNTIME = runtimeNodeModules()
const req = createRequire(pathToFileURL(`${RUNTIME}/@deepseek-ai/cordis-plugin-include/lib/index.js`))
const yaml = req('js-yaml')

const JsExpr = new yaml.Type('tag:yaml.org,2002:js', {
  kind: 'scalar',
  resolve: (data) => typeof data === 'string',
  construct: (data) => ({ __jsExpr: data }),
  predicate: (v) => v instanceof Object && '__jsExpr' in v,
  represent: (data) => data['__jsExpr'],
})
const entryListSchema = yaml.JSON_SCHEMA.extend(JsExpr)

test('YAML Schema 语法有效性与顶层结构', () => {
  const patchText = readFileSync('cordis.patch.yml', 'utf8')
  const patch = yaml.load(patchText, { schema: entryListSchema })
  
  assert.ok(Array.isArray(patch), '顶层必须是数组')
  assert.equal(patch.length, 1, '期望恰好 1 个 patch 条目')
  assert.ok(patch[0].insert, '必须包含 insert 操作')
  
  // 按 config.id 定位(会话持久化外键),不按下标、也不按 Loader 行 id ——
  //   行 id 是可改命名空间(2026-10-19 曾改成 preset-yum,同日回退),下标会随插行漂移。
  const decl = patch[0].insert.find((r) => r?.config?.id === 'jev')
  assert.ok(decl, '找不到 config.id=jev 的 preset 声明行 —— config.id 是会话外键,不可改名')
  assert.equal(decl.name, '@deepseek-ai/dsh-agent-preset')
  assert.match(String(decl.id), /^preset-[a-z0-9-]+$/, `Loader 行 id 形状不对: ${decl.id}`)
})
