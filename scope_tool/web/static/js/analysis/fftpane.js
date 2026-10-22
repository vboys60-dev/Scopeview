// FFT 頻譜窗格：顯示 store.fftResult（由 L5 以 fft job 寫入）；頻譜資料走 /fft 二進位。
// 對數軸、峰值標記、RF 位置（store.rfPos）；RF 操作只發 rf.intent。FFT 參數控制列由 L5 掛在 .analysis__fftbar。
import { linear, logmap, niceTicks, logTicks, tickLabel, envPixels, drawPixels, makeLatest, debounce, createCanvas, drawGrid, plotColors } from "./plotcore.js";

export const MARGIN = { l: 64, t: 8, r: 10, b: 22 };
/** 頻率視窗：log 時下界須 >0（以 df 或 f_max/1e6 為底）。 */
export function freqWindow(res, view, log) {
  let f0 = view?.f0 ?? res.f_min ?? 0, f1 = view?.f1 ?? res.f_max ?? 1;
  if (log) f0 = Math.max(f0, res.df > 0 ? res.df : f1 / 1e6);
  return { f0, f1: Math.max(f1, f0 * 1.0001 + 1e-12) };
}
/** Y 範圍：只看有限值，加 5% 邊界；無資料回 [0,1]。 */
export function yRange(env) {
  let lo = Infinity, hi = -Infinity;
  for (let i = 0; i < env.n; i++) {
    const a = env.lo[i], b = env.hi[i];
    if (a < lo) lo = a;
    if (b > hi) hi = b;
  }
  if (!(lo <= hi)) return [0, 1];
  const pad = (hi - lo || Math.abs(hi) || 1) * 0.05;
  return [lo - pad, hi + pad];
}

export function mount(el, ctx) {
  const { store, bridge, ui } = ctx;
  el.innerHTML = '<div class="analysis__fftbar"><label class="check"><input type="checkbox" data-log> 對數頻率</label>'
    + '<span data-rf class="row"><button class="btn btn--small" data-d="-1" type="button">◀ 上一峰</button>'
    + '<button class="btn btn--small" data-d="0" type="button">吸附</button>'
    + '<button class="btn btn--small" data-d="1" type="button">下一峰 ▶</button></span>'
    + '<span class="muted" data-status></span></div><div class="analysis__fftplot"></div>';
  const host = el.querySelector(".analysis__fftplot"), status = el.querySelector("[data-status]");
  const logBox = el.querySelector("[data-log]");
  let env = null, view = null, resId = null, rect = { l: 0, t: 0, w: 1, h: 1 }, drag = null, yr = [0, 1];
  const latest = makeLatest();
  const cv = createCanvas(host, (w, h) => {
    rect = { l: MARGIN.l, t: MARGIN.t, w: Math.max(1, w - MARGIN.l - MARGIN.r), h: Math.max(1, h - MARGIN.t - MARGIN.b) };
    draw(); fetchSoon();
  });
  const { canvas, ctx: g } = cv;
  const res = () => { const r = store.get().fftResult; return r?.ok && r.spectrum_id ? r : null; };
  const log = () => logBox.checked;
  const win = () => freqWindow(res() ?? {}, view, log());
  const Fmap = () => { const w = win(); return (log() ? logmap : linear)(w.f0, w.f1, rect.l, rect.l + rect.w); };
  const Ymap = () => linear(yr[1], yr[0], rect.t, rect.t + rect.h);

  function draw() {
    const [w, h] = cv.size();
    if (!w || !h) return;
    const col = plotColors(), r = res();
    g.fillStyle = col.bg; g.fillRect(0, 0, w, h);
    if (!r) { g.fillStyle = col.text; g.font = "12px sans-serif"; g.fillText("尚無頻譜（開啟 FFT 後顯示）", rect.l + 8, rect.t + 18); return; }
    const fw = win(), F = Fmap(), Y = Ymap(), unit = r.unit;
    const ft = log() ? logTicks(fw.f0, fw.f1) : niceTicks(fw.f0, fw.f1);
    drawGrid(g, rect, ft.map((v) => ({ p: F(v), label: tickLabel(v, "Hz") })), niceTicks(yr[0], yr[1], 6).map((v) => ({ p: Y(v), label: tickLabel(v, unit) })), col);
    g.save(); g.beginPath(); g.rect(rect.l, rect.t, rect.w, rect.h); g.clip();
    if (env) drawPixels(g, envPixels(env, F, Y), "#c58bff");
    g.fillStyle = "#ff5b5b"; g.font = "10px sans-serif"; g.textAlign = "center";
    for (const p of r.peaks ?? []) { // 峰值：向下三角形＋頻率
      if (p.x < fw.f0 || p.x > fw.f1) continue;
      const x = F(p.x), y = Y(p.y);
      g.beginPath(); g.moveTo(x - 4, y - 12); g.lineTo(x + 4, y - 12); g.lineTo(x, y - 4); g.fill();
      g.fillText(tickLabel(p.x, "Hz"), x, y - 15);
    }
    const rf = store.get().rfPos;
    if (rf && rf.x >= fw.f0 && rf.x <= fw.f1) {
      const x = Math.round(F(rf.x)) + 0.5;
      g.strokeStyle = g.fillStyle = "#ffffff"; g.setLineDash([4, 3]);
      g.beginPath(); g.moveTo(x, rect.t); g.lineTo(x, rect.t + rect.h); g.stroke(); g.setLineDash([]);
      g.textAlign = "left"; g.fillText(`RF ${tickLabel(rf.x, "Hz")}${rf.y == null ? "" : "  " + tickLabel(rf.y, unit)}`, x + 4, rect.t + 12);
    }
    g.restore();
  }

  function fetchNow() {
    const r = res();
    if (!r || rect.w < 2) return;
    const fw = win(), req = latest.begin(), px = Math.min(16384, Math.round(rect.w)), id = r.spectrum_id;
    bridge.fetchSpectrum({ id, f0: fw.f0, f1: fw.f1, px, log: log(), signal: req.signal })
      .then((e) => { if (req.ok()) { env = e; yr = yRange(e); draw(); } })
      .catch((e) => {
        if (e?.name === "AbortError" || e?.code === "STALE" || !req.ok()) return; // 頻譜已被新結果取代
        ui.toast(`讀取頻譜失敗：${e.message}`, "error");
      });
  }
  const fetchSoon = debounce(fetchNow, 200);
  const setView = (v) => { view = v; draw(); fetchSoon(); };
  const refreshAll = () => {
    const r = res();
    status.textContent = r ? `RBW ${tickLabel(r.rbw, "Hz")}｜${r.window}｜${r.unit}` : store.get().fftResult?.reason ?? "";
    if ((r?.spectrum_id ?? null) !== resId) { resId = r?.spectrum_id ?? null; env = null; view = null; latest.cancel(); if (r) fetchNow(); }
    draw();
  };
  store.on(["fftResult"], refreshAll);
  store.on(["rfPos"], draw);
  logBox.addEventListener("change", () => { env = null; fetchSoon(); draw(); });

  // RF：按鈕與點擊都只發 rf.intent。x 為目前 RF（無則視窗中心）。
  const rfX = () => store.get().rfPos?.x ?? (win().f0 + win().f1) / 2;
  el.querySelector("[data-rf]").addEventListener("click", (e) => {
    const d = e.target.closest("[data-d]");
    if (d && res()) store.command("rf.intent", { direction: Number(d.dataset.d), x: rfX() });
  });
  const lx = (e) => e.clientX - canvas.getBoundingClientRect().left;
  canvas.addEventListener("pointerdown", (e) => {
    if (e.button !== 0 || !res()) return;
    drag = { x: lx(e), view: win(), moved: false };
    canvas.setPointerCapture(e.pointerId);
  });
  canvas.addEventListener("pointermove", (e) => {
    if (!drag) return;
    const x = lx(e);
    if (Math.abs(x - drag.x) > 3) drag.moved = true;
    if (!drag.moved) return;
    const w = drag.view, F = (log() ? logmap : linear)(w.f0, w.f1, rect.l, rect.l + rect.w);
    const a = F.inv(rect.l - (x - drag.x)), b = F.inv(rect.l + rect.w - (x - drag.x));
    if (Number.isFinite(a) && Number.isFinite(b)) setView({ f0: Math.max(a, 0), f1: b });
  });
  canvas.addEventListener("pointerup", (e) => {
    if (drag && !drag.moved && res()) store.command("rf.intent", { direction: 0, x: Fmap().inv(lx(e)) }); // 點擊＝吸附最近頻格
    drag = null;
  });
  canvas.addEventListener("dblclick", () => { view = null; draw(); fetchSoon(); });
  canvas.addEventListener("wheel", (e) => {
    e.preventDefault();
    if (!res()) return;
    const w = win(), f = e.deltaY > 0 ? 1.25 : 0.8, F = Fmap(), a = F.inv(Math.min(Math.max(lx(e), rect.l), rect.l + rect.w));
    if (log()) setView({ f0: a * (w.f0 / a) ** f, f1: a * (w.f1 / a) ** f });
    else setView({ f0: Math.max(a - (a - w.f0) * f, 0), f1: a + (w.f1 - a) * f });
  }, { passive: false });
  refreshAll();
  return { draw, dispose() { cv.dispose(); latest.cancel(); fetchSoon.cancel(); } };
}
