const PREFIX = 'fantasy-view-v1:'
const MAX_AGE_MS = 15 * 60 * 1000
const MAX_ENTRIES = 12

type Entry = { savedAt: number; value: unknown }

export function createViewCache(storage: () => Storage = () => sessionStorage) {
  const memory = new Map<string, Entry>()

  function read<T>(key: string): T | null {
    try {
      const raw = storage().getItem(PREFIX + key)
      if (raw) memory.set(key, JSON.parse(raw) as Entry)
    } catch { /* Storage can be unavailable or full. */ }
    const entry = memory.get(key)
    if (!entry || typeof entry.savedAt !== 'number'
      || Date.now() - entry.savedAt >= MAX_AGE_MS || entry.savedAt > Date.now()
      || !entry.value || typeof entry.value !== 'object') {
      memory.delete(key)
      try { storage().removeItem(PREFIX + key) } catch { /* Optional cache. */ }
      return null
    }
    return entry.value as T
  }

  function write(key: string, value: unknown) {
    const entry = { savedAt: Date.now(), value }
    memory.delete(key)
    memory.set(key, entry)
    while (memory.size > MAX_ENTRIES) memory.delete(memory.keys().next().value!)
    try {
      const target = storage()
      const keys = Array.from({ length: target.length }, (_, index) => target.key(index))
        .filter((name): name is string => name !== null && name.startsWith(PREFIX))
      // Bound browser storage too; preserve unrelated settings such as theme.
      const entries = keys.map((name) => {
        try { return { name, savedAt: Number(JSON.parse(target.getItem(name)!).savedAt) || 0 } }
        catch { return { name, savedAt: 0 } }
      }).sort((a, b) => a.savedAt - b.savedAt)
      while (entries.length >= MAX_ENTRIES) target.removeItem(entries.shift()!.name)
      target.setItem(PREFIX + key, JSON.stringify(entry))
    } catch { /* Keep the in-memory copy when browser storage is full. */ }
  }

  function clear() {
    memory.clear()
    try {
      const target = storage()
      const keys = Array.from({ length: target.length }, (_, index) => target.key(index))
      for (const key of keys) if (key?.startsWith(PREFIX)) target.removeItem(key)
    } catch { /* Optional cache. */ }
  }

  return { read, write, clear }
}

export const viewCache = createViewCache()

export function viewKey(view: string, mode: string, leagueId: number,
  season: number, week: number, teamId?: number) {
  return JSON.stringify([import.meta.env?.VITE_API_BASE_URL ?? '', view,
    mode, leagueId, season, week, teamId ?? null])
}
