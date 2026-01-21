"""
Circular gauge widget for GTK4.

Lightweight circular progress indicator using Cairo for rendering.
"""

from __future__ import annotations
from typing import Optional
import math

try:
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import Gtk, GLib
    GTK_AVAILABLE = True
except (ImportError, ValueError):
    GTK_AVAILABLE = False


class CircularGauge(Gtk.DrawingArea):
    """
    Circular progress gauge widget.

    Design:
    - Uses Gtk.DrawingArea + Cairo for custom rendering
    - Configurable size, colors, and range
    - Shows percentage value in center
    - Smooth animations optional (via GLib timeout)
    - Extremely lightweight (single Cairo draw call)
    """

    def __init__(
        self,
        size: int = 80,
        min_value: float = 0.0,
        max_value: float = 100.0,
        color: str = "#3584e4",  # Adwaita blue
    ):
        """
        Initialize circular gauge.

        Args:
            size: Widget size in pixels (square)
            min_value: Minimum value for gauge
            max_value: Maximum value for gauge
            color: Color for progress arc (hex)
        """
        if not GTK_AVAILABLE:
            raise RuntimeError("GTK4 not available")

        super().__init__()

        self._size = size
        self._min_value = min_value
        self._max_value = max_value
        self._color = self._parse_color(color)

        self._value: Optional[float] = None
        self._label: Optional[str] = None

        # Configure drawing area
        self.set_size_request(size, size)
        self.set_draw_func(self._on_draw)

        # Styling
        self.add_css_class("circular-gauge")

    def set_value(self, value: Optional[float], label: Optional[str] = None):
        """
        Update gauge value.

        Args:
            value: New value (None shows "N/A")
            label: Optional label to show in center (e.g., "24%", "180 MiB")
        """
        self._value = value
        self._label = label
        self.queue_draw()  # Request redraw

    def _on_draw(self, area, cr, width, height):
        """
        Draw the circular gauge using Cairo.

        Args:
            area: Drawing area widget
            cr: Cairo context
            width: Widget width
            height: Widget height
        """
        # Center and radius
        cx = width / 2
        cy = height / 2
        radius = min(width, height) / 2 - 6  # 6px margin

        # Background circle (track)
        cr.set_line_width(6)
        cr.set_source_rgba(0.5, 0.5, 0.5, 0.2)  # Gray, transparent
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.stroke()

        # Progress arc (if value available)
        if self._value is not None:
            # Normalize value to 0-1 range
            normalized = (self._value - self._min_value) / (self._max_value - self._min_value)
            normalized = max(0.0, min(1.0, normalized))  # Clamp to [0, 1]

            # Arc angle (starts at top, clockwise)
            start_angle = -math.pi / 2  # Top
            end_angle = start_angle + (2 * math.pi * normalized)

            # Draw progress arc
            cr.set_line_width(6)
            cr.set_line_cap(1)  # Round cap
            cr.set_source_rgba(*self._color)
            cr.arc(cx, cy, radius, start_angle, end_angle)
            cr.stroke()

        # Center text
        if self._label:
            text = self._label
        elif self._value is not None:
            text = f"{self._value:.0f}"
        else:
            text = "N/A"

        # Draw text
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.9)  # White text
        cr.select_font_face("Sans", 0, 1)  # Normal weight, bold

        # Font size based on widget size
        font_size = radius / 2.5
        cr.set_font_size(font_size)

        # Center text
        extents = cr.text_extents(text)
        text_x = cx - extents.width / 2 - extents.x_bearing
        text_y = cy - extents.height / 2 - extents.y_bearing

        cr.move_to(text_x, text_y)
        cr.show_text(text)

    def _parse_color(self, color_str: str) -> tuple[float, float, float, float]:
        """
        Parse hex color to RGBA tuple.

        Args:
            color_str: Hex color (e.g., "#3584e4")

        Returns:
            RGBA tuple (0.0-1.0)
        """
        try:
            color_str = color_str.lstrip("#")

            if len(color_str) == 6:
                r = int(color_str[0:2], 16) / 255
                g = int(color_str[2:4], 16) / 255
                b = int(color_str[4:6], 16) / 255
                return (r, g, b, 1.0)

            # Fallback: blue
            return (0.21, 0.52, 0.89, 1.0)

        except ValueError:
            # Fallback: blue
            return (0.21, 0.52, 0.89, 1.0)

    def set_color(self, color: str):
        """Change gauge color"""
        self._color = self._parse_color(color)
        self.queue_draw()