from __future__ import annotations
import time
from dataclasses import dataclass
from hyprwall.core.power import PowerStatus

@dataclass(frozen=True)
class Hysteresis:
    eco_enter: int = 40
    eco_exit: int = 45
    strict_enter: int = 20
    strict_exit: int = 25

def choose_profile(st: PowerStatus, last: str | None, h: Hysteresis) -> str:
    # On AC power, always use balanced
    if st.on_ac is True:
        return "balanced"  # Or "performance"

    # If no battery percentage info, fallback to balanced
    if st.percent is None:
        return last or "balanced"

    p = st.percent

    # STRICT hysteresis
    if last == "eco_strict":
        if p > h.strict_exit:
            return "eco" if p < h.eco_enter else "balanced"
        return "eco_strict"
    else:
        if p <= h.strict_enter:
            return "eco_strict"

    # ECO hysteresis
    if last == "eco":
        if p > h.eco_exit:
            return "balanced"
        return "eco"
    else:
        if p <= h.eco_enter:
            return "eco"

    return "balanced"


def should_switch(
    target: str,
    last: str,
    last_switch_at: float,
    cooldown_s: int,
    override_profile: str | None,
) -> bool:
    """
    Determine if a profile switch should be allowed.

    Returns False if:
    - An override profile is set (manual mode)
    - Cooldown period hasn't elapsed
    - Target is same as last
    """
    # Manual override active - no auto switching
    if override_profile is not None:
        return False

    # Same profile - no need to switch
    if target == last:
        return False

    # Cooldown check
    now = time.time()
    if last_switch_at > 0 and (now - last_switch_at) < cooldown_s:
        return False

    return True
