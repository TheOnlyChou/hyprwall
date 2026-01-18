from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "hyprwall"
CACHE_DIR = Path.home() / ".cache" / "hyprwall"
STATE_DIR = CACHE_DIR / "state"

OPT_DIR = CACHE_DIR / "optimized"
STATE_FILE = STATE_DIR / "state.json"
LOG_FILE = CACHE_DIR / "hyprwall.log"
SESSION_FILE = STATE_DIR / "session.json"

def ensure_directories():
    for d in (CONFIG_DIR, CACHE_DIR, STATE_DIR, OPT_DIR):
        d.mkdir(parents=True, exist_ok=True)

# Count the number of files and directories under a given root path (cache clearing, etc.)
def count_tree(root: Path) -> tuple[int, int]:
    """
    Count directories and files under root (recursive).
    Returns: (dirs, files)
    """
    files = 0
    dirs = 0

    if not root.exists():
        return 0, 0

    for p in root.rglob("*"):
        if p.is_file():
            files += 1
        elif p.is_dir():
            dirs += 1

    return dirs, files