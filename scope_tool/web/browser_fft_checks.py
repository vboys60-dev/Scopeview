"""L8：FFT 獨立分頁四尺寸與零尺寸匯出檢查；由 browser_check 注入已開檔的 CDP。"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scope_tool.web.browser_check import Cdp

SIZES = ((2000, 1290), (1400, 900), (1000, 800), (1000, 700))


def fft_page(c: Cdp, prep: str) -> None:
    original = c.js("""(async()=>({width:innerWidth,height:innerHeight,dpr:devicePixelRatio,
        lowerHidden:document.querySelector('.analysis__lowerbody').hidden,
        layoutRaw:localStorage.getItem('scope.analysis.layout.v1'),
        layoutPrefs:(await import('/js/analysis/layout.js')).loadPrefs()}))()""")
    chan_open = False
    try:
        # 分析頁窄矮視窗切 FFT：B 區展開時頻譜至少 280px、B 內容至少 90px 且圖區不捲動；主圖隱藏時匯出應立即提示。
        c.send('Emulation.setDeviceMetricsOverride', width=1000, height=700, deviceScaleFactor=1, mobile=False)
        c.js(f"(async()=>{{{prep}S.command('tab.select','analysis');S.command('fft.visible',true)}})()")
        c.wait("!document.querySelector('.analysis__plotTabs').hidden")
        # 通道列展開（約多 72px）時預算不足，頻譜只能 ≈230px；此項以收折通道列驗證，展開屬已知限制（docs/驗證.md）。
        chan_open = c.js("(()=>{const t=document.querySelector('.chanbar__toggle');const o=t.getAttribute('aria-expanded')==='true';if(o)t.click();return o})()")
        c.js(f"(async()=>{{{prep}S.command('layout.resize',{{kind:'lower',value:240}})}})()")
        c.pump(0.2)
        c.js("if(document.querySelector('.analysis__lowerbody').hidden) document.querySelector('.analysis__lowertoggle').click()")
        c.wait("!document.querySelector('.analysis__lowerbody').hidden")
        c.js("document.querySelector('[data-pane=fft]').click()"); c.pump(0.4)
        hh = c.js("document.querySelector('.analysis .analysis__fftplot').getBoundingClientRect().height"); info = c.js("(()=>{const h=s=>{const e=document.querySelector(s);return e&&Math.round(e.getBoundingClientRect().height)};return {iw:innerWidth,ih:innerHeight,analysis:h('.analysis'),toolbar:h('.analysis__toolbar'),chanbar:h('.analysis__chanbar'),band:h('.analysis__decodeband'),plotTabs:h('.analysis__plotTabs'),fft:h('.analysis__fft'),lower:h('.analysis__lower'),lowerbody:h('.analysis__lowerbody'),overview:h('.analysis__overview'),layout:localStorage.getItem('scope.analysis.layout.v1')}})()"); assert hh >= 280, f'fftplot 高度 {hh}，應至少 280px：{info}'
        lower = c.js("document.querySelector('.analysis__lowerbody').getBoundingClientRect().height")
        assert lower >= 91, f'B 區內容高度 {lower}，應至少 92px（容許 1px 捨入）'
        scroll = c.js("(()=>{const e=document.querySelector('.analysis__plot');return {scroll:e.scrollHeight,client:e.clientHeight}})()")
        assert scroll['scroll'] <= scroll['client'] + 1, f'分析圖區不應捲動：{scroll}'
        assert c.js("document.querySelector('.analysis__main canvas').getBoundingClientRect().width===0"), '主圖未隱藏'
        response = c.js('(async()=>{' + prep + """
            const {exportReport}=await import('/js/analysis/report.js');let message='';const start=performance.now();
            return Promise.race([
              exportReport({store:S,ui:{toast:m=>{message=m}}},document.querySelector('.analysis'),()=>{throw Error('零尺寸不應開啟對話框')})
                .then(()=>({message,ms:performance.now()-start})),
              new Promise(resolve=>setTimeout(()=>resolve({message:'逾時',ms:1000}),1000))]);})()""")
        assert response['ms'] < 1000 and response['message'] == '請先切回波形分頁再匯出', f'零尺寸匯出提示或耗時不符：{response}'
        c.js("document.querySelector('[data-pane=wave]').click()")
        c.pump(0.4); lower = c.js("document.querySelector('.analysis__lowerbody').getBoundingClientRect().height")
        assert lower >= 200, f'切回波形分頁 B 區應還原約 212px，實際 {lower}'
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
            assert dims['plot']['height'] >= 240, f'FFT 分頁版面不符：{dims}'
            assert dims['table']['height'] > 0 and dims['table']['top'] < height, f'FFT 分頁版面不符：{dims}'
            assert all(0 <= e['left'] and e['right'] <= width for e in dims['controls']), f'FFT 分頁版面不符：{dims}'
            assert all(e['top'] >= bar['top'] and e['bottom'] <= bar['bottom']
                       for bar in dims['bars'] for e in bar['controls']), f'FFT 分頁版面不符：{dims}'
            assert len(dims['ids']) == len(set(dims['ids'])), f'FFT 分頁版面不符：{dims}'
        # 疊圖色與圖例畫進畫布；切相位後隱藏，重新開檔後清空。
        c.js("document.querySelector('.fftpage [data-pin]').click()")
        c.wait("!document.querySelector('.fftpage [data-clear-overlay]').disabled", 20)
        c.js("document.querySelector('.fftpage [data-pin]').click()")
        c.wait("""(()=>{const c=document.querySelector('.fftpage canvas'),d=c.getContext('2d').getImageData(0,0,c.width,c.height).data;
            let pink=0,cyan=0;for(let i=0;i<d.length;i+=4){if(d[i]>200&&d[i+1]>40&&d[i+1]<150&&d[i+2]>120) pink++;
            if(d[i]<120&&d[i+1]>160&&d[i+2]>200) cyan++;}return pink>0&&cyan>0})()""", 20)
        c.js("""(()=>{const root=document.querySelector('.fftpage'), unit=[...root.querySelectorAll('select')].find(e=>[...e.options].some(o=>o.value==='Phase')); unit.dataset.previousUnit=unit.value; unit.value='Phase'; unit.dispatchEvent(new Event('change')); const box=root.querySelector('[aria-label="Unwrap"]'); box.checked=true; box.dispatchEvent(new Event('change'));})()""")
        c.wait(f"(async()=>{{{prep}return S.state.fftResult?.ok && S.state.fftResult.unit === '°'}})()", 20)
        assert c.js("document.querySelector('.fftpage [data-status]').textContent.includes('2 條疊圖')"), '切相位後應保留兩條疊圖狀態'
        assert c.js('''(()=>{const c=document.querySelector('.fftpage canvas'),d=c.getContext('2d').getImageData(0,0,c.width,c.height).data;
            for(let i=0;i<d.length;i+=4) if(d[i]>200&&d[i+1]>40&&d[i+1]<150&&d[i+2]>120) return false;return true})()'''), '切相位後不應繪出疊圖'
        c.js("""(()=>{const root=document.querySelector('.fftpage'), unit=[...root.querySelectorAll('select')].find(e=>e.dataset.previousUnit); unit.value=unit.dataset.previousUnit; unit.dispatchEvent(new Event('change'));})()""")
        old_gen = c.js(f"(async()=>{{{prep}return S.state.file.gen}})()")
        c.js(f"(async()=>{{{prep}S.command('file.open',{{path:S.state.file.path}})}})()")
        c.wait(f"(async()=>{{{prep}return S.state.file?.gen !== {old_gen} && !!S.state.file}})()", 20)
        assert c.js("document.querySelector('.fftpage [data-clear-overlay]').disabled"), '重新開檔後應清空疊圖'
    finally:
        c.js(f"(async()=>{{{prep}S.command('tab.select','analysis');S.command('fft.visible',false)}})()")
        c.send("Emulation.setDeviceMetricsOverride", width=original['width'], height=original['height'],
               deviceScaleFactor=original['dpr'], mobile=False)
        c.js(f"(async()=>{{{prep}S.command('layout.restore',{json.dumps(original['layoutPrefs'])})}})()")
        c.pump(0.2)
        c.js(f"if({json.dumps(chan_open)}&&document.querySelector('.chanbar__toggle').getAttribute('aria-expanded')!=='true') document.querySelector('.chanbar__toggle').click()")
        c.js(f"if(document.querySelector('.analysis__lowerbody').hidden!=={json.dumps(original['lowerHidden'])}) document.querySelector('.analysis__lowertoggle').click()")
        c.pump(0.2)
        c.js(f"(()=>{{const raw={json.dumps(original['layoutRaw'])};if(raw===null) localStorage.removeItem('scope.analysis.layout.v1');else localStorage.setItem('scope.analysis.layout.v1',raw)}})()")


if __name__ == '__main__':
    assert len(SIZES) == 4 and (1000, 700) in SIZES and min(h for _, h in SIZES) == 700, 'FFT 四尺寸清單須含 1000×700 且最低 700px'
    print('browser_fft_checks self-check OK（尺寸清單；實際版面待 browser_check）')
