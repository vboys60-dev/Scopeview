// I3C 解碼狀態與手動工作排程；設定只保留於記憶體。
export const REASONS = {
  parity:'同位錯', t_bit:'T 位交握錯誤', addr_parity:'位址同位錯', addr_7e_read:'非 DAA 的 7E 讀取',
  nack:'未應答', ccc_unknown:'未知 CCC', ccc_invalid:'無效 CCC', ccc_format:'CCC 格式錯誤',
  type_unknown:'類型未確認', ibi_unexpected_payload:'IBI 非預期資料', addr_conflict:'位址資料衝突',
  pattern_incomplete:'形狀不完整', pattern_unknown:'未知形狀', truncated:'資料不完整', ambiguous_edge:'邊沿不明確',
};
export const reasonText = code => REASONS[code] ?? code;
export const defaultConfig = channels => {
  const raw = channels.filter(c => !c.derived);
  return { scl:raw[0]?.name ?? '', sda:raw[1]?.name ?? '', thr:{ scl:null, sda:null }, i2c:[], band:true };
};
/** I2C 清單只接受 7-bit hex 位址；空白＝無清單。 */
export function parseAddresses(text) {
  if (!text.trim()) return [];
  const parts = text.split(',').map(s => s.trim());
  if (parts.some(s => !/^(?:0x)?[\da-f]{1,2}$/i.test(s) || parseInt(s,16) > 127)) throw Error('I2C 位址須為 00–7F，以逗號分隔');
  return [...new Set(parts.map(s => parseInt(s,16)))];
}
export function decodeParams(p) {
  if (!p.scl || !p.sda || p.scl === p.sda) throw Error('請選擇兩個不同的原始通道');
  for (const v of Object.values(p.thr)) if (v !== null && (!v.every(Number.isFinite) || v[0] >= v[1])) throw Error('手動門檻須為有限數，且 lo < hi');
  return { protocol:'i3c', channels:{ scl:p.scl, sda:p.sda }, thresholds:p.thr, options:{ i2c_addrs:p.i2c } };
}
/** frame 時間為來源時間；顯示／跳轉才加 SCL dx。 */
export function jumpView(frame, view, dx = 0) {
  const length = frame.t1-frame.t0, span = view.t1-view.t0;
  const width = length <= span*.8 ? span : length*1.25;
  const center = (frame.t0+frame.t1)/2+dx;
  return { t0:center-width/2, t1:center+width/2 };
}
export function selectFrame(store, frame) {
  const st = store.get(), dx = st.channels.find(c => c.name === st.decodeResult?.scl)?.time_offset ?? 0;
  store.set({ decodeSel:frame.i },'user');
  store.command('viewport.intent',jumpView(frame,st.view,dx));
}
export function createDecode({ store, bridge, ui = {} }) {
  let config = defaultConfig(store.get().channels), gen = store.get().file?.gen, token = 0, busy = false, message = '';
  const subs = new Set(), notify = () => { for (const fn of subs) fn(); };
  store.set({ decodeResult:null, decodeSel:null });
  const current = (t, g) => t === token && g === store.get().file?.gen;
  function change(patch = {}) {
    if (Object.keys(patch).length === 1 && 'band' in patch) { config = { ...config,...patch }; notify(); return; }
    token++; busy = false; message = ''; config = { ...config, ...patch };
    const old = store.get().decodeResult;
    if (old) store.set({ decodeResult:{ ...old, stale:true } });
    notify();
  }
  store.on(['file'],st => {
    if (gen === st.file?.gen) return;
    gen = st.file?.gen; token++; busy = false; message = ''; config = defaultConfig(st.channels);
    store.set({ decodeResult:null, decodeSel:null }); notify();
  });
  async function run() {
    const t = ++token, g = store.get().file?.gen;
    store.set({ decodeResult:null, decodeSel:null });
    try {
      if (!store.get().file) throw Error('請先開啟波形檔');
      const params = decodeParams(config);
      busy = true; message = ''; notify();
      const summary = await bridge.job('decode',params);
      if (!current(t,g)) return;
      if (summary.gen !== g) { message = '解碼結果已過期，請重新解碼'; return; }
      if (!summary.ok) { message = summary.reason; return; }
      const data = await bridge.call('decode_frames',{ decode_id:summary.decode_id });
      if (!current(t,g)) return;
      store.set({ decodeResult:{ summary, frames:data.frames, addresses:data.addresses, scl:params.channels.scl, stale:false }, decodeSel:null });
    } catch (e) {
      if (current(t,g)) { message = e.message ?? String(e); ui.showError?.(e,'解碼失敗'); }
    } finally {
      if (current(t,g)) { busy = false; notify(); }
    }
  }
  async function exportCsv() {
    const r = store.get().decodeResult;
    if (!r || r.stale || r.summary.gen !== store.get().file?.gen) { ui.toast?.('解碼結果已過期，請重新解碼','info'); return; }
    try {
      const result = await bridge.call('export_decode',{ decode_id:r.summary.decode_id, directory:null });
      ui.toast?.(`已匯出 CSV：${result.path}`,'info');
      return result;
    } catch (e) {
      if (e.code === 'STALE') ui.toast?.('解碼結果已過期，請重新解碼','info');
      else ui.showError?.(e,'匯出解碼失敗');
    }
  }
  return { get config() { return config; }, get busy() { return busy; }, get message() { return message; },
    change, run, exportCsv, on(fn) { subs.add(fn); return () => subs.delete(fn); } };
}
const models = new WeakMap();
export function decodeModel(ctx) {
  if (!models.has(ctx.store)) models.set(ctx.store,createDecode(ctx));
  return models.get(ctx.store);
}
