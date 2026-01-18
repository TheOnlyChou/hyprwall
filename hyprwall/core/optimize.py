from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast
from subprocess import CalledProcessError, run

from hyprwall.core import paths
from hyprwall.core.detect import IMAGE_EXTS

Codec = Literal["h264", "vp9", "av1"]
Encoder = Literal["auto", "cpu", "vaapi", "nvenc"]

@dataclass(frozen=True)
class OptimizeProfile:
    name: str
    fps: int
    quality: int  # CRF/QP value
    preset: str

@dataclass(frozen=True)
class OptimizeResult:
    """Result of optimization operation"""
    path: Path
    cache_hit: bool
    requested: Encoder
    chosen: Encoder
    used: Encoder

ECO = OptimizeProfile(name="eco", fps=24, quality=28, preset="veryfast")
ECO_STRICT = OptimizeProfile(name="eco_strict", fps=18, quality=30, preset="veryfast")
BALANCED = OptimizeProfile(name="balanced", fps=30, quality=24, preset="veryfast")
QUALITY = OptimizeProfile(name="quality", fps=30, quality=20, preset="fast")

# Codec → allowed encoders mapping (reflects real hardware capabilities)
CODEC_ENCODERS: dict[Codec, list[Encoder]] = {
    "h264": ["cpu", "nvenc"],      # VAAPI H.264 NOT supported on AMD Radeon 780M
    "vp9": ["cpu"],                # VP9 CPU only
    "av1": ["vaapi"],              # AV1 VAAPI only (working on AMD)
}

def _sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def _source_fingerprint(p: Path) -> dict:
    st = p.stat()
    return {
        "path": str(p.resolve()),
        "size": st.st_size,
        "mtime": int(st.st_mtime),
    }

def cache_key(
    source: Path,
    width: int,
    height: int,
    profile: OptimizeProfile,
    mode: str,
    codec: Codec,
    encoder: Encoder,
) -> str:
    payload = {
        "src": _source_fingerprint(source),
        "w": width,
        "h": height,
        "fps": profile.fps,
        "codec": codec,
        "quality": profile.quality,
        "preset": profile.preset,
        "enc": encoder,
        "mode": mode,
    }
    return _sha256_text(json.dumps(payload, sort_keys=True))

def optimized_path(key: str, codec: Codec) -> Path:
    out_dir = paths.OPT_DIR / key
    if codec == "h264":
        ext = ".mp4"
    elif codec == "vp9":
        ext = ".webm"
    else:  # av1
        ext = ".mkv"
    return out_dir / f"wallpaper{ext}"

def _ffmpeg_exists() -> bool:
    return shutil.which("ffmpeg") is not None

def _ffmpeg_encoders_text() -> str:
    proc = run(
        ["ffmpeg", "-hide_banner", "-encoders"],
        capture_output=True,
        text=True,
        check=True,
    )
    return (proc.stdout or "") + (proc.stderr or "")

def _has_nvenc(enc_txt: str) -> bool:
    if "h264_nvenc" not in enc_txt:
        return False

    # NVENC requires CUDA runtime
    return (
        Path("/usr/lib64/libcuda.so.1").exists()
        or Path("/usr/lib/x86_64-linux-gnu/libcuda.so.1").exists()
        or Path("/usr/lib/libcuda.so.1").exists()
    )

def _has_av1_vaapi(enc_txt: str) -> bool:
    return "av1_vaapi" in enc_txt and Path("/dev/dri/renderD128").exists()

def pick_encoder(requested: Encoder, codec: Codec) -> Encoder:
    """Pick encoder based on codec and requested preference"""
    allowed = CODEC_ENCODERS.get(codec, ["cpu"])

    # Explicit request: validate against allowed encoders
    if requested in ("cpu", "vaapi", "nvenc"):
        if requested not in allowed:
            allowed_str = ", ".join(allowed)
            raise RuntimeError(
                f"{requested.upper()} encoder not supported for {codec.upper()} codec. "
                f"Supported encoders for {codec.upper()}: {allowed_str}"
            )
        return requested

    # Auto mode: select best available encoder for this codec
    if requested != "auto":
        return "cpu"

    try:
        enc_txt = _ffmpeg_encoders_text()
    except CalledProcessError:
        return "cpu"

    # Auto selection logic per codec
    if codec == "h264":
        if "nvenc" in allowed and _has_nvenc(enc_txt):
            return "nvenc"
        return "cpu"
    elif codec == "av1":
        if "vaapi" in allowed and _has_av1_vaapi(enc_txt):
            return "vaapi"
        raise RuntimeError("AV1 codec requires VAAPI hardware support (not available on this system)")
    elif codec == "vp9":
        return "cpu"
    else:
        return "cpu"

def _build_vf(width: int, height: int, fps: int) -> str:
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},"
        f"fps={fps},"
        f"setsar=1"
    )

def _run(cmd: list[str]) -> None:
    """Run ffmpeg command and provide clear error messages"""
    try:
        run(cmd, check=True, capture_output=True, text=True)
    except CalledProcessError as e:
        msg = (e.stderr or e.stdout or "").strip()
        raise RuntimeError(msg or f"ffmpeg failed with code {e.returncode}") from e
    except KeyboardInterrupt:
        raise RuntimeError("Encoding interrupted by user.")

def _encode_h264_cpu(src: Path, dst: Path, vf: str, quality: int, preset: str) -> None:
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(src),
        "-an",
        "-vf", vf,
        "-c:v", "libx264",
        "-crf", str(quality),
        "-preset", preset,
        "-pix_fmt", "yuv420p",
        str(dst),
    ]
    _run(cmd)

def _encode_h264_nvenc(src: Path, dst: Path, vf: str, quality: int) -> None:
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(src),
        "-an",
        "-vf", vf,
        "-c:v", "h264_nvenc",
        "-preset", "p4",
        "-cq", str(quality),
        "-pix_fmt", "yuv420p",
        str(dst),
    ]
    _run(cmd)

def _encode_vp9_cpu(src: Path, dst: Path, vf: str, quality: int) -> None:
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(src),
        "-an",
        "-vf", vf,
        "-c:v", "libvpx-vp9",
        "-crf", str(quality),
        "-b:v", "0",
        str(dst),
    ]
    _run(cmd)

def _encode_av1_vaapi(src: Path, dst: Path, width: int, height: int, fps: int, quality: int) -> None:
    dev = "/dev/dri/renderD128"
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},"
        f"fps={fps},"
        f"format=nv12,hwupload,setsar=1"
    )
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-vaapi_device", dev,
        "-i", str(src),
        "-an",
        "-vf", vf,
        "-c:v", "av1_vaapi",
        "-quality", str(quality),
        str(dst),
    ]
    _run(cmd)

def ensure_optimized(
    source: Path,
    width: int,
    height: int,
    profile: OptimizeProfile,
    mode: str,
    codec: Codec,
    encoder: Encoder = "auto",
    verbose: bool = False,
) -> OptimizeResult:
    """
    Return optimization result with path to optimized file in cache.
    If already cached, reuse it (cache hit).

    Encoder selection:
    - "auto": pick best available encoder for the codec
    - "cpu", "nvenc", "vaapi": explicit encoder (fails if not supported)

    No implicit fallback in strict mode.
    """
    if not _ffmpeg_exists():
        raise RuntimeError("ffmpeg not found in PATH. Install it to enable optimization.")

    requested = encoder
    chosen = pick_encoder(requested, codec)

    if verbose:
        print(f"[encode] codec={codec} requested={requested} chosen={chosen}")

    key = cache_key(source, width, height, profile, mode, codec, chosen)
    dst = optimized_path(key, codec)
    dst.parent.mkdir(parents=True, exist_ok=True)

    # Cache hit
    if dst.exists() and dst.stat().st_size > 0:
        if verbose:
            print(f"[cache] hit: {dst}")
        return OptimizeResult(
            path=dst,
            cache_hit=True,
            requested=requested,
            chosen=chosen,
            used=chosen,
        )

    if verbose:
        print(f"[cache] miss: {dst}")

    # Handle static images: loop for 2 seconds (mpvpaper loops indefinitely anyway)
    if source.suffix.lower() in IMAGE_EXTS:
        tmp = dst.with_name(dst.stem + ".tmp" + dst.suffix)
        vf = _build_vf(width, height, profile.fps)

        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-loop", "1",
            "-i", str(source),
            "-t", "2",
            "-an",
            "-vf", vf,
        ]

        if codec == "h264":
            cmd += ["-c:v", "libx264", "-crf", str(profile.quality), "-preset", profile.preset, "-pix_fmt", "yuv420p"]
        elif codec == "av1":
            cmd += ["-c:v", "libaom-av1", "-crf", str(profile.quality), "-b:v", "0"]
        else:  # vp9
            cmd += ["-c:v", "libvpx-vp9", "-crf", str(profile.quality), "-b:v", "0"]

        cmd += [str(tmp)]
        _run(cmd)
        tmp.replace(dst)

        return OptimizeResult(
            path=dst,
            cache_hit=False,
            requested=requested,
            chosen=chosen,
            used=cast(Encoder, "cpu"),
        )

    # Video inputs: encode based on codec and chosen encoder
    tmp = dst.with_name(dst.stem + ".tmp" + dst.suffix)
    vf = _build_vf(width, height, profile.fps)

    try:
        if codec == "h264":
            if chosen == "nvenc":
                _encode_h264_nvenc(source, tmp, vf, quality=profile.quality)
            else:  # cpu
                _encode_h264_cpu(source, tmp, vf, profile.quality, profile.preset)

        elif codec == "av1":
            # AV1 always uses VAAPI (pick_encoder enforces this)
            _encode_av1_vaapi(source, tmp, width, height, profile.fps, quality=profile.quality)

        elif codec == "vp9":
            _encode_vp9_cpu(source, tmp, vf, profile.quality)

        tmp.replace(dst)

        return OptimizeResult(
            path=dst,
            cache_hit=False,
            requested=requested,
            chosen=chosen,
            used=chosen,
        )

    except RuntimeError:
        # Clean up temp file on failure
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        raise