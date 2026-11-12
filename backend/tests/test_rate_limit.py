from app.core.rate_limit import LoginRateLimiter


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_not_blocked_before_the_limit():
    limiter = LoginRateLimiter(max_attempts=3, window_seconds=60, clock=FakeClock())
    limiter.register_failure("k")
    limiter.register_failure("k")
    assert limiter.blocked_for("k") == 0


def test_blocked_after_max_failures_and_reports_wait_time():
    clock = FakeClock()
    limiter = LoginRateLimiter(max_attempts=3, window_seconds=60, clock=clock)
    for _ in range(3):
        limiter.register_failure("k")
    assert 0 < limiter.blocked_for("k") <= 60


def test_block_expires_after_the_window():
    clock = FakeClock()
    limiter = LoginRateLimiter(max_attempts=3, window_seconds=60, clock=clock)
    for _ in range(3):
        limiter.register_failure("k")
    clock.now += 61
    assert limiter.blocked_for("k") == 0


def test_keys_are_independent_and_reset_clears_one():
    limiter = LoginRateLimiter(max_attempts=2, window_seconds=60, clock=FakeClock())
    limiter.register_failure("a")
    limiter.register_failure("a")
    assert limiter.blocked_for("a") > 0
    assert limiter.blocked_for("b") == 0
    limiter.reset("a")
    assert limiter.blocked_for("a") == 0
