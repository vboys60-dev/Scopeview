"""L8：分割格線幾何與命中檢查；實際瀏覽器步驟由主控執行。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from scope_tool.web.browser_check import Cdp


def grid_checks(c: Cdp, prep: str, out: Path) -> None:
    """共用已開啟的波形；步驟待主控驗收，結束時還原格線、偏好與尺寸。"""
    def command(expr: str) -> None:
        c.js('(async()=>{' + prep + expr + '})()')
        c.pump(0.4)

    def geometry() -> dict:
        return c.js("""(()=>{const cv=[...document.querySelectorAll('canvas')].find(e=>e.hitChannel);
          const r=cv.gridRect();return {t:r.t,h:r.h,rows:r.rows};})()""")

    def state(expr: str):
        return c.js('(async()=>{' + prep + 'return ' + expr + '})()')

    def drag(start: dict, end: dict, hold: Callable[[], None] | None = None, esc: bool = False) -> None:
        c.mouse('mousePressed', start['x'], start['y'])
        for i in range(1, 9):
            c.mouse('mouseMoved', start['x'] + (end['x'] - start['x']) * i / 8,
                    start['y'] + (end['y'] - start['y']) * i / 8, buttons=1)
        if hold: hold()
        if esc:
            for typ in ('keyDown', 'keyUp'): c.send('Input.dispatchKeyEvent', type=typ, key='Escape', code='Escape', windowsVirtualKeyCode=27)
        c.mouse('mouseReleased', end['x'], end['y'])
        c.pump(0.4)
        assert not c.errors, c.errors

    def plot_point(index: int, fraction: float) -> dict:
        return c.js("""(()=>{const cv=[...document.querySelectorAll('canvas')].find(e=>e.hitChannel);
          const box=cv.getBoundingClientRect(),r=cv.gridRect().rows[""" + str(index) + """];
          return {x:box.left+r.l+r.w*0.43,y:box.top+r.t+r.h*""" + str(fraction) + """};})()""")

    def analysis_menu() -> None:
        c.js("[...document.querySelectorAll('.analysis__toolbar > button')].find(e=>e.textContent==='分析 ▾').click()")
        c.wait("!!document.querySelector('.analysis__toolbar [role=menu]:popover-open')")

    def menu_click(title: str) -> None:
        analysis_menu()
        c.js("[...document.querySelectorAll('.analysis__toolbar .popmenu:popover-open button')].find(e=>e.textContent===" + json.dumps(title) + ").click()")
        c.pump(0.4)

    size = c.js('({width:innerWidth,height:innerHeight,scale:devicePixelRatio})')
    saved = c.js('(async()=>{' + prep + """
        return {grids:S.get().grids,channels:S.get().channels,view:S.get().view,cursors:S.get().cursors,
          selected:S.get().selected,measurements:S.get().measurements,markerMode:S.get().markerMode,
          markerResult:S.get().markerResult,source:document.querySelector('.cursors__source')?.value,
          mode:document.querySelector('.analysis__hmodes>button[aria-pressed="true"]')?.title==='框選放大'?'zoom':'pan',
          kind:document.querySelector('[data-zoom-kind][aria-pressed="true"]')?.dataset.zoomKind??'horizontal',
          raw:localStorage.getItem('scope.analysis.grids.v1')};})()""")
    try:
        # 格數選單：文字不含偽元素勾號，一次點擊只新增一筆歷史。
        command("S.set({grids:{n:1,assign:{}}},'program');")
        assert c.js("[...document.querySelectorAll('.chip__grid')].every(e=>e.hidden)")
        analysis_menu()
        assert c.js("[...document.querySelectorAll('.analysis__toolbar .popmenu:popover-open button')].map(e=>e.textContent)") == [
            'FFT 頻譜 ↗', 'Math…', '分開堆疊', '疊圖（自動縮放）', '1 格', '2 格', '4 格', '8 格']
        c.js("[...document.querySelectorAll('.analysis__toolbar .popmenu:popover-open button')].find(e=>e.textContent==='4 格').click()")
        c.pump(0.4)
        assert state('S.get().grids.n') == 4
        assert c.js("[...document.querySelectorAll('.analysis__toolbar [aria-current=true]')].map(e=>e.textContent)") == ['4 格']
        command("S.command('view.undo');")
        assert state('S.get().grids') == {'n': 1, 'assign': {}}
        assert c.js("[...document.querySelectorAll('.analysis__toolbar [aria-current=true]')].map(e=>e.textContent)") == ['1 格']
        menu_click('2 格')
        assert c.js("[...document.querySelectorAll('.chip__grid')].every(e=>!e.hidden&&e.options.length===2)")
        before = state('S.get().grids')
        command("const el=document.querySelector('[data-channel=CHAN1] .chip__grid');el.value='1';el.dispatchEvent(new Event('change',{bubbles:true}));")
        assert state('S.get().grids.assign.CHAN1') == 1
        assert 'CHAN1' in geometry()['rows'][1]['names']
        command("S.command('view.undo');")
        assert state('S.get().grids') == before
        assert 'CHAN1' in geometry()['rows'][0]['names']
        # 同格與單格皆用既有 W7 的對稱範圍，檢查各位置及一步復原。
        for n in (2, 1):
            command("S.set({grids:{n:" + str(n) + ",assign:{CHAN1:0,CHAN2:0}},channels:S.get().channels.map(ch=>"
                    "({...ch,visible:" + ("true" if n == 1 else "['CHAN1','CHAN2'].includes(ch.name)") + ",vmin:-1,vmax:1,scale:1,position:0}))},'program');")
            before = state('S.get().channels')
            menu_click('分開堆疊')
            positions = state('S.get().channels.filter(ch=>ch.visible).map(ch=>ch.position)')
            assert len(positions) == sum(ch['visible'] for ch in before) and len(set(positions)) == len(positions) and all(-5 <= p <= 5 for p in positions), positions
            command("S.command('view.undo');")
            assert state('S.get().channels') == before
        command("S.set({channels:" + json.dumps(saved['channels']) + "},'program');")
        command("const {autoScale}=await import('/js/analysis/scales.js');"
                "S.set({channels:S.get().channels.map(ch=>{const [scale,position]=Number.isFinite(ch.vmin)&&Number.isFinite(ch.vmax)?autoScale(ch.vmin,ch.vmax,ch.unit):[1,0];"
                "return {...ch,scale,position}}),grids:{n:2,assign:{}}},'user');")
        c.wait("[...document.querySelectorAll('canvas')].find(e=>e.hitChannel)?.dataset.pending!== '1'")
        g = geometry()
        assert len(g['rows']) == 2, g
        a, b = g['rows']
        assert abs(a['t'] + a['h'] + 4 - b['t']) <= 0.5, g
        names = [ch['name'] for ch in saved['channels']]
        assert len(names) >= 2 and names[0] in a['names'] and names[1] in b['names'], g
        assert c.js("JSON.parse(localStorage.getItem('scope.analysis.grids.v1')).n") == 2
        hits = c.js("""(()=>{const cv=[...document.querySelectorAll('canvas')].find(e=>e.hitChannel),box=cv.getBoundingClientRect();
          return cv.gridRect().rows.map(r=>{let hit=0,bad=[];
            for(let y=r.t;y<=r.t+r.h;y+=2)for(let x=r.l;x<=r.l+r.w;x+=4){
              const name=cv.hitChannel(box.left+x,box.top+y);
              if(name!==null){hit++;if(!r.names.includes(name))bad.push(name);}}
            return {hit,bad};});})()""")
        visible = {ch['name'] for ch in saved['channels'] if ch['visible']}
        for row, result in zip(g['rows'], hits):
            assert not result['bad'], result
            if visible.intersection(row['names']):
                assert result['hit'] > 0, (row, result)
        # 固定兩個來源的格位，逐一檢查拖曳與一次復原。
        command("S.set({grids:{n:2,assign:{CHAN1:0,CHAN2:1}},markerMode:null,"
                "channels:S.get().channels.map(ch=>({...ch,visible:['CHAN1','CHAN2'].includes(ch.name)}))},'user');"
                "S.command('view.mode','pan');")
        assert state("S.get().channels.filter(ch=>ch.visible).map(ch=>ch.name)") == ['CHAN1', 'CHAN2']
        g = geometry()
        start = state("""(await (async()=>{const {channelHandles}=await import('/js/analysis/handles.js');
          const cv=[...document.querySelectorAll('canvas')].find(e=>e.hitChannel),box=cv.getBoundingClientRect();
          const h=channelHandles(S.get().channels,cv.gridRect()).find(h=>h.name==='CHAN2');
          return {x:box.left+h.x+h.w/2,y:box.top+h.y+h.h/2};})())""")
        before = state("S.get().channels.find(ch=>ch.name==='CHAN2').position")
        drag(start, {**start, 'y': start['y'] + 20})
        after = state("S.get().channels.find(ch=>ch.name==='CHAN2').position")
        assert abs(after - before + 20 * 10 / g['rows'][1]['h']) <= 0.05, (before, after, g)


        # 真拖跨格：先還原中途位置、只預覽；格位與位置共用一筆歷史。
        command("S.updateChannel('CHAN2',{position:0},'user');")
        snapshot = "({grids:S.get().grids,channels:S.get().channels})"
        before_drop = state(snapshot)
        def handle_point() -> dict:
            return state("""(await (async()=>{const {channelHandles}=await import('/js/analysis/handles.js');
              const cv=[...document.querySelectorAll('canvas')].find(e=>e.hitChannel),box=cv.getBoundingClientRect();
              const h=channelHandles(S.get().channels,cv.gridRect()).find(h=>h.name==='CHAN2');
              return {x:box.left+h.x+h.w/2,y:box.top+h.y+h.h/2+6};})())""")
        brightness = """(()=>{const cv=[...document.querySelectorAll('canvas')].find(e=>e.hitChannel),r=cv.gridRect().rows[0],k=cv.width/cv.getBoundingClientRect().width;
          const a=cv.getContext('2d').getImageData(Math.ceil(r.l*k),Math.ceil(r.t*k),Math.floor(r.w*k)-1,Math.floor(r.h*k)-1).data;
          let sum=0;for(let i=0;i<a.length;i+=4)sum+=a[i]+a[i+1]+a[i+2];return sum/(a.length/4*3)})()"""
        light = c.js(brightness)
        def preview() -> None:
            c.pump(0.2)
            assert state(snapshot) == before_drop and abs(c.js(brightness) - light) > 2
            assert not c.errors, c.errors
        drag(handle_point(), plot_point(0, 0.5), hold=preview)
        dropped = state(snapshot)
        assert dropped['grids']['assign']['CHAN2'] == 0 and 'CHAN2' in geometry()['rows'][0]['names'] and 'CHAN2' not in geometry()['rows'][1]['names']
        assert abs(next(ch['position'] for ch in dropped['channels'] if ch['name'] == 'CHAN2') - 60 / g['rows'][0]['h']) < 0.1
        command("S.command('view.undo');"); assert state(snapshot) == before_drop and not c.errors
        command("S.command('view.redo');"); assert state(snapshot) == dropped and not c.errors
        command("S.command('view.undo');"); assert state(snapshot) == before_drop and not c.errors
        drag(handle_point(), plot_point(0, 0.5), esc=True)
        assert state(snapshot) == before_drop and not c.errors
        drag(handle_point(), plot_point(0, -0.2))
        assert state(snapshot) == before_drop and not c.errors

        command("const e=document.querySelector('.cursors__source');e.value='CHAN1';"
                "e.dispatchEvent(new Event('change'));S.set({cursors:{x1:null,x2:null,y1:0,y2:null}},'user');")
        assert state("(await import('/js/analysis/cursors.js')).cursorSource(S).channel.name") == 'CHAN1'
        start = plot_point(0, 0.5)
        drag(start, {**start, 'y': start['y'] + 10})
        after = state('S.get().cursors.y1')
        assert abs(after + 10 * 10 / g['rows'][0]['h']) <= 0.05, (after, g)

        before = state("S.get().channels.filter(ch=>['CHAN1','CHAN2'].includes(ch.name)).map(({name,scale,position})=>({name,scale,position}))")
        command("S.command('view.zoomKind','vertical');S.command('view.mode','zoom');")
        drag(plot_point(1, 0.25), plot_point(1, 0.75))
        after = state("S.get().channels.filter(ch=>['CHAN1','CHAN2'].includes(ch.name)).map(({name,scale,position})=>({name,scale,position}))")
        assert after[0] == before[0] and after[1]['scale'] != before[1]['scale'], (before, after)
        command("S.command('view.undo');S.command('view.mode','pan');")
        assert state("S.get().channels.filter(ch=>['CHAN1','CHAN2'].includes(ch.name)).map(({name,scale,position})=>({name,scale,position}))") == before

        c.wait("[...document.querySelectorAll('canvas')].find(e=>e.hitChannel)?.dataset.pending!== '1'")
        start = c.js("""(()=>{const e=[...document.querySelectorAll('.measure button')].find(e=>e.textContent.trim().startsWith('Vmax'));
          e.scrollIntoView({block:'nearest'});const r=e.getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2};})()""")
        target = c.js("""(()=>{const cv=[...document.querySelectorAll('canvas')].find(e=>e.hitChannel),box=cv.getBoundingClientRect();
          const r=cv.gridRect().rows[1];
          for(let y=box.top+r.t+8;y<box.top+r.t+r.h-8;y+=4)for(let x=box.left+r.l+10;x<box.left+r.l+r.w-10;x+=6)
            if(document.elementFromPoint(x,y)===cv&&cv.hitChannel(x,y)==='CHAN2')return {x,y};return null})()""")
        assert target, '格 1 找不到 CHAN2 波形點'
        before = state('S.get().measurements.length')
        drag(start, target)
        assert state('S.get().measurements.length') == before + 1
        assert state('S.get().measurements.at(-1).channel') == 'CHAN2'
        before = state('S.get().grids')
        command("S.command('view.zoomRect',{grids:{n:2,assign:{CHAN1:1}}});")
        assert state('S.get().grids') == {'n': 2, 'assign': {'CHAN1': 1}}
        command("S.command('view.undo');")
        assert state('S.get().grids') == before
        command("S.command('view.redo');")
        assert state('S.get().grids') == {'n': 2, 'assign': {'CHAN1': 1}}
        command("S.command('view.undo');")
        for n in (4, 8):
            command(f"S.set({{grids:{{n:{n},assign:{{}}}}}},'user');")
            assert len(geometry()['rows']) == n
            assert not c.errors, c.errors
        command("S.set({grids:{n:1,assign:{}}},'user');")
        g = geometry()
        assert len(g['rows']) == 1 and g['rows'][0]['t'] == g['t'] and g['rows'][0]['h'] == g['h'], g
        for width, height in ((1400, 900), (1100, 700), (900, 600)):
            c.send('Emulation.setDeviceMetricsOverride', width=width, height=height,
                   deviceScaleFactor=1, mobile=False)
            command("S.set({grids:{n:8,assign:{}}},'program');")
            c.wait("[...document.querySelectorAll('canvas')].find(e=>e.hitChannel)?.dataset.pending!=='1'")
            g = geometry()
            assert len(g['rows']) == 8 and all(row['h'] > 0 for row in g['rows']), g
            assert c.js('document.documentElement.scrollWidth<=document.documentElement.clientWidth+1')
            assert not c.errors, c.errors
            c.shot(out / f'grids_8_{width}x{height}.png')
    finally:
        c.js("document.querySelectorAll('.analysis__toolbar .popmenu:popover-open').forEach(e=>e.hidePopover())")
        c.send('Emulation.setDeviceMetricsOverride', width=size['width'], height=size['height'],
               deviceScaleFactor=size['scale'], mobile=False)
        patch = {k: saved[k] for k in ('channels', 'view', 'cursors', 'selected', 'measurements', 'markerMode', 'markerResult') if k in saved}
        grids = json.dumps(saved['grids']) if 'grids' in saved else 'undefined'
        command("S.set({..." + json.dumps(patch) + ",grids:" + grids + "},'program');")
        command("const e=document.querySelector('.cursors__source');if(e){e.value=" + json.dumps(saved.get('source')) +
                ";e.dispatchEvent(new Event('change'));}S.set({cursors:" + json.dumps(saved['cursors']) + "},'program');"
                "S.command('view.zoomKind'," + json.dumps(saved['kind']) + ");S.command('view.mode'," + json.dumps(saved['mode']) + ");")
        c.js("(()=>{const k='scope.analysis.grids.v1',v=" + json.dumps(saved['raw']) +
             ";if(v===null)localStorage.removeItem(k);else localStorage.setItem(k,v)})()")


if __name__ == '__main__':
    assert callable(grid_checks)
    print('browser_grid_checks self-check OK（實際瀏覽器步驟待主控執行）')
