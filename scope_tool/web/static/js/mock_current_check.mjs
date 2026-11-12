// 以不同週期／延遲辨識目前選中的事件，並核對回退及同距規則。
import assert from 'node:assert/strict';
import { eventStats, singleResult } from './mock_measure.js';
import { dualResult } from './mock_measure2.js';
export function currentCheck() {
  assert.equal(eventStats([9,3],[1,-1],[-2,2]).current,3);
  assert.deepEqual(eventStats([9,3],[1,-1],[-2,2],0,false), {current:3,mean:3,min:3,max:3,range:0,std:0,count:1});
  assert.equal(eventStats([9,3],undefined,[-2,2]).current,9);
  assert.equal(eventStats([7],undefined,[10,20]).current,7);
  const t = Float64Array.from({length:5501},(_,i) => -25+i*.01);
  const starts = [-22,-14,-3,7,20], delay = [.1,.2,.3,.4,.5];
  const voltage = (x, offsets) => starts.some((s,i) => Math.round(x*100)>=Math.round((s+offsets[i])*100) && Math.round(x*100)<Math.round((s+offsets[i]+3)*100)) ? 1 : 0;
  const v = Float64Array.from(t,x => voltage(x,[0,0,0,0,0]));
  const w = Float64Array.from(t,x => voltage(x,delay));
  const data = { A:{t,v}, B:{t,v:w} }, pct=[10,50,90];
  const near = (x,y) => assert.ok(Math.abs(x-y)<1e-9,`${x} != ${y}`);
  const entry = {channel:'A',channel2:'B',name:'延遲',rising:true};
  for (const [dx,range,i] of [[{},null,2],[{A:100,B:100},null,3],[{A:-10,B:-10},null,3],[{A:100,B:100},[105,128],4]]) {
    near(dualResult(entry,data,range,dx,pct,{}).stats.current,delay[i]);
  }
  const MEAS = { Vmin:v => Math.min(...v), Vmax:v => Math.max(...v), Vavg:v => v.reduce((a,b) => a+b,0)/v.length };
  const oneCycle = d => singleResult({name:"Vavg",rising:true,mode:"cycle"},t,v,pct,{},MEAS,d);
  assert.ok(oneCycle(0).ok && oneCycle(-10).ok);
  assert.notEqual(oneCycle(0).stats.current, oneCycle(-10).stats.current);
  const period = d => singleResult({name:'週期',rising:true},t,v,pct,{},MEAS,d).stats;
  near(period(0).current,10); near(period(-10).current,13);
  const positive = singleResult({name:'週期',rising:true},Float64Array.from(t,x => x+100),v,pct,{},MEAS,0).stats;
  near(positive.current,13);
  const bound = singleResult({name:'上升時間'},t,v,pct,{},MEAS,0);
  assert.equal(bound.bound,'<'); near(bound.stats.current,.01);
  const bt = Float64Array.from([-10,-8,-7,-6,-5,-2,0,1,2,3,4,5]);
  const bv = Float64Array.from({length:12},(_,i) => [0,1,1,0][i%4]);
  const bounded = singleResult({name:'上升時間'},bt,bv,pct,{},MEAS,0);
  assert.equal(bounded.bound,'<'); near(bounded.stats.current,1); near(bounded.stats.max,3);
  for (const [dx,center] of [[.1,.4],[.7,.1]]) {
    const at = [center-.3,center+.3];
    assert.equal(eventStats([3,9],at,at,dx).current,3);
  }
  // 相位省略最後一事件，仍依來源 1 的起始時間選事件。
  near(dualResult({...entry,name:'相位'},data,null,{},pct,{}).stats.current,.3/10*360);
}
currentCheck();
console.log('mock current self-check OK');
