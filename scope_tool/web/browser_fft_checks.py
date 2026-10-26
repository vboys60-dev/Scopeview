"""L8：FFT 獨立分頁三尺寸檢查；由 browser_check 注入已開檔的 CDP。"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scope_tool.web.browser_check import Cdp

SIZES = ((2000, 1290), (1400, 900), (1000, 800))


def fft_page(c: Cdp, prep: str) -> None:
    original = c.js("({width:innerWidth,height:innerHeight,dpr:devicePixelRatio})")
    try:
        # 從分析頁新增按鈕切換，連同 tab.select 接線一起驗證。
        c.js("[...document.querySelectorAll('.analysis__toolbar button')].find(e=>e.textContent==='FFT 頻譜 ↗').click()")
        c.wait("!document.querySelector('#tab-fft').hidden")
        c.wait(f"(async()=>{{{prep}return !!S.state.fftResult?.ok}})()", 20)
        for width, height in SIZES:
            c.send("Emulation.setDeviceMetricsOverride", width=width, height=height, deviceScaleFactor=1, mobile=False)
            c.pump(0.5)
            dims = c.js("""(()=>{
                const root=document.querySelector('.fftpage'), box=e=>{
                    const r=e.getBoundingClientRect();return {top:r.top,bottom:r.bottom,left:r.left,right:r.right,height:r.height};
                };
                const controls=[...root.querySelectorAll('input,select,button')].filter(e=>e.getClientRects().length);
                return {plot:box(root.querySelector('.analysis__fftplot')),
                    table:box(root.querySelector('[aria-label="FFT Marker Table"]')),
                    bars:[...root.querySelectorAll('.fftpage__source,.fftpage__params,.fftpage__markers,.analysis__fftbar')].map(e=>({
                        ...box(e),controls:[...e.querySelectorAll('input,select,button,label')].map(box)
                    })), controls:controls.map(box), width:innerWidth,height:innerHeight,
                    ids:[...root.querySelectorAll('[id]')].map(e=>e.id)};
            })()""")
            assert dims['plot']['height'] >= 240, dims
            assert dims['table']['height'] > 0 and dims['table']['top'] < height, dims
            assert all(0 <= e['left'] and e['right'] <= width for e in dims['controls']), dims
            assert all(e['top'] >= bar['top'] and e['bottom'] <= bar['bottom']
                       for bar in dims['bars'] for e in bar['controls']), dims
            assert len(dims['ids']) == len(set(dims['ids'])), dims
    finally:
        c.js(f"(async()=>{{{prep}S.command('tab.select','analysis')}})()")
        c.send("Emulation.setDeviceMetricsOverride", width=original['width'], height=original['height'],
               deviceScaleFactor=original['dpr'], mobile=False)
        c.pump(0.2)


if __name__ == '__main__':
    assert len(SIZES) == 3 and min(h for _, h in SIZES) == 800
    print('browser_fft_checks self-check OK（尺寸清單；實際版面待 browser_check）')
