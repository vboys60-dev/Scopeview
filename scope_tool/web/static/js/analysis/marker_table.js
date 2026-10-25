// Marker 表：註記 Enter 確認、Esc 取消；點列透過既有視圖意圖置中。
import { markerModel } from './markers.js';
import { fmt } from '../fmt.js';
export const HEADERS = ['#', '通道', '時間', '電壓', 'Δt vs M1', '註記', '刪除'];
export function markerCells(row, format = fmt) {
  const f = (v, u) => Number.isFinite(v) ? format(v, u) : '—';
  return [row.id, row.ch, f(row.value === null ? null : row.t, 's'), f(row.value, row.channel.unit), f(row.value === null ? null : row.dt, 's'), row.note];
}
export function mount(el, ctx) {
  const { store } = ctx, model = markerModel(ctx);
  const h = (tag, text) => { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; return e; };
  const bar = h('div'), title = h('span', 'Marker '), link = h('button', '新增／移動連動 M1');
  link.type = 'button'; link.className = 'btn btn--small'; link.title = '把 M1 放在目前畫面中心；右鍵可在指標處新增';
  link.onclick = () => { const v = store.get().view; store.command('marker.link', { t: (v.t0 + v.t1) / 2 }); };
  bar.append(title, link);
  const table = h('table'); table.className = 'table table--num'; table.setAttribute('aria-label', 'Marker Table');
  el.append(bar, table); let editing = false, signature = '';
  const highlight = () => {
    for (const tr of table.children) if (tr.dataset.markerKey) tr.className = tr.dataset.markerKey === model.selected || tr.dataset.markerKey === model.hovered ? 'is-selected' : '';
  };
  function render() {
    link.disabled = !store.get().file;
    const data = model.rows(), next = JSON.stringify(data.map(row => [row.key, ...markerCells(row)]));
    if (editing || next === signature) { highlight(); return; }
    signature = next;
    const head = h('tr'); HEADERS.forEach(label => head.append(h('th', label)));
    const rows = data.map(row => {
      const tr = h('tr'); tr.dataset.markerKey = row.key; tr.tabIndex = 0;
      const values = markerCells(row);
      values.slice(0, 5).forEach(text => tr.append(h('td', text)));
      const note = h('td'), input = h('input'); input.className = 'input marker-table__note'; input.value = row.note; input.setAttribute('aria-label', `${row.id} ${row.ch} 註記`);
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
      tr.onkeydown = e => { if (e.target?.isContentEditable || /^(INPUT|TEXTAREA)$/i.test(e.target?.tagName ?? '')) return; if (['Delete', 'Backspace'].includes(e.key)) { e.preventDefault(); model.remove(row.id); } else if (e.key === 'Enter') model.select(row.key); };
      return tr;
    });
    table.replaceChildren(head, ...rows); highlight();
  }
  model.on(render); render();
}
