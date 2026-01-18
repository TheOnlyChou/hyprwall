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
- **Battery-Aware** — Automatic quality profiles (eco/balanced/quality)
- **Intelligent Caching** — Avoid redundant re-encoding
- **Clean & Predictable** — No bloat, just works

---

## Quick Start

### Installation

```bash
git clone https://github.com/TheOnlyChou/hyprwall.git
cd hyprwall

# CLI only
pip install -e .

# With GUI (quotes needed for zsh)
pip install -e '.[gui]'
```

### System Dependencies

```bash
# Fedora
sudo dnf install mpvpaper mpv ffmpeg python3-gobject gtk4 libadwaita

# Arch
sudo pacman -S mpvpaper mpv ffmpeg python-gobject gtk4 libadwaita

# Ubuntu
sudo apt install mpvpaper mpv ffmpeg python3-gi gir1.2-gtk-4.0 gir1.2-adw-1
```

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

```bash
# Launch GUI
hyprwall-gui
```

**Features:**
- File chooser dialog for individual wallpapers
- Folder browser with library view for wallpaper collections
- Live monitor detection display
- Mode selection (auto/fit/cover/stretch)
- Profile selection (off/eco/balanced/quality)
- Auto-power toggle for battery-aware optimization
- Real-time status display

**Usage:**
1. Click "Choose file" to select a single wallpaper
2. OR click "Choose folder" to browse a wallpaper library
3. Select mode, profile, and auto-power options
4. Click "Start" to apply wallpaper to all monitors
5. Click "Stop" to remove wallpapers

**Note:** Wallpapers always apply to all monitors (global-only mode).
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

- **Config**: `~/.config/hyprwall/`
- **Cache**: `~/.cache/hyprwall/optimized/`
- **State**: `~/.cache/hyprwall/state/`

### Optimization Profiles

| Profile | FPS | Quality | Battery Threshold |
|---------|-----|---------|-------------------|
| `eco_strict` | 18 | 30 CRF | ≤20% |
| `eco` | 24 | 28 CRF | ≤40% |
| `balanced` | 30 | 24 CRF | Default |
| `quality` | 30 | 20 CRF | AC power |

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