import assert from 'node:assert/strict';
import { mount } from './chanbar.js';
import { createStore } from './store.js';
import { slotPatch } from './slots.js';
import { openPatch } from './tab_analysis.js';
import * as scales from './scales.js';
import * as fmt from '../fmt.js';
class Element {
  constructor(tag) { this.tagName=tag.toUpperCase(); this.children=[]; this.dataset={}; this.style={}; this.className=''; this.hidden=false; this.classList={add:()=>{},toggle:(n,on)=>{ const s=new Set(this.className.split(/\s+/)); on?s.add(n):s.delete(n); this.className=[...s].join(' '); }}; }
  setAttribute(k,v) { this[k]=v; }
  append(...nodes) { for(const n of nodes) { n.parent=this; this.children.push(n); } }
  replaceChildren(...nodes) { this.children.forEach(n=>n.parent=null); this.children=[]; this.append(...nodes); }
  after(n) { n.parent=this.parent; this.parent.children.splice(this.parent.children.indexOf(this)+1,0,n); }
  remove() { const p=this.parent; if(p) { p.children.splice(p.children.indexOf(this),1); this.parent=null; this.onblur?.(); } }
  querySelector(q) { const cls=q.slice(1); return this.children.flatMap(n=>[n,...n.descendants()]).find(n=>n.className.split(/\s+/).includes(cls)) ?? null; }
  descendants() { return this.children.flatMap(n=>[n,...n.descendants()]); }
  focus() { document.activeElement=this; } select() { this.wasSelected=true; } click() { this.clicks=(this.clicks??0)+1; this.onclick?.(event()); }
  closest(q) { return q.split(',').includes(this.tagName.toLowerCase()) ? this : null; }
}
const event=(extra={})=>({ stopped:false, prevented:false, stopPropagation(){this.stopped=true;}, preventDefault(){this.prevented=true;}, ...extra });
globalThis.document={createElement:t=>new Element(t),activeElement:null};
const store=createStore(), channels=['CH1','CH2'].map(name=>({name,unit:'V',visible:true,scale:1,position:0,color:'#ffffff'}));
store.set({file:{gen:1,channels},channels,selected:'CH1'});
const writes=[], update=store.updateChannel.bind(store); store.updateChannel=(...args)=>{writes.push(args); update(...args);};
const toasts=[], host=new Element('div'); mount(host,{store,fmt,scales,bridge:{},ui:{toast:(...a)=>toasts.push(a)}});
const chip=()=>host.children[1].children[0], name=()=>chip().querySelector('.chip__name'), input=()=>chip().querySelector('.chip__alias'), button=()=>chip().querySelector('.chip__alias-btn');
name().onclick(); assert.equal(store.get().selected,'CH1'); assert.equal(input(),null);
const color=chip().querySelector('.chip__color'); chip().ondblclick(event({target:name()})); assert.equal(color.clicks,1);
let e=event({key:'F2'}); name().onkeydown(e); assert.ok(e.prevented && input()?.wasSelected); assert.equal(input().placeholder,'CH1');
let field=input(); field.value='SDA'; e=event({key:'Enter',isComposing:true}); field.onkeydown(e); assert.ok(e.stopped); assert.equal(writes.length,0);
e=event({key:'Enter',keyCode:229}); field.onkeydown(e); assert.equal(writes.length,0);
for(const type of ['pointerdown','click','dblclick']) { e=event(); field['on'+type](e); assert.ok(e.stopped); }
e=event({key:'Enter',keyCode:13}); field.onkeydown(e); field.onblur(); assert.equal(writes.length,1); assert.equal(store.get().channels[0].alias,'SDA'); assert.equal(name().textContent,'●SDA');
assert.ok(chip().className.includes('chip--selected')); assert.equal(button().textContent,'✎');
button().onclick(event()); field=input(); field.value='cancel'; field.onkeydown(event({key:'Escape'})); assert.equal(writes.length,1);
button().onclick(event()); field=input(); field.value='CH2'; field.onblur(); assert.equal(writes.length,1); assert.equal(toasts.length,1); assert.equal(toasts[0][1],'error');
button().onclick(event()); field=input(); field.value='stale'; store.set({file:{...store.get().file,gen:2}}); field.onblur(); assert.equal(writes.length,1); assert.equal(toasts.length,1);
button().onclick(event()); field=input(); store.set({channels:[store.get().channels[1]]}); field.onblur(); assert.equal(writes.length,1);
const info={name:'Mem1.CH1',unit:'V',t0:0,t1:1,vmin:-1,vmax:1,points:10}, summary={gen:7,path:'/same',channels:[info],info:[],all:[]};
const old={...info,alias:'bus',labelBg:'solid',visible:true,scale:1,position:0,color:'#fff'}, st={file:{gen:7,channels:[info]},channels:[old],slots:[{slot:'Mem1',path:'/same',channels:[info.name]}]};
assert.equal(slotPatch(st,'Mem1',summary,['#fff'],scales).channels[0].alias,'bus');
const changed=slotPatch(st,'Mem1',{...summary,path:'/other'},['#fff'],scales).channels[0]; assert.equal(changed.alias,undefined); assert.equal(changed.labelBg,'solid');
const opened=openPatch({gen:8,channels:[info]},['#fff']).channels[0]; assert.equal(opened.alias,undefined); assert.equal(opened.labelBg,undefined);
console.log('alias chanbar self-check OK: 15, 16, 19');
