import math


def clamp_ts_to_milliseconds(ts: float) -> float:
    return round(ts, 3)


def sanitize_cost(value: float | None) -> float | None:
    """Normalize a reported cost or hourly rate to a usable USD amount, or None.

    Cost fields are nullable precisely so an unknown price stays distinguishable from a
    free resource, and SCT's `get_instance_price()` returns 0 for "unknown" (OCI always,
    modern GCE spot types, any catalog miss). SCT maps those to None, but a stale client
    or a mapping bug would otherwise store a 0 that renders as a genuine $0.00 - so
    anything unusable is collapsed to None here, at the boundary.

    Non-positive and non-finite values (NaN and the infinities both survive JSON parsing)
    are unusable. Unusable input is coerced rather than rejected: the cost rides along on
    `terminate_resource`, and failing that call over a bad cost would cost us the
    termination record itself, which matters far more than the number.
    """
    # bool is a subclass of int, so float(True) would silently become a $1.00 amount.
    # These payloads are untyped dicts, so a JSON `true` really can arrive here.
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or value <= 0:
        return None
    return value
