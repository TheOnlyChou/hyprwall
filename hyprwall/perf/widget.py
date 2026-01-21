"""
GTK performance widget for HyprWall.

Displays wallpaper performance metrics in a clean, non-intrusive dashboard.
"""

from __future__ import annotations
from typing import Optional

try:
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import Gtk, GLib
    GTK_AVAILABLE = True
except (ImportError, ValueError):
    GTK_AVAILABLE = False

from hyprwall.perf.monitor import WallpaperPerfMonitor


class PerformanceWidget(Gtk.Box):
    """
    GTK widget displaying wallpaper performance metrics.

    Design:
    - Compact dashboard with circular progress indicators
    - Shows CPU, RAM, GPU usage and temperatures
    - Gracefully handles unavailable metrics (shows "N/A")
    - Auto-refreshes every 1-2 seconds
    - Can be hidden/shown via toggle
    """

    def __init__(self):
        """Initialize the performance widget"""
        if not GTK_AVAILABLE:
            raise RuntimeError("GTK4 not available")

        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        self.add_css_class("perf-widget")
        self.set_margin_start(12)
        self.set_margin_end(12)
        self.set_margin_top(8)
        self.set_margin_bottom(8)

        # Monitor instance
        self._monitor = WallpaperPerfMonitor()
        self._current_pid: Optional[int] = None
        self._refresh_timer: Optional[int] = None

        # Build UI
        self._build_ui()

    def _build_ui(self):
        """Build the performance widget UI"""
        # Title
        title = Gtk.Label(label="Wallpaper Performance")
        title.set_xalign(0)
        title.add_css_class("title-4")
        self.append(title)

        # Metrics grid (2x3)
        grid = Gtk.Grid()
        grid.set_column_spacing(12)
        grid.set_row_spacing(8)
        grid.set_margin_top(8)
        self.append(grid)

        # Row 0: CPU and RAM
        self._cpu_label = self._create_metric_label("CPU", "—")
        self._ram_label = self._create_metric_label("RAM", "—")
        grid.attach(self._cpu_label, 0, 0, 1, 1)
        grid.attach(self._ram_label, 1, 0, 1, 1)

        # Row 1: GPU
        self._gpu_label = self._create_metric_label("GPU", "—")
        grid.attach(self._gpu_label, 0, 1, 1, 1)

        # Row 2: Temperatures
        self._cpu_temp_label = self._create_metric_label("CPU Temp", "—")
        self._gpu_temp_label = self._create_metric_label("GPU Temp", "—")
        grid.attach(self._cpu_temp_label, 0, 2, 1, 1)
        grid.attach(self._gpu_temp_label, 1, 2, 1, 1)

        # Info label (small hint)
        info = Gtk.Label(label="Updates every second")
        info.set_xalign(0)
        info.add_css_class("dim-label")
        info.add_css_class("caption")
        info.set_margin_top(4)
        self.append(info)

    def _create_metric_label(self, name: str, value: str) -> Gtk.Box:
        """Create a labeled metric display"""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.add_css_class("perf-metric")

        # Name label
        name_label = Gtk.Label(label=name)
        name_label.set_xalign(0)
        name_label.add_css_class("dim-label")
        name_label.add_css_class("caption")
        box.append(name_label)

        # Value label
        value_label = Gtk.Label(label=value)
        value_label.set_xalign(0)
        value_label.add_css_class("title-3")
        value_label.set_name(f"{name.lower().replace(' ', '_')}_value")
        box.append(value_label)

        return box

    def _get_value_label(self, metric_box: Gtk.Box) -> Optional[Gtk.Label]:
        """Extract the value label from a metric box"""
        child = metric_box.get_first_child()
        while child:
            if isinstance(child, Gtk.Label) and "title-3" in child.get_css_classes():
                return child
            child = child.get_next_sibling()
        return None

    def set_pid(self, pid: Optional[int]):
        """
        Set the PID to monitor.

        Args:
            pid: Process ID of wallpaper, or None to stop monitoring
        """
        self._current_pid = pid

        if pid is None:
            self.stop_monitoring()
        else:
            # Clear history when switching wallpapers
            self._monitor.clear_history()
            self.start_monitoring()

    def start_monitoring(self):
        """Start auto-refresh timer"""
        if self._refresh_timer is not None:
            return  # Already running

        # Refresh every 1.5 seconds (monitor internally rate-limits to 1s)
        self._refresh_timer = GLib.timeout_add_seconds(1, self._refresh_metrics)

        # Immediate first refresh
        self._refresh_metrics()

    def stop_monitoring(self):
        """Stop auto-refresh timer"""
        if self._refresh_timer is not None:
            GLib.source_remove(self._refresh_timer)
            self._refresh_timer = None

        # Reset all labels
        self._set_metric_value(self._cpu_label, "—")
        self._set_metric_value(self._ram_label, "—")
        self._set_metric_value(self._gpu_label, "—")
        self._set_metric_value(self._cpu_temp_label, "—")
        self._set_metric_value(self._gpu_temp_label, "—")

    def _refresh_metrics(self) -> bool:
        """Refresh metrics display (timer callback)"""
        if self._current_pid is None:
            return False  # Stop timer

        # Get metrics
        metrics = self._monitor.get_metrics(self._current_pid)


        # Update CPU
        if metrics.cpu_percent is not None:
            self._set_metric_value(self._cpu_label, f"{metrics.cpu_percent:.1f}%")
        else:
            self._set_metric_value(self._cpu_label, "N/A")

        # Update RAM
        if metrics.ram_mib is not None:
            self._set_metric_value(self._ram_label, f"{metrics.ram_mib:.1f} MiB")
        else:
            self._set_metric_value(self._ram_label, "N/A")

        # Update GPU
        if metrics.gpu_percent is not None:
            self._set_metric_value(self._gpu_label, f"{metrics.gpu_percent:.1f}%")
        else:
            self._set_metric_value(self._gpu_label, "N/A")

        # Update CPU temperature
        if metrics.cpu_temp is not None:
            self._set_metric_value(self._cpu_temp_label, f"{metrics.cpu_temp:.1f}°C")
        else:
            self._set_metric_value(self._cpu_temp_label, "N/A")

        # Update GPU temperature
        if metrics.gpu_temp is not None:
            self._set_metric_value(self._gpu_temp_label, f"{metrics.gpu_temp:.1f}°C")
        else:
            self._set_metric_value(self._gpu_temp_label, "N/A")

        return True  # Continue timer


    def _set_metric_value(self, metric_box: Gtk.Box, value: str):
        """Update the value label in a metric box"""
        value_label = self._get_value_label(metric_box)
        if value_label:
            value_label.set_label(value)