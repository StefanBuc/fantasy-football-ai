import { test } from 'node:test'
import assert from 'node:assert/strict'
import { getTeamProjections, getAccuracy, syncAccuracy, getAutomationStatus, getRetrainingStatus, getLiveScores, getOptimizedLineup, getTradeRosters, analyzeTrade } from '../src/lib/api.ts'

const input = { league_id: 1, season: 2026, team_id: 1, week: 8 }

test('retraining status is a read-only request without starting a training job', async (t) => {
  const fetch = t.mock.method(globalThis, 'fetch', () => Promise.resolve(new Response('{"state":"waiting"}')))
  assert.deepEqual(await getRetrainingStatus(), { state: 'waiting' })
  const [path, options] = fetch.mock.calls[0].arguments
  assert.equal(path, '/api/training/status')
  assert.equal(options.method, 'GET')
  assert.equal(options.body, undefined)
})

test('trade roster selection is separate from analysis and local requests omit connection fields', async (t) => {
  const fetch = t.mock.method(globalThis, 'fetch', () => Promise.resolve(new Response('{}')))
  const connection = { league_id: 1, season: 2026 }
  await getTradeRosters(connection, 'public')
  assert.equal(fetch.mock.calls[0].arguments[0], '/api/espn/trade-rosters')
  assert.deepEqual(JSON.parse(fetch.mock.calls[0].arguments[1].body), connection)
  await getTradeRosters(connection, 'local')
  assert.equal(fetch.mock.calls[1].arguments[0], '/api/espn/local/trade-rosters')
  assert.deepEqual(JSON.parse(fetch.mock.calls[1].arguments[1].body), {})
  const trade = { team_a_id: 1, team_b_id: 2, team_a_player_ids: [-16002, 50], team_b_player_ids: [51], week: 13, end_week: 17 }
  await analyzeTrade({ ...connection, ...trade }, 'public')
  assert.equal(fetch.mock.calls[2].arguments[0], '/api/espn/trade-analysis')
  assert.deepEqual(JSON.parse(fetch.mock.calls[2].arguments[1].body), { ...connection, ...trade })
  await analyzeTrade({ ...connection, ...trade }, 'local')
  assert.equal(fetch.mock.calls[3].arguments[0], '/api/espn/local/trade-analysis')
  assert.deepEqual(JSON.parse(fetch.mock.calls[3].arguments[1].body), trade)
})

test('optimizer sends the free-agent choice and keeps private requests local', async (t) => {
  const fetch = t.mock.method(globalThis, 'fetch', () => Promise.resolve(new Response('{}')))
  await getOptimizedLineup({ ...input, include_free_agents: false }, 'public')
  assert.equal(fetch.mock.calls[0].arguments[0], '/api/espn/optimized-lineup')
  assert.deepEqual(JSON.parse(fetch.mock.calls[0].arguments[1].body), { ...input, include_free_agents: false })
  await getOptimizedLineup({ ...input, include_free_agents: true }, 'local')
  assert.equal(fetch.mock.calls[1].arguments[0], '/api/espn/local/optimized-lineup')
  assert.deepEqual(JSON.parse(fetch.mock.calls[1].arguments[1].body), {
    team_id: 1, week: 8, include_free_agents: true, refresh: false,
  })
})

test('identical pending requests share one HTTP call', async (t) => {
  const deferred = Promise.withResolvers()
  const fetch = t.mock.method(globalThis, 'fetch', () => deferred.promise)
  const first = getTeamProjections(input)
  const second = getTeamProjections(input)
  assert.equal(first, second)
  assert.equal(fetch.mock.callCount(), 1)
  deferred.resolve(new Response(JSON.stringify({ points: 20 })))
  assert.deepEqual(await first, { points: 20 })
  assert.deepEqual(await second, { points: 20 })
  // Once completed, a subsequent request checks the server again.
  fetch.mock.mockImplementation(() => Promise.resolve(new Response('{}')))
  await getTeamProjections(input)
  assert.equal(fetch.mock.callCount(), 2)
})

test('failed requests can be retried', async (t) => {
  const fetch = t.mock.method(globalThis, 'fetch', () => Promise.reject(new Error('offline')))
  await assert.rejects(getTeamProjections(input), /Could not reach/)
  fetch.mock.mockImplementation(() => Promise.resolve(new Response('{}')))
  await getTeamProjections(input)
  assert.equal(fetch.mock.callCount(), 2)
})

test('accuracy reads use GET with filters and sync uses POST for the selected league', async (t) => {
  const fetch = t.mock.method(globalThis, 'fetch', () => Promise.resolve(new Response('{}')))
  await getAccuracy({ season: 2026, league_id: 123, week: 10, position: 'QB', roster_category: 'starter', offset: 100 })
  const [path, options] = fetch.mock.calls[0].arguments
  assert.equal(path, '/api/accuracy/2026?league_id=123&week=10&position=QB&roster_category=starter&offset=100')
  assert.equal(options.method, 'GET')
  assert.equal(options.body, undefined)
  await syncAccuracy(2026, 123)
  assert.equal(fetch.mock.calls[1].arguments[0], '/api/accuracy/2026/sync?league_id=123')
  assert.equal(fetch.mock.calls[1].arguments[1].method, 'POST')
})

test('accuracy displays backend sync errors so saved data is not mistaken for empty history', async (t) => {
  t.mock.method(globalThis, 'fetch', () => Promise.resolve(new Response(
    JSON.stringify({ detail: 'Results could not be synced. Saved predictions are preserved; try again later.' }),
    { status: 503 },
  )))
  await assert.rejects(syncAccuracy(2026), /Saved predictions are preserved/)
})

test('automation status reads only the selected history scope', async (t) => {
  const fetch = t.mock.method(globalThis, 'fetch', () => Promise.resolve(new Response('{"enabled":true}')))
  assert.deepEqual(await getAutomationStatus(2026, 123), { enabled: true })
  assert.equal(fetch.mock.calls[0].arguments[0], '/api/accuracy/2026/automation?league_id=123')
  assert.equal(fetch.mock.calls[0].arguments[1].method, 'GET')
  assert.equal(fetch.mock.calls[0].arguments[1].body, undefined)
  await getAutomationStatus(2026)
  assert.equal(fetch.mock.calls[1].arguments[0], '/api/accuracy/2026/automation')
})

test('live scores use their lightweight endpoint and local requests omit public connection fields', async (t) => {
  const fetch = t.mock.method(globalThis, 'fetch', () => Promise.resolve(new Response('{}')))
  const players = [{ espn_id: -16002, player_id: 'BUF', position: 'D/ST', team: 'BUF' }]
  await getLiveScores({ league_id: 123, season: 2026, week: 10, players }, 'public')
  assert.equal(fetch.mock.calls[0].arguments[0], '/api/espn/live')
  await getLiveScores({ league_id: 123, season: 2026, week: 10, players }, 'local')
  assert.equal(fetch.mock.calls[1].arguments[0], '/api/espn/local/live')
  assert.deepEqual(JSON.parse(fetch.mock.calls[1].arguments[1].body), { week: 10, players })
})
