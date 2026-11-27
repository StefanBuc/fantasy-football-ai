import { test } from 'node:test'
import assert from 'node:assert/strict'
import { configureSession, setActiveConnection, sendJson, getLocalTeamProjections, getTeamLogoUrl } from '../src/lib/api.ts'
import { getSession } from '../src/lib/account.ts'

test('concurrent session initialization shares one server-issued CSRF/cookie pair', async (t) => {
  const reply = Promise.withResolvers()
  const fetch = t.mock.method(globalThis, 'fetch', () => reply.promise)
  const first = getSession()
  const second = getSession()
  assert.equal(first, second)
  assert.equal(fetch.mock.callCount(), 1)
  reply.resolve(new Response('{"authenticated":false,"csrf_token":"one"}'))
  assert.equal((await first).csrf_token, 'one')
  assert.equal((await second).csrf_token, 'one')
})

test('authenticated writes attach a CSRF token and saved-connection context without exposing ESPN credentials', async (t) => {
  const fetch = t.mock.method(globalThis, 'fetch', () => Promise.resolve(new Response('{}')))
  configureSession('csrf-from-server', true)
  setActiveConnection('saved-connection-id')
  t.after(() => { configureSession('', false); setActiveConnection(null) })
  await getLocalTeamProjections({ team_id: 1, week: 13 })
  const [path, options] = fetch.mock.calls[0].arguments
  assert.equal(path, '/api/espn/local/projections')
  assert.equal(options.credentials, 'include')
  assert.equal(options.cache, 'no-store')
  assert.equal(options.headers['X-CSRF-Token'], 'csrf-from-server')
  assert.equal(options.headers['X-League-Connection'], 'saved-connection-id')
  assert.deepEqual(JSON.parse(options.body), { team_id: 1, week: 13 })
  await sendJson('/api/account/connections', undefined, 'GET')
  assert.equal(fetch.mock.calls[1].arguments[1].headers['X-CSRF-Token'], undefined)
  assert.equal(fetch.mock.calls[1].arguments[1].headers['X-League-Connection'], undefined)
  assert.match(getTeamLogoUrl(1, 'https://mystique-api.fantasy.espn.com/logo', 'local'), /connection_id=saved-connection-id$/)
})

test('switching private connections never shares the same pending local projection request', async (t) => {
  const replies = [Promise.withResolvers(), Promise.withResolvers()]
  let index = 0
  const fetch = t.mock.method(globalThis, 'fetch', () => replies[index++].promise)
  configureSession('csrf', true)
  t.after(() => { configureSession('', false); setActiveConnection(null) })
  setActiveConnection('league-one')
  const first = getLocalTeamProjections({ team_id: 1, week: 13 })
  setActiveConnection('league-two')
  const second = getLocalTeamProjections({ team_id: 1, week: 13 })
  assert.notEqual(first, second)
  assert.equal(fetch.mock.callCount(), 2)
  assert.equal(fetch.mock.calls[0].arguments[1].headers['X-League-Connection'], 'league-one')
  assert.equal(fetch.mock.calls[1].arguments[1].headers['X-League-Connection'], 'league-two')
  replies[0].resolve(new Response('{"league":1}'))
  replies[1].resolve(new Response('{"league":2}'))
  assert.deepEqual(await first, { league: 1 })
  assert.deepEqual(await second, { league: 2 })
})

test('a response from a logged-out session cannot repopulate the UI or cache', async (t) => {
  const reply = Promise.withResolvers()
  t.mock.method(globalThis, 'fetch', () => reply.promise)
  configureSession('csrf', true)
  const pending = sendJson('/api/accuracy/2026', undefined, 'GET')
  configureSession('', false)
  reply.resolve(new Response('{"private_data":"old session"}'))
  await assert.rejects(pending, /session changed/)
})
