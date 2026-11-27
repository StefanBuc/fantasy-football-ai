import { test } from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { readFile } from 'node:fs/promises'
import { pathToFileURL } from 'node:url'
import ts from 'typescript'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

const require = createRequire(import.meta.url)
const source = await readFile(new URL('../src/components/PublicSite.tsx', import.meta.url), 'utf8')
let compiled = ts.transpileModule(source, { compilerOptions: {
  jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2023,
}}).outputText
compiled = compiled.replaceAll('react/jsx-runtime', pathToFileURL(require.resolve('react/jsx-runtime')).href)
  .replaceAll("from 'react'", `from '${pathToFileURL(require.resolve('react')).href}'`)
  .replaceAll('../lib/navigation', new URL('../src/lib/navigation.ts', import.meta.url).href)
  .replaceAll('../lib/publicPerformance', new URL('../src/lib/publicPerformance.ts', import.meta.url).href)
const { PublicSite, PerformanceTiles, PublicHeader } = await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)

test('public home clearly labels sample data and offers login with disabled signup', () => {
  const markup = renderToStaticMarkup(createElement(PublicSite, {}))
  for (const text of ['Your next move.', 'Backed by data.', 'Explore the preview',
    'SAMPLE DATA', 'Fictional players', 'Model performance', 'How it works', 'Signups currently closed']) {
    assert.ok(markup.includes(text), text)
  }
  assert.match(markup, /<button[^>]*disabled=""[^>]*>Sign up<\/button>/)
  assert.match(markup, /href="\/login"/)
  assert.ok(!markup.includes('ESPN SWID'))
  assert.ok(!markup.includes('manage_owner'))
})

test('direct signup page is closed and has no account creation form', () => {
  const markup = renderToStaticMarkup(createElement(PublicSite, { page: '/signup' }))
  assert.match(markup, /Registration is closed/)
  assert.ok(!markup.includes('<form'))
  assert.ok(!markup.includes('<input'))
})

test('authenticated public navigation points to the dashboard', () => {
  const markup = renderToStaticMarkup(createElement(PublicHeader, { authenticated: true }))
  assert.match(markup, /href="\/app"/)
  assert.match(markup, /Open dashboard/)
})

test('performance shows measured error, threshold, and sample size without claiming an accuracy percentage', () => {
  const markup = renderToStaticMarkup(createElement(PerformanceTiles, { loading: false, error: null, data: {
    state: 'ready', season: 2026, saved: 3, compared: 2, pending: 1, mae: 7, within_five_pct: 50,
    last_result_update: '2026-11-25T15:00:00Z', latest_week: 12,
  }}))
  for (const value of ['7.00 pts', '50.0%', 'Within 5 points', 'Forecasts graded', 'Latest graded week: 12']) assert.ok(markup.includes(value), value)
  assert.ok(!markup.includes('accuracy %'))
})

test('empty/error states do not invent performance scores', () => {
  const empty = renderToStaticMarkup(createElement(PerformanceTiles, { loading: false, error: null,
    data: { state: 'collecting', saved: 0, compared: 0, mae: null, within_five_pct: null, last_result_update: null } }))
  assert.match(empty, /Collecting results/)
  assert.ok(!empty.includes('0.00 pts'))
  assert.ok(!empty.includes('0.0%'))
  const failed = renderToStaticMarkup(createElement(PerformanceTiles, { data: null, loading: false, error: 'database failed' }))
  assert.match(failed, /temporarily unavailable/)
  assert.ok(!failed.includes('database failed'))
})
