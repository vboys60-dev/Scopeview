// 無框架驗證：alias.js 純函式（測試 13–14）。其餘別名測試由各套用檔的 alias_*_check.mjs 負責。
import assert from "node:assert/strict";
import { aliasValue, aliasError, chLabel, labelsOf, aliasRows } from "./alias.js";
const ch = (name, alias) => ({ name, ...(alias === undefined ? {} : { alias }) });
const cs = [ch("CH1"), ch("CH2", "SDA"), ch("CH3")];
// 13
assert.equal(aliasValue("CH1", "  CH1 "), ""); assert.equal(aliasValue("CH1", "  x "), "x");
assert.equal(aliasError(cs, "CH1", ""), null); assert.equal(aliasError(cs, "CH1", "CH1"), null);
assert.equal(aliasError(cs, "CH1", "a".repeat(24)), null); assert.ok(aliasError(cs, "CH1", "a".repeat(25)));
assert.equal(aliasError(cs, "CH1", "電".repeat(24)), null); assert.ok(aliasError(cs, "CH1", "電".repeat(25)));
assert.equal(aliasError(cs, "CH1", "😀".repeat(24)), null); assert.ok(aliasError(cs, "CH1", "😀".repeat(25)));
assert.ok(aliasError(cs, "CH1", "ch2")); assert.ok(aliasError(cs, "CH1", "sda")); assert.ok(aliasError(cs, "CH1", " SDA "));
assert.equal(aliasError(cs, "CH2", "sda"), null, "改自己的別名大小寫不算撞名");
assert.equal(aliasError(cs, "CH2", "CH2"), null, "等於自己原名＝清除");
// 14
assert.equal(chLabel(cs, "CH1"), "CH1"); assert.equal(chLabel(cs, "CH2"), "SDA");
const cs2 = [...cs, ch("sda")];
assert.equal(chLabel(cs2, "CH2"), "SDA（CH2）"); assert.equal(chLabel(cs2, "sda"), "sda");
assert.equal(chLabel(cs, "不存在"), "不存在");
assert.deepEqual([...labelsOf(cs2)], [["CH1", "CH1"], ["CH2", "SDA（CH2）"], ["CH3", "CH3"], ["sda", "sda"]]);
assert.equal(aliasRows([ch("CH1")]), null);
assert.deepEqual(aliasRows(cs), { head: ["別名", "原名"], rows: [["SDA", "CH2"]] });
console.log("alias_check OK");
