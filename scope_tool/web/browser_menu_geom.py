"""選單 hit test 共用幾何；包含四邊內縮 0.5／1／2 px，排除圓角透明區。"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scope_tool.web.browser_check import Cdp

# 在瀏覽器讀取實際 CSS 半徑（含百分比／橢圓），依 CSS 重疊規則縮放。
HIT_TEST = r"""(p=>{
    const r=p.getBoundingClientRect(),s=getComputedStyle(p),points=new Map();
    const radius=v=>{const a=v.split(/\s+/),n=(v,d)=>parseFloat(v)*(/%$/.test(v)?d/100:1);
      return [n(a[0],r.width),n(a[1]??a[0],r.height)];};
    const corners=[s.borderTopLeftRadius,s.borderTopRightRadius,s.borderBottomRightRadius,s.borderBottomLeftRadius].map(radius);
    const [tl,tr,br,bl]=corners,scale=Math.min(1,r.width/(tl[0]+tr[0]),r.width/(bl[0]+br[0]),r.height/(tl[1]+bl[1]),r.height/(tr[1]+br[1]));
    corners.forEach(a=>{a[0]*=scale;a[1]*=scale;});
    const inside=(x,y)=>corners.every(([rx,ry],i)=>{
      if(!rx||!ry)return true;
      const cx=(i===0||i===3)?r.left+rx:r.right-rx,cy=i<2?r.top+ry:r.bottom-ry;
      const dx=(i===0||i===3)?cx-x:x-cx,dy=i<2?cy-y:y-cy;
      return dx<=0||dy<=0||(dx/rx)**2+(dy/ry)**2<=(1-1/Math.min(rx,ry))**2;
    });
    const add=(x,y)=>{if(x>r.left&&x<r.right&&y>r.top&&y<r.bottom&&inside(x,y))points.set(x+','+y,[x,y]);};
    for(let y=r.top+3;y<r.bottom;y+=12)for(let x=r.left+3;x<r.right;x+=12)add(x,y);
    for(const d of [.5,1,2]){
      for(let x=r.left+.5;x<r.right;x+=8){add(x,r.top+d);add(x,r.bottom-d);}
      for(let y=r.top+.5;y<r.bottom;y+=8){add(r.left+d,y);add(r.right-d,y);}
      add(r.left+r.width/2,r.top+d);add(r.left+r.width/2,r.bottom-d);
      add(r.left+d,r.top+r.height/2);add(r.right-d,r.top+r.height/2);
    }
    const miss=[];
    for(const [x,y] of points.values()){const e=document.elementFromPoint(x,y);if(!p.contains(e))miss.push([x,y,e?e.tagName+'.'+e.className:null]);}
    return {count:points.size,miss,inside:r.width>0&&r.height>0&&r.left>=0&&r.top>=0&&r.right<=innerWidth&&r.bottom<=innerHeight};
})"""


def menu_hits(c: Cdp, panel: str) -> dict:
    """panel 為選單元素的 JS 運算式，回傳取樣數、遮擋點與視窗內判定。"""
    return c.js(HIT_TEST + '(' + panel + ')')


if __name__ == '__main__':
    assert callable(menu_hits) and 'borderTopLeftRadius' in HIT_TEST
    print('browser_menu_geom self-check OK（實際 hit test 待主控執行）')
