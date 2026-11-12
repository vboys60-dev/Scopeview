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
    c.js("(async()=>{" + prep + "const s=document.querySelector('.analysis__toolbar select'); const o=[...document.querySelectorAll('.analysis__toolbar select')].find(x=>[...x.options].some(o=>o.value==='Track Measurements')); o.value='Track Measurements';o.dispatchEvent(new Event('change'));})()")
    c.wait("(async()=>{" + prep + "return S.state.measurements.some(e=>e.track&&e.result?.marks?.length)})()")
    c.js("[...document.querySelectorAll('.results__table tr')].find(r=>r.textContent.includes('Vmid')).click()")
    c.wait("(async()=>{" + prep + "return S.state.measurements.some(e=>e.name==='Vmid'&&e.track&&e.result?.marks?.length)&&S.state.markerResult?.points?.length})()")
    assert c.js("(async()=>{" + prep + "const {points}=S.state.markerResult,v=S.state.view;return points.some(p=>p.x>=v.t0&&p.x<=v.t1&&Math.abs(p.y)<=5)})()")
    assert c.js("""(async()=>{""" + prep + """
        const original=B.job, old=S.state.rangeMode; let count=0;
        B.job=function(m,...args){if(m==='measure') count++;return original.call(this,m,...args)};
        try { S.set({rangeMode:'cursors'},'user'); S.command('cursor.intent',{which:'x1',value:S.state.cursors.x1+(S.state.view.t1-S.state.view.t0)*0.01});
            await new Promise(r=>setTimeout(r,1500)); count=0; await new Promise(r=>setTimeout(r,1000)); return count===0;
        } finally { B.job=original; S.set({rangeMode:old,markerMode:null},'program'); }
    })()""")


def _self_check():
    assert callable(measure_more)
    print("browser_measure_more_checks self-check OK")


if __name__ == "__main__":
    _self_check()
