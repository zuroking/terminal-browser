import time

from terminal_browser.core.clock import Clock, FakeClock, SystemClock


def test_system_clock_monotonic_is_non_decreasing() -> None:
    clock = SystemClock()
    first = clock.now_monotonic()
    second = clock.now_monotonic()

    assert second >= first


def test_system_clock_epoch_is_plausible() -> None:
    before = time.time()
    observed = SystemClock().now_epoch()
    after = time.time()

    assert before <= observed <= after


def test_fake_clock_advance_moves_both_clocks() -> None:
    clock = FakeClock(monotonic_start=10.0, epoch_start=100.0)

    clock.advance(2.5)

    assert clock.now_monotonic() == 12.5
    assert clock.now_epoch() == 102.5


def test_fake_clock_epoch_can_move_backward_without_moving_monotonic() -> None:
    clock = FakeClock(monotonic_start=10.0, epoch_start=100.0)
    monotonic_before = clock.now_monotonic()

    clock.set_epoch(1.0)

    assert clock.now_monotonic() == monotonic_before
    assert clock.now_epoch() == 1.0


def test_fake_clock_rejects_negative_advance() -> None:
    clock = FakeClock(monotonic_start=10.0, epoch_start=100.0)

    try:
        clock.advance(-1.0)
    except ValueError:
        return
    raise AssertionError("negative advance must be rejected")


def test_clock_protocol_is_structurally_satisfied() -> None:
    assert isinstance(SystemClock(), Clock)
    assert isinstance(FakeClock(monotonic_start=0.0, epoch_start=0.0), Clock)
