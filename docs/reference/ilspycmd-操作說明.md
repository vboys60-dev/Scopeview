# ilspycmd 操作說明

用來反編譯 .NET 組件（`.dll` / `.exe`），例如查看 Keysight Infiniium 隨附 DLL 的類別與方法。版本 11.1.0（2026-10-22 安裝於 macOS）。

## 環境

- .NET SDK 裝在 `~/.dotnet`（官方 `dotnet-install` 腳本，未用 sudo）。
- `~/.zshrc` 已加入 `DOTNET_ROOT` 與 PATH（`~/.dotnet`、`~/.dotnet/tools`）。新終端機自動生效，舊的要 `source ~/.zshrc`。
- 確認安裝：`ilspycmd --version`
- 升級：`dotnet tool update -g ilspycmd`

## 常用操作

```bash
# 1. 先看有哪些類別（最快的探索方式）
ilspycmd Foo.dll -l c            # c=class i=interface s=struct d=delegate e=enum
ilspycmd Foo.dll -l cie          # 可合併多種

# 2. 反編譯單一類別到終端機
ilspycmd Foo.dll -t Namespace.ClassName

# 3. 只看單一方法（XML doc id 或 metadata token）
ilspycmd Foo.dll -m "M:Namespace.ClassName.Method(System.String)"

# 4. 整包輸出成可編譯專案（一個類別一個 .cs）
ilspycmd Foo.dll -p -o ./out
ilspycmd Foo.dll -p -o ./out --nested-directories   # 依命名空間分資料夾

# 5. 輸出單一 .cs 檔（不加 -p）
ilspycmd Foo.dll -o ./out

# 6. 看 IL 而非 C#
ilspycmd Foo.dll -t Namespace.ClassName -il

# 7. 嵌入資源
ilspycmd Foo.dll --list-resources
ilspycmd Foo.dll --resource <名稱> -o ./out
```

## 常見問題

| 現象 | 原因 | 處理 |
|---|---|---|
| `Stream length minus starting position is too large to hold a PEImage` | 檔案超過 2 GB，或根本不是 .NET 組件（如安裝程式） | 先解出裡面的 DLL 再反編譯 |
| 輸出有 `// Could not decompile` 註解 | 部分方法反編譯失敗 | 加 `-r <相依 DLL 資料夾>`；或 `--ignore-decompilation-errors` 讓 exit code 為 0 |
| `-p` 報錯要求輸出資料夾 | `-p` 必須搭配 `-o` | 補 `-o ./out` |
| 檔案不是 .NET（原生 DLL） | ilspycmd 只認 .NET | 改用 Ghidra / IDA，或查官方文件 |

## 確認檔案是不是 .NET 組件

```bash
file Foo.dll    # 看到 "Mono/.Net assembly" 才能用 ilspycmd
```

## Infiniium 安裝包（SetupInfiniium11.80.00012_full.exe）

- 2.99 GB，InstallShield `ISSetupStream` 格式，資料加密。
- macOS 上 7-Zip 無法解開；ilspycmd 也無法直接讀。
- 要取得內含 DLL：在 Windows 執行 `SetupInfiniium11.80.00012_full.exe /extract_all:C:\out`，或在安裝程式開著時從 `%TEMP%` 複製，再把 DLL 帶回 Mac 反編譯。
