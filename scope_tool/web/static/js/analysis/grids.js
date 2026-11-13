// 分割格線：純幾何與偏好儲存；隱藏通道仍保留原本格位。
export const GRID_COUNTS = [1, 2, 4, 8];
export const GRID_GAP = 4;
export const GRIDS_KEY = "scope.analysis.grids.v1";
const defaults = () => ({ n: 1, assign: {} });
const object = v => v !== null && typeof v === 'object' && !Array.isArray(v);
export function gridsOf(s) {
  const g = s?.grids;
  return object(g) && GRID_COUNTS.includes(g.n) && object(g.assign) ? g : defaults();
}
export function gridIndex(grids, channels, name) {
  const g = gridsOf({ grids }), k = g.assign[name];
  return Number.isInteger(k) && k >= 0 && k < g.n ? k : Math.max(0, channels.findIndex(c => c.name === name)) % g.n;
}
export function gridRows(base, grids, channels) {
  const g = gridsOf({ grids }), h = (base.h - GRID_GAP * (g.n - 1)) / g.n;
  return Array.from({ length: g.n }, (_, index) => ({ l: base.l, t: base.t + index * (h + GRID_GAP), w: base.w, h, index,
    names: channels.filter(c => gridIndex(g, channels, c.name) === index).map(c => c.name) }));
}
export function withGrids(base, grids, channels, cursorName) {
  const rows = gridRows(base, grids, channels), of = name => rows[gridIndex(grids, channels, name)];
  const at = y => rows[Math.max(0, Math.min(rows.length - 1, Math.floor((y - base.t) / (rows[0].h + GRID_GAP))))];
  return { ...base, rows, of, at, cy: cursorName ? of(cursorName) : rows[0] };
}
export const rowOf = (r, name) => r.of?.(name) ?? r;
export const rowAt = (r, y) => r.at?.(y) ?? r;
export function setCount(grids, n) {
  const g = gridsOf({ grids });
  return { n: GRID_COUNTS.includes(n) ? n : 1, assign: { ...g.assign } };
}
export function assignGrid(grids, name, index) {
  const g = gridsOf({ grids }), assign = { ...g.assign };
  if (Number.isInteger(index) && index >= 0 && index < 8) assign[name] = index;
  else delete assign[name];
  return { n: g.n, assign };
}
function clean(grids) {
  const g = gridsOf({ grids });
  return { n: g.n, assign: Object.fromEntries(Object.entries(g.assign).filter(([, v]) => Number.isInteger(v) && v >= 0 && v < 8)) };
}
export function loadGrids(storage) {
  try { return clean(JSON.parse((storage ?? globalThis.localStorage).getItem(GRIDS_KEY))); } catch { return defaults(); }
}
export function saveGrids(grids, storage) {
  try { (storage ?? globalThis.localStorage).setItem(GRIDS_KEY, JSON.stringify(clean(grids))); } catch { /* 儲存不可用時仍可繪圖。 */ }
}
export function bindGrids(store, storage) {
  if (store.get().grids === undefined) store.set({ grids: loadGrids(storage) }, 'program');
  return store.on(['grids'], s => saveGrids(s.grids, storage));
}

/** 每格保留原通道順序與可見狀態，堆疊時才篩選有效通道。 */
export function groupByGrid(grids, channels) {
  const groups = Array.from({ length: gridsOf({ grids }).n }, () => []);
  for (const c of channels) groups[gridIndex(grids, channels, c.name)].push(c);
  return groups;
}
export function gridMenuItems(store, item) {
  const items = GRID_COUNTS.map(n => {
    const el = item(`${n} 格`, () => store.command("view.zoomRect", { grids: setCount(gridsOf(store.get()), n) }));
    el.setAttribute('role', 'menuitem');
    return el;
  });
  const sync = () => items.forEach((el, i) => {
    if (GRID_COUNTS[i] === gridsOf(store.get()).n) el.setAttribute('aria-current', 'true');
    else el.removeAttribute('aria-current');
  });
  store.on(['grids'], sync); sync();
  return items;
}
export function gridSelect(store, name) {
  const el = document.createElement('select'); el.className = 'chip__grid'; el.setAttribute('aria-label', '所在格');
  let count = 0;
  const sync = () => {
    const st = store.get(), grids = gridsOf(st);
    el.hidden = grids.n === 1;
    if (count !== grids.n) {
      count = grids.n;
      el.replaceChildren(...Array.from({ length: count }, (_, i) => {
        const option = document.createElement('option'); option.textContent = `格 ${i + 1}`; option.value = String(i); return option;
      }));
    }
    el.value = String(gridIndex(grids, st.channels, name));
  };
  el.onchange = () => store.command('view.zoomRect', { grids: assignGrid(gridsOf(store.get()), name, Number(el.value)) });
  sync();
  return { el, sync };
}
