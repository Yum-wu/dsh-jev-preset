import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { pathToFileURL } from 'node:url'

const RUNTIME = 'C:/Users/Yum/.dsh/runtime/dsh-0.1.7-rc.2/node_modules'
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
  
  const decl = patch[0].insert[0]
  assert.equal(decl.name, '@deepseek-ai/dsh-agent-preset')
  assert.equal(decl.id, 'preset-jev')
})
