// 入口：建立 ctx、切換三分頁、掛載各 lane 的頁面模組。共享入口只由 L0 修改。
import { bridge, MOCK } from "./bridge.js";
import { store } from "./analysis/store.js";
import * as ui from "./ui.js";
import * as fmt from "./fmt.js";
import * as scales from "./analysis/scales.js";

// 各 lane 的模組約定：export function mount(el, ctx)；模組尚未交付時顯示佔位，不中斷其他頁。
const MODULES = {
  connbar: { el: "connbar", src: "./connbar.js" },
  screenshot: { el: "tab-screenshot", src: "./tab_screenshot.js" },
  capture: { el: "tab-capture", src: "./tab_capture.js" },
  analysis: { el: "tab-analysis", src: "./analysis/tab_analysis.js" },
};
const ctx = { bridge, store, ui, fmt, scales, MOCK, appState: null, activeTab: "screenshot" };

async function mountAll() {
  for (const [name, m] of Object.entries(MODULES)) {
    const el = document.getElementById(m.el);
    try {
      (await import(m.src)).mount(el, ctx);
    } catch (e) {
      el.textContent = `（${name} 模組尚未載入：${e.message}）`;
      console.warn(`mount ${name} 失敗`, e);
    }
  }
}

function selectTab(name) {
  ctx.activeTab = name;
  for (const b of document.querySelectorAll("#tabs .tab")) {
    const on = b.dataset.tab === name;
    b.classList.toggle("tab--active", on);
    b.setAttribute("aria-selected", String(on));
  }
  for (const p of document.querySelectorAll(".pages .page")) p.hidden = p.id !== `tab-${name}`;
  store.command("tab.activated", name);
}

async function init() {
  document.getElementById("tabs").addEventListener("click", (e) => {
    const b = e.target.closest(".tab");
    if (b) selectTab(b.dataset.tab);
  });
  // 被中止的請求（AbortController）是正常流程，不提示
  window.addEventListener("unhandledrejection", (e) => {
    if (e.reason?.name === "AbortError") return;
    ui.toast(e.reason?.message ?? String(e.reason), "error");
  });
  try {
    ctx.appState = await bridge.call("get_state");
  } catch (e) {
    ui.showError(e, "無法取得程式狀態");
  }
  bridge.on("driver", (ev) => { if (ctx.appState) Object.assign(ctx.appState, { connected: ev.connected, model: ev.model, series: ev.series }); });
  bridge.on("desync", (ev) => ui.toast(ev.message, "error", 8000));
  if (MOCK) document.title += "（mock）";
  await mountAll();
  store.command("tab.activated", ctx.activeTab); // 初始分頁也發一次，各頁據此做首次載入
}

init();
