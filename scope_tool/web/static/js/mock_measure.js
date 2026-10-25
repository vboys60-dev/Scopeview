// 單來源 mock：事件統計以顯示時間的觸發參考點選取目前值。
export function eventStats(values, at, t, dx = 0) {
  const start = t[0]+dx, end = t.at(-1)+dx;
  const ref = start <= 0 && end >= 0 ? 0 : (start+end)/2;
  let i = 0;
  if (at) for (let j=1; j<values.length; j++) {
    const a = Math.abs(at[j]+dx-ref), b = Math.abs(at[i]+dx-ref);
    if (a < b || (a === b && at[j] < at[i])) i = j;
  }
  const mean = values.reduce((s,x) => s+x,0)/values.length;
  const min = Math.min(...values), max = Math.max(...values);
  return { current:values[i], mean, min, max, range:max-min,
    std:Math.sqrt(values.reduce((s,x) => s+(x-mean)**2,0)/values.length), count:values.length };
}
export function singleResult(e, t, v, pct, base, MEAS, d) {
  // 區間量測名稱依 analysis/measure.py 的 INTERVAL；catalog 尚無區間欄位。
  const interval = ["Vavg", "Vrms(DC)", "Vrms(AC)"].includes(e.name), es = [];
  const low = MEAS.Vmin(v), amp = MEAS.Vmax(v) - low, [lp, mp, hp] = pct;
  let prev = -1, state = -1;
  for (let i = 0; amp > 0 && i < v.length; i++) {
    const st = v[i] < low + amp * lp / 100 ? 0 : v[i] > low + amp * hp / 100 ? 2 : 1;
    if (st === 1) continue;
    if (state >= 0 && st !== state) {
      const rising = state === 0, cross = p => {
        let j = prev + 1; const level = low + amp * p / 100;
        while (j < i && (rising ? v[j] < level : v[j] > level)) j++;
        return t[j-1] + (level-v[j-1]) / (v[j]-v[j-1]) * (t[j]-t[j-1]);
      };
      es.push({ rising, a: prev, b: i, mid: cross(mp), duration: Math.abs(cross(hp)-cross(lp)) });
    }
    prev = i; state = st;
  }
  if (interval && e.mode === "cycles") {
    const mids = es.filter(x => x.rising === e.rising);
    if (mids.length < 2) return { ...base, ok: false, stats: null, reason: "No edges：範圍內不足一個完整週期" };
    v = v.subarray(t.findIndex(x => x >= mids[0].mid), t.findIndex(x => x >= mids.at(-1).mid));
  }
  let x, values, at;
  if (["上升時間", "下降時間", "上升斜率", "下降斜率"].includes(e.name)) {
    const selected = es.filter(x => x.rising === e.name.startsWith("上升"));
    if (!selected.length) return { ...base, ok: false, stats: null, reason: "沒有完整邊緣" };
    const good = selected.filter(x => x.b-x.a+1 >= 4), slope = e.name.endsWith("斜率");
    const times = good.length ? good.map(x => x.duration) : selected.map(x => t[x.b]-t[x.a]);
    values = slope ? times.map(dt => (e.name.startsWith("上升") ? 1 : -1) * amp * (hp-lp) / 100 / dt) : times;
    at = (good.length ? good : selected).map(q => q.mid);
    if (!good.length) base.bound = slope && e.name.startsWith("上升") ? ">" : "<";
  } else if (["工作週期", "-工作週期"].includes(e.name)) {
    const duties = es.slice(0, -2).flatMap((q, i) => q.rising === e.rising ? [(e.rising ? es[i+1].mid-q.mid : es[i+2].mid-es[i+1].mid) / (es[i+2].mid-q.mid) * 100] : []);
    if (!duties.length) return { ...base, ok: false, stats: null, reason: "沒有完整週期" };
    values = e.name === "工作週期" ? duties : duties.map(x => 100-x);
    at = es.slice(0,-2).filter(q => q.rising === e.rising).map(q => q.mid);
  } else if (["週期", "頻率", "+寬度", "-寬度"].includes(e.name)) {
    const cycle = ["週期", "頻率"].includes(e.name);
    const selected = cycle ? es.filter(q => q.rising === e.rising) : es;
    const pairs = selected.slice(0,-1).map((q,i) => [q,selected[i+1]])
      .filter(([q]) => cycle || q.rising === (e.name === "+寬度"));
    values = pairs.map(([q,r]) => e.name === "頻率" ? 1/(r.mid-q.mid) : r.mid-q.mid);
    at = pairs.map(([q]) => q.mid);
    if (!values.length) return { ...base, ok:false, stats:null, reason:"沒有完整週期或脈衝" };
  } else if (!MEAS[e.name]) return { ...base, ok: false, stats: null, reason: "mock 未實作此量測" };
  else x = MEAS[e.name](v);
  return { ...base, ok:true, stats:eventStats(values ?? [x], at, t, d), reason:null };
}
