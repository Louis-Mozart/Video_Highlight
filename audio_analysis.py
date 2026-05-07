"""
audio_analysis.py
-----------------
Analyses the audio track of a video and returns a list of
(start_sec, end_sec, score) tuples ranked by musical interest.

Scoring combines three complementary signals:
  • RMS energy       – how loud / powerful the moment is
  • Onset strength   – how many transients / hits (drum fills, pick attacks)
  • Spectral centroid– brightness; high values often indicate lead guitar solos
                       or prominent vocals
"""

import numpy as np
import librosa


# ──────────────────────────────────────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────────────────────────────────────

def _normalise(arr: np.ndarray) -> np.ndarray:
    """Min-max normalise to [0, 1], safe against flat arrays."""
    mn, mx = arr.min(), arr.max()
    if mx - mn < 1e-9:
        return np.zeros_like(arr)
    return (arr - mn) / (mx - mn)


def _smooth(arr: np.ndarray, window: int) -> np.ndarray:
    """Simple moving-average smoothing."""
    if window <= 1:
        return arr
    kernel = np.ones(window) / window
    return np.convolve(arr, kernel, mode="same")


# ──────────────────────────────────────────────────────────────────────────────
# public API
# ──────────────────────────────────────────────────────────────────────────────

def analyse(
    audio_path: str,
    segment_duration: float = 5.0,
    weights: dict | None = None,
    sr: int = 22050,
) -> list[tuple[float, float, float]]:
    """
    Load audio and score every non-overlapping segment.

    Parameters
    ----------
    audio_path      : path to the extracted audio file (wav/mp3/…)
    segment_duration: length of each candidate segment in seconds
    weights         : dict with keys 'energy', 'onset', 'centroid'
    sr              : sample rate used by librosa

    Returns
    -------
    List of (start_sec, end_sec, score) sorted by score descending.
    """
    if weights is None:
        weights = {"energy": 0.40, "onset": 0.35, "centroid": 0.25}

    print(f"  Loading audio from: {audio_path}")
    y, sr = librosa.load(audio_path, sr=sr, mono=True)
    duration = librosa.get_duration(y=y, sr=sr)
    print(f"  Duration: {duration:.1f}s  |  Sample rate: {sr} Hz")

    hop_length = 512

    # ── feature extraction ────────────────────────────────────────────────────
    # RMS energy (frame-level)
    rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]

    # Onset envelope
    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop_length)

    # Spectral centroid (brightness)
    centroid = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=hop_length)[0]

    # Normalise all three
    rms_n = _normalise(rms)
    onset_n = _normalise(onset_env)
    centroid_n = _normalise(centroid)

    # Combined frame-level score
    score_frames = (
        weights["energy"]   * rms_n +
        weights["onset"]    * onset_n +
        weights["centroid"] * centroid_n
    )

    # Smooth over ~1 second so we avoid micro-spikes
    smooth_win = int(sr / hop_length)          # ~1 s worth of frames
    score_frames = _smooth(score_frames, smooth_win)

    # ── convert frames → time ─────────────────────────────────────────────────
    times = librosa.frames_to_time(
        np.arange(len(score_frames)), sr=sr, hop_length=hop_length
    )

    # ── segment scoring ───────────────────────────────────────────────────────
    segments: list[tuple[float, float, float]] = []
    t = 0.0
    while t + segment_duration <= duration:
        t_end = t + segment_duration
        mask = (times >= t) & (times < t_end)
        seg_score = float(score_frames[mask].mean()) if mask.any() else 0.0
        segments.append((t, t_end, seg_score))
        t = t_end

    # Handle a leftover tail (≥ 2 s)
    if duration - t >= 2.0:
        mask = times >= t
        seg_score = float(score_frames[mask].mean()) if mask.any() else 0.0
        segments.append((t, duration, seg_score))

    # Sort best → worst
    segments.sort(key=lambda x: x[2], reverse=True)
    return segments


def select_segments(
    scored: list[tuple[float, float, float]],
    max_duration: float = 90.0,
    min_gap: float = 2.0,
) -> list[tuple[float, float, float]]:
    """
    Greedily pick the highest-scoring segments until we fill max_duration,
    enforcing a minimum gap between chosen segments to avoid duplicates.

    Returns the selected segments sorted by start time (chronological order).
    """
    chosen: list[tuple[float, float, float]] = []
    total = 0.0

    for seg in scored:
        start, end, score = seg
        seg_len = end - start

        if total + seg_len > max_duration:
            # Try a trimmed version of the segment if it helps fill a gap
            remaining = max_duration - total
            if remaining >= 2.0:
                chosen.append((start, start + remaining, score))
                total += remaining
            break

        # Reject if too close to an already-chosen segment
        overlap = False
        for cs, ce, _ in chosen:
            if not (end + min_gap <= cs or start >= ce + min_gap):
                overlap = True
                break

        if not overlap:
            chosen.append(seg)
            total += seg_len

        if total >= max_duration:
            break

    # Return in chronological order
    chosen.sort(key=lambda x: x[0])
    print(f"\n  Selected {len(chosen)} segments  |  total = {total:.1f}s")
    for s, e, sc in chosen:
        print(f"    {s:6.1f}s → {e:6.1f}s   score={sc:.4f}")

    return chosen
