import {test} from 'node:test'
import assert from 'node:assert/strict'
import {createRequire} from 'node:module'
import {readFile} from 'node:fs/promises'
import {pathToFileURL} from 'node:url'
import ts from 'typescript'
import {createElement} from 'react'
import {renderToStaticMarkup} from 'react-dom/server'

const require=createRequire(import.meta.url)
let compiled=ts.transpileModule(await readFile(new URL('../src/components/AccuracyInsights.tsx',import.meta.url),'utf8'),
  {compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2023}}).outputText
compiled=compiled.replaceAll('react/jsx-runtime',pathToFileURL(require.resolve('react/jsx-runtime')).href)
const {AccuracyInsights}=await import(`data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`)
const render=report=>renderToStaticMarkup(createElement(AccuracyInsights,{report}))
const empty={
  range_coverage:{count:0,inside:0,below:0,above:0,missing:5,coverage_pct:null,average_width:null,by_position:[]},
  error_distribution:{count:0,median_absolute_error:null,p90_absolute_error:null,rmse:null,within_two_pct:null,within_five_pct:null,within_ten_pct:null,buckets:[]},
  espn_comparison:{count:0,pending:3,ai_mae:null,espn_mae:null,ai_closer:0,espn_closer:0,ties:0,mae_improvement:null,by_position:[]},
}

test('new accuracy panels do not turn missing data into perfect error or zero coverage',()=>{
  const markup=render(empty)
  for(const text of ['Error patterns will appear','No graded forecasts with saved ranges','Collecting paired forecasts','3 awaiting results','5 graded forecasts had no usable saved range'])assert.ok(markup.includes(text),text)
  assert.ok(!markup.includes('0.0%'));assert.ok(!markup.includes('0.00 pts'))
})

test('coverage and ESPN comparisons explain denominators, scoring, and forecast provenance',()=>{
  const markup=render({...empty,
    range_coverage:{...empty.range_coverage,count:4,inside:2,below:1,above:1,coverage_pct:50,average_width:12},
    error_distribution:{...empty.error_distribution,count:10,within_two_pct:20,within_five_pct:60,within_ten_pct:90},
    espn_comparison:{...empty.espn_comparison,count:2,ai_mae:4,espn_mae:3,mae_improvement:-1,ai_closer:1,espn_closer:1},
  })
  for(const text of ['50.0%','2 inside / 4 graded','12.00 pts','80% coverage','-1.00 pts',
    'same players, same scoring','exactly the same 2 results','custom-scoring league','K/DST are excluded',
    'Only ESPN forecasts observed before kickoff','rows on other pages'])assert.ok(markup.includes(text),text)
})

test('older API responses can still display the existing accuracy page during deployment',()=>{
  assert.equal(render({}), '')
})
