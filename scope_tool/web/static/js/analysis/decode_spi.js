// SPI 模式、字組與雙線標註。
const reasons = { incomplete:'字組不完整',truncated:'擷取截斷',clk_phase:'時脈相位未確認',unknown_bit:'未知位元',no_cs:'無 CS，對齊未驗證' };
const kinds = { txn:'交易' };
const fieldText = x => x.value == null ? x.label : x.value.toString(16).toUpperCase().padStart(Math.ceil(x.nbits/4),'0');
function content(f) {
  return ['mosi','miso'].map(k => {
    const xs = f.fields.filter(x => x.kind === k);
    return xs.length ? `${k.toUpperCase()} ${xs.map(fieldText).join(' ')}` : '';
  }).filter(Boolean).join('／') || f.label || '交易';
}
const field = (kind,value,t0) => ({ t0,t1:t0+7,kind,addr:null,value,nbits:8,ninth:null,ninth_kind:null,ok:true,label:'' });
const sampleFrame = (i,value) => ({ i,t0:i*20,t1:i*20+10,kind:'txn',start:null,addr:null,rw:null,ack:null,ccc:null,ccc_name:null,label:'',status:'ok',reasons:[],fields:[field('mosi',value,i*20+1)] });
export default {
  name:'spi',label:'SPI',order:3,base:'sclk',diff:{},
  roles:[{ key:'sclk',label:'SCLK' },{ key:'mosi',label:'MOSI',optional:true },{ key:'miso',label:'MISO',optional:true },{ key:'cs',label:'CS',optional:true }],
  options:[{ key:'mode',label:'模式',type:'select',value:0,choices:[0,1,2,3].map(n => [n,`Mode ${n}`]) },
    { key:'bits',label:'字長',type:'text',value:'8',parse:s => { const n=Number(s); if (!/^\d+$/.test(s.trim()) || n<4 || n>32) throw Error('字長須為 4 至 32 的整數'); return n; } },
    { key:'lsb',label:'LSB 先',type:'check',value:false },
    { key:'cs_active',label:'CS 極性',type:'select',value:'low',choices:[['low','低有效'],['high','高有效']] },
    { key:'idle',label:'無 CS 閒置時間（秒）',type:'text',value:'',parse:s => { if (!s.trim() || s.trim() === 'null') return null; const n=Number(s); if (!Number.isFinite(n) || n<=0) throw Error('閒置時間須為有限正數'); return n; } }],
  reasons,kinds,eventKind:f => kinds[f.kind] ?? f.kind,content,fieldText,
  columns:[{ head:'字組數',cell:f => Math.max(...['mosi','miso'].map(k => f.fields.filter(x => x.kind === k).length)) }],
  // ponytail: 雙線時不顯示逐 bit；需要時 bits 改存兩線。
  lanes:s => s.channels.mosi && s.channels.miso ? ['mosi','miso'] : null,
  laneLabels:{ mosi:'MOSI',miso:'MISO' },addresses:null,reportSummary:true,
  summary:(s,opts) => { const o={ mode:0,bits:8,lsb:false,cs_active:'low',...opts }; return `SPI Mode ${o.mode} · ${o.bits} bit ${o.lsb ? 'LSB' : 'MSB'} · ${s.channels.cs ? `CS ${o.cs_active === 'low' ? '低' : '高'}有效` : '無 CS'}`; },
  sample:{ frames:[sampleFrame(0,0x96),sampleFrame(1,0x55)],addresses:[] },
};
