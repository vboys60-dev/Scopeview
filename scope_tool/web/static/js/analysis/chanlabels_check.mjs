// 3A：直接驗證產品配置、繪圖與主圖／報告事件。
import assert from 'node:assert/strict';
import { layoutRow, plotLayout, drawLayout, hitLabel, LABEL_BGS } from './chanlabels.js';
import { channelHandles } from './handles.js';
import { withGrids } from './grids.js';
import { mount, layoutRect } from './mainplot.js';
import { createStore } from './store.js';
import { collectReport } from './report.js';
import * as fmt from '../fmt.js';
const measure = t => [...t].length*7;
const overlap = (a,b) => a.x<b.x+b.w && b.x<a.x+a.w && a.y<b.y+b.h && b.y<a.y+a.h;
const boxes = r => [...r.readouts,...r.labels,...(r.plus ? [r.plus] : [])];
const disjoint = r => { const all=boxes(r); all.forEach((a,i)=>all.slice(i+1).forEach(b=>assert.ok(!overlap(a,b),JSON.stringify([a,b])))); };
const channels = Array.from({length:10},(_,i)=>({ name:`CH${i+1}`,visible:true,position:0,scale:1,unit:'V',color:'#12abef',time_offset:0 }));
const row = { l:84,t:8,w:800,h:200,index:0,names:channels.map(c=>c.name) };
const state = { channels:channels.slice(0,4),selected:'CH1',view:{t0:0,t1:10} };
const geom = (s,n=1,h=400,w=1000) => withGrids(layoutRect(w,h),{n,assign:{}},s.channels);
const layout = (s=state,extra={},r=geom(s)) => plotLayout(s,r,t=>r.l+t*10,measure,extra);
// 1：把手形狀／序號、越界指示、原名 title。
assert.deepEqual(channelHandles(channels,row).map(b=>b.label),['●1','▲2','■3','◆4','●5','▲6','■7','◆8','●9','▲10']);
for (const position of [-8,8]) assert.ok(channelHandles(channels.map(c=>({...c,position})),row).every(b=>b.label.endsWith(position>0?'▲':'▼') && b.title===b.name));
// 2–3：標籤跟真實零位；同零位與不同零位都避讓。
const hs=channelHandles(state.channels,geom(state)), first=layout()[0];
assert.equal(new Set(hs.map(b=>b.y)).size,4); assert.equal(first.labels[0].y+8,hs[0].anchorY); disjoint(first);
const different={...state,channels:state.channels.map((c,i)=>({...c,position:i-2}))}; layout(different).forEach(disjoint);
// 4–6：選取先放且不收合、+N 預留、長名稱截短而保留單位。
const crowded={...state,selected:'CH8',channels:channels.slice(0,8).map(c=>({...c,alias:'很長的波形顯示名稱'.repeat(6)}))};
const compact=layout(crowded,{},geom(crowded,1,140,650))[0];
assert.equal(compact.labels[0].name,'CH8'); assert.ok(compact.plus); disjoint(compact);
assert.ok(compact.plus.title.includes(crowded.channels[0].alias));
assert.ok(compact.labels.every(b=>b.w<=220 && b.display.endsWith('…') && b.text.endsWith('1 V/格')));
assert.ok(compact.labels.at(-1).x+compact.labels.at(-1).w+measure('+9')+8 <= compact.row.l+compact.row.w*.5);
// 狹窄半格要先扣除 +N 的寬度，再截短選取標籤。
const narrow=layoutRow({ ...row,w:240 },{measure,selected:'A',labels:['A','B'].map(name=>({name,display:'長名稱'.repeat(20),shape:'●',scale:'1 V/格',anchorY:50}))});
assert.ok(narrow.labels[0].w <= 240*.5-8-(measure('+9')+8));
// 選取標籤的保底候選也須計算 Y 讀值的重疊面積。
const fallback=layoutRow({ ...row,w:100,h:34 },{measure,selected:'A',readouts:[{y:row.t,text:'123456789012',color:'#fff'}],labels:[{name:'A',display:'x',shape:'●',scale:'1 V/格',anchorY:row.t+8}]});
assert.ok(fallback.labels.length); assert.ok(!overlap(fallback.labels[0],fallback.readouts[0]));
// 7–8：底緣 ▲ 與整圖頂部 X 游標是固定障礙。
const bottom={...state,channels:[{...channels[0],position:-4.5}]}, br=geom(bottom);
const mark={x:br.l+10,row:br.rows[0]}, bm=layout(bottom,{marks:[mark]},br)[0];
assert.ok(bm.labels.every(b=>!bm.fixed.some(f=>overlap(b,f))));
const top={...bottom,channels:[{...channels[0],position:5}]}, tr=geom(top);
const tx={x:tr.l+10,y:tr.t+2,w:14,h:14,text:'t1'};
assert.ok(layout(top,{xTexts:[tx]},tr)[0].labels.every(b=>!overlap(b,tx)));
// 9：Y 讀值靠右、貼底、與邊緣提示及另一讀值分離。
const readout=(y,text='v1 1.23 V')=>({y,text,color:'#fff'});
let rr=layoutRow(row,{measure,readouts:[readout(row.t+row.h)]});
assert.equal(rr.readouts[0].x+rr.readouts[0].w,row.l+row.w-4);
assert.ok(rr.readouts[0].y+14<=row.t+row.h);
const edge={x:row.l+row.w-52,y:row.t+row.h-24,w:52,h:24};
rr=layoutRow(row,{measure,fixed:[edge],readouts:[readout(194),readout(189,'v2 1.2 V')]}); disjoint(rr);
assert.ok(rr.readouts.every(b=>!overlap(b,edge) && b.y>=row.t && b.y+b.h<=row.t+row.h));
// 10–11：真 save/restore 假畫筆記錄透明度、底色、描邊與對齊。
const paints=[],stack=[];
const g=new Proxy({globalAlpha:.8,textAlign:'center',textBaseline:'bottom'}, {get(t,k){
  if(k==='save') return ()=>stack.push({...t});
  if(k==='restore') return ()=>{Object.keys(t).forEach(k=>delete t[k]);Object.assign(t,stack.pop());};
  if(k==='measureText') return t=>({width:measure(t)});
  if(['fill','fillRect','fillText','strokeText'].includes(k)) return (...args)=>paints.push({op:k,args,...t});
  return t[k] ?? (()=>{});
}});
const before={...g}; drawLayout(g,[rr]); assert.deepEqual({...g},before); assert.equal(stack.length,0);
assert.ok(paints.filter(p=>p.op==='fillText').every(p=>p.textAlign==='right'));
for(const bg of Object.keys(LABEL_BGS)) {
  paints.length=0; const r=layout({...bottom,channels:[{...channels[0],labelBg:bg}]}); drawLayout(g,r);
  if(bg==='none') { assert.ok(!paints.some(p=>p.op==='fill'||p.op==='fillRect')); assert.ok(paints.some(p=>p.op==='strokeText'&&p.lineWidth===3)); }
  if(bg==='solid') assert.ok(paints.some(p=>p.op==='fillText'&&p.fillStyle==='#000'));
  if(bg==='tint') assert.ok(paints.some(p=>p.op==='fill'&&p.fillStyle==='#12abef'&&p.globalAlpha===.25));
}
// 12：命中／hover、隱藏、分格與主圖／報告接線。
assert.equal(hitLabel([first],first.labels[0].x+2,first.labels[0].y+2)?.name,'CH1'); assert.equal(hitLabel([first],0,0),null);
paints.length=0; drawLayout(g,[first],'CH1'); assert.ok(paints.some(p=>p.op==='fillText'&&p.args[0]===first.labels[0].text&&p.globalAlpha===.15)); assert.ok(paints.some(p=>p.op==='fillText'&&p.args[0]===first.labels[1].text&&p.globalAlpha===1));
for(const n of [2,4,8]) for(const r of layout({...state,channels:channels.map((c,i)=>({...c,visible:i!==3}))},{},geom({...state,channels},n))) {
  assert.ok(r.labels.every(b=>b.name!=='CH4')); for(const b of boxes(r)) assert.ok(b.x>=r.row.l && b.x+b.w<=r.row.l+r.row.w && b.y>=r.row.t && b.y+b.h<=r.row.t+r.row.h);
}
function element(tag='div') { return {style:{},dataset:{},listeners:{},width:1000,height:400,
  addEventListener(k,fn){(this.listeners[k]??=[]).push(fn);},removeEventListener(){},
  dispatchEvent(e){for(const fn of this.listeners[e.type]??[]) fn(e);this['on'+e.type]?.(e);return true;},
  append(c){this.child=c;},getContext:()=>g,getBoundingClientRect:()=>({width:1000,height:400,left:0,top:0}),toDataURL:()=> 'data:image/png;base64,AA' }; }
globalThis.document={createElement:element,querySelectorAll:()=>[]}; globalThis.window={devicePixelRatio:1,addEventListener(){},removeEventListener(){}};
globalThis.ResizeObserver=class{observe(){} disconnect(){}};
const store=createStore(); store.set({...state,file:{path:'x.csv',info:[],gen:1,channels:[]},measurements:[]});
const host=element(), mounted=mount(host,{store,bridge:{},ui:{toast(){}}}), cv=host.child;
await new Promise(resolve=>setTimeout(resolve,0));
const label=cv.labelLayout()[0].labels[0]; paints.length=0;
cv.dispatchEvent({type:'pointermove',clientX:label.x+2,clientY:label.y+2}); assert.match(cv.title,/CH1/); assert.ok(paints.some(p=>p.globalAlpha===.15));
paints.length=0;cv.dispatchEvent(new Event('pointerleave')); assert.equal(cv.title,''); assert.ok(!paints.some(p=>p.globalAlpha===.15));
cv.dispatchEvent({type:'pointermove',clientX:label.x+2,clientY:label.y+2}); let leaves=0;cv.addEventListener('pointerleave',()=>leaves++);
await collectReport({store,fmt},{querySelector:s=>s==='.analysis__main canvas'?cv:null},{title:'測試',invert:false});
assert.equal(leaves,1); assert.equal(cv.title,'');
assert.ok(!paints.some(p=>p.op==='fillText' && p.args[0]==='CH1 · 1 V/格')); mounted.dispose();
console.log('chanlabels self-check OK：1–12 配置／底色／把手／hover／報告清理');
