"""Statistics for the study (PREREGISTRATION §7).

Wilson 95% CI here (no SciPy dependency — closed form). Bootstrap spread / McNemar live in
the separate analysis stage; this module holds what the runner's results table needs inline.
"""

from __future__ import annotations

import math

Z_95 = 1.959963984540054  # standard normal 0.975 quantile


def wilson_ci(k: int, n: int, z: float = Z_95) -> tuple[float, float, float]:
    """Wilson score interval for a binomial proportion.

    Returns (point_estimate, lo, hi) as proportions in [0,1]. n==0 -> (nan, 0, 1).
    """
    if n == 0:
        return (float("nan"), 0.0, 1.0)
    p = k / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    margin = (z * math.sqrt((p * (1 - p) + z2 / (4 * n)) / n)) / denom
    return (p, max(0.0, center - margin), min(1.0, center + margin))
