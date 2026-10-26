/* Liquid Glass P1 瀏覽器驗收；測試夾具只在檢查期間存在。 */
export function glassSmoke(mode) {
  const host = document.querySelector('.app');
  if (mode === 'setup') {
    const fixture = document.createElement('div');
    fixture.id = 'glass-smoke';
    fixture.innerHTML = `<div class="dcap__card">
      <div class="tabs"><button class="tab tab--active">選中</button><button class="tab">分頁</button></div>
      <button class="btn">一般</button><button class="btn btn--primary">主要</button><button class="btn btn--danger">危險</button>
      <input class="input" value="輸入"><span class="muted">狀態</span><span class="field__hint">提示</span>
      <h2 class="dcap__title">標題</h2><table class="table"><tbody><tr><td>數值</td></tr></tbody></table>
      <span class="chip"><span class="chip__name">CH1</span><input type="checkbox"></span>
      <div class="legacy-warning">警示</div><div class="toast">訊息</div><div class="dlg">對話框</div>
      <div class="results__choices"><input type="checkbox"></div>
      <button data-before="btn">起點</button><button class="btn" data-focus="btn">焦點</button>
      <button data-before="input">起點</button><input class="input" data-focus="input">
      <button data-before="toggle">起點</button><input type="checkbox" data-focus="toggle">
    </div>`;
    host.append(fixture);
    return true;
  }
  const fixture = document.querySelector('#glass-smoke');
  const rgba = value => {
    const ctx = document.createElement('canvas').getContext('2d');
    ctx.fillStyle = value;
    ctx.fillRect(0, 0, 1, 1);
    const a = [...ctx.getImageData(0, 0, 1, 1).data];
    return [a[0], a[1], a[2], a[3] / 255];
  };
  const over = (fg, bg) => [...fg.slice(0, 3).map((v, i) => v * fg[3] + bg[i] * (1 - fg[3])), 1];
  const luminance = c => c.slice(0, 3).map(v => v / 255).map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4)
    .reduce((sum, v, i) => sum + v * [.2126, .7152, .0722][i], 0);
  const background = el => {
    const chain = [];
    for (let e = el; e; e = e.parentElement) chain.unshift(e);
    let bg = rgba(getComputedStyle(document.body).backgroundColor);
    for (const e of chain) {
      const style = getComputedStyle(e);
      // 漸層用最亮停點作保守底；必須先合成祖先，再逐層合成 alpha。
      if (style.backgroundImage !== 'none') {
        if (e !== host || !style.backgroundImage.includes('52, 58, 74')) throw Error('未識別的背景漸層');
        bg = [52, 58, 74, 1];
      }
      bg = over(rgba(style.backgroundColor), bg);
    }
    return bg;
  };
  if (mode === 'contrast') {
    const selectors = ['.tab--active', '.tab:not(.tab--active)', '.btn:not(.btn--primary):not(.btn--danger)',
      '.btn--primary', '.btn--danger', '.input', '.muted', '.field__hint', '.dcap__title', '.table td', '.chip__name', '.legacy-warning'];
    return selectors.flatMap(selector => {
      const actual = [...document.querySelectorAll(selector)].find(el => !fixture.contains(el) && el.getClientRects().length && !el.matches(':disabled, .is-busy, .is-disabled'));
      return [fixture.querySelector(selector), ...(actual ? [actual] : [])].map(el => {
        const bg = background(el), fg = over(rgba(getComputedStyle(el).color), bg);
        const a = luminance(fg), b = luminance(bg);
        return {selector, ratio: (Math.max(a, b) + .05) / (Math.min(a, b) + .05)};
      });
    });
  }
  if (mode === 'solid') return ['.dcap__card', '.tab--active', '.toast', '.dlg'].map(selector =>
    ({selector, alpha: rgba(getComputedStyle(fixture.querySelector(selector)).backgroundColor)[3]}));
  if (mode === 'forced') return ['[data-focus=toggle]', '.chip input', '.results__choices input'].map(selector => {
    const el = fixture.querySelector(selector);
    return {selector, appearance: getComputedStyle(el).appearance, thumb: getComputedStyle(el, '::before').content};
  });
  if (mode === 'cleanup') { fixture.remove(); return true; }
  throw Error(`未知檢查 ${mode}`);
}
