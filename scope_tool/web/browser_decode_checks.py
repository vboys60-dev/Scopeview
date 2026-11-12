from __future__ import annotations

"""P3／P4 真瀏覽器解碼驗收與搬出的既有 NaN CSV 步驟。# 待真機驗證。"""
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
    assert c.js("[...document.querySelectorAll('.decode__bar select[data-role]')].map(s=>s.value)") == ['CHAN1', 'CHAN2']
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
    # 匯出先選資料夾（頁內 <dialog> prompt）：填入 directory 並確定
    c.wait("!!document.querySelector('dialog[open] input')")
    c.js(f"(()=>{{const d=document.querySelector('dialog[open]');d.querySelector('input').value={json.dumps(str(directory))};d.querySelector('.btn--primary').click()}})()")
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
    decode_band(c, prep, directory)
    c.shot(out / 'decode_1400.png')
    c.send('Emulation.setDeviceMetricsOverride', width=1000, height=800, deviceScaleFactor=1, mobile=False)
    c.pump(.4)
    assert c.js('document.documentElement.scrollWidth <= document.documentElement.clientWidth')
    assert c.js("(()=>{const e=document.querySelector('.decode__bar');e.scrollLeft=e.scrollWidth;return e.scrollWidth<=e.clientWidth||e.scrollLeft>0})()")  # 兩列版面可自動換行，不再必然溢出；溢出時須可捲到
    c.shot(out / 'decode_1000.png')
    c.js(f"(async()=>{{{prep} S.command('fft.visible',true)}})()")
    c.pump(.3)
    c.js("document.querySelector('[data-pane=fft]').click()")
    c.wait("document.querySelector('.analysis__decodeband').hidden")
    c.js("document.querySelector('[data-pane=wave]').click()")
    c.wait("!document.querySelector('.analysis__decodeband').hidden")
    c.js(f"(async()=>{{{prep} S.command('fft.visible',false)}})()")
    c.js("(()=>{const e=document.querySelector('.decode__addresses');e.value='50, 51';e.dispatchEvent(new Event('input',{bubbles:true}))})()")
    assert c.js(f'(async()=>{{{prep} return S.state.decodeResult.stale}})()')
    assert c.js("document.querySelector('.decode__sum').textContent.includes('設定已變更，請重新解碼') && document.querySelector('[data-decode-action=export]').disabled")
    c.send('Emulation.setDeviceMetricsOverride', width=1400, height=900, deviceScaleFactor=1, mobile=False)
    assert not c.errors, c.errors
    protocol_pages(c, prep, out, directory)


def decode_band(c: Cdp, prep: str, directory: str) -> None:
    """P4：實際 canvas 像素、RPC、互選、報告與 Chrome 重畫效能。"""
    c.wait("!document.querySelector('.analysis__decodeband').hidden")
    assert c.js("document.querySelector('.analysis__main').getBoundingClientRect().height >= 270")
    # 使用實際後端 byte，並記錄真 mount 的 decode_bits 呼叫。
    c.js(f"""(async()=>{{{prep}
      window.__decodeOriginalCall=B.call;window.__decodeBitCalls=0;
      B.call=async function(n,p){{if(n==='decode_bits')window.__decodeBitCalls++;return window.__decodeOriginalCall.call(this,n,p)}};
      const r=S.state.decodeResult, f=r.frames.find(f=>f.fields.some(x=>x.nbits===9&&x.kind==='data'));
      const x=f.fields.find(x=>x.nbits===9&&x.kind==='data'), d=S.state.channels.find(c=>c.name===r.base).time_offset||0;
      window.__decodeFrame=f.i; S.set({{decodeSel:null}});
      const pad=(x.t1-x.t0)/80; S.command('viewport.intent',{{t0:x.t0+d-pad,t1:x.t1+d+pad}});
    }})()""")
    c.wait("window.__decodeBitCalls>0 && +document.querySelector('.analysis__decodeband canvas').dataset.bits===9")
    geometry = c.js(f"""(async()=>{{{prep}
      const cv=document.querySelector('.analysis__decodeband canvas'),g=cv.getContext('2d'),d=devicePixelRatio,
        l=S.state.plotRect.l,p=g.getImageData(0,0,cv.width,cv.height).data,w=cv.width;
      const bg=[...p.slice(0,3)];let ink=0,first=null;
      for(let y=0;y<cv.height;y++)for(let x=0;x<w;x++){{const i=(y*w+x)*4;if(bg.some((v,k)=>p[i+k]!==v))ink++}}
      for(let x=Math.floor((l-2)*d);x<w;x++){{const i=(Math.round(8*d)*w+x)*4;if(bg.some((v,k)=>p[i+k]!==v)){{first=x/d;break}}}}
      const main=document.querySelector('.analysis__main canvas').getBoundingClientRect(),b=cv.getBoundingClientRect();
      cv.dispatchEvent(new MouseEvent('click',{{clientX:b.left+l+S.state.plotRect.w/2,clientY:b.top+8,bubbles:true}}));
      return {{ink,delta:Math.abs(main.left+l-b.left-first),height:b.height}};
    }})()""")
    assert geometry['ink'] > 100 and geometry['delta'] <= 1 and geometry['height'] == 80, geometry
    c.wait("document.querySelector('.decode__tablewrap tr.is-selected')?.dataset.decodeFrame===String(window.__decodeFrame)")
    assert c.js("""(()=>{const e=document.querySelector('.analysis__splitter--lower'),r=e.getBoundingClientRect();return document.elementFromPoint(r.left+r.width/2,r.top+r.height/2)===e})()""")
    # 開關只改顯示；保留有效資料，且 chrome 預算恢復主圖高度。
    c.js("document.querySelector('.decode__bar input[type=checkbox]').click()")
    c.wait("document.querySelector('.analysis__decodeband').hidden")
    assert c.js(f'(async()=>{{{prep} return !S.state.decodeResult.stale}})()')
    c.js("document.querySelector('.decode__bar input[type=checkbox]').click()")
    c.wait("!document.querySelector('.analysis__decodeband').hidden")
    # 實際 exportReport → export_report → 來源資料夾，不開人工對話框。
    old = set(Path(directory).glob('*.html'))
    c.js(f"""(async()=>{{{prep}
      const {{exportReport}}=await import('/js/analysis/report.js'),fmt=await import('/js/fmt.js');
      const ui={{toast(){{}},showError(e){{throw e}},pickPath:async()=>{json.dumps(str(directory))}}};
      await exportReport({{store:S,bridge:B,fmt,ui}},document.querySelector('.analysis'),async()=>({{title:'I3C P4 驗收',invert:false}}));
    }})()""")
    created = set(Path(directory).glob('*.html')) - old
    assert len(created) == 1, created
    html = next(iter(created)).read_text('utf-8')
    assert '解碼（I3C）' in html and '私有寫' in html and '<th>內容</th>' in html
    assert 'alt="解碼（I3C）"' in html
    # 直接使用產品 drawBand，5000 筆互不重疊且包含 fields；量一次完整重畫。
    elapsed = c.js(f"""(async()=>{{{prep}
      const {{drawBand,bandHeight}}=await import('/js/analysis/decode_band.js'),r=S.state.decodeResult;
      const frames=Array.from({{length:5000}},(_,i)=>({{i,t0:i,t1:i+.9,kind:'private_write',status:['ok','warn','error'][i%3],label:'私有寫',
        fields:[{{t0:i+.1,t1:i+.8,value:0x5A,nbits:9,ninth:1,ninth_kind:'parity',ok:i%3!==2}}]}}));
      const cv=document.createElement('canvas');cv.width=1400;const g=cv.getContext('2d');
      const st={{...S.state,view:{{t0:0,t1:5000}},channels:[],plotRect:{{l:84,w:1306}},decodeResult:{{...r,frames}}}};
      cv.height=bandHeight(st);
      for(let i=0;i<3;i++)drawBand(g,1400,st);
      const t=performance.now();drawBand(g,1400,st);const ms=performance.now()-t;
      B.call=window.__decodeOriginalCall;delete window.__decodeOriginalCall;return ms;
    }})()""")
    assert elapsed < 30, elapsed
    print(f'  P4 標註列：左緣差 {geometry["delta"]:.2f}px；5000 frames draw {elapsed:.2f}ms；報告 {next(iter(created))}')


def protocol_pages(c: Cdp, prep: str, out: Path, directory: str) -> None:
    """只驗已註冊且提供 fixture 的新協定；I3C 由上方完整步驟驗收。"""
    import importlib
    names = c.js("(async()=>Object.keys(await import('/js/analysis/decode_protocols.js')))()")
    for name in names:
        if name == 'i3c':
            continue
        module = f'scope_tool.web.{name}_synth'
        try:
            synth = importlib.import_module(module)
        except ModuleNotFoundError as exc:
            if exc.name != module:
                raise
            continue
        if not hasattr(synth, 'fixture'):
            continue
        path = Path(directory) / f'decode_{name}_{time.strftime("%Y%m%d_%H%M%S")}.csv'
        fixture = synth.fixture(path)
        gen = c.js(f'(async()=>{{{prep} return S.state.file?.gen}})()')
        c.js(f"(async()=>{{{prep} S.command('file.open',{{path:{json.dumps(str(path))}}})}})()")
        c.wait(f'(async()=>{{{prep} return S.state.file?.gen !== {gen}}})()')
        c.js("document.querySelector('[data-result-tab=decode]').click()")
        c.js(f"(()=>{{const s=document.querySelector('[data-protocol]');s.value={json.dumps(name)};s.dispatchEvent(new Event('change'))}})()")
        for kind, values in [('role', fixture['channels']), ('option', fixture['options'])]:
            for key, value in values.items():
                c.js(f"""(()=>{{const e=document.querySelector('[data-{kind}={key}]');
                  if(e.type==='checkbox')e.checked={json.dumps(value)};else e.value=String({json.dumps(value)});
                  e.dispatchEvent(new Event('input'))}})()""")
        c.js("document.querySelector('[data-decode-action=run]').click()")
        c.wait(f'(async()=>{{{prep} return S.state.decodeResult?.summary.ok}})()', 30)
        result = c.js(f'(async()=>{{{prep} return S.state.decodeResult}})()')
        if name == 'uart':
            # 先把鮑率改錯，才看得出估計真的填了值；改值只會使結果過期，不清除。
            c.js("(()=>{const e=document.querySelector('[data-option=baud]');e.value='1200';e.dispatchEvent(new Event('input'))})()")
            c.js(f"(async()=>{{{prep} window.__estimateBefore=S.state.decodeResult;window.__estimateSel=S.state.decodeSel}})()")
            c.js("document.querySelector('[data-decode-action=estimate]').click()")
            c.wait(f"document.querySelector('[data-option=baud]').value==='{fixture['options']['baud']}'", 30)
            same = c.js(f"(async()=>{{{prep} const r=S.state.decodeResult,b=window.__estimateBefore;return !!r && r.summary.decode_id===b.summary.decode_id && r.frames===b.frames && S.state.decodeSel===window.__estimateSel}})()")
            assert same, '估計不應清除既有解碼結果或選取'
            c.wait("document.querySelector('.decode__sum').textContent.includes('請確認後解碼')", 10)
            # 改鮑率使結果過期（匯出停用），重新解碼後再繼續後面的共用檢查。
            c.js("document.querySelector('[data-decode-action=run]').click()")
            c.wait(f'(async()=>{{{prep} const r=S.state.decodeResult;return r?.summary.ok && !r.stale && r.options.baud==={fixture["options"]["baud"]}}})()', 30)
            result = c.js(f'(async()=>{{{prep} return S.state.decodeResult}})()')
        if name == 'i2c':
            c.js("(()=>{const e=document.querySelector('[data-option=addr_bits]');e.value='8';e.dispatchEvent(new Event('input'));document.querySelector('[data-decode-action=run]').click()})()")
            c.wait(f'(async()=>{{{prep} return S.state.decodeResult?.options.addr_bits===8}})()', 30)
            result = c.js(f'(async()=>{{{prep} return S.state.decodeResult}})()')
            assert c.js("document.querySelector('.decode__tablewrap tbody tr td:nth-child(4)').textContent") == '0xA0'
            # 直接截取實際繪圖文字，維持 byte 檢視以驗證標註列。
            c.js(f"""(async()=>{{{prep} const p=CanvasRenderingContext2D.prototype,fill=p.fillText;
              window.__addrTexts=[];p.fillText=function(t,...a){{window.__addrTexts.push(t);return fill.call(this,t,...a)}};
              window.__addrRestore=()=>{{p.fillText=fill}};S.command('viewport.intent',{{t0:S.state.decodeResult.summary.t0,t1:S.state.decodeResult.summary.t0+.003}})}})()""")
            c.wait("window.__addrTexts.includes('A0')")
            c.js('window.__addrRestore()')
        frames = result['frames']
        assert len(frames) < 2000 and len(frames) > 1
        assert set(fixture['expect_kinds']) <= {f['kind'] for f in frames}
        assert c.js("document.querySelectorAll('.decode__tablewrap tbody tr').length") == len(frames)
        c.js("document.querySelectorAll('.decode__tablewrap tbody tr')[1].click()")
        centered = c.js(f"""(async()=>{{{prep} const s=S.state,r=s.decodeResult,f=r.frames[1],
          dx=s.channels.find(c=>c.name===r.base).time_offset||0;
          return Math.abs((s.view.t0+s.view.t1)/2-(f.t0+f.t1)/2-dx)/(s.view.t1-s.view.t0)}})()""")
        assert centered < .01
        before = set(Path(directory).glob('*解碼*.csv'))
        c.js("document.querySelector('[data-decode-action=export]').click()")
        c.wait("!!document.querySelector('dialog[open] input')")
        c.js(f"(()=>{{const d=document.querySelector('dialog[open]');d.querySelector('input').value={json.dumps(str(directory))};d.querySelector('.btn--primary').click()}})()")
        for _ in range(30):
            c.pump(.1)
            created = set(Path(directory).glob('*解碼*.csv')) - before
            if created:
                break
        assert len(created) == 1
        rows = list(csv.reader(next(iter(created)).open(encoding='utf-8-sig')))
        assert len(rows)-7 == sum(max(1, len(f['fields'])) for f in frames)
        c.js(f"""(async()=>{{{prep} const r=S.state.decodeResult,def=(await import('/js/analysis/decode_protocols.js'))[r.protocol];
          window.__protoBits=0;const call=B.call;B.call=async(n,p)=>{{if(n==='decode_bits')window.__protoBits++;return call(n,p)}};
          window.__protoSingle=!def.lanes(r.summary);const x=r.frames.flatMap(f=>f.fields).find(x=>x.nbits>1),dx=S.state.channels.find(c=>c.name===r.base).time_offset||0;
          if(x&&window.__protoSingle){{const pad=(x.t1-x.t0)/80;S.command('viewport.intent',{{t0:x.t0+dx-pad,t1:x.t1+dx+pad}})}}
          window.__protoRestore=()=>{{B.call=call}};}})()""")
        c.wait("!window.__protoSingle || window.__protoBits>0")
        assert c.js("(()=>{const c=document.querySelector('.analysis__decodeband canvas'),p=c.getContext('2d').getImageData(0,0,c.width,c.height).data;return p.some((v,i)=>i%4<3&&v!==p[i%4])})()")
        for width in (1400, 1000):
            c.send('Emulation.setDeviceMetricsOverride', width=width, height=900, deviceScaleFactor=1, mobile=False)
            c.pump(.3)
            assert c.js("document.documentElement.scrollWidth<=document.documentElement.clientWidth")
            c.shot(out / f'decode_{name}_{width}.png')
        c.send('Emulation.setDeviceMetricsOverride', width=1400, height=900, deviceScaleFactor=1, mobile=False)  # 還原寬度；模組命名空間依字母排序，後一個協定不可從 1000 寬開始
        c.pump(.3)
        c.js('window.__protoRestore()')
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
