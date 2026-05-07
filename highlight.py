#!/usr/bin/env python3
"""
highlight.py  –  Video Highlight Generator
==========================================

Usage
-----
  python highlight.py input.mp4 [options]

Examples
--------
  # Basic – output saved next to the input file
  python highlight.py concert.mp4

  # Custom output path and 2-minute highlight
  python highlight.py concert.mp4 -o highlight.mp4 --max-duration 120

  # Heavier weight on solos (spectral brightness)
  python highlight.py concert.mp4 --w-centroid 0.5 --w-energy 0.3 --w-onset 0.2

  # Disable crossfade (hard cuts)
  python highlight.py concert.mp4 --crossfade 0
"""

import argparse
import os
import sys
import tempfile

# ── guard: check file size / duration before heavy processing ─────────────────
MAX_SIZE_BYTES  = 1 * 1024 ** 3   # 1 GB
MAX_DURATION_S  = 10 * 60         # 10 minutes


def _validate_input(path: str) -> None:
    if not os.path.isfile(path):
        sys.exit(f"❌  File not found: {path}")

    size = os.path.getsize(path)
    if size > MAX_SIZE_BYTES:
        sys.exit(
            f"❌  File is {size / 1024**3:.2f} GB – maximum allowed is 1 GB."
        )

    # Quick duration check via moviepy (reads header only)
    try:
        from moviepy import VideoFileClip
        with VideoFileClip(path) as v:
            duration = v.duration
        if duration > MAX_DURATION_S:
            sys.exit(
                f"❌  Video is {duration/60:.1f} min – maximum allowed is 10 min."
            )
        print(f"✔  Input OK  ({size/1024**2:.1f} MB, {duration:.1f}s)")
    except Exception as e:
        sys.exit(f"❌  Could not read video: {e}")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a musical highlight reel from a band/concert video.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("input", help="Path to the source video file.")
    parser.add_argument(
        "-o", "--output",
        default=None,
        help="Output path (default: <input>_highlight.mp4).",
    )
    parser.add_argument(
        "--max-duration",
        type=float,
        default=90.0,
        metavar="SEC",
        help="Maximum length of the highlight reel in seconds (default: 90).",
    )
    parser.add_argument(
        "--segment-duration",
        type=float,
        default=5.0,
        metavar="SEC",
        help="Granularity of candidate segments in seconds (default: 5).",
    )
    parser.add_argument(
        "--crossfade",
        type=float,
        default=0.5,
        metavar="SEC",
        help="Crossfade duration between clips in seconds (default: 0.5). Set 0 for hard cuts.",
    )
    parser.add_argument(
        "--w-energy",
        type=float,
        default=0.40,
        metavar="W",
        help="Weight for RMS energy feature (default: 0.40).",
    )
    parser.add_argument(
        "--w-onset",
        type=float,
        default=0.35,
        metavar="W",
        help="Weight for onset strength feature (default: 0.35).",
    )
    parser.add_argument(
        "--w-centroid",
        type=float,
        default=0.25,
        metavar="W",
        help="Weight for spectral centroid / brightness (default: 0.25). "
             "Raise this to prioritise solos.",
    )
    parser.add_argument(
        "--min-gap",
        type=float,
        default=0.0,
        metavar="SEC",
        help="Minimum gap between selected segments (avoids near-duplicate clips).",
    )
    parser.add_argument(
        "--resolution",
        type=str,
        default=None,
        metavar="WxH",
        help="Optionally resize output, e.g. 1280x720.",
    )

    args = parser.parse_args()

    # ── derived values ────────────────────────────────────────────────────────
    in_path = os.path.abspath(args.input)

    if args.output:
        out_path = os.path.abspath(args.output)
    else:
        base, _ = os.path.splitext(in_path)
        out_path = base + "_highlight.mp4"

    weights = {
        "energy":   args.w_energy,
        "onset":    args.w_onset,
        "centroid": args.w_centroid,
    }
    # Normalise weights so they sum to 1
    total_w = sum(weights.values())
    weights = {k: v / total_w for k, v in weights.items()}

    resolution = None
    if args.resolution:
        try:
            w, h = args.resolution.lower().split("x")
            resolution = (int(w), int(h))
        except ValueError:
            sys.exit("❌  --resolution must be in WxH format, e.g. 1280x720")

    # ── validate ──────────────────────────────────────────────────────────────
    print("\n── Validating input ──────────────────────────────────────────────")
    _validate_input(in_path)

    # ── extract audio to a temp file ──────────────────────────────────────────
    print("\n── Extracting audio ──────────────────────────────────────────────")
    from moviepy import VideoFileClip

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        tmp_audio = tf.name

    try:
        with VideoFileClip(in_path) as vc:
            vc.audio.write_audiofile(tmp_audio, logger=None)
        print(f"  Temp audio: {tmp_audio}")

        # ── analyse ───────────────────────────────────────────────────────────
        print("\n── Analysing audio ───────────────────────────────────────────────")
        from audio_analysis import analyse, select_segments

        scored = analyse(
            audio_path=tmp_audio,
            segment_duration=args.segment_duration,
            weights=weights,
        )
        chosen = select_segments(
            scored,
            max_duration=args.max_duration,
            min_gap=args.min_gap,
        )

    finally:
        if os.path.exists(tmp_audio):
            os.remove(tmp_audio)

    if not chosen:
        sys.exit("❌  No segments selected – the video may be too short.")

    # ── build highlight ───────────────────────────────────────────────────────
    print("\n── Building highlight reel ───────────────────────────────────────")
    from highlight_builder import build_highlight

    build_highlight(
        video_path=in_path,
        segments=chosen,
        output_path=out_path,
        crossfade=args.crossfade,
        target_resolution=resolution,
    )


if __name__ == "__main__":
    main()
