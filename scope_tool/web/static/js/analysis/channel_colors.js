// 通道顏色偏好按完整名稱區分主檔、Mem 槽位與數學通道；儲存失敗仍可即時換色。
const validColor = value => typeof value === 'string' && /^#[0-9a-f]{6}$/i.test(value);
const keyOf = name => `scopeChanColor:${name}`;

/** 保留建立當下的契約預設色，重設不受其他通道增刪影響。 */
export function channelColors(name, defaultColor) {
  let color = defaultColor;
  try {
    const saved = localStorage.getItem(keyOf(name));
    if (validColor(saved)) color = saved;
  } catch {}
  return { color, defaultColor };
}

/** 原生選色器的 input／change 共用入口；先存偏好再通知畫面。 */
export function setChannelColor(store, name, color) {
  if (!validColor(color) || !store.get().channels.some(c => c.name === name)) return;
  try { localStorage.setItem(keyOf(name), color); } catch {}
  store.updateChannel(name, { color }, 'user');
}

export function resetChannelColor(store, name) {
  const c = store.get().channels.find(c => c.name === name);
  if (!c || !validColor(c.defaultColor)) return;
  try { localStorage.removeItem(keyOf(name)); } catch {}
  store.updateChannel(name, { color: c.defaultColor }, 'user');
}
