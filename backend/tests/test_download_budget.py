import pytest


def test_download_budget_stops_before_extra_request_or_bytes():
    from app.download_budget import DownloadBudget

    budget = DownloadBudget(max_requests=2, max_bytes=5, interval=0)
    budget.request()
    budget.received(3)
    budget.request()
    budget.received(2)
    with pytest.raises(ValueError, match="REQUEST_BUDGET"):
        budget.request()
    with pytest.raises(ValueError, match="BYTE_BUDGET"):
        budget.received(1)
    assert budget.requests == 2 and budget.bytes == 5


def test_request_spacing_uses_monotonic_clock(monkeypatch):
    from app import download_budget as mod

    now = [0.0]
    monkeypatch.setattr(mod.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(mod.time, "sleep", lambda seconds: now.__setitem__(0, now[0] + seconds))
    budget = mod.DownloadBudget(interval=2)
    budget.request()
    budget.request()
    budget.request()
    assert now[0] >= 4
