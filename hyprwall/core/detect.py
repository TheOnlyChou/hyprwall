from pathlib import Path
import os
from typing import Iterable

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
VIDEO_EXTS = {".mp4", ".mkv", ".webm"}

SUPPORTED_EXTS = IMAGE_EXTS | VIDEO_EXTS


def is_image(path: Path) -> bool:
    """Check if a file is an image"""
    return path.suffix.lower() in IMAGE_EXTS


def is_video(path: Path) -> bool:
    """Check if a file is a video"""
    return path.suffix.lower() in VIDEO_EXTS

def _iter_candidates(dir_path: Path) -> Iterable[Path]:
    files = [
        p for p in dir_path.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
    ]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files

def validate_wallpaper(path: str) -> Path:
    p = Path(path).expanduser()

    if not p.exists():
        raise ValueError("File or directory does not exist")
    if p.is_dir():
        candidates = list(_iter_candidates(p))
        if not candidates:
            raise ValueError("No supported wallpaper files found in directory")
        p = candidates[0]  # Pick the latest file

    if not p.is_file():
        raise ValueError("Path is not a file")

    if p.suffix.lower() not in SUPPORTED_EXTS:
        raise ValueError("Unsupported file format")

    if not os.access(p, os.R_OK):
        raise ValueError("File is not readable")

    return p

def find_supported_files(directory: Path, recursive: bool = True) -> list[Path]:
    """
    Find all supported media files (images and videos) in a directory.

    Args:
        directory: Directory to search
        recursive: If True, search recursively (default); if False, search only top-level

    Returns:
        List of Path objects sorted by name (lexicographic order)
    """
    pattern = "**/*" if recursive else "*"
    files = []
    for ext in SUPPORTED_EXTS:
        files.extend(directory.glob(f"{pattern}{ext}"))
    return sorted(files)
