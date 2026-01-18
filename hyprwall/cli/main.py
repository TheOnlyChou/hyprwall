import argparse

import shutil
import subprocess
import sys
import time
from pathlib import Path

from hyprwall.core import paths
from hyprwall.core import detect
from hyprwall.core.paths import count_tree
from hyprwall.core.session import save_session, load_session, Session
from hyprwall.core.power import get_power_status
from hyprwall.core.policy import choose_profile, Hysteresis, should_switch

from hyprwall.core import runner
from hyprwall.core import hypr
from hyprwall.core import optimize

# ANSI color codes for terminal output
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    # Basic colors
    BLACK = "\033[30m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    # Bright colors
    BRIGHT_BLACK = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"

def print_separator(char="─", width=60):
    """Print a horizontal separator line"""
    print(f"{Colors.DIM}{char * width}{Colors.RESET}")

def print_info(label: str, value: str, indent: int = 0):
    """Print formatted info line"""
    spaces = "  " * indent
    print(f"{spaces}{Colors.CYAN}{label}:{Colors.RESET} {Colors.BRIGHT_WHITE}{value}{Colors.RESET}")

def print_success(message: str):
    """Print success message with checkmark"""
    print(f"{Colors.BRIGHT_GREEN}✓{Colors.RESET} {message}")

def print_warning(message: str):
    """Print warning message"""
    print(f"{Colors.BRIGHT_YELLOW}!{Colors.RESET} {message}")

def print_error(message: str):
    """Print error message"""
    print(f"{Colors.BRIGHT_RED}✗{Colors.RESET} {message}")

def print_header(text: str):
    """Print a header"""
    print(f"\n{Colors.BOLD}{Colors.BRIGHT_CYAN}{text}{Colors.RESET}")
    print_separator()

def animate_progress(text: str, duration: float = 0.5):
    """Simple progress animation"""
    frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    end_time = time.time() + duration
    i = 0
    while time.time() < end_time:
        frame = frames[i % len(frames)]
        sys.stdout.write(f"\r{Colors.CYAN}{frame}{Colors.RESET} {text}")
        sys.stdout.flush()
        time.sleep(0.08)
        i += 1
    sys.stdout.write(f"\r{' ' * (len(text) + 3)}\r")
    sys.stdout.flush()

def print_banner():
    if shutil.which("figlet"):
        subprocess.run(["figlet", "-f", "standard", "HyprWall"], check=False)
        print(f"{Colors.DIM}Wallpaper Manager for Hyprland{Colors.RESET}")
    else:
        print(f"{Colors.BOLD}{Colors.BRIGHT_CYAN}╔═══════════════════════════════════╗")
        print(f"║          H Y P R W A L L          ║")
        print(f"╚═══════════════════════════════════╝{Colors.RESET}")
        print(f"{Colors.DIM}Wallpaper Manager for Hyprland{Colors.RESET}")
        print(f"{Colors.DIM}(Tip: install 'figlet' for ASCII art banner){Colors.RESET}")

def get_reference_resolution(ref_monitor_name: str) -> tuple[int, int]:
    """
    Get resolution from ref_monitor, with fallback to focused>largest if invalid.

    Args:
        ref_monitor_name: Name of the reference monitor (may be empty or invalid)

    Returns:
        Tuple of (width, height)

    Raises:
        SystemExit: If no monitors are detected
    """
    if ref_monitor_name:
        try:
            return hypr.monitor_resolution(ref_monitor_name)
        except RuntimeError:
            pass  # Monitor not found, fallback below

    # Fallback: pick reference monitor
    all_mons = hypr.list_monitors()
    if not all_mons:
        raise RuntimeError("No monitors detected")

    ref_mon = hypr.pick_reference_monitor(all_mons)
    if not ref_mon:
        raise RuntimeError("No valid reference monitor found")

    return ref_mon.width, ref_mon.height

def parse_arguments():
    parser = argparse.ArgumentParser(
        prog="hyprwall",
        description="HyprWall - Lightweight Wallpaper Manager for Hyprland",
        epilog=f"{Colors.DIM}Project: https://github.com/TheOnlyChou/hyprwall{Colors.RESET}",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument("-v", "--verbose", action="store_true", help="Print extra debug info")
    parser.add_argument("--no-banner", action="store_true", help="Disable banner output")

    sub = parser.add_subparsers(dest="command", required=True)

    # TLDR command parser
    sub.add_parser(
        "tldr",
        help="Quick project overview (Too Long; Didn't Read)",
        description="Display a quick overview of what HyprWall is and what it does."
    )

    # Set commands parser
    set_cmd = sub.add_parser(
        "set",
        help="Set a wallpaper (file or directory)",
        description="""Set a wallpaper on all monitors.
        
Supports images (jpg, png, gif, webp) and videos (mp4, mkv, webm).
When pointing to a directory, the most recent file will be used.
Wallpaper is applied to ALL active monitors.""",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    set_cmd.add_argument("path", type=str, help="Path to the image/video file OR directory")
    set_cmd.add_argument(
        "--mode",
        choices=["auto", "fit", "cover", "stretch"],
        default="auto",
        metavar="MODE",
        help="""Rendering mode (default: auto)
  • auto    - Images use 'cover', videos use 'fit'
  • fit     - Letterbox: keep aspect ratio, add black bars
  • cover   - Fill screen, crop edges if needed
  • stretch - Fill screen completely, may distort image""",
    )
    set_cmd.add_argument(
        "--profile",
        choices=["eco", "balanced", "quality", "off"],
        default="balanced",
        metavar="PROFILE",
        help="""Optimization profile for videos (default: balanced)
  • eco      - 24fps, Quality 28, veryfast preset (lowest CPU/battery usage)
  • balanced - 30fps, Quality 24, veryfast preset (recommended)
  • quality  - 30fps, Quality 20, fast preset (best visual quality)
  • off      - No optimization, use source file directly""",
    )
    set_cmd.add_argument(
        "--codec",
        choices=["h264", "av1", "vp9"],
        default="h264",
        metavar="CODEC",
        help="""Video codec for encoding (default: h264)
  • h264 - H.264/AVC codec, outputs MP4 (widely compatible)
  • av1  - AV1 codec, outputs MKV (modern, efficient, requires VAAPI)
  • vp9  - VP9 codec, outputs WebM (open format, CPU only)""",
    )
    set_cmd.add_argument(
        "--encoder",
        choices=["auto", "cpu", "vaapi", "nvenc"],
        default="auto",
        metavar="ENC",
        help="""Encoding backend (default: auto)
  • auto  - Smart selection: NVENC > CPU for H.264, VAAPI for AV1, CPU for VP9
  • cpu   - Software encoding (libx264/libvpx-vp9, no hardware acceleration)
  • vaapi - Intel/AMD hardware encode (strict, no fallback) - AV1 only
  • nvenc - NVIDIA hardware encode (strict, no fallback) - H.264 only""",
    )

    set_cmd.add_argument(
        "--auto-power",
        action="store_true",
        help="Enable dynamic profile switching based on battery/AC state"
    )

    # Status commands parser
    sub.add_parser(
        "status",
        help="Show current wallpaper status",
        description="Display information about the currently running wallpaper (if any)."
    )

    # Stop commands parser
    sub.add_parser(
        "stop",
        help="Stop all wallpapers",
        description="Stop all currently running wallpapers (mpvpaper processes)."
    )

    # Auto commands parser
    auto_cmd = sub.add_parser(
        "auto",
        help="Run auto power-aware profile switching daemon",
        description="""Run the automatic power-aware profile switching daemon.

This daemon monitors your power status (AC/battery) and battery level to automatically
switch between optimization profiles. Requires a session created with --auto-power.""",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    auto_cmd.add_argument(
        "--once",
        action="store_true",
        help="Run one evaluation cycle and exit (no daemon loop)"
    )
    auto_cmd.add_argument(
        "--status",
        action="store_true",
        help="Show current auto power status and exit"
    )

    # Profile commands parser
    profile_cmd = sub.add_parser(
        "profile",
        help="Manage profile overrides",
        description="""Manually override automatic profile switching.
        
When an override is set, the auto daemon will not change profiles automatically.""",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    profile_cmd.add_argument(
        "action",
        choices=["set", "auto"],
        help="""Profile action
  • set  - Manually set a specific profile (disables auto switching)
  • auto - Clear override and resume automatic switching"""
    )
    profile_cmd.add_argument(
        "profile_name",
        nargs="?",
        choices=["eco", "balanced", "quality", "eco_strict"],
        help="Profile to set (required for 'set' action)"
    )

    # Cache commands parser
    cache_cmd = sub.add_parser(
        "cache",
        help="Manage optimization cache",
        description="""Manage the wallpaper optimization cache.
        
The cache stores optimized video files to avoid re-encoding on every run.
Cache location: ~/.cache/hyprwall/""",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    cache_cmd.add_argument(
        "action",
        nargs="?",
        default="size",
        choices=["clear", "size"],
        help="""Cache action (default: size)
  • size  - Show current cache size
  • clear - Delete all cached files"""
    )

    # List of commands
    args = parser.parse_args()

    return args

def cache_size_bytes(root: Path) -> int:
    total = 0
    if not root.exists():
        return 0
    for p in root.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total

def human_size(n: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    x = float(n)
    for u in units:
        if x < 1024.0:
            return f"{x:.1f}{u}"
        x /= 1024.0
    return f"{x:.1f}PB"

def main():
    args = parse_arguments()

    if not args.no_banner and args.command == "set":
        print_banner()
        print()

    paths.ensure_directories()

    if args.verbose:
        print_header("Debug Information")
        print_info("Config directory", str(paths.CONFIG_DIR))
        print_info("Cache directory", str(paths.CACHE_DIR))
        print_info("State directory", str(paths.STATE_DIR))
        print_info("State file", str(paths.STATE_FILE))
        print_info("Log file", str(paths.LOG_FILE))
        print()

    try:
        if args.command == "set":
            # Validate wallpaper path
            animate_progress("Validating wallpaper path", 0.3)
            valid_path = detect.validate_wallpaper(args.path)
            print_success(f"Wallpaper found: {Colors.DIM}{valid_path.name}{Colors.RESET}")

            # Detect all monitors (global-only)
            animate_progress("Detecting monitor configuration", 0.3)
            monitors = hypr.list_monitors()
            if not monitors:
                print_error("No monitors detected")
                raise SystemExit(1)

            print_success(f"Detected {len(monitors)} monitor(s):")
            for m in monitors:
                print_info(f"  • {m.name}", f"{m.width}×{m.height}", indent=1)

            target_monitors = [(m.name, m.width, m.height) for m in monitors]

            # Validate auto-power settings
            if args.auto_power and args.profile == "off":
                print_error("Cannot use --auto-power with --profile off")
                raise SystemExit(1)

            # Display configuration
            print_header("Configuration")
            print_info("Source", str(valid_path))
            print_info("Mode", args.mode)
            print_info("Target", f"All monitors ({len(target_monitors)})")
            print_info("Profile", args.profile if args.profile != "off" else "off (no optimization)")
            if args.profile != "off":
                print_info("Codec", args.codec.upper())
                print_info("Encoder", args.encoder)
            print()

            # Optimization phase - optimize per resolution
            monitor_files = {}  # {monitor_name: file_to_play}

            if args.profile != "off":
                prof = {
                    "eco": optimize.ECO,
                    "balanced": optimize.BALANCED,
                    "quality": optimize.QUALITY,
                }[args.profile]

                print_header("Optimization")

                # Group monitors by resolution to avoid duplicate optimizations
                res_to_monitors = {}
                for mon_name, w, h in target_monitors:
                    key = (w, h)
                    if key not in res_to_monitors:
                        res_to_monitors[key] = []
                    res_to_monitors[key].append(mon_name)

                # Optimize once per unique resolution
                res_to_file = {}
                for (w, h), mon_names in res_to_monitors.items():
                    animate_progress(f"Optimizing for {w}×{h} ({len(mon_names)} monitor(s))", 0.5)

                    res = optimize.ensure_optimized(
                        valid_path,
                        width=w,
                        height=h,
                        profile=prof,
                        mode=args.mode,
                        codec=args.codec,
                        encoder=args.encoder,
                        verbose=args.verbose,
                    )

                    res_to_file[(w, h)] = res.path

                    # Display truthful information about what happened
                    if res.cache_hit:
                        print_success(f"Cache hit for {w}×{h}")
                        if args.verbose:
                            print_info("Encoder used", res.used, indent=1)
                    else:
                        if res.used == res.chosen:
                            print_success(f"Encoded {w}×{h} with {res.used.upper()}")
                        else:
                            print_warning(f"{res.chosen.upper()} failed, fallback to {res.used.upper()} (auto mode)")

                    if args.verbose:
                        print_info("Optimized file", str(res.path), indent=1)
                        if res.requested != res.chosen:
                            print_info("Encoder selection", f"requested={res.requested}, chosen={res.chosen}, used={res.used}", indent=1)

                # Map monitors to their optimized files
                for mon_name, w, h in target_monitors:
                    monitor_files[mon_name] = res_to_file[(w, h)]

                print()
            else:
                # No optimization - use source file for all
                for mon_name, w, h in target_monitors:
                    monitor_files[mon_name] = valid_path

            # Stop existing wallpaper
            animate_progress("Stopping existing wallpaper", 0.3)
            runner.stop()

            # Start wallpaper on all monitors (global-only)
            print_header("Starting Wallpapers")
            entries = [
                runner.StartManyEntry(
                    monitor=mon_name,
                    file=monitor_files[mon_name],
                    mode=args.mode,
                )
                for mon_name, w, h in target_monitors
            ]

            animate_progress("Starting wallpapers on all monitors", 0.5)
            multi_state = runner.start_many(entries, extra_args=[])

            print_success(f"Started on {len(multi_state.monitors)} monitor(s)")
            for mon_name in multi_state.monitors:
                print_info(f"  • {mon_name}", f"PID={multi_state.monitors[mon_name].pid}", indent=1)

            # Save session with real reference monitor (focused > largest)
            ref_mon = hypr.pick_reference_monitor(monitors)
            save_session(Session(
                source=str(valid_path),
                ref_monitor=ref_mon.name if ref_mon else "",
                mode=str(args.mode),
                codec=str(args.codec),
                encoder=str(args.encoder),
                auto_power=bool(args.auto_power),
                last_profile=args.profile if args.profile != "off" else "off",
                last_switch_at=0.0,
                cooldown_s=60,
                override_profile=None,
            ))

            print()

        elif args.command == "status":
            print_header("Wallpaper Status")
            st = runner.status()

            if not st.get("running"):
                print_warning("No wallpaper is currently running")
                if args.verbose:
                    print()
                    print(f"{Colors.DIM}Raw state: {st}{Colors.RESET}")
                return

            # Check if multi-monitor
            if st.get("multi"):
                print_info("Status", f"{Colors.BRIGHT_GREEN}Running (Multi-Monitor){Colors.RESET}")
                print_info("Monitors", str(len(st.get("monitors", {}))))
                print()

                for mon_name, mon_st in st.get("monitors", {}).items():
                    print_separator("─", 40)
                    print_info("Monitor", f"{Colors.BRIGHT_WHITE}{mon_name}{Colors.RESET}")
                    print_info("Status", f"{Colors.BRIGHT_GREEN}Running{Colors.RESET}" if mon_st.get("running") else f"{Colors.BRIGHT_RED}Stopped{Colors.RESET}", indent=1)
                    print_info("File", mon_st.get('file', 'unknown'), indent=1)
                    print_info("Mode", mon_st.get('mode', 'auto'), indent=1)
                    print_info("Process", f"PID={mon_st['pid']}, PGID={mon_st['pgid']}", indent=1)

                    if args.verbose:
                        print_info("Process exists", str(mon_st.get('exists', False)), indent=1)
                        print_info("Is mpvpaper", str(mon_st.get('is_mpvpaper', False)), indent=1)

                print_separator("─", 40)

                if args.verbose:
                    print()
                    print_info("State file", st.get('state_file', 'unknown'))
                    print_info("Log file", st.get('log_file', 'unknown'))
            else:
                # Single-monitor (legacy)
                print_info("Status", f"{Colors.BRIGHT_GREEN}Running{Colors.RESET}")
                print_info("Monitor", st.get('monitor', 'unknown'))
                print_info("File", st.get('file', 'unknown'))
                print_info("Mode", st.get('mode', 'auto'))
                print_info("Process", f"PID={st['pid']}, PGID={st['pgid']}")

                if args.verbose:
                    print()
                    print_separator()
                    print_info("State file", st.get('state_file', 'unknown'))
                    print_info("Log file", st.get('log_file', 'unknown'))
                    print_info("Process exists", str(st.get('exists', False)))
                    print_info("Is mpvpaper", str(st.get('is_mpvpaper', False)))
            print()

        elif args.command == "stop":
            animate_progress("Stopping wallpaper(s)", 0.5)
            was_stopped = runner.stop()

            if was_stopped:
                print_success("Wallpaper(s) stopped successfully")
            else:
                print_warning("No wallpaper process was running")
            print()

        elif args.command == "auto":
            sess = load_session()
            if not sess:
                print_error("No session found. Run 'hyprwall set ... --auto-power' first.")
                raise SystemExit(1)

            if not sess.auto_power:
                print_warning("auto_power is disabled in session. Re-run set with --auto-power.")
                raise SystemExit(1)


            # Handle --status flag
            if args.status:
                print_header("Auto Power Status")
                st = get_power_status()
                h = Hysteresis()
                target = choose_profile(st, sess.last_profile, h)

                print_info("Power State", f"AC={st.on_ac}, Battery={st.percent}%")
                print_info("Last Profile", sess.last_profile)
                print_info("Target Profile", target)
                print_info("Auto Power", "enabled" if sess.auto_power else "disabled")
                print_info("Override", sess.override_profile or "none")
                print_info("Cooldown", f"{sess.cooldown_s}s")

                elapsed = int(time.time() - sess.last_switch_at) if sess.last_switch_at > 0 else 0
                if sess.last_switch_at > 0:
                    print_info("Last Switch", f"{elapsed}s ago")
                else:
                    print_info("Last Switch", "never")

                print()

                if sess.override_profile:
                    print_warning(f"Manual override active: {sess.override_profile}")
                    print_info("Tip", "Run 'hyprwall profile auto' to resume automatic switching", indent=1)
                elif target != sess.last_profile:
                    can_switch = should_switch(
                        target,
                        sess.last_profile,
                        sess.last_switch_at,
                        sess.cooldown_s,
                        sess.override_profile
                    )
                    if can_switch:
                        print_success(f"Ready to switch to: {target}")
                    else:
                        remaining = sess.cooldown_s - elapsed
                        if remaining < 0:
                            remaining = 0
                        print_warning(f"Cooldown active: {remaining}s remaining")
                else:
                    print_success("Profile is optimal")

                print()
                raise SystemExit(0)

            # Normal daemon mode
            print_header("Auto Power Profiles")
            h = Hysteresis()
            last = sess.last_profile

            print_info("Source", sess.source)
            print_info("Monitor", sess.ref_monitor)
            print_info("Mode", sess.mode)
            print_info("Codec", sess.codec)
            print_info("Encoder", sess.encoder)
            print_info("Last profile", last)
            if sess.override_profile:
                print_info("Override", sess.override_profile)
            print()

            if not args.once:
                print_success("Auto power daemon started. Press Ctrl+C to stop.")
                print()

            while True:
                st = get_power_status()
                target = choose_profile(st, last, h)

                # Check if switch is allowed (respects override and cooldown)
                if should_switch(target, last, sess.last_switch_at, sess.cooldown_s, sess.override_profile):
                    print_info("Power", f"on_ac={st.on_ac} percent={st.percent}")
                    print_warning(f"Switch profile: {last} -> {target}")

                    # Resolve OptimizeProfile object
                    prof = {
                        "eco": optimize.ECO,
                        "balanced": optimize.BALANCED,
                        "quality": optimize.QUALITY,
                        "eco_strict": optimize.ECO_STRICT,
                    }[target]

                    # Re-optimize from SOURCE (not cached optimized file)
                    src = Path(sess.source)
                    w, hres = get_reference_resolution(sess.ref_monitor)

                    res = optimize.ensure_optimized(
                        src,
                        width=w,
                        height=hres,
                        profile=prof,
                        mode=sess.mode,
                        codec=sess.codec,
                        encoder=sess.encoder,
                        verbose=False,
                    )

                    runner.stop()
                    # Global start (all monitors) - ref_monitor used only for resolution hint
                    all_monitors = hypr.list_monitors()
                    entries = [
                        runner.StartManyEntry(monitor=m.name, file=res.path, mode=sess.mode)
                        for m in all_monitors
                    ]
                    runner.start_many(entries)

                    last = target
                    save_session(Session(
                        source=sess.source,
                        ref_monitor=sess.ref_monitor,
                        mode=sess.mode,
                        codec=sess.codec,
                        encoder=sess.encoder,
                        auto_power=True,
                        last_profile=last,
                        last_switch_at=time.time(),
                        cooldown_s=sess.cooldown_s,
                        override_profile=sess.override_profile,
                    ))

                    # debounce
                    time.sleep(10)

                # Exit if --once flag
                if args.once:
                    if target == last:
                        print_success(f"Profile is optimal: {last}")
                    print()
                    break

                # polling interval
                if st.on_ac is True:
                    time.sleep(90)
                else:
                    time.sleep(25)

        elif args.command == "profile":
            print_header("Profile Management")
            sess = load_session()
            if not sess:
                print_error("No session found. Run 'hyprwall set' first.")
                raise SystemExit(1)


            if args.action == "set":
                if not args.profile_name:
                    print_error("Profile name required for 'set' action")
                    print_info("Usage", "hyprwall profile set <eco|balanced|quality|eco_strict>", indent=1)
                    raise SystemExit(1)

                target_profile = args.profile_name

                print_info("Current profile", sess.last_profile)
                print_info("Override to", target_profile)
                print()

                # Resolve OptimizeProfile object
                prof = {
                    "eco": optimize.ECO,
                    "balanced": optimize.BALANCED,
                    "quality": optimize.QUALITY,
                    "eco_strict": optimize.ECO_STRICT,
                }[target_profile]

                # Re-optimize and apply
                src = Path(sess.source)
                w, hres = get_reference_resolution(sess.ref_monitor)

                animate_progress("Optimizing video", 1.0)
                res = optimize.ensure_optimized(
                    src,
                    width=w,
                    height=hres,
                    profile=prof,
                    mode=sess.mode,
                    codec=sess.codec,
                    encoder=sess.encoder,
                    verbose=args.verbose,
                )

                runner.stop()
                # Global start (all monitors) - ref_monitor used only for resolution hint
                all_monitors = hypr.list_monitors()
                entries = [
                    runner.StartManyEntry(monitor=m.name, file=res.path, mode=sess.mode)
                    for m in all_monitors
                ]
                runner.start_many(entries)

                # Save with override set
                save_session(Session(
                    source=sess.source,
                    ref_monitor=sess.ref_monitor,
                    mode=sess.mode,
                    codec=sess.codec,
                    encoder=sess.encoder,
                    auto_power=sess.auto_power,
                    last_profile=target_profile,
                    last_switch_at=time.time(),
                    cooldown_s=sess.cooldown_s,
                    override_profile=target_profile,  # Set override
                ))

                print_success(f"Profile set to: {target_profile}")
                print_warning("Auto power switching is now DISABLED")
                print_info("Tip", "Run 'hyprwall profile auto' to re-enable automatic switching", indent=1)
                print()

            elif args.action == "auto":
                if sess.override_profile is None:
                    print_success("Auto mode already active")
                    print()
                    raise SystemExit(0)

                print_info("Previous override", sess.override_profile)
                print_info("Resuming", "automatic profile switching")
                print()

                # Clear override
                save_session(Session(
                    source=sess.source,
                    ref_monitor=sess.ref_monitor,
                    mode=sess.mode,
                    codec=sess.codec,
                    encoder=sess.encoder,
                    auto_power=sess.auto_power,
                    last_profile=sess.last_profile,
                    last_switch_at=sess.last_switch_at,
                    cooldown_s=sess.cooldown_s,
                    override_profile=None,  # Clear override
                ))

                print_success("Automatic profile switching re-enabled")
                if sess.auto_power:
                    print_info("Tip", "Run 'hyprwall auto' daemon to apply automatic switching", indent=1)
                else:
                    print_warning("Note: auto_power is disabled in session")
                    print_info("Tip", "Run 'hyprwall set --auto-power' to enable it", indent=1)
                print()

        elif args.command == "tldr":
            print_banner()
            print()

            print_header("What is HyprWall?")
            print(f"{Colors.BRIGHT_WHITE}HyprWall{Colors.RESET} is a {Colors.BRIGHT_CYAN}lightweight wallpaper manager{Colors.RESET} for Hyprland.")
            print(f"Set {Colors.BRIGHT_MAGENTA}images{Colors.RESET} or {Colors.BRIGHT_MAGENTA}animated videos{Colors.RESET} as your desktop background.")
            print()

            print_header("Why HyprWall?")
            print(f"{Colors.CYAN}▸{Colors.RESET} {Colors.BOLD}Wayland-native{Colors.RESET} {Colors.DIM}— Built for Hyprland, no X11 legacy{Colors.RESET}")
            print(f"{Colors.CYAN}▸{Colors.RESET} {Colors.BOLD}Smart optimization{Colors.RESET} {Colors.DIM}— Auto-encode videos for battery efficiency{Colors.RESET}")
            print(f"{Colors.CYAN}▸{Colors.RESET} {Colors.BOLD}Power-aware{Colors.RESET} {Colors.DIM}— Automatically adjust quality based on AC/battery state{Colors.RESET}")
            print(f"{Colors.CYAN}▸{Colors.RESET} {Colors.BOLD}Intelligent caching{Colors.RESET} {Colors.DIM}— Never re-encode the same file twice{Colors.RESET}")
            print(f"{Colors.CYAN}▸{Colors.RESET} {Colors.BOLD}Multi-monitor ready{Colors.RESET} {Colors.DIM}— Detects your displays automatically{Colors.RESET}")
            print(f"{Colors.CYAN}▸{Colors.RESET} {Colors.BOLD}CLI-first design{Colors.RESET} {Colors.DIM}— No bloat, pure terminal efficiency{Colors.RESET}")
            print()

            print_header("Quick Start")
            print(f"{Colors.BRIGHT_GREEN}# Set an image wallpaper{Colors.RESET}")
            print(f"{Colors.DIM}${Colors.RESET} hyprwall set ~/Pictures/sunset.jpg")
            print()
            print(f"{Colors.BRIGHT_GREEN}# Set a video wallpaper (auto-optimized){Colors.RESET}")
            print(f"{Colors.DIM}${Colors.RESET} hyprwall set ~/Videos/ocean-waves.mp4")
            print()
            print(f"{Colors.BRIGHT_GREEN}# Use a directory (picks most recent file){Colors.RESET}")
            print(f"{Colors.DIM}${Colors.RESET} hyprwall set ~/Wallpapers/")
            print()

            print_header("Rendering Modes")
            print(f"{Colors.BRIGHT_YELLOW}cover{Colors.RESET}   {Colors.DIM}→{Colors.RESET}  Fill screen, crop edges {Colors.DIM}(default for images){Colors.RESET}")
            print(f"{Colors.BRIGHT_YELLOW}fit{Colors.RESET}     {Colors.DIM}→{Colors.RESET}  Letterbox, keep aspect ratio {Colors.DIM}(default for videos){Colors.RESET}")
            print(f"{Colors.BRIGHT_YELLOW}stretch{Colors.RESET} {Colors.DIM}→{Colors.RESET}  Fill completely, may distort")
            print()
            print(f"{Colors.DIM}Example:{Colors.RESET} hyprwall set --mode fit wallpaper.jpg")
            print()

            print_header("Optimization Profiles")
            print(f"{Colors.BRIGHT_GREEN}eco{Colors.RESET}      {Colors.DIM}→{Colors.RESET}  24fps, Quality 28 {Colors.DIM}(lowest battery usage){Colors.RESET}")
            print(f"{Colors.BRIGHT_CYAN}balanced{Colors.RESET} {Colors.DIM}→{Colors.RESET}  30fps, Quality 24 {Colors.DIM}(recommended){Colors.RESET}")
            print(f"{Colors.BRIGHT_MAGENTA}quality{Colors.RESET}  {Colors.DIM}→{Colors.RESET}  30fps, Quality 20 {Colors.DIM}(best visual quality){Colors.RESET}")
            print(f"{Colors.DIM}off{Colors.RESET}      {Colors.DIM}→{Colors.RESET}  No optimization, use source directly")
            print()
            print(f"{Colors.DIM}Example:{Colors.RESET} hyprwall set --profile eco video.mp4")
            print()

            print_header("Video Codecs")
            print(f"{Colors.BRIGHT_YELLOW}h264{Colors.RESET} {Colors.DIM}→{Colors.RESET}  H.264/AVC, outputs MP4 {Colors.DIM}(widely compatible, default){Colors.RESET}")
            print(f"{Colors.BRIGHT_YELLOW}av1{Colors.RESET}  {Colors.DIM}→{Colors.RESET}  AV1, outputs MKV {Colors.DIM}(modern, efficient, VAAPI only){Colors.RESET}")
            print(f"{Colors.BRIGHT_YELLOW}vp9{Colors.RESET}  {Colors.DIM}→{Colors.RESET}  VP9, outputs WebM {Colors.DIM}(open format, CPU only){Colors.RESET}")
            print()
            print(f"{Colors.DIM}Example:{Colors.RESET} hyprwall set --codec av1 video.mp4")
            print()

            print_header("Hardware Encoding")
            print(f"{Colors.BRIGHT_YELLOW}auto{Colors.RESET}   {Colors.DIM}→{Colors.RESET}  Smart selection based on codec {Colors.DIM}(recommended){Colors.RESET}")
            print(f"{Colors.BRIGHT_YELLOW}nvenc{Colors.RESET}  {Colors.DIM}→{Colors.RESET}  NVIDIA GPU encoding {Colors.DIM}(H.264 only, strict){Colors.RESET}")
            print(f"{Colors.BRIGHT_YELLOW}vaapi{Colors.RESET}  {Colors.DIM}→{Colors.RESET}  Intel/AMD GPU encoding {Colors.DIM}(AV1 only, strict){Colors.RESET}")
            print(f"{Colors.BRIGHT_YELLOW}cpu{Colors.RESET}    {Colors.DIM}→{Colors.RESET}  Software encoding {Colors.DIM}(libx264/libvpx-vp9){Colors.RESET}")
            print()
            print(f"{Colors.DIM}Example:{Colors.RESET} hyprwall set --codec h264 --encoder nvenc video.mp4")
            print()

            print_header("Codec/Encoder Compatibility")
            print(f"{Colors.BRIGHT_CYAN}H.264{Colors.RESET}  {Colors.DIM}→{Colors.RESET}  CPU, NVENC {Colors.DIM}(no VAAPI on AMD Radeon 780M){Colors.RESET}")
            print(f"{Colors.BRIGHT_CYAN}AV1{Colors.RESET}    {Colors.DIM}→{Colors.RESET}  VAAPI only {Colors.DIM}(hardware accelerated){Colors.RESET}")
            print(f"{Colors.BRIGHT_CYAN}VP9{Colors.RESET}    {Colors.DIM}→{Colors.RESET}  CPU only")
            print()

            print_header("Auto Power Management")
            print(f"{Colors.BRIGHT_GREEN}# Enable auto power switching{Colors.RESET}")
            print(f"{Colors.DIM}${Colors.RESET} hyprwall set video.mp4 --auto-power")
            print()
            print(f"{Colors.BRIGHT_GREEN}# Run the auto daemon (monitors battery/AC state){Colors.RESET}")
            print(f"{Colors.DIM}${Colors.RESET} hyprwall auto")
            print()
            print(f"{Colors.BRIGHT_GREEN}# Check auto power status{Colors.RESET}")
            print(f"{Colors.DIM}${Colors.RESET} hyprwall auto --status")
            print()
            print(f"{Colors.BRIGHT_GREEN}# Run one evaluation cycle (no daemon loop){Colors.RESET}")
            print(f"{Colors.DIM}${Colors.RESET} hyprwall auto --once")
            print()

            print_header("Manual Profile Override")
            print(f"{Colors.BRIGHT_GREEN}# Manually set a specific profile (disables auto){Colors.RESET}")
            print(f"{Colors.DIM}${Colors.RESET} hyprwall profile set eco")
            print()
            print(f"{Colors.BRIGHT_GREEN}# Clear override and resume automatic switching{Colors.RESET}")
            print(f"{Colors.DIM}${Colors.RESET} hyprwall profile auto")
            print()

            print_header("Other Commands")
            print(f"{Colors.CYAN}hyprwall status{Colors.RESET}       {Colors.DIM}→{Colors.RESET}  Show current wallpaper info")
            print(f"{Colors.CYAN}hyprwall stop{Colors.RESET}         {Colors.DIM}→{Colors.RESET}  Stop the current wallpaper")
            print(f"{Colors.CYAN}hyprwall cache size{Colors.RESET}   {Colors.DIM}→{Colors.RESET}  Display cache statistics")
            print(f"{Colors.CYAN}hyprwall cache clear{Colors.RESET}  {Colors.DIM}→{Colors.RESET}  Delete all cached files")
            print()

            print_header("Supported Formats")
            print(f"{Colors.BRIGHT_MAGENTA}Images{Colors.RESET}  {Colors.DIM}→{Colors.RESET}  JPG, PNG, GIF, WebP")
            print(f"{Colors.BRIGHT_MAGENTA}Videos{Colors.RESET}  {Colors.DIM}→{Colors.RESET}  MP4, MKV, WebM, AVI, MOV")
            print()

            print_header("Systemd Integration")
            print(f"{Colors.BRIGHT_GREEN}# Run auto daemon as a systemd user service{Colors.RESET}")
            print(f"{Colors.DIM}${Colors.RESET} systemctl --user enable --now hyprwall-auto.service")
            print()
            print(f"{Colors.BRIGHT_GREEN}# View daemon logs{Colors.RESET}")
            print(f"{Colors.DIM}${Colors.RESET} journalctl --user -u hyprwall-auto -f")
            print()
            print(f"{Colors.BRIGHT_GREEN}# Stop the daemon{Colors.RESET}")
            print(f"{Colors.DIM}${Colors.RESET} systemctl --user stop hyprwall-auto.service")
            print()

            print_header("Under the Hood")
            print(f"{Colors.CYAN}▸{Colors.RESET} Built on {Colors.BRIGHT_WHITE}mpvpaper{Colors.RESET} {Colors.DIM}(the video wallpaper backend){Colors.RESET}")
            print(f"{Colors.CYAN}▸{Colors.RESET} Uses {Colors.BRIGHT_WHITE}ffmpeg{Colors.RESET} {Colors.DIM}for smart video optimization{Colors.RESET}")
            print(f"{Colors.CYAN}▸{Colors.RESET} Talks to {Colors.BRIGHT_WHITE}hyprctl{Colors.RESET} {Colors.DIM}for monitor detection{Colors.RESET}")
            print(f"{Colors.CYAN}▸{Colors.RESET} XDG-compliant {Colors.DIM}(~/.cache/hyprwall, ~/.config/hyprwall){Colors.RESET}")
            print()

            print_header("Philosophy")
            print(f"{Colors.BRIGHT_CYAN}Predictable{Colors.RESET} {Colors.DIM}— Clean process management, deterministic behavior{Colors.RESET}")
            print(f"{Colors.BRIGHT_CYAN}Performant{Colors.RESET}  {Colors.DIM}— Minimal CPU/battery usage, laptop-friendly{Colors.RESET}")
            print(f"{Colors.BRIGHT_CYAN}Simple{Colors.RESET}      {Colors.DIM}— No GUI bloat, just CLI efficiency{Colors.RESET}")
            print()

            print_separator("═", 60)
            print(f"{Colors.DIM}Project:{Colors.RESET} {Colors.BRIGHT_CYAN}https://github.com/TheOnlyChou/hyprwall{Colors.RESET}")
            print(f"{Colors.DIM}License:{Colors.RESET} {Colors.BRIGHT_WHITE}MIT{Colors.RESET}")
            print_separator("═", 60)
            print()

        elif args.command == "cache":
            if args.action == "clear":
                print_header("Cache Management")
                animate_progress("Clearing cache", 0.5)

                removed_dirs = 0
                removed_files = 0

                if paths.CACHE_DIR.exists():
                    for p in paths.CACHE_DIR.iterdir():
                        # Preserve state directory (state.json + pid files)
                        if p.name == "state":
                            continue

                        # Count what will be removed (recursive for directories)
                        if p.is_dir():
                            d, f = count_tree(p)
                            # +1 for the directory itself (so 'optimized' counts too)
                            removed_dirs += d # Directories inside
                            removed_files += f
                            shutil.rmtree(p, ignore_errors=True)
                        else:
                            try:
                                p.unlink()
                                removed_files += 1
                            except OSError:
                                pass

                paths.ensure_directories()
                print_success(
                    f"Cache cleared successfully ({removed_dirs} dirs, {removed_files} files removed)"
                )
                print_info("State preserved", str(paths.STATE_DIR), indent=1)
                print()

            # Always show cache info for both "size" and after "clear"
            print_header("Cache Information")
            n = cache_size_bytes(paths.CACHE_DIR)

            # Show how many entries exist in optimized cache
            opt_dirs, opt_files = count_tree(paths.OPT_DIR)

            print_info("Cache location", str(paths.CACHE_DIR))
            print_info("Cache size", f"{human_size(n)} ({n:,} bytes)")
            print_info("Optimized entries", f"{opt_dirs} dirs, {opt_files} files")
            print()

    except KeyboardInterrupt:
        print()
        print_warning("Operation cancelled by user")
        raise SystemExit(130)
    except Exception as e:
        print()
        print_error(f"Error: {e}")
        if args.verbose:
            import traceback
            print()
            print(f"{Colors.DIM}{traceback.format_exc()}{Colors.RESET}")
        raise SystemExit(1)

if __name__ == "__main__":
    main()