# SaaS 計費報表工具（202608）

每月初把 Authme Dashboard 的原始計費資料，換算成各客戶報表與內部試算表要填的數字，
並自動跑 `saas-billing-report` skill 階段 3 的驗算。

## 為什麼需要這個

原本的流程是人工在 Excel / Google Sheets 篩選欄位、去重、算百分比。
這裡把算法 1 / 算法 2 與 JUJI 的 C–L 欄位寫成程式，好處是每次計算方式一致、
驗算公式（G+I+K = C、H+J+L = 100%）一定會跑到，而且算錯會擋下來而不是靜靜寄出去。

## 流程

```
1. 取原始資料   fetch/fetch_202608.js  →  data/202608/<client>.json
2. 計算 + 驗算  python -m saas_billing.report --month 202608 --data-dir data/202608
3. 填表         照輸出逐格填入各客戶報表（百分比記得加 ' 前綴）
4. 內部表       更新用量試算表 115/08 欄與收入認列表
5. 剩餘次數     剩餘率 ≤ 20% 的客戶標記續約提醒
```

### 1. 取得原始資料

瀏覽器登入 Dashboard，DevTools console 執行 `fetch/fetch_202608.js`。
JUJI 和 Aftee 的 tenantId 已經寫死在檔案裡；其餘客戶要先從 Dashboard 的
tenant 選擇器抄下 tenantId 填進去 —— 打錯 tenant 會拿到別的客戶的數字。

腳本會用 `skipCount` 翻頁到取完為止，避免用量大的月份被 `maxResultCount`
默默截斷。

### 2. 計算與驗算

```
python -m saas_billing.report --month 202608 --data-dir data/202608
```

沒放進去的客戶會自動跳過，所以可以先抓到誰算誰。
驗算沒過會列出原因並以 exit code 1 結束。

### 3. 填表注意

- 百分比欄位（JUJI 的 F/H/J/L）輸入時前面加半形單引號，例如 `'99.74%`，
  否則從上月複製來的儲存格會變成 `99.74%%`。
- Total 列是硬編碼不是公式，要手動算新值。
- Aftee、JUJI 的隱藏 Row 1 是內部計算說明，寄出前要刪掉。
- 紅陽報表有「內部使用（匯出請刪除）」欄位，匯出前刪除。

## 開始前請先看

**`docs/202608-carryforward.md`** —— 承接數字，以及三件要先跟國展確認的事：
Aftee 剩餘次數自 2026/04 起多報（B2B +5、B2C +86）、JUJI 剩餘率分母漏算續購、
Aftee 的 B2B/B2C 拆分規則無法從歷史 tab 重現。

## 測試

```
python3 tests/test_algorithms.py
```

## 檔案

| 路徑 | 用途 |
|---|---|
| `saas_billing/config.py` | 客戶單價、算法、tenant、承接餘額 |
| `saas_billing/algorithms.py` | 算法 1／算法 2、JUJI C–L 欄、驗算公式 |
| `saas_billing/report.py` | CLI，輸出各客戶要填的數字 |
| `fetch/fetch_202608.js` | 瀏覽器 console 抓原始資料 |
| `docs/202608-carryforward.md` | 承接數字與待確認事項 |
| `tests/test_algorithms.py` | 算法的合成資料測試 |

原始資料 `data/` 不進版控（含客戶 CustomerID）。
