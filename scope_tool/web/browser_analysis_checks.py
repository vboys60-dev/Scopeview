"""L8：browser_check 的分析頁 CDP 驗證；由主流程注入已開啟檔案的瀏覽器。"""
from __future__ import annotations

from scope_tool.web.browser_marker_checks import p3a_markers, p3b_markers

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
                const b=[...document.querySelectorAll('.analysis__toolbar button')].find(b=>b.textContent==='X軸Maker歸位');
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
                  "const toggle=document.querySelector('.chanbar__toggle');if(toggle.getAttribute('aria-expanded')!=='true')toggle.click();"
                  "const name=old[1].name;document.querySelectorAll('.analysis__chanbar .chip')[1].click();"
                  "const active=document.querySelectorAll('.analysis__chanbar .chip')[1].classList.contains('chip--selected');"
                  "S.updateChannel(name,{scale:0.002},'user');const before=S.state.channels;"
                  "const proto=CanvasRenderingContext2D.prototype,original=proto.fillText,draws=[];"
                  "proto.fillText=function(t,x,y,...a){draws.push({t,color:this.fillStyle});return original.call(this,t,x,y,...a)};"
                  "try{const i=document.querySelectorAll('.analysis__chanbar .chanbar__col')[1].querySelector('[data-vertical=position]');i.value='-4m';"
                  "i.dispatchEvent(new Event('change',{bubbles:true}));"
                  "const after=S.state.channels,cv=document.querySelector('.analysis__main canvas'),g=cv.getContext('2d');"
                  "g.fillStyle=after[1].color;return {active,name,position:after[1].position,"
                  "others:before.every((v,k)=>k===1||JSON.stringify(v)===JSON.stringify(after[k])),"
                  "axis:draws.some(d=>d.t==='2.0 mV'&&d.color===g.fillStyle)}"
                  "}finally{proto.fillText=original;S.set({channels:old,selected},'program')}})()")
    assert result["active"] is True, result
    assert result["position"] == 2 and result["others"] and result["axis"], result


def vertical_bounds(c: Cdp, prep: str, click: str, out: Path) -> None:
    for width in (1400, 1000):
        c.send("Emulation.setDeviceMetricsOverride", width=width, height=900, deviceScaleFactor=1, mobile=False)
        c.pump(0.3)
        dims = c.js("(async()=>{" + prep + """
            const bar=document.querySelector('.analysis__chanbar'),old=S.state.channels;
            const toggle=bar.querySelector('.chanbar__toggle');
            if(toggle.getAttribute('aria-expanded')!=='true')toggle.click();
            await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
            const columns=[...bar.querySelectorAll('.chanbar__col')];
            const lefts=()=>[...bar.querySelectorAll('.chip')].map(e=>e.getBoundingClientRect().left);
            const before=lefts();
            try {
                S.updateChannel(old[0].name,{scale:0.0005},'user');
                return {before,after:lefts(),scrollWidth:document.documentElement.scrollWidth,width:innerWidth,
                    columns:columns.map(col=>{const r=col.getBoundingClientRect();
                        return {left:r.left,right:r.right,top:r.top,
                            controls:[...col.querySelectorAll('.vertical input,.vertical button')].map(e=>{
                                const b=e.getBoundingClientRect();return {text:e.title,left:b.left,right:b.right}})}})};
            } finally { S.set({channels:old},'program'); }
        })()""")
        assert dims["columns"], dims
        for col in dims["columns"]:
            assert col["controls"], (width, col)
            assert all(e["right"] <= col["right"] + 0.5 and e["left"] >= col["left"] - 0.5
                       for e in col["controls"]), (width, col)
        tops = [col["top"] for col in dims["columns"]]
        assert max(tops) - min(tops) < 1, (width, dims)
        assert dims["scrollWidth"] <= dims["width"] + 1, (width, dims)
        assert dims["before"] == dims["after"], (width, dims)
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
    assert 0 <= dims["readout"] <= 140 and dims["values"] >= 7, dims
    c.js("document.querySelector('.results__menu summary').click()")
    c.wait("document.querySelector('.results__menu').open")
    original_count = c.js("document.querySelector('[data-column=count]').checked")
    if not original_count:
        c.js("document.querySelector('[data-column=count]').click()")
    assert c.js("[...document.querySelectorAll('.analysis__results th')].some(e=>e.textContent==='Count')")
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
            document.querySelector('.results__export').click();
            // 匯出先選資料夾：無原生對話框時是頁內 <dialog> prompt，填路徑後按確定
            for(let i=0;i<50&&!document.querySelector('dialog[open] input');i++) await new Promise(r=>setTimeout(r,20));
            document.querySelector('dialog[open] input').value='/tmp';
            document.querySelector('dialog[open] .btn--primary').click();
            for(let i=0;i<50&&!exported;i++) await new Promise(r=>setTimeout(r,20));
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
            assert state == [k == cls for k in ("results", "cursors", "peaks")], (width, height, key, state)
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


if __name__ == "__main__":
    import ast
    ast.parse(Path(__file__).read_text(encoding="utf-8"))
    assert callable(compact_results) and callable(center_cursors)
    print("browser_analysis_checks self-check OK（CDP 斷言由 browser_check 執行）")


def channel_collapse(c: Cdp) -> None:
    result = c.js("""(async()=>{
        const bar=document.querySelector('.analysis__chanbar'),toggle=bar.querySelector('.chanbar__toggle');
        const initial=toggle.getAttribute('aria-expanded')==='true';
        const frame=()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));
        const columns=()=>[...bar.querySelectorAll('.chanbar__col')];
        const snapshot=()=>({bar:bar.getBoundingClientRect().height,
            plot:document.querySelector('.analysis__main').getBoundingClientRect().height,
            widths:columns().map(e=>e.getBoundingClientRect().width)});
        try {
            if(!initial)toggle.click(); await frame(); const expanded=snapshot();
            toggle.click(); await frame(); const collapsed=snapshot();
            return {expanded,collapsed,hidden:columns().every(e=>e.querySelector('.vertical').hidden),
                aria:toggle.getAttribute('aria-expanded'),saved:localStorage.getItem('analysis.vertical.expanded'),
                zoom:!!document.querySelector('.analysis__horizontal .analysis__preview input[type=checkbox]'),
                toolbarZoom:[...document.querySelectorAll('.analysis__toolbar label')].some(e=>e.textContent.trim()==='Zoom'),
                summary:!!document.querySelector('.analysis__cursorSummary')};
        } finally { if((toggle.getAttribute('aria-expanded')==='true')!==initial)toggle.click(); await frame(); }
    })()""")
    assert result['hidden'] and result['aria'] == 'false' and result['saved'] == 'false', result
    assert result['expanded']['bar'] > result['collapsed']['bar'], result
    assert result['expanded']['plot'] < result['collapsed']['plot'], result
    assert result['expanded']['widths'] == result['collapsed']['widths'], result
    assert result['zoom'] and not result['toolbarZoom'] and not result['summary'], result
