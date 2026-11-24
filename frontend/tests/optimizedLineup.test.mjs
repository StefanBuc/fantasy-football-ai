import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { readFile } from 'node:fs/promises'
import { pathToFileURL } from 'node:url'
import ts from 'typescript'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

const require = createRequire(import.meta.url)
const source = await readFile(new URL('../src/components/OptimizedLineupView.tsx', import.meta.url), 'utf8')
let compiled = ts.transpileModule(source, { compilerOptions: {
  jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2023,
}}).outputText
compiled = compiled.replaceAll('react/jsx-runtime', pathToFileURL(require.resolve('react/jsx-runtime')).href)
  .replaceAll("from 'react'", `from '${pathToFileURL(require.resolve('react')).href}'`)
  .replaceAll('../lib/api', new URL('../src/lib/api.ts', import.meta.url).href)
const { OptimizedPlayerName, OptimizedLineupView } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)

test('outside players are visibly marked as Free agent, while owned players are not', () => {
  const render = (is_free_agent) => renderToStaticMarkup(createElement(OptimizedPlayerName, {
    player: { player_name: 'Recommended Player', is_free_agent },
  }))
  assert.match(render(true), /Recommended Player.*\(Free agent\)/)
  assert.ok(!render(false).includes('(Free agent)'))
})

test('optimizer initially offers a roster-only lineup and a free-agent checkbox', () => {
  const markup = renderToStaticMarkup(createElement(OptimizedLineupView, {
    league: { league_id: 1, season: 2026, teams: [{ team_id: 1, team_name: 'My team' }] },
    connectionMode: 'public', selectedTeamId: 1, week: 13,
    onTeamChange() {}, onWeekChange() {},
  }))
  assert.match(markup, /Optimized lineup/)
  assert.match(markup, /Include free agents/)
  assert.match(markup, /Only use players already on this team/)
  assert.ok(!markup.includes('checked=""'))
})
