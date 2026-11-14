import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { readFile } from 'node:fs/promises'
import { pathToFileURL } from 'node:url'
import ts from 'typescript'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { scoreDisplay, teamScoreDisplay } from '../src/lib/scoreDisplay.ts'

const player = { predicted_points: 20, pregame_predicted_points: 18, prediction_saved: true,
  floor_points: 8, ceiling_points: 29, kickoff_at: '2026-11-08T18:00:00Z' }
const live = { espn_id: 501, game_state: 'live', live_points: 4.2, prediction_saved: true,
  pregame_predicted_points: 18, kickoff_at: player.kickoff_at, game_detail: 'Q2 3:20' }

test('pregame range surrounds the saved projection; live points replace it after kickoff', () => {
  const pregame = scoreDisplay(player, undefined, Date.parse('2026-11-08T17:00:00Z'))
  assert.equal(pregame.started, false)
  assert.equal(pregame.prediction, 18)
  assert.equal(pregame.floor, 8)
  assert.equal(pregame.ceiling, 29)
  const current = scoreDisplay({ ...player, predicted_points: 999 }, live)
  assert.equal(current.actual, 4.2)
  assert.equal(current.prediction, 18)
  assert.equal(current.floor, null)
})

test('missing scores and unsaved pregame forecasts stay unavailable, including a late first visit', () => {
  const current = scoreDisplay({ predicted_points: 99 }, { ...live, live_points: null,
    prediction_saved: false, pregame_predicted_points: null })
  assert.equal(current.actual, null)
  assert.equal(current.prediction, null)
  const unknown = scoreDisplay({ predicted_points: 99, kickoff_at: player.kickoff_at }, undefined,
    Date.parse('2026-11-08T19:00:00Z'))
  assert.equal(unknown.started, true)
  assert.equal(unknown.prediction, null)
})

test('zero and negative real scores remain valid and final state stays final', () => {
  assert.equal(scoreDisplay(player, { ...live, live_points: 0 }).actual, 0)
  assert.equal(scoreDisplay(player, { ...live, game_state: 'final', live_points: -3 }).actual, -3)
})

test('team totals exclude bench and do not turn missing starter scores into zero', () => {
  const roster = [{ ...player, espn_id: 501, lineup_slot: 'QB' },
    { ...player, espn_id: 502, lineup_slot: 'BE' }]
  const current = teamScoreDisplay(roster, new Map([[501, live], [502, { ...live, live_points: 100 }]]))
  assert.equal(current.actual, 4.2)
  assert.equal(current.prediction, 18)
  assert.equal(teamScoreDisplay(roster, new Map([[501, { ...live, live_points: null }]])).actual, null)
  assert.equal(teamScoreDisplay([], new Map()).prediction, null)
})

test('rendered layout has Ceiling above the prediction and Floor below; final score above pregame', async () => {
  const source = await readFile(new URL('../src/components/PlayerScore.tsx', import.meta.url), 'utf8')
  const require = createRequire(import.meta.url)
  let compiled = ts.transpileModule(source, { compilerOptions: {
    jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2023,
  }}).outputText
  compiled = compiled.replaceAll('react/jsx-runtime', pathToFileURL(require.resolve('react/jsx-runtime')).href)
    .replaceAll('../lib/scoreDisplay', new URL('../src/lib/scoreDisplay.ts', import.meta.url).href)
  const { PlayerScore } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)
  const future = { ...player, kickoff_at: '2099-11-08T18:00:00Z' }
  const pre = renderToStaticMarkup(createElement(PlayerScore, { player: future }))
  assert.ok(pre.indexOf('Ceiling') < pre.indexOf('18.0'))
  assert.ok(pre.indexOf('18.0') < pre.indexOf('Floor'))
  const final = renderToStaticMarkup(createElement(PlayerScore, { player, live: { ...live, game_state: 'final' } }))
  assert.ok(final.includes('Final'))
  assert.ok(final.indexOf('4.2') < final.indexOf('AI pregame'))
  assert.ok(!final.includes('Ceiling'))
})
