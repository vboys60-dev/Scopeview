"""新量測項目的真瀏覽器選單與結果檢查。"""


def measure_more(c, prep):
    c.js("(async()=>{" + prep + "S.command('layout.resize',{kind:'lower',value:150})})()")
    c.js("document.querySelector('[data-result-tab=measure]').click()")
    c.wait("[...document.querySelectorAll('button')].some(b=>b.textContent.trim()==='Vmid')")
    c.js("[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='Vmid').click()")
    c.wait("(async()=>{" + prep + "return S.state.measurements.some(e=>e.name==='Vmid' && e.result?.ok)})()")
    c.js("[...document.querySelectorAll('button')].find(b=>b.textContent.trim().startsWith('Delta Time')).click()")
    c.wait("(async()=>{" + prep + "return S.state.measurements.some(e=>e.name==='Delta Time' && e.result?.ok)})()")
    assert c.js("document.querySelector('.results__table').textContent.includes('Delta Time')")
    assert c.js("document.querySelector('.results__table').textContent.includes('Vmid')")


def _self_check():
    assert callable(measure_more)
    print("browser_measure_more_checks self-check OK")


if __name__ == "__main__":
    _self_check()
