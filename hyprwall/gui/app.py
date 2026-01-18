"""
Main application for GTK4/libadwaita
"""

import sys
from pathlib import Path

try:
    import gi
    gi.require_version('Gtk', '4.0')
    gi.require_version('Adw', '1')
    gi.require_version('Gdk', '4.0')
    from gi.repository import Gtk, Adw, Gio, Gdk
except (ImportError, ValueError) as e:
    print(f"Error: GTK4 or libadwaita not available: {e}", file=sys.stderr)
    print("Install: python-gobject gtk4 libadwaita", file=sys.stderr)
    sys.exit(1)

from hyprwall.core.api import get_core

try:
    from hyprwall.gui.window import HyprwallWindow
except RuntimeError as e:
    print(f"Error: {e}", file=sys.stderr)
    print("Install: python-gobject gtk4 libadwaita", file=sys.stderr)
    sys.exit(1)

class HyprwallApplication(Adw.Application):
    """
    Main application for GTK4/libadwaita

    Used to manage:
    - Application lifecycle
    - Resource loading (CSS, .ui)
    - Main window creation
    """

    def __init__(self):
        super().__init__(
            application_id='com.github.theonlychou.hyprwall',
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS
        )

        self.core = get_core()
        self._window = None

    def do_startup(self):
        """Called once at application startup"""
        Adw.Application.do_startup(self)

        # Load custom CSS
        self._load_css()

        # Setup global actions
        self._setup_actions()

    def do_activate(self):
        """Called when the application is activated (launched)"""
        if self._window:
            self._window.present()
            return

        # Create and show the main window
        self._window = HyprwallWindow(application=self, core=self.core)
        self._window.present()

    def _load_css(self):
        """Load custom CSS styles for the application"""
        css_path = Path(__file__).parent / "style" / "style.css"

        if not css_path.exists():
            # CSS file not found; skip loading
            return

        css_provider = Gtk.CssProvider()
        css_provider.load_from_path(str(css_path))

        Gtk.StyleContext.add_provider_for_display(
            display=Gdk.Display.get_default(),
            provider=css_provider,
            priority=Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _setup_actions(self):
        """Setup global application actions (About, Preferences, Quit)"""
        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *_: self.quit())
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<Ctrl>Q"])

        # Action: About
        about_action = Gio.SimpleAction.new("about", None)
        about_action.connect("activate", self._on_about)
        self.add_action(about_action)

        # Action: Preferences
        prefs_action = Gio.SimpleAction.new("preferences", None)
        prefs_action.connect("activate", self._on_preferences)
        self.add_action(prefs_action)
        self.set_accels_for_action("app.preferences", ["<Ctrl>comma"])

    def _on_about(self, action, param):
        """Display the About dialog"""
        about = Adw.AboutWindow(
            transient_for=self._window,
            application_name="HyprWall",
            application_icon="video-display-symbolic",
            developer_name="TheOnlyChou",
            version="0.1.0",
            website="https://github.com/TheOnlyChou/hyprwall",
            issue_url="https://github.com/TheOnlyChou/hyprwall/issues",
            license_type=Gtk.License.MIT_X11,
            developers=["TheOnlyChou"],
            copyright="© 2026 TheOnlyChou",
        )
        about.present()

    def _on_preferences(self, action, param):
        """Display the Preferences dialog"""
        # TODO: Implement preferences dialog
        if self._window:
            dialog = Adw.MessageDialog.new(
                self._window,
                "Preferences",
                "Preferences dialog not yet implemented"
            )
            dialog.add_response("ok", "OK")
            dialog.present()

def main():
    """Entry point for the HyprWall application"""
    app = HyprwallApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())