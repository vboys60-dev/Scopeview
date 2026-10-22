// 截圖頁（對照 ui/tab_screenshot.py）：設定 → 截圖工作 → 預覽／存檔路徑／複製或另存。
// 截圖為單一同步 SCPI 傳輸，無進度可報：只顯示前端自計的已耗時秒數，不顯示百分比，也不提供取消。
const BUSY_MSG = "儀器忙碌中，請等目前操作完成";
export const elapsedText = (sec) => `擷取中… 已 ${sec} 秒`;

/** 截圖邏輯。view＝{ render(s), setPreview(url) }；timer 可注入（測試用）。 */
export function createShot({ bridge, ui, view, config = {}, timer = { set: setInterval, clear: clearInterval } }) {
  const s = {
    dir: config.screenshot_dir ?? "", name: config.screenshot_name || "scope", fmt: config.image_format || "PNG",
    inverted: !!config.inverted, area: config.area || "full",
    connected: false, running: false, text: "", path: "", n: 0, count: 0,
  };
  const draw = () => view.render(s);
  const api = {
    state: s,
    set(patch) { Object.assign(s, patch); draw(); },
    setConnected(c) { s.connected = !!c; draw(); },
    async browse() {
      const d = await ui.pickPath({ bridge, appState: { native_dialogs: config.native_dialogs } }, "folder", s.dir || null);
      if (d) api.set({ dir: d });
    },
    async start() {
      if (s.running) return;
      if (!s.connected) { await ui.alert("請先連線儀器。", "尚未連線"); return; }
      if (!s.dir.trim()) { await ui.alert("請先選擇存檔目錄。", "缺少目錄"); return; }
      s.running = true; let sec = 0; s.text = elapsedText(0); draw();
      const tick = timer.set(() => { s.text = elapsedText(++sec); draw(); }, 1000);
      try {
        // 設定存回 config（後端 Config 鍵）；之後截圖用同一組值
        await bridge.call("save_config", { patch: { screenshot_dir: s.dir, screenshot_name: s.name, image_format: s.fmt, inverted: s.inverted, area: s.area } });
        const r = await bridge.job("screenshot", { directory: s.dir, name: s.name || "scope", image_format: s.fmt, inverted: s.inverted, area: s.area });
        s.path = r.path; s.n = r.preview; s.count++; s.text = `已存檔：${r.path}`;
        view.setPreview(await bridge.screenshotUrl(r.preview));
      } catch (e) {
        s.text = "存圖失敗";
        await ui.showError(e?.code === "BUSY" ? { message: BUSY_MSG } : e, e?.code === "REMOTE_DESKTOP" ? "遠端桌面連線中" : "存圖失敗");
      } finally { timer.clear(tick); s.running = false; draw(); }
    },
  };
  return api;
}

function h(tag, cls, text) { const el = document.createElement(tag); if (cls) el.className = cls; if (text !== undefined) el.textContent = text; return el; }

export function mount(el, ctx) {
  const { bridge, ui } = ctx, cfg = ctx.appState?.config ?? {}, cat = ctx.appState?.catalog ?? {};
  const field = (label, ctrl) => { const f = h("label", "field"); f.append(h("span", "field__label", label), ctrl); return f; };
  const sel = (items) => { const x = h("select", "select"); for (const [v, t] of items) x.append(new Option(t, v)); return x; };
  const dir = h("input", "input grow"), bBrowse = h("button", "btn", "瀏覽…"), name = h("input", "input");
  const fmt = sel((cat.image_formats ?? ["PNG", "BMP"]).map((x) => [x, x]));
  const color = sel([["0", "正常色"], ["1", "反轉色"]]);
  const area = sel([["full", "全螢幕"], ["graticule", "格線區"]]);
  const bStart = h("button", "btn btn--primary", "開始存圖"), bCopy = h("button", "btn", "複製到剪貼簿"), bSave = h("a", "btn", "另存…");
  bBrowse.type = bStart.type = bCopy.type = "button"; bSave.style.lineHeight = "28px"; bSave.style.textDecoration = "none";
  const status = h("div", "muted"), seq = h("div", "muted"), img = h("img"), hint = h("div", "legacy-warning", "尚未連線，請先在上方連線儀器。");
  img.alt = "截圖預覽"; img.style.cssText = "max-width:100%;max-height:60vh;display:none;background:#000";
  const row = h("div", "row"); row.append(dir, bBrowse);
  const dirField = h("div", "field"); dirField.append(h("span", "field__label", "存檔目錄"), row);
  const btns = h("div", "row"); btns.append(bStart, bCopy, bSave);
  el.append(hint, dirField, field("檔名前綴", name), field("格式", fmt), field("顏色", color), field("擷取區域", area), btns, status, seq, img);

  const view = {
    render(s) {
      hint.hidden = s.connected;
      for (const [c, v] of [[dir, s.dir], [name, s.name], [fmt, s.fmt], [color, s.inverted ? "1" : "0"], [area, s.area]]) if (c.value !== v) c.value = v;
      for (const c of [dir, bBrowse, name, fmt, color, area]) c.disabled = s.running;
      bStart.disabled = s.running || !s.connected;
      bStart.textContent = s.running ? "擷取中…" : "開始存圖";
      bCopy.disabled = !s.path;
      bSave.toggleAttribute("hidden", !s.path);
      status.textContent = s.text;
      seq.textContent = s.path ? `第 ${s.count} 張（預覽序號 ${s.n}）　${s.path.split(/[\\/]/).pop()}` : "";
    },
    setPreview(url) { img.src = url; img.style.display = ""; bSave.href = url; bSave.download = shot.state.path.split(/[\\/]/).pop(); },
  };
  const shot = createShot({ bridge, ui, view, config: { ...cfg, native_dialogs: ctx.appState?.native_dialogs } });
  dir.oninput = () => (shot.state.dir = dir.value); name.oninput = () => (shot.state.name = name.value);
  fmt.onchange = () => (shot.state.fmt = fmt.value); color.onchange = () => (shot.state.inverted = color.value === "1"); area.onchange = () => (shot.state.area = area.value);
  bBrowse.onclick = shot.browse; bStart.onclick = shot.start;
  // 複製：以 canvas 轉 PNG 再寫剪貼簿（同源圖，不需 fetch）；WebView 不支援時提示改用另存
  bCopy.onclick = async () => {
    try {
      const c = h("canvas"); c.width = img.naturalWidth; c.height = img.naturalHeight; c.getContext("2d").drawImage(img, 0, 0);
      const blob = await new Promise((ok, ng) => c.toBlob((b) => (b ? ok(b) : ng(new Error("轉檔失敗"))), "image/png"));
      await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
      ui.toast("已複製到剪貼簿", "ok");
    } catch (e) { ui.toast(`此環境無法複製圖片（${e.message}），請改用「另存…」`, "error", 6000); } // 待真機驗證
  };
  bridge.on("driver", (ev) => shot.setConnected(ev.connected));
  shot.setConnected(ctx.appState?.connected);
}
