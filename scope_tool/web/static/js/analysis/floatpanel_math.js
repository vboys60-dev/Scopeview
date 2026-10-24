// L4：浮動面板純尺寸／偏好邏輯，不依賴 DOM，不寫分析狀態。
export const STORAGE_KEY = 'scope.analysis.float.v1';
export const defaults = () => ({ version:1, floating:false, x:80, y:120, width:960, height:300 });
const finite = (n) => typeof n === 'number' && Number.isFinite(n);
const clip = (n,a,b) => Math.max(a,Math.min(b,n));
export const canFloat = (width) => finite(width) && width >= 900;
export function validatePrefs(raw) {
  const p = defaults();
  if (!raw || raw.version !== 1) return p;
  if (typeof raw.floating === 'boolean') p.floating = raw.floating;
  for (const k of ['x','y','width','height']) if (finite(raw[k])) p[k] = clip(raw[k],k === 'width' || k === 'height' ? 0 : -100000,100000);
  p.width = Math.max(360,p.width); p.height = Math.max(160,p.height);
  return p;
}
/** 全框夾入分析頁區域；極矮視窗仍以可視尺寸優先，標題最多保留 28px。 */
export function clampRect(raw, W, H, top = 0) {
  const p = validatePrefs({ ...raw, version:1 });
  W = finite(W) ? Math.max(0,W) : 0; H = finite(H) ? Math.max(0,H) : 0;
  top = finite(top) ? clip(top,0,H) : 0;
  const width = Math.min(W,p.width), height = Math.min(H-top,p.height);
  return { x:clip(p.x,0,Math.max(0,W-width)), y:clip(p.y,top,Math.max(top,H-height)), width, height };
}
export function keyboardRect(rect, event, W, H, top = 0) {
  const delta = { ArrowLeft:[-1,0], ArrowRight:[1,0], ArrowUp:[0,-1], ArrowDown:[0,1] }[event.key];
  if (!delta || event.ctrlKey || event.metaKey) return null;
  const [dx,dy] = delta.map(n => n*(event.shiftKey ? 50 : 10));
  return clampRect(event.altKey ? { ...rect,width:rect.width+dx,height:rect.height+dy } : { ...rect,x:rect.x+dx,y:rect.y+dy },W,H,top);
}
export function resizeRect(rect, edge, dx, dy, W, H, top = 0) {
  let { x,y,width,height } = rect;
  if (edge.includes('e')) width = clip(width+dx,360,Math.max(360,W-x));
  if (edge.includes('s')) height = clip(height+dy,160,Math.max(160,H-y));
  if (edge.includes('w')) { const right=x+width; x=clip(x+dx,0,Math.max(0,right-360)); width=right-x; }
  if (edge.includes('n')) { const bottom=y+height; y=clip(y+dy,top,Math.max(top,bottom-160)); height=bottom-y; }
  return clampRect({x,y,width,height},W,H,top);
}
let memory = defaults();
export function loadPrefs(storage = () => globalThis.localStorage) {
  try { const raw=storage().getItem(STORAGE_KEY); if (raw) memory=validatePrefs(JSON.parse(raw)); } catch { /* 記憶體備援 */ }
  return { ...memory };
}
export function savePrefs(prefs, storage = () => globalThis.localStorage) {
  memory=validatePrefs(prefs);
  try { storage().setItem(STORAGE_KEY,JSON.stringify(memory)); } catch { /* 私密模式仍可使用 */ }
}
