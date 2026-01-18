from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class PowerStatus:
    on_ac: bool | None
    percent: int | None

def _read_text(p: Path) -> str | None:
    try:
        return p.read_text(errors="ignore").strip()
    except Exception:
        return None

def _read_int(p: Path) -> int | None:
    s = _read_text(p)
    if s is None:
        return None
    try:
        return int(s)
    except ValueError:
        return None

def get_power_status() -> PowerStatus:
    root = Path("/sys/class/power_supply")
    if not root.exists():
        return PowerStatus(on_ac=None, percent=None)

    on_ac: bool | None = None
    percent: int | None = None

    for d in root.iterdir():
        if not d.is_dir():
            continue

        t = (_read_text(d / "type") or "").lower()
        name = d.name.lower()

        # AC detection
        if t in ("mains", "ac") or name.startswith(("ac", "adp", "mains")):
            v = _read_int(d / "online")
            if v is not None:
                on_ac = (v == 1)

        # Battery detection
        if t == "battery" or name.startswith("bat"):
            v = _read_int(d / "capacity")
            if v is not None:
                percent = v

    return PowerStatus(on_ac=on_ac, percent=percent)