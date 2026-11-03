import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createViewCache, viewKey } from '../src/lib/viewCache.ts'

class MemoryStorage {
  values = new Map()
  get length() { return this.values.size }
  key(index) { return [...this.values.keys()][index] ?? null }
  getItem(key) { return this.values.get(key) ?? null }
  setItem(key, value) { this.values.set(key, value) }
  removeItem(key) { this.values.delete(key) }
}

test('saved results survive recreation but expire after 15 minutes', (t) => {
  const storage = new MemoryStorage()
  let clock = 1000
  t.mock.method(Date, 'now', () => clock)
  createViewCache(() => storage).write('team', { points: 20 })
  assert.deepEqual(createViewCache(() => storage).read('team'), { points: 20 })
  clock += 15 * 60 * 1000
  assert.equal(createViewCache(() => storage).read('team'), null)
})

test('keys separate leagues, weeks, teams and private/public connections', () => {
  const keys = [
    viewKey('team', 'public', 1, 2026, 8, 1),
    viewKey('team', 'local', 1, 2026, 8, 1),
    viewKey('team', 'public', 2, 2026, 8, 1),
    viewKey('team', 'public', 1, 2026, 9, 1),
    viewKey('team', 'public', 1, 2026, 8, 2),
  ]
  assert.equal(new Set(keys).size, keys.length)
})

test('blocked storage falls back to memory and clearing removes it', () => {
  const cache = createViewCache(() => { throw new Error('blocked') })
  cache.write('team', { points: 20 })
  assert.deepEqual(cache.read('team'), { points: 20 })
  cache.clear()
  assert.equal(cache.read('team'), null)
})

test('storage stays bounded and clearing preserves unrelated settings', () => {
  const storage = new MemoryStorage()
  storage.setItem('theme', 'dark')
  const cache = createViewCache(() => storage)
  for (let index = 0; index < 30; index++) cache.write(String(index), { index })
  assert.ok(storage.length <= 13)
  cache.clear()
  assert.equal(storage.length, 1)
  assert.equal(storage.getItem('theme'), 'dark')
})
