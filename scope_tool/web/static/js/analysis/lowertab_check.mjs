// L8：窄版 FFT 分頁（lowerTab）下 B 區標頭仍顯示，只停用拖曳與雙擊重設；▾ 仍可收折。
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { defaults } from './layout.js';
import { mountSplitter } from './splitter.js';
import { createStore } from './store.js';
import { bindLayoutCommands } from './tab_analysis.js';
function element() {
  return { listeners:{}, attrs:{}, style:{}, children:[], append(b) { this.children.push(b); },
    setAttribute(k,v) { this.attrs[k] = v; }, addEventListener(k,fn) { this.listeners[k] = fn; }, removeEventListener() {},
    getBoundingClientRect() { return { top:86,height:28 }; }, setPointerCapture() { this.captured = true; }, hasPointerCapture() { return this.captured; }, releasePointerCapture() { this.captured = false; } };
}
globalThis.window = element();
globalThis.requestAnimationFrame = () => 1; globalThis.cancelAnimationFrame = () => {};
const store = createStore(); let dragging = false;
const ctl = bindLayoutCommands(store,{ initial:{ ...defaults(),lower:200,lowerCollapsed:false },persist:() => {},schedule:() => {},dragging:(v) => { dragging = v; },viewport:() => 1000 });
ctl.update({ main:400,lower:200,lowerCollapsed:false,fft:200,fftCollapsed:false,tabbed:true,steps:['lowerTab'] });
assert.equal(ctl.state('lower').disabled,true);
const host = element(), button = element();
const api = mountSplitter(host,{ kind:'lower',button,store,getState:() => ctl.state('lower') });
api.update(ctl.state('lower'));
assert.equal(host.hidden,false,'lowerTab 下 B 區標頭不可隱藏');
assert.equal(host.attrs['data-resize'],'off'); assert.equal(host.tabIndex,-1);
const before = JSON.stringify(ctl.prefs);
host.listeners.pointerdown({ button:0,target:host,pointerId:1,clientY:100,preventDefault() {} }); assert.ok(!host.captured && !dragging,'不可開始拖曳');
host.listeners.dblclick({ target:host }); assert.equal(JSON.stringify(ctl.prefs),before,'雙擊不可重設偏好');
store.command('layout.resize',{ kind:'lower',value:300 }); assert.equal(JSON.stringify(ctl.prefs),before);
button.onclick(); assert.equal(ctl.prefs.lowerCollapsed,true,'▾ 在窄版仍可收折');
// FFT 分隔線維持原行為：停用時整條隱藏。
const fhost = element(); const fapi = mountSplitter(fhost,{ kind:'fft',button:element(),store,getState:() => ({ value:200,max:300,collapsed:false,disabled:true }) });
fapi.update({ value:200,max:300,collapsed:false,disabled:true }); assert.equal(fhost.hidden,true);
// 變異：還原任一修法都必須被上面斷言抓到。
if (process.argv.includes('--mutations')) {
  const dir = fileURLToPath(new URL('.',import.meta.url)), sp = readFileSync(dir+'splitter.js','utf8'), ta = readFileSync(dir+'tab_analysis.js','utf8');
  assert.ok(sp.includes("host.hidden = disabled && kind === 'fft'") && ta.includes("(kind === 'fft' && state(kind).disabled)"));
}
console.log('lowertab self-check OK：標頭顯示／拖曳與雙擊停用／▾ 可收折／FFT 線仍隱藏');
