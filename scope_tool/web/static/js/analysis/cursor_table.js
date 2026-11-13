// L5：Marker_Results 資料與 TSV 為純函式；DOM／剪貼簿另行處理，不寫 store。
import { chLabel } from './alias.js';
import { fmt } from '../fmt.js';
export const HEADERS = ['Marker', '水平(X)', '垂直(Y，來源單位)', 'ΔX', '1/ΔX', 'ΔY', 'ΔY/ΔX', 'Delta To'];
const finite = Number.isFinite;
const difference = (a, b) => finite(a) && finite(b) ? b - a : null;
/** 只列有效模式的 Marker；手動 X/Y 線沒有另一軸座標，追蹤 X 帶取樣 Y。
 * 差值固定為第二條減第一條；Delta To 顯示配對，不因所在列而反轉符號。
 */
export function buildMarkerRows(r, format = fmt) {
  if (!r || r.kind === 'unsupported' || r.available === false) return [];
  const legacy = r.kind === 'legacy', track = r.mode === 'Track Waveforms';
  const x = legacy || track || ['Manual X only', 'Manual X and Y'].includes(r.mode);
  const y = legacy || ['Manual Y only', 'Manual X and Y'].includes(r.mode);
  const dx = x ? difference(r.t1, r.t2) : null, dy = y || track ? difference(r.v1, r.v2) : null;
  const inv = finite(dx) && dx !== 0 ? 1 / dx : null;
  const slope = finite(dx) && finite(dy) && dx !== 0 ? dy / dx : null;
  const f = (v, u) => finite(v) ? format(v, u) : '—';
  const deltas = [f(dx, 's'), f(inv, 'Hz'), f(dy, r.unit), f(slope, r.unit ? `${r.unit}/s` : '1/s')];
  return ['X1', 'X2', 'Y1', 'Y2'].filter(k => k[0] === 'X' ? x : y).map(k => {
    const second = k[1] === '2', horizontal = k[0] === 'X';
    return [k, f(horizontal ? (second ? r.t2 : r.t1) : null, 's'),
      f(!horizontal || track ? (second ? r.v2 : r.v1) : null, r.unit),
      ...deltas, `${k[0]}${second ? '1' : '2'}`];
  });
}
export const markerTSV = (rows) => [HEADERS, ...rows].map(row => row.map(cell => String(cell).replace(/[\t\r\n]/g, ' ')).join('\t')).join('\n');

/** 安全環境優先用 Clipboard API；WebView／權限拒絕時保留傳統複製途徑。 */
export async function copyText(text, nav = globalThis.navigator, doc = globalThis.document) {
  try { await nav.clipboard.writeText(text); return true; } catch { /* 改走選取文字 */ }
  const active = doc.activeElement, area = doc.createElement('textarea');
  area.value = text; area.setAttribute('readonly', '');
  Object.assign(area.style, { position: 'fixed', left: '-9999px', top: '0' });
  try {
    doc.body.append(area); area.select();
    return !!doc.execCommand('copy');
  } catch { return false; }
  finally { area.remove(); active?.focus?.({ preventScroll: true }); }
}
export function mountCursorTable({ ui, store }) {
  const el = document.createElement('section'); el.className = 'cursor-results';
  const bar = document.createElement('div'); bar.className = 'cursor-results__bar';
  const label = document.createElement('span'); label.textContent = '游標結果';
  const button = document.createElement('button'); button.className = 'btn btn--small cursor-results__copy'; button.type = 'button'; button.textContent = '複製';
  const wrap = document.createElement('div'); wrap.className = 'cursor-results__wrap';
  const table = document.createElement('table'); table.className = 'table table--num cursor-results__table'; table.setAttribute('aria-label', '游標結果');
  bar.append(label, button); wrap.append(table); el.append(bar, wrap);
  let rows = [], timer, lastReadout;
  button.onclick = async () => {
    const ok = await copyText(markerTSV(rows)), message = ok ? '已複製' : '複製失敗';
    if (ui?.toast) ui.toast(message, ok ? 'success' : 'error');
    else { clearTimeout(timer); button.textContent = message; timer = setTimeout(() => { button.textContent = '複製'; }, 1800); }
  };
  const view = { el, render(readout) {
    lastReadout = readout; rows = buildMarkerRows(readout);
    label.textContent = `游標結果（${chLabel(store?.get().channels ?? [], readout?.source || '—')}，${readout?.mode ?? '傳統游標'}）`;
    table.setAttribute('aria-label', label.textContent);
    table.replaceChildren(...[HEADERS, ...rows].map((row, i) => {
      const tr = document.createElement('tr');
      for (const value of row) { const cell = document.createElement(i ? 'td' : 'th'); cell.textContent = value; tr.append(cell); }
      return tr;
    }));
    button.disabled = !rows.length;
    return rows.length;
  } };
  store?.on(["channels"], () => view.render(lastReadout));
  return view;
}
