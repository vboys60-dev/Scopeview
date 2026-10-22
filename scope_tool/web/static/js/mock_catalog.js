// 由 api_contract.json 的 catalog 產生（取自 analysis/*.py 實際常數），勿手改；l0_check.mjs 驗證兩者相等。
export const CATALOG = {
  "measurements": [{"name": "上升時間", "category": "時間", "unit": "s", "sloped": false, "tip": "上升緣從下閾值到上閾值的時間（邊緣至少 4 點）"}, {"name": "下降時間", "category": "時間", "unit": "s", "sloped": false, "tip": "下降緣從上閾值到下閾值的時間（邊緣至少 4 點）"}, {"name": "上升斜率", "category": "時間", "unit": "{u}/s", "sloped": false, "tip": "上下閾值電壓差 ÷ 上升時間"}, {"name": "下降斜率", "category": "時間", "unit": "{u}/s", "sloped": false, "tip": "上下閾值電壓差 ÷ 下降時間"}, {"name": "週期", "category": "時間", "unit": "s", "sloped": true, "tip": "同方向相鄰兩邊緣在中閾值的時間差"}, {"name": "頻率", "category": "時間", "unit": "Hz", "sloped": true, "tip": "1 ÷ 週期（逐週期）"}, {"name": "+寬度", "category": "時間", "unit": "s", "sloped": false, "tip": "上升緣中閾值到下一個下降緣中閾值"}, {"name": "-寬度", "category": "時間", "unit": "s", "sloped": false, "tip": "下降緣中閾值到下一個上升緣中閾值"}, {"name": "工作週期", "category": "時間", "unit": "%", "sloped": true, "tip": "+寬度 ÷ 週期 × 100（逐週期）"}, {"name": "Vmax", "category": "電壓", "unit": "{u}", "sloped": false, "tip": "最大值"}, {"name": "Vmin", "category": "電壓", "unit": "{u}", "sloped": false, "tip": "最小值"}, {"name": "Vp-p", "category": "電壓", "unit": "{u}", "sloped": false, "tip": "最大值 − 最小值"}, {"name": "Vtop", "category": "電壓", "unit": "{u}", "sloped": false, "tip": "上方平台（直方圖眾數，不明顯時用最大值）"}, {"name": "Vbase", "category": "電壓", "unit": "{u}", "sloped": false, "tip": "下方平台（直方圖眾數，不明顯時用最小值）"}, {"name": "Vamp", "category": "電壓", "unit": "{u}", "sloped": false, "tip": "Vtop − Vbase"}, {"name": "Vavg", "category": "電壓", "unit": "{u}", "sloped": false, "tip": "第一個完整週期的平均"}, {"name": "Vrms(DC)", "category": "電壓", "unit": "{u}", "sloped": false, "tip": "含直流的有效值"}, {"name": "Vrms(AC)", "category": "電壓", "unit": "{u}", "sloped": false, "tip": "扣掉平均後的有效值"}, {"name": "過衝", "category": "電壓", "unit": "%", "sloped": true, "tip": "邊緣後到平台中點的局部極值超出 top／base 的量，÷ 振幅 × 100"}, {"name": "前衝", "category": "電壓", "unit": "%", "sloped": true, "tip": "平台中點到邊緣前的局部極值超出 base／top 的量，÷ 振幅 × 100"}],
  "thresholds": {"10/50/90 %": [10.0, 50.0, 90.0], "20/50/80 %": [20.0, 50.0, 80.0]},
  "stat_columns": ["目前", "平均", "最小", "最大", "範圍", "標準差", "次數"],
  "fft_windows": {"Hanning": [0.5, 0.5], "Flattop": [0.21557895, 0.41663158, 0.277263158, 0.083578947, 0.006947368], "Rectangular": [1.0], "Hamming": [0.54, 0.46], "Blackman-Harris": [0.35875, 0.48829, 0.14128, 0.01168]},
  "fft_units": ["dBm", "Vrms", "dBV", "dBmV", "dBµV", "Watt", "Phase"],
  "fft_max_points": 16777216,
  "peak_sorts": ["Decreasing Magnitude", "Increasing Frequency", "Decreasing Frequency", "Increasing Magnitude"],
  "math_ops": {"binary": ["加", "減", "乘", "除"], "unary": ["反相", "絕對值", "平方", "開根號", "log10", "微分", "積分"], "filters": ["低通", "高通", "平滑"], "symbols": {"加": "+", "減": "−", "乘": "×", "除": "÷"}},
  "marker_modes": ["Manual X only", "Manual Y only", "Manual X and Y", "Track Waveforms", "Track Measurements"],
  "marker_delta_to": [["X1", "X2"], ["X2", "X1"], ["Y1", "Y2"], ["Y2", "Y1"]],
  "v_table": [0.0005, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 5.0, 10.0],
  "divs": 5,
  "series": ["InfiniiVision", "Infiniium"],
  "image_formats": ["PNG", "BMP"],
  "capture_areas": ["full", "graticule"],
  "waveform_formats": ["CSV", "HDF5"],
  "csv_max_points_default": 10000000,
  "fft_impedances": [["Auto：其他／未知 50Ω", 50.0], ["Auto：單端 50Ω", 50.0], ["Auto：差動 100Ω", 100.0], ["Auto：共模 25Ω", 25.0], ["手動", null]],
  "channel_colors": ["#ffcc00", "#00d0ff", "#ff5fbf", "#7be36b", "#ff8a3d", "#b79cff"],
  "rf_directions": [-1, 0, 1]
};
