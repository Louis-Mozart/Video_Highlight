"""
highlight_builder.py
--------------------
Cuts the original video at the selected time ranges and concatenates
the clips into a single highlight reel using direct ffmpeg subprocess calls.

Why ffmpeg directly (not moviepy)?
  moviepy's concatenate_videoclips(method="compose") loads all frames into RAM
  at once, which easily exceeds the memory limits on cloud platforms (Streamlit
  Cloud free tier ≈ 800 MB).  ffmpeg streams everything — memory stays flat
  regardless of video length or number of clips.
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Callable


# ── ffmpeg helpers ────────────────────────────────────────────────────────────

def _ffmpeg_bin() -> str:
    result = subprocess.run(["which", "ffmpeg"], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError("ffmpeg not found. Install it: sudo apt install ffmpeg")
    return "ffmpeg"


def _duration_of(path: str) -> float:
    """Return video duration in seconds via ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        path,
    ]
    out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True)
    return float(out.strip())


def _cut_segment(ffmpeg: str, src: str, start: float, end: float, out: str) -> None:
    """Cut a single segment using stream copy — no re-encode, no RAM usage."""
    cmd = [
        ffmpeg, "-y",
        "-ss", f"{start:.3f}",
        "-to", f"{end:.3f}",
        "-i", src,
        "-c", "copy",
        "-avoid_negative_ts", "make_zero",
        out,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg cut failed:\n{result.stderr}")


# ── public API ────────────────────────────────────────────────────────────────

def build_highlight(
    video_path: str,
    segments: list[tuple[float, float, float]],
    output_path: str,
    crossfade: float = 0.5,
    target_resolution: tuple[int, int] | None = None,
    progress_callback: Callable[[int, str], None] | None = None,
) -> str:
    """
    Cut `video_path` at the given time ranges and concatenate into
    `output_path` using ffmpeg subprocess (memory-efficient, cloud-safe).

    crossfade > 0  →  xfade dissolve filter (re-encodes, slightly more CPU)
    crossfade == 0 →  stream-copy concat (instant, zero RAM, hard cuts)
    """
    if not segments:
        raise ValueError("No segments provided – nothing to build.")

    ffmpeg = _ffmpeg_bin()
    src_duration = _duration_of(video_path)

    # clamp segments
    clean: list[tuple[float, float]] = []
    for start, end, *_ in segments:
        start = max(0.0, float(start))
        end   = min(src_duration, float(end))
        if end - start >= 0.5:
            clean.append((start, end))
        else:
            print(f"  [builder] Skipping {start:.1f}→{end:.1f} (too short)")

    if not clean:
        raise RuntimeError("All segments were too short after clamping.")

    # rough total-frame estimate for progress (assume ≤ 30 fps)
    total_frames_approx = sum(e - s for s, e in clean) * 30

    tmp_dir = tempfile.mkdtemp(prefix="vhl_")
    try:
        # ── step 1: cut each segment ──────────────────────────────────────────
        seg_files: list[str] = []
        for i, (start, end) in enumerate(clean):
            seg_path = os.path.join(tmp_dir, f"seg_{i:04d}.mp4")
            print(f"  [builder] Cutting clip {i+1}/{len(clean)}: {start:.1f}s → {end:.1f}s")
            _cut_segment(ffmpeg, video_path, start, end, seg_path)
            seg_files.append(seg_path)
            if progress_callback:
                pct = int((i + 1) / len(clean) * 20)   # 0–20 % for cutting
                progress_callback(pct, f"Cutting clip {i+1}/{len(clean)}")

        # ── step 2: write concat list ─────────────────────────────────────────
        list_path = os.path.join(tmp_dir, "concat.txt")
        with open(list_path, "w") as f:
            for seg in seg_files:
                f.write(f"file '{seg}'\n")

        # ── step 3: build final encode command ────────────────────────────────
        vf_parts: list[str] = []
        if target_resolution:
            w, h = target_resolution
            vf_parts.append(
                f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2"
            )

        if crossfade > 0 and len(seg_files) > 1:
            cmd = _build_xfade_cmd(ffmpeg, seg_files, output_path, crossfade, vf_parts)
        else:
            # Stream-copy concat (zero RAM, instant)
            cmd = [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", list_path]
            if vf_parts:
                cmd += ["-vf", ",".join(vf_parts),
                        "-c:v", "libx264", "-crf", "23", "-preset", "fast",
                        "-c:a", "aac", "-b:a", "192k"]
            else:
                cmd += ["-c", "copy"]
            cmd.append(output_path)

        print(f"\n  [builder] Encoding → {output_path}")
        if progress_callback:
            progress_callback(22, "Starting final encode…")

        # ── step 4: run & stream progress ────────────────────────────────────
        _run_with_progress(cmd, total_frames_approx, progress_callback, start_pct=22)

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    print(f"\n✅  Highlight saved: {output_path}")
    if progress_callback:
        progress_callback(100, "Done!")
    return output_path


# ── xfade helper ──────────────────────────────────────────────────────────────

def _build_xfade_cmd(
    ffmpeg: str,
    seg_files: list[str],
    output_path: str,
    crossfade: float,
    extra_vf: list[str],
) -> list[str]:
    """Build ffmpeg xfade dissolve filter_complex command."""
    durations = [_duration_of(f) for f in seg_files]
    n = len(seg_files)

    inputs: list[str] = []
    for f in seg_files:
        inputs += ["-i", f]

    if n == 1:
        vf = ",".join(extra_vf) if extra_vf else "null"
        return [
            ffmpeg, "-y", "-i", seg_files[0],
            "-vf", vf,
            "-c:v", "libx264", "-crf", "23", "-preset", "fast",
            "-c:a", "aac", "-b:a", "192k",
            output_path,
        ]

    filter_parts: list[str] = []
    for i in range(n):
        filter_parts.append(f"[{i}:v]setpts=PTS-STARTPTS[v{i}]")

    offset = durations[0] - crossfade
    filter_parts.append(
        f"[v0][v1]xfade=transition=dissolve:duration={crossfade:.2f}:offset={offset:.3f}[xf1]"
    )
    for i in range(2, n):
        offset += durations[i - 1] - crossfade
        prev = f"[xf{i-1}]"
        filter_parts.append(
            f"{prev}[v{i}]xfade=transition=dissolve:duration={crossfade:.2f}:offset={offset:.3f}[xf{i}]"
        )

    last_v = f"[xf{n-1}]"
    audio_inputs = "".join(f"[{i}:a]" for i in range(n))
    filter_parts.append(f"{audio_inputs}concat=n={n}:v=0:a=1[aout]")

    if extra_vf:
        filter_parts.append(f"{last_v}{','.join(extra_vf)}[vout]")
        map_v = "[vout]"
    else:
        map_v = last_v

    return (
        [ffmpeg, "-y"]
        + inputs
        + [
            "-filter_complex", ";".join(filter_parts),
            "-map", map_v,
            "-map", "[aout]",
            "-c:v", "libx264", "-crf", "23", "-preset", "fast",
            "-c:a", "aac", "-b:a", "192k",
            output_path,
        ]
    )


# ── progress reader ───────────────────────────────────────────────────────────

_FRAME_RE = re.compile(r"frame=\s*(\d+)")


def _run_with_progress(
    cmd: list[str],
    total_frames: float,
    callback: Callable[[int, str], None] | None,
    start_pct: int = 22,
) -> None:
    """
    Run cmd, parse ffmpeg stderr for 'frame=N', call callback(pct, msg)
    in real time.  pct goes from start_pct → 99.
    """
    proc = subprocess.Popen(
        cmd,
        stderr=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        text=True,
        bufsize=1,
    )

    last_pct = start_pct
    buf = ""

    for char in iter(lambda: proc.stderr.read(1), ""):
        if char in ("\r", "\n"):
            line = buf.strip()
            buf = ""
            if not line:
                continue
            print(line, file=sys.stderr)   # keep cloud logs visible
            if callback and total_frames > 0:
                m = _FRAME_RE.search(line)
                if m:
                    frame = int(m.group(1))
                    raw = min(frame / total_frames, 1.0)
                    pct = start_pct + int(raw * (99 - start_pct))
                    if pct != last_pct:
                        last_pct = pct
                        callback(pct, f"Encoding… frame {frame}")
        else:
            buf += char

    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg exited with code {proc.returncode}. Check the app logs."
        )
