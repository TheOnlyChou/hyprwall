"""
Core API - User-facing facade for interacting with the core business logic.

This API is used by both CLI and GUI to interact with the hyprwall engine.
It encapsulates all business logic and avoids direct coupling.
"""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from hyprwall.core import (
    detect,
    hypr,
    optimize,
    paths,
    policy,
    power,
    runner,
    session,
)

# Re-export types commonly used
from hyprwall.core.hypr import Monitor
from hyprwall.core.power import PowerStatus
from hyprwall.core.session import Session
from hyprwall.core.optimize import OptimizeProfile, Codec, Encoder
from hyprwall.core.policy import Hysteresis

Mode = Literal["auto", "fit", "cover", "stretch"]

@dataclass
class WallpaperStatus:
    """Current wallpaper status"""
    running: bool
    monitors: dict[str, MonitorStatus]


@dataclass
class MonitorStatus:
    """Status of a wallpaper on a specific monitor"""
    name: str
    file: str | None
    mode: str
    pid: int | None


@dataclass(frozen=True)
class MediaItem:
    """A media file in the library"""
    path: Path
    kind: str  # "image" | "video"


class HyprwallCore:
    """
    Core API for interacting with hyprwall's business logic.
    This class provides methods to manage wallpapers, optimization, power profiles, and sessions.
    """

    def __init__(self):
        """Intialize the core API and ensure necessary directories exist"""
        paths.ensure_directories()

    def list_monitors(self) -> list[Monitor]:
        """List all connected monitors"""
        return hypr.list_monitors()

    def list_library(self, directory: Path, recursive: bool = True) -> list[MediaItem]:
        """
        List all supported media files in a directory.

        Args:
            directory: Directory to scan for media files
            recursive: If True, scan recursively (default)

        Returns:
            List of MediaItem sorted by filename
        """
        try:
            if not directory.exists() or not directory.is_dir():
                return []

            files = detect.find_supported_files(directory, recursive=recursive)

            items = []
            for file_path in files:
                kind = "video" if detect.is_video(file_path) else "image"
                items.append(MediaItem(path=file_path, kind=kind))

            # Sort by filename
            return sorted(items, key=lambda x: x.path.name.lower())
        except Exception:
            return []

    def set_wallpaper(
        self,
        source: Path | str,
        mode: Mode = "auto",
        profile: str = "balanced",
        codec: Codec = "h264",
        encoder: Encoder = "auto",
        auto_power: bool = False,
    ) -> bool:
        """
        Set wallpaper on all monitors (global-only) with full business logic.

        Args:
            source: Path to wallpaper file or directory
            mode: Display mode (auto/fit/cover/stretch)
            profile: Optimization profile ("off"/"eco"/"balanced"/"quality")
            codec: Codec to use for optimization (h264/vp9/av1)
            encoder: Encoder to use (auto/libx264/...)
            auto_power: If True, choose profile based on power status

        Returns:
            True if successful, False otherwise
        """
        # Validate source
        try:
            source_path = detect.validate_wallpaper(str(source))
        except Exception:
            return False
        if not source_path:
            return False

        # List monitors
        all_monitors = self.list_monitors()
        if not all_monitors:
            return False

        # Choose reference monitor (focused > largest > fallback)
        ref_monitor = hypr.pick_reference_monitor(all_monitors)
        if ref_monitor:
            ref_width = ref_monitor.width
            ref_height = ref_monitor.height
            ref_monitor_name = ref_monitor.name
        else:
            ref_width, ref_height = 1920, 1080
            ref_monitor_name = ""

        # Load previous session for last_profile continuity
        sess_prev = self.load_session()
        prev_last_profile = sess_prev.last_profile if sess_prev else "balanced"

        # Determine effective profile
        if auto_power:
            power_status = power.get_power_status()
            profile_effective = policy.choose_profile(
                power_status=power_status,
                last_profile=prev_last_profile,
                hysteresis=Hysteresis(),
            )
        else:
            profile_effective = profile

        # Validate profile_effective
        if profile_effective not in {"off", "eco", "balanced", "quality"}:
            profile_effective = "balanced"

        # Resolve target file and determine last_profile to save
        if detect.is_video(source_path):
            if profile_effective == "off":
                # No optimization - keep previous last_profile
                target = source_path
                last_profile_to_save = prev_last_profile
            else:
                # Optimize
                profile_obj = self._profile_by_name(profile_effective)
                result = optimize.ensure_optimized(
                    source=source_path,
                    width=ref_width,
                    height=ref_height,
                    profile=profile_obj,
                    mode=mode,
                    codec=codec,
                    encoder=encoder,
                )
                target = result.path
                last_profile_to_save = profile_effective
        else:
            # Image - no optimization, never change last_profile
            target = source_path
            last_profile_to_save = prev_last_profile

        # Stop any existing wallpapers before starting new ones (replace behavior)
        try:
            runner.stop()
        except Exception:
            # Ignore if nothing is running or stop fails
            pass

        # Start on all monitors
        entries = [
            runner.StartManyEntry(monitor=m.name, file=target, mode=mode)
            for m in all_monitors
        ]
        runner.start_many(entries)

        # Save session
        sess = session.Session(
            source=str(source_path),
            ref_monitor=ref_monitor_name,
            mode=mode,
            codec=codec,
            encoder=encoder,
            auto_power=auto_power,
            last_profile=last_profile_to_save,
            last_switch_at=0.0,
            cooldown_s=60,
            override_profile=None,
        )
        session.save_session(sess)

        return True

    def start_wallpaper(
        self,
        source: Path | str,
        monitor: str | None = None,
        mode: Mode = "auto",
        codec: Codec = "h264",
        encoder: Encoder = "auto",
    ) -> bool:
        """
        Start a wallpaper on all monitors (global-only).

        This is a compatibility wrapper around set_wallpaper().

        Args:
            source: Path to the wallpaper file (image or video)
            monitor: Ignored (kept for API compatibility, always starts on all monitors)
            mode: Display mode (auto/fit/cover/stretch)
            codec: Codec to use for optimization (h264/vp9/av1)
            encoder: Encoder to use (auto/libx264/...)

        Returns:
            True if successful, False otherwise
        """
        # Wrapper to set_wallpaper with default profile and no auto_power
        return self.set_wallpaper(
            source=source,
            mode=mode,
            profile="balanced",
            codec=codec,
            encoder=encoder,
            auto_power=False,
        )

    def stop_wallpaper(self, monitor: str | None = None) -> bool:
        """
        Stop all wallpapers (global stop only).

        Args:
            monitor: Ignored (kept for API compatibility, always stops all monitors)

        Returns:
            True if successful, False otherwise
        """
        # monitor parameter is ignored: stop is always global
        return runner.stop()

    def get_status(self) -> WallpaperStatus:
        """Return the current wallpaper status"""
        status_data = runner.status()

        if not status_data.get("running", False):
            return WallpaperStatus(running=False, monitors={})

        monitors = {}

        # Multi-monitor format (v2)
        if status_data.get("multi", False):
            monitors_data = status_data.get("monitors", {})
            for mon_name, mon_data in monitors_data.items():
                monitors[mon_name] = MonitorStatus(
                    name=mon_name,
                    file=mon_data.get("file"),
                    mode=mon_data.get("mode", "auto"),
                    pid=mon_data.get("pid"),
                )
        else:
            # Legacy single-monitor format (v1)
            mon_name = status_data.get("monitor", "")
            monitors[mon_name] = MonitorStatus(
                name=mon_name,
                file=status_data.get("file"),
                mode=status_data.get("mode", "auto"),
                pid=status_data.get("pid"),
            )

        return WallpaperStatus(running=True, monitors=monitors)

    def optimize_file(
        self,
        source: Path,
        profile: str = "balanced",
        codec: Codec = "h264",
        encoder: Encoder = "auto",
        width: int = 1920,
        height: int = 1080,
    ) -> Path:
        """
        Optimize a media file according to the specified profile and dimensions.
        Args:
            source: Path to the source media file
            profile: Optimization profile name (eco/eco_strict/balanced/quality)
            codec: Codec to use for optimization (h264/vp9/av1)
            encoder: Encoder to use (auto/libx264/...)
            width: Target width for optimization
            height: Target height for optimization
        Returns:
            Path to the optimized file
        """
        prof = self._profile_by_name(profile)
        result = optimize.ensure_optimized(
            source=source,
            width=width,
            height=height,
            profile=prof,
            mode="auto",
            codec=codec,
            encoder=encoder,
        )
        return result.path

    def _profile_by_name(self, name: str) -> OptimizeProfile:
        """Return the OptimizeProfile instance by its name"""
        profiles = {
            "eco": optimize.ECO,
            "eco_strict": optimize.ECO_STRICT,
            "balanced": optimize.BALANCED,
            "quality": optimize.QUALITY,
        }
        return profiles.get(name, optimize.BALANCED)

    def get_power_status(self) -> PowerStatus:
        """Return the current power status of the system"""
        return power.get_power_status()

    def choose_profile(
        self,
        power_status: PowerStatus | None = None,
        last_profile: str | None = None,
        hysteresis: Hysteresis | None = None,
    ) -> str:
        """
        Choose the appropriate optimization profile based on power status and last profile.
        Args:
            power_status: Current power status, if None it will be fetched
            last_profile: Last used profile name
            hysteresis: Hysteresis settings, if None default will be used
        Returns:
            Chosen profile name
        """
        if power_status is None:
            power_status = self.get_power_status()
        if hysteresis is None:
            hysteresis = Hysteresis()

        return policy.choose_profile(power_status, last_profile, hysteresis)

    def _get_current_profile(self) -> OptimizeProfile:
        """Determine the current optimization profile to use"""
        sess = self.load_session()
        if sess:
            profile_name = sess.last_profile
        else:
            profile_name = self.choose_profile()

        return self._profile_by_name(profile_name)

    def load_session(self) -> Session | None:
        """Load the saved session, if any"""
        return session.load_session()

    def save_session(self, sess: Session) -> None:
        """Save the current session"""
        session.save_session(sess)


    def find_media_files(self, directory: Path) -> list[Path]:
        """Find all supported media files (images and videos) in a directory recursively, sorted by name."""
        return detect.find_supported_files(directory, recursive=True)

    def clear_cache(self) -> tuple[int, int]:
        """
        Clear the optimization cache.
        Returns:
            A tuple (number_of_files_deleted, number_of_bytes_freed)
        """
        import shutil
        count = paths.count_tree(paths.OPT_DIR)
        if paths.OPT_DIR.exists():
            shutil.rmtree(paths.OPT_DIR)
            paths.OPT_DIR.mkdir(parents=True, exist_ok=True)
        return count


# Singleton instance
_core_instance: HyprwallCore | None = None


def get_core() -> HyprwallCore:
    """Return the singleton HyprwallCore instance"""
    global _core_instance
    if _core_instance is None:
        _core_instance = HyprwallCore()
    return _core_instance