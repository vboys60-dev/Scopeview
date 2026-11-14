// L8：浮動純函式、同節點搬移、Pointer Capture 與暫存變異。
import assert from 'node:assert/strict';
import { cpSync,mkdtempSync,readFileSync,writeFileSync,rmSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { tmpdir } from 'node:os';
import { join,dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import * as M from './floatpanel_math.js';
import { mountFloat } from './floatpanel.js';
import { bindLayoutCommands } from './tab_analysis.js';
import { clampLayout,defaults as layoutDefaults } from './layout.js';
import { createStore } from './store.js';
import { mount as mountResults } from './results.js';
import { useTabs } from './bpanel.js';
assert.equal(M.canFloat(899),false); assert.equal(M.canFloat(900),true); assert.equal(M.canFloat(NaN),false);
assert.deepEqual(M.validatePrefs({version:2,floating:true}),M.defaults());
assert.equal(M.validatePrefs({version:1,floating:'true',width:NaN}).floating,false);
assert.equal(M.validatePrefs({version:1,width:10,height:-5}).width,360);
assert.equal(M.validatePrefs({version:1,height:10}).height,160);
assert.equal(M.validatePrefs({version:1,x:Infinity}).x,80);
const r={x:100,y:100,width:500,height:250};
assert.deepEqual(M.clampRect({...r,x:-20,y:900},1000,600),{...r,x:0,y:350});
assert.deepEqual(M.clampRect({...r,width:5000,height:900},1000,600),{x:0,y:0,width:1000,height:600});
assert.deepEqual(M.clampRect(r,200,100),{x:0,y:0,width:200,height:100});
assert.deepEqual(M.keyboardRect(r,{key:'ArrowRight'},1400,900),{...r,x:110});
assert.deepEqual(M.keyboardRect(r,{key:'ArrowUp',shiftKey:true},1400,900),{...r,y:50});
assert.deepEqual(M.keyboardRect(r,{key:'ArrowDown',altKey:true},1400,900),{...r,height:260});
assert.deepEqual(M.keyboardRect(r,{key:'ArrowLeft',altKey:true,shiftKey:true},1400,900),{...r,width:450});
assert.equal(M.keyboardRect(r,{key:'Escape'},1400,900),null);
assert.deepEqual(M.resizeRect(r,'se',30,40,1400,900),{...r,width:530,height:290});
assert.deepEqual(M.resizeRect(r,'nw',30,40,1400,900),{x:130,y:140,width:470,height:210});
assert.deepEqual(M.resizeRect(r,'nw',900,900,1400,900),{x:240,y:190,width:360,height:160});
assert.deepEqual(M.resizeRect(r,'se',9000,9000,1000,600),{...r,width:900,height:500});
const denied=()=>{throw Error('無儲存空間');};
M.savePrefs({...M.defaults(),floating:true,x:300},denied); assert.equal(M.loadPrefs(denied).x,300);
assert.equal(M.loadPrefs(()=>({getItem:()=>'{'})).version,1);
const prefs={...layoutDefaults(),lower:180,lowerCollapsed:false};
const args={W:1360,H:700,vw:1360,vh:860,prefs,fftOn:false};
const normal=clampLayout(args),floated=clampLayout({...args,lowerFloating:true});
assert.equal(floated.lower,28); assert.equal(floated.lowerCollapsed,true); assert.ok(floated.main>normal.main); assert.equal(prefs.lowerCollapsed,false);
assert.equal(useTabs(819,300),true); assert.equal(useTabs(960,160),false);
class Element {
  constructor(tag='div') { this.tagName=tag;this.children=[];this.listeners={};this.style={};this.attrs={};this.dataset={};this.hidden=false;this.clientWidth=960;this.clientHeight=300;this.classList={add:()=>{}}; }
  append(...nodes) { for(const n of nodes) {n.remove();this.children.push(n);n.parentNode=this;} }
  replaceChildren(...nodes) {for(const n of [...this.children]) n.remove();this.append(...nodes);}
  remove() { if(this.parentNode) this.parentNode.children=this.parentNode.children.filter(n=>n!==this); }
  insertBefore(n,b) {n.remove();this.children.splice(this.children.indexOf(b),0,n);n.parentNode=this;}
  setAttribute(k,v) {this.attrs[k]=v;}
  addEventListener(k,fn) {(this.listeners[k]??=[]).push(fn);}
  fire(k,extra={}) {const e={target:this,button:0,pointerId:1,clientX:100,clientY:100,preventDefault(){this.prevented=true;},stopPropagation(){this.stopped=true;},...extra}; for(const fn of this.listeners[k]??[])fn(e);return e;}
  getBoundingClientRect() {return {top:0,bottom:28,right:100,height:160};}
  focus() {document.activeElement=this;}
  setPointerCapture(id) {this.capture=id;}
  hasPointerCapture(id) {return this.capture===id;}
  releasePointerCapture() {this.capture=null;}
}
globalThis.document={createElement:t=>new Element(t)};globalThis.window=new Element();globalThis.innerWidth=1400;globalThis.innerHeight=900;
const source=readFileSync(new URL('./tab_analysis.js',import.meta.url),'utf8');
const update=source.match(/resultTabs\.update\(([^;]+)\);/)[1];
let received;
Function('resultTabs','floating','lowerBody','e','store','fftOn',`resultTabs.update(${update});`)(
  {update:p=>received=p},{width:480,height:230,collapsed:false},{clientWidth:700},
  {lower:28,lowerCollapsed:true},{get:()=>({})},false);
assert.equal(received.width,480);assert.equal(received.height,230);assert.equal(received.lowerCollapsed,false);
const compute=source.match(/effective = (clampLayout\([^;]+\));/)[1];
let layoutArgs;
Function('clampLayout','root','H','innerWidth','innerHeight','controller','floating','fftOn','chrome','activeTab',`return ${compute};`)(
  p=>layoutArgs=p,{clientWidth:1300},700,1400,900,{prefs,drawerOpen:false},{width:480},false,56,'wave');
assert.equal(layoutArgs.lowerFloating,true);
const layoutStore=createStore();let locked=true;
const layoutCtl=bindLayoutCommands(layoutStore,{initial:prefs,persist(){},schedule(){},lowerLocked:()=>locked});
layoutCtl.update(floated);layoutStore.command('layout.toggle','lower');assert.equal(layoutCtl.prefs.lowerCollapsed,false);
layoutStore.command('layout.resize',{kind:'lower',value:300});assert.equal(layoutCtl.prefs.lower,180);
locked=false;layoutStore.command('layout.resize',{kind:'lower',value:300});assert.equal(layoutCtl.prefs.lower,300);
const store=createStore(),page=new Element(),lower=new Element(),header=new Element(),body=new Element(),tabs=new Element(),actions=new Element();
page.append(lower);lower.append(header,body);header.append(tabs,actions);tabs.selection='cursor';body.state={marker:42};
let saved,writes=0;const ctl=mountFloat(page,{store,lower,header,body,tabs,actions,schedule(){},initial:{...M.defaults(),...r},persist:p=>{saved={...p};writes++;}});
const panel=page.children[1],title=panel.children[0],bar=panel.children[1],launch=header.children[2];
assert.equal(writes,0);
assert.equal(panel.attrs.role,'dialog');assert.equal(panel.attrs['aria-label'],'量測資訊（浮動）');assert.equal(panel.attrs['aria-modal'],'false');assert.equal(title.tabIndex,0);
launch.onclick();assert.equal(document.activeElement,title);assert.equal(title.attrs['aria-describedby'],'analysis-float-help');ctl.update();assert.equal(header.tabIndex,-1);assert.equal(header.attrs['aria-disabled'],'true');assert.equal(ctl.floating,true);assert.equal(saved.floating,true);assert.equal(body.parentNode,panel);assert.equal(tabs.parentNode,bar);assert.equal(actions.parentNode,bar);
assert.equal(tabs.selection,'cursor');assert.equal(body.state.marker,42);assert.equal(ctl.update().width,960);
assert.equal(panel.fire('pointerdown').stopped,true);assert.equal(panel.fire('wheel').stopped,true);
assert.equal(panel.fire('keydown').stopped,undefined);assert.equal(panel.fire('keyup').stopped,undefined);
const beforeDragWrites=writes;
title.fire('pointerdown');assert.equal(title.capture,1);
panel.fire('pointermove',{clientX:160,clientY:140});assert.equal(panel.style.left,'160px');assert.equal(panel.style.top,'140px');
assert.equal(writes,beforeDragWrites);panel.fire('pointerup');assert.equal(writes,beforeDragWrites+1);assert.equal(title.capture,null);
title.fire('keydown',{key:'ArrowLeft',shiftKey:true});assert.equal(panel.style.left,'110px');
title.fire('keydown',{key:'ArrowRight',altKey:true});assert.equal(panel.style.width,'510px');
assert.equal(writes,beforeDragWrites+1);title.fire('keyup',{key:'ArrowRight'});assert.equal(writes,beforeDragWrites+2);
const grip=panel.children.find(n=>n.dataset.edge==='se');grip.fire('pointerdown');assert.equal(grip.capture,1);
panel.fire('pointermove',{clientX:200,clientY:180});assert.equal(panel.style.width,'610px');assert.equal(panel.style.height,'330px');panel.fire('pointerup');
store.command('layout.float.collapse');assert.equal(body.hidden,true);assert.equal(panel.style.height,'28px');
const foldedWrites=writes;grip.fire('pointerdown');assert.equal(grip.capture,null);
title.fire('keydown',{key:'ArrowDown',altKey:true});title.fire('keyup',{key:'ArrowDown'});assert.equal(writes,foldedWrites);
store.command('layout.float.collapse');assert.equal(body.hidden,false);
title.fire('keydown',{key:'Escape'});assert.equal(ctl.floating,true);
store.command('tab.activated','capture');assert.equal(ctl.floating,true);
title.fire('dblclick');assert.equal(document.activeElement,launch);assert.equal(ctl.floating,false);assert.equal(body.parentNode,lower);assert.equal(tabs.parentNode,header);assert.equal(actions.parentNode,header);assert.equal(panel.hidden,true);
launch.onclick();
const stable={...saved},stableWrites=writes;
for(const key of ['ArrowLeft','ArrowDown']) {title.fire('keydown',{key,ctrlKey:true});title.fire('keyup',{key});}
assert.deepEqual(saved,stable);assert.equal(writes,stableWrites);
for(const stop of ['pointercancel','lostpointercapture','blur','resize','tab']) {
  title.fire('pointerdown');panel.fire('pointermove',{clientX:125,clientY:135});
  assert.equal(writes,stableWrites);
  if(stop==='tab') store.command('tab.activated','capture');
  else (['blur','resize'].includes(stop) ? window : panel).fire(stop);
  assert.equal(title.capture,null);assert.equal(panel.style.left,stable.x+'px');
  panel.fire('pointermove',{clientX:160,clientY:180});panel.fire('pointerup');
  assert.equal(writes,stableWrites);assert.deepEqual(saved,stable);
}
const fold=title.children[2];
title.fire('pointerdown',{target:fold});assert.equal(title.capture,null);
title.fire('dblclick',{target:fold});assert.equal(ctl.floating,true);
page.getBoundingClientRect=()=>({top:72});
store.command('layout.float.rect',{x:800,y:500,width:550,height:350});
const original={...saved},originalWrites=writes;
globalThis.innerWidth=1000;globalThis.innerHeight=400;window.fire('resize');
assert.equal(panel.style.top,'72px');assert.equal(panel.style.height,'328px');
assert.deepEqual(saved,original);assert.equal(writes,originalWrites);
globalThis.innerWidth=899;window.fire('resize');assert.equal(ctl.floating,false);ctl.update();assert.equal(launch.disabled,true);
assert.equal(saved.floating,true);assert.equal(writes,originalWrites);
globalThis.innerWidth=1400;globalThis.innerHeight=900;window.fire('resize');
assert.equal(ctl.floating,true);assert.equal(panel.style.top,'500px');assert.equal(panel.style.left,'800px');
assert.equal(panel.style.width,'550px');assert.equal(panel.style.height,'350px');assert.equal(writes,originalWrites);
// 啟動即窄版仍保留浮動偏好，變寬後還原。
globalThis.innerWidth=899;
const narrowStore=createStore(),narrowPage=new Element(),narrowLower=new Element(),narrowHeader=new Element();
let narrowWrites=0;
const narrow=mountFloat(narrowPage,{store:narrowStore,lower:narrowLower,header:narrowHeader,body:new Element(),tabs:new Element(),actions:new Element(),schedule(){},initial:original,persist(){narrowWrites++;}});
assert.equal(narrow.floating,false);assert.equal(narrowWrites,0);
globalThis.innerWidth=1400;window.fire('resize');assert.equal(narrow.floating,true);assert.equal(narrowWrites,0);
assert.deepEqual(M.clampRect({...r,y:0,height:900},1000,600,72),{x:100,y:72,width:500,height:528});
assert.equal(M.keyboardRect(r,{key:'ArrowRight',ctrlKey:true},1400,900),null);
// 真正 results 掛載：浮動預設全欄、獨立欄位選擇、停靠復原原欄位。
const resultHost=new Element(),resultActions=new Element(),peaks=new Element();
mountResults(resultHost,{store,bridge:{},ui:{},fmt:{fmt:String},resultActions,fftPeaks:peaks});
const table=resultHost.children[0],dockColumns=table.children[0].children.length;
store.command('layout.float.state',true);assert.equal(table.children[0].children.length,9);
const boxes=resultActions.children[0].children[1].children.map(label=>label.children[0]);
assert.ok(boxes.every(box=>box.checked));boxes[0].checked=false;boxes[0].onchange();assert.equal(table.children[0].children.length,8);
store.command('layout.float.state',false);assert.equal(table.children[0].children.length,dockColumns);
store.command('layout.float.state',true);assert.equal(table.children[0].children.length,8);
const menu=resultActions.children[0],choices=menu.children[1];choices.fire('toggle',{newState:'open'});assert.equal(choices.style.top,'28px');
console.log('float self-check OK');
if(process.argv.includes('--mutations')) {
  const root=dirname(dirname(fileURLToPath(import.meta.url)));
  const mutations=[
    ['tab_analysis.js','lowerFloating:!!floating','lowerFloating:false'],
    ['tab_analysis.js','width:floating?.width ?? lowerBody.clientWidth','width:lowerBody.clientWidth'],
    ['tab_analysis.js',"&& !(kind === 'lower' && lowerLocked())",''],
    ['results.js','r.top >= height ? r.top-height : r.bottom','r.top-height'],
    ['results.js','floating ? floatColumns : prefs.columns','false ? floatColumns : prefs.columns'],
    ['floatpanel_math.js','width >= 900','width >= 899'],
    ['floatpanel_math.js','raw.version !== 1','raw.version !== 2'],
    ['floatpanel_math.js','Math.max(360,p.width)','Math.max(160,p.width)'],
    ['floatpanel_math.js','Math.max(160,p.height)','Math.max(360,p.height)'],
    ['floatpanel_math.js','Math.min(W,p.width)','p.width'],
    ['floatpanel_math.js','Math.min(H-top,p.height)','p.height'],
    ['floatpanel_math.js','event.shiftKey ? 50 : 10','event.shiftKey ? 10 : 50'],
    ['floatpanel_math.js','event.altKey ?','!event.altKey ?'],
    ['floatpanel_math.js','right-360','right-160'],
    ['layout.js','lowerFloating ||','false ||'],
    ['floatpanel.js','bar.append(tabs,actions)','bar.append(tabs)'],
    ['floatpanel.js','lower.append(body)','panel.append(body)'],
    ['floatpanel.js','host.setPointerCapture(e.pointerId)','host.setPointerCapture(99)'],
    ['floatpanel.js',"e.stopPropagation());\n  window", "(()=>{})());\n  window"],
    ['floatpanel.js',"title.tabIndex=0","title.tabIndex=-1"],
    ['floatpanel.js','setFloating(prefs.floating);','setFloating(false);'],
    ['floatpanel.js','if(on) draw(); schedule();','prefs={...prefs,floating:on}; persist(prefs); if(on) draw(); schedule();'],
    ['floatpanel.js',"'dblclick','wheel']","'dblclick','wheel','keydown','keyup']"],
    ['floatpanel.js','preview=clamp(drag.edge','persist(prefs); preview=clamp(drag.edge'],
    ['floatpanel.js','if(commit && preview)','if(preview)'],
    ['floatpanel.js',"['pointercancel','lostpointercapture']","['pointercancel']"],
    ['floatpanel.js',"['pointercancel','lostpointercapture']","['lostpointercapture']"],
    ['floatpanel.js',"window.addEventListener('blur',()=>end())","window.addEventListener('blur',()=>{})"],
    ['floatpanel.js','end(); setFloating(prefs.floating);','setFloating(prefs.floating);'],
    ['floatpanel.js',"name=>{end(); if(name", "name=>{if(name"],
    ['floatpanel.js','(!edge && e.target!==title && e.target!==caption)','false'],
    ['floatpanel.js','if(e.target===title || e.target===caption)','if(true)'],
    ['floatpanel_math.js','event.ctrlKey || event.metaKey','false'],
    ['floatpanel.js','if(!collapsed) start','if(true) start'],
    ['floatpanel.js','(collapsed && e.altKey)','false'],
    ['floatpanel.js','(on ? title : launch).focus()','title.focus()'],
    ['floatpanel.js',"title.setAttribute('aria-describedby',help.id)","title.setAttribute('aria-label',help.id)"],
    ['floatpanel.js','header.tabIndex=floating ? -1 : 0','header.tabIndex=0'],
    ['floatpanel_math.js','y:clip(p.y,top,Math.max(top,H-height))','y:clip(p.y,0,Math.max(0,H-height))'],
    ['floatpanel_math.js','Math.min(H-top,p.height)','Math.min(H,p.height)'],
  ];
  for(const [file,from,to] of mutations) {
    const tmp=mkdtempSync(join(tmpdir(),'float-'));
    try {
      cpSync(root,join(tmp,'js'),{recursive:true});writeFileSync(join(tmp,'package.json'),'{"type":"module"}');
      const p=join(tmp,'js/analysis',file),source=readFileSync(p,'utf8');assert.ok(source.includes(from),from);writeFileSync(p,source.replace(from,to));
      const result=spawnSync(process.execPath,[join(tmp,'js/analysis/float_check.mjs')],{encoding:'utf8'});
      assert.notEqual(result.status,0,`變異未被抓到：${file} ${from}`);assert.match(result.stderr,/AssertionError/);
    } finally {rmSync(tmp,{recursive:true,force:true});}
  }
  console.log(`float mutations self-check OK（${mutations.length}/${mutations.length}）`);
}
