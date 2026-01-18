from __future__ import annotations

import json
import os
import signal
import subprocess
import time
import shutil
from dataclasses import dataclass
from pathlib import Path

from hyprwall.core import paths
from hyprwall.core import hypr

# Type of images supported
from hyprwall.core.detect import IMAGE_EXTS

# Literal type for wallpaper modes
from typing import Literal
Mode = Literal["auto", "fit", "cover", "stretch"]

@dataclass(frozen=True)
class RunState:
    """Legacy single-monitor state (v1)"""
    pid: int
    pgid: int
    monitor: str
    file: str
    needle: str
    mode: str
    started_at: float

@dataclass(frozen=True)
class MonitorRunState:
    """Per-monitor state in multi-monitor setup (v2)"""
    pid: int
    pgid: int
    file: str
    mode: str
    started_at: float
    needle: str

@dataclass(frozen=True)
class MultiRunState:
    """Multi-monitor state container (v2)"""
    monitors: dict[str, MonitorRunState]

def _read_state() -> RunState | MultiRunState | None:
    """
    Read state file and return appropriate state object.

    Supports both:
    - v1 (legacy): single-monitor RunState
    - v2 (multi-monitor): MultiRunState

    Automatically migrates v1 to v2 if v1 is detected.
    """
    try:
        data = json.loads(paths.STATE_FILE.read_text())

        # Detect v2 format
        if "version" in data and data["version"] == 2:
            monitors_data = data.get("monitors", {})
            monitors = {}
            for mon_name, mon_data in monitors_data.items():
                monitors[mon_name] = MonitorRunState(
                    pid=int(mon_data["pid"]),
                    pgid=int(mon_data["pgid"]),
                    file=str(mon_data.get("file", "")),
                    mode=str(mon_data.get("mode", "auto")),
                    started_at=float(mon_data.get("started_at", 0.0)),
                    needle=str(mon_data.get("needle") or mon_data.get("file", "")),
                )
            return MultiRunState(monitors=monitors)

        # Legacy v1 format - migrate to v2 on write
        return RunState(
            pid=int(data["pid"]),
            pgid=int(data["pgid"]),
            monitor=str(data.get("monitor", "")),
            file=str(data.get("file", "")),
            mode=str(data.get("mode", "auto")),
            started_at=float(data.get("started_at", 0.0)),
            needle=str(data.get("needle") or data.get("file", "")),
        )
    except (FileNotFoundError, ValueError, KeyError, json.JSONDecodeError):
        return None

def _write_state(state: RunState | MultiRunState) -> None:
    """
    Write state to file.

    Supports both:
    - RunState: writes v2 format (migrates v1 to v2)
    - MultiRunState: writes v2 format
    """
    paths.STATE_DIR.mkdir(parents=True, exist_ok=True)

    if isinstance(state, MultiRunState):
        # Write v2 format
        monitors_data = {}
        for mon_name, mon_state in state.monitors.items():
            monitors_data[mon_name] = {
                "pid": mon_state.pid,
                "pgid": mon_state.pgid,
                "file": mon_state.file,
                "mode": mon_state.mode,
                "started_at": mon_state.started_at,
                "needle": mon_state.needle,
            }

        paths.STATE_FILE.write_text(
            json.dumps(
                {
                    "version": 2,
                    "monitors": monitors_data,
                },
                indent=2,
            )
            + "\n"
        )
    else:
        # Legacy RunState: migrate to v2 format automatically
        monitors_data = {
            state.monitor: {
                "pid": state.pid,
                "pgid": state.pgid,
                "file": state.file,
                "mode": state.mode,
                "started_at": state.started_at,
                "needle": state.needle,
            }
        }

        paths.STATE_FILE.write_text(
            json.dumps(
                {
                    "version": 2,
                    "monitors": monitors_data,
                },
                indent=2,
            )
            + "\n"
        )

def _remove_statefile() -> None:
    try:
        paths.STATE_FILE.unlink()
    except FileNotFoundError:
        pass

def _process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True

def _cmdline_contains(pid: int, needle: str) -> bool:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
        # /proc/<pid>/cmdline is null-byte separated
        txt = raw.replace(b"\0", b" ").decode(errors="ignore")
        return needle in txt
    except FileNotFoundError:
        return False
    except Exception:
        return False

def _is_mpvpaper(pid: int) -> bool:
    return _process_exists(pid) and _cmdline_contains(pid, "mpvpaper")

def _pgid_has_processes(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True

def _terminate_group(pgid: int, timeout_s: float = 2.0, poll_s: float = 0.05) -> None:
    try:
        os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return

    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if not _pgid_has_processes(pgid):
            return
        time.sleep(poll_s)

    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        return

def stop(timeout_s: float = 2.0) -> bool:
    """
    Stop all wallpapers.

    Args:
        timeout_s: Timeout for graceful termination.

    Returns:
        True if any wallpaper was stopped, False otherwise.
    """
    state = _read_state()

    # No state: nothing we can precisely target
    if state is None:
        return False

    stopped_any = False

    # Handle MultiRunState (v2) - stop all monitors
    if isinstance(state, MultiRunState):
        for mon_name, mon_state in state.monitors.items():
            if _process_exists(mon_state.pid) and _is_mpvpaper(mon_state.pid):
                _terminate_group(mon_state.pgid, timeout_s=timeout_s)
                try:
                    os.kill(mon_state.pid, signal.SIGKILL)
                except Exception:
                    pass
                stopped_any = True

            # Robust verification
            needle = mon_state.needle
            pids = _find_mpvpaper_pids(monitor=mon_name, needle=needle)
            if not pids:
                pids = _find_mpvpaper_pids(monitor=mon_name, needle="")

            if pids:
                for pid in pids:
                    try:
                        os.kill(pid, signal.SIGTERM)
                    except Exception:
                        pass
                time.sleep(0.1)
                for pid in pids:
                    try:
                        os.killpg(os.getpgid(pid), signal.SIGKILL)
                    except Exception:
                        pass
                stopped_any = True

        _remove_statefile()
        return stopped_any

    # Handle legacy RunState (v1)
    else:
        target_monitor = state.monitor

        # Best effort: try killing stored pgid/pid if they exist
        if _process_exists(state.pid) and _is_mpvpaper(state.pid):
            _terminate_group(state.pgid, timeout_s=timeout_s)
            try:
                os.kill(state.pid, signal.SIGKILL)
            except Exception:
                pass

        # Robust verification: look for a remaining mpvpaper matching monitor + needle
        needle = getattr(state, "needle", "") or state.file

        pids = _find_mpvpaper_pids(monitor=target_monitor, needle=needle)
        if not pids:
            # If needle match fails (maybe file changed), fallback to monitor-only
            pids = _find_mpvpaper_pids(monitor=target_monitor, needle="")

        if pids:
            # Kill them (TERM -> KILL)
            for pid in pids:
                try:
                    os.kill(pid, signal.SIGTERM)
                except Exception:
                    pass
            time.sleep(0.1)
            for pid in pids:
                try:
                    os.killpg(os.getpgid(pid), signal.SIGKILL)
                except Exception:
                    pass

            # Recheck
            still = _find_mpvpaper_pids(monitor=target_monitor, needle=needle) or _find_mpvpaper_pids(monitor=target_monitor, needle="")
            if still:
                # Do NOT remove state, because wallpaper is still running
                return False

        _remove_statefile()
        return True

def _is_image(file: Path) -> bool:
    return file.suffix.lower() in IMAGE_EXTS

def _mpv_options_for(
        file: Path,
        mode: Mode = "auto",
        target_w: int | None = None,
        target_h: int | None = None,
) -> str:
    """
    mpv options via mpvpaper -o "<opts>"
    Modes:
    - fit:    keepaspect
    - cover:  scale=increase + crop (fill, no letterbox)
    - stretch: keepaspect=no (distort to fit)
    - auto: image->cover, video->fit
    """
    ext = file.suffix.lower()
    opts = ["--no-audio", "--no-border", "--really-quiet", "--hwdec=auto-safe"]

    # Auto decision
    if mode == "auto":
        mode = "cover" if _is_image(file) else "fit"

    if mode == "fit":
        # Default mpv behavior keeps aspect ratio
        opts.append("--keepaspect=yes")

    elif mode == "stretch":
        opts.append("--keepaspect=no")

    elif mode == "cover":
        if not (target_w and target_h):
            # Fallback to stretch if no target size
            opts.append("--keepaspect=no")
        else:
            vf = (
                f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
                f"crop={target_w}:{target_h}"
            )
            opts.append(f"--vf={vf}")

    else:
        raise ValueError(f"Unknown mode: {mode}")

    if ext in IMAGE_EXTS:
        opts.append("--image-display-duration=inf")
    else:
        opts.append("--loop-file=inf")

    return " ".join(opts)

def _find_mpvpaper_pids(monitor: str = "", needle: str = "") -> list[int]:
    pids: list[int] = []
    for d in Path("/proc").iterdir():
        if not d.name.isdigit():
            continue
        pid = int(d.name)
        try:
            txt = (d / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="ignore")
        except Exception:
            continue
        if "mpvpaper" not in txt:
            continue
        if monitor and f" {monitor} " not in f" {txt} ":
            continue
        if needle and needle not in txt:
            continue
        pids.append(pid)
    return pids

def start(
    monitor: str,
    file: Path,
    extra_args: list[str] | None = None,
    mode: Mode = "auto",
    preserve_other_monitors: bool = False,
) -> RunState:
    """
    Start wallpaper on a single monitor.

    Args:
        monitor: Target monitor name
        file: Wallpaper file path
        extra_args: Extra mpvpaper arguments
        mode: Rendering mode
        preserve_other_monitors: If True, preserve existing monitors in state (for multi-monitor)

    Returns:
        RunState for the started monitor
    """
    if shutil.which("mpvpaper") is None:
        raise RuntimeError("mpvpaper not found in PATH. Install it first.")

    extra_args = extra_args or []
    file = Path(file)

    w, h = hypr.monitor_resolution(monitor)

    effective_mode: Mode = mode
    if mode == "auto":
        effective_mode = "cover" if _is_image(file) else "fit"

    mpv_opts = _mpv_options_for(
        file,
        mode=effective_mode,
        target_w=w,
        target_h=h,
    )

    # Before starting, kill swww if running (only once, not per-monitor)
    if not preserve_other_monitors:
        if shutil.which("swww"):
            subprocess.run(["pkill", "-x", "swww-daemon"], check=False)
            subprocess.run(["pkill", "-x", "swww"], check=False)

    paths.STATE_DIR.mkdir(parents=True, exist_ok=True)
    logf = paths.LOG_FILE.open("a")

    proc = subprocess.Popen(
        ["mpvpaper", "-o", mpv_opts, *extra_args, monitor, str(file)],
        stdout=logf,
        stderr=logf,
        start_new_session=True,
        text=False,
    )

    try:
        pgid = os.getpgid(proc.pid)
    except Exception:
        pgid = proc.pid

    needle = str(file)

    new_mon_state = MonitorRunState(
        pid=proc.pid,
        pgid=pgid,
        file=str(file),
        mode=str(effective_mode),
        started_at=time.time(),
        needle=needle,
    )

    # If preserving other monitors, merge with existing state
    if preserve_other_monitors:
        existing_state = _read_state()
        if isinstance(existing_state, MultiRunState):
            # Add/update this monitor in existing multi-monitor state
            new_monitors = dict(existing_state.monitors)
            new_monitors[monitor] = new_mon_state
            _write_state(MultiRunState(monitors=new_monitors))
        else:
            # Create new multi-monitor state with just this monitor
            _write_state(MultiRunState(monitors={monitor: new_mon_state}))
    else:
        # Legacy behavior: write single-monitor state (auto-migrated to v2)
        state = RunState(
            pid=proc.pid,
            pgid=pgid,
            monitor=monitor,
            file=str(file),
            needle=needle,
            mode=str(effective_mode),
            started_at=time.time(),
        )
        _write_state(state)
        return state

    # Return legacy RunState for compatibility
    return RunState(
        pid=proc.pid,
        pgid=pgid,
        monitor=monitor,
        file=str(file),
        needle=needle,
        mode=str(effective_mode),
        started_at=time.time(),
    )

@dataclass(frozen=True)
class StartManyEntry:
    """Entry for multi-monitor start"""
    monitor: str
    file: Path
    mode: Mode = "auto"

def start_many(
    entries: list[StartManyEntry],
    extra_args: list[str] | None = None,
) -> MultiRunState:
    """
    Start wallpapers on multiple monitors simultaneously.

    All entries should use the same source file (different optimized versions by resolution are OK).

    Args:
        entries: List of monitor entries to start
        extra_args: Extra mpvpaper arguments (applied to all)

    Returns:
        MultiRunState containing all started monitors
    """
    if shutil.which("mpvpaper") is None:
        raise RuntimeError("mpvpaper not found in PATH. Install it first.")

    if not entries:
        raise ValueError("start_many requires at least one entry")

    extra_args = extra_args or []

    # Kill swww once before starting
    if shutil.which("swww"):
        subprocess.run(["pkill", "-x", "swww-daemon"], check=False)
        subprocess.run(["pkill", "-x", "swww"], check=False)

    paths.STATE_DIR.mkdir(parents=True, exist_ok=True)
    logf = paths.LOG_FILE.open("a")

    monitors = {}

    for entry in entries:
        monitor = entry.monitor
        file = Path(entry.file)
        mode = entry.mode

        w, h = hypr.monitor_resolution(monitor)

        effective_mode: Mode = mode
        if mode == "auto":
            effective_mode = "cover" if _is_image(file) else "fit"

        mpv_opts = _mpv_options_for(
            file,
            mode=effective_mode,
            target_w=w,
            target_h=h,
        )

        proc = subprocess.Popen(
            ["mpvpaper", "-o", mpv_opts, *extra_args, monitor, str(file)],
            stdout=logf,
            stderr=logf,
            start_new_session=True,
            text=False,
        )

        try:
            pgid = os.getpgid(proc.pid)
        except Exception:
            pgid = proc.pid

        needle = str(file)

        monitors[monitor] = MonitorRunState(
            pid=proc.pid,
            pgid=pgid,
            file=str(file),
            mode=str(effective_mode),
            started_at=time.time(),
            needle=needle,
        )

    multi_state = MultiRunState(monitors=monitors)
    _write_state(multi_state)

    return multi_state

def status() -> dict:
    """
    Get current wallpaper status.

    Returns:
        Dictionary with status information.
        For multi-monitor setup, returns {"multi": True, "monitors": {...}}
        For single-monitor setup, returns legacy format for compatibility
    """
    state = _read_state()
    if state is None:
        return {"running": False, "reason": "no state file"}

    # Handle MultiRunState (v2)
    if isinstance(state, MultiRunState):
        monitors_status = {}
        any_running = False

        for mon_name, mon_state in state.monitors.items():
            exists = _process_exists(mon_state.pid)
            is_mpv = _is_mpvpaper(mon_state.pid) if exists else False

            running = bool(exists and is_mpv)
            if not running:
                running = bool(
                    _find_mpvpaper_pids(monitor=mon_name, needle=mon_state.needle) or
                    _find_mpvpaper_pids(monitor=mon_name, needle="")
                )

            if running:
                any_running = True

            monitors_status[mon_name] = {
                "running": running,
                "pid": mon_state.pid,
                "pgid": mon_state.pgid,
                "file": mon_state.file,
                "needle": mon_state.needle,
                "mode": mon_state.mode,
                "started_at": mon_state.started_at,
                "exists": exists,
                "is_mpvpaper": is_mpv,
            }

        return {
            "multi": True,
            "running": any_running,
            "monitors": monitors_status,
            "state_file": str(paths.STATE_FILE),
            "log_file": str(paths.LOG_FILE),
        }

    # Legacy RunState (v1)
    exists = _process_exists(state.pid)
    is_mpv = _is_mpvpaper(state.pid) if exists else False

    running = bool(exists and is_mpv)
    if not running:
        running = bool(
            _find_mpvpaper_pids(monitor=state.monitor, needle=state.needle) or
            _find_mpvpaper_pids(monitor=state.monitor, needle="")
        )

    return {
        "running": running,
        "pid": state.pid,
        "pgid": state.pgid,
        "monitor": state.monitor,
        "file": state.file,
        "needle": state.needle,
        "exists": exists,
        "is_mpvpaper": is_mpv,
        "started_at": state.started_at,
        "state_file": str(paths.STATE_FILE),
        "mode": state.mode,
        "log_file": str(paths.LOG_FILE),
    }