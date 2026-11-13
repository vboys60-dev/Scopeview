"""解碼 ▲ 的獨立 CDP 驗收；由主控注入已啟動頁面，不接入 browser_check。# 待真機驗證。"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING
from scope_tool.web.i2c_synth import fixture

if TYPE_CHECKING:
    from scope_tool.web.browser_check import Cdp

CANVAS = "document.querySelector('.analysis__main canvas')"
MARKS = f"{CANVAS}.decodeMarks()"
ROWS = '.decode__tablewrap tbody tr'


def decode_marks(c: Cdp, prep: str, directory: str) -> None:
    """I2C 真按鈕與像素檢查；DPR 1／2 各跑，座標一律由 CSS px 換算。"""
    source = Path(directory) / f'marks_{time.strftime("%Y%m%d_%H%M%S")}.csv'
    settings = fixture(source)
    original = c.js(f"(async()=>{{{prep}return {{w:innerWidth,h:innerHeight,dpr:devicePixelRatio,grids:S.state.grids}}}})()")

    def state(code: str) -> str:
        return f'(async()=>{{{prep}{code}}})()'

    def open_file() -> None:
        gen = c.js(state('return S.state.file?.gen ?? null'))
        c.js(state(f"S.command('file.open',{{path:{json.dumps(str(source))}}})"))
        c.wait(state(f'return !!S.state.file && S.state.file.gen!=={json.dumps(gen)}'), 30)
        c.wait(f"!!{CANVAS}?.decodeMarks")

    def select_third() -> None:
        c.wait(f"document.querySelectorAll('{ROWS}').length>=3")
        c.js(f"document.querySelectorAll('{ROWS}')[2].click()")
        c.wait(f'{MARKS}.length>0')
        c.wait(f"{CANVAS}.dataset.pending!== '1'", 30)

    def sample() -> list:
        return c.js(f"""(()=>{{const cv={CANVAS},g=cv.getContext('2d'),scale=cv.width/cv.clientWidth;
          return cv.decodeMarks().map(m=>Array.from(g.getImageData(
            Math.floor(m.x*scale),Math.floor((m.row.t+m.row.h-4)*scale),1,1).data));}})()""")

    try:
        for dpr in (1, 2):
            c.send('Emulation.setDeviceMetricsOverride', width=1400, height=900, deviceScaleFactor=dpr, mobile=False)
            c.js(state("S.command('tab.select','analysis');S.command('fft.visible',false)"))
            open_file()
            c.js("document.querySelector('[data-result-tab=decode]').click()")
            c.js("(()=>{const e=document.querySelector('[data-protocol]');e.value='i2c';e.dispatchEvent(new Event('change'))})()")
            for role, name in settings['channels'].items():
                c.js(f"(()=>{{const e=document.querySelector('[data-role={role}]');e.value={json.dumps(name)};e.dispatchEvent(new Event('input'))}})()")
            c.js(state("S.set({grids:{n:1,assign:{}}})"))
            c.js("document.querySelector('[data-decode-action=run]').click()")
            c.wait(state('return S.state.decodeResult?.summary.ok && !S.state.decodeResult.stale'), 30)
            select_third()
            c.wait(f'{MARKS}.length===1')
            expected = c.js("""(async()=>{const {plotColors}=await import('/js/analysis/plotcore.js');
              const cv=document.createElement('canvas'),g=cv.getContext('2d');g.fillStyle=plotColors().amber;
              g.fillRect(0,0,1,1);return Array.from(g.getImageData(0,0,1,1).data)})()""")
            assert all(abs(a-b) <= 3 for a, b in zip(sample()[0], expected)), f'DPR {dpr}：▲ 中心非琥珀'
            assert c.js(f'{CANVAS}.width/{CANVAS}.clientWidth') == dpr
            c.js(state("window.__markView=S.state.view;const v=S.state.view,d=v.t1-v.t0;S.command('viewport.intent',{t0:v.t1+d,t1:v.t1+2*d})"))
            c.wait(f'{MARKS}.length===0')
            c.js(state("S.command('viewport.intent',window.__markView);S.set({grids:{n:2,assign:{CHAN1:0,CHAN2:1}}})"))
            c.wait(f'{MARKS}.length===2')
            assert c.js(f'new Set({MARKS}.map(m=>m.row.index)).size') == 2
            c.js("(()=>{const e=document.querySelector('[data-option=addr_bits]');e.value=e.value==='7'?'8':'7';e.dispatchEvent(new Event('input'))})()")
            c.wait(f'{MARKS}.length===2 && {MARKS}.every(m=>m.stale)')
            assert all(pixel[0] < expected[0]-20 for pixel in sample()), '過期 ▲ 應淡化'
            c.js("document.querySelector('[data-decode-action=run]').click()")
            assert c.js(f'{MARKS}.length') == 0, '重新解碼須清除選取 ▲'
            c.wait(state('return S.state.decodeResult?.summary.ok && !S.state.decodeResult.stale'), 30)
            select_third()
            open_file()
            assert c.js(f'{MARKS}.length') == 0, '重新開檔須清除 ▲'
    finally:
        c.send('Emulation.setDeviceMetricsOverride', width=original['w'], height=original['h'],
               deviceScaleFactor=original['dpr'], mobile=False)
        c.js(state(f"S.set({{grids:{json.dumps(original.get('grids') or {'n': 1, 'assign': {}})}}})"))


if __name__ == '__main__':
    assert 'decodeMarks' in MARKS and ROWS.endswith('tbody tr')
    print('browser_mark_checks self-check OK（入口；實際 DPR 與像素待主控驗收）')
