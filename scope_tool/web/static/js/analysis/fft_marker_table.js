// B 區既有 FFT 峰值頁籤使用此表；峰值沒有註記欄。
import { fftMarkerModel } from './fft_markers.js';
export function mountFftMarkerTable(el, ctx, info) {
  const { store, fmt } = ctx, model = fftMarkerModel(ctx);
  const h = (tag, text) => { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; return e; };
  const title = h('div'), table = h('table'), foot = h('div');
  title.className = 'results__fftinfo muted'; table.className = 'table table--num results__table'; foot.className = 'muted';
  table.setAttribute('aria-label', 'FFT Marker Table'); el.append(title, table, foot);
  const row = (cells, tag = 'td') => { const tr = h('tr'); cells.forEach(v => tr.append(h(tag, v))); return tr; };
  function render() {
    const r = store.get().fftResult, level = model.displayLevel();
    title.textContent = info(r, fmt);
    const rows = model.rows().map((p, i) => {
      const tr = row([String(i + 1), fmt.fmt(p.x, 'Hz'), fmt.fmt(p.y, r.unit), fmt.fmt(p.y - level, r.unit.startsWith('dB') ? 'dB' : r.unit)]);
      tr.tabIndex = 0; tr.style.cursor = 'pointer';
      const select = () => store.command('rf.intent', { direction: 0, x: p.x });
      tr.onclick = select; tr.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); select(); } };
      return tr;
    });
    table.replaceChildren(row(['#', '頻率', '振幅', '高於基準線'], 'th'), ...rows);
    // 契約沒有總峰數；滿額即保守提示可能截斷，不宣稱已知實際總數。
    foot.textContent = `頻率已內插${model.truncated ? '｜已截斷（達 1000 峰抓取上限）' : ''}`;
  }
  const off = store.on(['fftResult', 'fftMarker'], render); render();
  return { dispose: off };
}
