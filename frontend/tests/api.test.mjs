import { test } from 'node:test'
import assert from 'node:assert/strict'
import { getTeamProjections } from '../src/lib/api.ts'

const input = { league_id: 1, season: 2026, team_id: 1, week: 8 }

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
