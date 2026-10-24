// 依序執行全部 JS 自檢（每支各開子行程：l0 結尾會 process.exit）。
// 用法：node scope_tool/web/static/js/selfcheck_node.js
const { spawnSync } = require("node:child_process");
const path = require("node:path");

const FILES = ["l0_check.mjs", "l2_check.mjs", "l3_check.mjs", "analysis/l4_check.mjs", "analysis/l5_check.mjs", "analysis/p1_check.mjs", "analysis/p2_check.mjs", "analysis/p2b_check.mjs", "analysis/p2b2_check.mjs", "analysis/p2b3_check.mjs", "analysis/p3_check.mjs", "analysis/p3b_check.mjs"];
for (const f of FILES) {
  const r = spawnSync(process.execPath, [path.join(__dirname, f), ...process.argv.slice(2)], { encoding: "utf8" });
  process.stdout.write(r.stdout);
  if (r.status !== 0) {
    process.stderr.write(`${f} 失敗（exit ${r.status}）\n${r.stderr}`);
    process.exit(1);
  }
}
// 直接匯入產品使用的純函式，避免自檢另寫一份邏輯。
const checks = spawnSync(process.execPath, ["--input-type=module", "-e", `
  import assert from "node:assert/strict";
  import { timeTickLabels } from ${JSON.stringify(require("node:url").pathToFileURL(path.join(__dirname, "analysis/plotcore.js")).href)};
  import { wheelFactor } from ${JSON.stringify(require("node:url").pathToFileURL(path.join(__dirname, "analysis/plotcore.js")).href)};
  const labels = timeTickLabels(196.0023e-6, 196.2023e-6);
  assert.equal(labels.length, 11);
  assert.equal(new Set(labels).size, 11);
  assert.ok(labels.every(s => s.endsWith(" µs")));
  const cross = timeTickLabels(-1e-6, 1e-6 + 2e-22);
  assert.ok(cross.includes("0 s"));
  assert.ok(cross.every(s => !s.includes("ps")));
  console.log("timeTickLabels self-check OK: " + labels.join(" | "));
  console.log("cross-zero: " + cross.join(" | "));
  const nearZero = timeTickLabels(-4.999999999e-4, 5e-4);
  assert.equal(nearZero[5], "0 s");
  console.log("near-zero: " + nearZero.join(" | "));
  for (const center of [0.5, 1]) {
    const fine = timeTickLabels(center - 5e-10, center + 5e-10);
    assert.equal(new Set(fine).size, 11);
    assert.equal(fine[5], center + " s");
    assert.equal(fine[6], "+100 ps");
    assert.equal(fine[4], "-100 ps");
    assert.ok(fine[4].startsWith("-") && fine[6].startsWith("+"));
    console.log("100 ps/div: " + fine.join(" | "));
  }
  for (const ctrlKey of [false, true]) {
    for (const deltaY of [-120, 120]) {
      const big = wheelFactor({ deltaY, ctrlKey });
      const small = wheelFactor({ deltaY: deltaY / 12, ctrlKey }) ** 12;
      assert.ok(Math.abs(big - small) < 1e-12);
    }
  }
  assert.equal(wheelFactor({ deltaY: 0, ctrlKey: true }), 1);
  assert.equal(wheelFactor({ deltaY: 3, deltaMode: 1 }), wheelFactor({ deltaY: 48 }));
  assert.equal(wheelFactor({ deltaY: 1, deltaMode: 2 }, 300), wheelFactor({ deltaY: 300 }));
  assert.ok(wheelFactor({ deltaY: -10, ctrlKey: true }) < wheelFactor({ deltaY: -10 }));
  assert.equal(wheelFactor({ deltaY: 1e6 }), 2);
  assert.equal(wheelFactor({ deltaY: -1e6 }), 0.5);
  console.log("wheelFactor self-check OK: big=" + wheelFactor({deltaY: 120}) + ", small=" + wheelFactor({deltaY: 10}) ** 12 + ", zero=" + wheelFactor({deltaY: 0}));
`], { encoding: "utf8" });
process.stdout.write(checks.stdout);
if (checks.status !== 0) { process.stderr.write(checks.stderr); process.exit(1); }
console.log("web js self-check OK");
