import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { readFile } from 'node:fs/promises'
import { pathToFileURL } from 'node:url'
import ts from 'typescript'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

const require = createRequire(import.meta.url)
const source = await readFile(new URL('../src/components/TradeAnalyzerView.tsx', import.meta.url), 'utf8')
let compiled = ts.transpileModule(source, { compilerOptions: {
  jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2023,
}}).outputText
compiled = compiled.replaceAll('react/jsx-runtime', pathToFileURL(require.resolve('react/jsx-runtime')).href)
  .replaceAll("from 'react'", `from '${pathToFileURL(require.resolve('react')).href}'`)
  .replaceAll('../lib/api', new URL('../src/lib/api.ts', import.meta.url).href)
const { TradeAnalysisResults, TradeAnalyzerView } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)

test('trade form offers two sending teams, an effective week, and a configurable final week', () => {
  const markup = renderToStaticMarkup(createElement(TradeAnalyzerView, {
    league: { league_id: 1, season: 2026, teams: [{ team_id: 1, team_name: 'Team A' }, { team_id: 2, team_name: 'Team B' }] },
    selectedTeamId: 1, week: 13, connectionMode: 'public', onTeamChange() {}, onWeekChange() {},
  }))
  for (const text of ['Trade analyzer', 'Team A sends', 'Team B sends', 'Effective week', 'Last week to include', 'Analyze trade']) {
    assert.ok(markup.includes(text), text)
  }
  assert.match(markup, /Roster space and drops are left to managers/)
})

test('results distinguish player totals from starter impact and show missing values as unavailable', () => {
  const player = { espn_id: 50, player_name: 'Incoming Receiver', predicted_points: 14 }
  const team = (id) => ({ team_id: id, team_name: `Team ${id}`, weekly_before: 100, weekly_after: 105, weekly_change: 5,
    rest_before: null, rest_after: null, rest_change: null, weeks_covered: 1,
    power_rank_before: null, power_rank_after: null,
    lineup_before: [{ slot: 'WR', player: { ...player, player_name: 'Previous Receiver' } }],
    lineup_after: [{ slot: 'WR', player, locked: false }],
    positions: [{ slot: 'WR', before_points: null, after_points: null, league_average: null, backups_before: 2, backups_after: 1 }],
    weeks: [{ week: 13, before_points: 100, after_points: 105, change: 5 }, { week: 14, before_points: null, after_points: null, change: null }],
    explanations: ['WR depth drops from two backups to one.'],
  })
  const data = { season: 2026, week: 13, end_week: 14, generated_at: '2026-11-24T17:00:00Z',
    verdict: 'Not enough projection coverage for a verdict', summary: 'Missing values are not treated as zero.',
    teams: [team(1), team(2)], players: [{ ...player, from_team_id: 2, position: 'WR', weekly_points: 14,
      rest_of_season_points: null, projected_games: 1, missing_weeks: 1 }],
    power_rankings: [{ team_id: 1, team_name: 'Team 1', before_points: null, after_points: null, rank_before: null, rank_after: null }],
    notes: ['Hypothetical only.'],
  }
  const markup = renderToStaticMarkup(createElement(TradeAnalysisResults, { data }))
  for (const text of ['Not enough projection coverage', 'Unavailable', '(Incoming)', 'Team needs and depth',
    'Players in the trade', 'Week-by-week lineup impact', 'Projected league power rankings', '1 missing week(s)',
    'Player totals include bench value', 'Previous Receiver']) assert.ok(markup.includes(text), text)
  assert.ok(!markup.includes('>0.0<'))
})
