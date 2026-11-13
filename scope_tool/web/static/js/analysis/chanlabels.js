// 格內標籤：全部幾何使用 CSS px；先配置再繪圖，不讀 store 或游標模組。
import { chLabel } from './alias.js';
import { channelHandles } from './handles.js';
import { fmt } from '../fmt.js';
export const LABEL_BGS = Object.freeze({ none: '透明', dark: '深色', panel: '面板', tint: '淡色', solid: '實心' });
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const intersects = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w && a.y < b.y + b.h && b.y < a.y + a.h;
const area = (a, b) => Math.max(0, Math.min(a.x+a.w,b.x+b.w)-Math.max(a.x,b.x)) * Math.max(0, Math.min(a.y+a.h,b.y+b.h)-Math.max(a.y,b.y));
const ys = (row, anchor) => [...new Set([0,-18,18,-36,36].map(d => clamp(anchor - 8 + d, row.t + 1, row.t + row.h - 17)))];
function candidates(row, item, placed, reserve = 0) {
  const out = [], limit = row.l + row.w * .5 - reserve;
  for (const y of ys(row, item.anchorY)) {
    let x = row.l + 4;
    while (x + item.w <= limit) {
      const box = { ...item, x, y, h: 16 }; out.push(box);
      const hits = placed.filter(b => intersects(box,b));
      if (!hits.length) break;
      x = Math.max(...hits.map(b => b.x + b.w)) + 4;
    }
  }
  return out;
}
function shorten(item, maxW, measure) {
  const text = name => `${item.shape}${name} · ${item.scale}`;
  let display = item.display, value = text(display);
  if (measure(value) + 8 > maxW) {
    const chars = [...display]; let lo = 0, hi = chars.length;
    while (lo < hi) { const mid = Math.ceil((lo+hi)/2); if (measure(text(chars.slice(0,mid).join('')+'…'))+8 <= maxW) lo = mid; else hi = mid-1; }
    display = chars.slice(0,lo).join('')+'…'; value = text(display);
  }
  return { ...item, display, text: value, w: measure(value)+8, h: 16 };
}
export function layoutRow(row, { fixed = [], readouts = [], labels = [], measure, selected }) {
  const placed = [...fixed], out = { row, fixed, readouts: [], labels: [], plus: null };
  for (const item of readouts) {
    const w = measure(item.text), h = 14, right = row.l + row.w - 4;
    const y = clamp(item.y + 2 + (item.y + 16 > row.t + row.h ? -16 : 0), row.t+1, row.t+row.h-15);
    let box = { ...item, x: right - w, y, w, h }, trials = [box];
    const hits = placed.filter(b => intersects(box,b));
    if (hits.length) trials.push({ ...box, x: Math.min(...hits.map(b => b.x)) - 4 - w });
    const base = trials.at(-1), previous = out.readouts[0], sign = previous && y < previous.y ? -1 : 1;
    for (let n = 1; n <= 4; n++) for (const d of [sign*n*16,-sign*n*16]) trials.push({ ...base, y: clamp(y+d,row.t+1,row.t+row.h-15) });
    box = trials.find(b => b.x >= row.l && !placed.some(p => intersects(b,p))) ?? trials.reduce((a,b) => placed.reduce((n,p)=>n+area(b,p),0) < placed.reduce((n,p)=>n+area(a,p),0) ? b : a);
    out.readouts.push(box); placed.push(box);
  }
  const sorted = labels.map((v,i)=>({ ...v, order:i })).sort((a,b)=>(b.name===selected)-(a.name===selected)||a.order-b.order), hidden = [];
  const maxW = Math.min(220,row.w*.5-8), plusWidth = measure(`+${Math.max(9,labels.length)}`)+8;
  for (const [i, label] of sorted.entries()) {
    const reserve = i < sorted.length-1 ? plusWidth : 0, item = shorten(label,maxW-reserve,measure);
    const trials = candidates(row,item,placed,reserve);
    let box = trials.find(b=>!placed.some(p=>intersects(b,p)));
    if (!box && label.name === selected) {
      const fallback = trials.length ? trials : ys(row,item.anchorY).map(y=>({ ...item,x:row.l+4,y }));
      box = fallback.reduce((a,b)=>placed.reduce((n,p)=>n+area(b,p),0)<placed.reduce((n,p)=>n+area(a,p),0)?b:a);
    }
    if (box) { placed.push(box); out.labels.push(box); } else hidden.push(label);
  }
  if (hidden.length) {
    const last = out.labels.at(-1), text = `+${hidden.length}`;
    const item = { text, title: hidden.map(b=>b.display).join('、'), w:measure(text)+8, h:16, anchorY:last ? last.y+8 : row.t+row.h/2, color: '#ddd', bg:'dark' };
    const trials = candidates(row,item,placed);
    out.plus = trials.find(b=>!placed.some(p=>intersects(b,p))) ?? { ...item,x:clamp(last ? last.x+last.w+4 : row.l+4,row.l,row.l+row.w-item.w),y:clamp(last?.y ?? row.t+1,row.t+1,row.t+row.h-17) };
  }
  return out;
}
export function plotLayout(s, rect, X, measure, extras = {}) {
  const handles = channelHandles(s.channels,rect);
  return (rect.rows ?? [rect]).map(row => {
    const fixed = (extras.marks ?? []).filter(m=>m.row.index===row.index).map(m=>({ x:m.x-7,y:row.t+row.h-12,w:14,h:14 }));
    fixed.push(...(extras.edges ?? []).filter(b=>b.y < row.t+row.h && b.y+b.h > row.t));
    const xTexts = row.index === 0 ? extras.xTexts ?? [] : []; fixed.push(...xTexts);
    const labels = s.channels.flatMap((c,i)=>!c.visible || !row.names.includes(c.name) ? [] : [{ name:c.name, display:chLabel(s.channels,c.name), shape:'●▲■◆'[i%4], scale:`${fmt(c.scale,c.unit ?? "")}/格`, color:c.color, bg:c.labelBg ?? 'none', anchorY:handles.find(b=>b.name===c.name).anchorY,
      title:`${c.alias ? `${chLabel(s.channels,c.name)}（原名 ${c.name}）` : c.name} · ${fmt(c.scale,c.unit ?? "")}/格` }]);
    return { ...layoutRow(row,{ fixed,readouts:row.index===(rect.cy ?? rect).index ? extras.yReadouts : [], labels,measure,selected:s.selected }), xTexts };
  });
}
function drawTag(g,b,hover) {
  g.save(); g.globalAlpha = hover === b || hover === (b.name ?? b.title) ? .15 : 1;
  const mode = b.bg ?? 'none';
  if (mode !== 'none') {
    g.fillStyle = mode==='solid' ? b.color : mode==='tint' ? b.color : mode==='panel' ? 'rgba(38,43,56,.92)' : 'rgba(0,0,0,.7)';
    if (mode==='tint') g.globalAlpha *= .25;
    g.beginPath(); g.roundRect(b.x,b.y,b.w,b.h,3); g.fill();
    if (mode==='tint') g.globalAlpha = hover===b || hover===(b.name ?? b.title) ? .15 : 1;
  }
  g.fillStyle = mode==='solid' ? '#000' : b.color; g.textAlign='left'; g.textBaseline='top';
  if (mode==='none' || mode==='tint') { g.lineJoin='round'; g.lineWidth=3; g.strokeStyle='#000'; g.strokeText(b.text,b.x+4,b.y+1); }
  g.fillText(b.text,b.x+4,b.y+1); g.restore();
}
// phase 用於讓 ▲ 位於標籤之上、游標文字之下；省略則繪製全部。
export function drawLayout(g, layout, hover, phase = 'all') {
  g.save(); g.font='12px sans-serif';
  for (const r of layout) {
    if (phase !== 'texts') for (const b of [...r.labels,...(r.plus ? [r.plus] : [])]) drawTag(g,b,hover);
    if (phase !== 'labels') {
      g.save(); g.textBaseline='top'; g.textAlign='right';
      for (const b of r.readouts) { g.fillStyle=b.color; g.fillText(b.text,b.x+b.w,b.y); }
      g.textAlign='left'; for (const b of r.xTexts ?? []) { g.fillStyle=b.color; g.fillText(b.text,b.x,b.y); } g.restore();
    }
  }
  g.restore();
}
export const hitLabel = (layout,x,y) => layout.flatMap(r=>[...r.labels,...(r.plus ? [r.plus] : [])]).find(b=>x>=b.x && x<=b.x+b.w && y>=b.y && y<=b.y+b.h) ?? null;
