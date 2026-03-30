from .config import CENTER_MERGE_DELTA_M, NEAR_THRESHOLD_M
from .models import ZoneDistances


def classify_zone(left_m, right_m) -> str:
    """
    Classify obstacle position based on left/right distances.

    Returns: "LEFT", "RIGHT", "CENTER", or "CLEAR".
    left_m / right_m can be None if a reading failed.
    """
    left_near = left_m is not None and left_m < NEAR_THRESHOLD_M
    right_near = right_m is not None and right_m < NEAR_THRESHOLD_M

    if left_near and right_near:
        # If similar distance, treat as center; else closer side dominates
        if abs(left_m - right_m) < CENTER_MERGE_DELTA_M:
            return "CENTER"
        return "LEFT" if left_m < right_m else "RIGHT"
    elif left_near:
        return "LEFT"
    elif right_near:
        return "RIGHT"
    else:
        return "CLEAR"


def classify_from_zones(zones: ZoneDistances) -> str:
    """
    Classify using left/right, then allow center to override when closest.
    """
    base = classify_zone(zones.left_m, zones.right_m)
    if zones.center_m is None:
        return base

    candidates = [d for d in (zones.left_m, zones.right_m) if d is not None]
    if not candidates:
        return "CENTER" if zones.center_m < NEAR_THRESHOLD_M else "CLEAR"

    nearest_lr = min(candidates)
    if zones.center_m < NEAR_THRESHOLD_M and zones.center_m <= nearest_lr + CENTER_MERGE_DELTA_M:
        return "CENTER"
    return base
