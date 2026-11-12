// 單來源 mock：事件統計以顯示時間的觸發參考點選取目前值。
export function eventStats(values, at, t, dx = 0, allEdges = true) {
  const start = t[0]+dx, end = t.at(-1)+dx;
  const ref = start <= 0 && end >= 0 ? 0 : (start+end)/2;
  let i = 0;
  if (at) for (let j=1; j<values.length; j++) {
    const a = Math.abs(at[j]+dx-ref), b = Math.abs(at[i]+dx-ref);
    if (a < b || (a === b && at[j] < at[i])) i = j;
  }
  if (!allEdges) { values = [values[i]]; i = 0; }
  const mean = values.reduce((s,x) => s+x,0)/values.length;
  const min = Math.min(...values), max = Math.max(...values);
  return { current:values[i], mean, min, max, range:max-min,
    std:Math.sqrt(values.reduce((s,x) => s+(x-mean)**2,0)/values.length), count:values.length };
}
export function singleResult(e, t, v, pct, base, MEAS, d) {
  // 區間量測名稱依 analysis/measure.py 的 INTERVAL；catalog 尚無區間欄位。
  const interval = ["Vavg", "Vrms(DC)", "Vrms(AC)"].includes(e.name), es = [];
  const low = MEAS.Vmin(v), amp = MEAS.Vmax(v) - low, [lp, mp, hp] = pct;
  let prev = -1, state = -1, intervalStart = 0, intervalEnd = t.length;
  for (let i = 0; amp > 0 && i < v.length; i++) {
    const st = v[i] < low + amp * lp / 100 ? 0 : v[i] > low + amp * hp / 100 ? 2 : 1;
    if (st === 1) continue;
    if (state >= 0 && st !== state) {
      const rising = state === 0, cross = p => {
        let j = prev + 1; const level = low + amp * p / 100;
        while (j < i && (rising ? v[j] < level : v[j] > level)) j++;
        return t[j-1] + (level-v[j-1]) / (v[j]-v[j-1]) * (t[j]-t[j-1]);
      };
      es.push({ rising, a: prev, b: i, lo:cross(lp), hi:cross(hp), mid: cross(mp), duration: Math.abs(cross(hp)-cross(lp)) });
    }
    prev = i; state = st;
  }
  if (interval && ["cycles", "cycle"].includes(e.mode)) {
    let nearest = null;
    if (e.mode === "cycle") {
      const ref = t[0]+d <= 0 && t.at(-1)+d >= 0 ? 0 : ((t[0]+d)+(t.at(-1)+d))/2;
      nearest = es.reduce((a, b) => !a || Math.abs(b.mid+d-ref) < Math.abs(a.mid+d-ref) ? b : a, null);
    }
    const mids = e.mode === "cycle" ? es.filter(x => nearest && x.rising === nearest.rising && x.mid >= nearest.mid).slice(0,2) : es.filter(x => x.rising === e.rising);
    if (mids.length < 2) return { ...base, ok: false, stats: null, reason: `${e.mode === "cycle" ? "EDGE" : "No edges"}：範圍內不足一個完整週期` };
    intervalStart = t.findIndex(x => x >= mids[0].mid); intervalEnd = t.findIndex(x => x >= mids.at(-1).mid);
    v = v.subarray(intervalStart, intervalEnd);
  }
  let x, values, at;
  if (["Vmid", "上升邊緣計數", "下降邊緣計數", "+脈衝計數", "-脈衝計數"].includes(e.name)) {
    if (!(amp > 0)) return { ...base, ok:false, stats:null, reason:"TOP_EQ_BASE：波形沒有振幅（top = base）。" };
    if (e.name === "Vmid") x = low + amp * mp / 100;
    else if (e.name.includes("邊緣")) x = es.filter(q => q.rising === e.name.startsWith("上升")).length;
    else x = es.slice(0,-1).filter((q,i) => q.rising === e.name.startsWith("+") && q.rising !== es[i+1].rising).length;
    return { ...base, ok:true, stats:eventStats([x], null, t, d), reason:null, ...(e.track ? {marks:e.name === "Vmid" ? [[t[0]+d,x,e.channel],[t.at(-1)+d,x,e.channel]] : null} : {}) };
  }
  if (["上升時間", "下降時間", "上升斜率", "下降斜率"].includes(e.name)) {
    const selected = es.filter(x => x.rising === e.name.startsWith("上升"));
    if (!selected.length) return { ...base, ok: false, stats: null, reason: "沒有完整邊緣" };
    const good = selected.filter(x => x.b-x.a+1 >= 4), slope = e.name.endsWith("斜率");
    const times = good.length ? good.map(x => x.duration) : selected.map(x => t[x.b]-t[x.a]);
    values = slope ? times.map(dt => (e.name.startsWith("上升") ? 1 : -1) * amp * (hp-lp) / 100 / dt) : times;
    at = (good.length ? good : selected).map(q => q.mid);
    if (!good.length) base.bound = slope && e.name.startsWith("上升") ? ">" : "<";
  } else if (["工作週期", "-工作週期"].includes(e.name)) {
    const duties = es.slice(0, -2).flatMap((q, i) => (e.all_edges === false || q.rising === e.rising) ? [(q.rising ? es[i+1].mid-q.mid : es[i+2].mid-es[i+1].mid) / (es[i+2].mid-q.mid) * 100] : []);
    if (!duties.length) return { ...base, ok: false, stats: null, reason: "沒有完整週期" };
    values = e.name === "工作週期" ? duties : duties.map(x => 100-x);
    at = es.slice(0,-2).filter(q => e.all_edges === false || q.rising === e.rising).map(q => q.mid);
  } else if (["週期", "頻率", "+寬度", "-寬度"].includes(e.name)) {
    const cycle = ["週期", "頻率"].includes(e.name);
    const selected = cycle ? es.filter(q => e.all_edges === false || q.rising === e.rising) : es;
    const pairs = selected.slice(0, cycle && e.all_edges === false ? -2 : -1).map((q,i) => [q,selected[i+(cycle && e.all_edges === false ? 2 : 1)]])
      .filter(([q]) => cycle || q.rising === (e.name === "+寬度"));
    values = pairs.map(([q,r]) => e.name === "頻率" ? 1/(r.mid-q.mid) : r.mid-q.mid);
    at = pairs.map(([q]) => q.mid);
    if (!values.length) return { ...base, ok:false, stats:null, reason:"沒有完整週期或脈衝" };
  } else if (!MEAS[e.name]) return { ...base, ok: false, stats: null, reason: "mock 未實作此量測" };
  else x = MEAS[e.name](v);
  let marks;
  if (e.track) {
    const ref = t[0]+d <= 0 && t.at(-1)+d >= 0 ? 0 : (t[0]+t.at(-1))/2+d;
    const q = at?.reduce((a,b) => Math.abs(b+d-ref)<Math.abs(a+d-ref) ? b : a);
    const k = es.findIndex(z => z.mid === q), mid = low+amp*mp/100;
    if (["Vmax","Vmin","Vp-p"].includes(e.name)) {
      const indices = e.name === "Vmax" ? [v.indexOf(Math.max(...v))] : e.name === "Vmin" ? [v.indexOf(Math.min(...v))] : [v.indexOf(Math.min(...v)),v.indexOf(Math.max(...v))];
      marks = indices.map(i => [t[i]+d,v[i],e.channel]);
    } else if (["Vtop","Vbase","Vamp"].includes(e.name)) {
      marks = e.name === "Vamp" ? [[t[0]+d,low,e.channel],[t.at(-1)+d,low+amp,e.channel]] : [[t[0]+d,x,e.channel],[t.at(-1)+d,x,e.channel]];
    } else if (k >= 0 && ["上升時間","下降時間","上升斜率","下降斜率"].includes(e.name)) {
      marks = [[es[k].lo+d,low+amp*lp/100,e.channel],[es[k].hi+d,low+amp*hp/100,e.channel]];
    } else if (k >= 0) {
      const count = ["週期","頻率","工作週期","-工作週期"].includes(e.name) ? 3 : 2;
      marks = es.slice(k,k+count).filter((_,i) => !["週期","頻率"].includes(e.name) || i !== 1).map(z => [z.mid+d,mid,e.channel]);
    } else marks = [[t[intervalStart]+d,v[0],e.channel],[t[intervalEnd-1]+d,v.at(-1),e.channel]];
  }
  return { ...base, ok:true, stats:eventStats(values ?? [x], at, t, d, e.all_edges !== false), reason:null, ...(e.track ? {marks} : {}) };
}
