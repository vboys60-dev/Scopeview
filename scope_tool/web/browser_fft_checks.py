"""L8：FFT 獨立分頁四尺寸與零尺寸匯出檢查；由 browser_check 注入已開檔的 CDP。"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scope_tool.web.browser_check import Cdp

SIZES = ((2000, 1290), (1400, 900), (1000, 800), (1000, 700))


def fft_page(c: Cdp, prep: str) -> None:
    original = c.js("({width:innerWidth,height:innerHeight,dpr:devicePixelRatio})")
    try:
        # 分析頁窄矮視窗切 FFT：頻譜至少 220px（實測 230）；主圖隱藏時匯出應立即提示。
        c.send('Emulation.setDeviceMetricsOverride', width=1000, height=700, deviceScaleFactor=1, mobile=False)
        c.js(f"(async()=>{{{prep}S.command('tab.select','analysis');S.command('fft.visible',true)}})()")
        c.wait("!document.querySelector('.analysis__plotTabs').hidden")
        c.js("document.querySelector('[data-pane=fft]').click()"); c.pump(0.4)
        hh = c.js("document.querySelector('.analysis .analysis__fftplot').getBoundingClientRect().height"); assert hh >= 220, f'fftplot 高度 {hh}'
        assert c.js("document.querySelector('.analysis__main canvas').getBoundingClientRect().width===0"), '主圖未隱藏'
        response = c.js('(async()=>{' + prep + """
            const {exportReport}=await import('/js/analysis/report.js');let message='';const start=performance.now();
            return Promise.race([
              exportReport({store:S,ui:{toast:m=>{message=m}}},document.querySelector('.analysis'),()=>{throw Error('零尺寸不應開啟對話框')})
                .then(()=>({message,ms:performance.now()-start})),
              new Promise(resolve=>setTimeout(()=>resolve({message:'逾時',ms:1000}),1000))]);})()""")
        assert response['ms'] < 1000 and response['message'] == '請先切回波形分頁再匯出', response
        c.js("document.querySelector('[data-pane=wave]').click()")
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
        # 疊圖色與圖例畫進畫布；切相位後隱藏，重新開檔後清空。
        c.js("document.querySelector('.fftpage [data-pin]').click()")
        c.wait("!document.querySelector('.fftpage [data-clear-overlay]').disabled", 20)
        c.js("document.querySelector('.fftpage [data-pin]').click()")
        c.wait("""(()=>{const c=document.querySelector('.fftpage canvas'),d=c.getContext('2d').getImageData(0,0,c.width,c.height).data;
            let pink=0,cyan=0;for(let i=0;i<d.length;i+=4){if(d[i]>200&&d[i+1]>40&&d[i+1]<150&&d[i+2]>120) pink++;
            if(d[i]<120&&d[i+1]>160&&d[i+2]>200) cyan++;}return pink>0&&cyan>0})()""", 20)
        c.js("""(()=>{const root=document.querySelector('.fftpage'), unit=[...root.querySelectorAll('select')].find(e=>[...e.options].some(o=>o.value==='Phase')); unit.dataset.previousUnit=unit.value; unit.value='Phase'; unit.dispatchEvent(new Event('change')); const box=root.querySelector('[aria-label="Unwrap"]'); box.checked=true; box.dispatchEvent(new Event('change'));})()""")
        c.wait(f"(async()=>{{{prep}return S.state.fftResult?.ok && S.state.fftResult.unit === '°'}})()", 20)
        assert c.js("document.querySelector('.fftpage [data-status]').textContent.includes('2 條疊圖')")
        assert c.js('''(()=>{const c=document.querySelector('.fftpage canvas'),d=c.getContext('2d').getImageData(0,0,c.width,c.height).data;
            for(let i=0;i<d.length;i+=4) if(d[i]>200&&d[i+1]>40&&d[i+1]<150&&d[i+2]>120) return false;return true})()''')
        c.js("""(()=>{const root=document.querySelector('.fftpage'), unit=[...root.querySelectorAll('select')].find(e=>e.dataset.previousUnit); unit.value=unit.dataset.previousUnit; unit.dispatchEvent(new Event('change'));})()""")
        old_gen = c.js(f"(async()=>{{{prep}return S.state.file.gen}})()")
        c.js(f"(async()=>{{{prep}S.command('file.open',{{path:S.state.file.path}})}})()")
        c.wait(f"(async()=>{{{prep}return S.state.file?.gen !== {old_gen} && !!S.state.file}})()", 20)
        assert c.js("document.querySelector('.fftpage [data-clear-overlay]').disabled")
    finally:
        c.js(f"(async()=>{{{prep}S.command('tab.select','analysis');S.command('fft.visible',false)}})()")
        c.send("Emulation.setDeviceMetricsOverride", width=original['width'], height=original['height'],
               deviceScaleFactor=original['dpr'], mobile=False)
        c.pump(0.2)


if __name__ == '__main__':
    assert len(SIZES) == 4 and (1000, 700) in SIZES and min(h for _, h in SIZES) == 700
    print('browser_fft_checks self-check OK（尺寸清單；實際版面待 browser_check）')
