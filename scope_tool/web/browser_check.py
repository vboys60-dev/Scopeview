"""真瀏覽器（Chrome headless + CDP）整條流程驗證：真 Server + FakeDriver，不開視窗。
執行：/opt/anaconda3/bin/python3 -m scope_tool.web.browser_check [截圖目錄]
需要 Chrome 與 websocket-client；失敗回傳非 0。"""
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
from scope_tool.web import browser_analysis_checks as analysis_checks, browser_measure_more_checks as more_checks
from scope_tool.web import browser_decode_checks as decode_checks, browser_slot_checks as slot_checks
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
def glass_smoke(c: Cdp) -> None:
    """驗文字合成對比、鍵盤操作、分析頁幾何及系統降級。"""
    run = "(async()=>{const {glassSmoke}=await import('/js/glass_smoke.js');return glassSmoke("
    check = lambda mode: c.js(run + json.dumps(mode) + ")})()")
    baseline = c.js("(()=>{const s=document.createElement('style');s.textContent='.tabs{width:auto;margin:0;padding:0 var(--sp-3)}.tab{padding:var(--sp-2) var(--sp-4);border-width:0 0 2px;border-style:solid}';document.head.append(s);const h=document.querySelector('.tabs').getBoundingClientRect().height;s.remove();return h})()")
    try:
        check("setup"); ratios = check("contrast")
        assert len(ratios) >= 12 and all(x["ratio"] >= 4.5 for x in ratios), ratios
        for kind in ("btn", "input", "toggle"):
            c.js(f"document.querySelector('[data-before={kind}]').focus()")
            for event in ("keyDown", "keyUp"):
                c.send("Input.dispatchKeyEvent", type=event, key="Tab", code="Tab", windowsVirtualKeyCode=9)
            assert c.js(f"document.activeElement.matches('[data-focus={kind}]') && parseFloat(getComputedStyle(document.activeElement).outlineWidth)>=2"), kind
        before = c.js("document.activeElement.checked")
        for event in ("keyDown", "keyUp"):
            c.send("Input.dispatchKeyEvent", type=event, key=" ", code="Space", windowsVirtualKeyCode=32)
        assert c.js("document.activeElement.checked") != before
        c.send("Emulation.setEmulatedMedia", features=[{"name": "prefers-contrast", "value": "more"}])
        assert all(x["alpha"] == 1 for x in check("solid"))
        c.send("Emulation.setEmulatedMedia", features=[{"name": "forced-colors", "value": "active"}])
        assert all(x["appearance"] == "auto" and x["thumb"] in ("none", "normal") for x in check("forced"))
    finally:
        c.send("Emulation.setEmulatedMedia", features=[])
        check("cleanup")
    try:
        c.js("document.querySelector('[data-tab=analysis]').click()")
        for width, height in ((1360, 860), (900, 600)):
            c.send("Emulation.setDeviceMetricsOverride", width=width, height=height, deviceScaleFactor=1, mobile=False)
            c.pump(.4)
            assert c.js(f"(()=>{{const e=document.querySelector('.tabs'),s=getComputedStyle(e);return e.getBoundingClientRect().height+parseFloat(s.marginTop)+parseFloat(s.marginBottom)}})() <= {baseline}+2")
            assert c.js("document.querySelector('.analysis__fftbar').getBoundingClientRect().height <= 40")
            assert c.js("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    finally:
        c.send("Emulation.setDeviceMetricsOverride", width=1400, height=900, deviceScaleFactor=1, mobile=False); c.pump(.4)
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
        c.wait("!!document.querySelector('#tab-capture .dcap') && document.querySelectorAll('#tabs .tab').length===3")
        c.shot(out / "01_home.png")
        click = "(t)=>{const b=[...document.querySelectorAll('button')].find(b=>b.textContent.replace(' ↕','').trim()===t);if(!b)throw Error('no button '+t);b.click();return true}"
        step("連線測試儀器", lambda: (c.js(f"({click})('測試儀器（模擬）')"), c.wait("document.body.innerText.includes('斷開模擬')")))
        c.shot(out / "02_connected.png")
        prep = "const B=(await import('/js/bridge.js')).bridge; const S=(await import('/js/analysis/store.js')).store;"
        step("資料截取同頁", lambda: c.wait("(()=>{const p=document.querySelector('#tab-capture');const buttons=[...p.querySelectorAll('button')].map(b=>b.textContent.trim());"
                                           "return !p.hidden&&buttons.includes('開始存圖')&&buttons.includes('開始擷取')&&!document.querySelector('[data-tab=screenshot]')"
                                           "&&document.querySelector('#tabs .tab').textContent.trim()==='資料截取'&&[...p.querySelectorAll('label.check')].some(l=>l.textContent.trim()==='CHAN1'&&l.querySelector('input[type=checkbox]')?.checked)})()"))
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
        def zoom_pan() -> None:
            c.send("Input.dispatchMouseEvent", type="mouseWheel", x=cx, y=cy, deltaX=0, deltaY=-120)
            c.pump(0.5)
            c.mouse("mousePressed", cx, cy); c.mouse("mouseMoved", cx - 150, cy); c.mouse("mouseReleased", cx - 150, cy)
            c.pump(0.8)
        step("滾輪縮放+拖曳平移", zoom_pan)
        c.shot(out / "05_zoom_pan.png")
        step("重設視圖(雙擊)", lambda: (c.send("Input.dispatchMouseEvent", type="mousePressed", x=cx, y=cy, button="left", clickCount=2),
                                     c.send("Input.dispatchMouseEvent", type="mouseReleased", x=cx, y=cy, button="left", clickCount=2), c.pump(0.5)))
        def cursors() -> None:
            c.js(f"(async()=>{{{prep} const f=S.state.file; const v=S.state.view; const w=v.t1-v.t0;"
                 "S.command('cursor.intent',{which:'x1',value:v.t0+w*0.3});S.command('cursor.intent',{which:'x2',value:v.t0+w*0.6});"
                 "S.command('cursor.intent',{which:'y1',value:1});S.command('cursor.intent',{which:'y2',value:-1});})()")
            c.pump(1.2)
        step("放置游標", cursors)
        c.shot(out / "06_cursors.png")
        step("游標讀值面板有文字", lambda: c.wait("document.body.innerText.match(/ΔX|Δt|ΔT|X1/)"))
        step("B 區收折仍可回中央並保留間距", lambda: analysis_checks.center_cursors(c, prep, click, out))
        step("P2a 框選範圍／Undo／20n／通道與游標不變", lambda: analysis_checks.p2a_view(c, prep, click, out))
        step("P3a 來源／Y 真值／摘要移除／禁用模式", lambda: analysis_checks.p3a_markers(c, prep))
        step("P3b 游標結果表／尺寸／TSV 複製", lambda: analysis_checks.p3b_markers(c, prep))
        from scope_tool.web.browser_marker_checks import p3b2_zoom, dock_layout, marker_add_button, marker_rightclick
        step("P3b-2 垂直框選／一次 Undo／游標物理值", lambda: p3b2_zoom(c, prep))
        step("Marker 獨立點按鈕可連續新增", lambda: marker_add_button(c, prep))
        step("Marker 主圖右鍵選單新增", lambda: marker_rightclick(c, prep))
        step("P4 版面 C 右側欄／窄版退回底部", lambda: dock_layout(c, prep))
        step("P2b2 選取通道2／中心電位／左軸電壓與顏色", lambda: analysis_checks.p2b2_vertical(c, prep, click, out))
        step("通道全域收折／圖區高度／Zoom 位置", lambda: analysis_checks.channel_collapse(c))
        step("P2b2 Vertical 1400／1000 控件無截斷", lambda: analysis_checks.vertical_bounds(c, prep, click, out))
        step("通道 dx 位移", lambda: (c.js(f"(async()=>{{{prep} S.updateChannel(S.state.channels[1].name,{{time_offset:(S.state.view.t1-S.state.view.t0)*0.05}},'user')}})()"), c.pump(1)))
        def measure() -> None:
            for t in ("Frequency", "Vp-p"):
                c.js(f"({click})({json.dumps(t)})")
            c.pump(2)
        step("新增量測", measure)
        c.shot(out / "07_measure.png")
        step("量測結果表有數值", lambda: c.wait("/\\d/.test(document.querySelector('.results')?.innerText||document.body.innerText)"))
        step("P2b3 緊湊結果／分頁／欄位／清除與匯出", lambda: analysis_checks.compact_results(c, prep)); step("Vmid 量測", lambda: more_checks.measure_more(c, prep))
        def fft() -> None:
            c.js("(()=>{const b=[...document.querySelectorAll('#tab-analysis input[type=checkbox]')].find(i=>/FFT/i.test(i.closest('label,div')?.textContent||''));if(!b)throw Error('no FFT checkbox');b.click()})()")
            c.wait("(async()=>{const S=(await import('/js/analysis/store.js')).store;return S.state.fftResult&&S.state.fftResult.ok})()", 20)
            c.pump(1)
        step("FFT", fft)
        c.shot(out / "08_fft.png")
        def fft_label_bounds() -> None:
            for end in (False, True):
                dims = c.js("(()=>{const b=document.querySelector('.analysis__fftbar');"
                            f"b.scrollLeft={'b.scrollWidth' if end else '0'};"
                            "const r=b.getBoundingClientRect();return {top:r.top,bottom:r.bottom,height:r.height,"
                            "plot:document.querySelector('.analysis__fftplot').getBoundingClientRect().height,"
                            "labels:[...b.querySelectorAll('label')].filter(e=>e.getClientRects().length).map(e=>{const t=e.getBoundingClientRect();"
                            "return {text:e.textContent.trim(),top:t.top,bottom:t.bottom,font:parseFloat(getComputedStyle(e).fontSize)}})}})()")
                assert len(dims["labels"]) == 4, dims
                assert dims["height"] <= 40 and dims["plot"] >= 120, dims
                assert all(e["top"] >= dims["top"] and e["bottom"] <= dims["bottom"]
                           and e["font"] >= 12 for e in dims["labels"]), dims
        def layout_check() -> None:
            for width, height in ((1360, 860), (900, 600)):
                c.send("Emulation.setDeviceMetricsOverride", width=width, height=height, deviceScaleFactor=2, mobile=False)
                c.js(f"(async()=>{{{prep} for(const k of ['side','lower','fft'])S.command('layout.reset',k);S.command('fft.visible',true)}})()")
                c.pump(0.5)
                dims = c.js("(()=>{const q=s=>document.querySelector('.analysis__'+s),h=s=>q(s).getBoundingClientRect().height;"
                            "return {main:h('main')-30,fft:h('fftplot'),side:q('sidepanel').getBoundingClientRect().width,"
                            "tabs:!q('plotTabs').hidden,tabHeight:h('plotTabs'),dpr:q('main').querySelector('canvas').width/q('main').clientWidth}})()")
                assert dims["main"] >= 240 and dims["tabs"] == (width == 900), dims
                assert abs(dims["dpr"] - 2) < 0.02, dims
                if width == 1360:
                    fft_label_bounds()
                    c.js(f"(async()=>{{{prep} S.command('fft.visible',false)}})()")
                    c.pump(0.2)
                    assert c.js("!document.querySelector('.analysis__overview').hidden")
                    c.js(f"(async()=>{{{prep} S.command('fft.visible',true)}})()")
                    c.pump(0.2)
                    c.js("(()=>{const t=document.querySelector('.analysis__lowertoggle');if(t.getAttribute('aria-expanded')==='true')t.click()})()")
                    c.pump(0.2)
                    c.js("document.querySelector('.analysis__lowertoggle').click()")
                    c.pump(0.2)
                    assert c.js("document.querySelector('.analysis__lower').getBoundingClientRect().height") >= 120
                    c.js(f"(async()=>{{{prep} S.command('layout.reset','lower')}})()")
                    c.pump(0.2)
                    assert dims["fft"] >= 120, dims
                    for kind, delta in (("side", 30), ("fft", -30), ("lower", -30)):
                        c.js(f"(async()=>{{{prep} S.command('fft.visible',{str(kind != 'lower').lower()});S.command('layout.resize',{{kind:'{kind}',value:180}})}})()")
                        c.pump(0.2)
                        box = c.js(f"(()=>{{const e=document.querySelector('.analysis__splitter--{kind}'),r=e.getBoundingClientRect(),x=r.left+(e.classList.contains('analysis__splitter--side')?2:r.width/{2 if kind == 'lower' else 4}),y=r.top+(e.classList.contains('analysis__splitter--side')?40:r.height/2),hit=document.elementFromPoint(x,y);return {{x,y,v:+e.getAttribute('aria-valuenow'),max:+e.getAttribute('aria-valuemax'),hit:hit?.className,free:hit===e}}}})()")
                        assert box["free"] and box["max"] >= box["v"] + abs(delta), (kind, box)
                        c.mouse("mousePressed", box["x"], box["y"])
                        c.mouse("mouseMoved", box["x"] + (delta if kind == "side" else 0), box["y"] + (0 if kind == "side" else delta), buttons=1)
                        c.pump(0.2)
                        c.mouse("mouseReleased", box["x"] + (delta if kind == "side" else 0), box["y"] + (0 if kind == "side" else delta))
                        now = c.js(f"+document.querySelector('.analysis__splitter--{kind}').getAttribute('aria-valuenow')")
                        assert now > box["v"] and now >= (180 if kind == "side" else 160 if kind == "fft" else 120), (kind, box, now)
                        assert c.js("document.querySelector('.analysis__main').getBoundingClientRect().height-30") >= 240
                        if kind != "lower":
                            assert c.js("document.querySelector('.analysis__fftplot').getBoundingClientRect().height") >= 120
                else:
                    assert dims["side"] == 36 and dims["tabHeight"] >= 28, dims
                    c.js("document.querySelector('[data-pane=fft]').click()")
                    c.pump(0.2)
                    assert c.js("document.querySelector('.analysis__fftplot').getBoundingClientRect().height") >= 120
                    fft_label_bounds()
                    c.js("document.querySelector('[data-pane=wave]').click()")
                c.js(f"(async()=>{{{prep} S.command('fft.visible',true)}})()")
                for kind, body in (("side", "side"), ("lower", "lowerbody"), ("fft", "fft")):
                    if kind == "fft" and width == 900:
                        continue  # 分頁共用空間，FFT splitter 禁用
                    c.js(f"document.querySelector('.analysis__splitter--{kind} button').click()")
                    c.pump(0.2)
                    assert c.js(f"(()=>{{const b=document.querySelector('.analysis__splitter--{kind} button');return (b.getAttribute('aria-expanded')==='false')===document.querySelector('.analysis__{body}').hidden}})()")
                c.shot(out / f"layout_{width}x{height}.png")
        step("P2b 多尺寸／splitter／DPR／共用收折", layout_check)
        from scope_tool.web.browser_fft_checks import fft_page
        step("FFT 分頁三尺寸／控制列／峰表", lambda: fft_page(c, prep))
        from scope_tool.web import browser_menu_checks as menu_c, browser_drag_checks as drag_c, browser_grid_checks as grid_c
        step("選單：⋮／檔案▾／分析▾", lambda: menu_c.menu_checks(c, prep)); step("量測拖到通道列", lambda: drag_c.drag_checks(c, prep))
        step("分割格線", lambda: grid_c.grid_checks(c, prep))
        from scope_tool.web.browser_float_checks import float_panel
        step("浮動面板／拖曳／縮放／停靠／窄版／字體", lambda: float_panel(c, prep))
        step("glass_smoke 對比／鍵盤／幾何／降級", lambda: glass_smoke(c))
        step("I3C 解碼分頁／CSV／尺寸／過期設定", lambda: decode_checks.decode_page(c, prep, out, prof))
        step("開含 NaN 的 CSV", lambda: decode_checks.nan_csv(c, prep, canvas_ink, out, prof))
        step("多檔比對／換槽／移除／量測游標保留", lambda: slot_checks.slot_page(c, prep, click, out, prof))
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
