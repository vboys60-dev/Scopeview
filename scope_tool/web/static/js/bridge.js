// 前後端唯一的傳輸層：其他檔案不得直接 fetch、不得知道 HTTP 或 mock 的存在。
// ?mock=1 → mock_backend.js；否則 HTTP（/rpc、/wave、/fft、long-poll wait_events），token 取自頁面 URL ?k=。
export class BridgeError extends Error {
  constructor(code, message, retryable = false) { super(message); this.name = "BridgeError"; this.code = code; this.retryable = retryable; }
}

const search = typeof location === "undefined" ? "" : location.search;
export const MOCK = new URLSearchParams(search).get("mock") === "1";

/** 解碼 /wave、/fft 二進位（little-endian）：16 byte header（n, mode, 0, 0）＋ float64 x[n] ＋ float32 lo[n] ＋ float32 hi[n]。 */
export function decodeWave(buf) {
  if (buf.byteLength < 16) throw new BridgeError("BAD_BINARY", "波形資料長度不足");
  const dv = new DataView(buf);
  const n = dv.getUint32(0, true), mode = dv.getUint32(4, true);
  if (mode > 1) throw new BridgeError("BAD_BINARY", `波形資料 mode 無效：${mode}`);
  if (dv.getUint32(8, true) !== 0 || dv.getUint32(12, true) !== 0) throw new BridgeError("BAD_BINARY", "波形資料保留欄位非 0");
  if (buf.byteLength !== 16 + 16 * n) throw new BridgeError("BAD_BINARY", `波形資料長度不符：${buf.byteLength} ≠ ${16 + 16 * n}`);
  // 位移 16、16+8n、16+12n 皆為對應型別的整數倍，可直接建立 view（零複製）
  return { n, mode, x: new Float64Array(buf, 16, n), lo: new Float32Array(buf, 16 + 8 * n, n), hi: new Float32Array(buf, 16 + 12 * n, n) };
}

/** 非 200 回應 → BridgeError：優先取 JSON {ok:false,error}；非 JSON（例如 500 HTML）依狀態碼。 */
async function toError(r) {
  let e = null;
  try { e = (await r.json())?.error; } catch { /* 非 JSON */ }
  if (e?.code) return new BridgeError(e.code, e.message ?? "", !!e.retryable);
  if (r.status === 403) return new BridgeError("FORBIDDEN", "存取權杖無效，請重新開啟程式");
  if (r.status === 404) return new BridgeError("NOT_FOUND", "找不到此方法或資源");
  return new BridgeError("UNEXPECTED", `伺服器回應異常（HTTP ${r.status}）`);
}

/** HTTP 傳輸。 */
function httpTransport() {
  const k = new URLSearchParams(search).get("k") ?? "";
  const q = (o) => new URLSearchParams({ ...o, k }).toString();
  const net = async (url, init) => {
    let r;
    try { r = await fetch(url, init); } catch (e) {
      if (e.name === "AbortError") throw e;
      throw new BridgeError("NETWORK", "無法連線到本機服務", true);
    }
    if (!r.ok) throw await toError(r);
    return r;
  };
  return {
    async rpc(method, params, requestId) {
      const body = requestId ? { ...params, request_id: requestId } : params;
      const r = await net(`/rpc/${method}?${q({})}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body ?? {}) });
      try { return await r.json(); } catch { throw new BridgeError("UNEXPECTED", "伺服器回應不是 JSON"); }
    },
    async binary(path, query, signal) { return (await net(`${path}?${q(query)}`, { signal })).arrayBuffer(); },
    url: (path, query) => `${path}?${q(query)}`,
    subscribe(handler, since = 0) { // long-poll：每次最多等 25 秒；斷線 1 秒後重試
      let stop = false;
      (async () => {
        while (!stop) {
          try {
            const r = await this.rpc("wait_events", { since, timeout: 25 });
            if (!r.ok) throw new Error(r.error?.message);
            since = Math.max(since, r.result.seq);
            r.result.events.forEach(handler);
          } catch { await new Promise((ok) => setTimeout(ok, 1000)); }
        }
      })();
      return () => { stop = true; };
    },
  };
}

let rid = 0;
const newId = () => `r${++rid}-${Math.random().toString(36).slice(2, 8)}`;
const failEv = (ev) => new BridgeError(ev.error?.code ?? "UNEXPECTED", ev.error?.message ?? "未預期錯誤", !!ev.error?.retryable);

/** 建立 bridge；transport 可為物件或 Promise（測試時傳 mock）。opts.gapMs＝序號斷層容忍毫秒，earlyMax＝早到事件暫存上限。 */
export function makeBridge(transport, isMock = false, { gapMs = 2000, earlyMax = 1000, dedupeMax = 256 } = {}) {
  const tp = Promise.resolve(transport);
  const listeners = new Map(); // type → Set<fn>
  const waiters = new Map(); // job id → {resolve, reject}
  const early = new Map(); // 比 RPC 回應先到的 job 事件
  const lost = new Set(); // 早到暫存超限而被擠出的工作代號：job() 遇到就失敗，不得永遠等待
  const done = new Map(); // requestId → Promise（進行中與已完成皆保留，最近 dedupeMax 筆）
  const held = new Map(); // seq → 尚未輪到的事件（亂序緩衝）
  let next = 1, gapTimer = null, ready = null, epoch = 0; // epoch：每次 desync 加 1，RPC 發出後遇到 desync 的工作不可再等

  const settle = (ev, w) => (ev.ok ? w.resolve(ev.result) : w.reject(failEv(ev)));
  function emitLocal(ev) { // 派送給訂閱者；單一 listener 丟例外不影響其他
    for (const fn of [...(listeners.get(ev.type) ?? [])]) {
      try { fn(ev); } catch (e) { console.error(`bridge listener(${ev.type}) 例外`, e); }
    }
  }
  function deliver(ev) {
    if (ev.type === "job") {
      const w = waiters.get(ev.id);
      if (w) { waiters.delete(ev.id); settle(ev, w); } else {
        early.set(ev.id, ev);
        if (early.size > earlyMax) { // 超限 → 把最舊的記成 lost（之後 job() 會明確失敗），不靜默丟棄
          const [oldId] = early.keys(); early.delete(oldId); lost.add(oldId);
          if (lost.size > earlyMax * 4) lost.delete(lost.values().next().value);
        }
      }
    }
    emitLocal(ev);
  }
  /** 序號斷層：先把已收到的後續事件依序送出，再讓所有仍在等待的工作以 NETWORK 失敗（結果未知，提示重新整理）。 */
  function desync() {
    while (held.size) { next = Math.min(...held.keys()); drain(true); }
    const err = () => new BridgeError("NETWORK", "事件連線序號中斷，工作結果未知，請重新整理頁面確認", true);
    for (const [id, w] of [...waiters]) { waiters.delete(id); w.reject(err()); }
    early.clear(); epoch++;
    emitLocal({ type: "desync", message: err().message });
  }
  function drain(force = false) {
    while (held.has(next)) { const ev = held.get(next); held.delete(next); next++; deliver(ev); }
    clearTimeout(gapTimer); gapTimer = null;
    if (held.size && !force) gapTimer = setTimeout(() => { gapTimer = null; if (held.size) desync(); }, gapMs);
  }
  /** 事件入口：依 seq 排序、去重；缺口超過 gapMs 視為斷層。 */
  function onEvent(ev) {
    if (ev.seq < next || held.has(ev.seq)) return; // 重複或舊事件
    held.set(ev.seq, ev);
    drain();
  }
  /** 第一次使用才啟動：先讀 get_state().seq，從目前序號起收（不重播舊事件）。 */
  const ensure = () => (ready ??= (async () => {
    const t = await tp;
    const st = await t.rpc("get_state", {});
    const seq = st?.ok ? st.result.seq ?? 0 : 0;
    next = seq + 1;
    t.subscribe(onEvent, seq);
    return t;
  })().catch((e) => { ready = null; throw e; }));

  async function rpc(method, params, requestId) {
    const r = await (await ensure()).rpc(method, params ?? {}, requestId);
    if (!r?.ok) throw new BridgeError(r?.error?.code ?? "UNEXPECTED", r?.error?.message ?? "未預期錯誤", !!r?.error?.retryable);
    return r.result;
  }
  async function run(method, params, requestId) {
    const ep = epoch, res = await rpc(method, params, requestId);
    if (res?.done) return new Promise((resolve, reject) => settle(res.done, { resolve, reject })); // 重送已完成的工作
    const id = res?.job;
    if (!id) throw new BridgeError("UNEXPECTED", `${method} 未回傳工作代號`);
    if (ep !== epoch) throw new BridgeError("NETWORK", "事件連線序號中斷，工作結果未知，請重新整理頁面確認", true); // RPC 期間發生 desync：事件可能已被清掉，不可永遠等待
    if (lost.delete(id)) throw new BridgeError("NETWORK", "工作結果事件遺失，請重新整理頁面確認", true);
    if (early.has(id)) { const ev = early.get(id); early.delete(id); return new Promise((resolve, reject) => settle(ev, { resolve, reject })); }
    return new Promise((resolve, reject) => waiters.set(id, { resolve, reject }));
  }
  async function bin(path, query, signal) {
    const t = await ensure();
    try { return decodeWave(await t.binary(path, query, signal)); } catch (e) {
      if (e instanceof BridgeError || e?.name === "AbortError") throw e;
      throw new BridgeError("UNEXPECTED", e?.message ?? String(e));
    }
  }

  return {
    MOCK: isMock,
    /** 快速方法：直接回結果。失敗丟 BridgeError（BUSY 也是同步 ok:false）。 */
    call: (method, params) => rpc(method, params),
    /** 工作型方法：回傳 Promise，於 job 事件到達時完成。同一 requestId 並行或事後重送都共用同一個 Promise（可重試的失敗除外）。 */
    job(method, params, { requestId = newId() } = {}) {
      if (done.has(requestId)) return done.get(requestId);
      const p = run(method, params, requestId).catch((e) => { if (e.retryable) done.delete(requestId); throw e; });
      done.set(requestId, p);
      if (done.size > dedupeMax) done.delete(done.keys().next().value);
      return p;
    },
    /** 訂閱非工作事件："driver"（儀器連線狀態）、"desync"（事件序號中斷，應提示重新整理）。回傳取消函式。 */
    on(type, fn) {
      ensure().catch(() => {});
      if (!listeners.has(type)) listeners.set(type, new Set());
      listeners.get(type).add(fn);
      return () => listeners.get(type).delete(fn);
    },
    /** 取降採樣包絡：{ch, t0, t1, px, gen, signal?} → {n, mode, x, lo, hi}；t0／t1／x 皆來源時間；gen 不符丟 STALE。 */
    fetchWave: ({ ch, t0, t1, px, gen, signal }) => bin("/wave", { ch, t0, t1, px, gen }, signal),
    /** 取頻譜包絡：{id, f0, f1, px, log?, signal?} → 同上（x 為 Hz）。 */
    fetchSpectrum: ({ id, f0, f1, px, log = false, signal }) => bin("/fft", { id, f0, f1, px, log: log ? 1 : 0 }, signal),
    /** 最近一張截圖的 URL（給 <img src>）；n 為截圖結果的 preview 序號（整數，只用來避開快取）。 */
    async screenshotUrl(n) { return (await ensure()).url("/screenshot/last", { n }); },
  };
}

export const bridge = makeBridge(MOCK ? import("./mock_backend.js").then((m) => m.createMock()) : httpTransport(), MOCK);
export default bridge;
