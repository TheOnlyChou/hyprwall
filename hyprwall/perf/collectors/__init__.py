"""
Performance data collectors for HyprWall.

This package contains specialized collectors for various metrics:
- psutil_proc: CPU/RAM via psutil (already in monitor.py)
- gpu: GPU usage (already in monitor.py)
- temps: Temperature sensors (already in monitor.py)
- fps_mpv: FPS from mpv IPC socket
- power: Power consumption via RAPL/powercap
"""

__all__ = ["fps_mpv", "power"]