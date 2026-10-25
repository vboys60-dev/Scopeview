// 時域 Marker 唯一寫入者；讀值只留暫存，不放進 markerTable，也不碰游標。
const models = new WeakMap();
const finite = Number.isFinite;
export function markerModel(ctx) {
  if (models.has(ctx.store)) return models.get(ctx.store);
  const { store, bridge, ui } = ctx;
  let serial = 1, token = 0, timer, gen = store.get().file?.gen;
  let readings = new Map(), selected = null, hovered = null, preview = null;
  const listeners = new Set();
  const notify = () => listeners.forEach(fn => fn());
  store.set({ markerTable: [] });
  const entries = () => store.get().markerTable;
  // 僅時間位移／通道集合使讀值失效；註記不影響吸附。
  const channelKey = s => JSON.stringify(s.channels.map(c => [c.name, c.time_offset || 0]).sort((a, b) => a[0].localeCompare(b[0])));
  const pointKey = s => JSON.stringify(s.markerTable.map(({ note, ...p }) => p));
  let channelsKey = channelKey(store.get()), pointsKey = pointKey(store.get());
  const display = (p, ch) => p.link ? p.t : p.t_src + (ch.time_offset || 0);
  const model = { on(fn) { listeners.add(fn); return () => listeners.delete(fn); },
    get selected() { return selected; }, get hovered() { return hovered; },
    hover(id) { if (hovered !== id) { hovered = id; notify(); } },
    rows() {
      const st = store.get(), base = entries().find(p => p.link);
      return entries().flatMap(p => st.channels.filter(ch => p.link || ch.name === p.ch).map(ch => {
        const key = `${p.id}:${ch.name}`, r = readings.get(key), t = preview?.id === p.id ? preview.t : display(p, ch);
        return { ...p, key, ch: ch.name, channel: ch, t: r && !preview ? r.t : t,
          value: r?.value ?? null, dt: base ? (r && !preview ? r.t : t) - base.t : null };
      }));
    },
    add({ ch = store.get().selected, t, link = false } = {}) {
      if (!store.get().file || !finite(t) || !store.get().channels.some(c => c.name === ch)) return false;
      if (link && entries().some(p => p.link)) return model.move({ id: 'M1', t });
      if (!link && entries().filter(p => !p.link && p.ch === ch).length >= 10) {
        ui?.toast?.('每通道最多 10 個獨立 Marker', 'info'); return false;
      }
      const channel = store.get().channels.find(c => c.name === ch);
      const p = link ? { id: 'M1', ch, t, link: true, note: '' } : { id: `M${++serial}`, ch, t_src: t - (channel.time_offset || 0), link: false, note: '' };
      store.set({ markerTable: [...entries(), p] }, 'user'); return true;
    },
    move({ id, t }) {
      if (!finite(t)) return false;
      store.set({ markerTable: entries().map(p => {
        const ch = store.get().channels.find(c => c.name === p.ch);
        return p.id !== id || (!p.link && !ch) ? p : p.link ? { ...p, t } : { ...p, t_src: t - (ch.time_offset || 0) };
      }) }, 'user'); return true;
    },
    preview(id, t) { token++; clearTimeout(timer); preview = id ? { id, t } : null; notify(); },
    remove(id) { store.set({ markerTable: entries().filter(p => p.id !== id) }, 'user'); },
    note({ id, note }) { store.set({ markerTable: entries().map(p => p.id === id ? { ...p, note: String(note) } : p) }, 'user'); },
    select(key, reveal = true) {
      selected = key; const row = model.rows().find(r => r.key === key), v = store.get().view;
      if (reveal && row && (row.t < v.t0 || row.t > v.t1)) {
        store.command('view.historyGroup', { end: true });
        const half = (v.t1 - v.t0) / 2;
        store.command('viewport.intent', { t0: row.t - half, t1: row.t + half });
      }
      notify();
    },
    async refresh() {
      clearTimeout(timer); const my = ++token, st = store.get(), fileGen = st.file?.gen;
      if (!st.file || preview) return;
      const alive = () => my === token && !preview && fileGen === store.get().file?.gen;
      const next = new Map(), snapped = new Map();
      try {
        const link = entries().find(p => p.link);
        // M1 先依傳統讀值吸附時間，各通道再依自己的原始取樣點求值。
        const legacy = link ? await bridge.call('cursor_readout', { t1: link.t, t2: link.t, dx: Object.fromEntries(st.channels.map(c => [c.name, c.time_offset || 0])) }) : null;
        if (!alive()) return;
        const first = st.channels[0], dx = first?.time_offset || 0;
        if (link && first && link.t >= first.t0 + dx && link.t <= first.t1 + dx && finite(legacy?.t1) && legacy.t1 !== link.t) {
          store.set({ markerTable: entries().map(p => p.link ? { ...p, t: legacy.t1 } : p) }, 'snap');
        }
        for (const row of model.rows()) {
          // 表格暫用舊讀值；吸附必須取模型的新時間，不能沿用快取時間。
          const ch = row.channel, t = display(entries().find(p => p.id === row.id), ch);
          const src = row.link ? t - (ch.time_offset || 0) : row.t_src;
          if (src < ch.t0 || src > ch.t1) { next.set(row.key, { t, value: null }); continue; }
          const r = await bridge.call('marker_eval', { mode: 'Track Waveforms', channel: ch.name, x1: src, x2: src, y1: null, y2: null, screen_width: ch.t1 - ch.t0, measurements: [] });
          if (!alive()) return;
          const value = r.available && finite(r.position.y1) ? r.position.y1 : null;
          next.set(row.key, { t: finite(r.position.x1) ? r.position.x1 + (ch.time_offset || 0) : t, value });
          if (!row.link && finite(r.position.x1)) snapped.set(row.id, r.position.x1);
        }
        if (!alive()) return;
        readings = next;
        const updated = entries().map(p => snapped.has(p.id) ? { ...p, t_src: snapped.get(p.id) } : p);
        if (updated.some((p, i) => p.t_src !== entries()[i].t_src)) store.set({ markerTable: updated }, 'snap');
        notify();
      } catch (e) {
        if (alive() && e.code !== 'STALE') {
          if (ui?.toast) ui.toast(e.message, 'error');
          else ui?.showError?.(e, 'Marker 讀值失敗');
        }
      }
    },
  };
  const schedule = () => { token++; clearTimeout(timer); timer = setTimeout(() => model.refresh(), 40); };
  store.on(['markerTable', 'channels', 'file'], (s, keys, origin) => {
    const nextChannels = channelKey(s), nextPoints = pointKey(s);
    const channelsChanged = nextChannels !== channelsKey, pointsChanged = nextPoints !== pointsKey;
    channelsKey = nextChannels; pointsKey = nextPoints;
    if (keys.includes('file') && s.file?.gen !== gen) {
      gen = s.file?.gen; token++; clearTimeout(timer); readings.clear(); selected = hovered = preview = null; serial = 1;
      store.set({ markerTable: [] }); notify(); return;
    }
    if (channelsChanged) readings.clear();
    if (origin !== 'snap' && (pointsChanged || keys.includes('channels') || keys.includes('file'))) schedule();
    notify();
  });
  for (const [name, fn] of [['add', model.add], ['move', model.move], ['remove', model.remove], ['note', model.note]]) store.onCommand(`marker.${name}`, fn);
  store.onCommand('marker.link', p => model.add({ ...p, link: true }));
  models.set(store, model); return model;
}
