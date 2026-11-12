// mock 雙來源量測：各自切片、三閾交越、最近事件與逐事件統計。
import { bound, span } from './mock_dsp.js';
import { eventStats } from './mock_measure.js';
import { CATALOG } from './mock_catalog.js';
export const isDual = name => CATALOG.measurements.some(m => m.name === name && m.sources === 2);
export function dualResult(e, data, range, dx, pct, base) {
  base = { ...base, channel2:e.channel2 };
  const fail = reason => ({ ...base, ok:false, stats:null, reason });
  if (!data[e.channel] || !data[e.channel2]) return fail('來源通道已刪除');
  const signals = [];
  for (const [i, ch] of [e.channel, e.channel2].entries()) {
    const d = dx[ch] ?? 0, w = data[ch];
    const [a,b] = range ? span(w.t, Math.min(...range)-d, Math.max(...range)-d) : [0,w.t.length];
    const t = Array.from(w.t.subarray(a,b), x => x+d), v = Array.from(w.v.subarray(a,b));
    if (!v.some(Number.isFinite)) return fail(`來源 ${i+1}：所選範圍內沒有資料`);
    if (v.length < 2) return fail(`來源 ${i+1}：範圍內至少要 2 個取樣點。`);
    if (!v.every(Number.isFinite)) return fail(`來源 ${i+1}：資料含 NaN 或無限大。`);
    signals.push({ t,v });
  }
  let values, at;
  if (e.name === '電壓比') {
    const rms = signals.map(({v}) => { const avg = v.reduce((s,x) => s+x,0)/v.length; return Math.sqrt(v.reduce((s,x) => s+(x-avg)**2,0)/v.length); });
    if (rms.some(x => x === 0)) return fail(`來源 ${rms[0] === 0 ? 1 : 2} 的 AC RMS 為 0，無法計算電壓比。`);
    values = [20*(Math.log10(rms[0])-Math.log10(rms[1]))];
  } else {
    const mids = signals.map(({t,v}, index) => {
      const lo = Math.min(...v), amp = Math.max(...v)-lo, es = [], up = index ? e.rising2 ?? e.rising : e.rising;
      let prev = -1, state = -1;
      for (let i=0; amp > 0 && i<v.length; i++) {
        const st = v[i] < lo+amp*pct[0]/100 ? 0 : v[i] > lo+amp*pct[2]/100 ? 2 : 1;
        if (st === 1) continue;
        if (state >= 0 && st !== state && (state === 0) === up) {
          let j=prev+1; const mid=lo+amp*pct[e.name === "Delta Time" ? ({lower:0,middle:1,upper:2}[index ? e.edge_level2 ?? "middle" : e.edge_level ?? "middle"]) : 1]/100;
          while (j<i && (up ? v[j]<mid : v[j]>mid)) j++;
          es.push(t[j-1]+(mid-v[j-1])/(v[j]-v[j-1])*(t[j]-t[j-1]));
        }
        prev=i; state=st;
      }
      return es;
    });
    if (mids.some(a => !a.length)) return fail(`${e.name === "Delta Time" ? "EDGE_NOT_FOUND：" : ""}來源 ${mids[0].length ? 2 : 1}：找不到指定方向的邊緣。`);
    if (e.name === 'Delta Time') {
      const a = mids[0][(e.edge_num ?? 1)-1], b = mids[1][(e.edge_num2 ?? 1)-1];
      if (a === undefined || b === undefined) return fail(`EDGE_NOT_FOUND：來源 ${a === undefined ? 1 : 2} 找不到指定邊緣。`);
      return { ...base, ok:true, reason:null, stats:eventStats([b-a], undefined, signals[0].t, 0, true) };
    }
    const [t1,t2] = signals.map(s => s.t);
    const a = mids[0].filter(t => t >= Math.max(t1[0],t2[0]) && t <= Math.min(t1.at(-1),t2.at(-1))), b = mids[1];
    if (!a.length) return fail('兩來源時間範圍沒有重疊');
    at = a;
    values = a.map(t => { const j=bound(b,t), l=b[Math.max(0,j-1)], r=b[Math.min(j,b.length-1)]; return (Math.abs(l-t)<=Math.abs(r-t) ? l : r)-t; });
    if (e.name === '相位') {
      if (a.length < 2) return fail('來源 1：找不到完整週期（需要兩個同方向邊緣）。');
      at = a.slice(0,-1);
      values = values.slice(0,-1).map((d,i) => d/(a[i+1]-a[i])*360);
    }
  }
  return { ...base, ok:true, reason:null, stats:eventStats(values,at,signals[0].t,0,e.all_edges !== false || e.name === "相位") };
}
