"""Tests for Wilson CI (PREREGISTRATION §7)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from pv.stats import wilson_ci


def test_wilson_point_estimate():
    p, lo, hi = wilson_ci(45, 50)
    assert abs(p - 0.9) < 1e-9
    assert lo < 0.9 < hi
    # known Wilson interval for 45/50 ~ [0.786, 0.957]
    assert abs(lo - 0.7855) < 0.01
    assert abs(hi - 0.9573) < 0.01


def test_wilson_extremes():
    p, lo, hi = wilson_ci(50, 50)
    assert p == 1.0 and hi == 1.0 and lo < 1.0   # upper bound capped, lower < 1
    p0, lo0, hi0 = wilson_ci(0, 50)
    assert p0 == 0.0 and lo0 < 1e-9 and hi0 > 0.0


def test_wilson_empty():
    import math
    p, lo, hi = wilson_ci(0, 0)
    assert math.isnan(p) and lo == 0.0 and hi == 1.0
