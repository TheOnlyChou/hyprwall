"""Library controller.

Strict constraints (project-level):
- No user-facing behavior changes.
- No business logic changes.
- hyprwall.core is untouched.
- GUI only delegates.
- No renaming of GTK actions or signals.

This controller extracts all wallpaper library-related logic from HyprwallWindow:
- sync/async scan
- pagination
- search
- grid/list rendering
- media selection
- library preview (search preview only; not Now Playing)

The controller manipulates widgets through the provided `window` reference.
"""

from __future__ import annotations

from pathlib import Path

try:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Gtk, GLib, Pango
except (ImportError, ValueError) as e:  # pragma: no cover
    raise RuntimeError("GTK4 or libadwaita not available") from e


class LibraryController:
    def __init__(self, window, core, *, lazy_loading: bool = False):
        self.window = window
        self.core = core
        self.lazy_loading = lazy_loading

        # Library state (kept local to controller)
        self._library_items = []
        self._library_folder: Path | None = None

        # Pagination state
        self._all_items = []
        self._page_size = 15
        self._page_index = 0
        self._total_pages = 1

        # Search state
        self._all_search_items = []
        self._filtered_search_items = []
        self._search_loaded = False

        # Background scan state
        self._scan_cancelled = False

    # ---- Public API expected by prompt ----

    def load_folder(self, path: Path):
        self._load_library(path)

    def on_search_changed(self, entry):
        self._on_library_search_changed(entry)

    def on_item_selected(self, path: Path):
        # Selection is owned by the window for compatibility with the rest of the UI.
        self.window.selected_file = path
        self.window._update_selected_label()

    # ---- Delegated handlers (keep names on window side; these are called by wrappers) ----

    def _load_library(self, folder: Path):
        """Load media library - synchronous or lazy depending on flag."""
        # Cancel any ongoing scan
        self._scan_cancelled = True

        # Store folder
        self._library_folder = folder
        self._library_items = []

        # Changing library folder invalidates search cache (matches previous behavior
        # effectively, because search loads based on current folder and relies on _library_folder).
        self._all_search_items = []
        self._filtered_search_items = []
        self._search_loaded = False

        # KEEP library container visible to avoid layout jump
        if getattr(self.window, "library_container", None):
            self.window.library_container.set_visible(True)

        # Show loading page (spinner + message)
        if getattr(self.window, "library_outer_stack", None):
            self.window.library_outer_stack.set_visible_child_name("loading")

        # Freeze window size to prevent Wayland recentering
        self.window._freeze_window_size()

        if self.lazy_loading:
            # === LAZY MODE (background thread) ===
            self._scan_cancelled = False
            import threading

            thread = threading.Thread(
                target=self._scan_library_thread,
                args=(folder,),
                daemon=True,
            )
            thread.start()
        else:
            # === SYNCHRONOUS MODE (baseline for debugging) ===
            items = self.core.list_library(folder, recursive=True)

            # Store all items for pagination
            self._all_items = items
            self._page_index = 0

            # Calculate total pages
            import math

            self._total_pages = max(1, math.ceil(len(self._all_items) / self._page_size))

            # Render first page
            self._render_current_page()

            # Show content page (gallery/list)
            if getattr(self.window, "library_outer_stack", None):
                self.window.library_outer_stack.set_visible_child_name("content")

            # Unfreeze window
            self.window._unfreeze_window_size()

            # Update status
            self.window._refresh_status()

    def _scan_library_thread(self, folder: Path):
        """Background thread for scanning library (calls core API only)."""
        try:
            all_items = []

            # Iterate over batches from core API and accumulate
            for batch in self.core.iter_library(folder, recursive=True, batch_size=50):
                if self._scan_cancelled:
                    return
                all_items.extend(batch)

            if not self._scan_cancelled:
                GLib.idle_add(self._on_library_scan_complete_with_items, all_items)

        except Exception as e:
            GLib.idle_add(self.window._unfreeze_window_size)
            GLib.idle_add(self.window._show_error, f"Library scan error: {e}")
            GLib.idle_add(self.window._refresh_status)

    def _on_library_scan_complete_with_items(self, items):
        """Called when library scan completes - setup pagination and render first page."""
        self._all_items = items
        self._page_index = 0

        import math

        self._total_pages = max(1, math.ceil(len(self._all_items) / self._page_size))

        self._render_current_page()

        if getattr(self.window, "library_outer_stack", None):
            self.window.library_outer_stack.set_visible_child_name("content")

        self.window._unfreeze_window_size()
        self.window._refresh_status()
        return False

    def _render_current_page(self):
        """Render only the current page of items in gallery view (pagination)."""
        if getattr(self.window, "library_grid", None):
            self.window.library_grid.remove_all()

        if not self._all_items:
            self._show_no_media_message()
            if getattr(self.window, "pagination_bar", None):
                self.window.pagination_bar.set_visible(False)
            return

        start_idx = self._page_index * self._page_size
        end_idx = min(start_idx + self._page_size, len(self._all_items))
        page_items = self._all_items[start_idx:end_idx]

        # Store current page items for compatibility
        self._library_items = page_items

        self._render_grid_view(page_items)
        self._update_pagination_ui()

    def _update_pagination_ui(self):
        if not getattr(self.window, "pagination_bar", None):
            return

        if self._total_pages > 1:
            self.window.pagination_bar.set_visible(True)
        else:
            self.window.pagination_bar.set_visible(False)
            return

        if getattr(self.window, "page_label", None):
            current_page = self._page_index + 1
            self.window.page_label.set_label(f"Page {current_page} / {self._total_pages}")

        if getattr(self.window, "page_prev", None):
            self.window.page_prev.set_sensitive(self._page_index > 0)

        if getattr(self.window, "page_next", None):
            self.window.page_next.set_sensitive(self._page_index < self._total_pages - 1)

    def _on_page_prev(self, button):
        if self._page_index > 0:
            self._page_index -= 1
            self._render_current_page()

    def _on_page_next(self, button):
        if self._page_index < self._total_pages - 1:
            self._page_index += 1
            self._render_current_page()

    # ----- Search -----

    def _on_library_search_changed(self, entry):
        query = entry.get_text().strip().lower()

        if not query:
            self.window.library_stack.set_visible_child_name("gallery")
            if getattr(self.window, "library_search_results_label", None):
                self.window.library_search_results_label.set_label("")

            if getattr(self.window, "library_search_preview_container", None):
                self.window.library_search_preview_container.set_visible(False)

            if getattr(self.window, "pagination_bar", None):
                if self._total_pages > 1:
                    self.window.pagination_bar.set_visible(True)
                else:
                    self.window.pagination_bar.set_visible(False)
            return

        if not self._search_loaded:
            self._load_all_for_search()

        self._filtered_search_items = [
            item for item in self._all_search_items if query in item.path.name.lower()
        ]

        if getattr(self.window, "library_search_results_label", None):
            count = len(self._filtered_search_items)
            total = len(self._all_search_items)
            self.window.library_search_results_label.set_label(f"{count} / {total}")

        self._render_library_search_results(self._filtered_search_items)
        self.window.library_stack.set_visible_child_name("search_results")

        if getattr(self.window, "pagination_bar", None):
            self.window.pagination_bar.set_visible(False)

    def _load_all_for_search(self):
        folder = self._library_folder if self._library_folder else self.core.get_default_library_dir()

        if not folder or not folder.exists():
            self._all_search_items = []
            self._search_loaded = True
            return

        try:
            all_items = self.core.list_library(folder, recursive=True)
            self._all_search_items = all_items
            self._search_loaded = True
        except Exception:
            self._all_search_items = []
            self._search_loaded = True

    def _render_library_search_results(self, items):
        if not getattr(self.window, "library_search_list", None):
            return

        while True:
            row = self.window.library_search_list.get_row_at_index(0)
            if row is None:
                break
            self.window.library_search_list.remove(row)

        for item in items:
            content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            content.set_margin_top(6)
            content.set_margin_bottom(6)
            content.set_margin_start(12)
            content.set_margin_end(12)

            icon_name = (
                "video-x-generic-symbolic" if item.kind == "video" else "image-x-generic-symbolic"
            )
            icon = Gtk.Image.new_from_icon_name(icon_name)
            content.append(icon)

            label = Gtk.Label(label=item.path.name)
            label.set_xalign(0)
            label.set_hexpand(True)
            label.set_ellipsize(Pango.EllipsizeMode.END)
            content.append(label)

            row = Gtk.ListBoxRow()
            row.set_child(content)

            row.media_path = item.path
            row.media_item = item

            self.window.library_search_list.append(row)

    def _on_library_search_activated(self, listbox, row):
        if not hasattr(row, "media_path"):
            return

        media_path = row.media_path
        media_item = getattr(row, "media_item", None)

        self.on_item_selected(media_path)
        self._show_library_search_preview(media_path, media_item)

    def _show_library_search_preview(self, file_path: Path, media_item=None):
        if not getattr(self.window, "library_search_preview_container", None):
            return
        if not getattr(self.window, "library_search_preview_box", None):
            return

        self.window.library_search_preview_container.set_visible(True)

        child = self.window.library_search_preview_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.window.library_search_preview_box.remove(child)
            child = next_child

        thumb_width = 320
        thumb_height = 180

        # Reuse existing helpers from window module to avoid behavioral changes.
        make_picture = self.window.__class__.__module__  # not used; kept for clarity
        from hyprwall.gui.utils.images import _make_picture_from_file
        from hyprwall.gui.utils.thumbnails import _ensure_video_thumb

        if media_item and media_item.kind == "image":
            thumb = _make_picture_from_file(file_path, thumb_width, thumb_height, cover=True)
            if thumb:
                thumb.add_css_class("wallpaper-thumb")
                self.window.library_search_preview_box.append(thumb)
            else:
                icon_box = self._create_fallback_icon(
                    "image-x-generic-symbolic", thumb_width, thumb_height
                )
                self.window.library_search_preview_box.append(icon_box)
        elif media_item and media_item.kind == "video":
            thumb_path = _ensure_video_thumb(file_path, thumb_width, thumb_height)
            if thumb_path:
                thumb = _make_picture_from_file(thumb_path, thumb_width, thumb_height, cover=True)
                if thumb:
                    thumb.add_css_class("wallpaper-thumb")
                    self.window.library_search_preview_box.append(thumb)
                else:
                    icon_box = self._create_fallback_icon(
                        "video-x-generic-symbolic", thumb_width, thumb_height
                    )
                    self.window.library_search_preview_box.append(icon_box)
            else:
                icon_box = self._create_fallback_icon(
                    "video-x-generic-symbolic", thumb_width, thumb_height
                )
                self.window.library_search_preview_box.append(icon_box)
        else:
            icon_box = self._create_fallback_icon("document-open-symbolic", thumb_width, thumb_height)
            self.window.library_search_preview_box.append(icon_box)

        label = Gtk.Label(label=file_path.name)
        label.set_xalign(0.5)
        label.set_wrap(True)
        label.set_max_width_chars(40)
        label.add_css_class("wallpaper-title")
        self.window.library_search_preview_box.append(label)

    # ----- Grid Rendering / Selection -----

    def _show_no_media_message(self):
        if getattr(self.window, "library_grid", None):
            label_grid = Gtk.Label(label="No media files found")
            label_grid.add_css_class("dim-label")
            label_grid.set_margin_top(24)
            label_grid.set_margin_bottom(24)
            child = Gtk.FlowBoxChild()
            child.set_child(label_grid)
            child.set_can_focus(False)
            self.window.library_grid.append(child)

    def _render_grid_view(self, items):
        self.window.library_grid.remove_all()

        if not items:
            label = Gtk.Label(label="No media files found")
            label.add_css_class("dim-label")
            label.set_margin_top(24)
            label.set_margin_bottom(24)

            child = Gtk.FlowBoxChild()
            child.set_child(label)
            child.set_can_focus(False)
            self.window.library_grid.append(child)
            return

        for item in items:
            card = self._create_gallery_card(item)
            child = Gtk.FlowBoxChild()
            child.set_child(card)
            child.media_path = item.path
            self.window.library_grid.append(child)

    def _create_gallery_card(self, item):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        card.add_css_class("wallpaper-card")

        thumb_width = 260
        thumb_height = 146

        from hyprwall.gui.utils.images import _make_picture_from_file
        from hyprwall.gui.utils.thumbnails import _ensure_video_thumb

        if item.kind == "image":
            thumb = _make_picture_from_file(item.path, thumb_width, thumb_height, cover=True)
            if thumb:
                thumb.set_size_request(thumb_width, thumb_height)
                thumb.add_css_class("wallpaper-thumb")
                card.append(thumb)
            else:
                icon_box = self._create_fallback_icon(
                    "image-x-generic-symbolic", thumb_width, thumb_height
                )
                card.append(icon_box)
        else:
            thumb_path = _ensure_video_thumb(item.path, thumb_width, thumb_height)
            if thumb_path:
                thumb = _make_picture_from_file(thumb_path, thumb_width, thumb_height, cover=True)
                if thumb:
                    thumb.set_size_request(thumb_width, thumb_height)
                    thumb.add_css_class("wallpaper-thumb")
                    card.append(thumb)
                else:
                    icon_box = self._create_fallback_icon(
                        "video-x-generic-symbolic", thumb_width, thumb_height
                    )
                    card.append(icon_box)
            else:
                icon_box = self._create_fallback_icon(
                    "video-x-generic-symbolic", thumb_width, thumb_height
                )
                card.append(icon_box)

        label = Gtk.Label(label=item.path.name)
        label.set_xalign(0.5)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        label.set_max_width_chars(20)
        label.add_css_class("wallpaper-title")
        card.append(label)

        return card

    def _create_fallback_icon(self, icon_name: str, width: int, height: int) -> Gtk.Box:
        icon_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        icon_box.set_valign(Gtk.Align.CENTER)
        icon_box.set_halign(Gtk.Align.CENTER)
        icon_box.set_size_request(width, height)
        icon_box.add_css_class("wallpaper-thumb")

        icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.set_pixel_size(48)
        icon_box.append(icon)

        return icon_box

    def _on_library_grid_activated(self, flow_box, child):
        media_path = getattr(child, "media_path", None)
        if media_path:
            self.on_item_selected(media_path)

    # ----- Startup / Reset default folder -----

    def _auto_load_default_library(self):
        """Auto-load the default library directory at startup (calls core API only)."""
        try:
            default_dir = self.core.get_default_library_dir()
            if default_dir and default_dir.exists() and default_dir.is_dir():
                self._load_library(default_dir)
        except Exception:
            # Silently fail - user can manually choose folder
            pass

    def _on_reset_default_folder(self, action, param):
        """Reset the default library folder to intelligent fallback"""
        try:
            # Call core API - no business logic here
            success = self.core.reset_default_library_dir()

            if success:
                # Get the new fallback directory
                fallback_dir = self.core.get_default_library_dir()

                message = (
                    f"Default folder reset successfully!\n\n"
                    f"Using fallback: {fallback_dir}"
                )

                from gi.repository import Adw, GLib
                dialog = Adw.MessageDialog.new(self.window, "Success", message)
                dialog.add_response("ok", "OK")

                # Connect to dialog response to reload library after it closes
                def on_dialog_response(dlg, response):
                    if response == "ok" and fallback_dir and fallback_dir.exists():
                        # Defer library reload to avoid blocking the dialog
                        GLib.idle_add(self._load_library, fallback_dir)

                dialog.connect("response", on_dialog_response)
                dialog.present()
            else:
                self.window._show_error("Failed to reset default folder")
        except Exception as e:
            self.window._show_error(f"Failed to reset default folder: {e}")

    # ----- Legacy / compat methods (for progressive loading, if still referenced) -----

    def _append_library_batch(self, batch):
        """Append a batch of items to both views (called from idle_add) - LEGACY"""
        # Remove loading placeholder on first batch
        if not self._library_items:
            self._clear_loading_placeholder()

        self._library_items.extend(batch)

        # Append to list view (if exists)
        for item in batch:
            self._append_to_list_view(item)

        # Append to grid view
        for item in batch:
            self._append_to_grid_view(item)

        return False  # Don't repeat

    def _on_library_scan_complete(self):
        """Called when library scan completes - LEGACY"""
        # Clear loading placeholder
        self._clear_loading_placeholder()

        # If no items found, show message
        if not self._library_items:
            self._show_no_media_message()

        return False  # Don't repeat

    def _show_loading_placeholder(self):
        """Show 'Loading...' placeholder in gallery view - LEGACY"""
        # Clear grid first
        if getattr(self.window, 'library_grid', None):
            self.window.library_grid.remove_all()

        from gi.repository import Gtk

        # Grid view placeholder - centered to avoid layout distortion
        label_grid = Gtk.Label(label="Loading wallpapers...")
        label_grid.add_css_class("dim-label")
        label_grid.set_halign(Gtk.Align.CENTER)
        label_grid.set_valign(Gtk.Align.CENTER)
        label_grid.set_hexpand(True)
        label_grid.set_vexpand(True)

        child = Gtk.FlowBoxChild()
        child.set_child(label_grid)
        child.set_can_focus(False)
        child.set_name("loading-placeholder")  # Mark for removal
        self.window.library_grid.append(child)

    def _clear_loading_placeholder(self):
        """Remove loading placeholder from gallery view - LEGACY"""
        # Clear grid view placeholder (FlowBox) - GTK4 iteration
        if getattr(self.window, 'library_grid', None):
            from gi.repository import Gtk
            child = self.window.library_grid.get_first_child()
            while child is not None:
                next_child = child.get_next_sibling()
                if isinstance(child, Gtk.FlowBoxChild) and child.get_name() == "loading-placeholder":
                    self.window.library_grid.remove(child)
                    break  # Only one placeholder
                child = next_child

    def _append_to_list_view(self, item):
        """Append a single item to list view (for progressive loading) - LEGACY"""
        # Check if library_list exists (only in programmatic UI fallback)
        if not getattr(self.window, 'library_list', None):
            return

        from gi.repository import Gtk, Pango

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

        # Store path as Python attribute
        row.media_path = item.path

        self.window.library_list.append(row)

    def _append_to_grid_view(self, item):
        """Append a single item to grid view (for progressive loading) - LEGACY"""
        if not getattr(self.window, 'library_grid', None):
            return

        from gi.repository import Gtk

        card = self._create_gallery_card(item)

        child = Gtk.FlowBoxChild()
        child.set_child(card)

        # Store path as Python attribute
        child.media_path = item.path

        self.window.library_grid.append(child)