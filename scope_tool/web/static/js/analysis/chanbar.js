// 通道列：顯示開關、V/格、位置、時間位移 dx；寫 store.updateChannel（time_offset 唯一寫入者）。對照 ui/analysis_chanbar.py。
// 處理意圖：channel.shift_intent、channel.scale_intent（絕對值）。DOM／手感待真人驗證。
import { centerButton } from "./cursors.js";

const h = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; };

/** 結構簽章：名稱／單位／衍生屬性不變就只同步數值，不重建 DOM（避免輸入中被打斷）。 */
export const signature = (chs) => chs.map((c) => `${c.name}|${c.unit}|${c.derived ? 1 : 0}`).join(",");

/** 換檔：以波形中心為準算新位置（scales.rescale）；vmin／vmax 為 null 時位置不動。 */
export function scaleChange(ch, next, scales) {
  if (ch.vmin === null || ch.vmax === null) return { scale: next };
  return { scale: next, position: scales.rescale(ch.vmin, ch.vmax, ch.scale, ch.position, next)[0] };
}

/** 任意輸入與微調共用界線；保留粗調表的上限，V 下限兼容 500 µV 檔位。 */
export function clampScale(value, unit, scales) {
  const steps = scales.scaleSteps(unit);
  return Math.min(steps.at(-1), Math.max(unit === "V" ? Math.min(0.001, steps[0]) : steps[0], value));
}
/** 表外值往指定方向找相鄰檔；容差避免浮點誤差讓同檔停住。 */
export function coarseScale(value, unit, up, scales) {
  const steps = scales.scaleSteps(unit);
  return up ? steps.find((s) => s > value * (1 + 1e-9)) ?? steps.at(-1)
    : steps.findLast((s) => s < value * (1 - 1e-9)) ?? steps[0];
}
export function fineScale(value, unit, up, scales) {
  const step = unit === "V" ? 0.01 : Number((value * 0.05).toPrecision(2));
  return clampScale(Number((value + (up ? step : -step)).toPrecision(15)), unit, scales);
}

export function mount(el, ctx) {
  const { store, bridge, ui, fmt, scales } = ctx;
  el.classList.add("chanbar");
  let sig = null, rows = new Map();
  const center = centerButton(store);

  function chip(c) {
    const box = h("div", "chip");
    const vis = h("input", "check"); vis.type = "checkbox"; vis.title = "顯示／隱藏";
    vis.onchange = () => store.updateChannel(c.name, { visible: vis.checked }, "user");
    const name = h("span", "chip__name", c.name);
    name.title = "點一下：選為量測／游標換算來源；雙擊：換色";
    name.onclick = () => store.set({ selected: c.name }, "user");
    const col = h("input"); col.type = "color"; col.hidden = true;
    col.oninput = () => store.updateChannel(c.name, { color: col.value }, "user");
    name.ondblclick = () => col.click();
    const sc = h("input", "input"); sc.style.width = "7em"; sc.title = "每格大小（可直接輸入，如 130m）；↑↓ 微調，Shift＋↑↓ 粗調";
    const apply = (value) => {
      const cur = store.get().channels.find((x) => x.name === c.name);
      if (Number.isFinite(value)) store.updateChannel(c.name, scaleChange(cur, clampScale(value, cur.unit, scales), scales), "user");
      sc.value = fmt.fmt(store.get().channels.find((x) => x.name === c.name).scale, c.unit, 15);
    };
    sc.onchange = () => apply(fmt.parseSI(sc.value));
    const step = (up, fine = false) => {
      const cur = store.get().channels.find((x) => x.name === c.name);
      const typed = fmt.parseSI(sc.value), start = Number.isFinite(typed) && typed !== cur.scale ? typed : cur.scale;
      apply(fine ? fineScale(start, cur.unit, up, scales) : coarseScale(start, cur.unit, up, scales));
    };
    sc.onkeydown = (e) => {
      if (e.isComposing || e.altKey || e.metaKey || e.ctrlKey) return;
      if (!["ArrowUp", "ArrowDown"].includes(e.key)) return;
      e.preventDefault(); step(e.key === "ArrowUp", !e.shiftKey);
    };
    const bUp = h("button", "btn btn--small", "▲"), bDn = h("button", "btn btn--small", "▼");
    bUp.title = "較矮（每格大小增加一檔）"; bDn.title = "較高（每格大小減少一檔）"; bUp.onclick = () => step(true); bDn.onclick = () => step(false);
    const fineDn = h("button", "btn btn--small", "−"), fineUp = h("button", "btn btn--small", "+");
    fineDn.title = "每格大小微減（V：10 mV；其他：5%）"; fineUp.title = "每格大小微增（V：10 mV；其他：5%）";
    fineDn.onclick = () => step(false, true); fineUp.onclick = () => step(true, true);
    const pos = h("input", "input"); pos.type = "number"; pos.step = "0.1"; pos.title = "垂直位置（格）"; pos.style.width = "5.5em";
    pos.onchange = () => { const v = Number(pos.value); if (Number.isFinite(v)) store.updateChannel(c.name, { position: v }, "user"); };
    const dx = h("input", "input"); dx.title = "時間位移 dx（如 200u、-1.5m）"; dx.style.width = "6em";
    dx.onchange = () => {
      const v = fmt.parseSI(dx.value);
      if (Number.isFinite(v)) store.updateChannel(c.name, { time_offset: v }, "user"); else sync();
    };
    const parts = [vis, name, col, sc, bUp, bDn, fineDn, fineUp, pos, dx];
    if (c.derived) {
      const rm = h("button", "chip__remove", "×"); rm.title = "刪除此衍生波形";
      rm.onclick = async () => {
        try { await bridge.call("remove_channel", { name: c.name }); store.removeChannel(c.name, "user"); } catch (e) { ui.showError(e); }
      };
      parts.push(rm);
    }
    box.append(...parts);
    rows.set(c.name, { box, vis, name, col, sc, pos, dx });
    return box;
  }

  function sync() {
    const { channels, selected } = store.get();
    for (const c of channels) {
      const r = rows.get(c.name); if (!r) continue;
      if (document.activeElement !== r.sc) r.sc.value = fmt.fmt(c.scale, c.unit, 15);
      r.vis.checked = c.visible;
      r.name.style.color = c.color; r.col.value = c.color;
      r.box.classList.toggle("chip--selected", c.name === selected);
      if (document.activeElement !== r.pos) r.pos.value = String(Number(c.position.toFixed(3)));
      if (document.activeElement !== r.dx) r.dx.value = c.time_offset ? fmt.fmt(c.time_offset, "s") : "0";
    }
  }
  function render() {
    const { channels } = store.get(), s = signature(channels);
    if (s !== sig) { sig = s; rows = new Map(); el.replaceChildren(...channels.map(chip), center); }
    sync();
  }
  store.on(["channels", "selected"], render);
  store.onCommand("channel.shift_intent", ({ name, time_offset }) => store.updateChannel(name, { time_offset }, "user"));
  store.onCommand("channel.scale_intent", ({ name, scale, position }) => {
    const patch = {};
    if (scale !== undefined) patch.scale = scale;
    if (position !== undefined) patch.position = position;
    store.updateChannel(name, patch, "user");
  });
  render();
}
