// B 區解碼設定、事件表與位址表；與主圖標註列共用解碼模型。
import { fmt, parseSI } from '../fmt.js';
import { decodeModel, parseAddresses, reasonText, selectFrame } from './decode.js';
export const MAX_ROWS = 2000;
export const hex = (v, width = 2) => v == null ? '—' : '0x'+v.toString(16).toUpperCase().padStart(width,'0');
export const eventKind = f => ({ private_write:'私有寫', private_read:'私有讀', ccc_broadcast:'CCC 廣播', ccc_direct:'CCC 直接',
  daa:'DAA 指派', ibi:'IBI', hotjoin:'Hot-Join', i2c:f.rw ? 'I2C 讀' : 'I2C 寫', hdr:'HDR 區段', hdr_exit:'HDR Exit',
  target_reset:'Target Reset', pattern:'形狀', partial:'不完整區段', error:'錯誤' })[f.kind] ?? f.kind;
export function frameContent(f) {
  return [f.ccc_name, ...f.fields.filter(x => x.kind !== 'addr').map(x =>
    (x.ok ? '' : '⚠')+(x.value == null ? x.label : hex(x.value,Math.ceil((x.nbits-(x.ninth_kind ? 1 : 0))/4)))+(x.kind === 'pid' ? ' PID' : ''))].filter(Boolean).join(' ') || f.label;
}
export function tableFrames(frames, onlyProblems) {
  // ponytail: 不做虛擬捲動；篩選後最多繪製 2000 列，CSV 由後端輸出全部。
  const filtered = onlyProblems ? frames.filter(f => f.status === 'error' || f.status === 'warn') : frames;
  return { rows:filtered.slice(0,MAX_ROWS), total:filtered.length };
}
const node = (tag, cls, text) => {
  const e = document.createElement(tag); e.className = cls ?? ''; if (tag === 'button') e.type = 'button'; if (text != null) e.textContent = text; return e;
};
function table(head) {
  const t = node('table','table table--num results__table'), h = node('thead'), tr = node('tr'), body = node('tbody');
  for (const title of head) tr.append(node('th','',title));
  h.append(tr); t.append(h,body); return { el:t, body };
}
function cells(row, values) { for (const value of values) row.append(node('td','',value)); }
export function mount(el, ctx) {
  const { store } = ctx, model = decodeModel(ctx), root = node('div','decode');
  const bar = node('div','decode__bar'), sum = node('div','decode__sum'), info = node('span','decode__info');
  const filter = node('div','decode__segment'), all = node('button','btn btn--small','全部'), problems = node('button','btn btn--small','只錯誤／警告');
  let onlyProblems = false, auto = true, fileGen, rendered = null, previousFilter;
  const sources = {}, thresholds = {};
  function label(text, input) { const l = node('label','decode__control',text); l.append(input); bar.append(l); return input; }
  for (const role of ['scl','sda']) sources[role] = label(role.toUpperCase(),node('select','input'));
  const mode = node('div','decode__segment'); mode.setAttribute('aria-label','門檻');
  const autoBtn = node('button','btn btn--small','自動'), manualBtn = node('button','btn btn--small','手動');
  mode.append(autoBtn,manualBtn); label('門檻',mode);
  for (const role of ['scl','sda']) {
    thresholds[role] = ['lo','hi'].map(name => {
      const input = node('input','input decode__threshold'); input.type = 'text'; input.placeholder = name;
      input.setAttribute('aria-label',`${role.toUpperCase()} ${name}`); input.title = `${name}（V，可用 SI 前綴）`;
      return label(name === 'lo' ? role.toUpperCase() : '',input);
    });
  }
  const addresses = label('I2C 位址',node('input','input decode__addresses')); addresses.placeholder = '50, 51';
  const run = node('button','btn btn--small btn--primary','解碼'), exp = node('button','btn btn--small','匯出 CSV');
  run.dataset.decodeAction = 'run'; exp.dataset.decodeAction = 'export'; bar.append(run,exp);
  const band = node('input'); band.type = 'checkbox'; label('標註列',band).parentNode.classList.add('decode__band');
  const wrap = node('div','decode__tablewrap'), events = table(['#','時間','類型','位址','R/W','內容','狀態']); wrap.append(events.el);
  const foot = node('div','decode__foot');
  const details = node('details','decode__addressesTable'), caption = node('summary');
  const addr = table(['DA','PID','BCR','DCR','起','迄','來源','備註']); details.append(caption,addr.el);
  filter.append(all,problems); sum.append(info,filter); root.append(bar,sum,wrap,foot,details); el.append(root);
  function readSettings() {
    model.change({ scl:sources.scl.value, sda:sources.sda.value, band:band.checked,
      thr:Object.fromEntries(['scl','sda'].map(k => [k,auto ? null : thresholds[k].map(e => parseSI(e.value))])) });
    try { const i2c = parseAddresses(addresses.value); addresses.setCustomValidity(''); model.change({ i2c }); }
    catch (e) { addresses.setCustomValidity(e.message); }
  }
  for (const input of [...Object.values(sources),...Object.values(thresholds).flat(),addresses]) input.addEventListener('input',readSettings);
  band.addEventListener('change',() => model.change({ band:band.checked }));
  autoBtn.onclick = () => { auto = true; readSettings(); };
  manualBtn.onclick = () => { auto = false; readSettings(); };
  run.onclick = () => { if (addresses.reportValidity()) model.run(); };
  exp.onclick = () => model.exportCsv();
  all.onclick = () => { onlyProblems = false; render(); };
  problems.onclick = () => { onlyProblems = true; render(); };
  function render() {
    const st = store.get(), r = st.decodeResult, p = model.config;
    if (fileGen !== st.file?.gen || !sources.scl.children.length) {
      fileGen = st.file?.gen; auto = true;
      for (const role of ['scl','sda']) {
        sources[role].replaceChildren(...st.channels.filter(c => !c.derived).map(c => { const o = node('option','',c.name); o.value = c.name; return o; }));
        sources[role].value = p[role];
        thresholds[role].forEach(e => { e.value = ''; });
      }
      addresses.value = ''; addresses.setCustomValidity('');
    }
    band.checked = p.band;
    autoBtn.setAttribute('aria-pressed',String(auto)); manualBtn.setAttribute('aria-pressed',String(!auto));
    all.setAttribute('aria-pressed',String(!onlyProblems)); problems.setAttribute('aria-pressed',String(onlyProblems));
    for (const role of ['scl','sda']) thresholds[role].forEach((e,i) => {
      e.disabled = auto;
      if (auto) e.value = r?.summary.thresholds[role] ? fmt(r.summary.thresholds[role][i],'V',3) : '';
    });
    run.disabled = !st.file || model.busy || st.channels.filter(c => !c.derived).length < 2;
    exp.disabled = !r || r.stale || model.busy;
    root.classList.toggle('decode--stale',!!r?.stale);
    info.replaceChildren();
    if (model.busy) info.textContent = '解碼中…（量測／FFT 會等候）';
    else if (model.message) info.textContent = model.message;
    else if (r) {
      const c = r.summary.counts;
      info.append(node('b','',`${c.frames} 筆`),node('span','decode__error',`錯誤 ${c.errors}`),node('span','decode__warn',`警告 ${c.warns}`));
      if (r.stale) info.append(node('span','decode__stale','設定已變更，請重新解碼'));
      const ts = ['scl','sda'].map(k => `${k.toUpperCase()} ${r.summary.thresholds[k]?.map(v => fmt(v,'V',3)).join(' / ') ?? '—'}`).join('；');
      info.append(node('span','',`I3C Basic SDR · 門檻 ${ts}`));
      if (r.summary.truncated) info.append(node('span','decode__warn','事件達上限，結果已截斷'));
      for (const w of r.summary.warnings) info.append(node('span','decode__warn',w));
    } else info.textContent = st.file ? '尚未解碼' : '請先開啟波形檔';
    ctx.resultTabs?.label('decode',`解碼${r ? ` (${r.summary.counts.frames})` : ''}`);
    if (rendered !== r || previousFilter !== onlyProblems) {
      rendered = r; previousFilter = onlyProblems;
      const { rows, total } = tableFrames(r?.frames ?? [],onlyProblems);
      const dx = st.channels.find(c => c.name === r?.scl)?.time_offset ?? 0;
      events.body.replaceChildren(...rows.map(f => {
        const row = node('tr'), content = frameContent(f); row.tabIndex = 0; row.dataset.decodeFrame = String(f.i);
        cells(row,[f.i+1,fmt(f.t0+dx,'s'),eventKind(f),hex(f.addr),f.rw == null ? '—' : f.rw ? 'R' : 'W',content.length > 64 ? content.slice(0,64)+'…' : content,
          f.reasons.length ? f.reasons.map(reasonText).join('、') : f.kind === 'hdr' ? '資訊' : '正常']);
        row.children[5].title = content; row.children[6].className = 'decode__'+(f.status === 'ok' && f.kind === 'hdr' ? 'infoStatus' : f.status);
        row.onclick = () => selectFrame(store,f);
        row.onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); row.onclick(); } };
        return row;
      }));
      foot.textContent = (total > MAX_ROWS ? '僅顯示前 2000 筆，匯出 CSV 含全部。' : '')+'點列跳到波形；Enter 也可以。';
      caption.textContent = `位址表（${r?.addresses.length ?? 0}）`;
      addr.body.replaceChildren(...(r?.addresses ?? []).slice(0,256).map(a => {
        const row = node('tr'); cells(row,[hex(a.da),hex(a.pid,12),hex(a.bcr),hex(a.dcr),a.t_from == null ? '未知（擷取前）' : fmt(a.t_from+dx,'s'),
          a.t_to == null ? '—' : fmt(a.t_to+dx,'s'),a.how === 'observed' ? '觀察到（未確認）' : a.how,a.note ?? '']); return row;
      }));
    }
    for (const row of events.body.children) row.classList.toggle('is-selected',+row.dataset.decodeFrame === st.decodeSel);
  }
  // dx 改變只刷新時間，不使既有解碼過期。
  store.on(['channels'],() => { rendered = null; render(); });
  store.on(['decodeSel'],() => {
    const row = [...events.body.children].find(e => +e.dataset.decodeFrame === store.get().decodeSel);
    row?.scrollIntoView?.({ block:'nearest',inline:'nearest' });
  });
  store.on(['decodeResult','decodeSel','file'],render); model.on(render); render();
  return { model, render };
}
