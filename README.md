<div align="center">

# HyprWall

**Wallpaper Manager for Hyprland** — CLI & GUI

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![Hyprland](https://img.shields.io/badge/Hyprland-compatible-purple)](https://hyprland.org/)

</div>

---

## Features

- **Images & Videos** — PNG, JPG, WebP, MP4, WebM, MKV
- **CLI & GUI** — Command-line or modern GTK4/libadwaita interface  
- **Multi-Monitor** — Full Hyprland multi-monitor support
- **Smart Optimization** — Auto-encode videos for performance
- **Battery-Aware** — Automatic quality profiles (eco_strict/eco/balanced/quality)
- **Intelligent Caching** — Avoid redundant re-encoding
- **Performance Monitoring** — Optional lightweight CPU/RAM/GPU/temperature tracking
- **Clean & Predictable** — No bloat, just works

---

## Quick Start

### Installation

**Recommended workflow (Fedora):**

```bash
git clone https://github.com/TheOnlyChou/hyprwall.git
cd hyprwall

# Install system dependencies first
sudo dnf install mpvpaper mpv ffmpeg python3-psutil python3-gobject gtk4 libadwaita

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install CLI only
pip install -e .

# OR install with GUI (quotes needed for zsh)
pip install -e '.[gui]'
```

**Alternative (without venv):**

```bash
# CLI only
pip install -e .

# With GUI (quotes needed for zsh)
pip install -e '.[gui]'
```

**Important:** If you use a virtual environment, `python3-psutil` installed via `dnf` won't be available inside the venv. In that case, either:
- Install psutil in the venv: `pip install psutil` (after activating venv)
- OR use system-site-packages: `python3 -m venv --system-site-packages .venv`

**Verify Installation:**

```bash
# Check if all dependencies are properly installed
python3 check_dependencies.py
```

This script will verify that all required system commands and Python packages are available.

### System Dependencies

```bash
# Fedora (recommended: use system psutil for better compatibility)
sudo dnf install mpvpaper mpv ffmpeg python3-psutil python3-gobject gtk4 libadwaita

# Arch
sudo pacman -S mpvpaper mpv ffmpeg python-psutil python-gobject gtk4 libadwaita

# Ubuntu
sudo apt install mpvpaper mpv ffmpeg python3-psutil python3-gi gir1.2-gtk-4.0 gir1.2-adw-1
```

**Note:** `python3-psutil` is required for performance monitoring (CPU/RAM/GPU usage). If not installed, the performance widget will show "N/A" for all metrics.

---

## Usage

### CLI

```bash
# Set wallpaper (always applies to all monitors)
hyprwall set video.mp4

# With profile
hyprwall set video.mp4 --profile balanced

# Auto mode (battery-aware)
hyprwall set video.mp4 --auto-power

# Control
hyprwall status
hyprwall stop
hyprwall cache
hyprwall cache clear
```

### GUI

#### Installation

After installing HyprWall with GUI support, create a desktop entry for proper integration:

```bash
# Create desktop applications directory
mkdir -p ~/.local/share/applications

# Create desktop entry
cat > ~/.local/share/applications/hyprwall.desktop << 'EOF'
[Desktop Entry]
Type=Application
Name=HyprWall
Comment=Local Wallpaper Engine for Hyprland
Exec=hyprwall-gui
Icon=preferences-desktop-wallpaper
Terminal=false
StartupNotify=true
Categories=Utility;Settings;
EOF

# Update desktop database
update-desktop-database ~/.local/share/applications >/dev/null 2>&1 || true
```

#### Launch

HyprWall GUI is meant to be launched as a desktop application from your application menu.

**Note:** If you run `hyprwall-gui` from a terminal, you may see GTK theme warnings. These are normal and come from the GTK theme system, not from HyprWall. Use the desktop launcher for the best experience.

#### Features

- **Library & Now Playing views** — Clean navigation between wallpaper browser and live status
- **Integrated search** — Fast search bar in Library with real-time filtering (no pagination)
- **File chooser** — Select individual wallpapers (images or videos)
- **Folder browser** — Browse wallpaper collections with thumbnail gallery
- **Video thumbnails** — Automatic preview generation for video files
- **Pagination** — Gallery displays 15 items per page for smooth performance
- **Loading screen** — Professional spinner during library scanning
- **Single file preview** — Clear preview of individually selected files
- **Now Playing panel** — Real-time status showing currently active wallpapers with preview
- **Live monitor detection** — Shows all connected displays with resolutions
- **Mode selection** — Choose rendering mode (auto/fit/cover/stretch)
- **Profile selection** — Set optimization profile (off/eco/eco_strict/balanced/quality)
- **Codec & Encoder** — Full control over video encoding (h264/vp9/av1, auto/cpu/nvenc/vaapi)
- **Auto-power toggle** — Enable battery-aware automatic profile switching
- **Session persistence** — Remembers your last wallpaper configuration
- **Cache management** — View cache size and clear optimized files (videos + thumbnails)
- **Default library folder** — Automatically loads your wallpaper collection at startup

#### Usage

1. **Browse Library (Library tab):**
   - Click "Choose file..." to select a single wallpaper
   - OR click "Choose folder..." to browse a wallpaper library
   - The chosen folder becomes your default library (persisted)
   - **Gallery view** — Browse thumbnails with pagination (15 items per page)
   - **Search** — Type in the search bar to filter wallpapers by name
     - Switches to list view for better performance
     - Real-time filtering as you type
     - Shows match count (e.g., "12 / 245")
     - Click any result to see preview (thumbnail appears above list)
     - Best for large libraries (1000+ wallpapers)
   - Click any thumbnail or search result to select that wallpaper

2. **Configure options:**
   - **Mode:** How wallpaper fits the screen (auto/fit/cover/stretch)
   - **Profile:** Optimization level (off/eco/balanced/quality)
   - **Codec:** Video encoding format (h264/vp9/av1)
   - **Encoder:** Encoding backend (auto/cpu/nvenc/vaapi)
   - **Auto-power:** Enable battery-aware profile switching

3. **Apply wallpaper:**
   - Click "Start" to apply wallpaper to all monitors globally
   - Click "Stop" to remove wallpapers from all monitors

4. **Check status (Now Playing tab):**
   - Switch to "Now Playing" to see currently active wallpaper
   - View wallpaper preview (thumbnail for videos, full image for pictures)
   - See detailed info per monitor (file, mode, PID, resolution)
   - View session info (profile, codec, encoder, auto-power status)
   - Status refreshes automatically every 2 seconds

5. **Manage cache (Menu):**
   - Menu → Cache Size (shows statistics)
   - Menu → Clear Cache (removes optimized files)
   - Menu → Reset Default Folder (clears saved library path)

**Important:** Wallpapers always apply to all monitors (global-only mode). There is no per-monitor selection.

---

## Architecture

```
hyprwall/
├── core/       # Business logic (UI-agnostic)
│   ├── api.py          # Main API facade
│   ├── detect.py       # File detection
│   ├── hypr.py         # Hyprland interface
│   ├── optimize.py     # Video optimization
│   ├── runner.py       # Process management
│   └── ...
├── cli/        # Command-line interface
│   └── main.py
└── gui/        # GTK4/libadwaita GUI
    ├── app.py          # Application
    ├── window.py       # Main window
    ├── ui/             # GtkBuilder layouts
    └── style/          # CSS styles
```

**Design Principle:** The core never depends on UI. CLI and GUI both use the same `core.api`.

---

## Configuration

### File Locations

- **Config**: `~/.config/hyprwall/`
  - `gui_config.json` — GUI preferences (default library folder)
- **Cache**: `~/.cache/hyprwall/optimized/`
  - Video thumbnails for GUI gallery
  - Optimized video files per resolution/profile
- **State**: `~/.cache/hyprwall/state/`
  - `session.json` — Last wallpaper session
  - `state.json` — Running wallpaper processes

### GUI Configuration

The GUI automatically saves preferences:

- **Default library folder** — Last selected folder for "Choose folder..."
  - Saved in `~/.config/hyprwall/gui_config.json`
  - Auto-loads on startup for instant access
  - Fallback: `~/Pictures/wallpapers/.../LiveWallpapers` → `~/Pictures` → `~`

- **View mode** — Gallery or List view preference (preserved in session)

- **Pagination** — Automatically enabled for folders with >15 items
  - Page size: 15 items (optimal for performance)
  - Navigation: Prev/Next buttons + page indicator

### Optimization Profiles

| Profile | FPS | Quality | Battery Threshold |
|---------|-----|---------|-------------------|
| `eco_strict` | 18 | 30 CRF | ≤20% |
| `eco` | 24 | 28 CRF | ≤40% |
| `balanced` | 30 | 24 CRF | Default |
| `quality` | 30 | 20 CRF | AC power |

**Profile "off"** skips video optimization entirely (uses source file directly).

### Codec & Encoder Selection

**Codecs:**
- `h264` — MP4 format (default, best compatibility)
- `vp9` — WebM format (good compression)
- `av1` — Modern codec (requires hardware support)

**Encoders:**
- `auto` — Smart selection (hardware if available, CPU fallback)
- `cpu` — Software encoding (libx264/libvpx-vp9)
- `nvenc` — NVIDIA GPU acceleration (H.264 only)
- `vaapi` — AMD/Intel GPU acceleration (AV1 recommended)

---

## Development

### Project Structure

- **core/** — Business logic, no UI dependencies
- **cli/** — Command-line interface
- **gui/** — GTK4 graphical interface

### Adding Features

1. Add logic to `core/`
2. Expose via `core/api.py`
3. Use in `cli/` or `gui/`

### Running Tests

```bash
# Test the CLI
hyprwall status 

# Test the GUI
hyprwall-gui
```

---

## Troubleshooting

### GUI Issues

**Problem:** File chooser dialog opens in another workspace  
**Cause:** Hyprland windowrules may be needed  
**Solution:** Add to `~/.config/hypr/hyprland.conf`:
```
windowrulev2 = float, class:^(xdg-desktop-portal-gtk)$
windowrulev2 = center, class:^(xdg-desktop-portal-gtk)$
windowrulev2 = stayfocused, class:^(xdg-desktop-portal-gtk)$
```
Then: `hyprctl reload`

**Problem:** File chooser button does not respond  
**Solution:** Make sure you installed GUI dependencies:
```bash
sudo dnf install python3-gobject gtk4 libadwaita xdg-desktop-portal xdg-desktop-portal-gtk
pip install -e '.[gui]'
```
Then restart your Hyprland session.

**Problem:** No monitors detected  
**Solution:** Must run under Hyprland. Check with:
```bash
hyprctl monitors  # Should list your monitors
echo $HYPRLAND_INSTANCE_SIGNATURE  # Should have a value
```

**Problem:** GTK theme warnings on launch  
**Solution:** Use Adwaita theme:
```bash
GTK_THEME=Adwaita hyprwall-gui
```

### CLI Issues

**Problem:** `hyprwall: command not found`  
**Solution:**
```bash
pip install -e .
# OR run directly
python -m hyprwall.cli set video.mp4
```

**Problem:** Video optimization fails  
**Solution:** Install ffmpeg:
```bash
sudo dnf install ffmpeg  # Fedora
sudo pacman -S ffmpeg    # Arch
```

**Problem:** Performance widget shows "N/A" for CPU/RAM usage  
**Solution:** Install psutil:
```bash
# Option 1: System package (recommended on Fedora)
sudo dnf install python3-psutil  # Fedora
sudo pacman -S python-psutil     # Arch
sudo apt install python3-psutil  # Ubuntu

# Option 2: Via pip (if using virtual environment)
pip install psutil

# Then restart the GUI
hyprwall-gui
```

---

## Requirements

### Mandatory
- **Hyprland** — Wayland compositor
- **mpvpaper** — Wallpaper backend
- **mpv** — Media player
- **ffmpeg** — Video encoding
- **Python ≥ 3.10**

### Optional (GUI)
- **PyGObject** — Python GTK bindings
- **GTK4** — Toolkit
- **libadwaita** — Modern widgets

---

## License

MIT License - see [LICENSE](LICENSE) file

---

## Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing`)
5. Open Pull Request

---

## Acknowledgments

- Built on [mpvpaper](https://github.com/GhostNaN/mpvpaper)
- Designed for [Hyprland](https://hyprland.org/)
- Uses [GTK4](https://gtk.org/) and [libadwaita](https://gnome.pages.gitlab.gnome.org/libadwaita/)

---

<div align="center">

**Made with ❤️ for the Hyprland community**

[Report Bug](https://github.com/TheOnlyChou/hyprwall/issues) • [Request Feature](https://github.com/TheOnlyChou/hyprwall/issues)

</div>