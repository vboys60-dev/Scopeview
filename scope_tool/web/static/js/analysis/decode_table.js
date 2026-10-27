// B 區解碼設定、事件表與位址表；與主圖標註列共用解碼模型。
import { fmt, parseSI } from '../fmt.js';
import { decodeModel, definition, selectFrame } from './decode.js';
export const MAX_ROWS = 2000;
export { hex, eventKind, frameContent } from './decode_i3c.js';
import * as protocols from './decode_protocols.js';
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
  let sources = {}, thresholds = {}, options = {}, active, eventProtocol;
  const protocol = node('select','input decode__protocol'); protocol.dataset.protocol = 'true';
  for (const def of Object.values(protocols).sort((a,b) => a.order-b.order)) { const o = node('option','',def.label); o.value = def.name; protocol.append(o); }
  label('協定',protocol);
  protocol.onchange = () => { model.change({ protocol:protocol.value }); };
  function label(text, input) { const l = node('label','decode__control',text); l.append(input); bar.append(l); return input; }
  const form = node('span','decode__form'); bar.append(form);
  const params = node('div','decode__params');
  const run = node('button','btn btn--small btn--primary','解碼'), exp = node('button','btn btn--small','匯出 CSV');
  run.dataset.decodeAction = 'run'; exp.dataset.decodeAction = 'export'; params.append(run,exp);
  const band = node('input'); band.type = 'checkbox'; const bandLabel = node('label','decode__control decode__band','標註列'); bandLabel.append(band); params.append(bandLabel); bar.append(params);
  const wrap = node('div','decode__tablewrap'); let events = table([]); wrap.append(events.el);
  const foot = node('div','decode__foot');
  const details = node('details','decode__addressesTable'), caption = node('summary');
  let addr = table([]); details.append(caption,addr.el);
  filter.append(all,problems); sum.append(info,filter); root.append(bar,sum,wrap,foot,details); el.append(root);
  function build(def, p, st) {
    sources = {}; thresholds = {}; options = {}; form.replaceChildren(); params.replaceChildren();
    const add = (parent,text,input) => { const l = node('label','decode__control',text); l.append(input); parent.append(l); return input; };
    for (const role of def.roles) {
      const select = node('select','input'); select.dataset.role = role.key;
      if (role.optional) { const o = node('option','','—不使用—'); o.value = ''; select.append(o); }
      for (const c of st.channels.filter(c => !c.derived)) { const o = node('option','',c.name); o.value = c.name; select.append(o); }
      sources[role.key] = add(form,role.label,select); select.value = p.ch[role.key]; select.oninput = readSettings;
    }
    auto = Object.values(p.thr).every(v => v === null);
    const mode = node('div','decode__segment'); mode.setAttribute('aria-label','門檻'); mode.append(autoBtn,manualBtn); add(form,'門檻',mode);
    for (const role of def.roles.filter(r => !def.diff?.[r.key])) {
      thresholds[role.key] = ['lo','hi'].map((name,i) => {
        const input = node('input','input decode__threshold'); input.type = 'text'; input.placeholder = name; input.dataset.line = role.key;
        input.setAttribute('aria-label',`${role.label} ${name}`); input.title = `${name}（V，可用 SI 前綴）`;
        input.value = p.thr[role.key]?.[i] ?? ''; input.oninput = readSettings;
        return add(form,name === 'lo' ? role.label : '',input);
      });
    }
    for (const o of def.options) {
      const input = node(o.type === 'select' ? 'select' : 'input','input'+(o.key === 'i2c_addrs' ? ' decode__addresses' : ''));
      input.dataset.option = o.key;
      if (o.type === 'select') for (const [value,text] of o.choices) { const choice = node('option','',text); choice.value = String(value); input.append(choice); }
      else input.type = o.type === 'check' ? 'checkbox' : 'text';
      input.placeholder = o.placeholder ?? ''; input.value = Array.isArray(p.opt[o.key]) ? p.opt[o.key].map(v => v.toString(16)).join(', ') : String(p.opt[o.key]);
      input.checked = !!p.opt[o.key]; input.oninput = readSettings;
      if (o.list) { const list = node('datalist'); list.id = `decode-${def.name}-${o.key}`; input.setAttribute('list',list.id); for (const v of o.list) { const e = node('option'); e.value = String(v); list.append(e); } params.append(list); }
      options[o.key] = add(params,o.label,input);
    }
    params.append(run,exp,bandLabel);
    eventProtocol = null; rendered = null;
  }
  const autoBtn = node('button','btn btn--small','自動'), manualBtn = node('button','btn btn--small','手動');
  function readSettings() {
    const p = model.config, def = definition(p.protocol), opt = { ...p.opt };
    for (const o of def.options) {
      const input = options[o.key];
      try { opt[o.key] = o.parse ? o.parse(input.value) : o.type === 'check' ? input.checked : o.type === 'select' ? o.choices.find(([v]) => String(v) === input.value)[0] : input.value; input.setCustomValidity(''); }
      catch (e) { input.setCustomValidity(e.message); }
    }
    model.change({ ch:Object.fromEntries(Object.entries(sources).map(([k,v]) => [k,v.value])),opt,band:band.checked,
      thr:Object.fromEntries(Object.entries(thresholds).map(([k,v]) => [k,auto ? null : v.map(e => parseSI(e.value))])) });
  }
  band.addEventListener('change',() => model.change({ band:band.checked }));
  autoBtn.onclick = () => { auto = true; readSettings(); };
  manualBtn.onclick = () => { auto = false; readSettings(); };
  run.onclick = () => { if (Object.values(options).every(e => e.reportValidity())) model.run(); };
  exp.onclick = () => model.exportCsv();
  all.onclick = () => { onlyProblems = false; render(); };
  problems.onclick = () => { onlyProblems = true; render(); };
  function render() {
    const st = store.get(), r = st.decodeResult, p = model.config;
    const def = definition(r?.protocol ?? p.protocol), formDef = definition(p.protocol);
    if (fileGen !== st.file?.gen || active !== p.protocol) {
      fileGen = st.file?.gen; active = p.protocol; protocol.value = p.protocol; build(formDef,p,st);
    }
    if (eventProtocol !== def.name) {
      eventProtocol = def.name; rendered = null;
      events = table(['#','時間','類型',...def.columns.map(c => c.head),'內容','狀態']); wrap.replaceChildren(events.el);
      addr = table(def.addresses?.head ?? []); details.replaceChildren(caption,addr.el); details.hidden = !def.addresses;
    }
    band.checked = p.band;
    autoBtn.setAttribute('aria-pressed',String(auto)); manualBtn.setAttribute('aria-pressed',String(!auto));
    all.setAttribute('aria-pressed',String(!onlyProblems)); problems.setAttribute('aria-pressed',String(onlyProblems));
    for (const role of Object.keys(thresholds)) thresholds[role].forEach((e,i) => {
      e.disabled = auto;
      if (auto) e.value = r?.summary.thresholds[role] ? fmt(r.summary.thresholds[role][i],'V',3) : '';
    });
    run.disabled = !st.file || model.busy || formDef.roles.some(r => !r.optional && !p.ch[r.key]);
    exp.disabled = !r || r.stale || model.busy;
    root.classList.toggle('decode--stale',!!r?.stale);
    info.replaceChildren();
    if (model.busy) info.textContent = '解碼中…（量測／FFT 會等候）';
    else if (model.message) info.textContent = model.message;
    else if (r) {
      const c = r.summary.counts;
      info.append(node('b','',`${c.frames} 筆`),node('span','decode__error',`錯誤 ${c.errors}`),node('span','decode__warn',`警告 ${c.warns}`));
      if (r.stale) info.append(node('span','decode__stale','設定已變更，請重新解碼'));
      info.append(node('span','',def.summary(r.summary,r.options)));
      if (r.summary.truncated) info.append(node('span','decode__warn','事件達上限，結果已截斷'));
      for (const w of r.summary.warnings) info.append(node('span','decode__warn',w));
    } else info.textContent = st.file ? '尚未解碼' : '請先開啟波形檔';
    ctx.resultTabs?.label('decode',`解碼${r ? ` (${r.summary.counts.frames})` : ''}`);
    if (rendered !== r || previousFilter !== onlyProblems) {
      rendered = r; previousFilter = onlyProblems;
      const { rows, total } = tableFrames(r?.frames ?? [],onlyProblems);
      const dx = st.channels.find(c => c.name === r?.base)?.time_offset ?? 0;
      events.body.replaceChildren(...rows.map(f => {
        const row = node('tr'), content = def.content(f); row.tabIndex = 0; row.dataset.decodeFrame = String(f.i);
        cells(row,[f.i+1,fmt(f.t0+dx,'s'),def.eventKind?.(f) ?? def.kinds[f.kind] ?? f.kind,...def.columns.map(c => c.cell(f)),content.length > 64 ? content.slice(0,64)+'…' : content,
          f.reasons.length ? f.reasons.map(k => def.reasons[k] ?? k).join('、') : f.kind === 'hdr' ? '資訊' : '正常']);
        row.children[3+def.columns.length].title = content; row.children[4+def.columns.length].className = 'decode__'+(f.status === 'ok' && f.kind === 'hdr' ? 'infoStatus' : f.status);
        row.onclick = () => selectFrame(store,f);
        row.onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); row.onclick(); } };
        return row;
      }));
      foot.textContent = (total > MAX_ROWS ? '僅顯示前 2000 筆，匯出 CSV 含全部。' : '')+'點列跳到波形；Enter 也可以。';
      caption.textContent = `位址表（${r?.addresses.length ?? 0}）`;
      addr.body.replaceChildren(...(r?.addresses ?? []).slice(0,256).map(a => {
        const row = node('tr'); cells(row,def.addresses.row(a,fmt,dx)); return row;
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
