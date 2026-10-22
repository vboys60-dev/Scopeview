// 連線列（對照 ui/main_window.py 的連線列）：搜尋、手動 IP、連線／斷線、假儀器、系列手選。
// 邏輯（createConn）與 DOM（mount）分開，邏輯可在 node 以 mock 後端驗證。
const BUSY_MSG = "儀器忙碌中，請等目前操作完成";

/** 連線邏輯。view＝{ chooseSeries(list)→Promise<string|null>, render(state) }。 */
export function createConn({ bridge, ui, view, config = {}, series = ["InfiniiVision", "Infiniium"] }) {
  const s = { found: [], selected: config.last_resource || "", connected: false, model: null, pending: null, text: "未連線", warn: "" };
  if (s.selected) s.found.push({ resource: s.selected, source: "config", label: s.selected });
  const draw = () => view.render(s);
  const setText = (t) => { s.text = t; draw(); };

  /** 統一錯誤顯示：BUSY 用固定文案；遠端桌面另掛警示。 */
  async function fail(e, title) {
    if (e?.code === "REMOTE_DESKTOP") { s.warn = e.message; }
    await ui.showError(e?.code === "BUSY" ? { message: BUSY_MSG } : e, e?.code === "REMOTE_DESKTOP" ? "遠端桌面連線中" : title);
  }
  /** 執行一個佔用連線列的操作；pending 期間按鈕全停用，避免重複送出。 */
  async function run(name, label, fn, title) {
    if (s.pending) return;
    s.pending = name; s.text = label; draw();
    try { return await fn(); } catch (e) { s.text = `${title}`; await fail(e, title); } finally { s.pending = null; draw(); }
  }

  const api = {
    state: s,
    select(resource) { s.selected = resource; draw(); },
    search: () => run("search", "搜尋中…", async () => {
      s.found = await bridge.job("search", {});
      if (!s.found.some((f) => f.resource === s.selected)) s.selected = s.found[0]?.resource ?? "";
      s.text = s.found.length ? `找到 ${s.found.length} 台` : "沒有找到儀器";
    }, "搜尋失敗"),
    async manual() {
      if (s.pending) return;
      const ip = (await ui.prompt("儀器 IP 位址：", "", "手動輸入 IP"))?.trim();
      if (!ip) return;
      try {
        const [it] = await bridge.call("add_manual_ip", { ip });
        if (!s.found.some((f) => f.resource === it.resource)) s.found.push(it);
        s.selected = it.resource; draw();
      } catch (e) { await fail(e, "手動輸入失敗"); }
    },
    connect: () => run("connect", "連線中…", async () => {
      if (!s.selected) { await ui.alert("請先搜尋或手動輸入一台儀器。", "尚未選擇儀器"); s.text = "未連線"; return; }
      let override = null;
      for (;;) {
        try { applyResult(await bridge.job("connect", { resource: s.selected, series_override: override })); return; }
        catch (e) {
          // 無法判斷系列：讓使用者手選後以同一資源重送（新 request_id）
          if (e?.code !== "UNSUPPORTED" || override) throw e;
          override = await view.chooseSeries(series, e.message);
          if (!override) { s.text = "連線已取消"; return; }
          s.text = "連線中…"; draw();
        }
      }
    }, "連線失敗"),
    disconnect: () => run("disconnect", "斷線中…", async () => { await bridge.job("disconnect", {}); applyDriver({ connected: false }); }, "斷線失敗"),
    fake: () => run("fake", "連線中…", async () => applyResult(await bridge.call("connect_fake", {})), "連線失敗"),
    toggle: () => (s.connected ? api.disconnect() : api.connect()),
    toggleFake: () => (s.connected ? api.disconnect() : api.fake()),
    onDriver: (ev) => applyDriver(ev),
  };
  function applyResult(r) { applyDriver({ connected: true, model: r.model }); }
  function applyDriver(ev) {
    s.connected = !!ev.connected; s.model = ev.model ?? null; if (s.connected) s.warn = "";
    s.text = s.connected ? `已連線：${s.model}` : "未連線";
    draw();
  }
  if (config.connected) applyDriver(config);
  return api;
}

function h(tag, cls, text) { const el = document.createElement(tag); if (cls) el.className = cls; if (text !== undefined) el.textContent = text; return el; }

/** 系列手選對話框（取消回 null）。 */
function chooseSeriesDialog(list, msg) {
  return new Promise((resolve) => {
    const dlg = h("dialog", "dlg"), sel = h("select", "select");
    for (const x of list) sel.append(new Option(x, x));
    const body = h("div", "dlg__body"), act = h("div", "dlg__actions");
    body.append(h("h2", "dlg__title", "請選擇儀器系列"), h("p", "dlg__msg", `${msg ?? "無法判斷儀器系列"}\n請手動指定後重試。`), sel);
    const done = (v) => { dlg.close(); dlg.remove(); resolve(v); };
    const no = h("button", "btn", "取消"), ok = h("button", "btn btn--primary", "重試連線");
    no.type = ok.type = "button"; no.onclick = () => done(null); ok.onclick = () => done(sel.value);
    dlg.addEventListener("cancel", (e) => { e.preventDefault(); done(null); });
    act.append(no, ok); dlg.append(body, act); document.body.append(dlg); dlg.showModal();
  });
}

export function mount(el, ctx) {
  const { bridge, ui } = ctx;
  const btn = (t, cls = "btn") => { const b = h("button", cls, t); b.type = "button"; return b; };
  const bSearch = btn("搜尋"), bManual = btn("手動輸入 IP"), bConn = btn("連線", "btn btn--primary"), bFake = btn("測試儀器（模擬）");
  const combo = h("select", "select grow"), status = h("span", "muted"), warn = h("span", "is-error");
  combo.style.minWidth = "240px"; combo.setAttribute("aria-label", "儀器清單");
  warn.setAttribute("role", "alert");
  bFake.dataset.tip = "不接真機，掛上模擬儀器供測試";
  el.append(bSearch, combo, bManual, bConn, bFake, status, warn);

  const view = {
    chooseSeries: chooseSeriesDialog,
    render(s) {
      const sel = combo.value;
      combo.replaceChildren(...(s.found.length ? s.found.map((f) => new Option(f.label || f.resource, f.resource)) : [new Option("（尚未搜尋）", "")]));
      combo.value = s.selected || sel;
      const busy = !!s.pending;
      for (const b of [bSearch, bManual, bConn, bFake, combo]) b.disabled = busy;
      bConn.textContent = s.connected ? "斷線" : "連線";
      bFake.textContent = s.connected && s.model === "FAKE-SCOPE" ? "斷開模擬" : "測試儀器（模擬）";
      status.textContent = s.text; warn.textContent = s.warn;
    },
  };
  const conn = createConn({ bridge, ui, view, config: { ...ctx.appState?.config, connected: ctx.appState?.connected, model: ctx.appState?.model } });
  bSearch.onclick = conn.search; bManual.onclick = conn.manual; bConn.onclick = conn.toggle; bFake.onclick = conn.toggleFake;
  combo.onchange = () => conn.select(combo.value);
  bridge.on("driver", conn.onDriver);
  view.render(conn.state);
}
