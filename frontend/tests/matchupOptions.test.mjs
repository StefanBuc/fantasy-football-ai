import { test } from 'node:test'
import assert from 'node:assert/strict'
import { matchupOptions } from '../src/lib/matchupOptions.ts'

const teams = [
  { team_id: 1, team_name: 'Team A', opponents_by_week: { 1: 2, 2: 3 } },
  { team_id: 2, team_name: 'Team B', opponents_by_week: { 1: 1, 2: 4 } },
  { team_id: 3, team_name: 'Team C', opponents_by_week: { 1: 4, 2: 1 } },
  { team_id: 4, team_name: 'Team D', opponents_by_week: { 1: 3, 2: 2 } },
]

test('lists both names once per matchup, with the right opponents for each week', () => {
  assert.deepEqual(
    matchupOptions(teams, 1).map((option) => option.label),
    ['Team A vs Team B', 'Team C vs Team D'],
  )
  assert.deepEqual(
    matchupOptions(teams, 2).map((option) => option.label),
    ['Team A vs Team C', 'Team B vs Team D'],
  )
})

test('the latest scoreboard replaces an older connection schedule', () => {
  assert.deepEqual(
    matchupOptions(teams, 1, { 1: 3, 3: 1, 2: 4, 4: 2 })
      .map((option) => option.label),
    ['Team A vs Team C', 'Team B vs Team D'],
  )
})

test('byes and unpublished opponents are labelled without inventing a pairing', () => {
  const options = matchupOptions([
    { team_id: 1, team_name: 'Team A', opponents_by_week: { 1: null } },
    { team_id: 2, team_name: 'Team B' },
  ], 1)

  assert.equal(options[0].label, 'Team A vs BYE')
  assert.equal(options[0].disabled, true)
  assert.equal(options[1].label, 'Team B vs TBD')
})
