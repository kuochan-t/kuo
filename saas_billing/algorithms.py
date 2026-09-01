"""The two live billing algorithms, plus the JUJI column set.

Input everywhere is the raw `items` array from the billing export API:

    GET /api/identity-verification/v1/reports/billing/export
        ?startTime=...&endTime=...&tenantId=...

Each item carries at least `customerId`, `state`, `eventName`; Aftee also
carries `workflowName`, and algorithm 2 reads `source` to drop manual review.
"""

from collections import Counter

INCOMPLETE = "incomplete"
AGENT = "agent"


def _norm(value):
    return (value or "").strip().lower()


def _state(item):
    state = item.get("state")
    if isinstance(state, dict):          # some exports nest as status.state
        state = state.get("state")
    return _norm(state)


def _source(item):
    source = item.get("source")
    if isinstance(source, dict):
        source = source.get("source")
    return _norm(source)


def algorithm1(items):
    """Drop Incomplete, then count distinct (EventName, CustomerID) pairs."""
    pairs = {
        (item.get("eventName"), item.get("customerId"))
        for item in items
        if _state(item) != INCOMPLETE
    }
    return len(pairs)


def algorithm2(items):
    """Drop Source=Agent and State=Incomplete; the remaining rows are billable."""
    return sum(
        1
        for item in items
        if _source(item) != AGENT and _state(item) != INCOMPLETE
    )


def billable_items(items):
    """The algorithm-2 billable subset, kept as rows for further breakdown."""
    return [
        item
        for item in items
        if _source(item) != AGENT and _state(item) != INCOMPLETE
    ]


def juji_columns(items):
    """Columns C..L of the JUJI monthly tab.

    C 驗證總次數        billable event count
    D 不重複的 ID        distinct CustomerID over all items
    E Incomplete 不重複 ID
    F E / D
    G/I/K Pending / Approved / Rejected event counts within the billable set
    H/J/L each over C
    """
    billable = billable_items(items)
    states = Counter(_state(item) for item in billable)

    c = len(billable)
    d = len({item.get("customerId") for item in items if item.get("customerId")})
    e = len({
        item.get("customerId")
        for item in items
        if _state(item) == INCOMPLETE and item.get("customerId")
    })
    g, i, k = states.get("pending", 0), states.get("approved", 0), states.get("rejected", 0)

    pct = lambda n, base: (n / base) if base else 0.0
    return {
        "C_total_verifications": c,
        "D_total_customer_ids": d,
        "E_incomplete_unique_ids": e,
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
            f"G+I+K = {parts} but C = {c} (差 {parts - c:+d}) — "
            "有 billable 事件落在 Pending/Approved/Rejected 以外的狀態"
        )
    pct_sum = cols["H_pending_pct"] + cols["J_approved_pct"] + cols["L_rejected_pct"]
    if abs(pct_sum - 1.0) > 0.0001 and c:
        problems.append(f"H+J+L = {pct_sum:.4%}, 應為 100.00%")
    if cols["E_incomplete_unique_ids"] > cols["D_total_customer_ids"]:
        problems.append("E > D — Incomplete 不重複 ID 不可能多於總不重複 ID")
    return problems


def aftee_by_workflow(items):
    """Algorithm-2 billable counts split by workflow (b2b / b2c / Samsung)."""
    counts = Counter(
        (item.get("workflowName") or "unknown") for item in billable_items(items)
    )
    return dict(counts)
