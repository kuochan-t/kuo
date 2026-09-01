"""Turn the 計費報表 exports for a month into the numbers each sheet needs.

Usage:
    python -m saas_billing.report --month 202608 --data-dir data/202608

`--data-dir` holds one export per client, named for the key in config.CLIENTS
(juji.csv, aftee.csv, ...). Both the CSV export from the 計費報表 dashboard and
the raw JSON from the billing export API are accepted.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

from . import algorithms as alg
from .config import CARRY_FORWARD, CLIENTS, LAST_MONTH_USAGE, RENEWAL_ALERT_THRESHOLD


def load_rows(path):
    """Read one export into a list of row dicts."""
    if path.suffix.lower() == ".csv":
        with open(path, encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, list):
        return payload
    for key in ("items", "result"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict) and isinstance(value.get("items"), list):
            return value["items"]
    raise ValueError(f"{path}: 找不到 items 陣列")


def find_export(data_dir, key):
    for suffix in (".csv", ".json"):
        path = data_dir / f"{key}{suffix}"
        if path.exists():
            return path
    return None


def pct(value):
    return f"{value * 100:.2f}%"


def compare_last_month(client, count):
    """階段 3 的歷史趨勢檢查。"""
    previous = LAST_MONTH_USAGE.get(client.get("internal_row"))
    if previous:
        delta = (count - previous) / previous
        flag = "  ⚠ 月變動 >30%，請國展確認" if abs(delta) > 0.30 else ""
        print(f"  對比 115/07 ({previous:,}): {delta:+.1%}{flag}")
    elif previous == 0 and count:
        print(f"  ⚠ 115/07 為 0，本月有 {count:,} 筆，請確認是否恢復使用")


def report_juji(rows, month):
    cols = alg.juji_columns(rows)
    problems = alg.check_juji(cols)
    cf = CARRY_FORWARD["juji"]
    divisor = CLIENTS["juji"]["usage_divisor"]

    usage = cols["C_total_verifications"]
    adjusted = usage // divisor
    cumulative = cf["cumulative_adjusted_usage_sheet"] + adjusted
    remaining = cf["contract_total"] - cumulative

    print(f"\n=== JUJI (Gogolook) — {month} ===")
    print("Row 4（逐格輸入，百分比欄位前面加半形單引號 '）:")
    layout = [
        ("C4 驗證總次數", "C_total_verifications", False),
        ("D4 驗證事件數", "D_total_events", False),
        ("E4 未完成", "E_incomplete", False),
        ("F4 未完成 %", "F_incomplete_pct", True),
        ("G4 Pending", "G_pending", False),
        ("H4 Pending %", "H_pending_pct", True),
        ("I4 Approved", "I_approved", False),
        ("J4 Approved %", "J_approved_pct", True),
        ("K4 Rejected", "K_rejected", False),
        ("L4 Rejected %", "L_rejected_pct", True),
    ]
    for label, key, is_pct in layout:
        # 半形單引號前綴，避免從上月 tab 複製來的儲存格把 % 二次格式化
        value = chr(39) + pct(cols[key]) if is_pct else f"{cols[key]:,}"
        print(f"  {label:<20}{value:>12}")

    print("\n總覽頁:")
    print(f"  使用量                {usage:>12,}")
    print(f"  調整用量 (÷{divisor})        {adjusted:>12,}")
    print(f"  累計已使用            {cumulative:>12,}   "
          f"= {cf['cumulative_adjusted_usage_sheet']:,} + {adjusted:,}")
    print(f"  剩餘數量              {remaining:>12,}   "
          f"= {cf['contract_total']:,} - {cumulative:,}")
    rate = remaining / cf["contract_total"]
    print(f"  剩餘率（對合約 {cf['contract_total']:,}）{pct(rate):>9}")

    compare_last_month(CLIENTS["juji"], adjusted)
    price = CLIENTS["juji"]["unit_price"]
    print(f"  收入認列              {adjusted:,} × ${price} = ${adjusted * price:,.0f}")
    return {"問題": problems, "剩餘率": rate}


def report_aftee(rows, month):
    client = CLIENTS["aftee"]
    split = alg.by_event_name(rows, client["algorithm"])
    cf = CARRY_FORWARD["aftee"]

    print(f"\n=== Aftee (恩沛科技) — {month} ===")
    print("算法 2 計費筆數，依 EventName 拆分:")
    for name, count in split.items():
        print(f"  {name:<14}{count:>10,}")
    print(f"  {'合計':<14}{sum(split.values()):>10,}")
    print("\n⚠ Usage Count 的 B2B / B2C 對應規則待確認 —— 見 docs/202608-carryforward.md。"
          "\n  這裡只輸出各 EventName 的算法 2 筆數，不代填 Usage Count。")
    print("\n剩餘次數（承接 115/07）:")
    for tag, purchase, cumulative, sheet in [
        ("B2B", cf["purchase_b2b"], cf["cumulative_b2b"], cf["remaining_b2b_sheet"]),
        ("B2C", cf["purchase_b2c"], cf["cumulative_b2c"], cf["remaining_b2c_sheet"]),
    ]:
        print(f"  {tag}  購買 {purchase:,} / 累計 {cumulative:,} / "
              f"表上剩餘 {sheet:,}（推算應為 {purchase - cumulative:,}）")
    compare_last_month(client, sum(split.values()))
    return {"問題": []}


def report_generic(key, rows, month):
    client = CLIENTS[key]
    algorithm = client["algorithm"]
    count = alg.algorithm1(rows) if algorithm == "algorithm1" else alg.algorithm2(rows)

    print(f"\n=== {client['label']} — {month} ===")
    print(f"  計費筆數（{algorithm}）{count:>10,}")

    problems = []
    if algorithm == "algorithm1":
        legacy = alg.algorithm1_legacy(rows)
        if legacy != count:
            print(f"  舊定義 (EventName+CustomerId) {legacy:>10,}   差 {count - legacy:+,}")
            problems.append(
                f"算法 1 新舊定義結果不同（{count:,} vs {legacy:,}），"
                "請確認要用哪一個對客戶計費"
            )

    price = client.get("unit_price")
    if price:
        print(f"  收入認列  {count:,} × ${price} = ${count * price:,.0f}")
    compare_last_month(client, count)
    return {"問題": problems}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--month", required=True, help="報表月份，如 202608")
    parser.add_argument("--data-dir", required=True, type=Path)
    args = parser.parse_args(argv)

    if not args.data_dir.is_dir():
        parser.error(f"{args.data_dir} 不存在 —— 請先依 README 取得計費報表匯出檔")

    problems, seen = [], []
    for key in CLIENTS:
        path = find_export(args.data_dir, key)
        if path is None:
            continue
        seen.append(key)
        rows = load_rows(path)
        if key == "juji":
            result = report_juji(rows, args.month)
        elif key == "aftee":
            result = report_aftee(rows, args.month)
        else:
            result = report_generic(key, rows, args.month)
        problems.extend(f"{CLIENTS[key]['label']}: {p}" for p in result["問題"])

    if not seen:
        parser.error(f"{args.data_dir} 裡沒有任何 <client>.csv 或 .json")

    missing = [CLIENTS[k]["label"] for k in CLIENTS
               if k not in seen and not CLIENTS[k].get("offboarding")]
    print("\n" + "=" * 60)
    if missing:
        print(f"尚未提供資料的客戶: {', '.join(missing)}")
    if problems:
        print("驗算未通過，請先處理:")
        for problem in problems:
            print(f"  ✗ {problem}")
        return 1
    print("驗算通過。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
