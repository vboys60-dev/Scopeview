// 多檔比對：槽位更新不寫 file，保留量測、游標與檢視歷史。
import { channelRecord } from './toolbar.js';
import { rangeOf, dxOf } from './measure.js';

/** 被替換的來源有參與解碼時，沿用解碼面板的過期標記。 */
export function staleDecode(st, names) {
  const old = st.decodeResult;
  return old && Object.values(old.summary?.channels ?? {}).some(n => names.includes(n))
    ? { decodeResult: { ...old, stale: true } } : {};
}

/** SlotSummary → 單次更新；同名通道只保留五個顯示設定。 */
export function slotPatch(st, slot, summary, colors, scales) {
  if (!st.file || (summary && summary.gen !== st.file.gen)) return null;
  const old = (st.slots ?? []).find(s => s.slot === slot), names = old?.channels ?? [];
  const slots = (st.slots ?? []).filter(s => s.slot !== slot);
  const channels = st.channels.filter(c => !names.includes(c.name));
  if (summary) {
    slots.push({ slot, path: summary.path, info: summary.info, all: summary.all,
      channels: summary.channels.map(c => c.name), infos: summary.channels });
    for (const info of summary.channels) {
      const record = channelRecord(info, channels.length, colors, scales), prev = st.channels.find(c => c.name === info.name);
      if (prev) for (const key of ['color', 'visible', 'scale', 'position', 'time_offset', 'labelBg', ...(old?.path === summary.path ? ['alias'] : [])]) record[key] = prev[key];
      channels.push(record);
    }
  }
  return { slots, dataRev: (st.dataRev ?? 0) + 1, channels,
    selected: channels.some(c => c.name === st.selected) ? st.selected : st.file.channels[0]?.name ?? null,
    ...staleDecode(st, names) };
}

const h = (tag, text) => { const e = document.createElement(tag); if (text !== undefined) e.textContent = text; return e; };
const filename = path => path.split(/[\\/]/).pop();

/** 對話框與檔案資訊共用的比對限制。 */
export const SLOT_LIMITS = Object.freeze([
  '各檔以自己的觸發點為時間 0；可用「對齊主檔」一鍵調整整槽 dx。',
  '游標吸附主檔第一通道；「完整時間」以主檔範圍為準。',
  '解碼的通道需來自同一檔（時間軸相同）。',
  'FFT 一次只算一個來源。',
  '數學二元運算用原始時間對齊，不含 dx。',
  '波形 CSV 只匯出主檔通道。',
  '開新檔或關閉會清空所有比對槽位。',
]);

export function appendSlotLimits(body) {
  const section = h('section'); section.dataset.slotLimits = '';
  section.append(h('h3', '比對限制'));
  for (const text of SLOT_LIMITS) section.append(h('div', `・${text}`));
  body.append(section);
}

/** 主檔在前，比對槽按 Mem1～Mem4 排列；所有檔案資訊以文字節點呈現。 */
export function appendFileInfo(body, st) {
  const table = (rows, slot) => {
    const t = h('table'); t.className = 'table'; t.dataset.fileInfo = slot;
    for (const [key, value] of rows) {
      const row = h('tr'); row.append(h('td', key), h('td', value)); t.append(row);
    }
    body.append(t);
  };
  table(st.file.info, 'main');
  const slots = [...(st.slots ?? [])].sort((a, b) => a.slot.localeCompare(b.slot));
  for (const s of slots) { body.append(h('h3', s.slot)); table(s.info, s.slot); }
  if (slots.length) appendSlotLimits(body);
}

// 不寫入 store 狀態；同 gen 的數學通道更新、移除與重加都不重複提示。
const notifiedGen = new WeakMap();

/** 選檔立即載入；勾選需套用，全不勾明確移除。原生選檔手感待真人驗證。 */
export async function openSlots(ctx, modal) {
  const { store, bridge, ui, scales } = ctx, initial = store.get().file;
  if (!initial) return;
  const colors = ctx.appState?.catalog?.channel_colors ?? ['#F0E442'];
  await modal('多檔比對', body => {
    const table = h('table'), head = h('tr'), rows = new Map();
    table.className = 'table'; table.dataset.slots = '';
    for (const name of ['槽位', '檔案', '通道', '']) head.append(h('th', name));
    table.append(head);
    body.append(h('p', `主檔：${filename(initial.path)}（${initial.channels.map(c => c.name).join(', ')}）— 不佔槽位`), table);
    let busy = false;
    const dialog = () => body.closest('dialog');
    const button = (text, action) => { const b = h('button', text); b.className = 'btn'; b.type = 'button'; b.onclick = action; return b; };
    function render(only = null) {
      for (const [slot, row] of rows) {
        const s = (store.get().slots ?? []).find(s => s.slot === slot);
        row.remove.disabled = !s;
        if (only && only !== slot) continue;
        row.path.textContent = s ? filename(s.path) : '（空）';
        row.checks.replaceChildren();
        for (const name of s?.all ?? []) {
          const label = h('label', name), check = h('input'); check.type = 'checkbox'; check.value = name; label.className = 'check';
          label.style.marginRight = 'var(--sp-2)';
          check.checked = s.channels.includes(`${slot}.${name}`); label.prepend(check); row.checks.append(label);
        }
        if (!s) row.checks.textContent = '—';
      }
    }
    async function change(slot, path = null, channels = []) {
      const gen = store.get().file?.gen;
      if (gen !== initial.gen) return;
      let summary = null;
      if (path) summary = await bridge.job('add_waveform', { path, slot, channels });
      else await bridge.call('remove_slot', { slot });
      const st = store.get();
      if (st.file?.gen !== gen || (summary && summary.gen !== gen)) return;
      const patch = slotPatch(st, slot, summary, colors, scales);
      if (patch) {
        store.set(patch, 'program');
        if (summary && notifiedGen.get(store) !== gen) {
          notifiedGen.set(store, gen);
          ui.toast(`已載入 ${slot}：各檔以自己的觸發點為 0，對齊請調 dx`);
        }
      }
    }
    async function run(slot, action) {
      if (busy) return;
      busy = true;
      dialog().querySelectorAll('button,input').forEach(b => { b.disabled = true; });
      if (slot) rows.get(slot).path.textContent = '載入中…';
      try { await action(); }
      catch (e) { showError(e); }
      finally {
        busy = false;
        dialog().querySelectorAll('button,input').forEach(b => { b.disabled = false; });
        render(slot);
      }
    }
    function showError(e) {
      if (e.code !== 'STALE') ui.showError(e, '比對檔載入失敗');
    }
    for (let i = 1; i <= 4; i++) {
      const slot = `Mem${i}`, tr = h('tr'), file = h('td'), path = h('span'), checks = h('td'), actions = h('td');
      tr.dataset.slot = slot;
      const pick = button('選檔…', () => run(slot, async () => {
        const selected = await ui.pickPath(ctx, 'file', (store.get().slots ?? []).find(s => s.slot === slot)?.path ?? null);
        if (selected) await change(slot, selected);
      }));
      const remove = button('移除', () => run(slot, () => change(slot)));
      file.append(pick, path); actions.append(remove); tr.append(h('td', slot), file, checks, actions); table.append(tr);
      rows.set(slot, { path, checks, remove });
    }
    body.append(h('p', '選檔後立即載入全部通道；改勾選後按「套用勾選」才生效；全不勾＝移除該槽。'));
    appendSlotLimits(body);
    const apply = button('套用勾選', () => {
      const changes = [];
      for (const [slot, row] of rows) {
        const s = (store.get().slots ?? []).find(s => s.slot === slot);
        if (!s) continue;
        const chosen = [...row.checks.querySelectorAll('input:checked')].map(c => c.value);
        if (chosen.map(n => `${slot}.${n}`).join() !== s.channels.join()) changes.push({ slot, path: s.path, chosen });
      }
      return run(null, async () => {
        for (const { slot, path, chosen } of changes) {
          rows.get(slot).path.textContent = '載入中…';
          try { await change(slot, chosen.length ? path : null, chosen); }
          catch (e) { showError(e); }
        }
      });
    });
    apply.className = 'btn btn--primary';
    // modal 的關閉鈕保留；套用不關窗，方便連續換檔與檢查勾選。
    queueMicrotask(() => {
      const d = dialog(); d.style.maxWidth = 'min(1100px, 95vw)';
      d.querySelector('.dlg__actions').append(apply);
      d.addEventListener('cancel', e => { if (busy) { e.preventDefault(); e.stopImmediatePropagation(); } }, true);
    });
    render();
  }, null);
}

/** 用目前量測範圍的第一個上升緣對齊整個比對槽。 */
export async function alignSlot({ store, bridge, ui }, name) {
  const st = store.get(), slot = (st.slots ?? []).find(s => s.channels.includes(name));
  const main = st.file?.channels.find(c => c.name === name.slice(name.indexOf('.') + 1)) ?? st.file?.channels[0];
  if (!slot || !main) { ui.toast('無法對齊：找不到主檔或比對通道'); return; }
  const signature = s => JSON.stringify([s.file?.gen, s.dataRev, rangeOf(s), s.threshold, dxOf(s.channels)]);
  const sig = signature(st);
  try {
    const r = await bridge.job('measure', { entries: [{ channel: main.name, channel2: name, name: 'Delta Time',
      rising: true, rising2: true, edge_num: 1, edge_num2: 1, edge_level: 'middle', edge_level2: 'middle' }],
      range: rangeOf(st), dx: dxOf(st.channels), threshold: st.threshold });
    const row = r.results?.[0], delta = row?.stats?.current;
    if (signature(store.get()) !== sig || r.gen !== st.file.gen) throw new Error('資料或量測設定已變更，請重新對齊');
    if (!row?.ok || !Number.isFinite(delta)) throw new Error(row?.reason || '量測沒有有效結果');
    const channels = store.get().channels.filter(c => slot.channels.includes(c.name))
      .map(c => ({ name: c.name, time_offset: (c.time_offset ?? 0) - delta }));
    store.command('view.historyGroup', { key: 'align', continuous: true });
    try { store.command('view.zoomRect', { channels }); } finally { store.command('view.historyGroup', { end: true }); }
  } catch (e) { ui.toast(`無法對齊：${e?.message || e?.reason || '量測失敗'}`); }
}
