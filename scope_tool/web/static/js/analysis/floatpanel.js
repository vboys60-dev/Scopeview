// L4：搬移同一組 B 區節點；固定定位仍留在分析頁內，隨頁面一起隱藏。
import { canFloat, clampRect, keyboardRect, resizeRect, loadPrefs, savePrefs, validatePrefs } from './floatpanel_math.js';
export function mountFloat(page, { store, lower, header, body, tabs, actions, schedule, initial = loadPrefs(), persist = savePrefs }) {
  let prefs=validatePrefs(initial), floating=false, collapsed=false, drag=null, preview=null, keyDirty=false;
  const make = (tag,cls,text) => { const e=document.createElement(tag); e.className=cls; if(text) e.textContent=text; return e; };
  const button = (text,label,fn) => { const b=make('button','btn btn--small',text); b.type='button'; b.setAttribute('aria-label',label); b.onclick=fn; return b; };
  const panel=make('section','analysis__float analysis__lower'); panel.hidden=true;
  panel.setAttribute('role','dialog'); panel.setAttribute('aria-label','量測資訊（浮動）'); panel.setAttribute('aria-modal','false');
  const title=make('div','analysis__floatTitle'); title.tabIndex=0; title.setAttribute('aria-label','移動或縮放量測資訊');
  const help=make('span','','可用方向鍵移動、Alt＋方向鍵縮放'); help.id='analysis-float-help'; help.hidden=true;
  title.setAttribute('aria-describedby',help.id);
  const caption=make('span','analysis__floatCaption','量測資訊');
  const dock=button('停靠','停靠量測資訊',()=>store.command('layout.float',false));
  const fold=button('收折','收折浮動面板內容',()=>store.command('layout.float.collapse'));
  title.append(caption,dock,fold);
  const bar=make('div','analysis__floatBar'); panel.append(title,bar,help); page.append(panel);
  const launch=button('浮動','浮動量測資訊',()=>store.command('layout.float',true)); launch.classList.add('analysis__floatLaunch');
  header.append(launch);
  const home=make('span','analysis__floatHome','已浮動 · ');
  home.append(button('停靠','停靠量測資訊',()=>store.command('layout.float',false))); home.hidden=true; header.append(home);
  for (const name of ['pointerdown','dblclick','keydown']) {
    launch.addEventListener(name,e=>e.stopPropagation()); home.addEventListener(name,e=>e.stopPropagation());
  }
  const top = () => Math.max(0,page.getBoundingClientRect().top);
  const clamp = rect => clampRect(rect,innerWidth,innerHeight,top());
  function draw() {
    const rect=clamp(preview ?? prefs);
    Object.assign(panel.style,{left:rect.x+'px',top:rect.y+'px',width:rect.width+'px',height:(collapsed ? Math.min(28,Math.max(0,innerHeight-top())) : rect.height)+'px'});
    body.hidden=collapsed; bar.hidden=collapsed;
    fold.textContent=collapsed ? '展開' : '收折'; fold.setAttribute('aria-label',collapsed ? '展開浮動面板內容' : '收折浮動面板內容');
    fold.setAttribute('aria-expanded',String(!collapsed));
  }
  function setFloating(on) {
    on=!!on && canFloat(innerWidth);
    if (on !== floating) {
      end(); floating=on;
      if (on) { bar.append(tabs,actions); panel.append(body); }
      else { header.insertBefore(tabs,launch); header.insertBefore(actions,launch); lower.append(body); }
      panel.hidden=!on; home.hidden=!on; launch.hidden=on;
      store.command('layout.float.state',on);
      (on ? title : launch).focus();
    }
    if(on) draw(); schedule();
  }
  store.onCommand('layout.float',on=>{
    end(); prefs={...prefs,floating:!!on}; persist(prefs); setFloating(on);
  });
  store.onCommand('layout.float.collapse',()=>{ if(floating) { collapsed=!collapsed; draw(); schedule(); } });
  store.onCommand('layout.float.rect',rect=>{
    if (!floating) return;
    prefs={...prefs,...clamp({...prefs,...rect})}; persist(prefs); draw(); schedule();
  });
  function end(commit=false) {
    if(keyDirty) { prefs={...prefs,...preview}; persist(prefs); keyDirty=false; preview=null; }
    if(!drag) return;
    const d=drag; drag=null;
    if(commit && preview) { prefs={...prefs,...preview}; persist(prefs); }
    preview=null; draw(); schedule();
    if(d.host.hasPointerCapture(d.id)) d.host.releasePointerCapture(d.id);
  }
  function start(e,edge,host) {
    if(!floating || drag || e.button!==0 || (!edge && e.target!==title && e.target!==caption)) return;
    end(); e.preventDefault(); title.focus();
    drag={id:e.pointerId,host,edge,x:e.clientX,y:e.clientY,rect:clamp(prefs)};
    host.setPointerCapture(e.pointerId);
  }
  title.addEventListener('pointerdown',e=>start(e,'',title));
  title.addEventListener('dblclick',e=>{ if(e.target===title || e.target===caption) store.command('layout.float',false); });
  title.addEventListener('keydown',e=>{
    if(!floating || e.target!==title || (collapsed && e.altKey)) return;
    const rect=keyboardRect(clamp(preview ?? prefs),e,innerWidth,innerHeight,top());
    if(rect) { e.preventDefault(); preview=rect; keyDirty=true; draw(); schedule(); }
  });
  title.addEventListener('keyup',e=>{ if(e.key.startsWith('Arrow')) end(); });
  title.addEventListener('blur',()=>end());
  for(const edge of ['n','e','s','w','ne','nw','se','sw']) {
    const grip=make('div','analysis__floatGrip'); grip.dataset.edge=edge;
    grip.addEventListener('pointerdown',e=>{if(!collapsed) start(e,edge,grip);}); panel.append(grip);
  }
  panel.addEventListener('pointermove',e=>{
    if(!drag || drag.id!==e.pointerId) return;
    const dx=e.clientX-drag.x,dy=e.clientY-drag.y;
    preview=clamp(drag.edge ? resizeRect(drag.rect,drag.edge,dx,dy,innerWidth,innerHeight,top()) : {...drag.rect,x:drag.rect.x+dx,y:drag.rect.y+dy});
    draw(); schedule();
  });
  panel.addEventListener('pointerup',e=>{ if(drag?.id===e.pointerId) end(true); });
  for(const name of ['pointercancel','lostpointercapture']) panel.addEventListener(name,()=>end());
  // 只攔面板內的事件，沒有覆蓋全視窗的遮罩；Esc 不處理。
  for(const name of ['pointerdown','pointermove','pointerup','dblclick','wheel']) panel.addEventListener(name,e=>e.stopPropagation());
  window.addEventListener('blur',()=>end());
  window.addEventListener('resize',()=>{
    end(); setFloating(prefs.floating);
    schedule();
  });
  store.onCommand('tab.activated',name=>{end(); if(name==='analysis') schedule();});
  function setFloatingIfNeeded() {
    if(floating !== (prefs.floating && canFloat(innerWidth))) setFloating(prefs.floating);
  }
  setFloating(prefs.floating);
  return { get floating() { return floating; }, update() {
    launch.disabled=!canFloat(innerWidth); launch.title=launch.disabled ? '窄版請使用停靠面板' : '浮動量測資訊';
    setFloatingIfNeeded();
    if(floating) draw();
    header.tabIndex=floating ? -1 : 0; header.setAttribute('aria-disabled',String(floating));
    return floating ? {width:body.clientWidth,height:panel.clientHeight,collapsed} : null;
  } };
}
