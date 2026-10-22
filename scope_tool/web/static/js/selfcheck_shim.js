// 瀏覽器版 node:assert 替身（selfcheck.html 的 import map 指向此檔）。
const fail = (m) => { throw new Error(m); };
const eq = (a, b) => a === b || (Number.isNaN(a) && Number.isNaN(b));
const deep = (a, b) => {
  if (eq(a, b)) return true;
  if (!a || !b || typeof a !== "object" || typeof b !== "object") return false;
  if (ArrayBuffer.isView(a) !== ArrayBuffer.isView(b)) return false;
  const ka = Object.keys(a), kb = Object.keys(b);
  return ka.length === kb.length && ka.every((k) => deep(a[k], b[k]));
};
const msg = (m, d) => (m instanceof Error ? m.message : m ?? d);
const assert = (v, m) => { if (!v) fail(msg(m, "assert 失敗")); };
assert.ok = assert;
assert.equal = (a, b, m) => { if (!eq(a, b)) fail(msg(m, `equal：${String(a)} !== ${String(b)}`)); };
assert.notEqual = (a, b, m) => { if (eq(a, b)) fail(msg(m, `notEqual：${String(a)}`)); };
assert.deepEqual = (a, b, m) => { if (!deep(a, b)) fail(msg(m, `deepEqual：${JSON.stringify(a)} vs ${JSON.stringify(b)}`)); };
assert.match = (s, re, m) => { if (!re.test(s)) fail(msg(m, `match：${s} !~ ${re}`)); };
assert.fail = (m) => fail(msg(m, "fail"));
const test = (e, x) => !x || (x instanceof RegExp ? x.test(String(e?.message ?? e)) : x.prototype ? e instanceof x : typeof x === "function" ? x(e) : true);
assert.throws = (f, x, m) => {
  try { f(); } catch (e) { if (test(e, x)) return; fail(`throws：錯誤不符 ${e?.message}`); }
  fail(msg(m, "預期丟出錯誤"));
};
assert.rejects = async (p, x, m) => {
  try { await (typeof p === "function" ? p() : p); } catch (e) { if (test(e, x)) return; fail(`rejects：錯誤不符 ${e?.message}`); }
  fail(msg(m, "預期 reject"));
};
export default assert;
