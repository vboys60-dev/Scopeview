// Marker 表：註記 Enter 確認、Esc 取消；點列透過既有視圖意圖置中。
import { markerModel } from './markers.js';
import { fmt } from '../fmt.js';
export const HEADERS = ['#', '通道', '時間', '電壓', 'Δt', 'ΔV', '基準', '註記', '刪除'];
export function markerCells(row, format = fmt) {
  const f = (v, u) => Number.isFinite(v) ? format(v, u) : '—';
  return [row.id, row.ch, f(row.value === null ? null : row.t, 's'), f(row.value, row.channel.unit), f(row.value === null ? null : row.dt, 's'), f(row.dv, row.channel.unit), row.ref, row.note];
}
export function mount(el, ctx) {
  const { store } = ctx, model = markerModel(ctx);
  const h = (tag, text) => { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; return e; };
  const bar = h('div'), title = h('span', 'Marker '), link = h('button', '新增／移動連動 M1');
  link.type = 'button'; link.className = 'btn btn--small'; link.title = '把 M1 放在目前畫面中心；右鍵可在指標處新增';
  link.onclick = () => { const v = store.get().view; store.command('marker.link', { t: (v.t0 + v.t1) / 2 }); };
  // 獨立點：加在目前通道、畫面中心；已有同位置的點就往右錯開 1/20 畫面，避免疊在一起。
  const add = h('button', '＋ 獨立點（目前通道）');
  add.type = 'button'; add.className = 'btn btn--small'; add.title = '在目前通道、畫面中心新增獨立 Marker；也可在主圖按右鍵新增';
  add.onclick = () => {
    const st = store.get(), v = st.view, span = v.t1 - v.t0, ch = st.selected;
    let t = (v.t0 + v.t1) / 2; const used = model.rows().filter(r => !r.link && r.ch === ch).map(r => r.t);
    while (used.some(u => Math.abs(u - t) < span / 100) && t < v.t1) t += span / 20;
    store.command('marker.add', { ch, t });
  };
  bar.append(title, link, add);
  const table = h('table'); table.className = 'table table--num'; table.setAttribute('aria-label', 'Marker Table'); table.style.tableLayout = 'fixed';
  el.append(bar, table); let editing = false, signature = '';
  const highlight = () => {
    for (const tr of table.children) if (tr.dataset.markerKey) tr.className = tr.dataset.markerKey === model.selected || tr.dataset.markerKey === model.hovered ? 'is-selected' : '';
  };
  function render() {
    link.disabled = add.disabled = !store.get().file;
    const data = model.rows(), next = JSON.stringify(data.map(row => [row.key, ...markerCells(row), store.get().markerTable.map(p => p.id)]));
    if (editing || next === signature) { highlight(); return; }
    signature = next;
    const head = h('tr'); HEADERS.forEach(label => { const th = h('th', label); th.style.cssText = 'white-space:normal;overflow-wrap:anywhere;padding:2px'; head.append(th); });
    const rows = data.map(row => {
      const tr = h('tr'); tr.dataset.markerKey = row.key; tr.tabIndex = 0;
      const values = markerCells(row);
      values.slice(0, 6).forEach(text => { const td = h('td', text); td.style.cssText = 'white-space:normal;overflow-wrap:anywhere;padding:2px'; tr.append(td); });
      const refCell = h('td'), select = h('select'); select.setAttribute('aria-label', `${row.id} ${row.ch} 基準`); select.style.cssText = 'width:100%;min-width:0';
      for (const id of [null, ...store.get().markerTable.map(p => p.id)]) { const option = h('option', id ?? '無'); option.value = id ?? ''; select.append(option); }
      select.value = row.ref ?? ''; select.onclick = e => e.stopPropagation(); select.onchange = () => model.ref({ id: row.id, ref: select.value || null }); refCell.style.padding = '2px'; refCell.append(select); tr.append(refCell);
      const note = h('td'), input = h('input'); input.className = 'input marker-table__note'; input.value = row.note; input.style.cssText = 'width:100%;min-width:0;box-sizing:border-box'; input.setAttribute('aria-label', `${row.id} ${row.ch} 註記`);
      input.onfocus = () => { editing = true; };
      input.onblur = () => { editing = false; input.value = row.note; render(); };
      input.onkeydown = e => {
        e.stopPropagation();
        if (e.key === 'Escape') { input.value = row.note; input.blur(); }
        if (e.key === 'Enter') { const value = input.value; editing = false; model.note({ id: row.id, note: value }); }
      };
      input.onclick = e => e.stopPropagation(); note.append(input); tr.append(note);
      const cell = h('td'), remove = h('button', '✕'); remove.type = 'button'; remove.className = 'btn btn--small'; remove.title = row.link ? '刪除整個連動組' : '刪除 Marker';
      remove.onclick = e => { e.stopPropagation(); model.remove(row.id); }; cell.append(remove); tr.append(cell);
      tr.onclick = () => { tr.focus?.({ preventScroll: true }); model.select(row.key); };
      tr.onkeydown = e => { if (e.target?.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/i.test(e.target?.tagName ?? '')) return; if (['Delete', 'Backspace'].includes(e.key)) { e.preventDefault(); model.remove(row.id); } else if (e.key === 'Enter') model.select(row.key); };
      return tr;
    });
    table.replaceChildren(head, ...rows); highlight();
  }
  model.on(render); render();
}
