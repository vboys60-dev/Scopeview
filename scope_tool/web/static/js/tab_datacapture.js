// 資料截取容器：分頁 id 沿用 capture，讓波形擷取沿用原本的作用中判斷。
import { mount as mountShot } from "./tab_screenshot.js";
import { mount as mountCapture } from "./tab_capture.js";

function h(tag, cls, text) {
  const el = document.createElement(tag);
  if (cls) el.className = cls;
  if (text !== undefined) el.textContent = text;
  return el;
}

export function mount(el, ctx) {
  const hint = h("div", "legacy-warning", "尚未連線，請先在上方連線儀器。");
  hint.hidden = !!ctx.appState?.connected;
  ctx.bridge.on("driver", (ev) => { hint.hidden = !!ev.connected; });
  const grid = h("div", "dcap");
  el.append(hint, grid);
  for (const [title, mountModule] of [["截圖", mountShot], ["波形擷取", mountCapture]]) {
    const card = h("section", "dcap__card"), body = h("div");
    card.append(h("h2", "dcap__title", title), body);
    grid.append(card);
    try { mountModule(body, ctx); }
    catch (e) {
      body.textContent = `（${title}模組尚未載入：${e.message}）`;
      console.warn(`掛載${title}失敗`, e);
    }
  }
}
