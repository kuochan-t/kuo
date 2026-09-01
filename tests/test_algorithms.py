"""Synthetic-data checks against the SQL definitions in the 計費報表 doc."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from saas_billing import algorithms as alg


def row(event_id, state, when, customer="c1", event="default", source="System"):
    """One VerificationEventState row, in the CSV export's column names."""
    return {"VerificationEventId": event_id, "EventName": event,
            "CustomerId": customer, "State": state, "Source": source,
            "CreationTime": when}


def test_algorithm1_counts_events_by_their_final_state():
    rows = [
        row("e1", "Pending", "2026-08-01T10:00:00Z"),
        row("e1", "Approved", "2026-08-01T11:00:00Z"),   # e1 ends Approved -> bills
        row("e2", "Pending", "2026-08-02T10:00:00Z"),
        row("e2", "Incomplete", "2026-08-02T12:00:00Z"),  # e2 ends Incomplete -> no
        row("e3", "Rejected", "2026-08-03T10:00:00Z"),    # bills
    ]
    assert alg.algorithm1(rows) == 2


def test_algorithm1_ignores_an_earlier_incomplete_transition():
    rows = [
        row("e1", "Incomplete", "2026-08-01T10:00:00Z"),
        row("e1", "Approved", "2026-08-01T11:00:00Z"),
    ]
    assert alg.algorithm1(rows) == 1


def test_algorithm1_legacy_differs_from_the_event_count():
    # Two events for the same customer and EventName: the SQL bills both,
    # the reference file's older wording collapses them into one.
    rows = [
        row("e1", "Approved", "2026-08-01T10:00:00Z", customer="a"),
        row("e2", "Approved", "2026-08-05T10:00:00Z", customer="a"),
    ]
    assert alg.algorithm1(rows) == 2
    assert alg.algorithm1_legacy(rows) == 1


def test_algorithm2_counts_transitions_dropping_incomplete_and_agent():
    rows = [
        row("e1", "Pending", "2026-08-01T10:00:00Z"),
        row("e1", "Approved", "2026-08-01T11:00:00Z"),    # both transitions bill
        row("e2", "Incomplete", "2026-08-02T10:00:00Z"),  # dropped
        row("e3", "Rejected", "2026-08-03T10:00:00Z", source="Agent"),  # dropped
        row("e4", "Approved", "2026-08-04T10:00:00Z"),
    ]
    assert alg.algorithm2(rows) == 3


def test_fields_are_read_from_camelcase_payloads_too():
    rows = [
        {"verificationEventId": "e1", "state": "Approved",
         "creationTime": "2026-08-01T10:00:00Z", "source": "System",
         "eventName": "default", "customerId": "a"},
        {"verificationEventId": "e2", "state": "incomplete",
         "creationTime": "2026-08-01T10:00:00Z", "source": "System",
         "eventName": "default", "customerId": "b"},
    ]
    assert alg.algorithm2(rows) == 1
    assert alg.algorithm1(rows) == 1


def test_split_by_event_name_matches_aftee_workflows():
    rows = [
        row("e1", "Approved", "2026-08-01T10:00:00Z", event="b2b"),
        row("e2", "Approved", "2026-08-01T10:00:00Z", event="b2c"),
        row("e2", "Rejected", "2026-08-01T11:00:00Z", event="b2c"),
        row("e3", "Incomplete", "2026-08-01T10:00:00Z", event="Samsung"),
    ]
    assert alg.by_event_name(rows, "algorithm2") == {"b2b": 1, "b2c": 2, "Samsung": 0}


def test_dashboard_cards_count_cases_not_transitions():
    rows = [
        row("e1", "Pending", "2026-08-01T10:00:00Z"),
        row("e1", "Approved", "2026-08-01T11:00:00Z"),
        row("e2", "Incomplete", "2026-08-02T10:00:00Z"),
    ]
    cards = alg.dashboard_cards(rows)
    assert cards["驗證事件數"] == 2          # two cases, three transitions
    assert cards["已審核"] == 1
    assert cards["未完成"] == 1
    assert abs(cards["已審核%"] - 0.5) < 1e-9


def test_juji_columns_and_verification_formulas():
    rows = []
    for n in range(10):
        rows.append(row(f"p{n}", "Pending", "2026-08-01T10:00:00Z", customer=f"p{n}"))
    for n in range(85):
        rows.append(row(f"a{n}", "Approved", "2026-08-01T10:00:00Z", customer=f"a{n}"))
    for n in range(5):
        rows.append(row(f"r{n}", "Rejected", "2026-08-01T10:00:00Z", customer=f"r{n}"))
    for n in range(40):
        rows.append(row(f"i{n}", "Incomplete", "2026-08-01T10:00:00Z", customer=f"i{n}"))
    rows.append(row("ag", "Approved", "2026-08-01T10:00:00Z", source="Agent"))

    cols = alg.juji_columns(rows)
    assert cols["C_total_verifications"] == 100      # 10 + 85 + 5, Agent excluded
    assert cols["D_total_events"] == 141             # every event id distinct
    assert cols["E_incomplete"] == 40
    assert (cols["G_pending"], cols["I_approved"], cols["K_rejected"]) == (10, 85, 5)
    assert abs(cols["J_approved_pct"] - 0.85) < 1e-9
    assert alg.check_juji(cols) == []                # G+I+K == C, H+J+L == 100%


def test_check_juji_flags_a_state_outside_g_i_k():
    rows = [
        row("e1", "Approved", "2026-08-01T10:00:00Z"),
        row("e2", "Processing", "2026-08-01T10:00:00Z"),
    ]
    assert alg.check_juji(alg.juji_columns(rows)), "Processing 應該被驗算擋下來"


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS  {name}")
            except AssertionError as exc:
                failures += 1
                print(f"  FAIL  {name}: {exc}")
    print(f"\n{'all passed' if not failures else f'{failures} failed'}")
    sys.exit(1 if failures else 0)
