"""L8：分割格線幾何與命中檢查；實際瀏覽器步驟由主控執行。"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scope_tool.web.browser_check import Cdp


def grid_checks(c: Cdp, prep: str) -> None:
    """共用已開啟的波形，結束時還原格線與本機偏好。"""
    def command(expr: str) -> None:
        c.js('(async()=>{' + prep + expr + '})()')
        c.pump(0.4)

    def geometry() -> dict:
        return c.js("""(()=>{const cv=[...document.querySelectorAll('canvas')].find(e=>e.hitChannel);
          const r=cv.gridRect();return {t:r.t,h:r.h,rows:r.rows};})()""")

    def state(expr: str):
        return c.js('(async()=>{' + prep + 'return ' + expr + '})()')

    def drag(start: dict, end: dict) -> None:
        c.mouse('mousePressed', start['x'], start['y'])
        for i in range(1, 9):
            c.mouse('mouseMoved', start['x'] + (end['x'] - start['x']) * i / 8,
                    start['y'] + (end['y'] - start['y']) * i / 8, buttons=1)
        c.mouse('mouseReleased', end['x'], end['y'])
        c.pump(0.4)

    def plot_point(index: int, fraction: float) -> dict:
        return c.js("""(()=>{const cv=[...document.querySelectorAll('canvas')].find(e=>e.hitChannel);
          const box=cv.getBoundingClientRect(),r=cv.gridRect().rows[""" + str(index) + """];
          return {x:box.left+r.l+r.w*0.43,y:box.top+r.t+r.h*""" + str(fraction) + """};})()""")

    saved = c.js('(async()=>{' + prep + """
        return {grids:S.get().grids,channels:S.get().channels,view:S.get().view,cursors:S.get().cursors,
          selected:S.get().selected,measurements:S.get().measurements,markerMode:S.get().markerMode,
          markerResult:S.get().markerResult,source:document.querySelector('.cursors__source')?.value,
          mode:document.querySelector('.analysis__hmodes>button[aria-pressed="true"]')?.title==='框選放大'?'zoom':'pan',
          kind:document.querySelector('[data-zoom-kind][aria-pressed="true"]')?.dataset.zoomKind??'horizontal',
          raw:localStorage.getItem('scope.analysis.grids.v1')};})()""")
    try:
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
    finally:
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
