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


def fallback_checks(c: Cdp, prep: str, path, data: str = '') -> None:
    """強制走替代浮層；只登記步驟，實際結果交主控驗收。"""
    def command(expr: str):
        return c.js('(async()=>{' + prep + expr + '})()')
    saved = command("return {width:innerWidth,height:innerHeight,scale:devicePixelRatio,file:S.state.file,storage:{...localStorage}};")
    script = c.send('Page.addScriptToEvaluateOnNewDocument', source="for(const k of ['popover','showPopover','hidePopover','togglePopover'])delete HTMLElement.prototype[k];for(const k of ['popoverTargetElement','popoverTargetAction'])delete HTMLButtonElement.prototype[k];window.__fallbackProbe=true;")['identifier']
    def viewport(w: int, h: int) -> None:
        c.send('Emulation.setDeviceMetricsOverride', width=w, height=h, deviceScaleFactor=1, mobile=False); c.pump(0.4)
    def key(name: str, code: int = 0) -> None:
        for typ in ('keyDown', 'keyUp'):
            c.send('Input.dispatchKeyEvent', type=typ, key=name, code=name, windowsVirtualKeyCode=code, **({'text':'\r'} if name == 'Enter' and typ == 'keyDown' else {}))
        c.pump(0.2)
    def load() -> None:
        c.wait("!!document.querySelector('[data-tab=analysis]')")
        c.js("document.querySelector('[data-tab=analysis]').click()"); c.pump(1.5)
        if saved['file']:
            command("S.command('file.open',{path:" + json.dumps(data or saved['file']['path']) + "});")
            try:
                c.wait('(async()=>{' + prep + "return !!S.state.file && S.state.channels.length>0})()")
            except TimeoutError:
                raise AssertionError('重載後開檔失敗：' + repr(data) + ' ' + json.dumps(c.js('(async()=>{' + prep + "return {file:S.state.file,ch:S.state.channels.length,err:S.state.error??null}})()"), ensure_ascii=False) + str(c.errors[-3:]))
        c.pump(1.5)
    buttons = "[...document.querySelectorAll('.analysis__toolbar > button,.analysis__fftbar button,.analysis__splitter--lower .results__menu button')].filter(b=>b.getBoundingClientRect().width)"
    def select(name: str) -> None:
        try:
            c.wait("!!" + buttons + ".find(b=>b.textContent.includes(" + json.dumps(name) + "))", 10)
        except TimeoutError:
            raise AssertionError(name + json.dumps(c.js("({tab:[...document.querySelectorAll('#tabs .tab')].map(t=>t.className+':'+t.textContent.trim()),tb:document.querySelector('.analysis__toolbar')?.innerText.slice(0,80),w:innerWidth,h:innerHeight,vis:!!document.querySelector('.analysis__toolbar')?.getBoundingClientRect().width})"), ensure_ascii=False))
        c.js("window.fb=" + buttons + ".find(b=>b.textContent.includes(" + json.dumps(name) + "));if(!fb)throw Error('找不到替代選單 " + name + "');window.fp=fb.nextElementSibling;")
    def opened(value: bool) -> None:
        assert c.js("fp.hasAttribute('data-open')===" + str(value).lower() + " && fp.hidden===" + str(not value).lower() + " && fb.getAttribute('aria-expanded')==='" + str(value).lower() + "'")
    rects = "(()=>{const t=document.querySelector('.analysis__toolbar');return [...t.querySelectorAll(':scope > label'),...[...t.querySelectorAll('button')].filter(b=>b.textContent.includes('游標置中')),t,...document.querySelector('.analysis__fftbar').children].filter(e=>!e.matches('.popmenu')).map(e=>{const r=e.getBoundingClientRect();return [r.x,r.y,r.width,r.height]})})()"
    try:
        c.send('Page.reload'); c.wait("window.__fallbackProbe===true"); load()
        assert c.js("!('popover' in HTMLElement.prototype)")
        viewport(1360, 860)
        command("S.command('layout.markerSide',false);S.command('layout.float',false);(await import('/js/analysis/fft_state.js')).getFftState({store:S}).setAnalysisOn(true);")
        c.js("document.querySelector('[data-pane=fft]')?.click()"); c.pump(0.4)
        command("if(document.querySelector('.analysis__lowerbody').hidden)S.command('layout.toggle','lower');"); c.js("document.querySelector('[data-result-tab=measure]')?.click()"); c.pump(0.4)
        for name in ('檔案', '分析', '更多…', '⋮'):
            select(name); before = c.js(rects); c.mouse('mouseMoved', 1, 1); c.js('fb.click()'); c.pump(0.2); opened(True)
            after = c.js(rects); assert len(before) == len(after) and all(abs(a-b)<=0.5 for aa,bb in zip(before,after) for a,b in zip(aa,bb)), (name,before,after)
            assert c.js("(()=>{const r=fp.getBoundingClientRect(),s=getComputedStyle(fp);return s.position==='fixed'&&+s.zIndex>=900&&r.width>0&&r.height>0&&r.left>=0&&r.top>=0&&r.right<=innerWidth&&r.bottom<=innerHeight&&(s.backdropFilter||s.webkitBackdropFilter).includes('blur')})()"), (name, 'L215')
            assert c.js("(()=>{const r=fp.getBoundingClientRect();for(let y=r.top+10;y<r.bottom-10;y+=9)for(let x=r.left+10;x<r.right-18;x+=9)if(!fp.contains(document.elementFromPoint(x,y)))return false;return true})()"), (name, 'L216')
            if name != '更多…':
                c.js("window.fi=fp.querySelector('[role=menuitem],label.check');fi.blur();fb.focus()"); c.pump(0.3)
                assert c.js("getComputedStyle(fi).borderTopWidth==='0px'&&['transparent','rgba(0, 0, 0, 0)'].includes(getComputedStyle(fi).backgroundColor)"), (name, 'L219', c.js("(()=>{const s=getComputedStyle(fi);return [fi.matches(':hover'),fi.matches(':focus-visible'),document.activeElement.tagName,s.backgroundColor,s.backgroundImage.slice(0,60),s.borderTopWidth]})()"))
                pt = c.js("(()=>{const r=fi.getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2}})()")
                c.mouse('mouseMoved', **pt); c.pump(0.15)
                assert c.js("!['transparent','rgba(0, 0, 0, 0)'].includes(getComputedStyle(fi).backgroundColor)")
            if name == '⋮':
                key('Tab',9); assert c.js("fp.contains(document.activeElement)&&document.activeElement.type==='checkbox'&&document.activeElement.matches(':focus-visible')&&getComputedStyle(document.activeElement).outlineStyle!=='none'")
            c.shot(path / ('menu_fallback_' + {'檔案':'file','分析':'analysis','更多…':'more','⋮':'columns'}[name] + '.png'))
            pt = c.js("(()=>{const r=document.querySelector('.analysis__main canvas').getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2}})()")
            c.mouse('mousePressed', **pt); c.mouse('mouseReleased', **pt); c.pump(0.2); opened(False)
            for _ in range(3):
                c.js('fb.click()'); opened(True); c.js('fb.click()'); opened(False)
            assert c.js("!document.querySelector('[data-open],.popover-fallback-stack')")
        select('檔案'); c.js('fb.focus()'); key('Enter',13); opened(True)
        for k,text in ((None,'比對…'),('ArrowUp','關閉'),('ArrowDown','比對…'),('End','關閉'),('Home','比對…')):
            if k: key(k, {'ArrowUp':38,'ArrowDown':40,'End':35,'Home':36}[k])
            assert c.js('document.activeElement.textContent===' + json.dumps(text))
        key('Escape',27); opened(False); assert c.js('document.activeElement===fb')
        for mode in ('float','drawer'):
            viewport(899,600); command("S.command('layout.float'," + str(mode=='float').lower() + ");" + ("S.command('layout.toggle','side');" if mode=='drawer' else ''))
            select('⋮'); c.js('fb.click()'); opened(True)
            assert c.js("(()=>{const r=fp.getBoundingClientRect();for(let y=r.top+10;y<r.bottom-10;y+=8)for(let x=r.left+10;x<r.right-18;x+=8)if(!fp.contains(document.elementFromPoint(x,y)))return false;return true})()"), mode
            c.shot(path / ('menu_fallback_' + mode + '.png')); key('Escape',27)
        viewport(1100,400); select('分析'); c.js('fb.click()'); opened(True)
        assert c.js("fp.getBoundingClientRect().bottom<=innerHeight&&getComputedStyle(fp).overflowY==='auto'&&fp.scrollHeight>=fp.clientHeight")
        c.shot(path / 'menu_fallback_short.png'); key('Escape',27)
        viewport(900,600); select('更多…'); c.js('fb.click()'); opened(True)
        assert c.js("(()=>{const a=[...fp.querySelectorAll('input,select')];return a.length===7&&a.every(e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&r.left>=0&&r.top>=0&&r.right<=innerWidth&&r.bottom<=innerHeight})})()")
        c.shot(path / 'menu_fallback_more_narrow.png')
        key('Escape',27); command("S.set({file:null},'program');"); select('檔案'); c.js("fb.click();window.fi=fp.querySelector('[role=menuitem]')"); opened(True)
        assert c.js('fi.disabled'); pt=c.js("(()=>{const r=fi.getBoundingClientRect();return {x:r.left+10,y:r.top+10}})()"); c.mouse('mouseMoved',**pt); c.pump(0.15)
        assert c.js("['transparent','rgba(0, 0, 0, 0)'].includes(getComputedStyle(fi).backgroundColor)")
    finally:
        c.send('Page.removeScriptToEvaluateOnNewDocument', identifier=script)
        c.js('localStorage.clear();Object.entries(' + json.dumps(saved['storage']) + ').forEach(([k,v])=>localStorage.setItem(k,v))')
        c.send('Page.reload'); c.wait("!window.__fallbackProbe && 'popover' in HTMLElement.prototype")
        c.send('Emulation.setDeviceMetricsOverride', width=saved['width'], height=saved['height'], deviceScaleFactor=saved['scale'], mobile=False); load()


if __name__ == '__main__':
    assert callable(menu_checks)
    print('browser_menu_checks self-check OK（實際瀏覽器步驟待主控執行）')
