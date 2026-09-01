"""Turn the raw billing exports for a month into the numbers each sheet needs.

Usage:
    python -m saas_billing.report --month 202608 --data-dir data/202608

`--data-dir` holds one JSON file per client, named for the key in config.CLIENTS
(e.g. juji.json, aftee.json). Each file is either the raw API response or the
bare `items` array.
"""

import argparse
import json
import sys
from pathlib import Path

from . import algorithms as alg
from .config import CARRY_FORWARD, CLIENTS, LAST_MONTH_USAGE, RENEWAL_ALERT_THRESHOLD


def load_items(path):
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


def pct(value):
    return f"{value * 100:.2f}%"


def report_juji(items, month):
    cols = alg.juji_columns(items)
    problems = alg.check_juji(cols)
    cf = CARRY_FORWARD["juji"]
    divisor = CLIENTS["juji"]["usage_divisor"]

    usage = cols["C_total_verifications"]
    adjusted = usage // divisor
    cumulative = cf["cumulative_adjusted_usage_sheet"] + adjusted
    remaining = cf["contract_total"] - cumulative

    print(f"\n=== JUJI (Gogolook) — {month} ===")
    print("Row 4 (逐格輸入，百分比欄位前面加半形單引號 '):")
    for label, key in [
        ("C4 驗證總次數", "C_total_verifications"),
        ("D4 不重複 ID", "D_total_customer_ids"),
        ("E4 Incomplete 不重複 ID", "E_incomplete_unique_ids"),
    ]:
        print(f"  {label:<26}{cols[key]:>10,}")
    for label, key in [
        ("F4 Incomplete %", "F_incomplete_pct"),
        ("H4 Pending %", "H_pending_pct"),
        ("J4 Approved %", "J_approved_pct"),
        ("L4 Rejected %", "L_rejected_pct"),
    ]:
        # 半形單引號前綴，避免從上月 tab 複製來的儲存格把 % 二次格式化
        print(f"  {label:<26}{chr(39) + pct(cols[key]):>10}")
    for label, key in [
        ("G4 Pending", "G_pending"),
        ("I4 Approved", "I_approved"),
        ("K4 Rejected", "K_rejected"),
    ]:
        print(f"  {label:<26}{cols[key]:>10,}")

    print("\n總覽頁:")
    print(f"  使用量                    {usage:>10,}")
    print(f"  調整用量 (÷{divisor})            {adjusted:>10,}")
    print(f"  累計已使用 (調整後)        {cumulative:>10,}   "
          f"= {cf['cumulative_adjusted_usage_sheet']:,} + {adjusted:,}")
    print(f"  剩餘數量                  {remaining:>10,}   "
          f"= {cf['contract_total']:,} - {cumulative:,}")
    print(f"  剩餘率 (對合約總數)        {pct(remaining / cf['contract_total']):>10}")

    price = CLIENTS["juji"]["unit_price"]
    print(f"\n收入認列: {adjusted:,} × ${price} = ${adjusted * price:,.0f}")
    return {"問題": problems, "調整用量": adjusted,
            "剩餘率": remaining / cf["contract_total"]}


def report_aftee(items, month):
    by_workflow = alg.aftee_by_workflow(items)
    cf = CARRY_FORWARD["aftee"]

    print(f"\n=== Aftee (恩沛科技) — {month} ===")
    print("算法 2 各 workflow 計費筆數:")
    for name, count in sorted(by_workflow.items()):
        print(f"  {name:<12}{count:>8,}")
    print(f"  {'合計':<12}{sum(by_workflow.values()):>8,}")
    print("\n⚠ Usage Count 的 B2B / B2C 拆分規則待確認 —— 見 docs/202608-carryforward.md。"
          "\n  歷史 tab 的 B2B 等於 Approved+Rejected，但 B2C 無法用單一規則重現，"
          "\n  所以這裡只輸出各 workflow 的算法 2 筆數，不代填 Usage Count。")
    print(f"\n剩餘次數 (承接 115/07):")
    print(f"  B2B  購買 {cf['purchase_b2b']:,} / 累計 {cf['cumulative_b2b']:,} "
          f"/ 表上剩餘 {cf['remaining_b2b_sheet']:,} "
          f"(推算應為 {cf['purchase_b2b'] - cf['cumulative_b2b']:,})")
    print(f"  B2C  購買 {cf['purchase_b2c']:,} / 累計 {cf['cumulative_b2c']:,} "
          f"/ 表上剩餘 {cf['remaining_b2c_sheet']:,} "
          f"(推算應為 {cf['purchase_b2c'] - cf['cumulative_b2c']:,})")
    return {"問題": [], "workflow": by_workflow}


def report_generic(key, items, month):
    client = CLIENTS[key]
    count = (alg.algorithm1(items) if client["algorithm"] == "algorithm1"
             else alg.algorithm2(items))
    print(f"\n=== {client['label']} — {month} ===")
    print(f"  計費筆數 ({client['algorithm']}) {count:>10,}")
    price = client.get("unit_price")
    if price:
        print(f"  收入認列  {count:,} × ${price} = ${count * price:,.0f}")

    previous = LAST_MONTH_USAGE.get(client.get("internal_row"))
    if previous:
        delta = (count - previous) / previous
        flag = "  ⚠ 月變動 >30%，請國展確認" if abs(delta) > 0.30 else ""
        print(f"  對比 115/07 ({previous:,}): {delta:+.1%}{flag}")
    elif previous == 0 and count:
        print(f"  ⚠ 115/07 為 0，本月有 {count:,} 筆，請確認")
    return {"問題": [], "計費筆數": count}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--month", required=True, help="報表月份，如 202608")
    parser.add_argument("--data-dir", required=True, type=Path)
    args = parser.parse_args(argv)

    if not args.data_dir.is_dir():
        parser.error(f"{args.data_dir} 不存在 —— 請先依 fetch/ 的說明取得原始資料")

    problems, seen = [], False
    for key in CLIENTS:
        path = args.data_dir / f"{key}.json"
        if not path.exists():
            continue
        seen = True
        items = load_items(path)
        if key == "juji":
            result = report_juji(items, args.month)
        elif key == "aftee":
            result = report_aftee(items, args.month)
        else:
            result = report_generic(key, items, args.month)
        problems.extend(f"{CLIENTS[key]['label']}: {p}" for p in result["問題"])

    if not seen:
        parser.error(f"{args.data_dir} 裡沒有任何 <client>.json")

    print("\n" + "=" * 60)
    if problems:
        print("驗算未通過，請先處理:")
        for problem in problems:
            print(f"  ✗ {problem}")
        return 1
    print("驗算通過。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
