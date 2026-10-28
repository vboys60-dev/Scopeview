// HTML 報告自檢：escape、區塊省略與重新編號、亮度反轉數值。
import assert from 'node:assert/strict';
import { buildReport, esc, invertPixels } from './report.js';

assert.equal(esc(`<b a="1">&'`), '&lt;b a=&quot;1&quot;&gt;&amp;&#39;');
const png = 'data:image/png;base64,AAAA';
const html = buildReport({ title: '<script>x</script>', time: '2026-10-26 14:35:12', note: 'a<b', info: [['DUT', '"U17"'], ['來源檔', 'C:\\d\\w.h5']],
  sections: [
    { title: '波形', img: png, caption: 'CH1 1 V/div' },
    { title: '量測結果', tables: [] },                                   // 無量測 → 省略
    { title: '游標', tables: [{ head: ['Marker'], rows: [] }] },          // 只有表頭 → 省略
    { title: 'Marker', tables: [{ head: ['#', '註記'], rows: [['M1', '<img src=x onerror=1>']] }] },
    { title: '壞圖', img: 'javascript:alert(1)' },                         // 非 PNG data URI → 整段省略
  ] });
assert.ok(!html.includes('<script>') && html.includes('&lt;script&gt;x&lt;/script&gt;'));
assert.ok(!html.includes('<img src=x') && html.includes('&lt;img src=x onerror=1&gt;'));
assert.ok(html.includes('&quot;U17&quot;') && html.includes('a&lt;b') && !/https?:\/\//.test(html));
assert.deepEqual([...html.matchAll(/<h2><i>(\d+)<\/i>([^<]+)/g)].map((m) => m[1] + m[2]), ['01波形', '02Marker']);
assert.equal((html.match(/<img /g) ?? []).length, 1);
assert.ok(!buildReport({ title: 't', time: '', sections: [] }).includes('class="remark"'));

// L→1−L：黑→白、白→黑、灰不變；#F0E442 → (189,177,15)；色相保留（R≥G≥B 順序不變）
const px = invertPixels(new Uint8ClampedArray([0, 0, 0, 255, 255, 255, 255, 255, 128, 128, 128, 7, 240, 228, 66, 255]));
assert.deepEqual([...px], [255, 255, 255, 255, 0, 0, 0, 255, 127, 127, 127, 7, 189, 177, 15, 255]);
console.log('report self-check OK');

// P4：直接從有效解碼快照建報告，不依賴分頁是否顯示。
const { decodeSection, collectReport, exportReport } = await import('./report.js');
const { createStore } = await import('./store.js');
const F = (v,u) => `${v} ${u}`, root = { querySelector:() => null };
const frame = { i:0,t0:0,t1:1,kind:'private_write',addr:8,rw:0,status:'ok',reasons:[],label:'"'.repeat(65),fields:[] };
const decoded = { summary:{ ok:true,gen:1,channels:{ scl:'CH1',sda:'CH2' },thresholds:{ scl:[.5,1],sda:[.5,1] },truncated:true },
  frames:Array.from({ length:2001 },(_,i) => ({ ...frame,i })),base:'CH1',protocol:'i3c',stale:false,
  addresses:Array.from({ length:257 },() => ({ da:8,pid:0x123456789ABC,bcr:6,dcr:68,t_from:null,t_to:null,how:'observed',note:'待確認' })) };
const store = createStore(); store.set({ file:{ gen:1,path:'/tmp/波形.csv',info:[] },channels:[{ name:'CH1',time_offset:2 }],decodeResult:decoded });
globalThis.document = { querySelectorAll:() => [] };
for (const r of [null,{ ...decoded,stale:true },{ ...decoded,summary:{ ...decoded.summary,gen:2 } }]) {
  store.set({ decodeResult:r });
  const report = await collectReport({ store,fmt:{ fmt:F } },root,{ title:'測試' });
  assert.ok(!report.sections.some(s => s.title === '解碼（I3C）'));
}
store.set({ decodeResult:decoded });
const report = await collectReport({ store,fmt:{ fmt:F } },root,{ title:'壓力測試' });
const section = report.sections.find(s => s.title === '解碼（I3C）');
assert.equal(section.img,null); assert.equal(section.tables[0].rows.length,2000); assert.equal(section.tables[1].rows.length,256);
assert.equal(section.tables[0].rows[0][5],'"'.repeat(64)+'…'); assert.equal(section.tables[0].rows[0][1],'2 s');
assert.match(section.caption,/CSV 含全部/); assert.match(section.caption,/解碼達上限/);
const filterRoot = { querySelector:s => s.includes('button') ? { getAttribute:() => 'true' } : null };
assert.equal(decodeSection(store.get(),filterRoot,F,false)[0].tables[0].rows.length,0);
// 重新顯示時 hidden 已解除，但 ResizeObserver 排定的 fit／重畫尚未執行。
const { createCanvas } = await import('./plotcore.js');
const savedDocument = globalThis.document;
let resized, painted = false;
globalThis.window = { devicePixelRatio:1 };
globalThis.requestAnimationFrame = cb => { queueMicrotask(cb); return 1; };
globalThis.ResizeObserver = class { constructor(cb) { resized = cb; } observe() {} disconnect() {} };
const source = { style:{},getContext:() => ({ setTransform() {} }) };
const band = { hidden:true,append() {},querySelector:() => source,
  getBoundingClientRect() { return { width:this.hidden ? 0 : 1400,height:this.hidden ? 0 : 80 }; } };
globalThis.document = { ...savedDocument,createElement:() => source };
const cv = createCanvas(band,() => { painted = true; });
await Promise.resolve();
assert.equal(source.width,0);
band.hidden = false; resized();
const bandRoot = { querySelector:s => s === '.analysis__decodeband' ? band : null };
assert.equal(decodeSection(store.get(),bandRoot,F,false)[0].img,null);
globalThis.document.createElement = () => ({ getContext:() => ({ drawImage(src) { assert.equal(src,source); assert.ok(painted); assert.equal(src.height,80); } }),toDataURL() { assert.equal(this.height,80); return png; } });
const visibleReport = await collectReport({ store,fmt:{ fmt:F } },bandRoot,{ title:'重新顯示' });
assert.ok(buildReport(visibleReport).includes('alt="解碼（I3C）"'));
band.hidden = true;
assert.equal(decodeSection(store.get(),bandRoot,F,false)[0].img,null);
cv.dispose(); globalThis.document = savedDocument;
delete globalThis.window; delete globalThis.requestAnimationFrame; delete globalThis.ResizeObserver;
// 標準庫產生有效 PNG：1400×80 高熵 RGBA（比實際標註圖更難壓縮）。
const { deflateSync } = await import('node:zlib');
const crc = b => { let c = -1; for (const v of b) { c ^= v; for (let i=0;i<8;i++) c = (c>>>1)^((c&1) ? 0xEDB88320 : 0); } return (c^-1)>>>0; };
function noisePng(w,h) {
  const chunk = (name,data) => { const type = Buffer.from(name), n = Buffer.alloc(4), sum = Buffer.alloc(4); n.writeUInt32BE(data.length); sum.writeUInt32BE(crc(Buffer.concat([type,data]))); return Buffer.concat([n,type,data,sum]); };
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(w); ihdr.writeUInt32BE(h,4); ihdr[8]=8; ihdr[9]=6;
  const raw = Buffer.alloc((w*4+1)*h); let seed=19;
  for (let y=0;y<h;y++) for (let x=1;x<=w*4;x++) { seed ^= seed<<13; seed ^= seed>>>17; seed ^= seed<<5; raw[y*(w*4+1)+x]=seed&255; }
  return 'data:image/png;base64,'+Buffer.concat([Buffer.from([137,80,78,71,13,10,26,10]),chunk('IHDR',ihdr),chunk('IDAT',deflateSync(raw)),chunk('IEND',Buffer.alloc(0))]).toString('base64');
}
section.img = noisePng(1400,80);
report.sections[0].img = noisePng(1400,400);
report.sections.push({ title:'FFT 頻譜',img:noisePng(1400,400) });
const body = { html:buildReport(report),directory:null };
const bytes = new TextEncoder().encode(JSON.stringify(body)).length;
assert.ok(bytes < 8_000_000,`完整 export_report 請求 ${bytes} bytes`);
console.log(`report P4 最壞資料：${bytes} bytes < 8 MB`);
// collectReport 的 await 期間替換 decodeResult：送 RPC 前必須攔下。
const toasts = [], calls = [], ctx = { store,fmt:{ fmt:F },bridge:{ call:async (...a) => { calls.push(a); return { path:'/tmp/report.html' }; } },ui:{ pickPath:async () => '/out',toast:(...a) => toasts.push(a),showError:e => { throw e; } } };
const modal = async () => { queueMicrotask(() => queueMicrotask(() => store.set({ decodeResult:{ ...decoded,stale:true } }))); return { title:'測試' }; };
await exportReport(ctx,root,modal);
assert.equal(calls.length,0); assert.match(toasts.at(-1)[0],/解碼結果已變更/);
store.set({ decodeResult:decoded });
await exportReport(ctx,root,async () => ({ title:'測試' }));
assert.equal(calls.length,1); assert.match(calls[0][1].html,/解碼（I3C）/); assert.equal(calls[0][1].directory,'/out');
// 選資料夾期間改 view（任一報告用到的鍵）：同樣攔下。
await exportReport({ ...ctx,ui:{ ...ctx.ui,pickPath:async () => { store.set({ view:{ t0:1,t1:2 } }); return '/out'; } } },root,async () => ({ title:'測試' }));
assert.equal(calls.length,1); assert.match(toasts.at(-1)[0],/已變更/);
// 主圖包絡在途（dataset.pending）：逾時以 REPORT_BUSY 中止；載入完成則正常收集。
globalThis.requestAnimationFrame = cb => { setTimeout(cb,5); return 1; };
const main = { dataset:{ pending:'1' },width:0 }, mainRoot = { querySelector:s => s === '.analysis__main canvas' ? main : null };
await assert.rejects(collectReport({ store,fmt:{ fmt:F } },mainRoot,{ title:'t' },{ pendingMs:50 }),{ code:'REPORT_BUSY' });
setTimeout(() => { main.dataset.pending = ''; },20);
assert.equal((await collectReport({ store,fmt:{ fmt:F } },mainRoot,{ title:'t' },{ pendingMs:1000 })).title,'t');
await exportReport(ctx,mainRoot,async () => { main.dataset.pending = '1'; return { title:'測試' }; });
assert.equal(calls.length,1); assert.match(toasts.at(-1)[0],/尚未載入完成/);
delete globalThis.requestAnimationFrame;
console.log('report P4 self-check OK');
