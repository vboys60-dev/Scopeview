"""L8：Marker 的瀏覽器接線、表格尺寸與剪貼簿驗證。"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scope_tool.web.browser_check import Cdp


def p3a_markers(c: Cdp, prep: str) -> None:
    """來源脫鉤、物理值與畫面投影、摘要移除與禁用模式。"""
    result = c.js("(async()=>{" + prep + """
        const C=await import('/js/analysis/cursors.js'),F=await import('/js/fmt.js'),M=await import('/js/analysis/mainplot.js'),original=S.state.channels,selected=S.state.selected;
        const mode=S.state.markerMode,cur={...S.state.cursors};
        const source=document.querySelector('.cursors__source'),choose=name=>{source.value=name;source.dispatchEvent(new Event('change',{bubbles:true}))};
        const originalSource=C.cursorSource(S).channel?.name;
        try {
            const first=original[0],second=original[1];
            choose(first.name);S.set({markerMode:null});S.command('cursor.intent',{which:'y1',value:first.position+2});
            const before=C.cursorSource(S).y1,division=S.state.cursors.y1;
            document.querySelectorAll('.analysis__chanbar .chip')[1].click();
            const independent=source.value===first.name&&S.state.selected===second.name&&C.cursorSource(S).y1===before;
            const proto=CanvasRenderingContext2D.prototype,fill=proto.fillText,draws=[];
            proto.fillText=function(t,x,y,...a){if(t.startsWith('v1 '))draws.push({t,y});return fill.call(this,t,x,y,...a)};
            try { S.updateChannel(first.name,{scale:first.scale*2},'user'); } finally { proto.fillText=fill; }
            const after=C.cursorSource(S),projected=S.state.cursors.y1;
            const field=document.querySelector('.cursors__field--y input');
            const expected=before/(first.scale*2)+first.position,cv=document.querySelector('.analysis__main canvas').getBoundingClientRect();
            const expectedY=Math.round(M.divY(M.layoutRect(cv.width,cv.height),expected))+2.5;
            const track=[...document.querySelectorAll('.analysis__toolbar option')].find(o=>o.value==='Track Measurements');
            return {independent,physical:Math.abs(after.y1-before)<1e-12,
                projected:Math.abs(projected-expected)<1e-12,moved:projected!==division,
                input:Math.abs(F.parseSI(field.value)-before)<Math.max(1e-12,Math.abs(before)*0.001),unit:field.parentElement.textContent,
                drawn:Math.abs(draws.at(-1)?.y-expectedY)<1&&draws.at(-1)?.t===`v1 ${F.fmt(before,first.unit)}`,
                selectable:!!track&&!track.disabled,title:track?.title,source:source.value};
        } finally {
            S.set({channels:original,selected,markerMode:mode},'program');
            if(originalSource)choose(originalSource);
            for(const [which,value] of Object.entries(cur))S.command('cursor.intent',{which,value});
        }
    })()""")
    assert all(result[k] for k in ('independent', 'physical', 'projected', 'moved', 'selectable', 'input', 'drawn')), result
    assert result['source'] == 'CHAN1' and '(V)' in result['unit'], result
    assert result['selectable'], result
    for width, height in ((1360, 860), (900, 600)):
        c.send('Emulation.setDeviceMetricsOverride', width=width, height=height, deviceScaleFactor=1, mobile=False)
        c.pump(0.3)
        assert c.js("!document.querySelector('.analysis__cursorSummary')")
    c.send('Emulation.setDeviceMetricsOverride', width=1400, height=900, deviceScaleFactor=1, mobile=False)


def p3b_markers(c: Cdp, prep: str) -> None:
    """游標表使用 B 全寬，數字單位不換行；點擊複製取得真正產生的 TSV。"""
    original = c.js("(async()=>{" + prep + """
        const C=await import('/js/analysis/cursors.js');
        return {mode:S.state.markerMode,cursors:S.state.cursors,source:C.cursorSource(S).channel?.name,
            tab:document.querySelector('.analysis__resultTabs [aria-selected=true]')?.dataset.resultTab,
            lower:document.querySelector('.analysis__lowerbody').hidden};
    })()""")
    try:
        c.js("(async()=>{" + prep + """
            if(document.querySelector('.analysis__lowerbody').hidden)S.command('layout.toggle','lower');
            S.command('layout.reset','lower');
            S.set({markerMode:'Manual X and Y'});
            for(const [which,value] of Object.entries({x1:3e-6,x2:1e-6,y1:1,y2:-1}))S.command('cursor.intent',{which,value});
        })()""")
        c.wait("!document.querySelector('.analysis__lowerbody').hidden")
        c.js("document.querySelector('[data-result-tab=cursor]').click()")
        c.wait("(()=>{const t=document.querySelector('.cursor-results__table');return t?.rows.length===5&&t.rows[1].cells[1].textContent==='3 µs'&&t.rows[1].cells[3].textContent==='-2 µs'})()")
        for width in (1100, 1360):
            c.send('Emulation.setDeviceMetricsOverride', width=width, height=860, deviceScaleFactor=1, mobile=False)
            c.pump(0.3)
            dims = c.js("""(()=>{
                const p=document.querySelector('.analysis__cursors'),t=p.querySelector('.cursor-results__table'),w=t.parentElement;
                p.scrollTop=0;
                const pr=p.getBoundingClientRect(),first=t.rows[1]?.getBoundingClientRect();
                const walker=document.createTreeWalker(p,NodeFilter.SHOW_TEXT),small=[];let n;
                while(n=walker.nextNode())if(n.textContent.trim()&&n.parentElement.getClientRects().length&&parseFloat(getComputedStyle(n.parentElement).fontSize)<12.5)small.push(n.textContent);
                return {rowVisible:!!first&&first.top>=pr.top&&first.bottom<=Math.min(pr.bottom,innerHeight)&&first.left>=pr.left&&first.right<=pr.right,
                    oldHidden:p.querySelector('.cursors__readout').hidden,exists:!!t,visible:t.getBoundingClientRect().height>0,panel:p.scrollWidth<=p.clientWidth+1,
                    table:w.scrollWidth<=w.clientWidth+1,page:document.documentElement.scrollWidth<=innerWidth+1,small,
                    nowrap:[...t.querySelectorAll('th,td')].every(e=>getComputedStyle(e).whiteSpace==='nowrap')};
            })()""")
            assert all(dims[k] for k in ('rowVisible', 'oldHidden', 'exists', 'visible', 'panel', 'table', 'page', 'nowrap')) and not dims['small'], (width, dims)
        # 傳統 @X1/@X2 通道表維持前置，預設高度無須捲動即可完整看見資料列。
        c.js("(async()=>{" + prep + "S.set({markerMode:null});})()")
        c.wait("!document.querySelector('.analysis__cursors > table').hidden&&document.querySelector('.analysis__cursors > table').rows.length>1")
        for width in (1100, 1360):
            c.send('Emulation.setDeviceMetricsOverride', width=width, height=860, deviceScaleFactor=1, mobile=False)
            c.pump(0.3)
            dims = c.js("""(()=>{
                const p=document.querySelector('.analysis__cursors');p.scrollTop=0;
                const t=p.querySelector(':scope > table'),pr=p.getBoundingClientRect(),r=t.rows[1].getBoundingClientRect();
                return {visible:!t.hidden&&r.height>0&&r.top>=pr.top&&r.bottom<=Math.min(pr.bottom,innerHeight)&&r.left>=pr.left&&r.right<=pr.right,
                    before:t.compareDocumentPosition(p.querySelector('.cursor-results'))===Node.DOCUMENT_POSITION_FOLLOWING};
            })()""")
            assert dims['visible'] and dims['before'], (width, dims)
        c.js("(async()=>{" + prep + "S.set({markerMode:'Manual X and Y'});})()")
        c.wait("document.querySelector('.analysis__cursors > table').hidden&&document.querySelector('.cursor-results__table').rows.length===5")
        copied = c.js(r"""(async()=>{
            const desc=Object.getOwnPropertyDescriptor(navigator,'clipboard'),writes=[];
            Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async t=>writes.push(t)}});
            try {
                const b=document.querySelector('.cursor-results__copy');b.scrollIntoView({block:'nearest'});
                const r=b.getBoundingClientRect(),hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
                const clickable=!b.disabled&&(hit===b||b.contains(hit));b.click();await Promise.resolve();
                return {clickable,text:writes[0],rows:[...document.querySelector('.cursor-results__table').rows].map(r=>[...r.cells].map(c=>c.textContent).join('\t')).join('\n')};
            } finally {if(desc)Object.defineProperty(navigator,'clipboard',desc);else delete navigator.clipboard;}
        })()""")
        header = 'Marker\t水平(X)\t垂直(Y，來源單位)\tΔX\t1/ΔX\tΔY\tΔY/ΔX\tDelta To'
        assert copied['clickable'] and copied['text'].splitlines()[0] == header, copied
        assert copied['text'] == copied['rows'] and len(copied['text'].splitlines()) == 5, copied
    finally:
        import json
        c.js("(async()=>{" + prep + "const old=" + json.dumps(original) + ";" + """
            S.set({markerMode:old.mode});
            for(const [which,value] of Object.entries(old.cursors))S.command('cursor.intent',{which,value});
            if(old.tab)document.querySelector(`[data-result-tab=${old.tab}]`).click();
            if(document.querySelector('.analysis__lowerbody').hidden!==old.lower)S.command('layout.toggle','lower');
        })()""")
        c.send('Emulation.setDeviceMetricsOverride', width=1400, height=900, deviceScaleFactor=1, mobile=False)


def p3b2_zoom(c: Cdp, prep: str) -> None:
    """真實 CDP 拖曳：可見通道範圍、一次復原、Y 真值與重投影。"""
    import json
    original = c.js("(async()=>{" + prep + """
        const C=await import('/js/analysis/cursors.js');
        return {channels:S.state.channels,view:S.state.view,mode:S.state.markerMode,cursors:S.state.cursors,
            source:C.cursorSource(S).channel?.name};
    })()""")
    try:
        c.js("(async()=>{" + prep + """
            S.set({markerMode:null});
            for(const ch of S.state.channels.filter(ch=>ch.visible))S.updateChannel(ch.name,{scale:1,position:1},'user');
            const source=document.querySelector('.cursors__source');
            source.value=S.state.channels.find(ch=>ch.visible).name;source.dispatchEvent(new Event('change'));
            S.command('cursor.intent',{which:'y1',value:2});S.command('cursor.intent',{which:'y2',value:0});
            S.command('view.mode','zoom');document.querySelector('[data-zoom-kind=vertical]').click();
        })()""")
        c.pump(0.3)
        before = c.js("(async()=>{" + prep + """
            const M=await import('/js/analysis/mainplot.js'),C=await import('/js/analysis/cursors.js');
            const cv=document.querySelector('.analysis__main canvas');cv.scrollIntoView({block:'nearest'});
            const b=cv.getBoundingClientRect(),r=M.layoutRect(b.width,b.height);
            return {channels:S.state.channels,view:S.state.view,y1:C.cursorSource(S).y1,y2:C.cursorSource(S).y2,
                x:b.x+b.width*0.55,a:b.y+r.t+r.h*0.3,z:b.y+r.t+r.h*0.6};
        })()""")
        c.mouse('mousePressed', before['x'], before['a'])
        c.mouse('mouseMoved', before['x'], before['z'], buttons=1)
        c.mouse('mouseReleased', before['x'], before['z'])
        c.pump(0.3)
        result = c.js("(async()=>{" + prep + """
            const C=await import('/js/analysis/cursors.js'),src=C.cursorSource(S),b=""" + json.dumps(before) + """;
            const near=(a,b)=>Math.abs(a-b)<1e-10;
            const tol=0.025; // 框選邊界落在整數像素，單像素約 0.02 格；剛好貼邊時會差幾個 1e-6
            return {view:JSON.stringify(S.state.view)===JSON.stringify(b.view),
                physical:near(src.y1,b.y1)&&near(src.y2,b.y2),
                projected:near((S.state.cursors.y1-src.channel.position)*src.channel.scale,b.y1),
                fit:b.channels.filter(ch=>ch.visible).every(ch=>{
                    const next=S.state.channels.find(n=>n.name===ch.name);
                    const lo=(-1-ch.position)*ch.scale,hi=(2-ch.position)*ch.scale;
                    return next.scale<ch.scale&&lo/next.scale+next.position>=-5-tol&&hi/next.scale+next.position<=5+tol;
                })};
        })()""")
        assert all(result.values()), result
        c.js("document.querySelector('.analysis__hmodes button[title^=復原視圖]').click()")
        restored = c.js("(async()=>{" + prep + """
            const C=await import('/js/analysis/cursors.js');
            return {channels:S.state.channels,view:S.state.view,y1:C.cursorSource(S).y1,y2:C.cursorSource(S).y2};
        })()""")
        for key in ('channels', 'view', 'y1', 'y2'):
            assert restored[key] == before[key], (key, before, restored)
    finally:
        c.js("(async()=>{" + prep + "const old=" + json.dumps(original) + ";" + """
            S.set({channels:old.channels,view:old.view,markerMode:old.mode},'program');
            if(old.source){const e=document.querySelector('.cursors__source');e.value=old.source;e.dispatchEvent(new Event('change'));}
            for(const [which,value] of Object.entries(old.cursors))S.command('cursor.intent',{which,value});
            S.command('view.zoomKind','horizontal');S.command('view.mode','pan');
        })()""")


if __name__ == '__main__':
    import ast
    ast.parse(Path(__file__).read_text(encoding='utf-8'))
    assert callable(p3a_markers) and callable(p3b_markers) and callable(p3b2_zoom)
    print('browser_marker_checks self-check OK（CDP 斷言由 browser_check 執行）')


def dock_layout(c: Cdp, prep: str) -> None:
    """版面 C：B 區移到圖右側、游標／Marker 上下疊、<1280px 自動退回底部，偏好不被覆寫。"""
    check = """(async()=>{""" + prep + """
        const R=s=>document.querySelector(s).getBoundingClientRect(),wait=()=>new Promise(r=>setTimeout(r,250));
        const state=()=>{const l=R('.analysis__lower'),p=R('.analysis__plot'),m=R('.analysis__markers'),k=R('.analysis__cursors');
            return {dock:document.querySelector('.analysis').classList.contains('analysis--dock'),right:l.left>=p.right-1,
                full:Math.abs(l.height-R('.analysis').height+R('.analysis__toolbar').height)<40,stack:m.top>=k.bottom-1||k.top>=m.bottom-1,
                page:document.documentElement.scrollWidth<=innerWidth+1,w:Math.round(l.width)}};
        try {
            S.command('layout.markerSide',true);
            document.querySelector('[data-result-tab=marker]').click();await wait();
            const on=state();
            window.__vw=innerWidth;
            return {on,pref:JSON.parse(localStorage.getItem('scope.analysis.layout.v1')).markerSide};
        } finally { }
    })()"""
    res = c.js(check)
    assert res["on"]["dock"] and res["on"]["right"] and res["on"]["stack"] and res["on"]["page"], res
    assert res["pref"] is True and 300 <= res["on"]["w"] <= 360, res
    c.send('Emulation.setDeviceMetricsOverride', width=800, height=860, deviceScaleFactor=1, mobile=False)
    c.pump(0.6)
    narrow = c.js("(()=>({dock:document.querySelector('.analysis').classList.contains('analysis--dock'),"
                  "pref:JSON.parse(localStorage.getItem('scope.analysis.layout.v1')).markerSide}))()")
    c.send('Emulation.setDeviceMetricsOverride', width=1400, height=900, deviceScaleFactor=1, mobile=False)
    c.pump(0.6)
    c.js("(async()=>{(await import('/js/analysis/store.js')).store.command('layout.markerSide',false)})()")
    c.pump(0.4)
    after = c.js("document.querySelector('.analysis').classList.contains('analysis--dock')")
    assert narrow["dock"] is False and narrow["pref"] is True and after is False, (narrow, after)


def marker_add_button(c: Cdp, prep: str) -> None:
    """「＋ 獨立點」連按三次：真後端吸附後表格出現 3 個獨立點（不是只有 M1）。"""
    res = c.js("(async()=>{" + prep + """
        const wait=ms=>new Promise(r=>setTimeout(r,ms));
        S.set({markerTable:[]},'program');
        document.querySelector('[data-result-tab=marker]').click();
        const b=[...document.querySelectorAll('.analysis__markers button')].find(x=>x.textContent.includes('獨立點'));
        for(let i=0;i<3;i++){b.click();await wait(150);}
        await wait(600);
        const t=S.state.markerTable,rows=document.querySelectorAll('.analysis__markers tbody tr, .analysis__markers tr[data-marker-key]');
        const r={n:t.filter(p=>!p.link).length,ids:t.map(p=>p.id),rows:rows.length};
        S.set({markerTable:[]},'program');return r;
    })()""")
    assert res["n"] == 3 and res["rows"] == 3, res
    # 900 寬量測表格與基準切換；由 browser_check 的 CDP 執行。
    c.send('Emulation.setDeviceMetricsOverride', width=900, height=600, deviceScaleFactor=1, mobile=False)
    try:
        result = c.js("(async()=>{" + prep + """
            S.command('marker.link',{t:(S.state.view.t0+S.state.view.t1)/2});
            S.command('marker.add',{ch:S.state.selected,t:(S.state.view.t0+S.state.view.t1)/2});
            await new Promise(r=>setTimeout(r,700));
            const p=document.querySelector('.analysis__markers'),t=p.querySelector('table'),s=t.querySelector('tr[data-marker-key] select');
            const id=S.state.markerTable.find(x=>!x.link).id;s.value=id;s.dispatchEvent(new Event('change',{bubbles:true}));
            const switched=S.state.markerTable.some(x=>x.ref===id);
            S.command('marker.remove',id);
            const reset=S.state.markerTable.every(x=>x.ref===undefined);
            const dims={panel:p.scrollWidth<=p.clientWidth+1,table:t.scrollWidth<=t.clientWidth+1,page:document.documentElement.scrollWidth<=innerWidth+1};
            S.set({markerTable:[]},'program');return {switched,reset,...dims};
        })()""")
        assert all(result.values()), result
    finally:
        c.send('Emulation.clearDeviceMetricsOverride'); c.pump(0.4)


def marker_rightclick(c: Cdp, prep: str) -> None:
    """真實右鍵：主圖中央應彈出 marker-menu，點「新增獨立 Marker」後表格多一點。"""
    box = c.js("(()=>{const r=document.querySelector('.analysis__main canvas').getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2}})()")
    c.js("(async()=>{" + prep + "S.set({markerTable:[]},'program')})()")
    c.send('Input.dispatchMouseEvent', type='mousePressed', x=box['x'], y=box['y'], button='right', clickCount=1)
    c.send('Input.dispatchMouseEvent', type='mouseReleased', x=box['x'], y=box['y'], button='right', clickCount=1)
    c.pump(0.5)
    texts = c.js("[...document.querySelectorAll('.marker-menu button')].map(b=>b.textContent)")
    assert texts, '右鍵沒有彈出選單'
    button = c.js("""(()=>{const b=[...document.querySelectorAll('.marker-menu button')].find(b=>b.textContent.includes('新增獨立 Marker'));
        const r=b.getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2}})()""")
    c.send('Input.dispatchMouseEvent', type='mouseMoved', x=button['x'], y=button['y'])
    c.send('Input.dispatchMouseEvent', type='mousePressed', x=button['x'], y=button['y'], button='left', clickCount=1)
    c.send('Input.dispatchMouseEvent', type='mouseReleased', x=button['x'], y=button['y'], button='left', clickCount=1)
    c.pump(0.8)
    n = c.js("(async()=>{" + prep + "return S.state.markerTable.filter(p=>!p.link).length})()")
    # 拖出範圍：獨立點夾回通道端點，仍有讀值（不會落在曲線外）
    far = c.js("(async()=>{" + prep + """const id=S.state.markerTable[0].id,ch=S.state.channels.find(x=>x.name===S.state.markerTable[0].ch);
        S.command('marker.move',{id,t:ch.t0-1e6});await new Promise(r=>setTimeout(r,700));
        const p=S.state.markerTable[0];return {src:p.t_src,t0:ch.t0,t1:ch.t1}})()""")
    c.js("(async()=>{" + prep + "S.set({markerTable:[]},'program')})()")
    assert n == 1, (texts, n)
    assert far['t0'] - 1e-12 <= far['src'] <= far['t1'], far
