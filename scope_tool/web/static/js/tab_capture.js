// 波形擷取頁（對應 ui/tab_capture.py）。檔案格式固定 HDF5（契約 capture 無格式參數）。
// 純邏輯（記憶體估算、警示、文案）匯出供 l3_check.mjs 驗證；mount 才碰 DOM。

export const BYTES_PER_POINT = 16; // 每通道每點約 16 B（float64 時間＋float32 值，沿用規劃書 4×100M≈6.4 GB）
export const WARN_BYTES = 2e9;     // ≥2 GB：提醒
export const DANGER_BYTES = 6.4e9; // ≥4×100M：高風險

export const estimateBytes = (points, nCh) => Math.max(0, points) * Math.max(0, nCh) * BYTES_PER_POINT;
export const fmtBytes = (b) => (b >= 1e9 ? `${(b / 1e9).toFixed(1)} GB` : `${Math.max(1, Math.round(b / 1e6))} MB`);
/** → null | {level:"warn"|"danger", text} */
export function riskOf(points, nCh) {
  const b = estimateBytes(points, nCh);
  if (b >= DANGER_BYTES) return { level: "danger", text: `預估記憶體約 ${fmtBytes(b)}（${nCh} 通道 × ${points.toLocaleString("en-US")} 點）：已達 4×100M 級，可能耗盡 RAM 或擷取失敗，請確認電腦記憶體足夠。` };
  if (b >= WARN_BYTES) return { level: "warn", text: `預估記憶體約 ${fmtBytes(b)}，點數很大，擷取與之後分析都會較慢、較吃記憶體。` };
  return null;
}
export const elapsedText = (sec) => `擷取中… 已 ${Math.max(0, Math.floor(sec))} 秒`;
export const STOP_NOTE = "擷取後示波器會維持 STOP 狀態（不會自動 RUN）；若要繼續觀察請在儀器上手動 RUN。";
export const busyText = (e) => (e?.code === "BUSY" ? "儀器忙碌中，請等目前操作完成後再按一次。" : e?.message ?? String(e));
/** BUSY 時延遲重試（最多 tries 次）；其他錯誤直接丟出。onWait(n) 供 UI 顯示「忙碌中」。 */
export async function retryBusy(fn, { tries = 5, delayMs = 1000, onWait = () => {}, sleep = (ms) => new Promise((r) => setTimeout(r, ms)) } = {}) {
  for (let n = 1; ; n++) {
    try { return await fn(); } catch (e) {
      if (e?.code !== "BUSY" || n >= tries) throw e;
      onWait(n); await sleep(delayMs);
    }
  }
}
/** 驗證輸入；回錯誤字串或 null。 */
export function validate({ connected, channels, maxPoints, points, dir }) {
  if (!connected) return "請先連線儀器。";
  if (maxPoints == null) return "還沒查到這台機器的點數上限，請稍候再試。";
  if (!channels.length) return "請至少勾選一個通道。";
  if (!Number.isInteger(points) || points < 1) return "點數必須是大於 0 的整數。";
  if (points > maxPoints) return `這台機器目前最多可取 ${maxPoints.toLocaleString("en-US")} 點，請調低點數。`;
  if (!dir) return "請選擇存檔資料夾。";
  return null;
}
export const doneText = (r) => `已存檔：${r.path}` + (r.got_points < r.requested ? `（示波器實際只有 ${r.got_points} 點，時基調慢可增加）` : "");

const h = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text !== undefined) e.textContent = text; return e; };

export function mount(el, ctx) {
  const { bridge, store, ui } = ctx;
  const cfg = ctx.appState?.config ?? {};
  let info = null, dirty = true, running = false, lastPath = null, token = 0;
  const checks = new Map();

  const dir = h("input", "input grow"); dir.value = cfg.waveform_dir ?? "";
  const pick = h("button", "btn", "瀏覽…");
  const name = h("input", "input grow"); name.value = cfg.waveform_name ?? "wave";
  const pts = h("input", "input"); pts.type = "number"; pts.min = "1"; pts.step = "1"; pts.value = cfg.points ?? 10000;
  const retrig = h("input"); retrig.type = "checkbox"; retrig.checked = !!cfg.retrigger;
  const chBox = h("div", "row"), maxHint = h("div", "field__hint"), risk = h("div", "field__hint");
  const go = h("button", "btn btn--primary", "開始擷取");
  const status = h("div", "muted", "尚未連線"), open = h("button", "btn", "用分析頁開啟"); open.hidden = true;
  const field = (label, ...kids) => { const f = h("div", "field"); f.append(h("div", "field__label", label)); const r = h("div", "row"); r.append(...kids); f.append(r); return f; };
  const lbl = h("label", "check"); lbl.append(retrig, h("span", "", "擷取前重新觸發單次擷取"));
  el.append(field("存檔資料夾", dir, pick), field("檔名（自動加時間戳，格式固定 HDF5 .h5）", name), field("通道", chBox), maxHint,
    field("點數", pts, lbl), risk, h("div", "field__hint", STOP_NOTE), go, status, open);

  const sel = () => [...checks].filter(([, c]) => c.checked).map(([k]) => k);
  const refreshRisk = () => {
    const r = riskOf(Number(pts.value), sel().length);
    risk.textContent = r ? r.text : ""; risk.className = "field__hint" + (r?.level === "danger" ? " is-error" : "");
  };
  const syncBtn = () => { const off = running || !ctx.appState?.connected; go.classList.toggle("is-disabled", off); go.disabled = off; };

  const active = () => ctx.activeTab === "capture";
  /** 只在擷取分頁作用中才查；否則記旗標，切入時再查。 */
  async function loadInfo() {
    if (!active()) { dirty = true; return; }
    dirty = false;
    const my = ++token;
    chBox.replaceChildren(); checks.clear(); info = null; maxHint.textContent = ""; refreshRisk(); syncBtn();
    if (!ctx.appState?.connected) { status.textContent = "尚未連線"; return; }
    status.textContent = "查詢通道與點數上限中…";
    try {
      const i = await retryBusy(() => bridge.job("capture_info", {}), { onWait: () => { if (my === token) status.textContent = "儀器忙碌中…稍後自動重試"; } });
      if (my !== token) return;
      info = i;
      for (const c of i.channels) {
        const l = h("label", "check"), cb = h("input"); cb.type = "checkbox"; cb.checked = true; cb.onchange = refreshRisk;
        l.append(cb, h("span", "", c)); chBox.append(l); checks.set(c, cb);
      }
      maxHint.textContent = `這台機器最多可取 ${i.max_points.toLocaleString("en-US")} 點`;
      status.textContent = "就緒"; refreshRisk();
    } catch (e) { if (my === token) { status.textContent = "查詢通道失敗"; ui.toast(busyText(e), "error"); } }
  }

  pick.onclick = async () => { const p = await ui.pickPath(ctx, "folder", dir.value || null); if (p) dir.value = p; };
  pts.oninput = refreshRisk;
  // 暫行：契約無 open_waveform 意圖，待 L4 認領
  open.onclick = () => { if (lastPath) { document.querySelector("#tabs .tab[data-tab=analysis]")?.click(); store.command("open_waveform", { path: lastPath }); } };

  go.onclick = async () => {
    if (running) return; // CSS 擋不住鍵盤 Enter／空白
    const points = Number(pts.value), channels = sel();
    const bad = validate({ connected: ctx.appState?.connected, channels, maxPoints: info?.max_points ?? null, points, dir: dir.value.trim() });
    if (bad) return ui.toast(bad, "error");
    const r = riskOf(points, channels.length);
    if (r?.level === "danger" && !(await ui.confirm(r.text + "\n仍要繼續擷取嗎？", "記憶體風險"))) return;
    if (running) return; // 確認對話框期間可能已被另一次按下
    running = true; open.hidden = true; syncBtn();
    const t0 = Date.now(), tick = () => { status.textContent = elapsedText((Date.now() - t0) / 1000); };
    tick(); const timer = setInterval(tick, 1000);
    try {
      bridge.call("save_config", { patch: { waveform_dir: dir.value.trim(), waveform_name: name.value || "wave", points, retrigger: retrig.checked } }).catch((e) => ui.toast("擷取設定未能儲存：" + (e.message || e), "error"));
      const res = await bridge.job("capture", { directory: dir.value.trim(), name: name.value || "wave", channels, points, retrigger: retrig.checked });
      lastPath = res.path; status.textContent = doneText(res) + " " + STOP_NOTE; open.hidden = false;
    } catch (e) { status.textContent = e.code === "BUSY" ? busyText(e) : "擷取失敗"; if (e.code !== "BUSY") ui.showError(e, "擷取失敗"); }
    finally { clearInterval(timer); running = false; syncBtn(); }
  };

  bridge.on("driver", () => loadInfo());
  store.onCommand("tab.activated", (n) => { if (n === "capture" && (dirty || !info) && !running) loadInfo(); });
  loadInfo();
}
