"""
Sparkline widget for GTK4.

Minimal line chart for showing historical trends in performance metrics.
"""

from __future__ import annotations
from typing import Optional

try:
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import Gtk
    GTK_AVAILABLE = True
except (ImportError, ValueError):
    GTK_AVAILABLE = False


class Sparkline(Gtk.DrawingArea):
    """
    Sparkline mini-chart widget.

    Design:
    - Renders a list of values as a line graph
    - Auto-scales to fit widget bounds
    - Lightweight (single Cairo path)
    - Ideal for showing short history (10-30 samples)
    """

    def __init__(
        self,
        width: int = 100,
        height: int = 30,
        color: str = "#3584e4",  # Adwaita blue
        max_points: int = 30,
    ):
        """
        Initialize sparkline.

        Args:
            width: Widget width in pixels
            height: Widget height in pixels
            color: Line color (hex)
            max_points: Maximum number of points to display
        """
        if not GTK_AVAILABLE:
            raise RuntimeError("GTK4 not available")

        super().__init__()

        self._width = width
        self._height = height
        self._color = self._parse_color(color)
        self._max_points = max_points

        self._values: list[float] = []
        self._min_value = 0.0
        self._max_value = 100.0

        # Configure drawing area
        self.set_size_request(width, height)
        self.set_draw_func(self._on_draw)

        # Styling
        self.add_css_class("sparkline")

    def set_data(
        self,
        values: list[float],
        min_value: Optional[float] = None,
        max_value: Optional[float] = None,
    ):
        """
        Update sparkline data.

        Args:
            values: List of values to plot
            min_value: Minimum Y value (auto-detected if None)
            max_value: Maximum Y value (auto-detected if None)
        """
        # Limit to max_points
        if len(values) > self._max_points:
            self._values = values[-self._max_points:]
        else:
            self._values = values.copy()

        # Auto-detect range if not provided
        if self._values:
            if min_value is None:
                self._min_value = min(self._values)
            else:
                self._min_value = min_value

            if max_value is None:
                self._max_value = max(self._values)
            else:
                self._max_value = max_value

            # Avoid zero range
            if abs(self._max_value - self._min_value) < 0.1:
                self._max_value = self._min_value + 10

        self.queue_draw()

    def _on_draw(self, area, cr, width, height):
        """
        Draw the sparkline using Cairo.

        Args:
            area: Drawing area widget
            cr: Cairo context
            width: Widget width
            height: Widget height
        """
        if not self._values or len(self._values) < 2:
            return  # Need at least 2 points

        # Padding
        padding = 2
        chart_width = width - 2 * padding
        chart_height = height - 2 * padding

        # Background (subtle)
        cr.set_source_rgba(0.5, 0.5, 0.5, 0.05)
        cr.rectangle(0, 0, width, height)
        cr.fill()

        # Compute X spacing
        num_points = len(self._values)
        x_step = chart_width / (num_points - 1) if num_points > 1 else 0

        # Start path
        cr.set_line_width(1.5)
        cr.set_line_join(1)  # Round joins
        cr.set_line_cap(1)   # Round caps
        cr.set_source_rgba(*self._color)

        # Draw line
        for i, value in enumerate(self._values):
            # Normalize value to chart height
            value_range = self._max_value - self._min_value
            if value_range > 0:
                normalized = (value - self._min_value) / value_range
            else:
                normalized = 0.5

            # Y coordinate (inverted, 0 at top)
            x = padding + i * x_step
            y = padding + chart_height * (1 - normalized)

            if i == 0:
                cr.move_to(x, y)
            else:
                cr.line_to(x, y)

        cr.stroke()

        # Optional: draw dots at each point for clarity
        if num_points <= 15:  # Only for small datasets
            cr.set_source_rgba(*self._color)
            for i, value in enumerate(self._values):
                value_range = self._max_value - self._min_value
                if value_range > 0:
                    normalized = (value - self._min_value) / value_range
                else:
                    normalized = 0.5

                x = padding + i * x_step
                y = padding + chart_height * (1 - normalized)

                cr.arc(x, y, 1.5, 0, 2 * 3.14159)
                cr.fill()

    def _parse_color(self, color_str: str) -> tuple[float, float, float, float]:
        """Parse hex color to RGBA tuple"""
        try:
            color_str = color_str.lstrip("#")

            if len(color_str) == 6:
                r = int(color_str[0:2], 16) / 255
                g = int(color_str[2:4], 16) / 255
                b = int(color_str[4:6], 16) / 255
                return (r, g, b, 0.9)

            return (0.21, 0.52, 0.89, 0.9)  # Fallback blue

        except ValueError:
            return (0.21, 0.52, 0.89, 0.9)  # Fallback blue

    def clear(self):
        """Clear all data"""
        self._values = []
        self.queue_draw()