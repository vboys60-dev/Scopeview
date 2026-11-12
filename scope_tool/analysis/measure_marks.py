"""追蹤目前量測事件的來源時間與電壓座標。"""
import numpy as np
from scope_tool.analysis import edge
from scope_tool.analysis.measure import levels, _sample_index


def _edges(t, v, pct, center=None, width=None, needed=1):
    _, _, top, base = levels(v)
    lv = tuple(base + (top-base)*p/100 for p in pct)
    if center is None:
        return edge.edges(t, v, *lv), lv
    width = max(width or 0, (t[-1]-t[0])/1000, np.finfo(float).eps)
    while True:
        a = max(0, int(np.searchsorted(t, center-width))-1)
        b = min(len(t), int(np.searchsorted(t, center+width, side='right'))+1)
        es = edge.edges(t[a:b], v[a:b], *lv)
        es = [e._replace(a=e.a+a, b=e.b+a) for e in es]
        if len(es) >= needed and es[0].t_mid < center and es[-1].t_mid > center or (a == 0 and b == len(t)):
            return es, lv
        width *= 2


def marks(name, t, v, pct, values, i, rising=True, mode='full', ref=0, t2=None, v2=None, rising2=True, n1=1, n2=1, level1='middle', level2='middle'):
    """回傳 (來源時間, 值)；雙來源回傳兩組點。"""
    if name == '電壓比' or '計數' in name:
        return None
    at = getattr(values, 'at', None)
    center = float(at[i]) if at is not None else ref
    if name in ('Vmax', 'Vmin', 'Vp-p'):
        indices = ([int(np.argmax(v))] if name == 'Vmax' else [int(np.argmin(v))] if name == 'Vmin' else [int(np.argmin(v)), int(np.argmax(v))])
        return [(float(t[j]), float(v[j])) for j in indices]
    if name in ('Vtop', 'Vbase', 'Vmid', 'Vamp'):
        _, _, top, base = levels(v)
        y = {'Vtop': top, 'Vbase': base, 'Vmid': base+(top-base)*pct[1]/100}
        return [(float(t[0]), base), (float(t[-1]), top)] if name == 'Vamp' else [(float(t[0]), y[name]), (float(t[-1]), y[name])]
    if name in ('Vavg', 'Vrms(DC)', 'Vrms(AC)'):
        a, b = 0, len(t)
        if mode != 'full':
            es, _ = _edges(t, v, pct)
            if mode == 'cycle':
                e0 = min(es, key=lambda e: (abs(e.t_mid-ref), e.t_mid))
                mids = [e.t_mid for e in es if e.rising == e0.rising and e.t_mid >= e0.t_mid][:2]
            else:
                mids = [e.t_mid for e in es if e.rising == rising]
            a, b = _sample_index(t-t[0], mids[0]-t[0]), _sample_index(t-t[0], mids[-1]-t[0])
        return [(float(t[a]), float(v[a])), (float(t[b-1]), float(v[b-1]))]
    if name == 'Delta Time':
        out = []
        for tx, vx, up, n, layer in ((t,v,rising,n1,level1),(t2,v2,rising2,n2,level2)):
            es, lv = _edges(tx, vx, pct)
            e = [q for q in es if q.rising == up][n-1]
            k = {'lower':0,'middle':1,'upper':2}[layer]
            out.append(((e.t_lo,e.t_mid,e.t_hi)[k], lv[k]))
        return [[out[0]], [out[1]]]
    if name in ('延遲', '相位'):
        es, lv = _edges(t, v, pct, center, None, 1)
        e = min(es, key=lambda q: abs(q.t_mid-center))
        # 已知第一來源事件，第二來源取與其最近的指定方向邊緣。
        es2, lv2 = _edges(t2, v2, pct, center, abs(float(values[i])) if name == '延遲' else None, 3)
        candidates = [q for q in es2 if q.rising == rising2]
        while not candidates:
            es2, lv2 = _edges(t2, v2, pct)
            candidates = [q for q in es2 if q.rising == rising2]
        q = min(candidates, key=lambda q: (abs(q.t_mid-center), q.t_mid))
        return [[(e.t_mid,lv[1])], [(q.t_mid,lv2[1])]]
    value = abs(float(values[i]))
    width = 1/value if name == '頻率' and value else value if name in ('週期','+寬度','-寬度','上升時間','下降時間') else None
    es, lv = _edges(t, v, pct, center, 3*width if width else None, 5)
    k = min(range(len(es)), key=lambda j: abs(es[j].t_mid-center))
    e = es[k]
    if name in ('上升時間','下降時間','上升斜率','下降斜率'):
        return [(e.t_lo, lv[0]), (e.t_hi, lv[2])]
    if name in ('週期','頻率','+寬度','-寬度','工作週期','-工作週期'):
        count = 3 if name in ('週期','頻率','工作週期','-工作週期') else 2
        return [(q.t_mid,lv[1]) for q in (es[k:k+count:2] if name in ('週期','頻率') else es[k:k+count])]
    pre = name == '前衝'
    start = ((es[k-1].t_lo if e.rising else es[k-1].t_hi) + (e.t_lo if e.rising else e.t_hi))/2 if pre else (e.t_hi if e.rising else e.t_lo)
    end = (e.t_lo if e.rising else e.t_hi) if pre else (start + (es[k+1].t_hi if e.rising else es[k+1].t_lo))/2
    a, b = np.searchsorted(t, start), np.searchsorted(t, end, side='right')
    ts = np.r_[start, t[a:b], end]; vs = np.r_[np.interp(start,t,v),v[a:b],np.interp(end,t,v)]
    j = int(np.argmax(vs) if e.rising != pre else np.argmin(vs))
    return [(e.t_mid,lv[1]), (float(ts[j]),float(vs[j]))]


def _self_check():
    from scope_tool.analysis.measure import measure, current_index
    t = np.arange(401, dtype=float); v = np.tile(np.r_[np.zeros(20),np.ones(20)],10); v = np.r_[v,0.]
    for name in ('上升時間','週期','+寬度','工作週期','過衝','前衝','Vmax','Vmin','Vp-p','Vtop','Vbase','Vmid','Vamp','Vavg','Vrms(DC)'):
        from scope_tool.analysis.measure_extra import measure_extra
        values = measure_extra(name,t,v,(10,50,90)) if name == 'Vmid' else measure(name,t,v)
        out = marks(name,t,v,(10,50,90),values,current_index(values,200),ref=200)
        assert out and all(t[0] <= p[0] <= t[-1] for p in out), (name,out)
    es, lv = _edges(t, v, (10,50,90))
    for name in ('上升時間','下降時間','上升斜率','下降斜率','週期','頻率','+寬度','-寬度','工作週期','-工作週期','過衝','前衝'):
        values = measure(name,t,v)
        i = current_index(values,200)
        out = marks(name,t,v,(10,50,90),values,i,ref=200)
        e = min(es,key=lambda q:abs(q.t_mid-values.at[i]))
        k = es.index(e)
        expected = ([e.t_lo,e.t_hi] if '時間' in name and name not in ('週期',) or '斜率' in name else
                    [q.t_mid for q in (es[k:k+3:2] if name in ('週期','頻率') else es[k:k+3] if '工作週期' in name else es[k:k+2])] if name not in ('過衝','前衝') else [e.t_mid])
        assert all(abs(p[0]-x) < 1e-12 for p,x in zip(out,expected)), (name,out,expected)
    for name in ('Vavg','Vrms(DC)','Vrms(AC)'):
        out = marks(name,t,v,(10,50,90),measure(name,t,v),0)
        assert out == [(t[0],v[0]),(t[-1],v[-1])]
    assert marks('電壓比',t,v,(10,50,90),np.array([0]),0) is None
    print('measure_marks self-check OK')


if __name__ == '__main__':
    _self_check()
