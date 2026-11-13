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

    saved = c.js('(async()=>{' + prep + """
        return {grids:S.get().grids,channels:S.get().channels,
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
        for n in (4, 8):
            command(f"S.set({{grids:{{n:{n},assign:{{}}}}}},'user');")
            assert len(geometry()['rows']) == n
            assert not c.errors, c.errors
        command("S.set({grids:{n:1,assign:{}}},'user');")
        g = geometry()
        assert len(g['rows']) == 1 and g['rows'][0]['t'] == g['t'] and g['rows'][0]['h'] == g['h'], g
    finally:
        command("S.set({grids:" + json.dumps(saved.get('grids')) + ",channels:" + json.dumps(saved['channels']) + "},'program');")
        c.js("(()=>{const k='scope.analysis.grids.v1',v=" + json.dumps(saved['raw']) +
             ";if(v===null)localStorage.removeItem(k);else localStorage.setItem(k,v)})()")


if __name__ == '__main__':
    assert callable(grid_checks)
    print('browser_grid_checks self-check OK（實際瀏覽器步驟待主控執行）')
