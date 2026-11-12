import assert from 'node:assert/strict';
import { dualResult } from '../mock_measure2.js';
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
const data = { A:{t,v}, B:{t,v:Float64Array.from(v, (_, i) => v[(i+v.length-3)%v.length])} };
const entry = {name:'Delta Time', channel:'A', channel2:'B', rising:true, rising2:true, edge_num:2, edge_num2:2};
const delta = (e=entry, range=null, dx={}) => dualResult(e, data, range, dx, [10,50,90], {});
assert.equal(delta().stats.current, 3);
assert.ok(Math.abs(delta({...entry,edge_level:'lower',edge_level2:'upper'}).stats.current-3.8)<1e-10);
assert.equal(delta(entry,null,{B:-5}).stats.current,-2);
assert.match(delta({...entry,edge_num:100}).reason,/EDGE_NOT_FOUND/);
assert.equal(delta({...entry,edge_num:1,edge_num2:1},[20,200]).stats.current,-37);
assert.equal(fmt(1234567, ''), '1234570');
const tracked = delta({...entry,track:true},null,{A:2,B:-1});
assert.deepEqual(tracked.marks.map(p => p[2]), ['A','B']);
assert.equal(tracked.marks[1][0]-tracked.marks[0][0], tracked.stats.current);
const single = singleResult({name:'週期',channel:'A',rising:true,track:true},t,v,[10,50,90],{},meas,2);
assert.equal(single.marks.length,2);
assert.equal(single.marks[1][0]-single.marks[0][0],single.stats.current);
assert.equal(singleResult({name:'上升邊緣計數',channel:'A',track:true},t,v,[10,50,90],{},meas,0).marks,null);
console.log('measure_more_check self-check OK');
