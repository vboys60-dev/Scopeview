// I2C 的通道、文案與固定小向量；欄位形狀沿用核心輸出。
import { fmt } from '../fmt.js';
import i3c, { hex } from './decode_i3c.js';

const reasons = {
  nack:'未應答', byte_cut:'位元組遭中斷', empty:'空交易', start_byte_ack:'START byte 不應應答',
  hs_code_ack:'Hs 控制碼不應應答', gc_invalid:'無效 General Call', addr10_unresolved:'10-bit 位址未確認',
  reserved_addr:'保留位址', sda_glitch:'SDA 異常跳變', truncated:'資料不完整', ambiguous_edge:'邊沿不明確',
};
const kinds = { write:'寫入', read:'讀取', gc:'General Call', start_byte:'START byte', hs_code:'Hs 控制碼', empty:'空交易', partial:'不完整區段' };
function content(f) {
  const names = f.kind === 'gc' ? ['General Call', ...f.fields.filter(x => x.kind === 'data').map(x => x.label)]
    : f.kind === 'start_byte' ? ['START byte'] : [];
  const data = f.fields.filter(x => x.kind === 'data').map(x =>
    (x.ninth === 1 || !x.ok ? '⚠' : '')+(x.value == null ? x.label : hex(x.value)));
  return [...data,...names].filter(Boolean).join(' ') || f.label || kinds[f.kind] || f.kind;
}
const field = (t, kind, value, ninth = 0) => ({ t0:t, t1:t+8, kind, addr:null, value, nbits:9,
  ninth, ninth_kind:'ack', ok:true, label:'' });
const frame = (i, kind, addr, rw, fields, label = '') => ({ i, t0:i*30, t1:i*30+29, kind, start:'S', addr, rw,
  ack:true, ccc:null, ccc_name:null, label, status:'ok', reasons:[], fields });
const frames = [frame(0,'write',0x50,0,[field(1,'addr',0xA0),field(11,'data',0x12)]),
  frame(1,'read',0x50,1,[field(31,'addr',0xA1),field(41,'data',0xAB,1)]),
  frame(2,'gc',0,0,[field(61,'addr',0),{ ...field(71,'data',6),label:'重設並寫入可程式位址' }],'General Call')];

export default {
  name:'i2c', label:'I2C', order:1, base:'scl', diff:{},
  roles:[{ key:'scl',label:'SCL' },{ key:'sda',label:'SDA' }], options:[], reasons, kinds,
  eventKind:f => kinds[f.kind] ?? f.kind, content,
  columns:[{ head:'位址',cell:f => hex(f.addr,f.addr > 0x7F || f.fields.some(x => x.kind === 'addr_lo' || x.kind === 'addr' && (x.value & 0xF8) === 0xF0) ? 3 : 2) },
    { head:'R/W',cell:f => f.rw == null ? '—' : f.rw ? 'R' : 'W' }],
  fieldText:i3c.fieldText, lanes:() => null, laneLabels:{}, addresses:null, reportSummary:true,
  summary:s => 'I2C · 門檻 '+['scl','sda'].map(k => `${k.toUpperCase()} ${s.thresholds[k]?.map(v => fmt(v,'V',3)).join(' / ') ?? '—'}`).join('；'),
  sample:{ frames,addresses:[] },
};
