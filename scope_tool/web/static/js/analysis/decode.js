// 解碼狀態與手動工作排程；每協定設定只保留於記憶體。
import * as protocols from './decode_protocols.js';
export { REASONS, reasonText, parseAddresses, eventKind, frameContent } from './decode_i3c.js';
export const definition = name => protocols[name ?? 'i3c'];
/** ASCII 顯示：只對 8 位元資料欄位（不含位址、PID 等）；不可印字元顯示 '.'。 */
const ASCII_KINDS = new Set(['data','mdb','tx','rx']);
export const isByteField = x => ASCII_KINDS.has(x.kind) && x.value != null && x.nbits-(x.ninth_kind ? 1 : 0) === 8;
export const asciiChar = v => v >= 32 && v < 127 ? String.fromCharCode(v) : '.';
/** 事件表／報告的內容欄尾端加 "ascii"（開關開啟時）。 */
export function withAscii(f, text, on) {
  const s = on ? f.fields.filter(isByteField).map(x => asciiChar(x.value)).join('') : '';
  return s ? `${text} "${s}"` : text;
}
export const defaultConfig = (channels, def = protocols.i3c) => {
  const raw = channels.filter(c => !c.derived);
  const ch = Object.fromEntries(def.roles.map((r,i) => [r.key,r.optional ? '' : raw[i]?.name ?? '']));
  return { protocol:def.name,ch,thr:Object.fromEntries(def.roles.filter(r => !def.diff?.[r.key]).map(r => [r.key,null])),
    opt:Object.fromEntries(def.options.map(o => [o.key,o.parse ? o.parse(String(o.value)) : o.value])),band:true };
};
export function decodeParams(p, def = definition(p.protocol)) {
  const channels = Object.fromEntries(Object.entries(p.ch).filter(([,v]) => v));
  if (!Object.keys(channels).length || def.roles.some(r => !r.optional && !channels[r.key] && !(def.name === 'uart' && p.opt.estimate === true)) || new Set(Object.values(channels)).size !== Object.keys(channels).length) throw Error('請選擇不同的原始通道並填齊必填角色');
  const thresholds = Object.fromEntries(Object.entries(p.thr).filter(([k]) => channels[k] && !def.diff?.[k]));
  for (const v of Object.values(thresholds)) if (v !== null && (!v.every(Number.isFinite) || v[0] >= v[1])) throw Error('手動門檻須為有限數，且 lo < hi');
  return JSON.parse(JSON.stringify({ protocol:def.name,channels,thresholds,options:p.opt }));
}
/** frame 時間為來源時間；顯示／跳轉才加 基準通道 dx。 */
export function jumpView(frame, view, dx = 0) {
  const length = frame.t1-frame.t0, span = view.t1-view.t0;
  const width = length <= span*.8 ? span : length*1.25;
  const center = (frame.t0+frame.t1)/2+dx;
  return { t0:center-width/2, t1:center+width/2 };
}
export function selectFrame(store, frame) {
  const st = store.get(), dx = st.channels.find(c => c.name === st.decodeResult?.base)?.time_offset ?? 0;
  store.set({ decodeSel:frame.i },'user');
  store.command('viewport.intent',jumpView(frame,st.view,dx));
}
export function createDecode({ store, bridge, ui = {} }) {
  let configs = {}, config = defaultConfig(store.get().channels), gen = store.get().file?.gen, token = 0, busy = false, message = '', ascii = true;
  const subs = new Set(), notify = () => { for (const fn of subs) fn(); };
  store.set({ decodeResult:null, decodeSel:null, decodeAscii:ascii });
  const current = (t, g) => t === token && g === store.get().file?.gen;
  function change(patch = {}) {
    if (Object.keys(patch).length === 1 && 'ascii' in patch) { ascii = !!patch.ascii; store.set({ decodeAscii:ascii }); notify(); return; }
    if (Object.keys(patch).length === 1 && 'band' in patch) { config = { ...config,...patch }; notify(); return; }
    token++; busy = false; message = ''; configs[config.protocol] = config;
    config = patch.protocol ? (configs[patch.protocol] ?? defaultConfig(store.get().channels,definition(patch.protocol))) : { ...config,...patch };
    configs[config.protocol] = config;
    const old = store.get().decodeResult;
    if (old) store.set({ decodeResult:{ ...old, stale:true } });
    notify();
  }
  store.on(['file'],st => {
    if (gen === st.file?.gen) return;
    gen = st.file?.gen; token++; busy = false; message = ''; configs = {}; config = defaultConfig(st.channels);
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
      store.set({ decodeResult:{ summary, frames:data.frames, addresses:data.addresses, protocol:params.protocol, base:params.channels[definition(params.protocol).base], options:params.options, stale:false }, decodeSel:null });
    } catch (e) {
      if (current(t,g)) { message = e.message ?? String(e); ui.showError?.(e,'解碼失敗'); }
    } finally {
      if (current(t,g)) { busy = false; notify(); }
    }
  }
  async function estimate(apply) {
    if (busy) return;
    const t = ++token, g = store.get().file?.gen;
    try {
      if (!store.get().file) throw Error('請先開啟波形檔');
      const params = decodeParams({ ...config,opt:{ ...config.opt,estimate:true } });
      busy = true; message = ''; notify();
      const summary = await bridge.job('decode',params);
      if (!current(t,g)) return;
      if (summary.gen !== g) { message = '估計結果已過期，請重新估計'; return; }
      busy = false;
      // apply 只在世代與設定仍有效時填欄位；input 事件才讓結果標示過期。
      message = apply(summary);
      notify();
    } catch (e) {
      if (current(t,g)) message = e.message ?? String(e);
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
  return { get config() { return config; }, get busy() { return busy; }, get message() { return message; }, get ascii() { return ascii; },
    change, run, estimate, exportCsv, on(fn) { subs.add(fn); return () => subs.delete(fn); } };
}
const models = new WeakMap();
export function decodeModel(ctx) {
  if (!models.has(ctx.store)) models.set(ctx.store,createDecode(ctx));
  return models.get(ctx.store);
}
