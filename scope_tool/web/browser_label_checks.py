"""波 3A B1–B6 獨立 CDP 驗收；由主控提供頁面，不啟動伺服器或瀏覽器。# 待真機驗證。"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING
from scope_tool.web.i2c_synth import fixture

if TYPE_CHECKING:
    from scope_tool.web.browser_check import Cdp

CV = "document.querySelector('.analysis__main canvas')"
LAYOUT = f'{CV}.labelLayout()'
# 嚴格相交，容許框邊接觸。
OVERLAP = '(a,b)=>a.x<b.x+b.w&&b.x<a.x+a.w&&a.y<b.y+b.h&&b.y<a.y+a.h'


def label_checks(c: Cdp, prep: str, directory: str) -> list[dict]:
    """DPR 1／2、兩種尺寸；回傳並寫入左邊距紀錄，>100 只記錄不修。"""
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    source = out / f'labels_{time.strftime("%Y%m%d_%H%M%S")}.csv'
    roles = fixture(source)['channels']
    size = c.js('({w:innerWidth,h:innerHeight,dpr:devicePixelRatio})')
    margins = []

    def state(code: str):
        return c.js('(async()=>{' + prep + code + '})()')

    def command(code: str) -> None:
        state(code)
        c.pump(0.25)

    def clean_layout() -> None:
        assert c.js(f'''(()=>{{const hit={OVERLAP};return {LAYOUT}.every(r=>{{
          const boxes=[...r.labels,...r.readouts,...(r.plus?[r.plus]:[])];
          return boxes.every((a,i)=>a.x>=r.row.l&&a.x+a.w<=r.row.l+r.row.w&&a.y>=r.row.t&&a.y+a.h<=r.row.t+r.row.h&&
            boxes.slice(i+1).every(b=>!hit(a,b))&&r.fixed.every(b=>!hit(a,b)));}})}})()''')

    def pixel() -> list:
        return c.js(f'''(()=>{{const cv={CV},b=cv.labelLayout()[0].labels[0],k=cv.width/cv.clientWidth;
          return Array.from(cv.getContext('2d').getImageData(Math.floor((b.x+2)*k),Math.floor((b.y+3)*k),1,1).data)}})()''')

    def ink() -> int:
        """標籤框內暗像素數：hover 淡出（alpha .15）後必與原狀不同，不受單點取樣落在波形上影響。"""
        return c.js(f'''(()=>{{const cv={CV},b=cv.labelLayout()[0].labels[0],k=cv.width/cv.clientWidth,
          d=cv.getContext('2d').getImageData(Math.floor(b.x*k),Math.floor(b.y*k),Math.floor(b.w*k),Math.floor(b.h*k)).data;
          let n=0;for(let i=0;i<d.length;i+=4)if(d[i]+d[i+1]+d[i+2]<200)n++;return n}})()''')

    def point() -> dict:
        return c.js(f'''(()=>{{const cv={CV},r=cv.getBoundingClientRect(),b=cv.labelLayout()[0].labels[0];
          return {{x:r.left+b.x+2,y:r.top+b.y+3}}}})()''')

    try:
        for dpr in (1, 2):
            for width, height in ((1400, 900), (1000, 700)):
                c.send('Emulation.setDeviceMetricsOverride', width=width, height=height,
                       deviceScaleFactor=dpr, mobile=False)
                command("S.command('tab.select','analysis');S.command('fft.visible',false);")
                gen = state('return S.get().file?.gen??null')
                command(f"S.command('file.open',{{path:{json.dumps(str(source))}}});")
                c.wait('(async()=>{' + prep + f'return !!S.get().file&&S.get().file.gen!=={json.dumps(gen)}' + '})()', 30)
                c.wait(f'!!{CV}?.labelLayout')
                # 假通道（Mem1.*）的 /wave 一律改抓 CHAN1，避免伺服器 400 污染 console。
                command("if(!window.__fw){window.__fw=B.fetchWave;"
                        "B.fetchWave=(o)=>window.__fw({...o,ch:String(o.ch).startsWith('Mem1.')?'CHAN1':o.ch});}")
                command("window.__labelBase=S.get().channels;S.set({grids:{n:1,assign:{}},cursors:{x1:null,x2:null,y1:null,y2:null},"
                        "channels:Array.from({length:4},(_,i)=>({...S.get().channels[i%2],name:i<2?S.get().channels[i].name:'Mem1.Function '+i,"
                        "position:0,scale:.0025,visible:true})),selected:S.get().channels[0].name});")
                # B1：四個同零位、長原名、-12.5mV 刻度；8 格迫使把手分欄。
                for n in (1, 8):
                    command(f"S.set({{grids:{{n:{n},assign:Object.fromEntries(S.get().channels.map(ch=>[ch.name,0]))}}}});")
                    clean_layout()
                    left = c.js(f'{CV}.gridRect().l')
                    margins.append(dict(dpr=dpr, width=width, height=height, grids=n, left=left,
                                        exceeds_target=left > 100))
                command('S.set({grids:{n:1,assign:{}},channels:[S.get().channels[0]]});')
                # B2：真拖把手；標籤中心跟 anchorY；平移與縮放不改標籤 y。
                start = state(f'''const {{channelHandles}}=await import('/js/analysis/handles.js');const cv={CV},r=cv.getBoundingClientRect();
                  const h=channelHandles(S.get().channels,cv.gridRect())[0];return {{x:r.left+h.x+h.w/2,y:r.top+h.y+h.h/2}};''')
                c.mouse('mousePressed', start['x'], start['y'])
                c.mouse('mouseMoved', start['x'], start['y'] - 20, buttons=1)
                c.mouse('mouseReleased', start['x'], start['y'] - 20)
                c.pump(0.3)
                assert state(f'''const {{channelHandles}}=await import('/js/analysis/handles.js');const cv={CV};
                  return Math.abs(cv.labelLayout()[0].labels[0].y+8-channelHandles(S.get().channels,cv.gridRect())[0].anchorY)<.1;''')
                y = c.js(f'{LAYOUT}[0].labels[0].y')
                command("const v=S.get().view,d=v.t1-v.t0;S.set({view:{t0:v.t0+d*.1,t1:v.t1+d*.1}});")
                assert abs(c.js(f'{LAYOUT}[0].labels[0].y') - y) < 0.1
                command("const v=S.get().view,d=v.t1-v.t0;S.set({view:{t0:v.t0+d*.2,t1:v.t1-d*.2}});")
                assert abs(c.js(f'{LAYOUT}[0].labels[0].y') - y) < 0.1
                # B3：真解碼／點事件，將事件平移到左端附近；標籤避讓 ▲。
                command("S.set({channels:window.__labelBase.map(ch=>({...ch,position:-4.5})),selected:window.__labelBase[0].name});")
                c.js("document.querySelector('[data-result-tab=decode]').click()")
                c.js("(()=>{const e=document.querySelector('[data-protocol]');e.value='i2c';e.dispatchEvent(new Event('change'))})()")
                for role, name in roles.items():
                    c.js(f"(()=>{{const e=document.querySelector('[data-role={role}]');e.value={json.dumps(name)};e.dispatchEvent(new Event('input'))}})()")
                c.js("document.querySelector('[data-decode-action=run]').click()")
                c.wait('(async()=>{' + prep + 'return S.get().decodeResult?.summary.ok&&!S.get().decodeResult.stale})()', 30)
                c.wait("document.querySelectorAll('.decode__tablewrap tbody tr').length>=3")
                c.js("document.querySelectorAll('.decode__tablewrap tbody tr')[2].click()")
                command("const s=S.get(),f=s.decodeResult.frames.find(f=>f.i===s.decodeSel),d=s.view.t1-s.view.t0;S.set({view:{t0:f.t0-d*.01,t1:f.t0+d*.99}});")
                c.wait(f'{CV}.decodeMarks().length>0')
                clean_layout()
                assert c.js(f'''(async()=>{{const {{plotColors}}=await import('/js/analysis/plotcore.js'),cv={CV},k=cv.width/cv.clientWidth;
                  const sw=document.createElement('canvas').getContext('2d');sw.fillStyle=plotColors().amber;sw.fillRect(0,0,1,1);
                  const expected=sw.getImageData(0,0,1,1).data;return cv.decodeMarks().every(m=>{{
                    const p=cv.getContext('2d').getImageData(Math.floor(m.x*k),Math.floor((m.row.t+m.row.h-4)*k),1,1).data;
                    return [...p].every((v,i)=>Math.abs(v-expected[i])<=3);}})}})()''')
                # B4：操作原生標籤底 select，取無文字的內部像素。
                command("S.set({decodeSel:null,channels:[{...S.get().channels[0],position:0}],selected:S.get().channels[0].name});")
                c.js("(()=>{const e=document.querySelector('.chanbar__toggle');if(e?.getAttribute('aria-expanded')!=='true')e?.click()})()")
                c.js("(()=>{const e=document.querySelector('[data-vertical=labelBg]');e.value='solid';e.dispatchEvent(new Event('change'))})()")
                expected = state("const g=document.createElement('canvas').getContext('2d');g.fillStyle=S.get().channels[0].color;g.fillRect(0,0,1,1);return [...g.getImageData(0,0,1,1).data];")
                c.mouse('mouseMoved', 1, 1)  # 先移出，避免上一輪 DPR 的滑鼠停在標籤上
                c.pump(0.2)
                normal = pixel()
                assert all(abs(a-b) <= 3 for a, b in zip(normal, expected)), (normal, expected)
                base_ink = ink()
                assert base_ink > 20, base_ink
                # B5：真 hover／移出，並直接執行 collectReport 檢查 PNG 標籤已恢復。
                p = point()
                c.mouse('mouseMoved', p['x'], p['y'])
                c.pump(0.2)
                assert state(f'return {CV}.title.includes(S.get().channels[0].name)')
                assert ink() != base_ink, base_ink  # hover 淡出後暗像素數必變
                c.mouse('mouseMoved', 1, 1)
                c.pump(0.2)
                assert ink() == base_ink
                c.mouse('mouseMoved', p['x'], p['y'])
                c.wait(f"{CV}.dataset.pending!=='1'", 30)
                report_pixel = state(f'''const {{collectReport}}=await import('/js/analysis/report.js'),fmt=await import('/js/fmt.js');
                  const report=await collectReport({{store:S,fmt}},document.querySelector('.analysis'),{{title:'標籤驗收',invert:false}});
                  const image=new Image();image.src=report.sections[0].img;await image.decode();
                  const cv={CV},k=cv.width/cv.clientWidth,b=cv.labelLayout()[0].labels[0],g=document.createElement('canvas').getContext('2d');
                  g.canvas.width=image.width;g.canvas.height=image.height;g.drawImage(image,0,0);
                  return [...g.getImageData(Math.floor((b.x+2)*k),Math.floor((b.y+3)*k),1,1).data];''')
                assert report_pixel == normal and c.js(f'{CV}.title') == ''
                # B6：Y1 貼底，Y2 畫面外；兩個框保持格內且避讓提示。
                command("S.set({cursors:{x1:null,x2:null,y1:-5,y2:-8}});")
                clean_layout()
                assert c.js(f'{LAYOUT}.flatMap(r=>r.readouts).length') == 2
                c.shot(out / f'labels_{width}x{height}_dpr{dpr}.png')
                assert not c.errors, c.errors
    finally:
        c.send('Emulation.setDeviceMetricsOverride', width=size['w'], height=size['h'],
               deviceScaleFactor=size['dpr'], mobile=False)
        state("if(window.__fw){(await import('/js/bridge.js')).bridge.fetchWave=window.__fw;delete window.__fw;}")
        state('if(window.__labelBase){S.set({channels:window.__labelBase,grids:{n:1,assign:{}},decodeSel:null});delete window.__labelBase;}')
        (out / 'label_margins.json').write_text(json.dumps(margins, ensure_ascii=False, indent=2), encoding='utf-8')
    return margins


def alias_checks(c: Cdp, prep: str, directory: str) -> None:
    """波 3B B7–B9：真頁面 F2 改名；需先開好含 ≥2 通道的檔案（1400×900）。# 待真機驗證。"""
    def state(code: str):
        return c.js('(async()=>{' + prep + code + '})()')

    def rename(index: int, text: str, key: str = 'Enter', composing: bool = False) -> None:
        c.js(f'''(()=>{{const n=document.querySelectorAll('.chip__name')[{index}];n.dispatchEvent(new KeyboardEvent('keydown',{{key:'F2',bubbles:true}}));
          const i=document.querySelectorAll('.chip__alias')[0];i.value={json.dumps(text)};
          i.dispatchEvent(new KeyboardEvent('keydown',{{key:{json.dumps(key)},isComposing:{str(composing).lower()},bubbles:true}}))}})()''')
        c.pump(0.2)

    out = Path(directory)
    source = out / f'alias_{time.strftime("%Y%m%d_%H%M%S")}.csv'
    fixture(source)
    state("S.command('tab.select','analysis');")
    gen = state('return S.get().file?.gen??null')
    state(f"S.command('file.open',{{path:{json.dumps(str(source))}}});")
    c.wait('(async()=>{' + prep + f'return !!S.get().file&&S.get().file.gen!=={json.dumps(gen)}&&S.get().channels.length>=2' + '})()', 30)
    c.pump(0.3)
    base = state('const s=S.get();return {name:s.channels[0].name,second:s.channels[1].name,stale:!!s.decodeResult?.stale,manual:s.fftMarker?.manual?.length??0}')
    # B7：F2 改名 → 各處顯示名變、value 與其他狀態不變。
    rename(0, 'SDA')
    after = state('const s=S.get();return {alias:s.channels[0].alias,name:s.channels[0].name,stale:!!s.decodeResult?.stale,manual:s.fftMarker?.manual?.length??0}')
    assert after['alias'] == 'SDA' and after['name'] == base['name'] and after['stale'] == base['stale'] and after['manual'] == base['manual'], after
    options = c.js("[...document.querySelectorAll('.analysis select option')].filter(o=>o.value===" + json.dumps(base['name']) + ").map(o=>o.textContent)")
    assert options and all(t == 'SDA' for t in options), options
    # B8：撞名被擋（toast、不寫）；輸入法組字中的 Enter 不提交。
    rename(1, 'sda')
    assert state('return S.get().channels[1].alias??""') == ''
    rename(1, 'SCL', composing=True)
    assert c.js('!!document.querySelector(".chip__alias")') and state('return S.get().channels[1].alias??""') == ''
    c.js('document.querySelector(".chip__alias").dispatchEvent(new KeyboardEvent("keydown",{key:"Escape",bubbles:true}))')
    # B9：報告波形段含別名／原名對照表。
    has = state('''const {collectReport}=await import('/js/analysis/report.js'),fmt=await import('/js/fmt.js');
      const r=await collectReport({store:S,fmt},document.querySelector('.analysis'),{title:'別名驗收',invert:false});
      return JSON.stringify(r.sections[0].tables)''')
    assert '別名' in has and 'SDA' in has, has
    state(f"S.updateChannel({json.dumps(base['name'])},{{alias:''}},'user')")
    assert not c.errors, c.errors
