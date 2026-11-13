from __future__ import annotations

"""波 B 真瀏覽器驗收函式；由主控呼叫，不接入 browser_check（主控已於真瀏覽器驗過）。"""
import json
from pathlib import Path
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from scope_tool.web.browser_check import Cdp


def i2c_roles(c: Cdp, prep: str, out: Path, root: Path | None = None) -> None:
    """參考檔直接解碼應對調；手選接反則尊重設定，不送估計。"""
    source = (root or Path(__file__).resolve().parents[2]) / 'H5參考波形' / 'i2cdemo.h5'
    if not source.is_file():
        print('  I2C 波 B：缺少 i2cdemo.h5，略過')
        return
    c.send('Emulation.setDeviceMetricsOverride', width=1400, height=900, deviceScaleFactor=1, mobile=False)
    c.js(f"(async()=>{{{prep} S.command('layout.restore',{{side:240,lower:350,fft:180}});S.command('fft.visible',false)}})()")
    c.js(f"""(async()=>{{{prep}
      window.__i2cRolesJob=B.job;window.__i2cRolesEstimates=0;
      B.job=function(n,p,...rest){{if(n==='decode'&&p.options?.estimate)window.__i2cRolesEstimates++;return window.__i2cRolesJob.call(this,n,p,...rest)}};
    }})()""")
    try:
        for manual in (False, True):
            gen = c.js(f'(async()=>{{{prep} return S.state.file?.gen}})()')
            c.js(f"(async()=>{{{prep} S.command('file.open',{{path:{json.dumps(str(source))}}})}})()")
            c.wait(f'(async()=>{{{prep} return S.state.file?.gen !== {json.dumps(gen)} && S.state.channels.length===2}})()', 30)
            c.js("document.querySelector('[data-result-tab=decode]').click()")
            c.wait("!document.querySelector('.analysis__decode').hidden")
            c.js("(()=>{const e=document.querySelector('[data-protocol]');e.value='i2c';e.dispatchEvent(new Event('change'))})()")
            picks = "[...document.querySelectorAll('.decode__bar select[data-role]')].map(e=>e.value)"
            assert c.js(picks) == ['Memory 1', 'Memory 2']
            if manual:
                # 先改成正向再接反，確保最後雖與預設相同，仍是使用者選的。
                for scl, sda in [('Memory 2', 'Memory 1'), ('Memory 1', 'Memory 2')]:
                    c.js(f"""(()=>{{const set=(r,v)=>{{const e=document.querySelector(`select[data-role=${{r}}]`);e.value=v;e.dispatchEvent(new Event('input',{{bubbles:true}}))}};
                      set('scl',{json.dumps(scl)});set('sda',{json.dumps(sda)});}})()""")
            before = c.js('window.__i2cRolesEstimates')
            c.js("document.querySelector('[data-decode-action=run]').click()")
            c.wait(f'(async()=>{{{prep} return S.state.decodeResult?.summary.ok}})()', 30)
            result = c.js(f'(async()=>{{{prep} return S.state.decodeResult}})()')
            warning = '已依波形自動對調 SCL／SDA（原 SCL=Memory 1）；可在下拉選單改回'
            if manual:
                assert c.js('window.__i2cRolesEstimates') == before
                assert c.js(picks) == ['Memory 1', 'Memory 2']
                assert result['summary']['channels'] == {'scl': 'Memory 1', 'sda': 'Memory 2'}
                assert not any(warning in w for w in result['summary']['warnings'])
            else:
                assert c.js('window.__i2cRolesEstimates') == before + 1
                assert c.js(picks) == ['Memory 2', 'Memory 1']
                assert len(result['frames']) == result['summary']['counts']['frames'] == 13
                assert sum(f['addr'] is not None for f in result['frames']) == 11
                assert warning in result['summary']['warnings']
                assert c.js(f"[...document.querySelectorAll('.decode__sum .decode__warn')].some(e=>e.textContent.includes({json.dumps(warning)}))")
            c.shot(out / ('i2c_roles_manual.png' if manual else 'i2c_roles_auto.png'))
        assert not c.errors, c.errors
        print('  I2C 波 B：自動對調 13 frames／11 位址、警告列與手選接反皆通過')
    finally:
        c.js(f'(async()=>{{{prep} B.job=window.__i2cRolesJob;delete window.__i2cRolesJob;delete window.__i2cRolesEstimates}})()')


if __name__ == '__main__':
    assert callable(i2c_roles)
    print('web.browser_i2c_roles_checks self-check OK（瀏覽器由主控驗收）')
