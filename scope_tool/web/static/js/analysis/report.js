// 離線分析 HTML 報告：buildReport 為純函式（資料 → 單一自包含 HTML 字串）；collectReport 從目前畫面的表格與 canvas 取資料（所見即所得）。
// 圖以 PNG data URI 內嵌、系統字型、不連網。區塊沒有資料就整段省略，編號依實際輸出重排。
import { fftInfo } from './fft_marker_table.js';
import { exportable } from './results.js';
import { tableFrames } from './decode_table.js';
import { definition, withAscii } from './decode.js';

const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
export const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ESC[c]);
const PNG = 'data:image/png;base64,';

/** 亮度反轉、保留色相與飽和度：各分量加上 255−(max+min)，即 L→1−L。原地修改 RGBA 陣列並回傳。 */
export function invertPixels(d) {
  for (let i = 0; i < d.length; i += 4) {
    const k = 255 - Math.max(d[i], d[i + 1], d[i + 2]) - Math.min(d[i], d[i + 1], d[i + 2]);
    d[i] += k; d[i + 1] += k; d[i + 2] += k;
  }
  return d;
}

const CSS = `:root{color-scheme:light;--ink:#1b2230;--ink2:#566074;--rule:#d7dce5;--rule2:#eef1f5;--accent:#1f4a8a;
--font:-apple-system,"PingFang TC","Microsoft JhengHei","Noto Sans TC",system-ui,sans-serif;--mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace}
*{box-sizing:border-box}body{margin:0;background:#fff;color:var(--ink);font:14px/1.6 var(--font)}
main{max-width:1000px;margin:0 auto;padding:40px clamp(16px,5vw,48px) 32px;display:grid;gap:28px}
header{display:grid;gap:14px;border-bottom:2px solid var(--ink);padding-bottom:16px}
.eyebrow{font-size:11px;letter-spacing:.16em;color:var(--ink2);display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap}
h1{margin:0;font-size:26px;line-height:1.25;text-wrap:balance}
dl{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:4px 28px;margin:0}
dl div{display:grid;grid-template-columns:5.5em 1fr;gap:8px;padding:3px 0;border-bottom:1px solid var(--rule2);min-width:0}
dt{color:var(--ink2);font-size:13px}dd{margin:0;font-size:13px;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}
.remark{background:#f6f8fb;border-left:3px solid var(--rule);padding:8px 12px;font-size:13px;white-space:pre-wrap}
section{display:grid;gap:10px;min-width:0;break-inside:avoid}
h2{margin:0;font-size:16px;display:flex;align-items:baseline;gap:10px}h2 i{font:normal 600 12px var(--mono);color:var(--accent)}
figure{margin:0;display:grid;gap:6px}img{width:100%;height:auto;display:block;border:1px solid var(--rule)}
figcaption,.cap{font:12px var(--mono);color:var(--ink2);overflow-wrap:anywhere;margin:0}
.tw{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:12.5px;font-variant-numeric:tabular-nums}
th,td{padding:5px 10px;text-align:right;white-space:nowrap;border-bottom:1px solid var(--rule2)}
th{font-weight:600;color:var(--ink2);border-bottom:1px solid var(--ink);background:#fafbfc}td{font:12px var(--mono)}
th:first-child,td:first-child{text-align:left;font-family:var(--font)}
footer{border-top:1px solid var(--rule);padding-top:10px;font-size:11px;color:var(--ink2)}
@media print{main{padding:0;max-width:none}figure,table{break-inside:avoid}}`;

/** 報告資料 → HTML。sections：[{title, img?(PNG data URI), caption?, tables?:[{head, rows}]}]；所有文字一律 escape。 */
export function buildReport({ title, time, info = [], note = '', sections = [] }) {
  const table = ({ head, rows }) => `<div class="tw"><table><tr>${head.map((c) => `<th>${esc(c)}</th>`).join('')}</tr>`
    + rows.map((r) => `<tr>${r.map((c) => `<td>${esc(c)}</td>`).join('')}</tr>`).join('') + '</table></div>';
  const body = sections.map((s) => ({ ...s, img: String(s.img ?? '').startsWith(PNG) ? s.img : null, tables: (s.tables ?? []).filter((t) => t?.rows.length) }))
    .filter((s) => s.img || s.tables.length)
    .map((s, i) => `<section><h2><i>${String(i + 1).padStart(2, '0')}</i>${esc(s.title)}</h2>`
      + (s.img ? `<figure><img src="${esc(s.img)}" alt="${esc(s.title)}">${s.caption ? `<figcaption>${esc(s.caption)}</figcaption>` : ''}</figure>` : s.caption ? `<p class="cap">${esc(s.caption)}</p>` : '')
      + s.tables.map(table).join('') + '</section>');
  return `<!doctype html>\n<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">`
    + `<title>${esc(title)}</title><style>${CSS}</style></head><body><main>`
    + `<header><div class="eyebrow"><span>示波器離線分析報告</span><span>${esc(time)}</span></div><h1>${esc(title)}</h1>`
    + `<dl>${info.map(([k, v]) => `<div><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl>`
    + (note ? `<div class="remark">${esc(note)}</div>` : '') + `</header>\n${body.join('\n')}\n<footer>示波器工具 · 離線分析匯出</footer></main></body></html>\n`;
}

/** 畫面表格 → {head, rows}：略過標題為空或「刪除」的欄（刪除鈕），輸入框取其值。 */
export function tableData(table) {
  const trs = [...(table?.rows ?? [])];
  if (!trs.length) return { head: [], rows: [] };
  const text = (c) => c.querySelector('input')?.value ?? c.textContent.trim();
  const keep = [...trs[0].cells].map((c) => !['', '刪除'].includes(text(c)));
  const pick = (tr) => [...tr.cells].map(text).filter((_, i) => keep[i]);
  return { head: pick(trs[0]), rows: trs.slice(1).map(pick) };
}

/** canvas → PNG data URI；invert 時寫入亮度反轉後的新圖。尺寸為 0（從未顯示）回 null。 */
export function snapshot(src, invert) {
  if (!src?.width || !src.height) return null;
  const c = document.createElement('canvas'); c.width = src.width; c.height = src.height;
  const g = c.getContext('2d'); g.drawImage(src, 0, 0);
  if (invert) { const im = g.getImageData(0, 0, c.width, c.height); invertPixels(im.data); g.putImageData(im, 0, 0); }
  return c.toDataURL('image/png');
}

const frames = (n) => new Promise((ok) => { const step = () => (n-- > 0 ? requestAnimationFrame(step) : ok()); step(); });
/** FFT 窗格常被拉得很矮：寬高比超過 ASPECT 時，暫時把宿主移到畫面外撐高，等 ResizeObserver 重畫後截圖再還原。
 *  只改高度時 fftpane 以現有頻譜包絡直接重畫（px 只隨寬度變），不需等重新取資料。 */
const ASPECT = 2.6;
async function tallSnapshot(canvas, invert) {
  const host = canvas?.parentElement, r = host?.getBoundingClientRect();
  if (!r?.width || r.width / r.height <= ASPECT) return snapshot(canvas, invert);
  const css = host.style.cssText;
  host.style.cssText = `${css};position:fixed;left:-20000px;top:0;width:${r.width}px;height:${Math.round(r.width / ASPECT)}px`;
  try { await frames(3); return snapshot(canvas, invert); } finally { host.style.cssText = css; }
}

/** 解碼資料不依賴分頁可見性；篩選狀態由畫面按鈕讀取，欄位與事件表一致。 */
export function decodeSection(st, root, F, invert) {
  const r = st.decodeResult;
  if (!r?.summary.ok || r.stale || r.summary.gen !== st.file?.gen) return [];
  const def = definition(r.protocol);
  const dx = st.channels.find(c => c.name === r.base)?.time_offset ?? 0;
  const only = root.querySelector('.decode__sum button:last-child')?.getAttribute('aria-pressed') === 'true';
  const { rows,total } = tableFrames(r.frames,only);
  const events = { head:['#','時間','類型',...def.columns.map(c => c.head),'內容','狀態'], rows:rows.map(f => {
    const content = withAscii(f,def.content(f),st.decodeAscii);
    return [f.i+1,F(f.t0+dx,'s'),def.eventKind?.(f) ?? def.kinds[f.kind] ?? f.kind,...def.columns.map(c => c.cell(f)),
      content.length > 64 ? content.slice(0,64)+'…' : content,f.reasons.map(k => def.reasons[k] ?? k).join('、') || (f.kind === 'hdr' ? '資訊' : '正常')];
  }) };
  const addresses = def.addresses && { head:def.addresses.head,rows:r.addresses.slice(0,256).map(a => def.addresses.row(a,F,dx)) };
  const band = root.querySelector('.analysis__decodeband');
  const channels = Object.entries(r.summary.channels ?? {}).map(([k,v]) => k.toUpperCase()+' '+v).join('／');
  const thresholds = Object.entries(r.summary.thresholds).map(([k,v]) => k.toUpperCase()+' '+(v?.map(n => F(n,'V')).join('～') ?? '—')).join('；');
  const caption = `${channels}；門檻 ${thresholds}；篩選：${only ? '只錯誤／警告' : '全部'}；表格最多 2000 列${def.addresses ? '，位址表最多 256 列' : ''}。`
    +(total > 2000 || r.addresses.length > 256 ? '表格已截斷；CSV 含全部。' : '')+(r.summary.truncated ? '解碼達上限，結果已截斷。' : '')+(def.reportSummary ? def.summary(r.summary,r.options) : '');
  return [{ title:`解碼（${def.label}）`,img:band && !band.hidden ? snapshot(band.querySelector('canvas'),invert) : null,caption,tables:[events,...(addresses ? [addresses] : [])] }];
}

const stamp =(d = new Date()) => { const p = (n) => String(n).padStart(2, '0'); return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`; };

/** 目前畫面 → buildReport 的資料。root＝分析頁 .analysis；FFT 圖取畫面上最大的頻譜 canvas（分析頁窗格或 FFT 大檢視）。 */
export async function collectReport({ store, fmt }, root, { title, dut, note, invert }) {
  const st = store.get(), decodeRef = st.decodeResult, f = st.file, v = st.view, q = (s) => root.querySelector(s), F = fmt.fmt;
  // 剛解除 hidden 時 canvas 仍可能為 0；等版面與 ResizeObserver 排定的 fit／重畫完成再截圖。
  const band = q('.analysis__decodeband');
  if (band && !band.hidden) await frames(3);
  const decoded = decodeSection({ ...st,decodeResult:decodeRef },root,F,invert);
  const fftCanvas = [...document.querySelectorAll('.analysis__fft canvas')].sort((a, b) => b.width * b.height - a.width * a.height)[0];
  const range = st.rangeMode === 'cursors' ? `游標區間 ${F(st.cursors.x1, 's')} ～ ${F(st.cursors.x2, 's')}` : '全部';
  const info = [...(dut ? [['DUT', dut]] : []), ['來源檔', f.path], ...f.info.filter(([k]) => k !== '檔名'),
    ['顯示範圍', `${F(v.t0, 's')} ～ ${F(v.t1, 's')}`], ['量測範圍', range]];
  const scales = st.channels.filter((c) => c.visible).map((c) => `${c.name} ${F(c.scale, c.unit)}/div`).join('　');
  const r = st.fftResult, fftImg = r?.ok ? await tallSnapshot(fftCanvas, invert) : null;
  return { title, time: stamp(), note, info, sections: [
    { title: '波形', img: snapshot(q('.analysis__main canvas'), invert), caption: `${scales}　·　水平 ${F((v.t1 - v.t0) / 10, 's')}/div` },
    { title: '量測結果', tables: st.measurements.length ? [tableData(q('.analysis__results .results__table'))] : [] },
    { title: '游標', tables: [tableData(q('.cursor-results__table')), tableData(q('.analysis__cursors > table'))] },
    { title: 'Marker', tables: [tableData(q('.analysis__markers table'))] },
    ...decoded,
    ...(r?.ok ? [{ title: 'FFT 頻譜', img: fftImg, caption: fftInfo(r, fmt), tables: [tableData(q('.analysis__peaks table'))] }] : []),
  ] };
}

const h = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; };
const field = (label, ctl) => { const f = h('label', 'field', label + ' '); f.append(ctl); return f; };

/** 「匯出報告」：量測計算中／過期時擋下；對話框填標題、DUT、備註與曲線區配色後寫到來源檔資料夾。modal 沿用工具列的對話框。 */
export async function exportReport(ctx, root, modal) {
  const { store, bridge, ui } = ctx, stale = () => { const s = store.get(); return !!s.measurements.length && !exportable(s.measurements, s.file); };
  const f = store.get().file;
  if (!f) return;
  if (stale()) return ui.toast('量測計算中或結果已過期，請稍後再匯出', 'error');
  const stem = f.path.split(/[\\/]/).pop().replace(/\.[^.]*$/, '');
  const o = await modal('匯出報告', (b) => {
    const title = h('input', 'input'), dut = h('input', 'input'), note = h('textarea', 'input'), color = h('select', 'select');
    title.placeholder = `${stem}（留空則用來源檔名）`; note.rows = 3;
    color.append(new Option('反白（白底）', 'inv'), new Option('維持原圖（黑底）', 'orig'));
    b.append(field('標題', title), field('DUT／測試物', dut), field('備註', note), field('曲線區配色', color),
      h('p', 'muted', `輸出：${f.path.replace(/[\\/][^\\/]*$/, '')}（與來源檔同資料夾，檔名加時間戳）`));
    return () => ({ title: title.value.trim() || stem, dut: dut.value.trim(), note: note.value.trim(), invert: color.value === 'inv' });
  }, '匯出報告');
  if (!o) return;
  if (store.get().file?.gen !== f.gen || stale()) return ui.toast('檔案或量測已變更，請重新匯出', 'error');
  try {
    const decodeRef = store.get().decodeResult;
    const html = buildReport(await collectReport(ctx, root, o));
    if (store.get().file?.gen !== f.gen || store.get().decodeResult !== decodeRef) return ui.toast('解碼結果已變更，請重新匯出', 'error');
    if (stale()) return ui.toast('檔案或量測已變更，請重新匯出', 'error');
    const r = await bridge.call('export_report', { html, directory: null });
    ui.toast(`已匯出：${r.path}`, 'ok', 6000);
  } catch (e) { ui.showError(e, '匯出報告失敗'); }
}
