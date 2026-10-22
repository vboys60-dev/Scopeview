// L3 自檢：node scope_tool/web/static/js/l3_check.mjs
import assert from "node:assert/strict";
import { makeBridge } from "./bridge.js";
import { createMock } from "./mock_backend.js";
import { estimateBytes, riskOf, elapsedText, validate, doneText, busyText, fmtBytes, retryBusy } from "./tab_capture.js";

assert.equal(estimateBytes(100e6, 4), 6.4e9);
assert.equal(riskOf(10000, 2), null);
assert.equal(riskOf(150e6, 1).level, "warn");
assert.equal(riskOf(100e6, 4).level, "danger");
assert.equal(riskOf(99e6, 4).level, "warn"); // 6.34 GB 未達 6.4 GB
assert.equal(fmtBytes(6.4e9), "6.4 GB"); assert.equal(fmtBytes(160000), "1 MB");
assert.equal(elapsedText(0), "擷取中… 已 0 秒"); assert.equal(elapsedText(12.9), "擷取中… 已 12 秒");
const ok = { connected: true, channels: ["CHAN1"], maxPoints: 1000, points: 500, dir: "/x" };
assert.equal(validate(ok), null);
assert.match(validate({ ...ok, connected: false }), /連線/);
assert.match(validate({ ...ok, channels: [] }), /通道/);
assert.match(validate({ ...ok, points: 1001 }), /最多/);
assert.match(validate({ ...ok, points: 1.5 }), /整數/);
assert.match(validate({ ...ok, dir: "" }), /資料夾/);
assert.match(doneText({ path: "/a.h5", got_points: 5, requested: 10 }), /只有 5 點/);
assert.equal(doneText({ path: "/a.h5", got_points: 10, requested: 10 }), "已存檔：/a.h5");

// mock 後端：info → capture；BUSY
const mock = createMock({ delay: 5 }), b = makeBridge(mock, true);
await b.call("connect_fake", {});
const info = await b.job("capture_info", {});
assert.deepEqual(info.channels, ["CHAN1", "CHAN2"]);
const r = await b.job("capture", { directory: "/mock", name: "w", channels: info.channels, points: 1000, retrigger: false });
assert.equal(r.path, "/mock/w.h5");
await assert.rejects(b.job("capture", { directory: "/mock", name: "w", channels: ["CHAN1"], points: info.max_points + 1, retrigger: false }), /上限/);
mock.setBusy(true);
const e = await b.job("capture_info", {}).catch((x) => x);
assert.equal(e.code, "BUSY"); assert.match(busyText(e), /忙碌/);
// BUSY 後重試成功／用盡次數
{
  let n = 0, waits = 0;
  const v = await retryBusy(async () => { if (++n < 3) throw Object.assign(new Error("忙"), { code: "BUSY" }); return "ok"; }, { delayMs: 1, onWait: () => waits++ });
  assert.equal(v, "ok"); assert.equal(waits, 2);
  await assert.rejects(retryBusy(async () => { throw Object.assign(new Error("忙"), { code: "BUSY" }); }, { tries: 2, delayMs: 1 }), (x) => x.code === "BUSY");
  let m = 0;
  await assert.rejects(retryBusy(async () => { m++; throw Object.assign(new Error("x"), { code: "SCOPE_ERROR" }); }, { delayMs: 1 }));
  assert.equal(m, 1);
}
console.log("l3 self-check OK");
