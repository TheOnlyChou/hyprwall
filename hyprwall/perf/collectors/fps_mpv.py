"""
FPS collector from mpv IPC socket.

Queries mpv's estimated-vf-fps property via JSON IPC to monitor video frame rate.
"""

from __future__ import annotations
from pathlib import Path
from typing import Optional
import json
import socket
import time


class MPVFPSCollector:
    """
    Collects FPS from mpv via IPC socket.

    Design:
    - Non-blocking socket operations
    - Returns None if IPC not available
    - Caches socket path for process
    """

    def __init__(self):
        """Initialize the FPS collector"""
        self._socket_cache: dict[int, Optional[Path]] = {}
        self._last_fps: dict[int, float] = {}
        self._timeout = 0.1  # 100ms socket timeout (non-blocking)

    def get_fps(self, pid: int) -> Optional[float]:
        """
        Get current FPS from mpv process.

        Args:
            pid: Process ID (mpv, not mpvpaper)

        Returns:
            FPS value or None if unavailable
        """
        # Find mpv IPC socket
        socket_path = self._find_ipc_socket(pid)
        if not socket_path:
            return None

        try:
            # Connect to socket (with timeout)
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(self._timeout)
            sock.connect(str(socket_path))

            # Send get_property command
            request = {"command": ["get_property", "estimated-vf-fps"]}
            sock.send((json.dumps(request) + "\n").encode("utf-8"))

            # Read response (non-blocking)
            response = sock.recv(4096).decode("utf-8")
            sock.close()

            # Parse JSON response
            data = json.loads(response)
            if data.get("error") == "success" and "data" in data:
                fps = float(data["data"])
                self._last_fps[pid] = fps
                return round(fps, 1)

            return self._last_fps.get(pid)

        except (socket.timeout, socket.error, json.JSONDecodeError, KeyError):
            # Fallback to last known FPS
            return self._last_fps.get(pid)

    def _find_ipc_socket(self, pid: int) -> Optional[Path]:
        """
        Find mpv IPC socket for a process.

        Strategy:
        1. Check /tmp/mpv-ipc-{pid}
        2. Check /run/user/{uid}/mpv-socket-{pid}
        3. Search /proc/{pid}/fd for socket connections

        Returns:
            Path to socket or None
        """
        # Check cache first
        if pid in self._socket_cache:
            cached = self._socket_cache[pid]
            if cached and cached.exists():
                return cached

        # Common socket locations
        candidates = [
            Path(f"/tmp/mpv-ipc-{pid}"),
            Path(f"/tmp/mpvsocket{pid}"),
        ]

        # Try user runtime dir
        try:
            import os
            uid = os.getuid()
            candidates.append(Path(f"/run/user/{uid}/mpv-socket-{pid}"))
        except Exception:
            pass

        # Check candidates
        for candidate in candidates:
            if candidate.exists() and candidate.is_socket():
                self._socket_cache[pid] = candidate
                return candidate

        # Try to find socket from /proc/fd (requires psutil)
        try:
            import psutil
            process = psutil.Process(pid)
            for conn in process.net_connections(kind="unix"):
                if conn.laddr and "mpv" in str(conn.laddr):
                    sock_path = Path(str(conn.laddr))
                    if sock_path.exists():
                        self._socket_cache[pid] = sock_path
                        return sock_path
        except Exception:
            pass

        # Not found
        self._socket_cache[pid] = None
        return None

    def clear_cache(self):
        """Clear socket path cache"""
        self._socket_cache.clear()
        self._last_fps.clear()
