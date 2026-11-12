// L4：框選／平移與視圖歷史；通道只經既有意圖套用。
import { DEFAULT_ZOOM_KIND, ZOOM_KINDS, verticalRect } from "./vzoom.js";
import { fullRange } from "./overview.js";
import { linear, wheelFactor, plotColors } from "./plotcore.js";
import { hitHandle, handlePosition, moveHandle, hitCursorEdge, revealCursor } from "./handles.js";
export const DEFAULT_MODE = "pan";
export const RECT_MIN_PX = 6;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const same = (a, b) => a.t0 === b.t0 && a.t1 === b.t1 && JSON.stringify(a.channels) === JSON.stringify(b.channels);
export const editableTarget = (el) => !!el && (!!el.isContentEditable || /^(INPUT|TEXTAREA|SELECT|BUTTON|SUMMARY|A)$/i.test(el.tagName ?? el.tag ?? "") || !!el.closest?.('[contenteditable]:not([contenteditable="false"]), [role="button"]'));
export function shortcutFor(e, target = e.target) {
  if (editableTarget(target) || e.isComposing || e.altKey) return null;
  if ((e.metaKey || e.ctrlKey) && e.key?.toLowerCase() === "z") return e.shiftKey ? "view.redo" : "view.undo";
  if ((e.metaKey || e.ctrlKey) && e.key?.toLowerCase() === "y") return "view.redo";
  if (e.code === "Space" || e.key === " ") return "space";
  return e.key === "Escape" ? "cancel" : null;
}
/** pointerdown 時固定動作；零位 > 邊緣游標 > Marker 點 > 平移模式游標線 > 模式手勢。 */
export function gestureFor({ button = 0, mode = DEFAULT_MODE, shiftKey = false, space = false, handle = false, edge = false, cursor = false, marker = false, inside = true }) {
  if (button !== 0 && button !== 1) return null;
  if (handle) return "handle";
  if (edge) return "edge";
  if (marker && button === 0) return "marker";
  if (button === 1 || space) return inside ? "pan" : null;
  const zoom = mode === "zoom" || shiftKey;
  if (!zoom && cursor) return "cursor";
  return inside ? (zoom ? "zoom" : "pan") : null;
}
/** 最少十個取樣間隔與浮點精度；極短檔案以全長為上限。 */
export function viewLimits(file) {
  const f = fullRange(file);
  if (!f || !(f.t1 > f.t0)) return null;
  const span = f.t1 - f.t0;
  const dt = Math.min(...file.channels.filter((c) => c.points > 1 && c.t1 > c.t0).map((c) => (c.t1 - c.t0) / (c.points - 1)));
  const precision = Math.max(Math.abs(f.t0), Math.abs(f.t1), span) * Number.EPSILON * 32;
  return { ...f, minSpan: Math.min(span, Math.max(Number.isFinite(dt) ? 10 * dt : span * 1e-9, precision)), maxSpan: span * 10 };
}
export function limitView(v, limits, contained = false) {
  if (!v || !limits || !Number.isFinite(v.t0) || !Number.isFinite(v.t1) || !(v.t1 > v.t0)) return null;
  if (v.t1 - v.t0 >= limits.minSpan && v.t1 - v.t0 <= (contained ? limits.t1 - limits.t0 : limits.maxSpan) && (!contained || v.t0 >= limits.t0 && v.t1 <= limits.t1)) return { t0: v.t0, t1: v.t1 };
  const span = clamp(v.t1 - v.t0, limits.minSpan, contained ? limits.t1 - limits.t0 : limits.maxSpan);
  let t0 = v.t0 + (v.t1 - v.t0) / 2 - span / 2;
  if (contained) t0 = clamp(t0, limits.t0, limits.t1 - span);
  const t1 = t0 + span;
  return Number.isFinite(t0) && Number.isFinite(t1) && t1 > t0 ? { t0, t1 } : null;
}
export function zoomToRect(view, a, b, rect, limits) {
  a = clamp(a, rect.l, rect.l + rect.w); b = clamp(b, rect.l, rect.l + rect.w);
  if (Math.abs(b - a) < RECT_MIN_PX) return null;
  const X = linear(view.t0, view.t1, rect.l, rect.l + rect.w);
  return limitView({ t0: X.inv(Math.min(a, b)), t1: X.inv(Math.max(a, b)) }, limits, true);
}
/** 獨立於 DOM／時鐘；一段拖曳可跨越 300ms。Undo／Redo 可傳函式，依目標項目取得局部快照。 */
export function createHistory(limit = 50) {
  let past = [], future = [], last = null;
  return {
    record(before, after, { key = null, time = 0, continuous = false } = {}) {
      if (same(before, after)) return;
      const merge = key && last?.key === key && (continuous || time - last.time <= 300);
      if (!merge) { past.push({ ...before }); if (past.length > limit) past.shift(); }
      future = [];
      last = key ? { key, time } : null;
    },
    undo(current) { last = null; if (!past.length) return null; future.push({ ...(typeof current === "function" ? current(past.at(-1)) : current) }); return past.pop(); },
    redo(current) { last = null; if (!future.length) return null; past.push({ ...(typeof current === "function" ? current(future.at(-1)) : current) }); return future.pop(); },
    end() { last = null; },
    clear() { past = []; future = []; last = null; },
    status: () => ({ undo: past.length, redo: future.length }),
  };
}
/** 時間與框選共用歷史；還原只送 scale／position，不回寫其他通道欄位。 */
export function bindViewport(store) {
  const history = createHistory();
  let group = {};
  const snapshot = (item) => ({
    ...(item.t0 !== undefined ? store.get().view : {}),
    ...(item.channels ? { channels: store.get().channels.filter((c) => item.channels.some((n) => n.name === c.name)).map((c) => Object.fromEntries(Object.keys(item.channels.find(n => n.name === c.name)).map(k => [k, c[k] ?? (k === "time_offset" ? 0 : c[k])]))) } : {}),
  });
  const apply = (next) => {
    if (next.t0 !== undefined) store.set({ view: { t0: next.t0, t1: next.t1 } }, "user");
    for (const c of next.channels ?? []) {
      const current = store.get().channels.find((ch) => ch.name === c.name);
      if (current && "time_offset" in c) store.updateChannel(c.name, { time_offset: c.time_offset }, "user");
      if (current && "scale" in c && (current.scale !== c.scale || current.position !== c.position)) store.command("channel.scale_intent", c);
    }
  };
  const notify = () => store.command("view.history", history.status());
  store.onCommand("view.historyGroup", (p) => { group = p ?? {}; if (p?.end) history.end(); });
  store.onCommand("viewport.intent", (p) => {
    const before = { ...store.get().view }, next = limitView(p, viewLimits(store.get().file));
    if (!next) return;
    history.record(before, next, { ...group, time: Date.now() });
    apply(next); notify();
  });
  store.onCommand("view.zoomRect", ({ view, channels = [] }) => {
    const valid = view ? limitView(view, viewLimits(store.get().file)) : null;
    if (view && !valid) return;
    const changed = channels.filter((n) => store.get().channels.some((c) => c.name === n.name && ("time_offset" in n ? (c.time_offset ?? 0) !== n.time_offset : c.visible && (c.scale !== n.scale || c.position !== n.position))));
    const next = { ...(valid && !same(valid, store.get().view) ? valid : {}), ...(changed.length ? { channels: changed } : {}) };
    const before = snapshot(next);
    history.end(); history.record(before, next); apply(next); notify();
  });
  for (const action of ["undo", "redo"]) store.onCommand(`view.${action}`, () => {
    const next = history[action](snapshot);
    if (next) apply(next);
    notify();
  });
  store.onCommand("view.reset", () => { const f = fullRange(store.get().file); if (f) store.command("viewport.intent", f); });
  store.on(["file"], () => { group = {}; history.clear(); notify(); });
  return history;
}

export const cursorRadius = (pointerType) => pointerType === "touch" ? 12 : 8;
/** 線命中半徑滑鼠／筆 ±8px、觸控 ±12px；等距時按 x1、x2、y1、y2 順序決定。 */
export function nearestCursor(cursors, view, r, x, y, pointerType) {
  if (x < r.l || x > r.l + r.w || y < r.t || y > r.t + r.h) return null;
  const X = linear(view.t0, view.t1, r.l, r.l + r.w);
  const radius = cursorRadius(pointerType);
  let best = null, distance = radius;
  for (const k of ["x1", "x2", "y1", "y2"]) {
    if (!Number.isFinite(cursors[k])) continue;
    if (k[0] === "x" && (cursors[k] < view.t0 || cursors[k] > view.t1)) continue;
    const d = Math.abs(k[0] === "x" ? X(cursors[k]) - x : r.t + (5 - cursors[k]) * r.h / 10 - y);
    if (d <= radius && (best === null || d < distance)) { best = k; distance = d; }
  }
  return best;
}
/** 主圖互動由此集中管理，繪圖仍由 mainplot 負責。 */
export function bindGestures(canvas, { store, ui }, geometry, draw, markers = null) {
  let drag = null, mode = DEFAULT_MODE, zoomKind = DEFAULT_ZOOM_KIND, space = false, edgeDownAt = -Infinity, hover = null, pointer = null;
  const listeners = [];
  canvas.tabIndex = 0;
  const on = (el, key, fn, opts) => { if (!el?.addEventListener) return; el.addEventListener(key, fn, opts); listeners.push(() => el.removeEventListener?.(key, fn, opts)); };
  const local = (e) => { const b = canvas.getBoundingClientRect(); return [e.clientX - b.left, e.clientY - b.top]; };
  const X = (view) => { const r = geometry(); return linear(view.t0, view.t1, r.l, r.l + r.w); };
  const inside = (x, y) => { const r = geometry(); return x >= r.l && x <= r.l + r.w && y >= r.t && y <= r.t + r.h; };
  function hitCursor(x, y, pointerType) {
    if (!inside(x, y)) return null;
    const s = store.get(), r = geometry();
    return nearestCursor(s.cursors, s.view, r, x, y, pointerType);
  }
  const updateHover = () => {
    const next = !drag && pointer && store.get().file && mode === "pan" && !space && !pointer.shiftKey ? hitCursor(pointer.x, pointer.y, pointer.pointerType) : null;
    if (next === hover) return false;
    hover = next; draw(); return true;
  };
  const end = () => {
    const d = drag; drag = null;
    if (d?.type === "marker") markers?.end(d.marker, d.current, false);
    if (d?.type === "pan") store.command("view.historyGroup", { end: true });
    if (d && canvas.hasPointerCapture?.(d.id)) canvas.releasePointerCapture(d.id);
    if (!updateHover() && d) draw();
  };
  let draggingView = false;
  const offGroup = store.onCommand("view.historyGroup", (p) => { draggingView = !!p?.continuous; });
  on(canvas, "mousedown", (e) => { if (e.button === 1) e.preventDefault(); });
  const offMode = store.onCommand("view.mode", (v) => { if (["pan", "zoom"].includes(v)) { end(); mode = v; updateHover(); canvas.style.cursor = mode === "zoom" ? "crosshair" : "grab"; } });
  const offKind = store.onCommand("view.zoomKind", (v) => { if (ZOOM_KINDS.includes(v)) { end(); zoomKind = v; } });
  on(canvas, "pointerdown", (e) => {
    if (e.ctrlKey && e.button === 0) return; // macOS 的 Ctrl＋左鍵交由右鍵選單處理。
    if (drag || !store.get().file && !store.get().channels.length) return;
    if (e.button !== 0 && e.button !== 1) return;
    canvas.focus?.({ preventScroll: true }); // 先讓欄位 blur 提交，再取得拖曳起始 view。
    const [x, y] = local(e), s = store.get(), r = geometry();
    pointer = { x, y, shiftKey: !!e.shiftKey, pointerType: e.pointerType };
    const handle = hitHandle(s.channels, r, x, y), edge = hitCursorEdge(s.cursors, s.view, r, x, y), which = hitCursor(x, y, e.pointerType);
    const marker = markers?.hit(x, y);
    const type = gestureFor({ ...e, button: e.button, shiftKey: e.shiftKey, mode, space: space && !editableTarget(document.activeElement), handle: !!handle, edge: !!edge, cursor: !!which, marker: !!marker, inside: inside(x, y) });
    if (type === "edge") { edgeDownAt = e.timeStamp; revealCursor(store, edge, ui); return; }
    if (!type) return;
    e.preventDefault?.();
    drag = { type, marker: type === "marker" ? markers.begin(marker) : null, x, y, current: x, currentY: y, zoomKind, view: { ...s.view }, name: handle?.name, position: handle?.position, which, id: e.pointerId, moved: false };
    if (type === "pan") store.command("view.historyGroup", { key: "pan", continuous: true });
    canvas.setPointerCapture(e.pointerId);
  });
  on(canvas, "pointermove", (e) => {
    const [x, y] = local(e), r = geometry(), s = store.get();
    pointer = { x, y, shiftKey: !!e.shiftKey, pointerType: e.pointerType };
    if (!drag) {
      const marker = markers?.hover(x, y); updateHover();
      canvas.title = hitHandle(s.channels, r, x, y)?.name ?? "";
      canvas.style.cursor = hitHandle(s.channels, r, x, y) ? "ns-resize" : hitCursorEdge(s.cursors, s.view, r, x, y) ? "pointer" : marker ? "move" : hover ? (hover[0] === "x" ? "ew-resize" : "ns-resize") : inside(x, y) ? (space || mode === "pan" && !e.shiftKey ? "grab" : "crosshair") : "default"; return; }
    const d = drag;
    if (e.pointerId !== d.id) return;
    d.current = x; d.currentY = y; d.moved ||= Math.hypot(x - d.x, y - d.y) >= 4;
    if (!d.moved) return;
    if (d.type === "marker") markers.move(d.marker, x, y);
    else if (d.type === "zoom") draw();
    else if (d.type === "handle") moveHandle(store, d.name, handlePosition(d.position, y - d.y, r));
    else if (d.type === "pan") { const dt = -(x - d.x) * (d.view.t1 - d.view.t0) / r.w; store.command("viewport.intent", { t0: d.view.t0 + dt, t1: d.view.t1 + dt }); }
    else store.command("cursor.intent", { which: d.which, value: d.which[0] === "x" ? X(d.view).inv(x) : 5 - (y - r.t) * 10 / r.h });
  });
  on(canvas, "pointerup", (e) => {
    if (!drag || e.pointerId !== drag.id) return;
    if (drag.type === "marker") { const d = drag; drag = null; markers.end(d.marker, local(e)[0], d.moved); if (canvas.hasPointerCapture?.(d.id)) canvas.releasePointerCapture(d.id); updateHover(); return; }
    if (drag.type === "zoom") {
      const d = drag, [x, y] = local(e), r = geometry();
      const view = d.zoomKind !== "vertical" ? zoomToRect(d.view, d.x, x, r, viewLimits(store.get().file)) : null;
      const channels = d.zoomKind !== "horizontal" ? verticalRect(store.get().channels, d.y, y, r, RECT_MIN_PX) : [];
      if (view || channels.length) store.command("view.zoomRect", { view, channels });
    }
    end();
  });
  for (const name of ["pointercancel", "lostpointercapture"]) on(canvas, name, end);
  on(window, "blur", () => { space = false; end(); });
  on(window, "keydown", (e) => {
    if (canvas.closest?.("[hidden]")) return;
    if (e.key === "Escape" && drag) { end(); return; }
    if (["Delete", "Backspace"].includes(e.key) && !editableTarget(document.activeElement ?? e.target) && document.activeElement === canvas) { e.preventDefault(); markers?.remove(); return; }
    const action = shortcutFor(e, document.activeElement ?? e.target);
    if (!action) return;
    if (action === "space") { space = true; updateHover(); e.preventDefault(); }
    else if (action === "cancel") end();
    else { e.preventDefault(); end(); store.command(action); }
  });
  on(window, "keyup", (e) => { if (e.code === "Space" || e.key === " ") { space = false; updateHover(); } });
  on(canvas, "dblclick", (e) => {
    if (e.timeStamp >= edgeDownAt && e.timeStamp - edgeDownAt <= 500) return;
    const [x, y] = local(e), s = store.get(), r = geometry(), handle = hitHandle(s.channels, r, x, y);
    if (handle) moveHandle(store, handle.name, 0);
    else if (mode === "pan" && !hitCursorEdge(s.cursors, s.view, r, x, y)) store.command("view.reset");
  });
  on(canvas, "wheel", (e) => {
    e.preventDefault();
    // 拖曳中忽略主圖滾輪，避免中斷 pan／overview 的歷史群組。
    if (drag || draggingView) return;
    const [x] = local(e), r = geometry(), v = store.get().view, factor = wheelFactor(e, r.h);
    if (factor === 1) return;
    const a = X(v).inv(clamp(x, r.l, r.l + r.w));
    store.command("view.historyGroup", { key: "wheel" });
    store.command("viewport.intent", { t0: a - (a - v.t0) * factor, t1: a + (v.t1 - a) * factor });
    store.command("view.historyGroup");
  }, { passive: false });
  on(canvas, "pointerleave", () => { pointer = null; canvas.title = ""; markers?.hover(-Infinity, -Infinity); updateHover(); });
  const offHover = store.on(["cursors", "view", "channels"], updateHover);
  const offFile = store.on(["file"], () => { draggingView = false; end(); });
  return {
    hovered: () => hover,
    overlay(g) {
      if (drag?.type !== "zoom" || !drag.moved) return;
      const r = geometry(), a = clamp(Math.min(drag.x, drag.current), r.l, r.l + r.w), b = clamp(Math.max(drag.x, drag.current), r.l, r.l + r.w);
      g.save(); g.fillStyle = plotColors().ovShade; g.strokeStyle = plotColors().ovWin; g.setLineDash([]);
      const top = drag.zoomKind === "horizontal" ? r.t : clamp(Math.min(drag.y, drag.currentY), r.t, r.t + r.h);
      const bottom = drag.zoomKind === "horizontal" ? r.t + r.h : clamp(Math.max(drag.y, drag.currentY), r.t, r.t + r.h);
      const left = drag.zoomKind === "vertical" ? r.l : a, width = drag.zoomKind === "vertical" ? r.w : b - a;
      g.fillRect(left, top, width, bottom - top);
      if (drag.zoomKind === "vertical") { g.beginPath(); g.moveTo(left, top); g.lineTo(left + width, top); g.moveTo(left, bottom); g.lineTo(left + width, bottom); g.stroke(); }
      else g.strokeRect(left, top, width, bottom - top);
      g.restore();
    },
    dispose() { end(); listeners.forEach((off) => off()); offMode(); offKind(); offFile(); offGroup(); offHover(); },
  };
}
