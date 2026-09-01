"""Client billing configuration for the monthly SaaS report.

Rates and carry-forward balances were read from the live sheets on 2026-09-01,
with 115/07 (2026-07) as the last closed month.
"""

# --- Billing algorithms -------------------------------------------------------
# ALG1: drop State=Incomplete, then count distinct (EventName, CustomerID).
# ALG2: drop Source=Agent and State=Incomplete, then count the remaining rows.
ALG1 = "algorithm1"
ALG2 = "algorithm2"

# Tenant IDs the reference file records explicitly. The rest have to be read off
# the Dashboard tenant selector each month; leaving them None keeps the fetch
# snippet honest instead of guessing an ID into a billing query.
CLIENTS = {
    "esafe": {
        "label": "紅陽",
        "tenant_name": "Esafe",
        "tenant_id": None,
        "algorithm": ALG2,
        "unit_price": 42.0,
        "internal_row": "紅陽",
    },
    "amazingtalker": {
        "label": "Amazing Talker",
        "tenant_name": "AmazingTalker",
        "tenant_id": None,
        "algorithm": ALG1,
        "unit_price": 35.772,
        "internal_row": "Amazing Talker",
        # AT bills on FaceMatch.State Approved + Reject, with Incomplete
        # remapped to Reject before the summary is taken.
        "remap_incomplete_to_reject": True,
    },
    "xo_dating": {
        "label": "XO Dating (Rooit)",
        "tenant_name": "XO_dating",
        "tenant_id": None,
        "algorithm": ALG1,
        "unit_price": 2.5,          # 活體辨識
        "unit_price_jp_document": 18.0,  # 日本證件
        "internal_row": "Rooit",
    },
    "aftee": {
        "label": "Aftee (恩沛科技)",
        "tenant_name": "aftee",
        "tenant_id": "3a0f6f28-ab2f-0ac1-abe5-502db51fc790",
        "algorithm": ALG2,
        "unit_price": 16.6,
        "internal_row": "恩沛科技Aftee",
        "workflows": ["b2b", "b2c", "Samsung"],
    },
    "gamania_xchanger": {
        "label": "GamaniaXchanger",
        "tenant_name": "GamaniaXchanger",
        "tenant_id": None,
        "algorithm": ALG1,
        "unit_price": None,
        "internal_row": None,
    },
    "juji": {
        "label": "JUJI (Gogolook)",
        "tenant_name": "JUJI",
        "tenant_id": "3a1799d1-fbb1-4c91-351a-edf86d0cb8b7",
        "algorithm": ALG2,
        # 收入認列表 note: 單次＠$31, 202607 起改為 $4.
        "unit_price": 4.0,
        "unit_price_before_202607": 31.0,
        "internal_row": "Juji(Gogolook)",
        # 使用量 is the raw billable count; 調整用量 = 使用量 / 3 because
        # 3 次 OCR 辨識算 1 次驗證 while 階段一 has no face match integrated.
        "usage_divisor": 3,
    },
    # 下線中 — no client-facing report, but the count is still needed monthly.
    "cashmallow_hk": {
        "label": "Cashmallow HK",
        "tenant_name": "cm api",
        "tenant_id": None,
        "algorithm": ALG2,
        "unit_price": 16.095,
        "internal_row": "Cashmallow",
        "offboarding": True,
    },
    "cashmallow_jp": {
        "label": "Cashmallow JP",
        "tenant_name": "Cashmallow_JP",
        "tenant_id": None,
        "algorithm": ALG2,
        "unit_price": 16.095,
        "internal_row": "Cashmallow",
        "offboarding": True,
    },
}

# --- Carry-forward balances as of 115/07 (2026-07) ----------------------------
# Read from the client report sheets on 2026-09-01. `remaining_*_sheet` is what
# the sheet currently shows; `remaining_*_derived` is purchase minus cumulative
# usage. Where the two disagree the sheet has drifted — see docs/.
CARRY_FORWARD = {
    "juji": {
        "purchased": 16000,
        "gift": 4000,
        "renewal_202605": 16000,
        "contract_total": 36000,
        "cumulative_adjusted_usage_sheet": 21543,
        "remaining_sheet": 14457,
        "remaining_rate_sheet": 0.7229,
        "last_month_usage": 4660,
        "last_month_adjusted_usage": 1553,
    },
    "aftee": {
        "purchase_b2b": 600,
        "purchase_b2c": 20000,
        "cumulative_b2b": 63,
        "cumulative_b2c": 727,
        "remaining_b2b_sheet": 542,
        "remaining_b2c_sheet": 19359,
        "last_month_b2b": 18,
        "last_month_b2c": 37,
    },
}

# 115/07 usage, for the >30% month-over-month check in 階段 3.
LAST_MONTH_USAGE = {
    "紅陽": 0,
    "Amazing Talker": 822,
    "Rooit": 3331,          # 活體辨識; 日本證件 0
    "Cashmallow": 0,
    "恩沛科技Aftee": 55,
    "Juji(Gogolook)": 1553,  # 調整用量
    "MicroClub": 4,
}

RENEWAL_ALERT_THRESHOLD = 0.20
