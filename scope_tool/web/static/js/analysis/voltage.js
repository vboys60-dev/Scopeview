// L4：左軸實際單位與動態邊界；物理值只由 scale／position 換算。
import { fmt } from "../fmt.js";
import { tickLabel } from "./plotcore.js";
export const voltageAt = (division, c) => (division - c.position) * c.scale + 0;
export function voltageAxis(c) {
  if (!c) return { title: "格數", color: null, ticks: Array.from({ length: 11 }, (_, i) => ({ division: 5 - i, value: 5 - i, label: String(5 - i) })) };
  const max = Math.max(Math.abs(voltageAt(-5, c)), Math.abs(voltageAt(5, c)));
  const ticks = Array.from({ length: 11 }, (_, i) => {
    const division = 5 - i, value = voltageAt(division, c);
    return { division, value, label: tickLabel(value, c.unit, c.scale, max) };
  });
  return { title: `${c.name} · ${fmt(c.scale, c.unit)}/格`, color: c.color, ticks };
}
/** 把手分欄與刻度文字分開保留；標題在格內左上，不擠入把手區。 */
export function voltageLeft(measure, axis, handles, minimum = 84) {
  const edge = Math.max(14, ...handles.map((b) => b.x + b.w));
  return Math.max(minimum, Math.ceil(edge + 10 + Math.max(...axis.ticks.map((t) => measure(t.label))) + 8));
}
