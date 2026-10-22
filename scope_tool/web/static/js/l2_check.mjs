// L2 自檢：node --experimental-default-type=module scope_tool/web/static/js/l2_check.mjs
// 以 mock 後端驗證連線列／截圖頁的純邏輯（BUSY、UNSUPPORTED 重試、計時文案），不需 DOM。
import assert from "node:assert/strict";
import { makeBridge } from "./bridge.js";
import { createMock } from "./mock_backend.js";
import { createConn } from "./connbar.js";
import { createShot, elapsedText } from "./tab_screenshot.js";

const mk = (opts) => { const m = createMock({ delay: 2, ...opts }); return { m, b: makeBridge(m, true) }; };
const ui = () => { const u = { errors: [], alerts: [] }; u.showError = async (e, t) => u.errors.push([e.message, t]); u.alert = async (m) => u.alerts.push(m); u.prompt = async () => "10.0.0.5"; return u; };

// 文案
assert.equal(elapsedText(0), "擷取中… 已 0 秒"); assert.equal(elapsedText(7), "擷取中… 已 7 秒");

// 連線列：搜尋 → 連線 → 斷線
{
  const { b } = mk(), u = ui(), c = createConn({ bridge: b, ui: u, view: { render() {}, chooseSeries: async () => null } });
  b.on("driver", c.onDriver);
  await c.search(); assert.equal(c.state.found.length, 1); assert.equal(c.state.selected, "MOCK::INSTR"); assert.equal(c.state.text, "找到 1 台");
  await c.toggle(); assert.ok(c.state.connected && c.state.text.startsWith("已連線")); assert.equal(c.state.pending, null);
  await c.toggle(); assert.ok(!c.state.connected); assert.equal(c.state.text, "未連線");
  await c.manual(); assert.equal(c.state.selected, "TCPIP0::10.0.0.5::hislip0::INSTR");
  await c.toggleFake(); assert.equal(c.state.model, "FAKE-SCOPE");
  assert.equal(u.errors.length, 0);
}

// 手動 IP：後端回整份清單，連加兩個要選到各自剛加的那筆
{
  const list = [], bridge = { on() {}, call: async (_, { ip }) => (list.push({ resource: `TCPIP0::${ip}::inst0::INSTR`, source: "manual", label: ip }), [...list]) };
  const ips = ["10.0.0.5", "10.0.0.6"]; const u = ui(); let i = 0; u.prompt = async () => ips[i++];
  const c = createConn({ bridge, ui: u, view: { render() {}, chooseSeries: async () => null } });
  await c.manual(); assert.equal(c.state.selected, "TCPIP0::10.0.0.5::inst0::INSTR");
  await c.manual(); assert.equal(c.state.selected, "TCPIP0::10.0.0.6::inst0::INSTR"); assert.equal(c.state.found.length, 2);
}

// 連著真機按模擬：不得斷線，只提示
{
  const { b } = mk(), u = ui(), c = createConn({ bridge: b, ui: u, config: { last_resource: "MOCK::INSTR" }, view: { render() {}, chooseSeries: async () => null } });
  b.on("driver", c.onDriver);
  await c.connect(); assert.equal(c.state.model, "DSO-X 3014G");
  await c.toggleFake(); assert.ok(c.state.connected); assert.equal(c.state.model, "DSO-X 3014G"); assert.deepEqual(u.alerts, ["目前連著真機，請先斷線再使用模擬儀器。"]);
  await c.disconnect(); await c.toggleFake(); assert.equal(c.state.model, "FAKE-SCOPE"); await c.toggleFake(); assert.ok(!c.state.connected);
}

// BUSY：固定文案，且不卡死（pending 會清掉）
{
  const { m, b } = mk(), u = ui(), c = createConn({ bridge: b, ui: u, view: { render() {}, chooseSeries: async () => null } });
  m.setBusy(true);
  await c.search();
  assert.deepEqual(u.errors[0], ["儀器忙碌中，請等目前操作完成", "搜尋失敗"]); assert.equal(c.state.pending, null);
  m.setBusy(false); await c.search(); assert.equal(c.state.found.length, 1);
}

// UNSUPPORTED：手選系列後重送；取消則不連線
{
  const { b } = mk(), u = ui(); let asked = 0;
  const c = createConn({ bridge: b, ui: u, config: { last_resource: "MOCK::UNKNOWN" }, view: { render() {}, chooseSeries: async (list) => { asked++; return list[1]; } } });
  b.on("driver", c.onDriver);
  await c.connect();
  assert.equal(asked, 1); assert.ok(c.state.connected); assert.equal(u.errors.length, 0);
  const b2 = mk().b, c2 = createConn({ bridge: b2, ui: u, config: { last_resource: "MOCK::UNKNOWN" }, view: { render() {}, chooseSeries: async () => null } });
  await c2.connect(); assert.ok(!c2.state.connected); assert.equal(c2.state.text, "連線已取消"); assert.equal(u.errors.length, 0);
}

// REMOTE_DESKTOP：掛警示並彈專用標題
{
  const u = ui(), e = Object.assign(new Error("請關閉遠端桌面連線後重試"), { code: "REMOTE_DESKTOP" });
  const bridge = { job: async () => { throw e; }, call: async () => { throw e; }, on() {} };
  const c = createConn({ bridge, ui: u, config: { last_resource: "X" }, view: { render() {}, chooseSeries: async () => null } });
  await c.connect(); assert.equal(c.state.warn, e.message); assert.equal(u.errors[0][1], "遠端桌面連線中");
}

// 截圖：未連線擋下、計時、BUSY、成功
{
  const { m, b } = mk({ delay: 30 }), u = ui(); const ticks = []; let tickFn, cleared = 0, previews = [];
  const timer = { set: (f) => { tickFn = f; return 1; }, clear: () => cleared++ };
  const s = createShot({ bridge: b, ui: u, timer, view: { render: (st) => ticks.push(st.text), setPreview: (x) => previews.push(x) }, config: { screenshot_dir: "/tmp/x" } });
  await s.start(); assert.deepEqual(u.alerts, ["請先連線儀器。"]);
  await b.call("connect_fake", {}); s.setConnected(true);
  const p = s.start(); tickFn(); tickFn(); tickFn();
  assert.ok(s.state.running); assert.equal(s.state.text, "擷取中… 已 3 秒"); assert.ok(!ticks.some((t) => /%/.test(t)));
  await p; assert.ok(!s.state.running); assert.equal(cleared, 1); assert.match(s.state.text, /^已存檔：\/tmp\/x\/scope\.png$/); assert.equal(previews.length, 1); assert.equal(s.state.count, 1);
  m.setBusy(true); await s.start();
  assert.deepEqual(u.errors.at(-1), ["儀器忙碌中，請等目前操作完成", "存圖失敗"]); assert.equal(s.state.text, "存圖失敗"); assert.ok(!s.state.running);
  s.set({ dir: "  " }); await s.start(); assert.equal(u.alerts.at(-1), "請先選擇存檔目錄。");
}
console.log("l2 self-check OK");
