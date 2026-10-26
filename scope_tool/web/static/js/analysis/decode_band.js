// 主圖時間軸下方的 I3C 事件／byte／bit 標註；時間一律由來源加 SCL dx。
import { createCanvas, cssVar, linear, debounce, makeLatest } from './plotcore.js';
import { MARGIN } from './mainplot.js';
import { decodeModel } from './decode.js';
export const BAND_H = 40;
/** frames 的 t1 單調；保留跨過左緣及恰好碰到邊界的事件。 */
export function visibleFrames(frames, t0, t1) {
  let lo = 0, hi = frames.length;
  while (lo < hi) { const mid = (lo+hi) >>> 1; if (frames[mid].t1 < t0) lo = mid+1; else hi = mid; }
  const out = [];
  for (let i = lo; i < frames.length && frames[i].t0 <= t1; i++) out.push(frames[i]);
  return out;
}
export const ninthLabel = f => f.ninth_kind === 'ack' ? (f.ninth ? 'N' : 'A') : f.ninth_kind === 'parity' ? (f.ok ? 'P✓' : 'P✗') : f.ninth_kind === 'tbit' ? `T${f.ninth}` : '';
export function bandLayout(frames, view, rect, dx = 0) {
  const X = linear(view.t0,view.t1,rect.l,rect.l+rect.w), bars = [], fields = [];
  for (const f of visibleFrames(frames,view.t0-dx,view.t1-dx)) {
    const x0 = Math.max(rect.l,X(f.t0+dx)), x1 = Math.min(rect.l+rect.w,X(f.t1+dx));
    const last = bars.at(-1), tiny = x1-x0 < 2;
    if (tiny && last?.tiny && x0-last.x1 < 2 && last.f.status === f.status) last.x1 = x1;
    else bars.push({ f,x0,x1,tiny,label:x1-x0 >= 40 ? f.label : '' });
    for (const field of f.fields) {
      if (field.t1 < view.t0-dx || field.t0 > view.t1-dx) continue;
      const a = X(field.t0+dx), b = X(field.t1+dx);
      const prev = fields.at(-1), small = b-a < 2;
      if (small && prev?.tiny && a-prev.x1 < 2 && prev.f.ok === field.ok) prev.x1 = b;
      else fields.push({ f:field,x0:a,x1:b,tiny:small,bitMode:field.nbits > 1 && (b-a)/(field.nbits-1) >= 10 });
    }
  }
  return { bars,fields,X };
}
/** 逐 bit 的格界取相鄰真實取樣點中點；不把整個 field 平均分割。 */
export function bitCells(field, bits, X, dx = 0) {
  const samples = bits.filter(([t]) => t >= field.t0 && t <= field.t1);
  return samples.map(([t,value],i) => {
    const before = samples[i-1]?.[0], after = samples[i+1]?.[0];
    const a = before == null ? t-(after == null ? 0 : after-t)/2 : (before+t)/2;
    const b = after == null ? t+(before == null ? 0 : t-before)/2 : (t+after)/2;
    return { x0:X(a+dx),x1:X(b+dx),sample:X(t+dx),ninth:t === field.t1 && !!field.ninth_kind,label:t === field.t1 && field.ninth_kind ? ninthLabel(field) : String(value) };
  });
}
export function drawBand(g, w, state, bits = []) {
  const r = state.decodeResult, rect = state.plotRect ?? { l:MARGIN.l,w:Math.max(1,w-MARGIN.l-MARGIN.r) };
  const col = { ok:cssVar('--c-ok','#62dd98'),warn:cssVar('--c-warn','#f7cd5f'),error:cssVar('--c-danger','#ff8f87'),info:cssVar('--c-accent','#8cc4ff') };
  const text = cssVar('--c-plot-text','#ccc');
  g.fillStyle = cssVar('--c-plot-bg','#000'); g.fillRect(0,0,w,BAND_H);
  if (!r?.summary.ok) return { bars:[],fields:[] };
  const dx = state.channels.find(c => c.name === r.scl)?.time_offset ?? 0;
  const layout = bandLayout(r.frames,state.view,rect,dx);
  g.globalAlpha = r.stale ? .55 : 1;
  g.fillStyle = cssVar('--c-plot-axis','#888'); g.font = '10px sans-serif'; g.textAlign = 'right'; g.textBaseline = 'alphabetic';
  g.fillText('事件',rect.l-8,14); g.fillText(layout.fields.some(f => f.bitMode) ? 'bit' : 'byte',rect.l-8,34);
  g.save(); g.beginPath(); g.rect(rect.l,0,rect.w,BAND_H); g.clip();
  function box(a,b,y,color,label,min = 24) {
    a = Math.max(rect.l,a); b = Math.min(rect.l+rect.w,b);
    if (b <= a) return;
    g.fillStyle = color; g.globalAlpha = r.stale ? .09 : .16; g.fillRect(a,y,b-a,18); g.globalAlpha = r.stale ? .55 : 1;
    g.strokeStyle = color; g.lineWidth = 1; g.strokeRect(a+.5,y+.5,Math.max(0,b-a-1),17);
    if (label && b-a >= min) {
      g.save(); g.beginPath(); g.rect(a+2,y,b-a-4,18); g.clip(); g.fillStyle = color; g.textAlign = 'left'; g.fillText(label,a+5,y+13); g.restore();
    }
  }
  g.font = '12px sans-serif';
  for (const b of layout.bars) {
    box(b.x0,b.x1,1,col[b.f.kind === 'hdr' && b.f.status === 'ok' ? 'info' : b.f.status] ?? col.info,b.label,40);
  }
  const selected = layout.bars.find(b => b.f.i === state.decodeSel) ?? (() => {
    const f = visibleFrames(r.frames,state.view.t0-dx,state.view.t1-dx).find(f => f.i === state.decodeSel);
    return f && { x0:Math.max(rect.l,layout.X(f.t0+dx)),x1:Math.min(rect.l+rect.w,layout.X(f.t1+dx)) };
  })();
  if (selected) { g.strokeStyle = '#fff'; g.lineWidth = 2; g.strokeRect(selected.x0,1,Math.max(1,selected.x1-selected.x0),18); }
  let count = 0;
  for (const b of layout.fields) {
    const c = b.f.ok ? text : col.error, tag = ninthLabel(b.f);
    if (b.bitMode) {
      for (const bit of bitCells(b.f,bits,layout.X,dx)) {
        const color = bit.ninth ? (b.f.ok ? col.info : col.error) : c;
        box(bit.x0,bit.x1,21,color,''); count++;
        if (bit.x1-bit.x0 >= 10) {
          g.save(); g.beginPath(); g.rect(bit.x0,21,bit.x1-bit.x0,18); g.clip();
          g.fillStyle = color; g.font = bit.ninth ? '9px sans-serif' : '12px sans-serif';
          g.textAlign = 'center'; g.fillText(bit.label,(bit.x0+bit.x1)/2,34); g.restore();
        }
        g.strokeStyle = cssVar('--c-ch1','#f0e442'); g.beginPath(); g.moveTo(bit.sample,21); g.lineTo(bit.sample,25); g.stroke();
      }
    } else {
      const value = b.f.value == null ? b.f.label : b.f.kind === 'addr' ? (b.f.value>>1).toString(16).toUpperCase().padStart(2,'0')+(b.f.value & 1 ? ' R' : ' W') : b.f.value.toString(16).toUpperCase().padStart(Math.ceil((b.f.nbits-(b.f.ninth_kind ? 1 : 0))/4),'0');
      box(b.x0,b.x1,21,c,'');
      if (!b.tiny && Math.min(rect.l+rect.w,b.x1)-Math.max(rect.l,b.x0) >= 24) {
        g.save(); g.beginPath(); g.rect(Math.max(rect.l,b.x0)+2,21,Math.min(rect.l+rect.w,b.x1)-Math.max(rect.l,b.x0)-4,18); g.clip();
        g.fillStyle = c; g.textAlign = 'left'; g.fillText(value,Math.max(rect.l,b.x0)+4,34);
        g.font = '9px sans-serif'; g.textAlign = 'right'; g.fillStyle = b.f.ok ? col.info : col.error;
        if (g.measureText(tag).width+value.length*7+10 <= Math.min(rect.l+rect.w,b.x1)-Math.max(rect.l,b.x0)) g.fillText(tag,b.x1-3,37); g.font = '12px sans-serif'; g.restore();
      }
    }
  }
  g.restore(); g.globalAlpha = 1;
  return { ...layout,bitCount:count };
}
export function mount(el, ctx) {
  const { store,bridge } = ctx, model = decodeModel(ctx), latest = makeLatest();
  let cached = null, wanted = '', pending = '', disposed = false;
  const cv = createCanvas(el,draw);
  const fetchSoon = debounce(async () => {
    const s = store.get(), r = s.decodeResult;
    if (!wanted || !r || el.hidden) return;
    const key = wanted, req = latest.begin(), dx = s.channels.find(c => c.name === r.scl)?.time_offset ?? 0;
    pending = key;
    try {
      const data = await bridge.call('decode_bits',{ decode_id:r.summary.decode_id,t0:s.view.t0-dx,t1:s.view.t1-dx });
      if (req.ok() && !disposed && wanted === key) { cached = { key,bits:data.bits }; draw(); }
    } catch (e) { if (req.ok() && e.code !== 'STALE') ctx.ui?.showError?.(e,'讀取解碼 bit 失敗'); }
    finally { if (pending === key) pending = ''; }
  },150);
  function draw() {
    const [w,h] = cv.size(); if (!w || !h) return;
    const s = store.get(), r = s.decodeResult, dx = s.channels.find(c => c.name === r?.scl)?.time_offset ?? 0;
    const key = r ? [s.view.t0-dx,s.view.t1-dx,r.summary.decode_id].join('|') : '';
    const layout = drawBand(cv.ctx,w,s,cached?.key === key ? cached.bits : []);
    cv.canvas.dataset.left = String(s.plotRect?.l ?? MARGIN.l); cv.canvas.dataset.bits = String(layout.bitCount ?? 0);
    const next = !el.hidden && model.config.band && layout.fields.some(f => f.bitMode) ? key : '';
    if (wanted !== next) { latest.cancel(); fetchSoon.cancel(); wanted = next; pending = ''; }
    if (next && cached?.key !== next && pending !== next) fetchSoon();
  }
  cv.canvas.onclick = e => {
    const s = store.get(), r = s.decodeResult; if (!r) return;
    const rect = s.plotRect ?? { l:MARGIN.l,w:cv.size()[0]-MARGIN.l-MARGIN.r }, x = e.clientX-cv.canvas.getBoundingClientRect().left;
    if (x < rect.l || x > rect.l+rect.w || e.clientY-cv.canvas.getBoundingClientRect().top > 20) return;
    const dx = s.channels.find(c => c.name === r.scl)?.time_offset ?? 0;
    const t = linear(rect.l,rect.l+rect.w,s.view.t0,s.view.t1)(x)-dx;
    const f = visibleFrames(r.frames,t,t)[0]; if (f) store.set({ decodeSel:f.i },'user');
  };
  const off = store.on(['view','channels','plotRect','decodeResult','decodeSel'],draw), offModel = model.on(draw);
  return { draw,dispose() { disposed = true; off(); offModel(); latest.cancel(); fetchSoon.cancel(); cv.dispose(); } };
}
