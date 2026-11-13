// L5：精簡通道 chip 與各通道 Vertical 欄位；通道設定經 store.updateChannel。
// 處理意圖：channel.shift_intent、channel.scale_intent（絕對值）。DOM／手感待真人驗證。
import { mount as mountVertical, hasDx } from "./vertical.js";
import { gridSelect } from "./grids.js";
import { setChannelColor, resetChannelColor } from "./channel_colors.js";

const h = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; };

/** 結構簽章：名稱／單位／衍生屬性不變就只同步數值，不重建 DOM（避免輸入中被打斷）。 */
export const signature = (chs) => chs.map((c) => `${c.name}|${c.unit}|${c.derived ? 1 : 0}`).join(",");

/** 換檔保留畫面中心的物理值（−position×scale），與整檔 min/max 無關。 */
export function scaleChange(ch, next, _scales) {
  return { scale: next, position: ch.position * ch.scale / next + 0 };
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
  const { store, bridge, ui, fmt } = ctx;
  el.classList.add("chanbar");
  let sig = null, rows = new Map(), expanded = false;
  const storageKey = "analysis.vertical.expanded";
  try { expanded = localStorage.getItem(storageKey) === "true"; } catch {}
  const toggle = h("button", "btn btn--small chanbar__toggle"); toggle.type = "button";
  function syncExpanded() {
    toggle.textContent = expanded ? "▾" : "▸";
    toggle.title = expanded ? "收折電壓控制" : "展開電壓控制";
    toggle.setAttribute("aria-label", toggle.title);
    toggle.setAttribute("aria-expanded", String(expanded));
    for (const r of rows.values()) r.v.setExpanded(expanded);
  }
  toggle.onclick = () => {
    expanded = !expanded;
    try { localStorage.setItem(storageKey, String(expanded)); } catch {}
    syncExpanded();
    // 高度改變由 tab_analysis 的 chanbar ResizeObserver 排程 renderLayout。
  };

  function column(c) {
    const box = h("div", "chip");
    const vis = h("input", "check"); vis.type = "checkbox"; vis.title = "顯示／隱藏";
    vis.onchange = () => store.updateChannel(c.name, { visible: vis.checked }, "user");
    const name = h("span", "chip__name", c.name);
    name.title = `${c.name}：點一下選為目前通道／量測來源；雙擊換色`;
    name.onclick = () => store.set({ selected: c.name }, "user");
    name.tabIndex = 0; name.setAttribute("role", "button");
    name.onkeydown = (e) => {
      if (e.key !== "Enter" && e.key !== " ") return;
      if (e.key === " ") e.preventDefault();
      store.set({ selected: c.name }, "user");
    };
    const col = h("input", "chip__color"); col.type = "color";
    col.setAttribute("aria-label", "通道顏色"); col.title = `${c.name} 通道顏色`;
    col.oninput = col.onchange = () => setChannelColor(store, c.name, col.value);
    const reset = h("button", "chip__reset", "↺"); reset.type = "button";
    reset.title = "重設顏色"; reset.setAttribute("aria-label", "重設顏色");
    reset.onclick = () => resetChannelColor(store, c.name);
    const sc = h("span", "chip__scale");
    const badge = h("span", "vertical__badge", "dx"); badge.title = "會影響游標區間量測與 FFT";
    box.onclick = (e) => { if (e.target.closest?.("input,button,select")) return; store.set({ selected: c.name }, "user"); };
    box.ondblclick = (e) => { if (e.target.closest?.("input,button,select")) return; col.click(); };
    const grid = gridSelect(store, c.name), parts = [vis, name, col, reset, sc, grid.el, badge];
    if (c.derived) {
      const rm = h("button", "chip__remove", "×"); rm.title = "刪除此衍生波形";
      rm.onclick = async () => {
        if (!await ui.confirm(`刪除衍生波形 ${c.name}？`, "刪除波形")) return;
        try { await bridge.call("remove_channel", { name: c.name }); store.removeChannel(c.name, "user"); } catch (e) { ui.showError(e); }
      };
      parts.push(rm);
    }
    box.append(...parts);
    const verticalEl = h("div", "vertical");
    const v = mountVertical(verticalEl, ctx, { scaleChange, clampScale, fineScale, coarseScale }, c.name);
    const colEl = h("div", "chanbar__col"); colEl.dataset.channel = c.name; colEl.append(box, verticalEl);
    rows.set(c.name, { box, vis, name, col, sc, badge, v, grid, colEl });
    return colEl;
  }

  function sync() {
    const { channels, selected } = store.get();
    for (const [i, c] of channels.entries()) {
      const r = rows.get(c.name); if (!r) continue;
      r.v.render(); r.grid.sync();
      r.sc.textContent = `${fmt.fmt(c.scale, c.unit)}/格`;
      r.badge.hidden = !hasDx(c);
      r.vis.checked = c.visible;
      r.name.textContent = `${"●▲■◆"[i % 4]}${c.name}`  /* 形狀輔助辨識，不只靠顏色 */; r.name.style.color = c.color; r.col.value = c.color;
      r.name.setAttribute("aria-pressed", String(c.name === selected));
      r.box.classList.toggle("chip--selected", c.name === selected);
      r.colEl.dataset.selected = String(c.name === selected);
    }
  }
  function render() {
    const { channels } = store.get(), s = signature(channels);
    if (s !== sig) { sig = s; rows = new Map(); el.replaceChildren(toggle, ...channels.map(column)); syncExpanded(); }
    sync();
  }
  store.on(["channels", "selected", "file", "grids"], render);
  store.onCommand("channel.shift_intent", ({ name, time_offset }) => store.updateChannel(name, { time_offset }, "user"));
  store.onCommand("channel.scale_intent", ({ name, scale, position }) => {
    const patch = {};
    if (scale !== undefined) patch.scale = scale;
    if (position !== undefined) patch.position = position;
    store.updateChannel(name, patch, "user");
  });
  render();
}
