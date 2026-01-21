# Performance Module - Integration Guide

## Overview

The performance module provides lightweight, non-intrusive monitoring of wallpaper processes.

## Features

- **CPU Usage** — Process + children aggregation (mpvpaper → mpv)
- **RAM Usage** — RSS memory in MiB
- **GPU Usage** — NVIDIA/AMD support (Intel placeholder)
- **Temperatures** — CPU and GPU via hwmon
- **Smoothing** — Rolling average to avoid visual spikes
- **Fail-safe** — Returns None for unavailable metrics, never crashes

## Backend Usage

```python
from hyprwall.perf.monitor import WallpaperPerfMonitor

# Initialize monitor
monitor = WallpaperPerfMonitor()

# Get metrics for a wallpaper PID
metrics = monitor.get_metrics(pid=12345)

# Access values (all Optional[float])
print(f"CPU: {metrics.cpu_percent}%")
print(f"RAM: {metrics.ram_mib} MiB")
print(f"GPU: {metrics.gpu_percent}%")
print(f"CPU Temp: {metrics.cpu_temp}°C")
print(f"GPU Temp: {metrics.gpu_temp}°C")

# Clear history when switching wallpapers
monitor.clear_history()
```

## GTK Widget Usage

### Basic Widget (Label-based)

```python
from hyprwall.perf.widget import PerformanceWidget

# Create widget
perf_widget = PerformanceWidget()

# Add to a container
container.append(perf_widget)

# Start monitoring a wallpaper PID
perf_widget.set_pid(12345)

# Stop monitoring
perf_widget.set_pid(None)
```

### Enhanced Panel (Circular Gauges + Sparklines)

```python
from hyprwall.gui.widgets.perf_panel import PerformancePanel

# Create enhanced panel
perf_panel = PerformancePanel()

# Add to a container
container.append(perf_panel)

# Start monitoring (with optional mpv PID for FPS)
perf_panel.set_pid(
    pid=12345,          # mpvpaper PID
    mpv_pid=12346       # mpv child PID (optional, for FPS)
)

# Stop monitoring
perf_panel.set_pid(None)
```

**Features of Enhanced Panel:**
- Circular progress gauges for CPU/RAM/GPU
- Historical sparklines (30 seconds of data)
- Optional FPS monitoring from mpv IPC
- Optional power consumption (Watts) via RAPL
- Graceful degradation (shows N/A for unavailable metrics)

## Integration in Now Playing View

### Step 1: Add to window.py initialization

```python
# In HyprwallWindow.__init__ or _load_from_ui

# Option 1: Basic widget (label-based)
from hyprwall.perf.widget import PerformanceWidget
self.perf_widget = PerformanceWidget()

# Option 2: Enhanced panel (circular gauges + sparklines)
from hyprwall.gui.widgets.perf_panel import PerformancePanel
self.perf_panel = PerformancePanel()

# Set initially hidden
self.perf_panel.set_visible(False)

# Add to now_playing_container
if self.now_playing_container:
    self.now_playing_container.append(self.perf_panel)
```

### Step 2: Add toggle in UI (window.ui)

```xml
<!-- In Now Playing controls -->
<child>
  <object class="GtkBox">
    <property name="orientation">horizontal</property>
    <property name="spacing">6</property>
    
    <child>
      <object class="GtkLabel">
        <property name="label">Show Performance</property>
      </object>
    </child>
    
    <child>
      <object class="GtkSwitch" id="perf_toggle">
        <property name="valign">center</property>
      </object>
    </child>
  </object>
</child>
```

### Step 3: Connect toggle signal

```python
# In _load_from_ui
self.perf_toggle = builder.get_object("perf_toggle")
if self.perf_toggle:
    self.perf_toggle.connect("notify::active", self._on_perf_toggle)
```

### Step 4: Handle toggle

```python
def _on_perf_toggle(self, switch, param):
    """Toggle performance widget visibility"""
    active = switch.get_active()
    
    # Use perf_panel if enhanced, otherwise perf_widget
    widget = getattr(self, 'perf_panel', None) or getattr(self, 'perf_widget', None)
    
    if widget:
        widget.set_visible(active)
        
        if active:
            # Get PID from current status
            status = self.core.get_status()
            if status.running and status.monitors:
                # Get first monitor's PID
                first_monitor = next(iter(status.monitors.values()))
                pid = first_monitor.pid
                
                # For enhanced panel, try to find mpv child PID
                if isinstance(widget, PerformancePanel):
                    mpv_pid = self._find_mpv_child_pid(pid)
                    widget.set_pid(pid, mpv_pid=mpv_pid)
                else:
                    widget.set_pid(pid)
        else:
            widget.set_pid(None)

def _find_mpv_child_pid(self, parent_pid: int) -> Optional[int]:
    """Find mpv child process PID (for FPS monitoring)"""
    try:
        import psutil
        parent = psutil.Process(parent_pid)
        for child in parent.children(recursive=False):
            if 'mpv' in child.name().lower():
                return child.pid
    except Exception:
        pass
    return None
```

### Step 5: Update on wallpaper change

```python
def _refresh_now_playing(self):
    """Refresh the Now Playing view with current status"""
    # ...existing code...
    
    # Update performance widget if visible
    widget = getattr(self, 'perf_panel', None) or getattr(self, 'perf_widget', None)
    
    if widget and widget.get_visible():
        status = self.core.get_status()
        if status.running and status.monitors:
            first_monitor = next(iter(status.monitors.values()))
            pid = first_monitor.pid
            
            # Enhanced panel needs mpv PID for FPS
            if isinstance(widget, PerformancePanel):
                mpv_pid = self._find_mpv_child_pid(pid)
                widget.set_pid(pid, mpv_pid=mpv_pid)
            else:
                widget.set_pid(pid)
        else:
            widget.set_pid(None)
```

## Dependencies

### Required
- `psutil>=5.9.0` — For CPU/RAM monitoring
  - **Automatically installed** with HyprWall (in dependencies)
  - If missing, install manually: `pip install psutil`

### Optional (graceful degradation)
- `nvidia-smi` — For NVIDIA GPU monitoring
- `/sys/class/drm` — For AMD GPU monitoring
- `/sys/class/hwmon` — For temperature sensors

## Performance Impact

- **Sampling rate**: Max 1/second (configurable)
- **CPU overhead**: ~0.1% (psutil process tree scan)
- **Memory overhead**: ~2-3 MiB (Python + psutil)
- **No background threads**: Uses GLib timer (GTK main loop)

## Configuration

The monitor can be configured by modifying `WallpaperPerfMonitor`:

```python
# In monitor.py __init__
self._sample_interval = 2.0  # Sample every 2 seconds
self._history_size = 5       # Average over 5 samples
```

## Troubleshooting

### "N/A" shown for CPU and RAM

**Common causes**:

1. **No wallpaper is running** (MOST COMMON)
   - CPU and RAM metrics require an active wallpaper process to monitor
   - Start a wallpaper first: `hyprwall set <path>` or use the GUI "Start" button
   - The performance widget will show "N/A" when no wallpaper is active (this is correct behavior)

2. **psutil library not installed**
   
   **Check if installed**:
   ```bash
   python3 -c "import psutil; print('✅ psutil installed')"
   ```
   
   **Install if missing**:
   ```bash
   # Install psutil
   pip install psutil
   
   # Or reinstall HyprWall to get all dependencies
   pip install -e .  # If in development mode
   ```
   
   After installing, **restart HyprWall GUI** to see CPU/RAM metrics.

**Test the monitor**:
```bash
# Run test script (requires a wallpaper to be running)
python3 test_perf.py
```

### GPU shows "N/A"
- **NVIDIA**: Install `nvidia-utils` package
  ```bash
  sudo pacman -S nvidia-utils  # Arch
  sudo dnf install nvidia-utils  # Fedora
  ```
- **AMD**: Check `/sys/class/drm/card*/device/gpu_busy_percent` exists
  - GPU monitoring works out of the box on recent kernels (5.15+)
- **Intel**: Currently not supported (too complex to implement reliably)

### Temperatures show "N/A"
**Cause**: hwmon sensors not detected

**Solution**:
```bash
# Install lm-sensors
sudo pacman -S lm-sensors  # Arch
sudo dnf install lm_sensors  # Fedora

# Detect sensors (run once)
sudo sensors-detect

# Verify sensors work
sensors
```

Check that `/sys/class/hwmon` contains temperature sensors:
```bash
ls -la /sys/class/hwmon/
```

## Future Enhancements

Possible improvements (not implemented):

- [ ] Circular progress bars for CPU/RAM/GPU
- [ ] Historical graphs (sparklines)
- [ ] Frame rate monitoring (mpv IPC)
- [ ] Power consumption (via RAPL)
- [ ] Network usage (for remote wallpapers)
- [ ] Per-monitor metrics (if multiple wallpapers)
