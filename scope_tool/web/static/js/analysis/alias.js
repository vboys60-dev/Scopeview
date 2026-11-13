// L5：通道別名（純顯示欄位）。`name` 永不改；別名只經 chanbar.js 寫入 `channel.alias`。
const key = (s) => String(s).toLowerCase();
const others = (channels, name) => channels.filter((c) => c.name !== name);

/** 輸入 → 要寫入的 alias：trim；空或等於自己原名＝清除（""）。 */
export const aliasValue = (name, text) => { const t = String(text ?? "").trim(); return t === name ? "" : t; };

/** 驗證別名；通過回 null，否則回錯誤訊息。上限 24 字元（以 code point 計），不分大小寫不可與他通道原名或別名相同。 */
export function aliasError(channels, name, text) {
  const t = aliasValue(name, text);
  if (!t) return null;
  if ([...t].length > 24) return "別名最多 24 個字";
  const k = key(t);
  return others(channels, name).some((c) => key(c.name) === k || (c.alias && key(c.alias) === k)) ? "別名與其他通道的名稱重複" : null;
}

/** 顯示名：無別名＝原名；有別名＝別名，但與他通道原名或顯示名相同時顯示「別名（原名）」。 */
export function chLabel(channels, name) {
  const c = channels.find((x) => x.name === name), d = c?.alias || name;
  if (!c?.alias) return name;
  const k = key(d);
  return others(channels, name).some((o) => key(o.name) === k || key(o.alias || o.name) === k) ? `${d}（${name}）` : d;
}

/** 整組對照：Map(原名 → 顯示名)。 */
export const labelsOf = (channels) => new Map(channels.map((c) => [c.name, chLabel(channels, c.name)]));

/** 報告用對照表；只列有別名者，沒有則回 null。 */
export function aliasRows(channels) {
  const rows = channels.filter((c) => c.alias).map((c) => [c.alias, c.name]);
  return rows.length ? { head: ["別名", "原名"], rows } : null;
}
