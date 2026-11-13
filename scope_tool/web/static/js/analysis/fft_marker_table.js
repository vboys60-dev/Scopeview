// 分析頁 B 區與 FFT 大檢視共用峰表；峰值沒有註記欄。
import { fftManualModel } from './fft_manual.js';
import { fftMarkerModel } from './fft_markers.js';
export function mountFftMarkerTable(el, ctx, info) {
  const { store, fmt } = ctx, model = fftMarkerModel(ctx), manual = fftManualModel(ctx);
  const h = (tag, text) => { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; return e; };
  const title = h('div'), table = h('table'), foot = h('div');
  title.className = 'results__fftinfo muted'; table.className = 'table table--num results__table'; foot.className = 'muted';
  table.setAttribute('aria-label', 'FFT Marker Table'); el.append(title, table, foot);
  const row = (cells, tag = 'td') => { const tr = h('tr'); cells.forEach(v => tr.append(h(tag, v))); return tr; };
  function render() {
    const r = store.get().fftResult, level = model.displayLevel();
    title.textContent = info(r, fmt);
    const list = [...model.rows(), ...(r?.ok && r.unit !== '°' ? manual.points() : [])];
    const rows = list.map((p, i) => {
      const tr = row([p.id ? `M${p.id}` : String(i + 1), fmt.fmt(p.x, 'Hz'), p.y == null ? '—' : fmt.fmt(p.y, r.unit), p.y == null ? '—' : fmt.fmt(p.y - level, r.unit.startsWith('dB') ? 'dB' : r.unit), '']);
      tr.tabIndex = 0; tr.style.cursor = 'pointer';
      const select = () => store.command('rf.intent', { direction: 0, x: p.x });
      tr.onclick = select; tr.onkeydown = e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); select(); } };
      if (p.id) {
        const del = h('button', '×'); del.type = 'button'; del.className = 'btn btn--small'; del.setAttribute('aria-label', `刪除 M${p.id}`);
        del.onclick = e => { e.stopPropagation(); manual.remove(p.id); };
        del.onkeydown = e => e.stopPropagation(); tr.children[4].append(del);
      }
      return tr;
    });
    table.replaceChildren(row(['#', '頻率', '振幅', '高於 Peak Line', '刪除'], 'th'), ...rows);
    // ponytail: 峰快取是全頻譜前 1000；需要時加 fft_peaks RPC 取畫面內的峰。
    // 契約沒有總峰數；滿額即保守提示可能截斷，不宣稱已知實際總數。
    foot.textContent = `峰頻率已內插；手動 Marker 取最近頻格${model.truncated ? '｜已截斷（全頻譜達 1000 峰上限，畫面內可能漏列）' : ''}`;
  }
  const off = store.on(['fftResult', 'fftMarker', 'fftView'], render); render();
  return { dispose: off };
}

export function fftInfo(r, fmt) {
  if (!r) return "";
  if (!r.ok) return r.reason ?? "FFT 失敗";
  return `Δf ${fmt.fmt(r.df, "Hz")}｜RBW ${fmt.fmt(r.rbw, "Hz")}（${r.segments ?? 1} 段）｜VBW ${r.vbw == null ? "Auto（不平滑）" : fmt.fmt(r.vbw, "Hz")}｜ENBW ${fmt.fmt(r.enbw, "Hz")}｜${r.window}｜N=${r.n}（${r.effective_n}）｜R=${r.r_ohm} Ω｜${r.unit}`;
}
