"""
Wallpaper performance monitoring.

Measures CPU, RAM, GPU usage and temperatures for running wallpaper processes.
Designed to be lightweight, non-intrusive, and fail-safe.
"""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import time


@dataclass
class PerfMetrics:
    """Performance metrics snapshot"""
    cpu_percent: Optional[float] = None      # CPU usage (%)
    ram_mib: Optional[float] = None          # RAM usage (MiB)
    gpu_percent: Optional[float] = None      # GPU usage (%)
    cpu_temp: Optional[float] = None         # CPU temperature (°C)
    gpu_temp: Optional[float] = None         # GPU temperature (°C)
    timestamp: float = 0.0                   # Timestamp of measurement


class WallpaperPerfMonitor:
    """
    Monitors performance of running wallpaper processes.

    Design principles:
    - Lightweight: minimal overhead, samples at most once per second
    - Fail-safe: never crashes, returns None for unavailable metrics
    - Accurate: aggregates parent + child processes (mpvpaper → mpv)
    - Non-intrusive: no heavy dependencies, graceful degradation
    """

    def __init__(self):
        """Initialize the performance monitor"""
        self._last_sample_time = 0.0
        self._sample_interval = 1.0  # Minimum interval between samples (seconds)

        # Smoothing (rolling average to avoid spikes)
        self._history_size = 3
        self._cpu_history: list[float] = []
        self._ram_history: list[float] = []
        self._gpu_history: list[float] = []

        # Track if we've warmed up CPU measurement for a PID
        self._cpu_warmed_up: set[int] = set()

        # Detect available capabilities once
        self._psutil_available = self._check_psutil()
        if not self._psutil_available:
            self._log_psutil_unavailable()

        self._gpu_backend = self._detect_gpu_backend()
        self._hwmon_paths = self._detect_hwmon_paths()

    def _log_psutil_unavailable(self):
        """Log a warning when psutil is not available"""
        try:
            import sys
            print(
                "Warning: psutil not found. Performance monitoring (CPU/RAM) will be unavailable.",
                file=sys.stderr
            )
            print(
                "Install with: sudo dnf install python3-psutil (Fedora) or pip install psutil",
                file=sys.stderr
            )
        except Exception:
            pass

    def _check_psutil(self) -> bool:
        """Check if psutil is available"""
        try:
            import psutil
            return True
        except ImportError:
            return False

    def _detect_gpu_backend(self) -> Optional[str]:
        """
        Detect available GPU backend.

        Returns:
            "nvidia" | "amd" | "intel" | None
        """
        # NVIDIA
        if Path("/usr/bin/nvidia-smi").exists():
            return "nvidia"

        # AMD (via radeontop or /sys/class/drm)
        if any(Path("/sys/class/drm").glob("card*/device/gpu_busy_percent")):
            return "amd"

        # Intel (via intel_gpu_top or similar)
        if Path("/usr/bin/intel_gpu_top").exists():
            return "intel"

        return None

    def _detect_hwmon_paths(self) -> dict[str, Path]:
        """
        Detect hwmon paths for CPU and GPU temperatures.

        Returns:
            Dictionary with "cpu" and "gpu" keys mapping to hwmon paths
        """
        paths = {}
        hwmon_base = Path("/sys/class/hwmon")

        if not hwmon_base.exists():
            return paths

        try:
            for hwmon in hwmon_base.iterdir():
                name_file = hwmon / "name"
                if not name_file.exists():
                    continue

                try:
                    name = name_file.read_text().strip().lower()

                    # CPU temperature (priority: k10temp > coretemp > zenpower > generic cpu)
                    # Only set if not already found or if this is a higher priority match
                    if any(x in name for x in ["coretemp", "k10temp", "zenpower", "cpu"]):
                        temp_input = hwmon / "temp1_input"
                        if temp_input.exists():
                            # Prefer specific CPU sensors over generic "thinkpad" or "cpu"
                            if "cpu" not in paths or any(x in name for x in ["k10temp", "coretemp", "zenpower"]):
                                paths["cpu"] = temp_input

                    # GPU temperature (common names: amdgpu, nouveau, i915)
                    # Don't confuse thinkpad's "cpu"/"gpu" labels with real sensors
                    if any(x in name for x in ["amdgpu", "nouveau", "i915", "radeon"]):
                        temp_input = hwmon / "temp1_input"
                        if temp_input.exists():
                            paths["gpu"] = temp_input

                except Exception:
                    continue

        except Exception:
            pass

        return paths

    def get_metrics(self, pid: int) -> PerfMetrics:
        """
        Get current performance metrics for a wallpaper process.

        Args:
            pid: Process ID of the wallpaper (mpvpaper)

        Returns:
            PerfMetrics with available data (None for unavailable metrics)
        """
        now = time.time()

        # Rate limiting: don't sample more than once per interval
        if now - self._last_sample_time < self._sample_interval:
            # Return smoothed values from history
            return self._get_smoothed_metrics(now)

        self._last_sample_time = now

        # Collect raw metrics
        cpu = self._get_cpu_usage(pid)
        ram = self._get_ram_usage(pid)
        gpu = self._get_gpu_usage()
        cpu_temp = self._get_temperature("cpu")
        gpu_temp = self._get_temperature("gpu")

        # Update histories (for smoothing)
        if cpu is not None:
            self._cpu_history.append(cpu)
            if len(self._cpu_history) > self._history_size:
                self._cpu_history.pop(0)

        if ram is not None:
            self._ram_history.append(ram)
            if len(self._ram_history) > self._history_size:
                self._ram_history.pop(0)

        if gpu is not None:
            self._gpu_history.append(gpu)
            if len(self._gpu_history) > self._history_size:
                self._gpu_history.pop(0)

        return self._get_smoothed_metrics(now)

    def _get_smoothed_metrics(self, timestamp: float) -> PerfMetrics:
        """Return smoothed metrics from history"""
        cpu_avg = sum(self._cpu_history) / len(self._cpu_history) if self._cpu_history else None
        ram_avg = sum(self._ram_history) / len(self._ram_history) if self._ram_history else None
        gpu_avg = sum(self._gpu_history) / len(self._gpu_history) if self._gpu_history else None

        return PerfMetrics(
            cpu_percent=cpu_avg,
            ram_mib=ram_avg,
            gpu_percent=gpu_avg,
            cpu_temp=self._get_temperature("cpu"),  # Temps read directly (no smoothing)
            gpu_temp=self._get_temperature("gpu"),
            timestamp=timestamp,
        )

    def _get_cpu_usage(self, pid: int) -> Optional[float]:
        """
        Get CPU usage for process + children.

        Returns:
            CPU percentage (0-100+) or None if unavailable
        """
        if not self._psutil_available:
            return None

        try:
            import psutil

            # Get main process
            try:
                process = psutil.Process(pid)
            except psutil.NoSuchProcess:
                return None

            # Warm up: first call primes the baseline (non-blocking)
            if pid not in self._cpu_warmed_up:
                try:
                    # Prime baseline with non-blocking call (returns 0.0 on first call)
                    process.cpu_percent(interval=None)
                    # Also prime children
                    for child in process.children(recursive=True):
                        try:
                            child.cpu_percent(interval=None)
                        except:
                            pass
                    self._cpu_warmed_up.add(pid)
                except:
                    pass
                # First call establishes baseline
                # Return 0.0 to avoid UI flickering between "N/A" and values
                # Next call (after ~1s) will have accurate data
                return 0.0

            # Aggregate CPU for process + children (non-blocking)
            total_cpu = 0.0

            try:
                # Non-blocking measurement (uses cached data from baseline)
                total_cpu += process.cpu_percent(interval=None)

                # Children CPU
                for child in process.children(recursive=True):
                    try:
                        total_cpu += child.cpu_percent(interval=None)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return None

            # Return the measurement (can be 0.0 if process is idle)
            return round(total_cpu, 1)

        except Exception:
            return None

    def _get_ram_usage(self, pid: int) -> Optional[float]:
        """
        Get RAM usage (RSS) for process + children.

        Returns:
            RAM usage in MiB or None if unavailable
        """
        if not self._psutil_available:
            return None

        try:
            import psutil

            try:
                process = psutil.Process(pid)
            except psutil.NoSuchProcess:
                return None

            # Aggregate RSS for process + children
            total_rss = 0

            try:
                # Main process RSS
                total_rss += process.memory_info().rss

                # Children RSS
                for child in process.children(recursive=True):
                    try:
                        total_rss += child.memory_info().rss
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                return None

            # Convert bytes to MiB
            return round(total_rss / (1024 * 1024), 1)

        except Exception:
            return None

    def _get_gpu_usage(self) -> Optional[float]:
        """
        Get GPU usage percentage.

        Returns:
            GPU usage (0-100) or None if unavailable
        """
        if self._gpu_backend is None:
            return None

        try:
            if self._gpu_backend == "nvidia":
                return self._get_nvidia_usage()
            elif self._gpu_backend == "amd":
                return self._get_amd_usage()
            elif self._gpu_backend == "intel":
                return self._get_intel_usage()
        except Exception:
            pass

        return None

    def _get_nvidia_usage(self) -> Optional[float]:
        """Get NVIDIA GPU usage via nvidia-smi"""
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=1,
                check=False,
            )
            if result.returncode == 0:
                usage = float(result.stdout.strip())
                return round(usage, 1)
        except Exception:
            pass
        return None

    def _get_amd_usage(self) -> Optional[float]:
        """Get AMD GPU usage via sysfs"""
        try:
            # Try gpu_busy_percent (newer kernels)
            for card_path in Path("/sys/class/drm").glob("card*/device/gpu_busy_percent"):
                try:
                    usage = int(card_path.read_text().strip())
                    return float(usage)
                except Exception:
                    continue
        except Exception:
            pass
        return None

    def _get_intel_usage(self) -> Optional[float]:
        """Get Intel GPU usage (placeholder - requires intel_gpu_top parsing)"""
        # intel_gpu_top output parsing is complex and not stable
        # Would require running it in background and parsing JSON output
        # For now, return None (not worth the complexity)
        return None

    def _get_temperature(self, sensor: str) -> Optional[float]:
        """
        Get temperature from hwmon.

        Args:
            sensor: "cpu" or "gpu"

        Returns:
            Temperature in °C or None if unavailable
        """
        path = self._hwmon_paths.get(sensor)
        if path is None or not path.exists():
            return None

        try:
            # hwmon returns millidegrees Celsius
            temp_millidegrees = int(path.read_text().strip())
            temp_celsius = temp_millidegrees / 1000.0
            return round(temp_celsius, 1)
        except Exception:
            return None

    def clear_history(self):
        """Clear smoothing history (useful when switching wallpapers)"""
        self._cpu_history.clear()
        self._ram_history.clear()
        self._gpu_history.clear()
        self._cpu_warmed_up.clear()
        self._last_sample_time = 0.0