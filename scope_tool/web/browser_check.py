"""真瀏覽器（Chrome headless + CDP）整條流程驗證：真 Server + FakeDriver，不開視窗。

執行：/opt/anaconda3/bin/python3 -m scope_tool.web.browser_check [截圖目錄]
需要 Chrome 與 websocket-client。截圖預設存到暫存目錄；console 錯誤或步驟失敗則結束碼非 0。
"""
from __future__ import annotations

import base64
import json
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import websocket  # websocket-client

from scope_tool import config as config_mod
from scope_tool.web.analysis_api import Analysis
from scope_tool.web.api import Api
from scope_tool.web.jobs import Jobs
from scope_tool.web.server import Server

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9222


class Cdp:
    def __init__(self, port: int) -> None:
        for _ in range(50):
            try:
                tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json"))
                url = next(t for t in tabs if t["type"] == "page")["webSocketDebuggerUrl"]
                break
            except Exception:
                time.sleep(0.2)
        else:
            raise RuntimeError("連不上 Chrome CDP")
        self.ws, self.n, self.errors, self.events = websocket.create_connection(url, suppress_origin=True), 0, [], []
        for m in ("Runtime.enable", "Log.enable", "Page.enable"):
            self.send(m)

    def send(self, method: str, **params):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            self._note(msg)
            if msg.get("id") == self.n:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg["result"]

    def _note(self, msg: dict) -> None:
        m, p = msg.get("method"), msg.get("params", {})
        if m == "Runtime.exceptionThrown":
            d = p["exceptionDetails"]
            self.errors.append("exception: " + (d.get("exception", {}).get("description") or d["text"]))
        elif m == "Runtime.consoleAPICalled" and p["type"] in ("error", "warning", "assert"):
            self.errors.append(f"console.{p['type']}: " + " ".join(str(a.get("value", a.get("description"))) for a in p["args"]))
        elif m == "Log.entryAdded" and "willReadFrequently" not in p["entry"]["text"] and "favicon" not in p["entry"].get("url", "") and p["entry"]["level"] in ("error", "warning"):
            self.errors.append(f"log.{p['entry']['level']}: {p['entry']['text']} {p['entry'].get('url', '')}")

    def pump(self, sec: float) -> None:
        self.ws.settimeout(0.1)
        end = time.time() + sec
        while time.time() < end:
            try:
                self._note(json.loads(self.ws.recv()))
            except Exception:
                pass
        self.ws.settimeout(None)

    def js(self, expr: str):
        r = self.send("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
        if "exceptionDetails" in r:
            raise RuntimeError(f"JS 失敗：{r['exceptionDetails'].get('exception', {}).get('description', r['exceptionDetails']['text'])}")
        return r["result"].get("value")

    def wait(self, expr: str, sec: float = 15):
        end = time.time() + sec
        while time.time() < end:
            v = self.js(expr)
            if v:
                return v
            self.pump(0.3)
        raise TimeoutError(expr)

    def shot(self, path: Path) -> None:
        path.write_bytes(base64.b64decode(self.send("Page.captureScreenshot", format="png")["data"]))

    def mouse(self, typ: str, x: float, y: float, **kw) -> None:
        self.send("Input.dispatchMouseEvent", type=typ, x=x, y=y, button="left", clickCount=1, **kw)


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(tempfile.mkdtemp())
    out.mkdir(parents=True, exist_ok=True)
    jobs = Jobs()
    srv = Server(Api(jobs, cfg=dict(config_mod.DEFAULTS), persist=False), Analysis(), jobs, token="tok")
    srv.start()
    prof = tempfile.mkdtemp()
    chrome = subprocess.Popen([CHROME, "--headless=new", f"--remote-debugging-port={PORT}", f"--user-data-dir={prof}",
                               "--window-size=1400,900", "--no-first-run", "about:blank"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    steps: list[tuple[str, str]] = []

    def step(name: str, fn) -> None:
        try:
            fn()
            steps.append((name, "OK"))
        except Exception as e:  # 單步失敗只記錄，繼續下一步
            steps.append((name, f"FAIL {e}"))

    try:
        c = Cdp(PORT)
        c.send("Emulation.setDeviceMetricsOverride", width=1400, height=900, deviceScaleFactor=1, mobile=False)
        c.send("Page.navigate", url=srv.url)
        c.pump(1.5)
        c.wait("document.querySelectorAll('#tabs .tab').length===3")
        c.shot(out / "01_home.png")
        click = "(t)=>{const b=[...document.querySelectorAll('button')].find(b=>b.textContent.replace(' ↕','').trim()===t);if(!b)throw Error('no button '+t);b.click();return true}"
        step("連線測試儀器", lambda: (c.js(f"({click})('測試儀器（模擬）')"), c.wait("document.body.innerText.includes('斷開模擬')")))
        c.shot(out / "02_connected.png")
        # 擷取（經 bridge，同 UI 的 job 路徑）；通道 2 條、4000 點
        prep = "const B=(await import('/js/bridge.js')).bridge; const S=(await import('/js/analysis/store.js')).store;"
        c.js("document.querySelector('[data-tab=capture]').click()")
        c.shot(out / "03_capture_tab.png")
        cap: dict = {}
        step("擷取波形", lambda: cap.update(c.js(f"(async()=>{{{prep} return await B.job('capture',{{directory:{json.dumps(prof)},name:'w',"
                                                 "channels:['CHAN1','CHAN2'],points:20000,retrigger:false})})()")))
        c.js("document.querySelector('[data-tab=analysis]').click()")
        step("開檔(file.open+path)", lambda: (c.js(f"(async()=>{{{prep} S.command('file.open',{{path:{json.dumps(cap.get('path', ''))}}})}})()"),
                                           c.wait("(async()=>{const S=(await import('/js/analysis/store.js')).store;return S.state.channels.length>=2})()")))
        c.pump(1.5)
        canvas_ink = ("(()=>{let best=0;for(const cv of document.querySelectorAll('#tab-analysis canvas')){const w=cv.width,h=cv.height;if(w<300||h<150)continue;"
                      "const d=cv.getContext('2d').getImageData(0,0,w,h).data;const bg=[d[0],d[1],d[2]];let n=0;"
                      "for(let i=0;i<d.length;i+=16)if(Math.abs(d[i]-bg[0])+Math.abs(d[i+1]-bg[1])+Math.abs(d[i+2]-bg[2])>60)n++;best=Math.max(best,n)}return best})()")
        step("主圖有非空白像素", lambda: c.wait(f"{canvas_ink}>200"))
        c.shot(out / "04_analysis_loaded.png")
        rect = c.js("(()=>{let b=null;for(const cv of document.querySelectorAll('#tab-analysis canvas')){const r=cv.getBoundingClientRect();if(!b||r.width*r.height>b.w*b.h)b={x:r.x,y:r.y,w:r.width,h:r.height}}return b})()")
        cx, cy = rect["x"] + rect["w"] / 2, rect["y"] + rect["h"] / 2
        # 滾輪縮放 + 拖曳平移
        def zoom_pan() -> None:
            c.send("Input.dispatchMouseEvent", type="mouseWheel", x=cx, y=cy, deltaX=0, deltaY=-120)
            c.pump(0.5)
            c.mouse("mousePressed", cx, cy); c.mouse("mouseMoved", cx - 150, cy); c.mouse("mouseReleased", cx - 150, cy)
            c.pump(0.8)
        step("滾輪縮放+拖曳平移", zoom_pan)
        c.shot(out / "05_zoom_pan.png")
        step("重設視圖(雙擊)", lambda: (c.send("Input.dispatchMouseEvent", type="mousePressed", x=cx, y=cy, button="left", clickCount=2),
                                     c.send("Input.dispatchMouseEvent", type="mouseReleased", x=cx, y=cy, button="left", clickCount=2), c.pump(0.5)))
        # 游標：經 intent 指令放兩條 X、兩條 Y，再看游標面板
        def cursors() -> None:
            c.js(f"(async()=>{{{prep} const f=S.state.file; const v=S.state.view; const w=v.t1-v.t0;"
                 "S.command('cursor.intent',{which:'x1',value:v.t0+w*0.3});S.command('cursor.intent',{which:'x2',value:v.t0+w*0.6});"
                 "S.command('cursor.intent',{which:'y1',value:1});S.command('cursor.intent',{which:'y2',value:-1});})()")
            c.pump(1.2)
        step("放置游標", cursors)
        c.shot(out / "06_cursors.png")
        step("游標讀值面板有文字", lambda: c.wait("document.body.innerText.match(/ΔX|Δt|ΔT|X1/)"))
        def center_cursors() -> None:
            result = c.js(f"(async()=>{{{prep} const v=S.state.view,w=v.t1-v.t0,mid=(v.t0+v.t1)/2;"
                          "S.set({cursors:{x1:v.t0-w,x2:v.t0-w*0.8,y1:1,y2:-1}},'user');"
                          "document.querySelector('.analysis__lowertoggle').click();"
                          "const b=[...document.querySelectorAll('.analysis__chanbar button')].find(b=>b.textContent==='回中央');"
                          "const visible=!!b&&b.getBoundingClientRect().height>0&&!b.disabled; b.click();"
                          "const q=S.state.cursors;return {visible,hidden:document.querySelector('.analysis__lowerbody').hidden,"
                          "center:Math.abs((q.x1+q.x2)/2-mid)/w,gap:Math.abs((q.x2-q.x1)/w-0.2),y:q.y1===1&&q.y2===-1}})()")
            assert result["visible"] and result["hidden"] and result["y"], result
            assert result["center"] < 1e-12 and result["gap"] < 1e-12, result
            c.shot(out / "06_center_collapsed.png")
            c.js("document.querySelector('.analysis__lowertoggle').click()")
        step("B 區收折仍可回中央並保留間距", center_cursors)
        # P2a：送真實滑鼠事件，驗範圍與只改 view；JS 區塊不用 f-string 避免括號誤植。
        def p2a_view() -> None:
            before = c.js("(async()=>{" + prep + " const cv=document.querySelector('.analysis__main canvas');"
                          "cv.scrollIntoView({block:'nearest'});const b=cv.getBoundingClientRect();"
                          "const M=await import('/js/analysis/mainplot.js'),H=await import('/js/analysis/handles.js');"
                          "let r=M.layoutRect(b.width,b.height);"
                          "const V=await import('/js/analysis/voltage.js'),g=cv.getContext('2d');g.font='11px sans-serif';"
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
            assert after["channels"] == before["channels"] and after["cursors"] == before["cursors"], after
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
        step("P2a 框選範圍／Undo／20n／通道與游標不變", p2a_view)
        # P2b2：截取真正 Canvas fillText，驗證左軸實際文字／顏色與欄位隔離。
        def p2b2_vertical() -> None:
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
        step("P2b2 選取通道2／中心電位／左軸電壓與顏色", p2b2_vertical)
        # 兩通道的 Vertical 控件必須完整落在列容器內；寬版維持單列。
        def vertical_bounds() -> None:
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
        step("P2b2 Vertical 1400／1000 控件無截斷", vertical_bounds)
        # 不同 dx（通道 2 位移）
        step("通道 dx 位移", lambda: (c.js(f"(async()=>{{{prep} S.updateChannel(S.state.channels[1].name,{{time_offset:(S.state.view.t1-S.state.view.t0)*0.05}},'user')}})()"), c.pump(1)))
        # 量測：頻率／Vp-p 按鈕
        def measure() -> None:
            for t in ("頻率", "Vp-p"):
                c.js(f"({click})({json.dumps(t)})")
            c.pump(2)
        step("新增量測", measure)
        c.shot(out / "07_measure.png")
        step("量測結果表有數值", lambda: c.wait("/\\d/.test(document.querySelector('.results')?.innerText||document.body.innerText)"))
        # FFT：找工具列的 FFT 按鈕
        def fft() -> None:
            c.js("(()=>{const b=[...document.querySelectorAll('#tab-analysis input[type=checkbox]')].find(i=>/FFT/i.test(i.closest('label,div')?.textContent||''));if(!b)throw Error('no FFT checkbox');b.click()})()")
            c.wait("(async()=>{const S=(await import('/js/analysis/store.js')).store;return S.state.fftResult&&S.state.fftResult.ok})()", 20)
            c.pump(1)
        step("FFT", fft)
        c.shot(out / "08_fft.png")
        # 880×700：側欄保留內容高度與 30vh 上限，FFT 開關皆採自然結果區高度。
        def narrow_layout() -> None:
            c.send("Emulation.setDeviceMetricsOverride", width=880, height=700, deviceScaleFactor=1, mobile=False)
            for on in (True, False):
                c.js(f"(async()=>{{{prep} S.command('fft.visible', {str(on).lower()})}})()")
                c.pump(0.4)
                dims = c.js("(()=>{const side=document.querySelector('.analysis__side'),lower=document.querySelector('.analysis__lower');"
                            "return {side:side.getBoundingClientRect().height,flex:getComputedStyle(side).flex,"
                            "max:getComputedStyle(side).maxHeight,lower:lower.getBoundingClientRect().height}})()")
                assert 26 < dims["side"] <= 210, dims
                assert dims["flex"] == "0 1 auto" and dims["max"] == "210px", dims
                before = dims["lower"]
                c.js("document.querySelector('.analysis__lower').style.height='auto'")
                after = c.js("document.querySelector('.analysis__lower').getBoundingClientRect().height")
                c.js("document.querySelector('.analysis__lower').style.height=''")
                assert abs(before - after) < 0.1, (before, after)
                print(f"880×700 FFT={on}: {dims}, height:auto={after}")
            c.shot(out / "880x700.png")
        step("880×700 窄版側欄與 FFT 結果區", narrow_layout)
        # NaN 缺口 CSV
        nanp = Path(prof) / "nan.csv"
        nanp.write_text("Time(s),CH1(V)\n" + "".join(f"{i * 1e-6},{'nan' if 40 <= i < 60 else (i % 20) / 10}\n" for i in range(200)), "utf-8")
        step("開含 NaN 的 CSV", lambda: (c.js(f"(async()=>{{{prep} S.command('file.open',{{path:{json.dumps(str(nanp))}}})}})()"), c.pump(2), c.wait(f"{canvas_ink}>100")))
        c.shot(out / "09_nan_csv.png")
        # 窄視窗版面
        c.send("Emulation.setDeviceMetricsOverride", width=1000, height=700, deviceScaleFactor=1, mobile=False)
        c.pump(1)
        c.shot(out / "10_narrow.png")
        c.pump(0.5)
        print("steps:")
        for n, s in steps:
            print(f"  {n}: {s}")
        print("console 錯誤：", *c.errors, sep="\n  " if c.errors else " 無")
        print("截圖目錄：", out)
        assert not c.errors and all(s == "OK" for _, s in steps), "browser_check 失敗"
        print("browser_check OK")
    finally:
        chrome.terminate()
        srv.stop()


if __name__ == "__main__":
    main()
