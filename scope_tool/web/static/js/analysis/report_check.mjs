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
