"""CI has never once been green since it was created (2026-08-18) --
FAILURES (a genuine break) and NEEDS SIGNOFF (expected mid-development,
nothing's actually wrong) were treated as the same severity, both
exiting 1. A chronically-red CI trains everyone, agent included, to stop
looking at it -- which is exactly how 9 consecutive red pushes went
unnoticed 2026-08-25. Fixed: only real failures block; pending signoffs
are surfaced loudly (see main()'s warning output) but don't fail the
build. Falsification per Gate B18: these tests confirm compute_exit_code
actually distinguishes the two cases, not just returns 0 always.
"""
from validate_grounding import compute_exit_code
from validate_metrics import compute_exit_code as metrics_compute_exit_code


def test_no_failures_no_unsigned_is_clean():
    assert compute_exit_code(all_failures=[], all_unsigned=[]) == 0


def test_unsigned_only_does_not_block():
    """The actual behavior change: this used to exit 1."""
    assert compute_exit_code(all_failures=[], all_unsigned=["some pending item"]) == 0


def test_failures_alone_block():
    assert compute_exit_code(all_failures=["a broken claim"], all_unsigned=[]) == 1


def test_failures_and_unsigned_together_still_block():
    """A real break isn't excused by also having pending signoffs --
    failures always win, regardless of what else is going on."""
    assert compute_exit_code(all_failures=["a broken claim"], all_unsigned=["pending"]) == 1


def test_validate_metrics_reuses_the_same_function_not_a_copy():
    """Found live, 2026-08-25: validate_metrics.py had the identical
    severity-conflation bug in a sibling script that didn't get touched
    by the first fix -- CI still failed after 'the fix' because of this
    second, un-fixed copy. Now it imports the same function rather than
    re-deriving the same decision, so the two validators can't silently
    drift apart on this again."""
    assert metrics_compute_exit_code is compute_exit_code
