// L4：垂直框選純函式；衍生通道沿用 Vertical 的實際單位檔位表。
import { DIVS, scaleSteps } from "./scales.js";
export const DEFAULT_ZOOM_KIND = "horizontal";
export const ZOOM_KINDS = ["horizontal", "vertical", "both"];
export const FIT_DIVS = 2 * DIVS; // 框選範圍使用整個格高，共十格。
/** 格數範圍換成來源物理值；V/格＝選框高度／10，超出檔位表界時夾限。 */
export function verticalZoom(channel, d1, d2, steps) {
  if (!channel || !(channel.scale > 0) || ![channel.scale, channel.position, d1, d2].every(Number.isFinite) || !(d2 > d1) || !steps?.length) return null;
  const lo = (d1 - channel.position) * channel.scale, hi = (d2 - channel.position) * channel.scale;
  const target = (hi - lo) / FIT_DIVS;
  const scale = Math.min(Math.max(target, steps[0]), steps.at(-1)); // 連續值：吸附到檔位表會讓大於約 40% 的選框完全不放大
  const position = -(lo / 2 + hi / 2) / scale + 0;
  return Number.isFinite(position) ? { scale, position } : null;
}
/** 像素先夾在格內；高度門檻與水平框選相同，由呼叫端提供。 */
export function verticalRect(channels, a, b, r, minPixels) {
  const clamp = (y) => Math.max(r.t, Math.min(r.t + r.h, y));
  a = clamp(a); b = clamp(b);
  if (Math.abs(b - a) < minPixels) return [];
  const division = (y) => DIVS - (y - r.t) * (2 * DIVS) / r.h;
  const d1 = division(Math.max(a, b)), d2 = division(Math.min(a, b));
  return channels.filter((c) => c.visible).flatMap((c) => {
    const patch = verticalZoom(c, d1, d2, scaleSteps(c.unit));
    return patch ? [{ name: c.name, ...patch }] : [];
  });
}
