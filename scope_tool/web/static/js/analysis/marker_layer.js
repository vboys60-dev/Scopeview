// 圖上只做投影／命中與拖曳預覽，放開才送模型吸附。
import { createMarkerMenu, markerMenuItems } from './marker_menu.js';
import { markerModel } from './markers.js';
import { linear, nearestDist } from './plotcore.js';
const inside = (r, x, y) => x >= r.l && x <= r.l + r.w && y >= r.t && y <= r.t + r.h;
export function markerPoints(model, state, r) {
  const X = linear(state.view.t0, state.view.t1, r.l, r.l + r.w);
  return model.rows().filter(p => p.channel.visible && Number.isFinite(p.value)).map(p => ({ ...p,
    x: X(p.t), y: r.t + (5 - p.value / p.channel.scale - p.channel.position) * r.h / 10,
  })).filter(p => inside(r, p.x, p.y));
}
export function hitMarker(points, x, y) {
  return points.map(p => ({ p, d: Math.hypot(p.x - x, p.y - y) })).filter(p => p.d <= 6).sort((a, b) => a.d - b.d)[0]?.p ?? null;
}
export function nearestChannel(channels, cache, x, y, selected) {
  const hits = channels.filter(c => c.visible && cache.get(c.name)?.px).map(c => ({ name: c.name, d: nearestDist(cache.get(c.name).px, x, y, 8) })).filter(c => Number.isFinite(c.d)).sort((a, b) => a.d - b.d);
  return hits[0]?.name ?? selected;
}
export function createMarkerLayer(canvas, ctx, geometry, cache, draw) {
  const { store } = ctx, model = markerModel(ctx), menu = createMarkerMenu();
  const points = () => markerPoints(model, store.get(), geometry());
  const time = x => { const r = geometry(), v = store.get().view; return linear(v.t0, v.t1, r.l, r.l + r.w).inv(x); };
  const context = e => {
    const b = canvas.getBoundingClientRect(), x = e.clientX - b.left, y = e.clientY - b.top;
    if (!inside(geometry(), x, y) || !store.get().file) return;
    e.preventDefault();
    const st = store.get(), ch = nearestChannel(st.channels, cache, x, y, st.selected);
    menu.open(e.clientX, e.clientY, markerMenuItems(st, ch, time(x), hitMarker(points(), x, y), model));
  };
  canvas.addEventListener('contextmenu', context);
  const off = model.on(draw), offFile = store.on(['file'], menu.close);
  return {
    hit: (x, y) => hitMarker(points(), x, y),
    hover(x, y) { const p = hitMarker(points(), x, y); model.hover(p?.key ?? null); return p; },
    begin(p) { model.select(p.key, false); return p; },
    move(p, x) { model.preview(p.id, time(x)); },
    end(p, x, commit) { model.preview(null); if (commit) model.move({ id: p.id, t: time(x) }); else model.refresh(); },
    remove() { const p = model.rows().find(p => p.key === model.selected); if (p) model.remove(p.id); },
    draw(g) {
      g.save(); g.setLineDash([]); g.font = '12.5px sans-serif'; g.textAlign = 'left'; g.textBaseline = 'bottom';
      for (const p of points()) {
        const active = model.selected === p.key || model.hovered === p.key;
        g.strokeStyle = p.channel.color; g.fillStyle = active ? '#fff' : p.channel.color; g.lineWidth = active ? 3 : 1;
        g.beginPath(); g.arc(p.x, p.y, active ? 6 : 4, 0, 2 * Math.PI); g.fill(); g.stroke();
        g.fillText(`${p.id}${p.note ? ' ' + [...p.note].slice(0, 12).join('') : ''}`, p.x + 8, p.y - 5);
      }
      g.restore();
    },
    dispose() { menu.close(); offFile(); off(); canvas.removeEventListener?.('contextmenu', context); },
  };
}
