from __future__ import annotations

import json
from dataclasses import dataclass
from hyprwall.core import paths

@dataclass(frozen=True)
class Session:
    source: str
    ref_monitor: str  # Reference monitor for resolution hint (global-only API)
    mode: str
    codec: str
    encoder: str
    auto_power: bool
    last_profile: str
    last_switch_at: float = 0.0  # unix timestamp
    cooldown_s: int = 60  # cooldown in seconds
    override_profile: str | None = None  # manual override

def load_session() -> Session | None:
    try:
        data = json.loads(paths.SESSION_FILE.read_text())
        # Backward compatibility: accept old "monitor" key
        ref_monitor = data.get("ref_monitor") or data.get("monitor") or ""
        return Session(
            source=str(data["source"]),
            ref_monitor=str(ref_monitor),
            mode=str(data.get("mode", "auto")),
            codec=str(data.get("codec", "h264")),
            encoder=str(data.get("encoder", "auto")),
            auto_power=bool(data.get("auto_power", False)),
            last_profile=str(data.get("last_profile", "balanced")),
            last_switch_at=float(data.get("last_switch_at", 0.0)),
            cooldown_s=int(data.get("cooldown_s", 60)),
            override_profile=data.get("override_profile"),  # None if missing
        )
    except Exception:
        return None

def save_session(s: Session) -> None:
    paths.STATE_DIR.mkdir(parents=True, exist_ok=True)
    paths.SESSION_FILE.write_text(
        json.dumps(
            {
                "source": s.source,
                "ref_monitor": s.ref_monitor,
                "monitor": s.ref_monitor,  # Backward compatibility
                "mode": s.mode,
                "codec": s.codec,
                "encoder": s.encoder,
                "auto_power": s.auto_power,
                "last_profile": s.last_profile,
                "last_switch_at": s.last_switch_at,
                "cooldown_s": s.cooldown_s,
                "override_profile": s.override_profile,
            },
            indent=2,
        )
        + "\n"
    )