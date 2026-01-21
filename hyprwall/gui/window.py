"""
Main window for hyprwall GTK4 application.
"""

from pathlib import Path

try:
    import gi
    gi.require_version('Gtk', '4.0')
    gi.require_version('Adw', '1')
    gi.require_version('Gdk', '4.0')
    gi.require_version('GdkPixbuf', '2.0')
    from gi.repository import Gtk, Adw, Gio, Gdk, Pango, GLib, GdkPixbuf
except (ImportError, ValueError) as e:
    raise RuntimeError("GTK4 or libadwaita not available") from e

from hyprwall.core.api import HyprwallCore
from hyprwall.gui.utils.thumbnails import _ensure_video_thumb
from hyprwall.gui.utils.images import _make_picture_from_file
from hyprwall.gui.controllers.library_controller import LibraryController
# Feature flag: Set to False to use synchronous loading (baseline for debugging layout issues)
LAZY_LIBRARY_LOADING = False



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

        # Library controller (GUI delegates; no core calls from window for library)
        self.library_controller = LibraryController(self, self.core, lazy_loading=LAZY_LIBRARY_LOADING)

        # Auto-load default library directory at startup (after controller creation)
        self._auto_load_default_library()

        # Load initial status
        self._refresh_status()

        # Initialize Now Playing view (in case wallpaper is already running)
        if hasattr(self, '_refresh_now_playing'):
            GLib.idle_add(self._refresh_now_playing)

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

        # Main view stack and switcher
        self.main_view_stack = builder.get_object("main_view_stack")
        self.view_switcher = builder.get_object("view_switcher")

        # Library views
        self.library_page = builder.get_object("library_page")
        self.library_container = builder.get_object("library_container")
        self.library_outer_stack = builder.get_object("library_outer_stack")
        self.library_stack = builder.get_object("library_stack")
        self.library_grid = builder.get_object("library_grid")
        self.library_scroll_grid = builder.get_object("library_scroll_grid")
        self.library_search_entry = builder.get_object("library_search_entry")
        self.library_search_results_label = builder.get_object("library_search_results_label")
        self.library_search_list = builder.get_object("library_search_list")
        self.library_scroll_search = builder.get_object("library_scroll_search")
        self.library_search_preview_container = builder.get_object("library_search_preview_container")
        self.library_search_preview_box = builder.get_object("library_search_preview_box")
        self.single_file_preview_box = builder.get_object("single_file_preview_box")
        self.single_file_view_stack = builder.get_object("single_file_view_stack")
        self.single_file_list = builder.get_object("single_file_list")

        # Now Playing views
        self.now_playing_container = builder.get_object("now_playing_container")
        self.now_playing_preview_container = builder.get_object("now_playing_preview_container")
        self.now_playing_info_list = builder.get_object("now_playing_info_list")
        self.now_playing_empty_state = builder.get_object("now_playing_empty_state")

        # Performance monitoring
        self.perf_toggle = builder.get_object("perf_toggle")
        self.perf_widget_container = builder.get_object("perf_widget_container")
        self.perf_widget = None  # Will be created on demand

        # Pagination
        self.pagination_bar = builder.get_object("pagination_bar")
        self.page_prev = builder.get_object("page_prev")
        self.page_next = builder.get_object("page_next")
        self.page_label = builder.get_object("page_label")


        # Controls
        self.mode_dropdown = builder.get_object("mode_dropdown")
        self.profile_dropdown = builder.get_object("profile_dropdown")
        self.codec_dropdown = builder.get_object("codec_dropdown")
        self.encoder_dropdown = builder.get_object("encoder_dropdown")
        self.auto_power_switch = builder.get_object("auto_power_switch")

        # Library state
        self._library_items = []
        self._library_folder = None

        # Pagination state
        self._all_items = []
        self._page_size = 15
        self._page_index = 0
        self._total_pages = 1

        # Search state
        self._all_search_items = []  # All items loaded for search (no pagination)
        self._filtered_search_items = []  # Filtered results based on search query
        self._search_loaded = False  # Whether we've loaded all items for search

        # Now Playing refresh timer ID
        self._now_playing_timer = None

        # Get content
        content = builder.get_object("window_content")
        if content:
            # Create header and toolbar view
            header = Adw.HeaderBar()

            # Menu
            menu_button = Gtk.MenuButton()
            menu_button.set_icon_name("open-menu-symbolic")
            menu = Gio.Menu()

            # Cache section
            cache_menu = Gio.Menu()
            cache_menu.append("Cache Size", "win.cache-size")
            cache_menu.append("Clear Cache", "win.cache-clear")
            cache_menu.append("Reset Default Folder", "win.reset-default-folder")
            menu.append_section("Cache", cache_menu)

            # App actions
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
        if self.library_grid:
            self.library_grid.connect("child-activated", self._on_library_grid_activated)

        # Library search
        if hasattr(self, 'library_search_entry') and self.library_search_entry:
            self.library_search_entry.connect("search-changed", self._on_library_search_changed)
        if hasattr(self, 'library_search_list') and self.library_search_list:
            self.library_search_list.connect("row-activated", self._on_library_search_activated)

        # Main view stack - refresh Now Playing when switched to
        if self.main_view_stack:
            self.main_view_stack.connect("notify::visible-child-name", self._on_main_view_changed)

        # Performance toggle
        if hasattr(self, 'perf_toggle') and self.perf_toggle:
            self.perf_toggle.connect("notify::active", self._on_perf_toggle)
            # If toggle is active by default, initialize the widget
            if self.perf_toggle.get_active():
                self._on_perf_toggle(self.perf_toggle, None)

        # Pagination
        if hasattr(self, 'page_prev') and self.page_prev:
            self.page_prev.connect("clicked", self._on_page_prev)
        if hasattr(self, 'page_next') and self.page_next:
            self.page_next.connect("clicked", self._on_page_next)

        # Update monitors display
        if self.monitors_label:
            self._update_monitors_display()

        # Add window actions for cache management
        cache_size_action = Gio.SimpleAction.new("cache-size", None)
        cache_size_action.connect("activate", self._on_cache_size)
        self.add_action(cache_size_action)

        cache_clear_action = Gio.SimpleAction.new("cache-clear", None)
        cache_clear_action.connect("activate", self._on_cache_clear)
        self.add_action(cache_clear_action)

        # Add action to reset default library folder
        reset_folder_action = Gio.SimpleAction.new("reset-default-folder", None)
        reset_folder_action.connect("activate", self._on_reset_default_folder)
        self.add_action(reset_folder_action)

        self.selected_file = None
        self.set_default_size(800, 600)  # Larger default to accommodate library
        self.set_title("HyprWall")

        # Prevent window from recentering when content changes
        # Set size request to avoid resize jumps
        if self.library_container:
            self.library_container.set_size_request(-1, 300)  # Minimum height for library

        # Note: Auto-load default library is now called in __init__ after controller creation

    def _freeze_window_size(self):
        """Freeze window size to prevent repositioning during content changes"""
        width = self.get_width()
        height = self.get_height()

        # Only freeze if we have valid dimensions
        if width > 0 and height > 0:
            self.set_size_request(width, height)

    def _unfreeze_window_size(self):
        """Unfreeze window size to allow normal resizing"""
        self.set_size_request(-1, -1)

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
        self.library_list.connect("row-activated", self._on_library_list_activated)
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

                # Show single file preview mode
                self._show_single_file_preview(self.selected_file)
        except Exception:
            pass

    def _show_single_file_preview(self, file_path: Path):
        """Show preview of a single selected file in both gallery and list views"""
        if not hasattr(self, 'single_file_preview_box') or not self.single_file_preview_box:
            return

        # Clear previous gallery preview
        child = self.single_file_preview_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.single_file_preview_box.remove(child)
            child = next_child

        # Clear previous list
        if hasattr(self, 'single_file_list') and self.single_file_list:
            child = self.single_file_list.get_first_child()
            while child:
                next_child = child.get_next_sibling()
                self.single_file_list.remove(child)
                child = next_child

        # Determine if it's an image or video
        from hyprwall.core import detect
        is_video = detect.is_video(file_path)

        # Create thumbnail
        thumb_width = 320
        thumb_height = 180

        # === GALLERY VIEW ===
        if is_video:
            # Try to generate video thumbnail
            thumb_path = _ensure_video_thumb(file_path, thumb_width, thumb_height)
            if thumb_path:
                thumb = _make_picture_from_file(thumb_path, thumb_width, thumb_height, cover=True)
            else:
                thumb = None

            if not thumb:
                # Fallback: icon
                icon_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                icon_box.set_valign(Gtk.Align.CENTER)
                icon_box.set_halign(Gtk.Align.CENTER)
                icon_box.set_size_request(thumb_width, thumb_height)

                icon = Gtk.Image.new_from_icon_name("video-x-generic-symbolic")
                icon.set_pixel_size(64)
                icon_box.append(icon)
                self.single_file_preview_box.append(icon_box)
            else:
                thumb.set_size_request(thumb_width, thumb_height)
                thumb.add_css_class("wallpaper-thumb")
                self.single_file_preview_box.append(thumb)
        else:
            # Image thumbnail
            thumb = _make_picture_from_file(file_path, thumb_width, thumb_height, cover=True)
            if thumb:
                thumb.set_size_request(thumb_width, thumb_height)
                thumb.add_css_class("wallpaper-thumb")
                self.single_file_preview_box.append(thumb)
            else:
                # Fallback: icon
                icon_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                icon_box.set_valign(Gtk.Align.CENTER)
                icon_box.set_halign(Gtk.Align.CENTER)
                icon_box.set_size_request(thumb_width, thumb_height)

                icon = Gtk.Image.new_from_icon_name("image-x-generic-symbolic")
                icon.set_pixel_size(64)
                icon_box.append(icon)
                self.single_file_preview_box.append(icon_box)

        # Filename label (gallery)
        filename_label = Gtk.Label(label=file_path.name)
        filename_label.set_wrap(True)
        filename_label.set_max_width_chars(40)
        filename_label.add_css_class("title-4")
        self.single_file_preview_box.append(filename_label)

        # File type label (gallery)
        type_label = Gtk.Label(label=f"Type: {'Video' if is_video else 'Image'}")
        type_label.add_css_class("dim-label")
        self.single_file_preview_box.append(type_label)

        # === LIST VIEW ===
        if hasattr(self, 'single_file_list') and self.single_file_list:
            # Create list row with file info
            content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            content.set_margin_top(12)
            content.set_margin_bottom(12)
            content.set_margin_start(12)
            content.set_margin_end(12)

            # Icon
            icon_name = "video-x-generic-symbolic" if is_video else "image-x-generic-symbolic"
            icon = Gtk.Image.new_from_icon_name(icon_name)
            icon.set_pixel_size(32)
            content.append(icon)

            # File info box
            info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            info_box.set_hexpand(True)

            # Filename
            name_label = Gtk.Label(label=file_path.name)
            name_label.set_xalign(0)
            name_label.set_wrap(True)
            name_label.add_css_class("heading")
            info_box.append(name_label)

            # Path + type
            details_label = Gtk.Label(label=f"{file_path.parent} • {'Video' if is_video else 'Image'}")
            details_label.set_xalign(0)
            details_label.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
            details_label.add_css_class("dim-label")
            details_label.add_css_class("caption")
            info_box.append(details_label)

            content.append(info_box)

            # Create row
            row = Gtk.ListBoxRow()
            row.set_child(content)
            row.set_activatable(False)
            row.set_selectable(False)
            self.single_file_list.append(row)

        # Hide pagination bar (not relevant for single file)
        if hasattr(self, 'pagination_bar') and self.pagination_bar:
            self.pagination_bar.set_visible(False)

        # Switch to single file view (respects current gallery/list mode)
        if hasattr(self, 'library_outer_stack') and self.library_outer_stack:
            self.library_outer_stack.set_visible_child_name("single_file")

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
        """Handle folder selection and set as default"""
        self.folder_chooser_button.set_sensitive(True)
        self._folder_dialog = None

        try:
            folder = dialog.select_folder_finish(result)
            if folder:
                folder_path = Path(folder.get_path())

                # Save as default library directory (calls core API)
                if not self.core.set_default_library_dir(folder_path):
                    self._show_error(f"Failed to set default folder: {folder_path}")
                    return

                # Clear selected_file (switching to folder mode)
                self.selected_file = None
                self._update_selected_label()

                # Load library from this folder (switches to library view)
                self._load_library(folder_path)
        except GLib.Error:
            # User cancelled the dialog - this is normal, don't show error
            pass
        except Exception as e:
            self._show_error(f"Folder selection error: {e!r}")

    # ===== Library (delegated) =====

    def _load_library(self, folder: Path):
        return self.library_controller._load_library(folder)

    def _scan_library_thread(self, folder: Path):
        return self.library_controller._scan_library_thread(folder)

    def _append_library_batch(self, batch):
        return self.library_controller._append_library_batch(batch)

    def _on_library_scan_complete_with_items(self, items):
        return self.library_controller._on_library_scan_complete_with_items(items)

    def _render_current_page(self):
        return self.library_controller._render_current_page()

    def _update_pagination_ui(self):
        return self.library_controller._update_pagination_ui()

    def _on_page_prev(self, button):
        return self.library_controller._on_page_prev(button)

    def _on_page_next(self, button):
        return self.library_controller._on_page_next(button)

    def _on_library_search_changed(self, entry):
        return self.library_controller._on_library_search_changed(entry)

    def _load_all_for_search(self):
        return self.library_controller._load_all_for_search()

    def _render_library_search_results(self, items):
        return self.library_controller._render_library_search_results(items)

    def _on_library_search_activated(self, listbox, row):
        return self.library_controller._on_library_search_activated(listbox, row)

    def _show_library_search_preview(self, file_path: Path, media_item=None):
        return self.library_controller._show_library_search_preview(file_path, media_item)

    def _on_library_scan_complete(self):
        return self.library_controller._on_library_scan_complete()

    def _show_loading_placeholder(self):
        return self.library_controller._show_loading_placeholder()

    def _clear_loading_placeholder(self):
        return self.library_controller._clear_loading_placeholder()

    def _show_no_media_message(self):
        return self.library_controller._show_no_media_message()

    def _render_grid_view(self, items):
        return self.library_controller._render_grid_view(items)

    def _append_to_list_view(self, item):
        return self.library_controller._append_to_list_view(item)

    def _append_to_grid_view(self, item):
        return self.library_controller._append_to_grid_view(item)

    def _create_gallery_card(self, item):
        return self.library_controller._create_gallery_card(item)

    def _create_fallback_icon(self, icon_name: str, width: int, height: int) -> Gtk.Box:
        return self.library_controller._create_fallback_icon(icon_name, width, height)

    def _on_library_grid_activated(self, flow_box, child):
        return self.library_controller._on_library_grid_activated(flow_box, child)

    def _auto_load_default_library(self):
        """Auto-load default library directory at startup (safe guard against early calls)"""
        if not hasattr(self, "library_controller") or self.library_controller is None:
            return
        return self.library_controller._auto_load_default_library()

    # ===== End Library (delegated) =====

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

        codec_idx = self.codec_dropdown.get_selected()
        codecs = ["h264", "vp9", "av1"]
        codec = codecs[codec_idx] if codec_idx < len(codecs) else "h264"

        encoder_idx = self.encoder_dropdown.get_selected()
        encoders = ["auto", "cpu", "vaapi", "nvenc"]
        encoder = encoders[encoder_idx] if encoder_idx < len(encoders) else "auto"

        auto_power = self.auto_power_switch.get_active()

        # Call core API - all business logic is in core
        try:
            success = self.core.set_wallpaper(
                source=self.selected_file,
                mode=mode,
                profile=profile,
                codec=codec,
                encoder=encoder,
                auto_power=auto_power,
            )

            if success:
                self._refresh_status()
                # Update performance monitoring
                self._update_perf_monitoring()
                # Refresh Now Playing if visible
                if hasattr(self, 'main_view_stack') and self.main_view_stack:
                    if self.main_view_stack.get_visible_child_name() == "now_playing":
                        self._refresh_now_playing()
            else:
                self._show_error("Failed to start wallpaper")
        except Exception as e:
            self._show_error(f"Error starting wallpaper: {e}")

    def _on_stop_clicked(self, button):
        """Stop wallpaper on all monitors (global-only)"""
        self.core.stop_wallpaper()
        self._refresh_status()
        # Stop performance monitoring
        self._update_perf_monitoring()
        # Refresh Now Playing if visible
        if hasattr(self, 'main_view_stack') and self.main_view_stack:
            if self.main_view_stack.get_visible_child_name() == "now_playing":
                self._refresh_now_playing()

    def _refresh_status(self):
        """Refresh Now Playing view if visible (status info moved to Now Playing tab)"""
        # Refresh Now Playing if visible
        if hasattr(self, 'main_view_stack') and self.main_view_stack:
            if self.main_view_stack.get_visible_child_name() == "now_playing":
                self._refresh_now_playing()

    def _show_error(self, message: str):
        """Display an error message"""
        dialog = Adw.MessageDialog.new(self, "Error", message)
        dialog.add_response("ok", "OK")
        dialog.present()

    def _on_cache_size(self, action, param):
        """Display cache size statistics (calls core API only)"""
        try:
            # Call core API - no business logic here
            cache_info = self.core.cache_size()

            # Format display message
            message = (
                f"Cache Directory: {cache_info['path']}\n\n"
                f"Files: {cache_info['files']}\n"
                f"Directories: {cache_info['dirs']}\n"
                f"Total Size: {cache_info['size_mb']} MB ({cache_info['size_bytes']} bytes)"
            )

            dialog = Adw.MessageDialog.new(self, "Cache Statistics", message)
            dialog.add_response("ok", "OK")
            dialog.present()
        except Exception as e:
            self._show_error(f"Failed to get cache size: {e}")

    def _on_cache_clear(self, action, param):
        """Clear the optimization cache with confirmation"""
        # First show confirmation dialog
        def on_response(dialog, response):
            if response == "clear":
                self._do_clear_cache()

        dialog = Adw.MessageDialog.new(
            self,
            "Clear Cache?",
            "This will delete all optimized video files. Original files will not be affected."
        )
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("clear", "Clear Cache")
        dialog.set_response_appearance("clear", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")
        dialog.connect("response", on_response)
        dialog.present()

    def _do_clear_cache(self):
        """Actually clear the cache (calls core API only)"""
        try:
            # Call core API - no business logic here
            result = self.core.clear_cache()

            if result.get("success"):
                files = result.get("files_deleted", 0)
                bytes_freed = result.get("bytes_freed", 0)
                mb_freed = round(bytes_freed / (1024 * 1024), 2)

                message = (
                    f"Cache cleared successfully!\n\n"
                    f"Files deleted: {files}\n"
                    f"Space freed: {mb_freed} MB"
                )

                dialog = Adw.MessageDialog.new(self, "Success", message)
                dialog.add_response("ok", "OK")
                dialog.present()
            else:
                error_msg = result.get("error", "Unknown error")
                self._show_error(f"Failed to clear cache: {error_msg}")
        except Exception as e:
            self._show_error(f"Failed to clear cache: {e}")

    def _on_reset_default_folder(self, action, param):
        """Reset the default library folder to intelligent fallback"""
        return self.library_controller._on_reset_default_folder(action, param)

    # ===== NOW PLAYING VIEW =====

    def _on_main_view_changed(self, stack, param):
        """Called when main view stack changes (Library / Now Playing / Search)"""
        visible_child = stack.get_visible_child_name()

        if visible_child == "now_playing":
            # Refresh Now Playing view when switched to
            self._refresh_now_playing()

            # Start auto-refresh timer (every 2 seconds)
            if self._now_playing_timer:
                GLib.source_remove(self._now_playing_timer)
            self._now_playing_timer = GLib.timeout_add_seconds(2, self._refresh_now_playing_timer)
        else:
            # Stop timer when leaving Now Playing view
            if self._now_playing_timer:
                GLib.source_remove(self._now_playing_timer)
                self._now_playing_timer = None


    def _refresh_now_playing_timer(self):
        """Timer callback for auto-refreshing Now Playing view"""
        if self.main_view_stack and self.main_view_stack.get_visible_child_name() == "now_playing":
            self._refresh_now_playing()
            return True  # Continue timer
        return False  # Stop timer

    def _refresh_now_playing(self):
        """Refresh the Now Playing view with current status (calls core API only)"""
        # Check if widgets are properly initialized
        if not hasattr(self, 'now_playing_container') or not self.now_playing_container:
            return False

        try:
            # Get status from core
            status = self.core.get_status()

            if not status.running or not status.monitors:
                self._show_now_playing_empty()
            else:
                self._show_now_playing_content(status)

            # Update performance monitoring if enabled
            self._update_perf_monitoring()

        except Exception as e:
            self._show_now_playing_empty()
            return False

    def _show_now_playing_empty(self):
        """Show empty state (no wallpaper running)"""
        if not self.now_playing_empty_state:
            return

        # Hide preview and info
        if self.now_playing_preview_container:
            # Clear preview
            child = self.now_playing_preview_container.get_first_child()
            while child:
                next_child = child.get_next_sibling()
                self.now_playing_preview_container.remove(child)
                child = next_child

        if self.now_playing_info_list:
            # Clear info list
            while True:
                row = self.now_playing_info_list.get_row_at_index(0)
                if row is None:
                    break
                self.now_playing_info_list.remove(row)

        # Show empty state
        self.now_playing_empty_state.set_visible(True)

    def _show_now_playing_content(self, status):
        """Show Now Playing content with current wallpaper status"""
        if not self.now_playing_container:
            return

        # Hide empty state
        if self.now_playing_empty_state:
            self.now_playing_empty_state.set_visible(False)

        # Load session for additional info (profile, codec, encoder)
        sess = self.core.load_session()

        # Get first monitor to show preview
        first_monitor = next(iter(status.monitors.values()), None)

        # === PREVIEW ===
        if self.now_playing_preview_container and first_monitor and first_monitor.file:
            # Clear existing preview
            child = self.now_playing_preview_container.get_first_child()
            while child:
                next_child = child.get_next_sibling()
                self.now_playing_preview_container.remove(child)
                child = next_child

            file_path = Path(first_monitor.file)
            if file_path.exists():
                # Try to show preview (image or video thumbnail)
                from hyprwall.core import detect
                is_video = detect.is_video(file_path)

                if is_video:
                    # Try video thumbnail
                    thumb_path = _ensure_video_thumb(file_path, 320, 180)
                    if thumb_path:
                        picture = _make_picture_from_file(thumb_path, 320, 180, cover=True)
                        if picture:
                            picture.set_size_request(320, 180)
                            picture.add_css_class("wallpaper-thumb")
                            self.now_playing_preview_container.append(picture)
                    else:
                        # Fallback: video icon
                        icon = Gtk.Image.new_from_icon_name("video-x-generic-symbolic")
                        icon.set_pixel_size(64)
                        icon.add_css_class("dim-label")
                        self.now_playing_preview_container.append(icon)
                else:
                    # Image preview
                    picture = _make_picture_from_file(file_path, 400, 225, cover=True)
                    if picture:
                        picture.set_size_request(400, 225)
                        picture.add_css_class("wallpaper-thumb")
                        self.now_playing_preview_container.append(picture)

                # Filename label
                filename_label = Gtk.Label(label=file_path.name)
                filename_label.set_wrap(True)
                filename_label.set_max_width_chars(50)
                filename_label.add_css_class("title-3")
                self.now_playing_preview_container.append(filename_label)

        # === INFO LIST ===
        if self.now_playing_info_list:
            # Clear existing info
            while True:
                row = self.now_playing_info_list.get_row_at_index(0)
                if row is None:
                    break
                self.now_playing_info_list.remove(row)

            # Running status
            self._add_now_playing_info_row("Status", "Running" if status.running else "Stopped")

            # Monitor-specific info
            monitors = self.core.list_monitors()
            monitor_map = {m.name: m for m in monitors}

            for mon_name, mon_status in status.monitors.items():
                # Section separator
                separator_row = Gtk.ListBoxRow()
                separator_label = Gtk.Label(label=f"Monitor: {mon_name}")
                separator_label.set_xalign(0)
                separator_label.set_margin_top(8)
                separator_label.set_margin_bottom(4)
                separator_label.set_margin_start(12)
                separator_label.set_margin_end(12)
                separator_label.add_css_class("heading")
                separator_row.set_child(separator_label)
                separator_row.set_activatable(False)
                separator_row.set_selectable(False)
                self.now_playing_info_list.append(separator_row)

                # Resolution (if available)
                if mon_name in monitor_map:
                    mon = monitor_map[mon_name]
                    self._add_now_playing_info_row("Resolution", f"{mon.width}x{mon.height}")

                # File
                if mon_status.file:
                    file_basename = Path(mon_status.file).name
                    self._add_now_playing_info_row("File", file_basename)

                # Mode
                self._add_now_playing_info_row("Mode", mon_status.mode or "auto")

                # PID
                if mon_status.pid:
                    self._add_now_playing_info_row("PID", str(mon_status.pid))

            # Global info from session
            if sess:
                separator_row = Gtk.ListBoxRow()
                separator_label = Gtk.Label(label="Session Info")
                separator_label.set_xalign(0)
                separator_label.set_margin_top(8)
                separator_label.set_margin_bottom(4)
                separator_label.set_margin_start(12)
                separator_label.set_margin_end(12)
                separator_label.add_css_class("heading")
                separator_row.set_child(separator_label)
                separator_row.set_activatable(False)
                separator_row.set_selectable(False)
                self.now_playing_info_list.append(separator_row)

                # Profile
                profile = sess.last_profile if sess.last_profile else "unknown"
                self._add_now_playing_info_row("Profile", profile)

                # Codec
                if sess.codec:
                    self._add_now_playing_info_row("Codec", sess.codec)

                # Encoder
                if sess.encoder:
                    self._add_now_playing_info_row("Encoder", sess.encoder)

                # Auto-power
                auto_power_text = "Yes" if sess.auto_power else "No"
                self._add_now_playing_info_row("Auto-power", auto_power_text)

    def _add_now_playing_info_row(self, label: str, value: str):
        """Add a key-value row to the Now Playing info list"""
        if not self.now_playing_info_list:
            return

        row = Gtk.ListBoxRow()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(12)
        box.set_margin_end(12)

        # Label (key)
        key_label = Gtk.Label(label=label + ":")
        key_label.set_xalign(0)
        key_label.set_width_chars(15)
        key_label.add_css_class("dim-label")
        box.append(key_label)

        # Value
        value_label = Gtk.Label(label=value)
        value_label.set_xalign(0)
        value_label.set_hexpand(True)
        value_label.set_wrap(True)
        value_label.set_selectable(True)
        box.append(value_label)

        row.set_child(box)
        row.set_activatable(False)
        row.set_selectable(False)
        self.now_playing_info_list.append(row)

    # ===== PERFORMANCE MONITORING =====

    def _on_perf_toggle(self, switch, param):
        """Toggle performance widget visibility and monitoring"""
        active = switch.get_active()

        if active:
            # Create widget if not exists
            if self.perf_widget is None:
                self._create_perf_widget()

            # Show widget
            if self.perf_widget:
                self.perf_widget.set_visible(True)

                # Start monitoring current wallpaper
                self._update_perf_monitoring()
        else:
            # Hide and stop monitoring
            if self.perf_widget:
                self.perf_widget.set_visible(False)
                self.perf_widget.set_pid(None)

    def _create_perf_widget(self):
        """Create the performance widget on demand"""
        try:
            from hyprwall.gui.widgets.perf_panel import PerformancePanel

            self.perf_widget = PerformancePanel()
            self.perf_widget.set_visible(False)  # Hidden initially

            # Add to container
            if hasattr(self, 'perf_widget_container') and self.perf_widget_container:
                self.perf_widget_container.append(self.perf_widget)

        except ImportError as e:
            # GTK or perf module not available
            self._show_error(f"Performance monitoring not available: {e}")
            self.perf_widget = None

            # Disable toggle
            if hasattr(self, 'perf_toggle') and self.perf_toggle:
                self.perf_toggle.set_active(False)
                self.perf_toggle.set_sensitive(False)

    def _update_perf_monitoring(self):
        """Update performance monitoring with current wallpaper PID"""
        if not self.perf_widget or not self.perf_widget.get_visible():
            return

        try:
            # Get status from core
            status = self.core.get_status()

            if status.running and status.monitors:
                # Get PID from first monitor (mpvpaper process)
                first_monitor_status = next(iter(status.monitors.values()))
                pid = first_monitor_status.pid

                # Start monitoring (FPS and Power removed)
                self.perf_widget.set_pid(pid)
            else:
                # No wallpaper running
                self.perf_widget.set_pid(None)

        except Exception:
            # Silently fail
            self.perf_widget.set_pid(None)