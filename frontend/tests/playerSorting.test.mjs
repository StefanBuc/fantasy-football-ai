import { test } from 'node:test'
import assert from 'node:assert/strict'
import { sortPlayers } from '../src/lib/playerSorting.ts'

const player = (espn_id, player_name, predicted_points = 10, season_average = 5) =>
  ({ espn_id, player_name, predicted_points, season_average })
const live = (espn_id, live_points, game_state = 'live') =>
  [espn_id, { espn_id, live_points, game_state }]

test('current scores descend, including zero and negative points, with unplayed/missing last', () => {
  const players = [player(1, 'Missing'), player(2, 'Negative'), player(3, 'Zero'),
    player(4, 'Leader'), player(5, 'Pregame')]
  const scores = new Map([live(2, -2), live(3, 0), live(4, 25, 'final'), live(5, 0, 'pregame')])
  assert.deepEqual(sortPlayers(players, 'current_score', scores).map(p => p.espn_id), [4, 3, 2, 1, 5])
  assert.equal(players[0].espn_id, 1)
})

test('score changes reorder players and ties use names', () => {
  const players = [player(1, 'Zed'), player(2, 'Amy')]
  const scores = new Map([live(1, 10), live(2, 10)])
  assert.equal(sortPlayers(players, 'current_score', scores)[0].espn_id, 2)
  scores.set(...live(1, 11))
  assert.equal(sortPlayers(players, 'current_score', scores)[0].espn_id, 1)
})

test('projection and season average sorting remain independent of live scores', () => {
  const players = [player(1, 'A', null, 20), player(2, 'B', 30, null)]
  assert.equal(sortPlayers(players, 'projection', new Map())[0].espn_id, 2)
  assert.equal(sortPlayers(players, 'season_average', new Map())[0].espn_id, 1)
})
