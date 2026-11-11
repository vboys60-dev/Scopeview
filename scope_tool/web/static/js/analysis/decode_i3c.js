// I3C 的設定、文案與固定小向量。
import { fmt } from '../fmt.js';
export const REASONS = {
  parity:'同位錯', t_bit:'T 位交握錯誤', addr_parity:'位址同位錯', addr_7e_read:'非 DAA 的 7E 讀取',
  nack:'未應答', ccc_unknown:'未知 CCC', ccc_invalid:'無效 CCC', ccc_format:'CCC 格式錯誤',
  type_unknown:'類型未確認', ibi_unexpected_payload:'IBI 非預期資料', addr_conflict:'位址資料衝突',
  pattern_incomplete:'形狀不完整', pattern_unknown:'未知形狀', truncated:'資料不完整', ambiguous_edge:'邊沿不明確',
  hdr_nack:'HDR 未應答', hdr_parity:'HDR 同位錯', hdr_crc:'HDR CRC 錯', hdr_preamble:'HDR 前導碼錯誤',
};
export const reasonText = code => REASONS[code] ?? code;
/** I2C 清單只接受 7-bit hex 位址；空白＝無清單。 */
export function parseAddresses(text) {
  if (!text.trim()) return [];
  const parts = text.split(',').map(s => s.trim());
  if (parts.some(s => !/^(?:0x)?[\da-f]{1,2}$/i.test(s) || parseInt(s,16) > 127)) throw Error('I2C 位址須為 00–7F，以逗號分隔');
  return [...new Set(parts.map(s => parseInt(s,16)))];
}
export const hex = (v, width = 2) => v == null ? '—' : '0x'+v.toString(16).toUpperCase().padStart(width,'0');
export const eventKind = f => ({ private_write:'私有寫', private_read:'私有讀', ccc_broadcast:'CCC 廣播', ccc_direct:'CCC 直接',
  daa:'DAA 指派', ibi:'IBI', hotjoin:'Hot-Join', i2c:f.rw ? 'I2C 讀' : 'I2C 寫', hdr:'HDR 區段', hdr_exit:'HDR Exit',
  target_reset:'Target Reset', pattern:'形狀', partial:'不完整區段', error:'錯誤' })[f.kind] ?? f.kind;
export function frameContent(f) {
  return [f.ccc_name, ...f.fields.filter(x => x.kind !== 'addr').map(x =>
    (x.ok ? '' : '⚠')+({ hdr_cmd:'命令 ', hdr_data:'資料 ', hdr_crc:'CRC ' }[x.kind] ?? '')+(x.value == null ? x.label : hex(x.value,Math.ceil((x.nbits-(x.ninth_kind ? 1 : 0))/4)))+(x.kind === 'pid' ? ' PID' : ''))].filter(Boolean).join(' ') || f.label;
}
const field = (t, kind, value, ok = true) => ({ t0: t, t1: t + 8, kind, addr: null, value, nbits: 8,
    ninth: 1, ninth_kind: 'parity', ok, label: kind });
const frame = (i, kind, fields, reasons = []) => ({ i, t0: i * 20, t1: i * 20 + 19, kind, start: 'S', addr: 48, rw: 0,
    ack: true, ccc: kind === 'ccc_broadcast' ? 0 : null, ccc_name: kind === 'ccc_broadcast' ? 'ENEC' : null,
    label: kind, status: reasons.length ? 'error' : 'ok', reasons, fields });

const frames = [frame(0, 'ccc_broadcast', [field(1, 'ccc', 0)]),
  frame(1, 'private_write', [field(21, 'data', 0xA5, false)], ['parity']), frame(2, 'ibi', [field(41, 'mdb', 0x80)])];
export default {
  name:'i3c', label:'I3C', order:0, base:'scl', diff:{},
  roles:[{ key:'scl',label:'SCL' },{ key:'sda',label:'SDA' }],
  options:[{ key:'i2c_addrs',label:'I2C 位址',type:'text',value:'',placeholder:'50, 51',parse:parseAddresses }],
  reasons:REASONS,
  kinds:{ private_write:'私有寫',private_read:'私有讀',ccc_broadcast:'CCC 廣播',ccc_direct:'CCC 直接',daa:'DAA 指派',ibi:'IBI',hotjoin:'Hot-Join',i2c:'I2C',hdr:'HDR 區段',hdr_exit:'HDR Exit',target_reset:'Target Reset',pattern:'形狀',partial:'不完整區段',error:'錯誤' },
  eventKind, content:frameContent,
  columns:[{ head:'位址',cell:f => hex(f.addr) },{ head:'R/W',cell:f => f.rw == null ? '—' : f.rw ? 'R' : 'W' }],
  fieldText:x => ({ hdr_cmd:'命令 ', hdr_data:'資料 ', hdr_crc:'CRC ' }[x.kind] ?? '') + (x.value == null ? x.label : x.kind === 'addr' ? (x.value>>1).toString(16).toUpperCase().padStart(2,'0')+(x.value & 1 ? ' R' : ' W') : x.value.toString(16).toUpperCase().padStart(Math.ceil((x.nbits-(x.ninth_kind ? 1 : 0))/4),'0')),
  lanes:() => null, laneLabels:{}, reportSummary:false,
  addresses:{ head:['DA','PID','BCR','DCR','起','迄','來源','備註'],row:(a,F,dx) =>
    [hex(a.da),hex(a.pid,12),hex(a.bcr),hex(a.dcr),a.t_from == null ? '未知（擷取前）' : F(a.t_from+dx,'s'),
      a.t_to == null ? '—' : F(a.t_to+dx,'s'),a.how === 'observed' ? '觀察到（未確認）' : a.how,a.note ?? ''] },
  summary:s => 'I3C Basic SDR · 門檻 '+['scl','sda'].map(k => `${k.toUpperCase()} ${s.thresholds[k]?.map(v => fmt(v,'V',3)).join(' / ') ?? '—'}`).join('；'),
  sample:{ frames,addresses:[] },
};
