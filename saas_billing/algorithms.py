"""The two billing algorithms, as implemented in e-KYC 3.17.0.

Source of truth is the SQL in the「e-KYC SaaS 計費報表」Notion page, not the
older prose description in the skill reference. The two disagree on 算法 1 —
see `algorithm1_legacy` below.

算法 1 驗證事件計次
    SELECT COUNT(*) FROM VerificationEvent
    WHERE TenantId = @TenantId
      AND COALESCE(LastModificationTime, CreationTime) >= @StartTime
      AND COALESCE(LastModificationTime, CreationTime) <  @EndTime
      AND State != 'Incomplete'

算法 2 狀態轉換計次
    SELECT COUNT(*) FROM VerificationEventState
    WHERE TenantId = @TenantId
      AND CreationTime >= @StartTime AND CreationTime < @EndTime
      AND State != 'Incomplete'
      AND ChildEventId IS NULL
      AND Source != 'Agent'

Input is the 計費報表 CSV export, one row per *state transition*:

    VerificationEventId,EventName,CustomerId,State,Source,CreationTime

The export is already restricted to 主事件 state changes, so `ChildEventId IS
NULL` needs no extra filtering here. EventName carries the workflow name
(default, id-card-fraud, b2b, b2c, Samsung, ...).
"""

from collections import Counter, defaultdict

INCOMPLETE = "incomplete"
AGENT = "agent"

# The export is PascalCase; the dashboard's JSON API is camelCase. Read both.
_ALIASES = {
    "event_id": ("VerificationEventId", "verificationEventId", "eventId", "id"),
    "event_name": ("EventName", "eventName", "workflowName", "WorkflowName"),
    "customer_id": ("CustomerId", "customerId", "clientCustomerId"),
    "state": ("State", "state"),
    "source": ("Source", "source"),
    "creation_time": ("CreationTime", "creationTime", "createdAt"),
}


def field(row, name):
    """Read a logical field from a row, whatever casing the export used."""
    for key in _ALIASES[name]:
        if key in row:
            value = row[key]
            if isinstance(value, dict):          # some payloads nest under status
                value = value.get(key) or value.get(name)
            return value
    return None


def _norm(value):
    return (value or "").strip().lower()


def state_of(row):
    return _norm(field(row, "state"))


def source_of(row):
    return _norm(field(row, "source"))


def final_states(rows):
    """The last state each VerificationEventId transitioned into.

    `VerificationEvent.State` in the 算法 1 SQL is the event's current state;
    reconstructed from the transition log by taking the latest CreationTime.
    """
    latest = {}
    for row in rows:
        event_id = field(row, "event_id")
        if event_id is None:
            continue
        stamp = field(row, "creation_time") or ""
        previous = latest.get(event_id)
        if previous is None or stamp >= previous[0]:
            latest[event_id] = (stamp, state_of(row))
    return {event_id: state for event_id, (_, state) in latest.items()}


def algorithm1(rows):
    """驗證事件計次: verification events whose current state is not Incomplete."""
    return sum(1 for state in final_states(rows).values() if state != INCOMPLETE)


def algorithm1_legacy(rows):
    """The skill reference's older wording: distinct (EventName, CustomerId).

    Kept only to show, month over month, whether the two definitions still
    agree. `algorithm1` is what the product now bills on.
    """
    return len({
        (field(row, "event_name"), field(row, "customer_id"))
        for row in rows
        if state_of(row) != INCOMPLETE
    })


def billable_transitions(rows):
    """算法 2's billable rows, kept for further breakdown."""
    return [
        row for row in rows
        if state_of(row) != INCOMPLETE and source_of(row) != AGENT
    ]


def algorithm2(rows):
    """狀態轉換計次: main-event state changes, excluding Incomplete and Agent."""
    return len(billable_transitions(rows))


def by_event_name(rows, algorithm):
    """Billable count split by EventName (Aftee's b2b / b2c / Samsung)."""
    grouped = defaultdict(list)
    for row in rows:
        grouped[field(row, "event_name") or "unknown"].append(row)
    fn = algorithm1 if algorithm == "algorithm1" else algorithm2
    return {name: fn(group) for name, group in sorted(grouped.items())}


def dashboard_cards(rows):
    """The 特定租戶 stat cards, so the sheet can be checked against the UI.

    驗證事件數 counts verification *cases* across every state; 已審核/已退件/
    待審核/未完成 are unique case counts by current state, each shown as a
    share of 驗證事件數.
    """
    states = final_states(rows)
    total_events = len(states)
    counts = Counter(states.values())
    share = lambda n: (n / total_events) if total_events else 0.0
    return {
        "驗證事件數": total_events,
        "已審核": counts.get("approved", 0),
        "已審核%": share(counts.get("approved", 0)),
        "已退件": counts.get("rejected", 0),
        "已退件%": share(counts.get("rejected", 0)),
        "待審核": counts.get("pending", 0),
        "待審核%": share(counts.get("pending", 0)),
        "未完成": counts.get(INCOMPLETE, 0),
        "未完成%": share(counts.get(INCOMPLETE, 0)),
        "不重複CustomerId": len({
            field(row, "customer_id") for row in rows if field(row, "customer_id")
        }),
    }


def juji_columns(rows):
    """Columns C..L of the JUJI monthly tab, built on 算法 2 (JUJI's algorithm).

    C 驗證總次數 is the billable state-transition count. D/E/F describe cases
    (matching the dashboard's 驗證事件數 and 未完成 cards), while G..L split the
    billable transitions by state, so G+I+K must come back to C.
    """
    billable = billable_transitions(rows)
    cards = dashboard_cards(rows)
    transition_states = Counter(state_of(row) for row in billable)

    c = len(billable)
    d = cards["驗證事件數"]
    e = cards["未完成"]
    g = transition_states.get("pending", 0)
    i = transition_states.get("approved", 0)
    k = transition_states.get("rejected", 0)

    pct = lambda n, base: (n / base) if base else 0.0
    return {
        "C_total_verifications": c,
        "D_total_events": d,
        "E_incomplete": e,
        "F_incomplete_pct": pct(e, d),
        "G_pending": g,
        "H_pending_pct": pct(g, c),
        "I_approved": i,
        "J_approved_pct": pct(i, c),
        "K_rejected": k,
        "L_rejected_pct": pct(k, c),
    }


def check_juji(cols):
    """階段 3 verification formulas. Returns a list of failure strings."""
    problems = []
    c = cols["C_total_verifications"]
    parts = cols["G_pending"] + cols["I_approved"] + cols["K_rejected"]
    if parts != c:
        problems.append(
            f"G+I+K = {parts} 但 C = {c}（差 {parts - c:+d}）—— "
            "有計費狀態轉換不屬於 Pending/Approved/Rejected"
        )
    pct_sum = cols["H_pending_pct"] + cols["J_approved_pct"] + cols["L_rejected_pct"]
    if c and abs(pct_sum - 1.0) > 0.0001:
        problems.append(f"H+J+L = {pct_sum:.4%}，應為 100.00%")
    if cols["E_incomplete"] > cols["D_total_events"]:
        problems.append("E > D —— 未完成案件數不可能多於驗證事件數")
    return problems
