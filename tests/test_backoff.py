from app.tasks.backoff import exponential_backoff_with_jitter


def test_first_attempt_backoff_is_small():
    delay = exponential_backoff_with_jitter(0, base=2.0, cap=60.0)

    assert delay >= 1.0
    assert delay <= 2.0


def test_backoff_is_bounded_by_cap():
    delay = exponential_backoff_with_jitter(20, base=2.0, cap=60.0)

    assert delay <= 60.0


def test_backoff_is_nonnegative():
    delay = exponential_backoff_with_jitter(3, base=2.0, cap=60.0)

    assert delay >= 0.0
