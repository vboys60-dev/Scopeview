// USB PD 單線解碼與顯示。
const reasons = { crc:'CRC 錯誤',invalid_5b:'無效 5b 碼',bad_eop:'EOP 錯誤',bad_sop:'SOP 錯誤',
  sampler:'判位失敗',preamble:'前導碼不足',reserved:'保留值',truncated:'擷取截斷' };
const kinds = { control:'控制訊息',data:'資料訊息',extended:'延伸訊息',hard_reset:'硬重設',cable_reset:'線纜重設',partial:'不完整' };
const fieldText = x => x.value == null ? x.label : x.value.toString(16).toUpperCase().padStart(Math.ceil(x.nbits/5), '0');
const content = f => f.label || kinds[f.kind] || f.kind;
const sampleFrame = (i,label,kind) => ({ i,t0:i*20,t1:i*20+10,kind,start:null,addr:null,rw:null,ack:null,
  ccc:null,ccc_name:null,label,status:'ok',reasons:[],fields:[] });
export default {
  name:'usbpd',label:'USB PD',order:7,base:'cc',diff:{},
  roles:[{ key:'cc',label:'CC' }],
  options:[{ key:'bitrate',label:'位元率（空白＝前導碼量測）',type:'text',value:'',parse:s => {
    if (!s.trim() || s.trim() === 'null') return null; const n=Number(s);
    if (!Number.isFinite(n) || n <= 0) throw Error('位元率須為有限正數'); return n;
  } }],
  reasons,kinds,eventKind:f => kinds[f.kind] ?? f.kind,content,fieldText,
  columns:[{ head:'資料物件數',cell:f => f.fields.filter(x => x.kind === 'obj').length }],
  lanes:() => null,laneLabels:{},addresses:null,reportSummary:true,
  summary:(s,opts) => `USB PD · ${opts.bitrate ? `${opts.bitrate} bit/s` : '前導碼量測位元率'} · CC ${s.channels.cc}`,
  sample:{ frames:[sampleFrame(0,'SOP GoodCRC','control'),sampleFrame(1,'SOP Source_Capabilities','data')],addresses:[] },
};
