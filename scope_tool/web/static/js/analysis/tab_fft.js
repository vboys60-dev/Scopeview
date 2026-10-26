// FFT 的獨立大檢視：與分析頁共用結果／參數，繪圖視窗維持各自本地狀態。
import { mount as mountPane } from './fftpane.js';
import { mountFftControls } from './fft_state.js';
import { mountFftMarkerTable, fftInfo } from './fft_marker_table.js';
export function mount(el, ctx) {
  const { store, fmt } = ctx;
  const h = (tag, cls, text) => { const e = document.createElement(tag); e.className = cls; if (text) e.textContent = text; return e; };
  const root = h('div', 'fftpage'), source = h('div', 'fftpage__source'), params = h('div', 'fftpage__params');
  const body = h('div', 'fftpage__body'), plot = h('div', 'fftpage__plot analysis__fft'), side = h('aside', 'fftpage__side');
  const marker = h('div', 'fftpage__markers'), table = h('div', 'fftpage__table'), empty = h('div', 'fftpage__empty', '請先在離線分析開啟波形檔 ');
  const back = h('button', 'btn', '離線分析 ↗'); back.type = 'button'; back.onclick = () => store.command('tab.select', 'analysis'); empty.append(back);
  const range = h('select', 'select'); range.append(new Option('全部', 'all'), new Option('游標區間', 'cursors'));
  range.title = '量測與 FFT 共用範圍'; range.onchange = () => store.set({ rangeMode: range.value }, 'user');
  const field = (name, ctl) => { const f = h('label', 'field', name + ' '); f.append(ctl); source.append(f); };
  // 先掛共用來源選單，其餘參數與峰值控制分別放入參數列／右欄。
  mountFftControls(params, ctx, { sourceHost: source, markerHost: marker });
  field('範圍', range);
  const inputs = ['x1', 'x2'].map(which => {
    const input = h('input', 'input'); input.setAttribute('aria-label', which.toUpperCase());
    input.onchange = () => {
      const value = input.value.trim() ? fmt.parseSI(input.value) : null;
      if (value === null || Number.isFinite(value)) store.command('cursor.intent', { which, value });
      sync();
    };
    field(which.toUpperCase(), input); return input;
  });
  side.append(marker, table); body.append(plot, side); root.append(empty, source, params, body); el.append(root);
  mountPane(plot, ctx); mountFftMarkerTable(table, ctx, fftInfo);
  function sync() {
    const st = store.get(); empty.hidden = !!st.file; range.disabled = !st.file; range.value = st.rangeMode;
    inputs.forEach((input, i) => {
      input.disabled = !st.file;
      if (document.activeElement !== input) input.value = Number.isFinite(st.cursors[['x1', 'x2'][i]]) ? fmt.fmt(st.cursors[['x1', 'x2'][i]], 's') : '';
    });
  }
  store.on(['file', 'cursors', 'rangeMode'], sync); sync();
}
