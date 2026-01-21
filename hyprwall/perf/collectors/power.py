"""
Power consumption collector via RAPL (Running Average Power Limit).

Reads energy counters from /sys/class/powercap/intel-rapl and computes Watts
from energy_uj deltas over time.
"""

from __future__ import annotations
from pathlib import Path
from typing import Optional
import time


class PowerCollector:
    """
    Collects power consumption via RAPL.

    Design:
    - Reads package energy from intel-rapl
    - Computes Watts from energy_uj deltas
    - Non-blocking, fail-safe
    - Works on Intel/AMD CPUs with RAPL support
    """

    def __init__(self):
        """Initialize the power collector"""
        self._rapl_path = self._detect_rapl_path()
        self._last_energy_uj: Optional[int] = None
        self._last_timestamp: Optional[float] = None
        self._last_watts: Optional[float] = None

    def get_power_watts(self) -> Optional[float]:
        """
        Get current power consumption in Watts.

        Returns:
            Power in Watts or None if unavailable

        Note:
            This measures total package power, not just the wallpaper process.
            It's useful for monitoring overall system impact.
        """
        if not self._rapl_path:
            return None

        try:
            # Read current energy counter (microjoules)
            energy_uj = int(self._rapl_path.read_text().strip())
            now = time.time()

            # First reading: just store baseline
            if self._last_energy_uj is None or self._last_timestamp is None:
                self._last_energy_uj = energy_uj
                self._last_timestamp = now
                return self._last_watts  # Return cached value or None

            # Compute power from energy delta
            energy_delta_j = (energy_uj - self._last_energy_uj) / 1_000_000
            time_delta_s = now - self._last_timestamp

            # Avoid division by zero
            if time_delta_s < 0.001:
                return self._last_watts

            # Power = Energy / Time (Watts = Joules / seconds)
            watts = energy_delta_j / time_delta_s

            # Handle counter rollover (unlikely but possible)
            if watts < 0 or watts > 300:  # Sanity check: 0-300W range
                self._last_energy_uj = energy_uj
                self._last_timestamp = now
                return self._last_watts

            # Update state
            self._last_energy_uj = energy_uj
            self._last_timestamp = now
            self._last_watts = round(watts, 1)

            return self._last_watts

        except (OSError, ValueError):
            return None

    def _detect_rapl_path(self) -> Optional[Path]:
        """
        Detect RAPL energy counter path.

        Looks for:
        - /sys/class/powercap/intel-rapl:0/energy_uj (package)
        - /sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj

        Returns:
            Path to energy_uj file or None
        """
        candidates = [
            Path("/sys/class/powercap/intel-rapl/intel-rapl:0/energy_uj"),
            Path("/sys/class/powercap/intel-rapl:0/energy_uj"),
        ]

        # Check for AMD RAPL (newer kernels)
        candidates.append(Path("/sys/class/powercap/amd-rapl/amd-rapl:0/energy_uj"))

        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                try:
                    # Verify readable and contains integer
                    int(candidate.read_text().strip())
                    return candidate
                except (OSError, ValueError):
                    continue

        return None

    def reset(self):
        """Reset baseline (call when switching wallpapers)"""
        self._last_energy_uj = None
        self._last_timestamp = None

    @property
    def available(self) -> bool:
        """Check if power monitoring is available"""
        return self._rapl_path is not None