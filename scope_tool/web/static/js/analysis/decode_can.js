// Classical CAN 的設定與顯示。
const reasons = { stuff:'位元填充錯誤',crc:'CRC 錯誤',form:'格式錯誤',no_ack:'未應答',
  timing:'時序偏差',truncated:'資料不完整',error_flag:'錯誤旗標',fd_unsupported:'尚不支援 CAN FD',unknown_bit:'未知位元' };
const kinds = { data:'資料',remote:'遠端請求',error_flag:'錯誤旗標',fd:'CAN FD',partial:'不完整區段' };
const hex = (v,n) => v == null ? '—' : v.toString(16).toUpperCase().padStart(n,'0');
const fieldText = x => x.kind === 'ack' ? (x.value === 0 ? 'ACK' : 'NO ACK') :
  x.value == null ? x.label : x.kind === 'data' ? hex(x.value,2) : x.label || hex(x.value,1);
const content = f => {
  const data = f.fields.filter(x => x.kind === 'data').map(x => hex(x.value,2));
  const crc = f.fields.find(x => x.kind === 'crc');
  return [...data,...(crc ? [crc.ok ? 'CRC✓' : 'CRC✗'] : [])].join(' ') || f.label || kinds[f.kind];
};
const field = (kind,value,nbits,ok = true) => ({ t0:1,t1:kind === 'ack' ? 1 : 2,kind,addr:null,value,nbits,
  ninth:null,ninth_kind:null,ok,label:'' });
const frames = [{ i:0,t0:0,t1:10,kind:'data',start:null,addr:0x123,rw:null,ack:true,ccc:null,ccc_name:null,
  label:'STD 0x123 DLC 2',status:'ok',reasons:[],fields:[field('id',0x123,11),field('dlc',2,4),
    field('data',0x12,8),field('data',0x34,8),field('crc',0x36b7,15),field('ack',0,1)] }];
export default {
  name:'can',label:'CAN',order:4,base:'can',diff:{ canl:'can' },
  roles:[{ key:'can',label:'CANH／差動／RXD' },{ key:'canl',label:'CANL',optional:true }],
  options:[{ key:'bitrate',label:'位元率（bit/s）',type:'text',value:'500000',list:[125000,250000,500000,1000000],
    parse:s => { const n=Number(s); if (!s.trim() || !Number.isFinite(n) || n<=0) throw Error('位元率須為有限正數'); return n; } },
  { key:'sample_point',label:'取樣點（%）',type:'text',value:'75',
    parse:s => { const n=Number(s); if (!s.trim() || !Number.isFinite(n) || n<50 || n>95) throw Error('取樣點須介於 50–95'); return n; } },
  { key:'dominant_high',label:'顯性電壓',type:'select',value:true,choices:[[true,'高電壓＝顯性'],[false,'低電壓＝顯性']] }],
  reasons,kinds,eventKind:f => kinds[f.kind] ?? f.kind,content,fieldText,
  columns:[{ head:'ID',cell:f => f.addr == null ? '—' : '0x'+hex(f.addr,f.fields.find(x => x.kind === 'id')?.nbits === 29 ? 8 : 3) },
    { head:'DLC',cell:f => f.fields.find(x => x.kind === 'dlc')?.value ?? '—' }],
  lanes:() => null,laneLabels:{},addresses:null,reportSummary:true,
  summary:(s,opts) => `CAN ${(opts?.bitrate ?? 500000)/1000} kbit/s · 取樣點 ${opts?.sample_point ?? 75}%`,
  sample:{ frames,addresses:[] },
};
