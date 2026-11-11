// eSPI 單線模式，待實機驗證。
const reasons = { crc_cmd:'命令 CRC 錯誤',crc_resp:'回應 CRC 錯誤',unknown_opcode:'未知命令',no_response:'無回應',defer:'延後',fatal:'致命錯誤',reserved_bit:'保留位元非零',truncated:'擷取截斷',incomplete:'資料不完整',unknown_bit:'未知位元' };
const kinds = { cmd:'命令',reset:'重設',partial:'不完整' };
const fieldText = x => x.value == null ? x.label : x.value.toString(16).toUpperCase().padStart(Math.ceil(x.nbits/4),'0');
const content = f => f.label || f.fields.map(fieldText).join(' ') || kinds[f.kind];
const sampleFrame = (i,value) => ({ i,t0:i*20,t1:i*20+10,kind:'cmd',start:null,addr:null,rw:null,ack:null,ccc:null,ccc_name:null,label:'GET_STATUS',status:'ok',reasons:[],fields:[{t0:i*20+1,t1:i*20+8,kind:'opcode',addr:null,value,nbits:8,ninth:null,ninth_kind:null,ok:true,label:''}] });
export default {
  name:'espi',label:'eSPI',order:6,base:'clk',diff:{},
  roles:[{key:'cs',label:'CS'},{key:'clk',label:'CLK'},{key:'io0',label:'IO0'},{key:'io1',label:'IO1'},{key:'io2',label:'IO2',optional:true},{key:'io3',label:'IO3',optional:true}],
  options:[{key:'io_mode',label:'I/O 模式',type:'select',value:'single',choices:[['single','單線']]},{key:'crc',label:'檢查 CRC',type:'check',value:true}],
  reasons,kinds,eventKind:f => kinds[f.kind] ?? f.kind,content,fieldText,
  columns:[{head:'欄位數',cell:f => f.fields.length}],lanes:() => null,addresses:null,reportSummary:true,
  summary:(s,o) => `eSPI 單線 · CRC ${o.crc === false ? '不檢查' : '檢查'} · 尚未以實機驗證`,
  sample:{frames:[sampleFrame(0,0x25),sampleFrame(1,0x21)],addresses:[]},
};
