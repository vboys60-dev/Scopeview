import assert from 'node:assert/strict';
import { singleResult } from '../mock_measure.js';
import { CATALOG } from '../mock_catalog.js';
import { fmt } from '../fmt.js';
const names = ['Vmid','上升邊緣計數','下降邊緣計數','+脈衝計數','-脈衝計數'];
const t = Float64Array.from({length:401}, (_, i) => i);
const v = Float64Array.from(t, (_, i) => i % 40 >= 20 ? 2 : 0);
const meas = { Vmin: a => Math.min(...a), Vmax: a => Math.max(...a) };
for (const pct of [[10,50,90], [20,50,80]]) for (const [i,name] of names.entries()) {
  const item = CATALOG.measurements.find(m => m.name === name);
  assert.ok(item && item.unit === (i ? '' : '{u}'));
  for (const all_edges of [true, false]) {
    const r = singleResult({name, all_edges}, t, v, pct, {}, meas, 0);
    assert.equal(r.stats.current, [1,10,10,10,9][i]);
    assert.equal(r.stats.count, 1);
  }
  assert.match(singleResult({name}, t, new Float64Array(t.length), pct, {}, meas, 0).reason, /TOP_EQ_BASE/);
}
assert.equal(fmt(1234567, ''), '1234570');
console.log('measure_more_check self-check OK');
