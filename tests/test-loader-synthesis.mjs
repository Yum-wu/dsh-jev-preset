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

test('Loader 合成与 Schemastery 配置契约', () => {
  const patchText = readFileSync('cordis.patch.yml', 'utf8')
  const patch = yaml.load(patchText, { schema: entryListSchema })
  const cfg = patch[0].insert[0].config

  const allowed = new Set(['id', 'name', 'description', 'order', 'plugins'])
  for (const k of Object.keys(cfg)) {
    assert.ok(allowed.has(k), `未知配置键: ${k}`)
  }

  assert.equal(cfg.id, 'jev')
  assert.equal(cfg.order, 5)
  assert.ok(typeof cfg.name === 'string' && cfg.name.length > 0)
  assert.ok(typeof cfg.description === 'string' && cfg.description.length > 0)
  assert.ok(Array.isArray(cfg.plugins))

  // 递归收集全部行 id，断言唯一性
  const ids = []
  const collect = (rs) => {
    for (const r of rs) {
      if (r.id) ids.push(r.id)
      if (r.group === true && Array.isArray(r.config)) collect(r.config)
    }
  }
  collect(cfg.plugins)
  const duplicates = ids.filter((v, i) => ids.indexOf(v) !== i)
  assert.equal(duplicates.length, 0, `行 ID 必须全局唯一，发现重复: ${duplicates.join(', ')}`)
})
