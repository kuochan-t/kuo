"""Synthetic-data checks for the billing algorithms."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from saas_billing import algorithms as alg


def item(customer, state, event="verify", source="System", workflow="b2c"):
    return {"customerId": customer, "state": state, "eventName": event,
            "source": source, "workflowName": workflow}


def test_algorithm1_dedupes_event_customer_pairs():
    items = [
        item("A", "Approved"), item("A", "Approved"),      # same pair -> 1
        item("A", "Approved", event="register"),           # different event -> 1
        item("B", "Rejected"),                             # -> 1
        item("C", "Incomplete"),                           # dropped
    ]
    assert alg.algorithm1(items) == 3


def test_algorithm2_drops_agent_and_incomplete():
    items = [
        item("A", "Approved"),
        item("A", "Approved"),                             # repeat still bills
        item("B", "Approved", source="Agent"),             # manual review, dropped
        item("C", "Incomplete"),                           # dropped
        item("D", "Rejected"),
    ]
    assert alg.algorithm2(items) == 3


def test_state_and_source_matching_is_case_insensitive_and_nested():
    items = [
        {"customerId": "A", "state": {"state": "INCOMPLETE"}},
        {"customerId": "B", "source": {"source": "agent"}, "state": "Approved"},
        {"customerId": "C", "state": "approved"},
    ]
    assert alg.algorithm2(items) == 1


def test_juji_columns_and_verification_formulas():
    items = (
        [item(f"p{n}", "Pending") for n in range(10)]
        + [item(f"a{n}", "Approved") for n in range(85)]
        + [item(f"r{n}", "Rejected") for n in range(5)]
        + [item(f"i{n}", "Incomplete") for n in range(40)]
        + [item("agent1", "Approved", source="Agent")]
    )
    cols = alg.juji_columns(items)
    assert cols["C_total_verifications"] == 100          # 10 + 85 + 5
    assert cols["D_total_customer_ids"] == 141           # every id distinct
    assert cols["E_incomplete_unique_ids"] == 40
    assert cols["G_pending"] == 10
    assert cols["I_approved"] == 85
    assert cols["K_rejected"] == 5
    assert abs(cols["J_approved_pct"] - 0.85) < 1e-9
    assert alg.check_juji(cols) == []                    # G+I+K == C, H+J+L == 100%


def test_check_juji_flags_unaccounted_states():
    items = [item("a", "Approved"), item("b", "Processing")]
    problems = alg.check_juji(alg.juji_columns(items))
    assert problems, "Processing 落在 G/I/K 之外，應該被驗算擋下來"


def test_aftee_splits_by_workflow():
    items = [
        item("a", "Approved", workflow="b2b"),
        item("b", "Approved", workflow="b2c"),
        item("c", "Rejected", workflow="Samsung"),
        item("d", "Incomplete", workflow="Samsung"),      # dropped
        item("e", "Approved", workflow="b2c", source="Agent"),  # dropped
    ]
    assert alg.aftee_by_workflow(items) == {"b2b": 1, "b2c": 1, "Samsung": 1}


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
