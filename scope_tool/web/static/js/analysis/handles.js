// L4：左緣通道零位把手與畫面外游標提示；只發既有意圖，不寫通道／游標。
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const yPixel = (r, d) => r.t + (5 - d) * r.h / 10;
// 視覺尺寸不變，命中矩形每軸至少 24px；重疊時選中心最近者。
export const hitBox = (b) => ({ x: b.x - Math.max(0, 24 - b.w) / 2, y: b.y - Math.max(0, 24 - b.h) / 2, w: Math.max(24, b.w), h: Math.max(24, b.h) });
const contains = (b, x, y) => { const a = hitBox(b); return x >= a.x && x <= a.x + a.w && y >= a.y && y <= a.y + a.h; };

export const handleLabel = (name) => name.replace(/^Mem([1-4])\.(?:CHAN|CH)(\d+)$/, "M$1·$2").replace(/^CHAN|^CH/, "");
/** 優先在左側垂直避讓；高度不足才另開欄，命中與繪圖共用配置。 */
export function channelHandles(channels, r) {
  const placed = [], visible = channels.filter((c) => c.visible);
  const width = Math.max(16, ...visible.map((c) => (handleLabel(c.name).length + (Math.abs(c.position) > 5 ? 1 : 0)) * 8 + 8));
  return visible.map((c) => {
    const anchor = clamp(yPixel(r, c.position) - 10, 0, Math.max(0, r.t + r.h - 20));
    const candidates = [anchor];
    for (let d = 24; d <= r.t + r.h + 24; d += 24) {
      candidates.push(clamp(anchor + d, 0, Math.max(0, r.t + r.h - 20)), clamp(anchor - d, 0, Math.max(0, r.t + r.h - 20)));
    }
    let lane = 0, y;
    while ((y = candidates.find((v) => !placed.some((b) => b.lane === lane && Math.abs(b.y - v) < 24))) === undefined) lane++;
    placed.push({ lane, y });
    return { name: c.name, color: c.color, position: c.position,
      label: handleLabel(c.name) + (c.position > 5 ? "▲" : c.position < -5 ? "▼" : ""), anchorY: anchor + 10,
      x: 2 + lane * (width + 6), y, w: width, h: 20 };
  });
}
export const hitHandle = (channels, r, x, y) => channelHandles(channels, r).filter((b) => contains(b, x, y)).sort((a, b) => Math.hypot(x-a.x-a.w/2,y-a.y-a.h/2)-Math.hypot(x-b.x-b.w/2,y-b.y-b.h/2))[0] ?? null;
/** 用相對位移保留抓取點；越界貼邊的把手拖動時也不會突然跳位。 */
export const handlePosition = (position, dy, r) => position - dy * 10 / r.h;
export function moveHandle(store, name, position) {
  store.command("channel.scale_intent", { name, position });
}

/** 邊緣提示只為有限且越界的游標產生；Y 判斷完全不依賴時間視窗。 */
export function outsideCursors(cursors, view) {
  return Object.entries(cursors).flatMap(([which, value]) => {
    if (!Number.isFinite(value)) return [];
    const x = which[0] === "x", lo = x ? view.t0 : -5, hi = x ? view.t1 : 5;
    return value < lo || value > hi ? [{ which, value, direction: x ? (value < lo ? "◀" : "▶") : (value < lo ? "▼" : "▲") }] : [];
  });
}
export function cursorEdges(cursors, view, r) {
  return outsideCursors(cursors, view).map((c) => {
    const x = c.which[0] === "x", second = c.which[1] === "2";
    return { ...c, x: x ? (c.value < view.t0 ? r.l : r.l + r.w - 52) : r.l + r.w - 52,
      y: x ? r.t + (second ? 26 : 2) : (c.value > 5 ? r.t + 54 + (second ? 26 : 0) : r.t + r.h - (second ? 50 : 24)), w: 52, h: 24 };
  });
}
export const hitCursorEdge = (cursors, view, r, x, y) => cursorEdges(cursors, view, r).find((b) => contains(b, x, y)) ?? null;
export function revealCursor(store, edge, ui) {
  if (edge.which[0] === "y") {
    store.command("cursor.intent", { which: edge.which, value: edge.which === "y1" ? 2 : -2 });
    return;
  }
  const v = store.get().view, half = (v.t1 - v.t0) / 2;
  store.command("viewport.intent", { t0: edge.value - half, t1: edge.value + half });
}
export function drawHandles(g, channels, cursors, view, r) {
  g.save(); g.font = "12.5px sans-serif"; g.textBaseline = "middle"; g.textAlign = "center"; g.setLineDash([]);
  for (const b of channelHandles(channels, r)) {
    if (b.y + b.h / 2 !== b.anchorY) {
      g.strokeStyle = b.color; g.beginPath(); g.moveTo(b.x + b.w, b.y + b.h / 2);
      g.lineTo(b.x + b.w + 3, b.anchorY); g.stroke();
    }
    g.fillStyle = b.color; g.fillRect(b.x, b.y, b.w - 1, b.h);
    g.fillStyle = "#000"; g.fillText(b.label, b.x + b.w / 2, b.y + b.h / 2);
  }
  for (const b of cursorEdges(cursors, view, r)) {
    g.fillStyle = "#fff"; g.fillRect(b.x, b.y, b.w, b.h);
    g.fillStyle = "#333"; g.fillText(`${b.direction} ${b.which}`, b.x + b.w / 2, b.y + b.h / 2);
  }
  g.restore();
}
