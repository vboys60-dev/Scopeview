"""L8：欄位與工具列 Popover 的瀏覽器檢查。"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scope_tool.web.browser_check import Cdp


def menu_checks(c: Cdp, prep: str) -> None:
    """共用已開啟的波形；實際瀏覽器行為待主控驗證。"""
    def command(expr: str) -> None:
        c.js('(async()=>{' + prep + expr + '})()')
        c.pump(0.3)

    def viewport(width: int, height: int, scale: float = 1) -> None:
        c.send('Emulation.setDeviceMetricsOverride', width=width, height=height,
               deviceScaleFactor=scale, mobile=False)
        c.pump(0.4)

    def escape() -> None:
        for typ in ('keyDown', 'keyUp'):
            c.send('Input.dispatchKeyEvent', type=typ, key='Escape', code='Escape', windowsVirtualKeyCode=27)
        c.pump(0.2)

    def open_columns() -> None:
        c.js("document.querySelector('.results__menu button').click()")
        c.wait("document.querySelector('.results__choices').matches(':popover-open')")
        c.pump(0.2)

    def toolbar_menu(name: str) -> None:
        c.js("(()=>{const t=document.querySelector('.analysis__toolbar'),b=[...t.querySelectorAll('button')]"
             f".find(e=>e.textContent.includes({json.dumps(name)}));if(!b)throw Error('找不到選單');b.focus();b.click()}})()")
        c.wait("(()=>{const t=document.querySelector('.analysis__toolbar'),b=[...t.querySelectorAll('button')]"
               f".find(e=>e.textContent.includes({json.dumps(name)}));return b.nextElementSibling?.matches('.popmenu:popover-open')}})()")
        c.pump(0.2)

    saved = c.js('(async()=>{' + prep + """
        const L=await import('/js/analysis/layout.js'),F=await import('/js/analysis/fft_state.js');
        return {width:innerWidth,height:innerHeight,scale:devicePixelRatio,file:S.state.file,
          layout:L.loadPrefs(),raw:localStorage.getItem(L.STORAGE_KEY),
          floating:!document.querySelector('.analysis__float').hidden,
          floatRaw:localStorage.getItem('scope.analysis.float.v1'),
          fft:F.getFftState({store:S}).analysisOn};})()""")
    assert saved['file'], '需要先開啟波形檔'
    try:
        command("S.command('layout.float',false);S.command('layout.markerSide',false);"
                "S.command('fft.visible',false);S.command('layout.resize',{kind:'lower',value:200});")
        for width, height, mode in ((1360, 860, 'bottom'), (899, 600, 'drawer'), (1600, 900, 'right')):
            viewport(width, height)
            command("S.command('layout.markerSide'," + str(mode == 'right').lower() + ");")
            if mode == 'drawer':
                command("S.command('layout.toggle','side');")
                assert c.js("document.querySelector('.analysis').classList.contains('analysis--drawer')"), '抽屜未開啟'
            if mode == 'right':
                assert c.js("document.querySelector('.analysis').classList.contains('analysis--dock')"), '右側欄未啟用'
            open_columns()
            hits = c.js("""(()=>{const p=document.querySelector('.results__choices'),r=p.getBoundingClientRect();
                let count=0,miss=[];for(let y=r.top+3;y<r.bottom-3;y+=12)for(let x=r.left+3;x<r.right-3;x+=12){
                  count++;const e=document.elementFromPoint(x,y);
                  if(!p.contains(e))miss.push([x,y,e?e.tagName+'.'+e.className:null]);}
                return {count,miss,inside:r.left>=0&&r.top>=0&&r.right<=innerWidth&&r.bottom<=innerHeight};})()""")
            assert hits['count'] and hits['inside'] and not hits['miss'], (mode, hits)
            escape()
            assert c.js("!document.querySelector('.results__choices').matches(':popover-open')")
        command("S.command('layout.markerSide',false);S.command('layout.resize',{kind:'lower',value:200});")
        open_columns()
        # 真實情境：選單開著時在 splitter 上按下（popover 外）會被 light dismiss 關閉。
        sp = c.js("(()=>{const r=document.querySelector('.analysis__splitter--lower').getBoundingClientRect();return {x:r.left+4,y:r.top+r.height/2}})()")
        c.mouse('mousePressed', sp['x'], sp['y']); c.mouse('mouseReleased', sp['x'], sp['y'])
        c.pump(0.2)
        assert c.js("!document.querySelector('.results__choices').matches(':popover-open')"), 'splitter 按下未關選單'
        open_columns()
        point = c.js("(()=>{const r=document.querySelector('.analysis__main canvas').getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2}})()")
        c.mouse('mousePressed', point['x'], point['y']); c.mouse('mouseReleased', point['x'], point['y'])
        c.pump(0.2)
        assert c.js("!document.querySelector('.results__choices').matches(':popover-open')")

        # 未開檔項目全 disabled：略過（會清空量測且不易還原），由 T5 的 Node 驗收涵蓋。
        command("(await import('/js/analysis/fft_state.js')).getFftState({store:S}).setAnalysisOn(true);")
        c.js("document.querySelectorAll(':popover-open').forEach(p=>p.hidePopover())")
        for width, height in ((1400, 900), (1100, 700), (900, 600)):
            viewport(width, height)
            dims = c.js("""(()=>{const t=document.querySelector('.analysis__toolbar');return {
                height:t.getBoundingClientRect().height,doc:document.documentElement.scrollWidth-document.documentElement.clientWidth};})()""")
            assert dims['height'] <= 50 and dims['doc'] <= 0, (width, dims)
            c.js("document.querySelector('[data-pane=fft]')?.click()"); c.pump(0.3)
            c.js("[...document.querySelectorAll('.analysis__fftbar button')].find(b=>b.textContent==='更多…').click()")
            c.wait("!!document.querySelector('.analysis__fftbar .popmenu:popover-open')")
            assert c.js("(()=>{const a=[...document.querySelectorAll('.analysis__fftbar .popmenu:popover-open select, .analysis__fftbar .popmenu:popover-open input')];return a.length===7&&a.every(e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&r.left>=0&&r.top>=0&&r.right<=innerWidth&&r.bottom<=innerHeight})})()"), width
            escape()
            assert c.js("!document.querySelector('.analysis__fftbar .popmenu:popover-open')")
            for name in ('檔案', '分析'):
                toolbar_menu(name)
                bounds = c.js("""(()=>{const p=document.querySelector('.analysis__toolbar .popmenu:popover-open');
                    const a=[...p.querySelectorAll('button,label')];return a.length>0&&a.every(e=>{
                      const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&r.left>=0&&r.top>=0&&r.right<=innerWidth&&r.bottom<=innerHeight;});})()""")
                assert bounds, (width, name)
                escape()
                assert c.js("(()=>{const t=document.querySelector('.analysis__toolbar'),b=[...t.querySelectorAll('button')]"
                            f".find(e=>e.textContent.includes({json.dumps(name)}));return !b.nextElementSibling.matches(':popover-open')&&document.activeElement===b}})()"), name
        viewport(1360, 860)
        # 以鍵盤開啟並驗證選單焦點及循環；方向鍵使用可冒泡事件。
        c.js("[...document.querySelectorAll('.analysis__toolbar > button')].find(b=>b.textContent==='檔案 ▾').focus()")
        for typ in ('keyDown', 'keyUp'):
            c.send('Input.dispatchKeyEvent', type=typ, key='Enter', code='Enter', windowsVirtualKeyCode=13, **({'text': '\r'} if typ == 'keyDown' else {}))
        c.wait("!!document.querySelector('.analysis__toolbar [role=menu]:popover-open')")
        c.pump(0.2)
        assert c.js("document.activeElement.textContent==='比對…'"), 'L109 ' + c.js("document.activeElement.outerHTML.slice(0,80)")
        def menu_key(key: str) -> None:
            c.js("document.activeElement.dispatchEvent(new KeyboardEvent('keydown',{key:" + json.dumps(key) + ",bubbles:true,cancelable:true}))")
            c.pump(0.1)
        menu_key('ArrowUp'); assert c.js("document.activeElement.textContent==='關閉'"), 'L113'
        menu_key('ArrowDown'); assert c.js("document.activeElement.textContent==='比對…'"), 'L114'
        menu_key('End'); assert c.js("document.activeElement.textContent==='關閉'"), 'L115'
        menu_key('Home'); assert c.js("document.activeElement.textContent==='比對…'"), 'L116'
        menu_key('Escape'); c.pump(0.2)
        assert c.js("document.activeElement.textContent==='檔案 ▾' && !document.querySelector('.analysis__toolbar [role=menu]:popover-open')"), 'L118'
        # 暫時只切換檔案狀態，完成後立即還原。
        try:
            command("S.set({file:null},'program');")
            toolbar_menu('檔案')
            assert c.js("[...document.querySelectorAll('.analysis__toolbar [role=menu]:popover-open [role=menuitem]')].every(e=>e.disabled)"), 'L123'
            c.js("document.querySelector('.analysis__toolbar [role=menu]:popover-open').dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowDown',bubbles:true,cancelable:true}))")
            escape()
        finally:
            command("S.set({file:" + json.dumps(saved['file']) + "},'program');")
        c.js("[...document.querySelectorAll('.analysis__fftbar button')].find(b=>b.textContent==='更多…').click()")
        c.wait("!!document.querySelector('.analysis__fftbar .popmenu:popover-open select')")
        assert c.js("(()=>{const s=document.querySelector('.analysis__fftbar .popmenu:popover-open select');s.focus();return s.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowDown',bubbles:true,cancelable:true}))})()"), 'L130'
        escape()
        toolbar_menu('檔案')
        c.js("[...document.querySelectorAll('.analysis__toolbar .popmenu:popover-open button')].find(b=>b.textContent.includes('檔案資訊')).click()")
        c.wait("document.querySelector('dialog[open] .dlg__title')?.textContent.includes('檔案資訊')")
        assert c.js("!document.querySelector('.analysis__toolbar .popmenu:popover-open')"), 'L135'
        c.js("document.querySelector('dialog[open] .dlg__actions button').click()")
        toolbar_menu('分析')
        assert c.js("[...document.querySelectorAll('.analysis__toolbar .popmenu:popover-open button')].map(e=>e.textContent)") == ['FFT 頻譜 ↗','Math…','分開堆疊','疊圖（自動縮放）','1 格','2 格','4 格','8 格']
        assert c.js("!document.querySelector('.analysis__toolbar .popmenu:popover-open input')")
        escape()
        original = c.js('(async()=>{' + prep + "return S.get().channels})()")
        try:
            command("S.set({channels:S.get().channels.map(c=>({...c,visible:true,vmin:-1,vmax:1,scale:1,position:0}))},'program');")
            prior = c.js('(async()=>{' + prep + "return S.get().channels.map(({name,scale,position})=>({name,scale,position}))})()")
            toolbar_menu('分析')
            c.js("[...document.querySelectorAll('.analysis__toolbar .popmenu:popover-open button')].find(b=>b.textContent==='分開堆疊').click()")
            stacked = c.js('(async()=>{' + prep + "return S.get().channels.map(c=>c.position)})()")
            assert len(set(stacked)) == len(stacked) and all(-5 <= p <= 5 for p in stacked), stacked
            command("S.command('view.undo');")
            assert c.js('(async()=>{' + prep + "return S.get().channels.map(({name,scale,position})=>({name,scale,position}))})()") == prior
            toolbar_menu('分析')
            c.js("[...document.querySelectorAll('.analysis__toolbar .popmenu:popover-open button')].find(b=>b.textContent==='分開堆疊').click()")
            toolbar_menu('分析')
            c.js("[...document.querySelectorAll('.analysis__toolbar .popmenu:popover-open button')].find(b=>b.textContent==='疊圖（自動縮放）').click()")
            assert c.js('(async()=>{' + prep + "const M=await import('/js/analysis/scales.js');return S.get().channels.every(c=>{const [s,p]=M.autoScale(c.vmin,c.vmax,c.unit);return c.scale===s&&c.position===p})})()")
            command("S.command('view.undo');")
            assert c.js('(async()=>{' + prep + "return S.get().channels.map(c=>c.position)})()") == stacked
        finally:
            command("S.set({channels:" + json.dumps(original) + "},'program');")
        before = c.js('(async()=>{' + prep + "return (await import('/js/analysis/fft_state.js')).getFftState({store:S}).analysisOn})()")
        assert c.js("(()=>{const t=document.querySelector('.analysis__toolbar'),l=[...t.querySelectorAll(':scope > label')].find(e=>e.textContent.includes('FFT 計算'));return !!l&&l.previousElementSibling?.classList.contains('popmenu')&&l.nextElementSibling?.textContent.includes('Marker')})()")
        c.js("[...document.querySelectorAll('.analysis__toolbar > label')].find(e=>e.textContent.includes('FFT 計算')).querySelector('input').click()")
        assert c.js('(async()=>{' + prep + "return (await import('/js/analysis/fft_state.js')).getFftState({store:S}).analysisOn})()") != before
    finally:
        c.js("document.querySelectorAll(':popover-open').forEach(p=>p.hidePopover());document.querySelector('dialog[open] .dlg__actions button')?.click()")
        if c.js("document.querySelector('.analysis').classList.contains('analysis--drawer')"):
            command("S.command('layout.toggle','side');")
        c.send('Emulation.clearDeviceMetricsOverride')
        viewport(1400, 900)
        command("(await import('/js/analysis/fft_state.js')).getFftState({store:S}).setAnalysisOn(" + str(saved['fft']).lower() + ");"
                "S.command('layout.restore'," + json.dumps(saved['layout']) + ");"
                "S.command('layout.float'," + str(saved['floating']).lower() + ");")
        c.js("(()=>{const k='scope.analysis.layout.v1',v=" + json.dumps(saved['raw']) + ";if(v===null)localStorage.removeItem(k);else localStorage.setItem(k,v)})()")
        c.js("(()=>{const k='scope.analysis.float.v1',v=" + json.dumps(saved['floatRaw']) + ";if(v===null)localStorage.removeItem(k);else localStorage.setItem(k,v)})()")


if __name__ == '__main__':
    assert callable(menu_checks)
    print('browser_menu_checks self-check OK（實際瀏覽器步驟待主控執行）')
