from __future__ import annotations

"""協定中立的類比渲染與 CSV；保持逐線亂數與運算順序。"""
from pathlib import Path
import numpy as np


def render(trans: list[tuple[float, str, int]], fs: float, *, lines: tuple[str, ...] = ('scl', 'sda'),
           levels: dict | None = None, vdd: float = 1.8,
           tr: float = 2e-9, noise: float = .02, seed: int = 0,
           nan: tuple = (), end: float | None = None) -> tuple[np.ndarray, ...]:
    """逐線以最後轉換的一階 RC 渲染，分塊暫存不隨整檔成長。"""
    end = end if end is not None else max(x[0] for x in trans) + 1e-6
    t = np.arange(int(np.ceil(end * fs)) + 1, dtype=float) / fs
    rng = np.random.default_rng(seed)
    out = []
    tau = tr / 2.2
    for line in lines:
        pair = (levels or {}).get(line)
        a = [(tm, val * vdd if pair is None else pair[val]) for tm, ln, val in trans if ln == line]
        et, target = np.array(a).T
        prev = np.r_[target[0], target[:-1]].copy()
        if tau > 0:
            for i in range(1, len(et)):
                prev[i] = target[i - 1] + (prev[i - 1] - target[i - 1]) * np.exp(-(et[i] - et[i - 1]) / tau)
        v = np.empty(len(t))
        for start in range(0, len(t), 1 << 20):
            ts = t[start:start + (1 << 20)]
            ix = np.maximum(0, np.searchsorted(et, ts, side='right') - 1)
            val = target[ix].copy()
            if tau > 0:
                val += (prev[ix] - val) * np.exp(-(ts - et[ix]) / tau)
            if noise:
                val += rng.normal(0, noise * vdd, len(ts))
            v[start:start + len(ts)] = val
        for lo, hi in nan:
            v[np.searchsorted(t, lo):np.searchsorted(t, hi)] = np.nan
        out.append(v)
    return t, *out


def write_csv(path: Path, waves: tuple[np.ndarray, ...]) -> None:
    """開新檔、不覆寫；呼叫端提供帶時間戳的路徑。"""
    with path.open('x', encoding='utf-8') as stream:
        np.savetxt(stream, np.column_stack(waves), delimiter=',', header='Time(s)'+''.join(f',CH{i}(V)' for i in range(1, len(waves))), comments='', fmt='%.17e')


if __name__ == '__main__':
    import tempfile
    t, v = render([(0., 'tx', 0), (1e-6, 'tx', 1)], 1e7, lines=('tx',), levels={'tx': (-12, 12)}, noise=0)
    assert v[0] == -12 and v[-1] > 11
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / '波形.csv'
        write_csv(p, (t, v))
        assert p.read_text().splitlines()[0] == 'Time(s),CH1(V)'
    print('web.synth self-check OK')
