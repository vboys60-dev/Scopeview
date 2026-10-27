// 已註冊協定的固定小向量與快照生命週期；獨立於 UI。
import * as protocols from './analysis/decode_protocols.js';
import { decodeParams } from './analysis/decode.js';
import { BridgeError } from './bridge.js';
let serial = 0;
export function makeDecode({ job, needFile, chan, generation }) {
  let snapshot = null;
  const bad = (s) => { throw new BridgeError('BAD_REQUEST', s, false); };
  const finite = (v) => typeof v === 'number' && Number.isFinite(v);
  const get = (id) => {
    if (typeof id !== 'string') bad('decode_id 必須為字串');
    if (!snapshot || snapshot.decode_id !== id || snapshot.gen !== generation()) throw new BridgeError('STALE', '解碼結果已過期', false);
    return snapshot;
  };
  return {
    decode: (p) => job('decode', () => {
      const estimating = p.protocol === 'uart' && p.options?.estimate === true;
      if (!estimating) snapshot = null;
      needFile();
      const def = protocols[p.protocol];
      if (!def) bad('不支援的協定');
      if (!p.channels || Array.isArray(p.channels) || Object.keys(p.channels).some(k => !def.roles.some(r => r.key === k)) || !Object.values(p.channels).every(v => typeof v === 'string')) bad('channels 無效');
      const lines = Object.keys(p.channels).filter(k => !def.diff?.[k]).sort().join(' ');
      if (!p.thresholds || Object.keys(p.thresholds).sort().join(' ') !== lines) bad('thresholds 無效');
      for (const th of Object.values(p.thresholds)) if (th !== null && !(Array.isArray(th) && th.length === 2 && th.every(finite) && th[0] < th[1])) bad('門檻無效');
      try { decodeParams({ protocol:p.protocol,ch:p.channels,thr:p.thresholds,opt:p.options },def); } catch (e) { bad(e.message); }
      Object.values(p.channels).forEach(chan);
      if (!p.options || typeof p.options !== 'object' || Array.isArray(p.options) || Object.keys(p.options).some(k => !def.options.some(o => o.key === k) && !(p.protocol === 'uart' && k === 'estimate'))) bad('options 無效');
      if (p.protocol === 'uart' && 'estimate' in p.options && typeof p.options.estimate !== 'boolean') bad('estimate 須為布林值');
      for (const o of def.options) if (o.parse && o.key in p.options && !(estimating && o.key === 'baud')) {
        if (Array.isArray(o.parse(String(o.value))) && !Array.isArray(p.options[o.key])) bad('options 無效');
        try { o.parse(Array.isArray(p.options[o.key]) ? p.options[o.key].map(v => typeof v === 'number' ? v.toString(16) : '!').join(',') : String(p.options[o.key])); } catch (e) { bad(e.message); }
      }
      if (p.protocol === 'i2c' && 'addr_bits' in p.options && ![7,8].includes(p.options.addr_bits)) bad('I2C addr_bits 須為 7 或 8 的整數');
      if (estimating) return { ok:false,reason:'估計鮑率 9600；估計值取最短脈寬，請確認',gen:generation(),decode_id:null,protocol:p.protocol,channels:p.channels,thresholds:p.thresholds,t0:null,t1:null,counts:{ frames:0,fields:0,errors:0,warns:0 },truncated:false,warnings:[] };
      const { frames,addresses } = structuredClone(def.sample);
      snapshot = { decode_id: `d${++serial}`, gen: generation(), frames, addresses };
      return { ok: true, reason: null, gen: snapshot.gen, decode_id: snapshot.decode_id, protocol: p.protocol, channels: p.channels,
        thresholds: Object.fromEntries(Object.entries(p.thresholds).map(([k,v]) => [k,v ?? [0.4,0.6]])),
        t0: frames[0]?.t0 ?? 0, t1: frames.at(-1)?.t1 ?? 0, counts: { frames: frames.length, fields: frames.reduce((n,f) => n+f.fields.length,0), errors: frames.filter(f => f.status === 'error').length, warns: frames.filter(f => f.status === 'warn').length }, truncated: false, warnings: [] };
    }),
    decode_frames: ({ decode_id }) => { const s = get(decode_id); return { decode_id, frames: s.frames, addresses: s.addresses }; },
    decode_bits: ({ decode_id, t0, t1 }) => {
      if (!finite(t0) || !finite(t1)) bad('時間須有限');
      get(decode_id); const [lo,hi] = [t0,t1].sort((a,b) => a-b);
      return { bits: Array.from({length:9}, (_,i) => [21+i, [1,0,1,0,0,1,0,1,1][i]]).filter(([t]) => t >= lo && t <= hi), truncated: false };
    },
    export_decode: ({ decode_id, directory }) => {
      if (directory !== null && typeof directory !== 'string') bad('directory 無效');
      get(decode_id); return { path: `${directory ?? '/mock/Desktop'}/demo_解碼_20261026_120000.csv` };
    },
  };
}
