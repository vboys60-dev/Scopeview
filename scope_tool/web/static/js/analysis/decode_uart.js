// UART 的格式設定、雙線顯示與固定小向量。
import { fmt } from '../fmt.js';

const reasons = { framing:'停止位錯誤', parity:'同位錯', short_stop:'停止位過短', break:'BREAK 中斷',
  truncated:'資料不完整', unsynced:'尚未同步', unknown_bit:'未知位元' };
const kinds = { chars:'字元',unsynced:'尚未同步' };
const dataBits = x => x.nbits-(x.ninth_kind === 'parity' ? 1 : 0);
const fieldText = x => x.value == null ? x.label : x.value.toString(16).toUpperCase().padStart(dataBits(x) > 8 ? 3 : 2,'0');
function content(f) {
  const lanes = ['tx','rx'].map(lane => {
    const fields = f.fields.filter(x => x.kind === lane);
    if (!fields.length) return '';
    return lane.toUpperCase()+' '+fields.map(x => (x.ok ? '' : '⚠')+fieldText(x)).join(' ');
  }).filter(Boolean);
  return lanes.join('／') || f.label || kinds[f.kind] || f.kind;
}
const field = (kind, value) => ({ t0:1.5, t1:8.5, kind, addr:null, value, nbits:8,
  ninth:null, ninth_kind:null, ok:true, label:'' });
const frame = (i, kind, fields, reasons = []) => ({ i, t0:i*20, t1:i*20+10, kind, start:null,
  addr:null, rw:null, ack:null, ccc:null, ccc_name:null, label:kind === 'chars' ? 'He' : '',
  status:reasons.length ? 'warn' : 'ok', reasons, fields });
const frames = [frame(0,'chars',[field('tx',0x48),field('rx',0x65)]),frame(1,'unsynced',[],['unsynced'])];

// 固定前綴與可選提示分開比對，避免把錯誤訊息中的數字填入欄位。
export function estimatedBaud(summary) {
  const match = summary.ok === false && /^估計鮑率 ([1-9]\d*)(?:；估計值取最短脈寬，請確認)?$/.exec(summary.reason ?? '');
  return match && Number.isSafeInteger(+match[1]) ? +match[1] : null;
}
const estimate = { label:'估計',key:'estimate',run:({ model,input }) => model.estimate(summary => {
  const baud = estimatedBaud(summary);
  if (baud === null) return summary.reason || '無法估計鮑率：回應無效';
  input.value = String(baud); input.dispatchEvent(new Event('input',{ bubbles:true }));
  return `已填入 ${baud}，請確認後解碼；估計值取最短脈寬，請確認`;
}) };

export default {
  name:'uart', label:'UART', order:2, base:'tx', diff:{ tx_n:'tx',rx_n:'rx' },
  roles:[{ key:'tx',label:'TX',allowEmpty:true },{ key:'rx',label:'RX',optional:true },
    { key:'tx_n',label:'TX−（B 線，可省）',optional:true },{ key:'rx_n',label:'RX−（B 線，可省）',optional:true }],
  options:[{ key:'baud',label:'鮑率（必填）',type:'text',value:'115200',action:estimate,
    list:[9600,19200,38400,57600,115200,230400,460800,921600,1000000],
    parse:s => { const n = Number(s); if (!s.trim() || !Number.isFinite(n) || n <= 0) throw Error('鮑率須為有限正數'); return n; } },
  { key:'bits',label:'資料位',type:'select',value:8,choices:[5,6,7,8,9].map(n => [n,String(n)]) },
  { key:'parity',label:'同位',type:'select',value:'N',choices:[['N','N（無）'],['E','E（偶）'],['O','O（奇）'],['M','M（固定 1）'],['S','S（固定 0）']] },
  { key:'stop',label:'停止位',type:'select',value:1,choices:[[1,'1'],[2,'2']] },
  { key:'invert',label:'反相（RS-232 勾反相）',type:'check',value:false }],
  reasons, kinds, eventKind:f => kinds[f.kind] ?? f.kind, content, fieldText,
  columns:[{ head:'字元數',cell:f => f.fields.filter(x => x.kind === 'tx' || x.kind === 'rx').length }],
  lanes:s => s.channels.tx && s.channels.rx ? ['tx','rx'] : null,
  laneLabels:{ tx:'TX',rx:'RX' }, addresses:null, reportSummary:true,
  summary:(s,opts) => {
    const o = { baud:115200,bits:8,parity:'N',stop:1,invert:false,...opts };
    return `UART ${o.baud} ${o.bits}${o.parity}${o.stop}${o.invert ? ' 反相' : ''} · 門檻 `+
      ['tx','rx'].filter(k => s.channels[k]).map(k => `${k.toUpperCase()} ${s.thresholds[k]?.map(v => fmt(v,'V',3)).join(' / ') ?? '—'}`).join('；');
  },
  sample:{ frames,addresses:[] },
};
