from datetime import datetime, timezone

from app.billing.periods import LIFETIME_END, lifetime_window, month_window


def test_month_window_mid_month():
    now = datetime(2026, 4, 18, 14, 30, tzinfo=timezone.utc)
    start, end = month_window(now)
    assert start == datetime(2026, 4, 1, tzinfo=timezone.utc)
    assert end == datetime(2026, 5, 1, tzinfo=timezone.utc)


def test_month_window_first_second():
    now = datetime(2026, 4, 1, 0, 0, 0, tzinfo=timezone.utc)
    start, end = month_window(now)
    assert start == datetime(2026, 4, 1, tzinfo=timezone.utc)
    assert end == datetime(2026, 5, 1, tzinfo=timezone.utc)


def test_month_window_last_microsecond():
    now = datetime(2026, 4, 30, 23, 59, 59, 999999, tzinfo=timezone.utc)
    start, end = month_window(now)
    assert start == datetime(2026, 4, 1, tzinfo=timezone.utc)
    assert end == datetime(2026, 5, 1, tzinfo=timezone.utc)


def test_month_window_december_rollover():
    now = datetime(2026, 12, 15, tzinfo=timezone.utc)
    start, end = month_window(now)
    assert start == datetime(2026, 12, 1, tzinfo=timezone.utc)
    assert end == datetime(2027, 1, 1, tzinfo=timezone.utc)


def test_month_window_non_utc_input_normalized():
    from datetime import timedelta
    tz_plus8 = timezone(timedelta(hours=8))
    now = datetime(2026, 5, 1, 3, 0, tzinfo=tz_plus8)
    start, end = month_window(now)
    assert start == datetime(2026, 4, 1, tzinfo=timezone.utc)
    assert end == datetime(2026, 5, 1, tzinfo=timezone.utc)


def test_lifetime_window():
    eff = datetime(2026, 1, 15, tzinfo=timezone.utc)
    start, end = lifetime_window(eff)
    assert start == eff
    assert end == LIFETIME_END
