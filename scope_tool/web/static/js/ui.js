// <dialog> 版 alert／confirm／prompt 與 toast；不使用 window.alert（原生 WebView 行為不一致）。
// class 名稱見 docs/web-api契約.md 的「樣式 token 與 CSS class 名稱」。
function h(tag, cls, text) {
  const el = document.createElement(tag);
  if (cls) el.className = cls;
  if (text !== undefined) el.textContent = text;
  return el;
}

/** 通用對話框：build(body) 可加入內容並回傳 getValue()；按鈕決定 resolve 的值。 */
function dialog({ title, message, buttons, build }) {
  return new Promise((resolve) => {
    const dlg = h("dialog", "dlg");
    const body = h("div", "dlg__body");
    if (title) body.append(h("h2", "dlg__title", title));
    if (message) body.append(h("p", "dlg__msg", message));
    const getValue = build ? build(body) : () => undefined;
    const actions = h("div", "dlg__actions");
    const done = (v) => { dlg.close(); dlg.remove(); resolve(v); };
    for (const b of buttons) {
      const btn = h("button", `btn${b.primary ? " btn--primary" : ""}`, b.label);
      btn.type = "button";
      btn.onclick = () => done(b.value(getValue));
      actions.append(btn);
    }
    dlg.append(body, actions);
    dlg.addEventListener("cancel", (e) => { e.preventDefault(); done(buttons[0].value(getValue)); }); // Esc＝第一顆（取消／關閉）
    document.body.append(dlg);
    dlg.showModal();
    actions.lastChild.focus();
  });
}

export const alert = (message, title = "訊息") =>
  dialog({ title, message, buttons: [{ label: "關閉", primary: true, value: () => undefined }] });

export const confirm = (message, title = "請確認") =>
  dialog({ title, message, buttons: [{ label: "取消", value: () => false }, { label: "確定", primary: true, value: () => true }] });

/** 取消回 null；確定回字串。 */
export const prompt = (message, def = "", title = "請輸入") =>
  dialog({
    title, message,
    build(body) {
      const input = h("input", "input");
      input.value = def;
      input.addEventListener("keydown", (e) => { if (e.key === "Enter") input.closest("dialog").querySelector(".btn--primary").click(); });
      body.append(input);
      queueMicrotask(() => input.select());
      return () => input.value;
    },
    buttons: [{ label: "取消", value: () => null }, { label: "確定", primary: true, value: (get) => get() }],
  });

/** 顯示錯誤對話框；err 可為 BridgeError（含 code／message）或任何 Error。 */
export const showError = (err, title = "發生錯誤") => alert(err?.message ?? String(err), title);

/** 輕量提示，數秒後自動消失。kind ∈ info／ok／error。 */
export function toast(message, kind = "info", ms = 3500) {
  let host = document.querySelector(".toast-host");
  if (!host) { host = h("div", "toast-host"); host.setAttribute("aria-live", "polite"); document.body.append(host); }
  const el = h("div", `toast toast--${kind}`, message);
  host.append(el);
  setTimeout(() => el.remove(), ms);
}

/** 選路徑：AppState.native_dialogs 為真走原生對話框，否則改用 prompt 手動輸入。取消（或空字串）回 null。
 *  kind ∈ folder／file；ctx 需有 bridge 與 appState。 */
export async function pickPath(ctx, kind, initial = null) {
  if (ctx.appState?.native_dialogs) return ctx.bridge.call(kind === "folder" ? "pick_folder" : "pick_waveform_file", { initial });
  const v = await prompt(kind === "folder" ? "請輸入資料夾的完整路徑" : "請輸入波形檔的完整路徑", initial ?? "");
  return v ? v.trim() || null : null;
}
