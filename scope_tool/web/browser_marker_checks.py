"""L8：Marker 的瀏覽器接線、表格尺寸與剪貼簿驗證。"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scope_tool.web.browser_check import Cdp


def p3a_markers(c: Cdp, prep: str) -> None:
    """來源脫鉤、物理值與畫面投影、單行摘要與禁用模式。"""
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
                disabled:track?.disabled,title:track?.title,source:source.value};
        } finally {
            S.set({channels:original,selected,markerMode:mode},'program');
            if(originalSource)choose(originalSource);
            for(const [which,value] of Object.entries(cur))S.command('cursor.intent',{which,value});
        }
    })()""")
    assert all(result[k] for k in ('independent', 'physical', 'projected', 'moved', 'disabled', 'input', 'drawn')), result
    assert result['source'] == 'CHAN1' and '(V)' in result['unit'], result
    assert result['title'] == '需先補後端事件座標，暫未提供', result
    for width, height in ((1360, 860), (900, 600)):
        c.send('Emulation.setDeviceMetricsOverride', width=width, height=height, deviceScaleFactor=1, mobile=False)
        c.pump(0.3)
        dims = c.js("""(()=>{const b=document.querySelector('.analysis__cursorSummary'),p=b.parentElement;
            const r=b.getBoundingClientRect(),pr=p.getBoundingClientRect(),s=getComputedStyle(b);
            return {height:r.height,line:parseFloat(s.lineHeight),right:r.right,parentRight:pr.right,
                nowrap:s.whiteSpace,overflow:s.overflowX,ellipsis:s.textOverflow,title:b.title,text:b.textContent}})()""")
        assert dims['nowrap'] == 'nowrap' and dims['overflow'] == 'hidden' and dims['ellipsis'] == 'ellipsis', dims
        assert dims['height'] < 28 and dims['right'] <= dims['parentRight'] + 1, dims
        assert dims['title'] == dims['text'] and 'ΔX' in dims['text'], dims
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


if __name__ == '__main__':
    import ast
    ast.parse(Path(__file__).read_text(encoding='utf-8'))
    assert callable(p3a_markers) and callable(p3b_markers)
    print('browser_marker_checks self-check OK（CDP 斷言由 browser_check 執行）')
