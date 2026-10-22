// 分析頁共享狀態。各模組只透過 store 與 bridge 溝通，不互相 import 內部函式。
// origin ∈ user／snap／program：snap 為游標吸附回寫，監聽者遇 snap 不得再觸發吸附。
//
// 【不可原地修改】state 內的巢狀物件（view、cursors、channels 的每筆記錄、rfPos…）一律視為不可變：
// 要改就建新物件再 set／updateChannel。set 只對「plain object」做一層淺比較（同值新物件不通知），
// 原地修改會讓比較誤判為沒變而漏通知。
//
// 通道記錄：{name, unit, derived, color, visible, scale, position, vmin, vmax, time_offset}
//   time_offset（dx，秒）是顯示時間位移的唯一真值；寫入者只有 chanbar／L5，經 updateChannel。
export const ORIGINS = ["user", "snap", "program"];

const isPlain = (o) => o !== null && typeof o === "object" && Object.getPrototypeOf(o) === Object.prototype;
/** 相同：Object.is，或兩邊都是 plain object 且鍵集合相同、各值 Object.is 相等（只比一層）。 */
export function same(a, b) {
  if (Object.is(a, b)) return true;
  if (!isPlain(a) || !isPlain(b)) return false;
  const ka = Object.keys(a);
  return ka.length === Object.keys(b).length && ka.every((k) => k in b && Object.is(a[k], b[k]));
}

export function createStore() {
  const state = {
    file: null, channels: [], selected: null, // selected 為通道名稱
    view: { t0: 0, t1: 1 }, cursors: { x1: null, x2: null, y1: null, y2: null },
    rangeMode: "all", // 量測／CSV 範圍：all｜cursors
    markerMode: null, // null＝傳統游標；否則 catalog.marker_modes 之一
    rfPos: null, // {x, y} Track RF 全精度位置（Hz）
    threshold: "10/50/90 %", fftResult: null, measurements: [],
  };
  const subs = new Set(), cmds = new Map();

  /** 淺比較後套用；只有真的變動才通知。回傳變動的鍵。 */
  function set(patch, origin = "program") {
    if (!ORIGINS.includes(origin)) throw new Error(`未知 origin：${origin}`);
    const keys = Object.keys(patch).filter((k) => !same(state[k], patch[k]));
    keys.forEach((k) => { state[k] = patch[k]; });
    if (keys.length) for (const s of [...subs]) if (!s.keys || keys.some((k) => s.keys.includes(k))) s.fn(state, keys, origin);
    return keys;
  }
  /** on(fn) 或 on(["view","cursors"], fn)；回傳取消函式。fn(state, 變動鍵, origin)。 */
  function on(a, b) {
    const s = typeof a === "function" ? { keys: null, fn: a } : { keys: a, fn: b };
    subs.add(s);
    return () => subs.delete(s);
  }

  /** 換整組通道；選取依名稱保留，被刪就選原位置附近的。channels 與 selected 在同一次 set 通知。 */
  function setChannels(list, origin = "program") {
    const old = state.selected, oldIdx = state.channels.findIndex((c) => c.name === old);
    const names = list.map((c) => c.name);
    const selected = !names.length ? null : names.includes(old) ? old : names[Math.min(Math.max(oldIdx, 0), names.length - 1)];
    set({ channels: [...list], selected }, origin);
  }
  function updateChannel(name, patch, origin = "program") {
    if (!state.channels.some((c) => c.name === name)) return;
    set({ channels: state.channels.map((c) => (c.name === name ? { ...c, ...patch } : c)) }, origin);
  }
  function removeChannel(name, origin = "program") {
    setChannels(state.channels.filter((c) => c.name !== name), origin);
  }

  /** 指令：fire-and-forget 的意圖（例如 "view.reset"、"viewport.intent"）。 */
  function command(name, payload) { for (const fn of [...(cmds.get(name) ?? [])]) fn(payload); }
  function onCommand(name, fn) {
    if (!cmds.has(name)) cmds.set(name, new Set());
    cmds.get(name).add(fn);
    return () => cmds.get(name).delete(fn);
  }
  return { state, get: () => state, set, on, setChannels, updateChannel, removeChannel, command, onCommand };
}

export const store = createStore();
