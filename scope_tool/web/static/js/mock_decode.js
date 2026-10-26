// I3C 固定小向量與快照生命週期；獨立於 UI。
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
  const field = (t, kind, value, ok = true) => ({ t0: t, t1: t + 8, kind, addr: null, value, nbits: 8,
    ninth: 1, ninth_kind: 'parity', ok, label: kind });
  const frame = (i, kind, fields, reasons = []) => ({ i, t0: i * 20, t1: i * 20 + 19, kind, start: 'S', addr: 48, rw: 0,
    ack: true, ccc: kind === 'ccc_broadcast' ? 0 : null, ccc_name: kind === 'ccc_broadcast' ? 'ENEC' : null,
    label: kind, status: reasons.length ? 'error' : 'ok', reasons, fields });
  return {
    decode: (p) => job('decode', () => {
      snapshot = null; needFile();
      if (p.protocol !== 'i3c') bad('目前只支援 i3c');
      if (!p.channels || Object.keys(p.channels).sort().join(' ') !== 'scl sda' ||
          !Object.values(p.channels).every(v => typeof v === 'string') || p.channels.scl === p.channels.sda) bad('channels 無效');
      Object.values(p.channels).forEach(chan);
      if (!p.thresholds || Object.keys(p.thresholds).sort().join(' ') !== 'scl sda') bad('thresholds 無效');
      for (const th of Object.values(p.thresholds)) if (th !== null && !(Array.isArray(th) && th.length === 2 && th.every(finite) && th[0] < th[1])) bad('門檻無效');
      if (!p.options || Array.isArray(p.options) || Object.keys(p.options).some(k => k !== 'i2c_addrs') ||
          ('i2c_addrs' in p.options && (!Array.isArray(p.options.i2c_addrs) || p.options.i2c_addrs.some(v => !Number.isInteger(v) || v < 0 || v > 127)))) bad('options 無效');
      const frames = [frame(0, 'ccc_broadcast', [field(1, 'ccc', 0)]),
        frame(1, 'private_write', [field(21, 'data', 0xA5, false)], ['parity']), frame(2, 'ibi', [field(41, 'mdb', 0x80)])];
      snapshot = { decode_id: `d${++serial}`, gen: generation(), frames, addresses: [] };
      return { ok: true, reason: null, gen: snapshot.gen, decode_id: snapshot.decode_id, protocol: 'i3c', channels: p.channels,
        thresholds: Object.fromEntries(Object.entries(p.thresholds).map(([k,v]) => [k,v ?? [0.4,0.6]])),
        t0: 0, t1: 59, counts: { frames: 3, fields: 3, errors: 1, warns: 0 }, truncated: false, warnings: [] };
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
