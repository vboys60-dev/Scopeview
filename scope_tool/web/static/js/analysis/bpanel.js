// B 區：欄位／分頁偏好；只存版面，不寫游標或分析結果。
export const STORAGE_KEY = 'scope.analysis.results.v1';
export const COLUMNS = ['current','mean','min','max','range','std','count'];
export const DEFAULT_COLUMNS = ['current','mean','min','max','std'];
export const TABS = ['measure','cursor','marker','peaks'];
const defaults = () => ({ version:1, columns:[...DEFAULT_COLUMNS], tab:'measure' });
export function validate(raw) {
  if (raw?.version !== 1) return defaults();
  return { version:1, columns:Array.isArray(raw.columns) ? COLUMNS.filter(k => raw.columns.includes(k)) : [...DEFAULT_COLUMNS],
    tab:TABS.includes(raw.tab) ? raw.tab : 'measure' };
}
let memory = defaults();
export function load(storage = () => globalThis.localStorage) {
  try { const raw = storage().getItem(STORAGE_KEY); if (raw) memory = validate(JSON.parse(raw)); } catch { /* 記憶體備援 */ }
  return { ...memory, columns:[...memory.columns] };
}
export function save(prefs, storage = () => globalThis.localStorage) {
  memory = validate(prefs);
  try { storage().setItem(STORAGE_KEY,JSON.stringify(memory)); } catch { /* 私密模式仍可切換 */ }
}
export const PAIR_MIN_WIDTH = 1200;
export const useTabs = (width, height) => width < 820 || height < 150;
export function panelVisible(panel, tab, tabbed) {
  if (tab === 'marker' || tab === 'cursor') return panel === tab || (!tabbed && ['cursor','marker'].includes(panel));
  return panel === tab || (!tabbed && tab === 'measure' && panel === 'cursor');
}
export function mountTabs(host, panels, { initial = load(), persist = save, actions } = {}) {
  let prefs = validate(initial), tabbed = true, pairTabbed = true, collapsed = false;
  const tabs = document.createElement('div'); tabs.className = 'analysis__resultTabs'; tabs.setAttribute('role','tablist');
  const buttons = {};
  for (const [key,label] of [['measure','量測'],['cursor','游標'],['marker','Marker'],['peaks','FFT 峰值']]) {
    const b = document.createElement('button'); b.type = 'button'; b.className = 'btn btn--small';
    b.dataset.resultTab = key; b.setAttribute('role','tab'); b.textContent = label; b.title = label;
    if (!panels[key]) continue;
    panels[key].id = `analysis-panel-${key}`; panels[key].setAttribute('role','tabpanel');
    b.id = `analysis-tab-${key}`; b.setAttribute('aria-controls',panels[key].id);
    panels[key].setAttribute('aria-labelledby',b.id);
    b.onclick = () => { prefs = { ...load(), tab:key }; persist(prefs); render(); };
    tabs.append(b); buttons[key] = b;
  }
  // 控件事件不可觸發 splitter 的拖曳、雙擊重設或 Enter 收折。
  for (const name of ['pointerdown','dblclick','keydown']) tabs.addEventListener(name,e => e.stopPropagation());
  host.append(tabs);
  function render() {
    const effectiveTabbed = panels.marker && ['marker','cursor'].includes(prefs.tab) ? pairTabbed : tabbed;
    const single = effectiveTabbed || (!panels.marker && prefs.tab === 'cursor');
    const visible = key => !panels.marker && prefs.tab === 'cursor' ? key === 'cursor' : panelVisible(key,prefs.tab,effectiveTabbed);
    tabs.hidden = collapsed;
    tabs.setAttribute('aria-multiselectable',String(!single));
    if (actions) actions.hidden = collapsed || !panelVisible('measure',prefs.tab,tabbed);
    for (const key of TABS) {
      if (!buttons[key]) continue;
      buttons[key].setAttribute('aria-selected',String(visible(key)));
      panels[key].hidden = !visible(key);
    }
    panels.measure.parentNode.dataset.resultTabbed = String(single);
    panels.measure.parentNode.dataset.markerPaired = String(!!panels.marker && !effectiveTabbed && ['cursor','marker'].includes(prefs.tab));
  }
  return { update({ width, height, count = 0, fftOn = false, lowerCollapsed = false }) {
    tabbed = useTabs(width,height); pairTabbed = width < PAIR_MIN_WIDTH || height < 150; collapsed = lowerCollapsed;
    buttons.peaks.textContent = `FFT 峰值${fftOn && count ? ` (${count})` : ''}`;
    render();
  }, get tab() { return prefs.tab; } };
}
