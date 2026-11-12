from __future__ import annotations

"""P2／P3 多檔比對的 Chrome/CDP 真後端驗收；由 browser_check 呼叫。原生選檔待真人驗證。"""
import json
import math
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from scope_tool.web.browser_check import Cdp


def fixture(path: Path, amplitude: float, delay: int = 0) -> None:
    """同通道名、不同電壓，讓換槽的波形差異可被觀察。"""
    rows = ['Time(s),CH1(V),CH2(V)\n']
    for i in range(2000):
        t = i * 1e-6
        rows.append(f'{t:.9e},{amplitude * math.sin((i - delay) * .1 - 1):.9e},{amplitude * math.cos((i - delay) * .1 - 1):.9e}\n')
    path.write_text(''.join(rows), encoding='utf-8')


def slot_page(c: Cdp, prep: str, click: str, out: Path, directory: str) -> None:
    """實際選檔／套用／移除；觀察主圖 fetchWave 與 /wave，並核對量測和游標。"""
    paths = [Path(directory) / f'slots_{i}.csv' for i in range(3)]
    for path, amplitude in zip(paths, (1, 2, 4)):
        fixture(path, amplitude, 10 if path == paths[1] else 0)

    def state(expr: str) -> Any:
        return c.js(f'(async()=>{{{prep}return {expr}}})()')

    def wait(expr: str) -> None:
        c.wait(f'(async()=>{{{prep}return {expr}}})()')

    def open_main(path: Path) -> None:
        gen = state('S.state.file?.gen')
        c.js(f"(async()=>{{{prep}S.command('file.open',{{path:{json.dumps(str(path))}}})}})()")
        wait(f'S.state.file?.gen !== {json.dumps(gen)} && S.state.file?.path === {json.dumps(str(path))}')

    def choose(path: Path, slot: str = 'Mem1') -> None:
        c.js(f"document.querySelector('[data-slot={slot}] button').click()")
        c.wait("document.querySelectorAll('dialog[open]').length===2")
        c.js(f"(()=>{{const d=[...document.querySelectorAll('dialog[open]')].at(-1);d.querySelector('input').value={json.dumps(str(path))};d.querySelector('.btn--primary').click()}})()")
        wait(f'S.state.slots?.find(s=>s.slot==={json.dumps(slot)})?.path === {json.dumps(str(path))}')
        c.wait(f"!document.querySelector('[data-slot={slot}] button').disabled")

    def apply() -> None:
        rev = state('S.state.dataRev')
        c.js("[...document.querySelectorAll('dialog[open] button')].find(b=>b.textContent==='套用勾選').click()")
        wait(f'S.state.dataRev === {rev + 1}')
        c.wait("!document.querySelector('[data-slot=Mem1] button').disabled")

    def close_dialog() -> None:
        c.js("[...document.querySelector('dialog[open] .dlg__actions').querySelectorAll('button')].find(b=>b.textContent==='關閉').click()")
        c.wait("!document.querySelector('dialog[open]')")

    def check_info(limits: list[str]) -> None:
        expected = state("[{slot:'main',info:S.state.file.info},...(S.state.slots??[]).slice().sort((a,b)=>a.slot.localeCompare(b.slot)).map(({slot,info})=>({slot,info}))]")
        c.js(f"({click})('檔案資訊')")
        c.wait("!!document.querySelector('dialog[open] [data-file-info=main]')")
        actual = c.js("""[...document.querySelectorAll('dialog[open] [data-file-info]')].map(t=>({
          slot:t.dataset.fileInfo,info:[...t.rows].map(r=>[...r.cells].map(c=>c.textContent))}))""")
        assert actual == expected, (actual, expected)
        headings = c.js("[...document.querySelectorAll('dialog[open] h3')].map(h=>h.textContent)")
        expected_slots = [s['slot'] for s in expected[1:]]
        assert headings == expected_slots + (['比對限制'] if expected_slots else [])
        actual_limits = c.js("[...document.querySelectorAll('dialog[open] [data-slot-limits] div')].map(d=>d.textContent)")
        assert actual_limits == (limits if expected_slots else [])
        close_dialog()

    c.send('Emulation.setDeviceMetricsOverride', width=1400, height=900, deviceScaleFactor=1, mobile=False)
    c.js("document.querySelector('[data-tab=analysis]').click()")
    open_main(paths[0])
    c.js(f"(async()=>{{{prep}S.set({{markerMode:null}});S.command('layout.restore',{{side:240,lower:350,fft:180}});S.command('fft.visible',false)}})()")
    c.js(f"({click})('Vp-p')")
    wait('S.state.measurements.length===1 && S.state.measurements[0].result?.ok')
    c.js(f"(async()=>{{{prep}S.command('cursor.intent',{{which:'x1',value:.0003}});S.command('cursor.intent',{{which:'x2',value:.0012}})}})()")
    c.pump(.6)  # 等主檔取樣點吸附完成後再記錄位置。
    before = state('({cursors:S.state.cursors,ids:S.state.measurements.map(m=>m.id),gen:S.state.file.gen})')
    c.js(f"""(async()=>{{{prep}
      const wave=B.fetchWave,fetch=window.fetch,call=B.call;
      window.__slotMain=[];window.__slotHttp=[];window.__slotRemoves=0;
      B.call=(name,p)=>{{if(name==='remove_slot')window.__slotRemoves++;return call(name,p)}};
      B.fetchWave=async p=>{{const main=new Error().stack.includes('mainplot.js');const r=await wave(p);
        if(main&&p.ch==='Mem1.CHAN1')window.__slotMain.push({{ch:p.ch,hi:Array.from(r.hi)}});return r}};
      window.fetch=(url,...args)=>{{if(String(url).includes('/wave?'))window.__slotHttp.push(String(url));return fetch(url,...args)}};
      window.__slotRestore=()=>{{B.fetchWave=wave;window.fetch=fetch;B.call=call}};
    }})()""")
    try:
        c.js(f"({click})('比對…')")
        # CDP returnByValue 將 DOM 節點序列化為 {}，Python 會視為 false；等待須回傳布林。
        c.wait("!!document.querySelector('dialog[open] [data-slots]')")
        assert c.js("document.querySelectorAll('[data-slots] [data-slot]').length") == 4
        limits = c.js("[...document.querySelectorAll('dialog[open] [data-slot-limits] div')].map(d=>d.textContent)")
        assert len(limits) == 7
        choose(paths[1])
        c.wait("document.querySelector('.analysis__chanbar').textContent.includes('Mem1.CHAN1')")
        c.wait("window.__slotMain.length>0 && window.__slotHttp.some(u=>decodeURIComponent(u).includes('Mem1.CHAN1'))")
        wait('S.state.measurements.length===1 && S.state.measurements[0].result?.ok')
        # 載入 Mem1 後，解碼來源選單要出現 Mem1.CHAN1（不必切到解碼分頁，選單隨通道清單重建）
        c.wait("[...document.querySelectorAll('.decode__bar select[data-role]')].some(s=>[...s.options].some(o=>o.value==='Mem1.CHAN1'))")
        after = state('({cursors:S.state.cursors,ids:S.state.measurements.map(m=>m.id),gen:S.state.file.gen})')
        assert before == after, (before, after)
        old_wave = c.js('window.__slotMain.at(-1).hi')
        c.js(f"(async()=>{{{prep}S.command('channel.shift_intent',{{name:'Mem1.CHAN1',time_offset:.0001}})}})()")
        c.js("document.querySelector('[data-slot=Mem1] input[value=CHAN2]').click()")
        apply()
        wait("!S.state.channels.some(c=>c.name==='Mem1.CHAN2')")
        assert state("S.state.channels.find(c=>c.name==='Mem1.CHAN1').time_offset") == .0001
        close_dialog()
        check_info(limits)  # 子集資訊應列出目前已選通道。
        c.js(f"({click})('比對…')")
        c.wait("!!document.querySelector('dialog[open] [data-slot=Mem1] input[value=CHAN2]')")
        assert c.js("document.querySelector('[data-slot=Mem1] input[value=CHAN1]').checked && !document.querySelector('[data-slot=Mem1] input[value=CHAN2]').checked")
        # 同名換槽必須重新抓波形；dx 沿用，電壓則是第三個檔案的值。
        count = c.js('window.__slotMain.length')
        choose(paths[2])
        c.wait(f'window.__slotMain.length>{count} && Math.max(...window.__slotMain.at(-1).hi)>{max(old_wave) * 1.5}')
        assert max(c.js('window.__slotMain.at(-1).hi')) > max(old_wave) * 1.5
        assert state("S.state.channels.find(c=>c.name==='Mem1.CHAN1').time_offset") == .0001
        c.js("document.querySelectorAll('[data-slot=Mem1] input').forEach(i=>{i.checked=false})")
        apply()
        wait('S.state.slots.length===0 && !S.state.channels.some(c=>c.name.startsWith("Mem1."))')
        assert c.js('window.__slotRemoves') == 1, '全不勾須呼叫 remove_slot'
        choose(paths[1])
        c.js("[...document.querySelectorAll('[data-slot=Mem1] button')].find(b=>b.textContent==='移除').click()")
        wait('S.state.slots.length===0')
        c.wait("!document.querySelector('[data-slot=Mem1] button').disabled")
        assert c.js('window.__slotRemoves') == 2
        choose(paths[1])
        choose(paths[2], 'Mem2')
        close_dialog()
        # 第一個完整上升緣延遲 10 個取樣；兩通道共用同一 dx。
        c.js("document.querySelector('[data-channel=\"Mem1.CHAN1\"] .chip__name').click()")
        c.js("[...document.querySelectorAll('[data-channel=\"Mem1.CHAN1\"] button')].find(b=>b.textContent==='對齊主檔').click()")
        wait("Math.abs(S.state.channels.find(c=>c.name==='Mem1.CHAN1').time_offset + .00001)<.0000001")
        assert abs(state("S.state.channels.find(c=>c.name==='Mem1.CHAN2').time_offset") + .00001) < .0000001
        check_info(limits)  # 多槽分段、各自檔案資訊與共用限制。
        c.shot(out / 'slots_loaded.png')
        open_main(paths[0])
        assert state('S.state.slots.length===0 && S.state.dataRev===0')
        check_info(limits)  # 換主檔後沒有殘留比對段落。
        assert not c.errors, c.errors
    finally:
        c.js('window.__slotRestore()')
        c.js("document.querySelectorAll('dialog[open]').forEach(d=>{d.close();d.remove()})")


if __name__ == '__main__':
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / 'slots.csv'
        fixture(path, 2)
        assert len(path.read_text(encoding='utf-8').splitlines()) == 2001
    print('browser_slot_checks self-check OK（資料產生；Chrome 流程由 browser_check 執行）')
