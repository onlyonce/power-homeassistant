import pytest

from custom_components.hungarian_power.rate_budget import RequestBudget, RequestBudgetExceeded


def test_request_budget_rejects_the_next_request() -> None:
    budget = RequestBudget(maximum=2, window_seconds=3600)

    budget.acquire()
    budget.acquire()

    with pytest.raises(RequestBudgetExceeded):
        budget.acquire()

    assert budget.remaining == 0

