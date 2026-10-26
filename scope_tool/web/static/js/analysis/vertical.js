// L5：各通道的 Vertical 欄位；沿用通道列唯一換檔／微調入口。
import { tickLabel } from "./plotcore.js";
export const centerPotential = (c) => -c.position * c.scale + 0;
export const positionOf = (value, scale) => -value / scale + 0;
export const hasDx = (c) => Number.isFinite(c?.time_offset) && c.time_offset !== 0;
/** 包絡包含可見範圍內的極值；NaN 缺口忽略，全空不提交。 */
export function fitEnvelope(env, unit, scales) {
  let lo = Infinity, hi = -Infinity;
  for (let i = 0; i < env.n; i++) {
    if (Number.isFinite(env.lo[i])) lo = Math.min(lo, env.lo[i]);
    if (Number.isFinite(env.hi[i])) hi = Math.max(hi, env.hi[i]);
  }
  if (!(lo <= hi)) return null;
  const [scale, position] = scales.autoScale(lo, hi, unit);
  return { scale, position };
}
const h = (tag, text, cls) => { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; if (cls) e.className = cls; return e; };
export function mount(el, { store, bridge, ui, fmt, scales }, changes, name) {
  el.classList.add("vertical");
  const current = () => store.get().channels.find((c) => c.name === name);
  const button = (text, fn, title = text) => { const b = h("button", text, "btn btn--small"); b.type = "button"; b.title = title; b.onclick = fn; return b; };
  function field(label, key, unit) {
    const wrap = h("div", undefined, "vertical__field"), input = h("input", undefined, "input");
    input.type = "text"; input.dataset.vertical = key; input.title = label;
    input.setAttribute("aria-label", label);
    const apply = (value = fmt.parseSI(input.value)) => {
      const c = current(); if (!c) return;
      if (Number.isFinite(value)) {
        const patch = key === "scale" ? changes.scaleChange(c, changes.clampScale(value, c.unit, scales), scales)
          : key === "position" ? { position: positionOf(value, c.scale) } : { time_offset: value };
        if (Object.values(patch).every(Number.isFinite) && Object.entries(patch).some(([k, v]) => c[k] !== v)) store.updateChannel(c.name, patch, "user");
      }
      render(true);
    };
    const step = (up, fine = false) => {
      const c = current(); if (!c) return;
      const typed = fmt.parseSI(input.value), base = Number.isFinite(typed) ? typed : key === "scale" ? c.scale : centerPotential(c);
      apply(key === "scale" ? (fine ? changes.fineScale : changes.coarseScale)(base, c.unit, up, scales) : base + (up ? c.scale : -c.scale));
    };
    const commit = () => { if (input.value !== input.dataset.rendered) apply(); };
    input.onchange = commit; input.onblur = commit;
    input.onkeydown = (e) => {
      if (e.isComposing || e.altKey || e.metaKey || e.ctrlKey) return;
      if (e.key === "Enter") { e.preventDefault(); input.blur(); }
      else if (key !== "dx" && ["ArrowUp", "ArrowDown"].includes(e.key)) { e.preventDefault(); step(e.key === "ArrowUp", !e.shiftKey); }
    };
    wrap.append(h("span", label));
    if (key !== "dx") wrap.append(button("▼", () => step(false), `${label}減小一${key === "scale" ? "檔（波形較高）" : "格"}`));
    wrap.append(input);
    if (key === "position") wrap.append(button("歸零", () => { const c = current(); if (c) store.updateChannel(c.name, { position: 0 }, "user"); }));
    if (key !== "dx") wrap.append(button("▲", () => step(true), `${label}增大一${key === "scale" ? "檔（波形較矮）" : "格"}`));
    if (key === "scale") {
      input.title = "每格大小（如 130m）；↑↓／−+ 微調，Shift＋↑↓／▲▼ 粗調";
      wrap.append(button("−", () => step(false, true), "每格大小微減（V：10 mV；其他：5%）"), button("+", () => step(true, true), "每格大小微增（V：10 mV；其他：5%）"));
    }
    el.append(wrap);
    return { input, wrap, key, unit };
  }
  const fields = [field("單位/格", "scale"), field("offset", "position"), field("dx", "dx", "s")];
  const fit = button("適配", async () => {
    const c = current(), s = store.get(), file = s.file, view = s.view;
    if (!c || !file) return;
    fit.disabled = true;
    try {
      const env = await bridge.fetchWave({ ch: c.name, t0: view.t0 - (c.time_offset ?? 0), t1: view.t1 - (c.time_offset ?? 0), px: 2048, gen: file.gen });
      const now = store.get();
      if (now.file !== file || now.view !== view || current() !== c) return;
      const patch = fitEnvelope(env, c.unit, scales);
      if (patch) store.updateChannel(c.name, patch, "user"); else ui.toast("目前範圍沒有可適配的有限資料");
    } catch (e) { if (e?.code !== "STALE" && e?.name !== "AbortError") ui.showError(e); }
    finally { render(); }
  }, "適配目前通道的可見資料範圍（含 dx）");
  fields[2].wrap.append(fit);
  function render(force = false) {
    const c = current();
    for (const f of fields) {
      for (const e of f.wrap.children) if (["INPUT", "BUTTON"].includes(e.tagName)) e.disabled = !c;
      if (force || document.activeElement !== f.input) {
        f.input.value = c ? f.key === "position" ? tickLabel(centerPotential(c), c.unit, c.scale / 100) : fmt.fmt(f.key === "dx" ? c.time_offset ?? 0 : c.scale, f.unit ?? c.unit, 15) : "";
        f.input.dataset.rendered = f.input.value;
      }
    }
    fit.disabled = !c || !store.get().file;
  }
  render();
  return { render, setExpanded(expanded) { el.hidden = !expanded; } };
}
