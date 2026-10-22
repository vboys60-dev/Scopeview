// L0 自檢共用工具：契約載入、型別檢查（依 api_contract.json types 的字串語法）、依契約呼叫。
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

export const rd = (p) => readFileSync(new URL(p, import.meta.url), "utf8");
export const contract = JSON.parse(rd("../api_contract.json"));
const T = contract.types;
export const near = (a, b, e = 1e-9) => assert.ok(Math.abs(a - b) <= e, `${a} ≠ ${b}`);
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
export const rej = async (p, code) => { try { await p; } catch (e) { assert.equal(e.code, code, `${e.code}：${e.message}`); return e; } assert.fail(`應以 ${code} 失敗`); };

/** 型別檢查：依契約 types 的字串語法驗證值。 */
export function tc(v, t, p = "$") {
  t = t.trim();
  if (t.endsWith("|null")) return v === null ? undefined : tc(v, t.slice(0, -5), p);
  if (t.endsWith("[]")) { assert.ok(Array.isArray(v), `${p} 應為陣列`); return v.forEach((x, i) => tc(x, t.slice(0, -2), `${p}[${i}]`)); }
  if (t.startsWith("map<")) { assert.ok(v && typeof v === "object", p); return Object.entries(v).forEach(([k, x]) => tc(x, t.slice(4, -1), `${p}.${k}`)); }
  if (t.startsWith("[")) { const parts = t.slice(1, -1).split(","); assert.ok(Array.isArray(v) && v.length === parts.length, `${p} tuple`); return parts.forEach((q, i) => tc(v[i], q, `${p}[${i}]`)); }
  const basic = { str: (x) => typeof x === "string", int: Number.isInteger, float: (x) => typeof x === "number" && Number.isFinite(x), bool: (x) => typeof x === "boolean",
    object: (x) => x && typeof x === "object" && !Array.isArray(x), any: () => true, null: (x) => x === null };
  if (basic[t]) return assert.ok(basic[t](v), `${p} 應為 ${t}，實際 ${JSON.stringify(v)}`);
  assert.ok(T[t] !== undefined, `${p} 未知型別 ${t}`);
  if (typeof T[t] === "string") return tc(v, T[t], p);
  assert.ok(basic.object(v), `${p} 應為 ${t}`);
  assert.deepEqual(Object.keys(v).sort(), Object.keys(T[t]).sort(), `${p}（${t}）欄位`);
  for (const [k, ft] of Object.entries(T[t])) tc(v[k], ft, `${p}.${k}`);
}
/** 依契約呼叫並檢查：參數鍵齊全、參數型別、回傳型別。 */
export async function call(b, m, params) {
  const sp = contract.methods[m];
  assert.deepEqual(Object.keys(params).sort(), sp.params.map((x) => x.name).sort(), `${m} 參數鍵`);
  sp.params.forEach((x) => tc(params[x.name], x.nullable ? `${x.type}|null` : x.type, `${m}.${x.name}`));
  const r = await (sp.job ? b.job(m, params) : b.call(m, params));
  tc(r, sp.returns, `${m}→`);
  return r;
}

