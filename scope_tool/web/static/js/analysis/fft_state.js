// 每個 store 只有一份 FFT 參數與 runner；兩個頁面的控制列共用此接線。
import { chLabel } from './alias.js';
import { createFft } from './fft_runner.js';
import { bindFftMarkerControls } from './fft_marker_controls.js';
const states = new WeakMap();
export function getFftState(ctx) {
  const { store, ui } = ctx;
  if (states.has(store)) return states.get(store);
  const catalog = ctx.appState?.catalog ?? {}, listeners = new Set();
  const p = { on: false, source: null, window: 'Hanning', unit: 'dBm', imp: 0, manualR: 50,
    rbw: null, vbw: null, autoRbw: null, phaseRef: null, unwrap: false, peakCount: 5, peakLevel: -40, peakSort: (catalog.peak_sorts ?? ['Decreasing Magnitude'])[0] };
  let autoTimer = null;
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
    onReset: () => { clearTimeout(autoTimer); p.autoRbw = null; analysisOn = false; enabled(); store.command('fft.visible', false); notify(); },
  });
  const state = { p, runner, catalog,
    get analysisOn() { return analysisOn; },
    subscribe(fn) { listeners.add(fn); fn(); return () => listeners.delete(fn); },
    change(key, value) {
      p[key] = value;
      if (key === 'rbw') { clearTimeout(autoTimer); if (value === null) p.autoRbw = autoBandwidth(store.get()); }
      runner.schedule(); notify();
    },
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
  // 只讀 P3 的 fftView；以最後送出的 Auto 要求值比較，避免新結果造成循環。
  const followSpan = () => {
    clearTimeout(autoTimer);
    if (p.rbw !== null || p.unit === 'Phase') return;
    const next = autoBandwidth(store.get());
    if (next === null || (p.autoRbw > 0 && Math.abs(next / p.autoRbw - 1) < 0.05)) return;
    autoTimer = setTimeout(() => {
      const value = autoBandwidth(store.get());
      if (p.rbw !== null || p.unit === 'Phase' || value === null) return;
      if (p.autoRbw > 0 && Math.abs(value / p.autoRbw - 1) < 0.05) return;
      p.autoRbw = value; runner.schedule(0); notify();
    }, 300);
  };
  store.on(['fftView', 'fftResult', 'fftMarker'], followSpan);
  store.on(['file', 'channels', 'fftMarker', 'fftResult'], notify);
  store.on(['fftResult'], st => {
    const r = st.fftResult;
    if (st.rfPos && r?.ok && r.unit !== '°') store.command('rf.intent', { direction: 0, x: st.rfPos.x });
    else if (st.rfPos && !r?.ok) store.set({ rfPos: null }, 'program');
  });
  followSpan(); enabled(); runner.ensure();
  return state;
}

/** 同一套控制項接線，可把來源與峰值控制分別放進分頁的來源列／右欄。 */
export function mountFftControls(el, ctx, { sourceHost = el, markerHost = el, impHost = el } = {}) {
  const state = getFftState(ctx), { p, catalog } = state;
  const h = (tag, cls) => { const e = document.createElement(tag); e.className = cls; return e; };
  const field = (host, name, control) => { const label = h('label', 'field'); label.textContent = name + ' '; label.append(control); host.append(label); return label; };
  const select = opts => { const s = h('select', 'select'); s.append(...opts.map(([v, t]) => new Option(t, v))); return s; };
  const src = select([]), win = select(Object.keys(catalog.fft_windows ?? {}).map(k => [k, k]));
  const unit = select((catalog.fft_units ?? []).map(k => [k, k]));
  const imp = select((catalog.fft_impedances ?? []).map(([t], i) => [i, t]));
  const sort = select((catalog.peak_sorts ?? []).map(k => [k, k]));
  const lvlUnit = h('span', 'muted'), man = h('input', 'input'), lvl = h('input', 'input'), cnt = h('input', 'input');
  for (const input of [man, lvl, cnt]) input.style.width = '5em';
  for (const [control, key, conv] of [[src, 'source', String], [win, 'window', String], [imp, 'imp', Number]])
    control.onchange = () => state.change(key, conv(control.value));
  man.onchange = () => { const n = Number(man.value); if (Number.isFinite(n) && n > 0) state.change('manualR', n); else man.value = String(p.manualR); };
  bindFftMarkerControls(ctx, p, { unit, lvl, cnt, sort, imp, man, lvlUnit }, catalog);
  field(sourceHost, '來源', src); field(el, '視窗', win); field(el, '單位', unit);
  if (impHost !== el) { field(impHost, '阻抗', imp); impHost.append(man); } else { if (sourceHost === el) el.append(imp); else field(el, '阻抗', imp); el.append(man); }
  field(markerHost, '排序', sort); field(markerHost, 'Peak Line', lvl).append(lvlUnit); field(markerHost, '顯示數量 n', cnt);
  const { fmt } = ctx;
  const refLabel = document.createElement('label'), ref = document.createElement('input'), unwrapLabel = document.createElement('label'), unwrap = document.createElement('input');
  refLabel.className = unwrapLabel.className = 'field'; refLabel.textContent = '相位參考（空白＝觸發 0） '; ref.className = 'input'; ref.style.width = '6em'; ref.setAttribute('aria-label', '相位參考（空白＝觸發 0）');
  ref.onchange = () => { const text = ref.value.trim(), value = text ? fmt.parseSI(text) : null; if (value === null && text || value !== null && !Number.isFinite(value)) { ref.value = p.phaseRef === null ? '' : fmt.fmt(p.phaseRef, 's'); return; } state.change('phaseRef', value); };
  unwrap.type = 'checkbox'; unwrap.setAttribute('aria-label', 'Unwrap'); unwrap.onchange = () => state.change('unwrap', unwrap.checked); refLabel.append(ref); unwrapLabel.append(unwrap, ' Unwrap'); markerHost.append(refLabel, unwrapLabel);
  const sync = () => {
    const st = ctx.store.get(), names = st.channels.map(c => c.name);
    if (src.options.length !== names.length || [...src.options].some((o, i) => o.value !== names[i] || o.text !== chLabel(st.channels, names[i]))) src.replaceChildren(...names.map(n => new Option(chLabel(st.channels, n), n)));
    for (const c of [src, win, unit, imp, man, lvl, cnt, sort]) c.disabled = !st.file;
    for (const [c, v] of [[src, p.source ?? ''], [win, p.window], [imp, String(p.imp)], [man, String(p.manualR)]])
      if (document.activeElement !== c) c.value = v;
    ref.disabled = unwrap.disabled = !st.file || p.unit !== 'Phase'; unwrap.checked = p.unwrap; if (document.activeElement !== ref) ref.value = p.phaseRef === null ? '' : fmt.fmt(p.phaseRef, 's');
    man.disabled = !st.file || (catalog.fft_impedances ?? [])[p.imp]?.[1] !== null;
    for (const c of [sort, lvl, cnt]) c.disabled = !st.file || p.unit === 'Phase';
  };
  const dispose = state.subscribe(sync);
  return { src, win, unit, imp, man, sort, lvl, cnt, ref, unwrap, dispose };
}

/** 由結果還原取樣率與完整範圍點數；短資料只能整段計算。 */
export function bandwidthLimits(r) {
  if (!r?.ok) return null;
  const fs = r.df * r.effective_n, factor = r.enbw_bins;
  if (![fs, factor, r.n].every(v => Number.isFinite(v) && v > 0)) return null;
  return { min: factor * fs / r.n, max: factor * fs / Math.min(64, r.n) };
}
export function autoBandwidth(st) {
  const r = st.fftResult, limits = bandwidthLimits(r), view = st.fftView ?? null;
  const span = view ? view.f1 - view.f0 : r?.f_max;
  if (!limits || !Number.isFinite(span) || span <= 0) return null;
  return Math.max(limits.min, Math.min(limits.max, span / 1000));
}

/** 大檢視的頻寬欄；參數仍由兩頁共用的 state 持有。 */
export function mountBandwidthControls(el, ctx) {
  const state = getFftState(ctx), { p } = state, { fmt, store } = ctx;
  const controls = {};
  for (const key of ['rbw', 'vbw']) {
    const label = document.createElement('label'), input = document.createElement('input');
    label.className = 'field'; label.textContent = key.toUpperCase() + ' ';
    input.className = 'input'; input.style.width = '6em'; input.setAttribute('aria-label', key.toUpperCase());
    input.onchange = () => {
      const text = input.value.trim(), value = !text || /^auto$/i.test(text) ? null : fmt.parseSI(text);
      if (value === null || (Number.isFinite(value) && value > 0)) state.change(key, value);
      input.value = p[key] === null ? 'Auto' : fmt.fmt(p[key], 'Hz');
    };
    label.append(input); el.append(label); controls[key] = input;
  }
  const hint = document.createElement('span'); hint.className = 'muted'; el.append(hint);
  const dispose = state.subscribe(() => {
    const st = store.get(), limits = bandwidthLimits(st.fftResult), phase = p.unit === 'Phase';
    for (const key of ['rbw', 'vbw']) {
      const input = controls[key]; input.disabled = !st.file || phase;
      if (document.activeElement !== input) input.value = p[key] === null ? 'Auto' : fmt.fmt(p[key], 'Hz');
    }
    controls.rbw.title = limits ? `可設範圍 ${fmt.fmt(limits.min, 'Hz')}～${fmt.fmt(limits.max, 'Hz')}；Auto＝Span/1000（依範圍限制）` : 'Auto＝Span/1000（有頻譜後連動）';
    controls.vbw.title = 'Auto＝不平滑；小於 RBW 時沿頻率軸平滑（本工具模擬）';
    const requested = p.rbw ?? p.autoRbw, actual = st.fftResult?.rbw;
    hint.textContent = !phase && st.fftResult?.ok && requested > 0 && Number.isFinite(actual) && Math.abs(actual / requested - 1) > 0.01 ? `已限制為 ${fmt.fmt(actual, 'Hz')}` : '';
  });
  return { ...controls, hint, dispose };
}
