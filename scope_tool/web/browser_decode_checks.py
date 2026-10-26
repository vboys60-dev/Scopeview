from __future__ import annotations

"""P3 真瀏覽器分頁驗收與搬出的既有 NaN CSV 步驟。# 待真機驗證。"""
import csv
import json
import time
from pathlib import Path
from typing import TYPE_CHECKING
from scope_tool.web.i3c_synth import Bus, write_csv
if TYPE_CHECKING:
    from scope_tool.web.browser_check import Cdp


def nan_csv(c: Cdp, prep: str, canvas_ink: str, out: Path, directory: str) -> None:
    """既有完整步驟移出主檔，保留相同資料、像素檢查與截圖。"""
    nanp = Path(directory) / 'nan.csv'
    nanp.write_text('Time(s),CH1(V)\n' + ''.join(f"{i * 1e-6},{'nan' if 40 <= i < 60 else (i % 20) / 10}\n" for i in range(200)), 'utf-8')
    c.js(f"(async()=>{{{prep} S.command('file.open',{{path:{json.dumps(str(nanp))}}})}})()")
    c.pump(2)
    c.wait(f'{canvas_ink}>100')
    c.shot(out / '09_nan_csv.png')


def decode_fixture(path: Path) -> None:
    """約 20 萬點，涵蓋中途開始、私有讀寫、錯同位、DAA 仲裁、IBI 與 Reset。"""
    b = Bus().start().header(8).byte_w(0x55).byte_w(0x33).stop()
    cut = b.now * .37
    b.start().header(0x7E, od=True).rstart().header(8).byte_w(0xA5).stop()
    b.start().header(8).byte_w(0x81, t=0).stop()
    b.start().header(0x7E, od=True).rstart().header(8, 1).byte_r(0x55, 1).byte_r(0x33, 1, abort=True).stop()
    b.entdaa([(0x800000000000, 2, 1), (0x0123456789AB, 6, 0x44)])
    b.ibi(8, (0x1F, 0x22, 0x44)).target_reset()
    b.idle(max(0, 200e-6 - b.now))
    waves = b.render(noise=.01, seed=3)
    keep = waves[0] >= cut
    write_csv(path, tuple(w[keep] for w in waves))


def decode_page(c: Cdp, prep: str, out: Path, directory: str) -> None:
    """走實際按鈕、真後端與 CSV；僅由沙箱外 browser_check 呼叫。"""
    c.send('Emulation.setDeviceMetricsOverride', width=1400, height=900, deviceScaleFactor=1, mobile=False)
    c.js(f"(async()=>{{{prep} S.command('layout.restore',{{side:240,lower:350,fft:180}});S.command('fft.visible',false)}})()")
    c.pump(.5)
    geometry = "(()=>{const h=s=>document.querySelector(s).getBoundingClientRect().height;return [h('.analysis__toolbar'),h('.analysis__resultTabs')]})()"
    baseline = c.js(geometry)
    stamp = time.strftime('%Y%m%d_%H%M%S')
    source = Path(directory) / f'decode_{stamp}.csv'
    decode_fixture(source)
    gen = c.js(f'(async()=>{{{prep} return S.state.file?.gen}})()')
    c.js(f"(async()=>{{{prep} S.command('file.open',{{path:{json.dumps(str(source))}}})}})()")
    c.wait(f'(async()=>{{{prep} return S.state.file?.gen !== {json.dumps(gen)} && S.state.channels.length===2}})()')
    c.js("document.querySelector('[data-result-tab=decode]').click()")
    c.wait("!document.querySelector('.analysis__decode').hidden")
    assert c.js("[...document.querySelectorAll('.decode__bar select')].map(s=>s.value)") == ['CHAN1', 'CHAN2']
    c.js("document.querySelector('[data-decode-action=run]').click()")
    c.wait(f'(async()=>{{{prep} return S.state.decodeResult?.summary.ok}})()', 30)
    c.pump(.3)
    result = c.js(f'(async()=>{{{prep} return S.state.decodeResult}})()')
    assert result['frames'] and len(result['frames']) < 2000
    rows = '.decode__tablewrap tbody tr'
    assert c.js(f"document.querySelectorAll('{rows}').length") == len(result['frames'])
    assert c.js(f"[...document.querySelectorAll('{rows}')].some(r=>r.lastElementChild.textContent.includes('同位錯'))")
    expected = sum(f['status'] in ('warn', 'error') for f in result['frames'])
    c.js("[...document.querySelectorAll('.decode__sum button')].find(b=>b.textContent==='只錯誤／警告').click()")
    assert c.js(f"document.querySelectorAll('{rows}').length") == expected
    c.js("[...document.querySelectorAll('.decode__sum button')].find(b=>b.textContent==='全部').click()")
    # SCL dx 明確非零，以免只驗到來源時間跳轉。
    c.js(f"(async()=>{{{prep} S.updateChannel('CHAN1',{{time_offset:2e-6}});S.command('viewport.intent',{{t0:0,t1:20e-6}})}})()")
    c.js(f"document.querySelectorAll('{rows}')[3].click()")
    v = c.js(f'(async()=>{{{prep} return {{view:S.state.view,sel:S.state.decodeSel}}}})()')
    f = result['frames'][3]
    assert v['sel'] == f['i']
    assert abs((v['view']['t0'] + v['view']['t1']) / 2 - (f['t0'] + f['t1']) / 2 - 2e-6) < .01 * (v['view']['t1'] - v['view']['t0'])
    # 點真正的匯出按鈕，以新增檔確認工作完成，再核對完整 field 與位址列數。
    old = set(Path(directory).glob('*解碼*.csv'))
    c.js("document.querySelector('[data-decode-action=export]').click()")
    for _ in range(50):
        c.pump(.2)
        created = set(Path(directory).glob('*解碼*.csv')) - old
        if created:
            break
    assert len(created) == 1, created
    exported = next(iter(created))
    with exported.open(encoding='utf-8-sig', newline='') as stream:
        records = list(csv.reader(stream))
    start = next(i for i, r in enumerate(records) if r and r[0] == 'frame#') + 1
    end = next(i for i in range(start, len(records)) if not records[i])
    assert end - start == sum(max(1, len(f['fields'])) for f in result['frames'])
    addr_start = next(i for i, r in enumerate(records) if r and r[0] == 'DA') + 1
    assert len(records) - addr_start == len(result['addresses'])
    print(f'  解碼 CSV：{exported}；事件 {len(result["frames"])}，field 列 {end-start}')
    c.pump(.3)
    assert all(abs(a-b) <= 1 for a, b in zip(baseline, c.js(geometry))), (baseline, c.js(geometry))
    assert c.js('document.documentElement.scrollWidth <= document.documentElement.clientWidth')
    c.shot(out / 'decode_1400.png')
    c.send('Emulation.setDeviceMetricsOverride', width=1000, height=800, deviceScaleFactor=1, mobile=False)
    c.pump(.4)
    assert c.js('document.documentElement.scrollWidth <= document.documentElement.clientWidth')
    assert c.js("(()=>{const e=document.querySelector('.decode__bar');e.scrollLeft=e.scrollWidth;return e.scrollWidth>e.clientWidth&&e.scrollLeft>0})()")
    c.shot(out / 'decode_1000.png')
    c.js("(()=>{const e=document.querySelector('.decode__addresses');e.value='50, 51';e.dispatchEvent(new Event('input',{bubbles:true}))})()")
    assert c.js(f'(async()=>{{{prep} return S.state.decodeResult.stale}})()')
    assert c.js("document.querySelector('.decode__sum').textContent.includes('設定已變更，請重新解碼') && document.querySelector('[data-decode-action=export]').disabled")
    c.send('Emulation.setDeviceMetricsOverride', width=1400, height=900, deviceScaleFactor=1, mobile=False)
    assert not c.errors, c.errors


if __name__ == '__main__':
    import tempfile
    from scope_tool.web.analysis_api import Analysis
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / f'decode_{time.strftime("%Y%m%d_%H%M%S")}.csv'
        decode_fixture(path)
        with path.open() as stream:
            assert 190_000 <= sum(1 for _ in stream) <= 210_000
        api = Analysis()
        info = api.open_waveform(str(path))
        assert [c['name'] for c in info['channels']] == ['CHAN1', 'CHAN2']
        summary = api.decode('i3c', {'scl': 'CHAN1', 'sda': 'CHAN2'}, {'scl': None, 'sda': None}, {})
        assert summary['ok']
        data = api.decode_frames(summary['decode_id'])
        assert any('parity' in f['reasons'] for f in data['frames'])
        assert {'partial', 'private_write', 'private_read', 'daa', 'ibi', 'target_reset'} <= {f['kind'] for f in data['frames']}
        print('browser fixture 真後端檢查 OK：', summary['counts'])
    print('web.browser_decode_checks self-check OK（合成資料；瀏覽器由 browser_check 驗收）')
