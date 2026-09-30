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

test('Isolate 私有隔离域审计', () => {
  const patchText = readFileSync('cordis.patch.yml', 'utf8')
  const patch = yaml.load(patchText, { schema: entryListSchema })
  const plugins = patch[0].insert[0].config.plugins

  const compactionGroup = plugins.find(p => p.id === 'compaction')
  assert.ok(compactionGroup, '必须存在 compaction group')
  assert.equal(compactionGroup.group, true)
  assert.deepEqual(compactionGroup.isolate, { compaction: true, toolResultPruner: true })

  const delegationGroup = plugins.find(p => p.id === 'delegation')
  assert.ok(delegationGroup, '必须存在 delegation group')
  assert.equal(delegationGroup.group, true)
  assert.deepEqual(delegationGroup.isolate, { workflowEngine: true })
})
