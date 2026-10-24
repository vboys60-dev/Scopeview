"""L8：浮動 B 區的真實拖曳、縮放、停靠、窄版及事件隔離。"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scope_tool.web.browser_check import Cdp


def float_panel(c: Cdp, prep: str) -> None:
    """由 browser_check 共用已開檔資料；不自行啟動 localhost。"""
    def command(expr: str) -> None:
        c.js('(async()=>{' + prep + expr + '})()')
        c.pump(0.2)

    def viewport(width: int, height: int) -> None:
        c.send('Emulation.setDeviceMetricsOverride', width=width, height=height,
               deviceScaleFactor=1, mobile=False)
        c.pump(0.3)

    def rect(selector: str) -> dict:
        return c.js(f"(()=>{{const r=document.querySelector('{selector}').getBoundingClientRect();"
                    "return {x:r.x,y:r.y,width:r.width,height:r.height}})()")

    def drag(x: float, y: float, dx: float, dy: float) -> None:
        c.mouse('mousePressed', x, y)
        for i in range(1, 6):
            c.mouse('mouseMoved', x + dx * i / 5, y + dy * i / 5, buttons=1)
        c.mouse('mouseReleased', x + dx, y + dy)
        c.pump(0.3)

    def press_key(name: str, modifiers: int = 0) -> None:
        for typ in ('keyDown', 'keyUp'):
            c.send('Input.dispatchKeyEvent', type=typ, key=name, modifiers=modifiers)

    def preference() -> str:
        return c.js("localStorage.getItem('scope.analysis.float.v1')")

    saved = c.js('(async()=>{' + prep + "return {file:S.state.file,mode:S.state.markerMode}})()")
    try:
        viewport(1400, 900)
        command("S.command('layout.float',false);S.command('fft.visible',false);"
                "S.command('layout.resize',{kind:'lower',value:200});")
        c.js("""(()=>{const q=s=>document.querySelector(s);window.__floatNodes={
            body:q('.analysis__lowerbody'),tabs:q('.analysis__resultTabs'),actions:q('.results__actions'),
            cursor:q('.analysis__cursors'),input:q('.cursors__field--x input'),
            columns:q('.results__table tr').children.length};q('[data-result-tab=cursor]').click()})()""")
        c.pump(0.2)
        command("window.__undoView={...S.state.view};const v=S.state.view,dt=(v.t1-v.t0)*0.05;"
                "S.command('viewport.intent',{t0:v.t0+dt,t1:v.t1+dt});")
        before = rect('.analysis__main')
        c.js("document.querySelector('.analysis__floatLaunch').click()")
        c.pump(0.3)
        dims = c.js("""(()=>{const p=document.querySelector('.analysis__float'),n=window.__floatNodes;
            return {dialog:p.getAttribute('role'),modal:p.getAttribute('aria-modal'),
              same:p.contains(n.body)&&p.contains(n.tabs)&&p.contains(n.actions)&&p.contains(n.input),
              selected:p.querySelector('[data-result-tab=cursor]').getAttribute('aria-selected'),
              lower:document.querySelector('.analysis > .analysis__lower').getBoundingClientRect().height,
              marker:p.querySelector('.cursor-results__table').getBoundingClientRect().width,
              cursor:!p.querySelector('.analysis__cursors').hidden,
              home:document.querySelector('.analysis__floatHome').innerText}})()""")
        assert dims['same'] and dims['dialog'] == 'dialog' and dims['modal'] == 'false', dims
        assert dims['selected'] == 'true' and dims['cursor'] and dims['marker'] > 0, dims
        assert dims['lower'] == 28 and '已浮動' in dims['home'], dims
        assert rect('.analysis__main')['height'] > before['height'] + 100
        assert c.js("document.activeElement===document.querySelector('.analysis__floatTitle')")
        assert c.js("document.querySelector('.analysis__splitter--lower').tabIndex===-1&&document.querySelector('.analysis__splitter--lower').getAttribute('aria-disabled')==='true'")
        # 以真實滑鼠移動面板；游標與 view 均不得受影響。
        command("window.__floatData=JSON.stringify({view:S.state.view,cursors:S.state.cursors});")
        a = rect('.analysis__float')
        drag(a['x'] + 80, a['y'] + 14, 70, 60)
        b = rect('.analysis__float')
        assert abs(b['x'] - a['x'] - 70) < 2 and abs(b['y'] - a['y'] - 60) < 2, (a, b)
        command("if(window.__floatData!==JSON.stringify({view:S.state.view,cursors:S.state.cursors}))throw Error('浮動拖曳誤觸圖區');")
        press_key('z', 2)
        command("if(JSON.stringify(S.state.view)!==JSON.stringify(window.__undoView))throw Error('拖曳後 Ctrl+Z 失效');")
        # Space 在主圖按下，點標題後放開，再以框選模式的滑鼠樣式確認已解除暫時平移。
        command("S.command('view.mode','zoom');")
        c.js("document.querySelector('.analysis__main canvas').focus()")
        c.send('Input.dispatchKeyEvent', type='keyDown', key=' ', code='Space')
        c.mouse('mousePressed', b['x'] + 80, b['y'] + 14)
        c.mouse('mouseReleased', b['x'] + 80, b['y'] + 14)
        c.send('Input.dispatchKeyEvent', type='keyUp', key=' ', code='Space')
        main = rect('.analysis__main canvas')
        c.mouse('mouseMoved', main['x'] + main['width'] * 0.65, main['y'] + main['height'] * 0.6)
        assert c.js("document.querySelector('.analysis__main canvas').style.cursor==='crosshair'")
        command("S.command('view.mode','pan');")
        # 中斷拖曳的各路徑都釋放 capture、還原顯示，且不寫偏好。
        for stop in ('pointercancel', 'lostpointercapture', 'blur', 'resize', 'tab'):
            stored = preference()
            c.mouse('mousePressed', b['x'] + 80, b['y'] + 14)
            c.mouse('mouseMoved', b['x'] + 100, b['y'] + 34, buttons=1)
            assert preference() == stored
            if stop == 'tab':
                command("S.command('tab.activated','capture');")
            else:
                target = 'window' if stop in ('blur', 'resize') else "document.querySelector('.analysis__float')"
                c.js(f"{target}.dispatchEvent(new Event('{stop}'))")
            c.mouse('mouseReleased', b['x'] + 100, b['y'] + 34)
            assert preference() == stored and rect('.analysis__float') == b
        # 按鈕上按下不能啟動拖曳；雙擊收折按鈕不能停靠。
        c.js('''(()=>{const p=document.querySelector('.analysis__floatTitle'),b=p.querySelectorAll('button')[1];
            b.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,button:0,pointerId:77}));
            if(p.hasPointerCapture(77))throw Error('按鈕誤啟拖曳');
            b.dispatchEvent(new MouseEvent('dblclick',{bubbles:true}));})()''')
        assert not c.js("document.querySelector('.analysis__float').hidden")
        # 真實右下角、左邊緣縮放。
        drag(b['x'] + b['width'] - 3, b['y'] + b['height'] - 3, -100, 50)
        d = rect('.analysis__float')
        assert abs(d['width'] - b['width'] + 100) < 2 and abs(d['height'] - b['height'] - 50) < 2, (b, d)
        drag(d['x'] + 2, d['y'] + 70, 30, 0)
        e = rect('.analysis__float')
        assert abs(e['width'] - d['width'] + 30) < 2, (d, e)
        # 鍵盤移動／縮放、收折及 Esc 保持浮動。
        c.js("document.querySelector('.analysis__floatTitle').focus()")
        for key, modifiers in [('ArrowLeft', 8), ('ArrowDown', 1), ('Escape', 0)]:
            c.send('Input.dispatchKeyEvent', type='keyDown', key=key, modifiers=modifiers)
            c.send('Input.dispatchKeyEvent', type='keyUp', key=key, modifiers=modifiers)
        c.pump(0.2)
        k = rect('.analysis__float')
        assert abs(k['x'] - e['x'] + 50) < 2 and abs(k['height'] - e['height'] - 10) < 2, (e, k)
        unchanged = rect('.analysis__float')
        press_key('ArrowRight', 2)
        assert rect('.analysis__float') == unchanged
        command("S.command('layout.float.collapse');")
        folded_pref = preference()
        press_key('ArrowDown', 1)
        f = rect('.analysis__float')
        drag(f['x'] + f['width'] - 3, f['y'] + 24, -50, 50)
        assert preference() == folded_pref
        assert rect('.analysis__float')['height'] == 28
        command("S.command('layout.float.collapse');")
        # 量測預設全欄位；最小面板也不能撐破容器，字體不可縮小。
        c.js("document.querySelector('.analysis__float [data-result-tab=measure]').click()")
        command("S.command('layout.float.rect',{width:360,height:160});")
        bounds = c.js("""(()=>{const p=document.querySelector('.analysis__float'),r=p.getBoundingClientRect(),
            t=p.querySelector('.results__table'),b=p.querySelector('.analysis__lowerbody');
            const visible=[...p.querySelectorAll('button,summary,th,td,label,input,span')].filter(e=>e.getClientRects().length);
            return {columns:t.rows[0].cells.length,font:Math.min(...visible.map(e=>parseFloat(getComputedStyle(e).fontSize))),
              overflow:p.scrollWidth-p.clientWidth,body:b.scrollWidth-b.clientWidth,table:t.getBoundingClientRect().right<=r.right}})()""")
        assert bounds['columns'] == 9 and bounds['font'] >= 12.5, bounds
        assert bounds['overflow'] <= 1 and bounds['body'] <= 1 and bounds['table'], bounds
        # 面板要求 y=0 時夾在分析頁頂端，欄位選單改往下開且完整可見。
        command("S.command('layout.float.rect',{y:0});")
        c.js("document.querySelector('.analysis__float .results__menu').open=true")
        c.pump(0.2)
        choices = rect('.results__choices')
        assert choices['y'] >= 0 and choices['y'] + choices['height'] <= 900, choices
        assert choices['x'] >= 0 and choices['x'] + choices['width'] <= 1400, choices
        assert c.js("document.querySelector('.analysis__float').getBoundingClientRect().top>=document.querySelector('#tab-analysis').getBoundingClientRect().top")
        c.js("document.querySelector('.results__menu').open=false")
        # 分頁與關檔不改浮動偏好；隱藏分析頁後不得留下浮動框。
        c.js("document.querySelector('[data-tab=capture]').click()")
        c.pump(0.2)
        assert c.js("document.querySelector('.analysis__float').getClientRects().length===0")
        c.js("document.querySelector('[data-tab=analysis]').click()")
        command("S.set({file:null},'program');")
        assert c.js("!document.querySelector('.analysis__float').hidden")
        command('S.set({file:' + json.dumps(saved['file']) + "},'program');")
        # 視窗縮小後全框夾回；窄版自動停靠且浮動按鈕禁用。
        command("S.command('layout.float.rect',{x:800,y:500,width:550,height:350});")
        original = rect('.analysis__float')
        original_pref = preference()
        viewport(1000, 600)
        clamped = rect('.analysis__float')
        assert clamped['x'] >= 0 and clamped['y'] >= 0, clamped
        assert clamped['x'] + clamped['width'] <= 1001 and clamped['y'] + clamped['height'] <= 601, clamped
        assert preference() == original_pref
        viewport(899, 600)
        assert c.js("document.querySelector('.analysis__float').hidden&&document.querySelector('.analysis__floatLaunch').disabled")
        assert preference() == original_pref
        viewport(1400, 900)
        assert c.js("!document.querySelector('.analysis__float').hidden&&!document.querySelector('.analysis__floatLaunch').disabled")
        assert rect('.analysis__float') == original and preference() == original_pref
        # 獨立瀏覽器 realm 從窄版啟動，實際使用 localStorage 的既存偏好。
        c.js("""(()=>{const f=document.createElement('iframe');f.id='float-startup-check';
            f.style.cssText='position:fixed;width:899px;height:600px;visibility:hidden;border:0';
            f.srcdoc=`<script type="module">
            import {mountFloat} from '/js/analysis/floatpanel.js';
            import {createStore} from '/js/analysis/store.js';
            const page=document.createElement('div'),lower=document.createElement('div'),header=document.createElement('div');
            document.body.append(page);page.append(lower);lower.append(header);
            window.ctl=mountFloat(page,{store:createStore(),lower,header,body:document.createElement('div'),
              tabs:document.createElement('div'),actions:document.createElement('div'),schedule(){}});
            window.ready=true;</script>`;document.body.append(f);})()""")
        c.wait("document.querySelector('#float-startup-check').contentWindow.ready")
        assert c.js("!document.querySelector('#float-startup-check').contentWindow.ctl.floating")
        assert preference() == original_pref
        c.js("document.querySelector('#float-startup-check').style.width='1400px'")
        c.wait("document.querySelector('#float-startup-check').contentWindow.ctl.floating")
        assert preference() == original_pref
        c.js("document.querySelector('#float-startup-check').remove()")
        # 停靠仍是原節點；再浮動後用真實雙擊停靠。
        command("S.command('layout.float',true);")
        c.js("document.querySelector('.analysis__floatTitle button').click()")
        c.pump(0.2)
        assert c.js("""(()=>{const n=window.__floatNodes,h=document.querySelector('.analysis__splitter--lower');
            return h.contains(n.tabs)&&h.contains(n.actions)&&n.body.parentNode===document.querySelector('.analysis > .analysis__lower')})()""")
        command("S.command('layout.float',true);")
        t = rect('.analysis__floatTitle')
        for typ in ('mousePressed', 'mouseReleased'):
            c.send('Input.dispatchMouseEvent', type=typ, x=t['x'] + 80, y=t['y'] + 14,
                   button='left', clickCount=2)
        c.pump(0.2)
        assert c.js("document.querySelector('.analysis__float').hidden")
        assert not c.errors, c.errors
    finally:
        viewport(1400, 900)
        command("S.command('layout.float',false);S.command('layout.reset','lower');S.command('fft.visible',true);")
        c.js("document.querySelector('#float-startup-check')?.remove()")
        c.js('delete window.__floatNodes;delete window.__floatData;delete window.__undoView')
        c.pump(0.6)


if __name__ == '__main__':
    assert callable(float_panel)
    print('browser_float_checks self-check OK（實際瀏覽器步驟由 browser_check 執行）')
