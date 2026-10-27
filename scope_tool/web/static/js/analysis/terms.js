// 量測／數學名詞的顯示用英文；後端、契約、存檔仍用中文 key，只在畫面轉換。
const EN = {
  上升時間: "Rise Time", 下降時間: "Fall Time", 上升斜率: "Rise Slew", 下降斜率: "Fall Slew",
  週期: "Period", 頻率: "Frequency", "+寬度": "+Width", "-寬度": "-Width",
  工作週期: "+Duty Cycle", "-工作週期": "-Duty Cycle", 過衝: "Overshoot", 前衝: "Preshoot",
  延遲: "Delay", 相位: "Phase", 電壓比: "Gain",
  時間: "Time", 電壓: "Voltage", 雙來源: "Dual-Source",
  目前: "Current", 平均: "Mean", 最小: "Min", 最大: "Max", 範圍: "Range", 標準差: "Std Dev", 次數: "Count",
  加: "Add", 減: "Subtract", 乘: "Multiply", 除: "Divide",
  反相: "Invert", 絕對值: "Abs", 平方: "Square", 開根號: "Sqrt", 微分: "Differentiate", 積分: "Integrate",
  低通: "Low-pass", 高通: "High-pass", 平滑: "Smooth",
  量測: "Measure", 數學: "Math", 運算: "Operation", 區間: "Range", 整數週期: "N Cycles",
};
export const T = (s) => EN[s] ?? s;
