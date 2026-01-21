"""
Enhanced performance panel with circular gauges and sparklines.

Modern, lightweight performance HUD for HyprWall wallpaper monitoring.
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
from hyprwall.gui.widgets.circular_gauge import CircularGauge
from hyprwall.gui.widgets.sparkline import Sparkline


class PerformancePanel(Gtk.Box):
    """
    Enhanced performance monitoring panel.

    Features:
    - Circular gauges for CPU/RAM/GPU
    - Sparklines showing historical trends
    - Optional FPS monitoring from mpv
    - Optional power consumption (Watts)
    - Graceful degradation for unavailable metrics

    Design:
    - Non-intrusive, battery-friendly
    - 1 Hz update rate (respects monitor rate limiting)
    - No background threads
    - Uses GTK main loop timer
    """

    def __init__(self):
        """Initialize the enhanced performance panel"""
        if not GTK_AVAILABLE:
            raise RuntimeError("GTK4 not available")

        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)

        self.add_css_class("perf-panel")
        self.set_margin_start(12)
        self.set_margin_end(12)
        self.set_margin_top(12)
        self.set_margin_bottom(12)

        # Collectors
        self._monitor = WallpaperPerfMonitor()
        # FPS and Power collectors removed - not reliable in all environments

        # State
        self._current_pid: Optional[int] = None
        self._refresh_timer: Optional[int] = None

        # History buffers (extended for sparklines)
        self._cpu_history: list[float] = []
        self._ram_history: list[float] = []
        self._gpu_history: list[float] = []
        self._max_history = 30  # 30 seconds of data at 1 Hz

        # Build UI
        self._build_ui()

    def _build_ui(self):
        """Build the performance panel UI"""
        # Title
        title = Gtk.Label(label="Performance Monitor")
        title.set_xalign(0)
        title.add_css_class("title-3")
        self.append(title)

        # Main metrics grid (circular gauges)
        gauges_grid = Gtk.Grid()
        gauges_grid.set_column_spacing(16)
        gauges_grid.set_row_spacing(8)
        gauges_grid.set_margin_top(8)
        self.append(gauges_grid)

        # CPU gauge + sparkline
        cpu_box = self._create_metric_box("CPU", "#3584e4")
        self._cpu_gauge = cpu_box["gauge"]
        self._cpu_sparkline = cpu_box["sparkline"]
        gauges_grid.attach(cpu_box["container"], 0, 0, 1, 1)

        # RAM gauge + sparkline
        ram_box = self._create_metric_box("RAM", "#33d17a")
        self._ram_gauge = ram_box["gauge"]
        self._ram_sparkline = ram_box["sparkline"]
        gauges_grid.attach(ram_box["container"], 1, 0, 1, 1)

        # GPU gauge + sparkline
        gpu_box = self._create_metric_box("GPU", "#f66151")
        self._gpu_gauge = gpu_box["gauge"]
        self._gpu_sparkline = gpu_box["sparkline"]
        gauges_grid.attach(gpu_box["container"], 2, 0, 1, 1)

        # Secondary metrics (smaller)
        secondary_grid = Gtk.Grid()
        secondary_grid.set_column_spacing(12)
        secondary_grid.set_row_spacing(6)
        secondary_grid.set_margin_top(12)
        self.append(secondary_grid)

        # Temperatures only (FPS and Power removed)
        self._cpu_temp_label = self._create_secondary_metric("CPU Temp", "—")
        secondary_grid.attach(self._cpu_temp_label, 0, 0, 1, 1)

        self._gpu_temp_label = self._create_secondary_metric("GPU Temp", "—")
        secondary_grid.attach(self._gpu_temp_label, 1, 0, 1, 1)

        # Info label
        info = Gtk.Label(label="Updates every second • Hover for details")
        info.set_xalign(0)
        info.add_css_class("dim-label")
        info.add_css_class("caption")
        info.set_margin_top(8)
        self.append(info)

    def _create_metric_box(self, name: str, color: str) -> dict:
        """
        Create a metric box with gauge + sparkline.

        Args:
            name: Metric name (e.g., "CPU")
            color: Hex color for gauge/sparkline

        Returns:
            Dict with 'container', 'gauge', 'sparkline' widgets
        """
        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        container.add_css_class("metric-box")

        # Gauge
        gauge = CircularGauge(size=80, color=color)
        gauge.set_halign(Gtk.Align.CENTER)
        container.append(gauge)

        # Label
        label = Gtk.Label(label=name)
        label.add_css_class("caption")
        label.set_halign(Gtk.Align.CENTER)
        container.append(label)

        # Sparkline (small historical graph)
        sparkline = Sparkline(width=80, height=20, color=color, max_points=self._max_history)
        sparkline.set_halign(Gtk.Align.CENTER)
        container.append(sparkline)

        return {
            "container": container,
            "gauge": gauge,
            "sparkline": sparkline,
        }

    def _create_secondary_metric(self, name: str, value: str) -> Gtk.Box:
        """Create a secondary metric (label-based)"""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.add_css_class("secondary-metric")

        # Name
        name_label = Gtk.Label(label=name)
        name_label.set_xalign(0)
        name_label.add_css_class("dim-label")
        name_label.add_css_class("caption")
        box.append(name_label)

        # Value
        value_label = Gtk.Label(label=value)
        value_label.set_xalign(0)
        value_label.add_css_class("title-3")
        value_label.set_name(f"{name.lower().replace(' ', '_')}_value")
        box.append(value_label)

        return box

    def set_pid(self, pid: Optional[int]):
        """
        Set the PID to monitor.

        Args:
            pid: Process ID of wallpaper (mpvpaper)
        """
        self._current_pid = pid

        if pid is None:
            self.stop_monitoring()
        else:
            # Clear histories
            self._cpu_history.clear()
            self._ram_history.clear()
            self._gpu_history.clear()
            self._monitor.clear_history()
            self.start_monitoring()

    def start_monitoring(self):
        """Start auto-refresh timer"""
        if self._refresh_timer is not None:
            return  # Already running

        # Refresh every 1 second (respects monitor rate limiting)
        self._refresh_timer = GLib.timeout_add_seconds(1, self._refresh_metrics)

        # Immediate first refresh
        self._refresh_metrics()

    def stop_monitoring(self):
        """Stop auto-refresh timer"""
        if self._refresh_timer is not None:
            GLib.source_remove(self._refresh_timer)
            self._refresh_timer = None

        # Reset all widgets
        self._cpu_gauge.set_value(None)
        self._ram_gauge.set_value(None)
        self._gpu_gauge.set_value(None)

        self._cpu_sparkline.clear()
        self._ram_sparkline.clear()
        self._gpu_sparkline.clear()

        self._set_secondary_value(self._cpu_temp_label, "—")
        self._set_secondary_value(self._gpu_temp_label, "—")

    def _refresh_metrics(self) -> bool:
        """
        Refresh metrics display (timer callback).

        Returns:
            True to continue timer, False to stop
        """
        if self._current_pid is None:
            return False  # Stop timer

        # Get metrics from monitor (rate-limited to 1 Hz)
        metrics = self._monitor.get_metrics(self._current_pid)

        # Update CPU
        if metrics.cpu_percent is not None:
            self._cpu_gauge.set_value(metrics.cpu_percent, f"{metrics.cpu_percent:.1f}%")
            self._cpu_history.append(metrics.cpu_percent)
            if len(self._cpu_history) > self._max_history:
                self._cpu_history.pop(0)
            self._cpu_sparkline.set_data(self._cpu_history, min_value=0, max_value=100)
        else:
            self._cpu_gauge.set_value(None, "N/A")

        # Update RAM (normalize to MiB, gauge shows 0-2048 MiB range)
        if metrics.ram_mib is not None:
            # Adaptive max: round up to nearest power of 2
            max_ram = 2048
            if metrics.ram_mib > 512:
                max_ram = 2048
            elif metrics.ram_mib > 256:
                max_ram = 512
            else:
                max_ram = 256

            self._ram_gauge.set_value(metrics.ram_mib, f"{metrics.ram_mib:.0f}M")
            self._ram_gauge._max_value = max_ram  # Dynamic range

            self._ram_history.append(metrics.ram_mib)
            if len(self._ram_history) > self._max_history:
                self._ram_history.pop(0)
            self._ram_sparkline.set_data(self._ram_history, min_value=0)
        else:
            self._ram_gauge.set_value(None, "N/A")

        # Update GPU
        if metrics.gpu_percent is not None:
            self._gpu_gauge.set_value(metrics.gpu_percent, f"{metrics.gpu_percent:.1f}%")
            self._gpu_history.append(metrics.gpu_percent)
            if len(self._gpu_history) > self._max_history:
                self._gpu_history.pop(0)
            self._gpu_sparkline.set_data(self._gpu_history, min_value=0, max_value=100)
        else:
            self._gpu_gauge.set_value(None, "N/A")

        # FPS and Power removed - not reliable in all environments

        # Update temperatures
        if metrics.cpu_temp is not None:
            self._set_secondary_value(self._cpu_temp_label, f"{metrics.cpu_temp:.0f}°C")
        else:
            self._set_secondary_value(self._cpu_temp_label, "N/A")

        if metrics.gpu_temp is not None:
            self._set_secondary_value(self._gpu_temp_label, f"{metrics.gpu_temp:.0f}°C")
        else:
            self._set_secondary_value(self._gpu_temp_label, "N/A")

        return True  # Continue timer

    def _set_secondary_value(self, metric_box: Gtk.Box, value: str):
        """Update value label in a secondary metric box"""
        child = metric_box.get_first_child()
        while child:
            if isinstance(child, Gtk.Label) and "title-3" in child.get_css_classes():
                child.set_label(value)
                return
            child = child.get_next_sibling()