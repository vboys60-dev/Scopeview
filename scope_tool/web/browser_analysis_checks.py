"""L8：browser_check 的分析頁 CDP 驗證；由主流程注入已開啟檔案的瀏覽器。"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scope_tool.web.browser_check import Cdp


def center_cursors(c: Cdp, prep: str, click: str, out: Path) -> None:
    # layout.toggle 排程 rAF；先等 aria/hidden 一致，再按實際狀態收折。
    lower_state = "(()=>{const b=document.querySelector('.analysis__lowertoggle'),p=document.querySelector('.analysis__lowerbody');return b.getAttribute('aria-expanded')===String(!p.hidden)})()"
    c.wait(lower_state)
    original_hidden = c.js("document.querySelector('.analysis__lowerbody').hidden")
    try:
        if not original_hidden:
            c.js("document.querySelector('.analysis__lowertoggle').click()")
        c.wait("document.querySelector('.analysis__lowerbody').hidden && " + lower_state)
        # 等回中央引發的真正 RPC 完成與控制器回寫，再交棒 P2a。
        # 不另送讀值請求、不靠固定 sleep，也不要求每次都會產生 snap 差值。
        result = c.js("(async()=>{" + prep + """
            const v=S.state.view,w=v.t1-v.t0,mid=(v.t0+v.t1)/2;
            const originalCall=B.call;
            let timer, complete, fail;
            const done=new Promise((resolve,reject)=>{complete=resolve;fail=reject});
            B.call=async function(method,args) {
                try {
                    const r=await originalCall.call(this,method,args);
                    if(method==='cursor_readout') requestAnimationFrame(()=>complete(r));
                    return r;
                } catch(e) { if(method==='cursor_readout') fail(e); throw e; }
            };
            try {
                timer=setTimeout(()=>fail(Error('回中央讀值未完成')),10000);
                S.command('cursor.intent',{which:'x1',value:v.t0-w});
                S.command('cursor.intent',{which:'x2',value:v.t0-w*0.8});
                S.command('cursor.intent',{which:'y1',value:1});
                S.command('cursor.intent',{which:'y2',value:-1});
                const b=[...document.querySelectorAll('.analysis__chanbar button')].find(b=>b.textContent==='回中央');
                const visible=!!b&&b.getBoundingClientRect().height>0&&!b.disabled;
                if(!visible) throw Error('回中央按鈕不可用');
                b.click();
                const q=S.state.cursors;
                const result={visible,hidden:document.querySelector('.analysis__lowerbody').hidden,
                    center:Math.abs((q.x1+q.x2)/2-mid)/w,gap:Math.abs((q.x2-q.x1)/w-0.2),y:q.y1===1&&q.y2===-1};
                await done;
                return result;
            } finally {clearTimeout(timer);B.call=originalCall;}
        })()""")
        assert result["visible"] and result["hidden"] and result["y"], result
        assert result["center"] < 1e-12 and result["gap"] < 1e-12, result
        c.shot(out / "06_center_collapsed.png")
    finally:
        # 即使斷言失敗仍還原，避免 step() 繼續後續案例時殘留 B 狀態。
        c.wait(lower_state)
        if c.js("document.querySelector('.analysis__lowerbody').hidden") != original_hidden:
            c.js("document.querySelector('.analysis__lowertoggle').click()")
        expected = "true" if original_hidden else "false"
        c.wait(f"document.querySelector('.analysis__lowerbody').hidden === {expected} && " + lower_state)


def p2a_view(c: Cdp, prep: str, click: str, out: Path) -> None:
    before = c.js("(async()=>{" + prep + " const cv=document.querySelector('.analysis__main canvas');"
                  "cv.scrollIntoView({block:'nearest'});const b=cv.getBoundingClientRect();"
                  "const M=await import('/js/analysis/mainplot.js'),H=await import('/js/analysis/handles.js');"
                  "let r=M.layoutRect(b.width,b.height);"
                  "const V=await import('/js/analysis/voltage.js'),g=cv.getContext('2d');g.font='12.5px sans-serif';"
                  "r=M.layoutRect(b.width,b.height,V.voltageLeft(t=>g.measureText(t).width,V.voltageAxis(S.state.channels.find(c=>c.name===S.state.selected)),H.channelHandles(S.state.channels,r)));"
                  "return {view:S.state.view,channels:S.state.channels,cursors:S.state.cursors,"
                  "x:b.x+r.l,y:b.y+r.t+r.h*0.6,w:r.w}})()")
    c.js("(" + click + ")('⬚ 框選放大')")
    x0, x1, y = before["x"] + before["w"] * 0.2, before["x"] + before["w"] * 0.7, before["y"]
    c.mouse("mousePressed", x0, y)
    c.mouse("mouseMoved", x1, y, buttons=1)
    c.mouse("mouseReleased", x1, y)
    c.pump(0.4)
    snapshot = "(async()=>{" + prep + "return {view:S.state.view,channels:S.state.channels,cursors:S.state.cursors}})()"
    after = c.js(snapshot)
    span = before["view"]["t1"] - before["view"]["t0"]
    for k, fraction in (("t0", 0.2), ("t1", 0.7)):
        assert abs(after["view"][k] - (before["view"]["t0"] + fraction * span)) < span * 0.003, (before, after)
    assert after["channels"] == before["channels"] and after["cursors"] == before["cursors"], (before["channels"], before["cursors"], after)
    c.js("(" + click + ")('↶')")
    undone = c.js(snapshot)
    assert undone["view"] == before["view"], (before, undone)
    assert undone["channels"] == before["channels"] and undone["cursors"] == before["cursors"], undone
    c.js("(()=>{const i=document.querySelector('.analysis__horizontal input[data-axis=scale]');"
         "if(!i||i.disabled)throw Error('時間/格欄位不可用');i.focus();i.value='20n';"
         "i.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',bubbles:true}));i.blur()})()")
    c.pump(0.3)
    typed = c.js(snapshot)
    assert abs((typed["view"]["t1"] - typed["view"]["t0"]) - 10 * 20e-9) < 1e-18, typed
    assert typed["channels"] == before["channels"] and typed["cursors"] == before["cursors"], typed
    c.shot(out / "06_p2a_horizontal.png")
    c.js("(" + click + ")('✥ 平移')")
    c.js("(async()=>{" + prep + "S.command('view.reset')})()")


def p2b2_vertical(c: Cdp, prep: str, click: str, out: Path) -> None:
    result = c.js("(async()=>{" + prep + "const old=S.state.channels,selected=S.state.selected;"
                  "const name=old[1].name;document.querySelectorAll('.analysis__chanbar .chip')[1].click();"
                  "const active=document.querySelector('.vertical__active').textContent;"
                  "S.updateChannel(name,{scale:0.002},'user');const before=S.state.channels;"
                  "const proto=CanvasRenderingContext2D.prototype,original=proto.fillText,draws=[];"
                  "proto.fillText=function(t,x,y,...a){draws.push({t,color:this.fillStyle});return original.call(this,t,x,y,...a)};"
                  "try{const i=document.querySelector('[data-vertical=position]');i.value='-4m';"
                  "i.dispatchEvent(new Event('change',{bubbles:true}));"
                  "const after=S.state.channels,cv=document.querySelector('.analysis__main canvas'),g=cv.getContext('2d');"
                  "g.fillStyle=after[1].color;return {active,name,position:after[1].position,"
                  "others:before.every((v,k)=>k===1||JSON.stringify(v)===JSON.stringify(after[k])),"
                  "axis:draws.some(d=>d.t==='2.0 mV'&&d.color===g.fillStyle)}"
                  "}finally{proto.fillText=original;S.set({channels:old,selected},'program')}})()")
    assert result["name"] in result["active"], result
    assert result["position"] == 2 and result["others"] and result["axis"], result


def vertical_bounds(c: Cdp, prep: str, click: str, out: Path) -> None:
    for width in (1400, 1000):
        c.send("Emulation.setDeviceMetricsOverride", width=width, height=900, deviceScaleFactor=1, mobile=False)
        c.pump(0.3)
        dims = c.js("(()=>{const bar=document.querySelector('.analysis__chanbar'),v=bar.querySelector('.vertical');"
                    "const r=bar.getBoundingClientRect(),vr=v.getBoundingClientRect();"
                    "const controls=[...v.querySelectorAll('input,button')].map(e=>({text:e.title,right:e.getBoundingClientRect().right}));"
                    "return {right:r.right,verticalRight:vr.right,controls,"
                    "tops:[...bar.children].map(e=>e.getBoundingClientRect().top)}})()")
        assert dims["controls"], dims
        assert all(e["right"] <= dims["right"] + 0.5 for e in dims["controls"]), (width, dims)
        assert all(e["right"] <= dims["verticalRight"] + 0.5 for e in dims["controls"]), (width, dims)
        if width == 1400:
            assert max(dims["tops"]) - min(dims["tops"]) < 12, dims
        c.shot(out / f"vertical_{width}.png")
    c.send("Emulation.setDeviceMetricsOverride", width=1400, height=900, deviceScaleFactor=1, mobile=False)
    c.pump(0.3)


def compact_results(c: Cdp, prep: str) -> None:
    """1360×860、兩個真量測：高度／不換行／分頁／選單與工具列可操作。"""
    c.send("Emulation.setDeviceMetricsOverride", width=1360, height=860, deviceScaleFactor=1, mobile=False)
    c.js("(async()=>{" + prep + "S.command('layout.resize',{kind:'lower',value:150})})()")
    c.wait("!document.querySelector('.analysis__lowerbody').hidden")
    c.js("document.querySelector('[data-result-tab=measure]').click()")
    c.wait("document.querySelectorAll('.results__table tr').length>=3 && !document.querySelector('.results__export').disabled")
    c.pump(0.2)
    dims = c.js("""(()=>{
        const visible=e=>e.getBoundingClientRect().height>0;
        const rows=[...document.querySelectorAll('.analysis__results tr')];
        const cells=rows.flatMap(r=>[...r.children]);
        const cursor=document.querySelector('.cursors__readout');
        return {rows:rows.map(r=>r.getBoundingClientRect().height),
            single:cells.every(e=>{const s=getComputedStyle(e),r=document.createRange();r.selectNodeContents(e);
                return s.whiteSpace==='nowrap' && r.getBoundingClientRect().height<=parseFloat(s.lineHeight)+1}),
            fonts:(()=>{const root=document.querySelector('.analysis__lower');
                const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);let n;
                while(n=walker.nextNode()) if(n.textContent.trim()&&parseFloat(getComputedStyle(n.parentElement).fontSize)<12.5)return false;
                return true})(),
            readout:cursor.getBoundingClientRect().height,values:cursor.children.length,
            parallel:visible(document.querySelector('.analysis__results'))&&visible(document.querySelector('.analysis__cursors')),
            actions:['clear','export'].every(k=>{const b=document.querySelector('.results__'+k);return visible(b)&&!b.disabled})};
    })()""")
    assert len(dims["rows"]) == 3 and max(dims["rows"]) <= 34, dims
    assert dims["single"] and dims["fonts"] and dims["parallel"] and dims["actions"], dims
    assert 0 < dims["readout"] <= 140 and dims["values"] >= 7, dims
    c.js("document.querySelector('.results__menu summary').click()")
    c.wait("document.querySelector('.results__menu').open")
    original_count = c.js("document.querySelector('[data-column=count]').checked")
    if not original_count:
        c.js("document.querySelector('[data-column=count]').click()")
    assert c.js("[...document.querySelectorAll('.analysis__results th')].some(e=>e.textContent==='次數')")
    if not original_count:
        c.js("document.querySelector('[data-column=count]').click()")
    c.js("document.querySelector('.results__menu summary').click()")
    # 用真正點擊進入匯出處理器，攔截 RPC 避免驗證產生使用者檔案。
    result = c.js("(async()=>{" + prep + """
        const old=B.call,list=S.state.measurements; let exported=0;
        B.call=async function(method,args){
            if(method==='export_measurements'){exported=args.rows.length;return {path:'驗證用.csv'}}
            return old.call(this,method,args);
        };
        try {
            document.querySelector('.results__export').click(); await Promise.resolve();
            document.querySelector('.results__clear').click();
            return {exported,cleared:S.state.measurements.length===0};
        } finally { B.call=old;S.set({measurements:list},'program'); }
    })()""")
    assert result == {"exported": 2, "cleared": True}, result
    # 寬版 peaks 仍獨佔；FFT 關閉時不可殘留峰值數字。
    c.js("document.querySelector('[data-result-tab=peaks]').click()")
    assert c.js("['results','cursors','peaks'].map(k=>!document.querySelector('.analysis__'+k).hidden)") == [False, False, True]
    c.js("(async()=>{" + prep + "S.command('fft.visible',false)})()")
    c.wait("document.querySelector('[data-result-tab=peaks]').textContent==='FFT 峰值'")
    c.js("document.querySelector('.analysis__lowertoggle').click()")
    c.wait("document.querySelector('.analysis__lowerbody').hidden")
    assert c.js(r"/量測 \d+／FFT 峰值 0／ΔX/.test(document.querySelector('.analysis__lowertoggle').textContent)")
    c.js("document.querySelector('.analysis__lowertoggle').click()")
    c.wait("!document.querySelector('.analysis__lowerbody').hidden")
    # 同寬度縮到 120px 即分頁；再驗窄視窗也切成單一面板。
    for width, height in ((1360, 120), (1024, 150)):
        c.send("Emulation.setDeviceMetricsOverride", width=width, height=860, deviceScaleFactor=1, mobile=False)
        c.js("(async()=>{" + prep + f"S.command('layout.resize',{{kind:'lower',value:{height}}})" + "})()")
        c.wait("document.querySelector('.analysis__lowerbody').dataset.resultTabbed==='true'")
        for key, cls in (("measure", "results"), ("cursor", "cursors"), ("peaks", "peaks")):
            c.js(f"document.querySelector('[data-result-tab={key}]').click()")
            state = c.js("(()=>{const keys=['results','cursors','peaks'];return keys.map(k=>"
                         "document.querySelector('.analysis__'+k).getBoundingClientRect().height>0)})()")
            assert state == [k == cls for k in ("results", "cursors", "peaks")], state
            assert c.js("document.querySelector('.results__actions').hidden") == (key != "measure")
    # 實測 B 寬度：1100×800，兩種展開側欄，X2 與 Y 負值的單位必須完整。
    c.send("Emulation.setDeviceMetricsOverride", width=1100, height=800, deviceScaleFactor=1, mobile=False)
    for side in (240, 360):
        c.js("(async()=>{" + prep + f"S.command('layout.resize',{{kind:'side',value:{side}}});S.command('layout.resize',{{kind:'lower',value:150}})" + "})()")
        c.wait(f"Math.abs(document.querySelector('.analysis__sidepanel').getBoundingClientRect().width-{side})<1")
        c.wait("(()=>{const b=document.querySelector('.analysis__lowerbody');return b.dataset.resultTabbed===String(b.clientWidth<820)})()")
        c.js("document.querySelector('[data-result-tab=cursor]').click()")
        dims = c.js("(async()=>{" + prep + """
            S.set({cursors:{...S.state.cursors,x2:999.5e-6}},'snap');
            const panel=document.querySelector('.analysis__cursors'),inputs=[...panel.querySelectorAll('input')];
            const samples=['-1.234 V','-500 mV','-12.34 mV'].map(value=>{
                inputs[3].value=value;inputs[3].dispatchEvent(new Event('change',{bubbles:true}));
                return {value:inputs[3].value,inputs:inputs.filter(e=>!e.parentElement.hidden).map(e=>({value:e.value,scroll:e.scrollWidth,client:e.clientWidth})),
                    panelScroll:panel.scrollWidth,panelClient:panel.clientWidth};
            });
            const walker=document.createTreeWalker(document.querySelector('.analysis__lower'),NodeFilter.SHOW_TEXT);let n;const small=[];
            while(n=walker.nextNode())if(n.textContent.trim()&&parseFloat(getComputedStyle(n.parentElement).fontSize)<12.5)small.push(n.textContent);
            const x2=inputs[1];
            return {value:x2.value,inputs:inputs.filter(e=>!e.parentElement.hidden).map(e=>({value:e.value,scroll:e.scrollWidth,client:e.clientWidth})),
                children:[...panel.children].filter(e=>!e.hidden).map(e=>({tag:e.tagName,cls:e.className,
                    scroll:e.scrollWidth,client:e.clientWidth,width:e.getBoundingClientRect().width,
                    right:e.getBoundingClientRect().right-panel.getBoundingClientRect().left})),
                panelScroll:panel.scrollWidth,panelClient:panel.clientWidth,small,samples};
        })()""")
        assert dims["value"] == "999.5 µs", (side, dims)
        assert all(e["scroll"] <= e["client"] + 1 for e in dims["inputs"]), (side, dims)
        assert dims["panelScroll"] <= dims["panelClient"] + 1 and not dims["small"], (side, dims)
        assert [s["value"] for s in dims["samples"]] == ["-1.234 V", "-500 mV", "-12.34 mV"], (side, dims)
        for sample in dims["samples"]:
            assert all(e["scroll"] <= e["client"] + 1 for e in sample["inputs"]), (side, sample)
            assert sample["panelScroll"] <= sample["panelClient"] + 1, (side, sample)
    c.js("document.querySelector('[data-result-tab=measure]').click()")
    c.send("Emulation.setDeviceMetricsOverride", width=1400, height=900, deviceScaleFactor=1, mobile=False)
    c.js("(async()=>{" + prep + "S.command('layout.reset','lower');S.command('layout.reset','side')})()")


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


if __name__ == "__main__":
    import ast
    ast.parse(Path(__file__).read_text(encoding="utf-8"))
    assert callable(compact_results) and callable(center_cursors)
    print("browser_analysis_checks self-check OK（CDP 斷言由 browser_check 執行）")
