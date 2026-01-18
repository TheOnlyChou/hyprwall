"""
Main window for hyprwall GTK4 application.
"""

from pathlib import Path
from gi.repository import Gtk, Adw, Gio, Gdk, Pango

try:
    import gi
    gi.require_version('Gtk', '4.0')
    gi.require_version('Adw', '1')
    gi.require_version('Gdk', '4.0')
    from gi.repository import Gtk, Adw, Gio, Gdk
except (ImportError, ValueError) as e:
    raise RuntimeError("GTK4 or libadwaita not available") from e

from hyprwall.core.api import HyprwallCore


class HyprwallWindow(Adw.ApplicationWindow):
    """
    Main window for the hyprwall GTK4 application.
    This window allows users to select wallpapers and control
    the wallpaper playback globally (all monitors).
    It uses GtkBuilder to load the UI from a .ui file if available,
    otherwise it builds the UI programmatically.
    """

    def __init__(self, application, core: HyprwallCore):
        super().__init__(application=application)

        self.core = core

        # Try to load UI from .ui file
        ui_path = Path(__file__).parent / "ui" / "window.ui"
        if ui_path.exists():
            self._load_from_ui(ui_path)
        else:
            self._build_ui_programmatically()

        # Load initial status
        self._refresh_status()

    def _load_from_ui(self, ui_path: Path):
        """Load the UI from a .ui file using GtkBuilder"""
        builder = Gtk.Builder()
        builder.add_from_file(str(ui_path))

        # Get widgets
        self.start_button = builder.get_object("start_button")
        self.stop_button = builder.get_object("stop_button")
        self.monitors_label = builder.get_object("monitors_label")
        self.file_chooser_button = builder.get_object("file_chooser_button")
        self.folder_chooser_button = builder.get_object("folder_chooser_button")
        self.selected_label = builder.get_object("selected_label")
        self.library_scroll = builder.get_object("library_scroll")
        self.library_list = builder.get_object("library_list")
        self.status_label = builder.get_object("status_label")
        self.mode_dropdown = builder.get_object("mode_dropdown")
        self.profile_dropdown = builder.get_object("profile_dropdown")
        self.auto_power_switch = builder.get_object("auto_power_switch")

        # Get content
        content = builder.get_object("window_content")
        if content:
            # Create header and toolbar view
            header = Adw.HeaderBar()

            # Menu
            menu_button = Gtk.MenuButton()
            menu_button.set_icon_name("open-menu-symbolic")
            menu = Gio.Menu()
            menu.append("Preferences", "app.preferences")
            menu.append("About", "app.about")
            menu.append("Quit", "app.quit")
            menu_button.set_menu_model(menu)
            header.pack_end(menu_button)

            # Toolbar view
            toolbar_view = Adw.ToolbarView()
            toolbar_view.add_top_bar(header)
            toolbar_view.set_content(content)

            self.set_content(toolbar_view)

        # Connect signals
        if self.start_button:
            self.start_button.connect("clicked", self._on_start_clicked)
        if self.stop_button:
            self.stop_button.connect("clicked", self._on_stop_clicked)
        if self.file_chooser_button:
            self.file_chooser_button.connect("clicked", self._on_choose_file)
        if self.folder_chooser_button:
            self.folder_chooser_button.connect("clicked", self._on_choose_folder)
        if self.library_list:
            self.library_list.connect("row-activated", self._on_library_item_activated)

        # Update monitors display
        if self.monitors_label:
            self._update_monitors_display()

        self.selected_file = None
        self.set_default_size(600, 400)
        self.set_title("HyprWall")

    def _build_ui_programmatically(self):
        """Build the UI in Python (fallback if no .ui file)"""
        # Header bar
        header = Adw.HeaderBar()

        # Menu button
        menu_button = Gtk.MenuButton()
        menu_button.set_icon_name("open-menu-symbolic")
        menu = Gio.Menu()
        menu.append("Preferences", "app.preferences")
        menu.append("About", "app.about")
        menu.append("Quit", "app.quit")
        menu_button.set_menu_model(menu)
        header.pack_end(menu_button)

        # Main content
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content.set_margin_top(12)
        content.set_margin_bottom(12)
        content.set_margin_start(12)
        content.set_margin_end(12)

        # Title
        title = Gtk.Label(label="HyprWall Manager")
        title.add_css_class("title-1")
        content.append(title)

        # Monitors display (read-only)
        monitors_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        monitors_header = Gtk.Label(label="Detected monitors:")
        monitors_header.set_xalign(0)
        monitors_header.add_css_class("dim-label")
        monitors_box.append(monitors_header)

        self.monitors_label = Gtk.Label(label="Loading...")
        self.monitors_label.set_xalign(0)
        self.monitors_label.set_wrap(True)
        self.monitors_label.set_hexpand(True)
        monitors_box.append(self.monitors_label)
        content.append(monitors_box)

        # File chooser
        file_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        file_label = Gtk.Label(label="Wallpaper:")
        file_box.append(file_label)

        self.file_chooser_button = Gtk.Button(label="Choose file...")
        self.file_chooser_button.set_hexpand(True)
        self.file_chooser_button.connect("clicked", self._on_choose_file)
        file_box.append(self.file_chooser_button)

        self.folder_chooser_button = Gtk.Button(label="Choose folder...")
        self.folder_chooser_button.set_hexpand(True)
        self.folder_chooser_button.connect("clicked", self._on_choose_folder)
        file_box.append(self.folder_chooser_button)

        content.append(file_box)

        # Selected file label
        self.selected_label = Gtk.Label(label="Selected: (none)")
        self.selected_label.set_xalign(0)
        self.selected_label.set_wrap(True)
        self.selected_label.add_css_class("dim-label")
        content.append(self.selected_label)

        # Library list (initially hidden)
        self.library_scroll = Gtk.ScrolledWindow()
        self.library_scroll.set_vexpand(True)
        self.library_scroll.set_max_content_height(200)
        self.library_scroll.set_propagate_natural_height(True)
        self.library_scroll.set_visible(False)

        self.library_list = Gtk.ListBox()
        self.library_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.library_list.add_css_class("boxed-list")
        self.library_list.connect("row-activated", self._on_library_item_activated)
        self.library_scroll.set_child(self.library_list)

        content.append(self.library_scroll)

        # Mode, Profile, and Auto-power controls
        controls_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)

        # Mode dropdown
        mode_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        mode_label = Gtk.Label(label="Mode:")
        mode_label.set_width_chars(12)
        mode_label.set_xalign(0)
        mode_box.append(mode_label)

        mode_list = Gtk.StringList()
        mode_list.append("auto")
        mode_list.append("fit")
        mode_list.append("cover")
        mode_list.append("stretch")
        self.mode_dropdown = Gtk.DropDown(model=mode_list)
        self.mode_dropdown.set_hexpand(True)
        mode_box.append(self.mode_dropdown)
        controls_box.append(mode_box)

        # Profile dropdown
        profile_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        profile_label = Gtk.Label(label="Profile:")
        profile_label.set_width_chars(12)
        profile_label.set_xalign(0)
        profile_box.append(profile_label)

        profile_list = Gtk.StringList()
        profile_list.append("off")
        profile_list.append("eco")
        profile_list.append("balanced")
        profile_list.append("quality")
        self.profile_dropdown = Gtk.DropDown(model=profile_list)
        self.profile_dropdown.set_selected(2)  # Default to "balanced"
        self.profile_dropdown.set_hexpand(True)
        profile_box.append(self.profile_dropdown)
        controls_box.append(profile_box)

        # Auto-power switch
        auto_power_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        auto_power_label = Gtk.Label(label="Auto-power:")
        auto_power_label.set_width_chars(12)
        auto_power_label.set_xalign(0)
        auto_power_box.append(auto_power_label)

        self.auto_power_switch = Gtk.Switch()
        self.auto_power_switch.set_valign(Gtk.Align.CENTER)
        auto_power_box.append(self.auto_power_switch)

        auto_power_hint = Gtk.Label(label="(adaptive profile based on power status)")
        auto_power_hint.set_hexpand(True)
        auto_power_hint.set_xalign(0)
        auto_power_hint.add_css_class("dim-label")
        auto_power_hint.add_css_class("caption")
        auto_power_box.append(auto_power_hint)

        controls_box.append(auto_power_box)
        content.append(controls_box)

        # Control buttons
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        button_box.set_halign(Gtk.Align.CENTER)

        self.start_button = Gtk.Button(label="Start")
        self.start_button.add_css_class("suggested-action")
        self.start_button.connect("clicked", self._on_start_clicked)
        button_box.append(self.start_button)

        self.stop_button = Gtk.Button(label="Stop")
        self.stop_button.add_css_class("destructive-action")
        self.stop_button.connect("clicked", self._on_stop_clicked)
        button_box.append(self.stop_button)

        content.append(button_box)

        # Status
        self.status_label = Gtk.Label(label="No wallpaper running")
        self.status_label.add_css_class("dim-label")
        content.append(self.status_label)

        # Toolbar view to combine header + content
        toolbar_view = Adw.ToolbarView()
        toolbar_view.add_top_bar(header)
        toolbar_view.set_content(content)

        self.set_content(toolbar_view)
        self.set_default_size(600, 400)
        self.set_title("HyprWall")

        self.selected_file = None
        self._update_monitors_display()

    def _update_monitors_display(self):
        """Update the read-only monitor display"""
        try:
            monitors = self.core.list_monitors()
            if monitors:
                monitor_info = [f"{m.name} {m.width}x{m.height}" for m in monitors]
                self.monitors_label.set_label(", ".join(monitor_info))
            else:
                self.monitors_label.set_label("No monitors detected (are you on Hyprland?)")
        except Exception as e:
            self.monitors_label.set_label(f"Error detecting monitors: {e}")

    def _on_choose_file(self, button):
        self.present()

        filter_media = Gtk.FileFilter()
        filter_media.set_name("Media files")
        filter_media.add_mime_type("image/*")
        filter_media.add_mime_type("video/*")

        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(filter_media)

        dialog = Gtk.FileDialog()
        dialog.set_title("Choose Wallpaper")
        dialog.set_filters(filters)
        dialog.set_default_filter(filter_media)
        dialog.set_modal(True)

        try:
            pictures = Path.home() / "Pictures"
            folder_path = pictures if pictures.exists() else Path.home()
            dialog.set_initial_folder(Gio.File.new_for_path(str(folder_path)))
        except Exception:
            pass

        self._file_dialog = dialog
        button.set_sensitive(False)

        try:
            dialog.open(self, None, self._on_file_chosen)
        except Exception as e:
            button.set_sensitive(True)
            self._show_error(f"Failed to open file dialog: {e!r}")

    def _on_file_chosen(self, dialog, result):
        self.file_chooser_button.set_sensitive(True)
        self._file_dialog = None

        try:
            file = dialog.open_finish(result)
            if file:
                self.selected_file = Path(file.get_path())
                self._update_selected_label()
        except Exception:
            pass

    def _on_choose_folder(self, button):
        """Open folder chooser dialog"""
        self.present()

        dialog = Gtk.FileDialog()
        dialog.set_title("Choose Wallpaper Folder")
        dialog.set_modal(True)

        try:
            pictures = Path.home() / "Pictures"
            folder_path = pictures if pictures.exists() else Path.home()
            dialog.set_initial_folder(Gio.File.new_for_path(str(folder_path)))
        except Exception:
            pass

        self._folder_dialog = dialog
        button.set_sensitive(False)

        try:
            dialog.select_folder(self, None, self._on_folder_chosen)
        except Exception as e:
            button.set_sensitive(True)
            self._show_error(f"Failed to open folder dialog: {e!r}")

    def _on_folder_chosen(self, dialog, result):
        """Handle folder selection"""
        self.folder_chooser_button.set_sensitive(True)
        self._folder_dialog = None

        try:
            folder = dialog.select_folder_finish(result)
            if folder:
                folder_path = Path(folder.get_path())
                self._load_library(folder_path)
        except Exception as e:
            self._show_error(f"Folder selection error: {e!r}")

    def _load_library(self, folder: Path):
        """Load media library from folder using core API"""
        # Clear existing items
        while True:
            row = self.library_list.get_row_at_index(0)
            if row is None:
                break
            self.library_list.remove(row)

        # Get media items from core
        media_items = self.core.list_library(folder, recursive=True)

        if not media_items:
            # Show "no media found" message - create proper ListBoxRow
            label = Gtk.Label(label="No media files found")
            label.add_css_class("dim-label")

            row = Gtk.ListBoxRow()
            row.set_child(label)
            row.set_activatable(False)
            row.set_selectable(False)
            self.library_list.append(row)
            self.library_scroll.set_visible(True)
            return

        # Populate list with proper ListBoxRow
        for item in media_items:
            # Create content box
            content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            content.set_margin_top(6)
            content.set_margin_bottom(6)
            content.set_margin_start(12)
            content.set_margin_end(12)

            # Icon based on kind
            icon_name = "video-x-generic-symbolic" if item.kind == "video" else "image-x-generic-symbolic"
            icon = Gtk.Image.new_from_icon_name(icon_name)
            content.append(icon)

            # Filename
            label = Gtk.Label(label=item.path.name)
            label.set_xalign(0)
            label.set_hexpand(True)
            label.set_ellipsize(Pango.EllipsizeMode.END)
            content.append(label)

            # Create ListBoxRow and set content
            row = Gtk.ListBoxRow()
            row.set_child(content)

            # Store path as data on the ROW (not on content)
            row.media_path = item.path

            self.library_list.append(row)

        self.library_scroll.set_visible(True)

    def _on_library_item_activated(self, list_box, row):
        """Handle library item selection"""
        media_path = getattr(row, "media_path", None)
        if media_path:
            self.selected_file = media_path
            self._update_selected_label()

    def _update_selected_label(self):
        """Update the selected file label"""
        if self.selected_file:
            self.selected_label.set_label(f"Selected: {self.selected_file.name}")
        else:
            self.selected_label.set_label("Selected: (none)")

    def _on_start_clicked(self, button):
        """Start wallpaper on all monitors (global-only)"""
        if not hasattr(self, 'selected_file') or self.selected_file is None:
            self._show_error("Please choose a file first")
            return

        # Read UI values
        mode_idx = self.mode_dropdown.get_selected()
        modes = ["auto", "fit", "cover", "stretch"]
        mode = modes[mode_idx] if mode_idx < len(modes) else "auto"

        profile_idx = self.profile_dropdown.get_selected()
        profiles = ["off", "eco", "balanced", "quality"]
        profile = profiles[profile_idx] if profile_idx < len(profiles) else "balanced"

        auto_power = self.auto_power_switch.get_active()

        # Call core API - all business logic is in core
        try:
            success = self.core.set_wallpaper(
                source=self.selected_file,
                mode=mode,
                profile=profile,
                auto_power=auto_power,
            )

            if success:
                self._refresh_status()
            else:
                self._show_error("Failed to start wallpaper")
        except Exception as e:
            self._show_error(f"Error starting wallpaper: {e}")

    def _on_stop_clicked(self, button):
        """Stop wallpaper on all monitors (global-only)"""
        self.core.stop_wallpaper()
        self._refresh_status()

    def _refresh_status(self):
        """Update the status display with global wallpaper state"""
        status = self.core.get_status()

        if status.running and status.monitors:
            monitor_details = []
            for name, mon_status in status.monitors.items():
                file_name = Path(mon_status.file).name if mon_status.file else "unknown"
                mode = mon_status.mode or "auto"
                monitor_details.append(f"  • {name}: {file_name} ({mode})")

            text = "Status: Running (global)\n" + "\n".join(monitor_details)
            self.status_label.set_label(text)
        else:
            self.status_label.set_label("Status: Stopped")

    def _show_error(self, message: str):
        """Display an error message"""
        dialog = Adw.MessageDialog.new(self, "Error", message)
        dialog.add_response("ok", "OK")
        dialog.present()