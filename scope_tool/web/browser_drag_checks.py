"""量測拖放的瀏覽器檢查；待主控實跑。"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scope_tool.web.browser_check import Cdp


def drag_checks(c: Cdp, prep: str) -> None:
    """使用既有頁面及資料，以 CDP 事件檢查拖放與鍵盤操作。"""
    def state(expr: str):
        return c.js('(async()=>{' + prep + 'return ' + expr + '})()')

    def key(name: str) -> None:
        for typ in ('keyDown', 'keyUp'):
            extra = {'text': '\r'} if name == 'Enter' and typ == 'keyDown' else {}
            c.send('Input.dispatchKeyEvent', type=typ, key=name, code=name, **extra,
                   windowsVirtualKeyCode={'Tab': 9, 'Enter': 13, 'Escape': 27}[name])

    def point(expr: str) -> dict:
        return c.js('''(()=>{const e=''' + expr + '''; if(!e) throw Error('找不到操作目標');
          e.scrollIntoView({block:'nearest',inline:'nearest'});const r=e.getBoundingClientRect();
          if(!r.width||!r.height) throw Error('操作目標不可見');
          return {x:r.left+r.width/2,y:r.top+r.height/2}})()''')

    def button(name: str) -> str:
        return "[...document.querySelectorAll('.measure button')].find(e=>e.textContent.trim().startsWith(" + json.dumps(name) + "))"

    target = "document.querySelector('.chanbar__col[data-channel=\"CHAN2\"]')"

    def mouse(typ: str, p: dict, **kw) -> None:
        c.mouse(typ, p['x'], p['y'], **kw)

    def move(a: dict, b: dict, check: bool = False) -> None:
        """先以小步越過 6px 門檻，再以較大步移到目標；check 時斷言已進入拖曳。"""
        dx, dy = b['x'] - a['x'], b['y'] - a['y']
        d = max((dx * dx + dy * dy) ** 0.5, 1e-9)
        small = min(8.0, d)  # 4 步，每步 ≤2px
        for i in range(1, 5):
            mouse('mouseMoved', {'x': a['x'] + dx / d * small * i / 4, 'y': a['y'] + dy / d * small * i / 4}, buttons=1)
        if d > small:
            s0 = {'x': a['x'] + dx / d * small, 'y': a['y'] + dy / d * small}
            for i in range(1, 5):
                if i == 4:
                    c.pump(0.1)
                mouse('mouseMoved', {k: s0[k] + (b[k] - s0[k]) * i / 4 for k in ('x', 'y')}, buttons=1)
        c.pump(0.15)
        if check:
            assert c.js("!!document.querySelector('.measure__dragtag')"), '沒進入拖曳（無 .measure__dragtag）'
            assert c.js("document.querySelectorAll('.is-droptarget').length>=1"), '沒進入拖曳（無 .is-droptarget）'

    def touch(typ: str, p: dict | None = None) -> None:
        points = [] if p is None else [{'x': p['x'], 'y': p['y'], 'id': 1}]
        c.send('Input.dispatchTouchEvent', type=typ, touchPoints=points)

    def snapshot() -> dict:
        return state('({selected:S.state.selected,entries:S.state.measurements.map(m=>({channel:m.channel,channel2:m.channel2,name:m.name}))})')

    def added(before: dict, channel: str, name: str = 'Vmax') -> dict:
        after = snapshot()
        assert len(after['entries']) == len(before['entries']) + 1, (before, after)
        assert after['entries'][-1]['channel'] == channel and after['entries'][-1]['name'] == name, after
        return after

    saved = state('({selected:S.state.selected,measurements:S.state.measurements})')
    try:
        c.js('(async()=>{' + prep + "S.set({selected:'CHAN1'},'program')})()")
        c.send('Emulation.setTouchEmulationEnabled', enabled=True, maxTouchPoints=1)
        a, b = point(button('Vmax')), point(target)
        before = snapshot()
        mouse('mousePressed', a); move(a, b, True); mouse('mouseReleased', b); c.pump(0.2)
        after = added(before, 'CHAN2')
        assert after['selected'] == before['selected'], (before, after)

        # 在非通道欄的空白位置放開。
        a = point(button('Vmax'))
        blank = c.js('''(()=>{for(let y=10;y<innerHeight;y+=20)for(let x=10;x<innerWidth;x+=20){
          const e=document.elementFromPoint(x,y);if(e&&!e.closest('[data-channel],button,input,select,a,.measure')) return {x,y}}
          throw Error('找不到空白放置點')})()''')
        before = snapshot(); mouse('mousePressed', a); move(a, blank); mouse('mouseReleased', blank); c.pump(0.2)
        assert snapshot() == before

        a, b = point(button('Vmax')), point(target)
        before = snapshot(); mouse('mousePressed', a); move(a, b, True); key('Escape'); mouse('mouseReleased', b); c.pump(0.2)
        assert snapshot() == before
        assert c.js("!document.querySelector('.is-droptarget,.is-dropover,.measure__dragtag')")

        a = point(button('Vmax')); end = {'x': a['x'] + 3, 'y': a['y']}
        before = snapshot(); mouse('mousePressed', a); move(a, end); mouse('mouseReleased', end); c.pump(0.2)
        added(before, before['selected'])

        a, b = point(button('Vmax')), point(target)
        before = snapshot(); touch('touchStart', a); c.pump(0.4); touch('touchMove', b); touch('touchEnd'); c.pump(0.2)
        added(before, 'CHAN2')
        a, b = point(button('Vmax')), point(target)
        before = snapshot(); touch('touchStart', a); touch('touchMove', b); touch('touchEnd'); c.pump(0.2)
        assert snapshot() == before

        # 從文件開頭逐次 Tab，確認兩個目標都能透過實際鍵盤抵達。
        c.js('document.activeElement.blur()')
        name = target + ".querySelector('.chip__name')"
        for expr in (name, button('Vmax')):
            for _ in range(250):
                key('Tab')
                if c.js('document.activeElement===' + expr):
                    break
            else:
                raise AssertionError('Tab 無法抵達 ' + expr)
            if expr == name:
                key('Enter')
                assert snapshot()['selected'] == 'CHAN2'
        before = snapshot(); key('Enter'); c.pump(0.2); added(before, 'CHAN2')

        a, b = point(button('Delay')), point(target)
        source2 = c.js(button('Delay') + ".parentElement.querySelector('select[title=\"來源 2\"]').value")
        before = snapshot(); mouse('mousePressed', a); move(a, b, True); mouse('mouseReleased', b); c.pump(0.2)
        after = added(before, 'CHAN2', '延遲')
        assert after['entries'][-1]['channel2'] == source2, after
        assert not c.errors, c.errors
    finally:
        c.send('Emulation.setTouchEmulationEnabled', enabled=False)
        c.js('(async()=>{' + prep + 'S.set(' + json.dumps(saved, ensure_ascii=False) + ",'program')})()")


if __name__ == '__main__':
    assert callable(drag_checks)
    print('browser_drag_checks self-check OK（待主控實跑）')
