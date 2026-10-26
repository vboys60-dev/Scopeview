// 包絡共用繪圖回歸檢查：連線、缺口、極值與至少 1px 高；原始折線維持原狀。
import assert from 'node:assert/strict';
import { drawPixels, envPixels, linear, logmap } from './plotcore.js';

function trace(p) {
  const paths = [];
  const ctx = {
    beginPath() {}, stroke() {},
    moveTo(x, y) { paths.push([[x, y]]); },
    lineTo(x, y) { paths.at(-1).push([x, y]); },
  };
  drawPixels(ctx, p, '#fff');
  return paths;
}

// 主圖、縮圖、FFT（含對數頻率）使用的映射，皆須保留每桶極值與桶間連線。
const env = { n: 6, mode: 1, x: [1, 2, 3, 4, 5, 6],
  hi: [10, 10.1, 2, 10, 10, 10], lo: [9.9, 10, 1, 9.9, 9.9, 9.9] };
for (const X of [linear(1, 6, 84, 1534), linear(1, 6, 0, 1450), logmap(1, 6, 84, 1534)]) {
  const p = envPixels(env, X, linear(12, 0, 0, 240));
  const paths = trace(p);
  assert.equal(paths.length, 1, '相鄰有限桶須形成連續路徑');
  for (let i = 0; i < env.n; i++) {
    const points = paths[0].filter(([x]) => x === p.x[i]);
    assert.equal(points.length, 2, '每桶須走完一條垂直線');
    assert.deepEqual(points.map(([, y]) => y).sort((a, b) => a - b),
      [p.top[i], Math.max(p.bot[i], p.top[i] + 1)], '保留桶極值與至少 1px 高');
  }
}
// 任一端為 NaN 都要中斷，不能跨過缺口連到後桶。
for (const invalid of ['top', 'bot', 'both']) {
  const p = { mode: 1, x: [0, 1, 2, 3, 4, 5], top: [5, 5, 5, 5, 5, 5], bot: [5, 5.1, 5, 5, 5, 5] };
  for (const key of invalid === 'both' ? ['top', 'bot'] : [invalid]) p[key][2] = p[key][3] = NaN;
  const paths = trace(p);
  assert.deepEqual(paths.map(path => [...new Set(path.map(([x]) => x))]), [[0, 1], [4, 5]], 'NaN 桶前後須分成兩條路徑');
}
assert.deepEqual(trace({ mode: 1, x: [0], top: [5], bot: [5] }), [[[0, 5], [0, 6]]]);
assert.deepEqual(trace({ mode: 1, x: [], top: [], bot: [] }), []);
assert.deepEqual(trace({ mode: 1, x: [0], top: [NaN], bot: [NaN] }), []);
assert.deepEqual(trace({ mode: 0, x: [0, 1, 2, 3, 4], top: [5, 6, NaN, 7, 8] }),
  [[[0, 5], [1, 6]], [[3, 7], [4, 8]]]);
console.log('envelope self-check OK');
