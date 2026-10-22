// 依序執行全部 JS 自檢（每支各開子行程：l0 結尾會 process.exit）。
// 用法：node scope_tool/web/static/js/selfcheck_node.js
const { spawnSync } = require("node:child_process");
const path = require("node:path");

const FILES = ["l0_check.mjs", "l2_check.mjs", "l3_check.mjs", "analysis/l4_check.mjs", "analysis/l5_check.mjs"];
for (const f of FILES) {
  const r = spawnSync(process.execPath, [path.join(__dirname, f)], { encoding: "utf8" });
  process.stdout.write(r.stdout);
  if (r.status !== 0) {
    process.stderr.write(`${f} 失敗（exit ${r.status}）\n${r.stderr}`);
    process.exit(1);
  }
}
console.log("web js self-check OK");
