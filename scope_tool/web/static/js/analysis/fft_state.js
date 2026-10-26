// 每個 store 只有一份 FFT 參數與 runner；兩個頁面的控制列共用此接線。
import { createFft } from './fft_runner.js';
import { bindFftMarkerControls } from './fft_marker_controls.js';
const states = new WeakMap();
export function getFftState(ctx) {
  const { store, ui } = ctx;
  if (states.has(store)) return states.get(store);
  const catalog = ctx.appState?.catalog ?? {}, listeners = new Set();
  const p = { on: false, source: null, window: 'Hanning', unit: 'dBm', imp: 0, manualR: 50,
    peakCount: 5, peakLevel: -40, peakSort: (catalog.peak_sorts ?? ['Decreasing Magnitude'])[0] };
  let analysisOn = false, active = ctx.activeTab === 'fft';
  const notify = () => { for (const fn of listeners) fn(); };
  const enabled = () => { p.on = analysisOn || (active && !!store.get().file); };
  const source = () => {
    const names = store.get().channels.map(c => c.name);
    if (!names.includes(p.source)) p.source = names[0] ?? null;
  };
  source();
  // 先正規化來源，再讓 runner 建立新檔的工作參數。
  store.on(['file', 'channels'], source);
  const runner = createFft(ctx, catalog, p, {
    onError: (e, manual) => manual ? ui.showError(e, 'FFT 失敗') : ui.toast(`FFT 失敗：${e.message}`, 'error', 6000),
    onReset: () => { analysisOn = false; enabled(); store.command('fft.visible', false); notify(); },
  });
  const state = { p, runner, catalog,
    get analysisOn() { return analysisOn; },
    subscribe(fn) { listeners.add(fn); fn(); return () => listeners.delete(fn); },
    change(key, value) { p[key] = value; runner.schedule(); notify(); },
    setAnalysisOn(on) {
      analysisOn = !!on && !!store.get().file; enabled();
      store.command('fft.visible', analysisOn);
      if (p.on) runner.ensure(); else runner.invalidate();
      notify();
    },
  };
  states.set(store, state);
  store.onCommand('tab.activated', name => {
    active = name === 'fft'; enabled();
    if (p.on) runner.ensure(); else runner.invalidate();
    notify();
  });
  store.on(['file', 'channels', 'fftMarker'], notify);
  store.on(['fftResult'], st => {
    const r = st.fftResult;
    if (st.rfPos && r?.ok && r.unit !== '°') store.command('rf.intent', { direction: 0, x: st.rfPos.x });
    else if (st.rfPos && !r?.ok) store.set({ rfPos: null }, 'program');
  });
  enabled(); runner.ensure();
  return state;
}

/** 同一套控制項接線，可把來源與峰值控制分別放進分頁的來源列／右欄。 */
export function mountFftControls(el, ctx, { sourceHost = el, markerHost = el } = {}) {
  const state = getFftState(ctx), { p, catalog } = state;
  const h = (tag, cls) => { const e = document.createElement(tag); e.className = cls; return e; };
  const field = (host, name, control) => { const label = h('label', 'field'); label.textContent = name + ' '; label.append(control); host.append(label); };
  const select = opts => { const s = h('select', 'select'); s.append(...opts.map(([v, t]) => new Option(t, v))); return s; };
  const src = select([]), win = select(Object.keys(catalog.fft_windows ?? {}).map(k => [k, k]));
  const unit = select((catalog.fft_units ?? []).filter(k => k !== 'Phase').map(k => [k, k]));
  const imp = select((catalog.fft_impedances ?? []).map(([t], i) => [i, t]));
  const sort = select((catalog.peak_sorts ?? []).map(k => [k, k]));
  const man = h('input', 'input'), lvl = h('input', 'input'), cnt = h('input', 'input');
  for (const input of [man, lvl, cnt]) input.style.width = '5em';
  for (const [control, key, conv] of [[src, 'source', String], [win, 'window', String], [imp, 'imp', Number]])
    control.onchange = () => state.change(key, conv(control.value));
  man.onchange = () => { const n = Number(man.value); if (Number.isFinite(n) && n > 0) state.change('manualR', n); else man.value = String(p.manualR); };
  bindFftMarkerControls(ctx, p, { unit, lvl, cnt, sort, imp, man }, catalog);
  field(sourceHost, '來源', src); field(el, '視窗', win); field(el, '單位', unit);
  if (sourceHost === el) el.append(imp); else field(el, '阻抗', imp);
  el.append(man);
  field(markerHost, '排序', sort); field(markerHost, '基準線', lvl); field(markerHost, '顯示數量 n', cnt);
  const sync = () => {
    const st = ctx.store.get(), names = st.channels.map(c => c.name);
    if (src.options.length !== names.length || [...src.options].some((o, i) => o.value !== names[i])) src.replaceChildren(...names.map(n => new Option(n, n)));
    for (const c of [src, win, unit, imp, man, lvl, cnt, sort]) c.disabled = !st.file;
    for (const [c, v] of [[src, p.source ?? ''], [win, p.window], [imp, String(p.imp)], [man, String(p.manualR)]])
      if (document.activeElement !== c) c.value = v;
    man.disabled = !st.file || (catalog.fft_impedances ?? [])[p.imp]?.[1] !== null;
    for (const c of [sort, lvl, cnt]) c.disabled = !st.file || p.unit === 'Phase';
  };
  const dispose = state.subscribe(sync);
  return { src, win, unit, imp, man, sort, lvl, cnt, dispose };
}
