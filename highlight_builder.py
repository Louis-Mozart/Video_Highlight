"""
highlight_builder.py
--------------------
Cuts the original video at the selected time ranges and concatenates
the clips into a single highlight reel, with optional crossfade transitions.
"""

import os
from moviepy import VideoFileClip, concatenate_videoclips
from moviepy import vfx


def build_highlight(
    video_path: str,
    segments: list[tuple[float, float, float]],
    output_path: str,
    crossfade: float = 0.5,
    target_resolution: tuple[int, int] | None = None,
) -> str:
    """
    Cut `video_path` at the given time ranges and write the result to
    `output_path`.

    Parameters
    ----------
    video_path        : source video file
    segments          : list of (start_sec, end_sec, score) in chronological order
    output_path       : destination file path (mp4 recommended)
    crossfade         : crossfade duration in seconds between clips (0 = hard cut)
    target_resolution : optional (width, height) to resize clips, e.g. (1280, 720)

    Returns
    -------
    output_path
    """
    if not segments:
        raise ValueError("No segments provided – nothing to build.")

    print(f"\n[builder] Opening source video: {video_path}")
    source = VideoFileClip(video_path)

    clips = []
    for i, (start, end, _) in enumerate(segments):
        # Clamp to actual video duration
        start = max(0.0, start)
        end   = min(source.duration, end)
        if end - start < 0.5:
            print(f"  Skipping segment {i} (too short after clamping)")
            continue

        clip = source.subclipped(start, end)

        if target_resolution:
            clip = clip.resized(target_resolution)

        # Crossfade: all clips except the first fade in
        if crossfade > 0 and i > 0:
            clip = clip.with_effects([vfx.CrossFadeIn(crossfade)])

        clips.append(clip)
        print(f"  Clip {i+1}: {start:.1f}s → {end:.1f}s  ({end-start:.1f}s)")

    if not clips:
        raise RuntimeError("All segments were too short or out of bounds.")

    print(f"\n[builder] Concatenating {len(clips)} clip(s)…")
    method = "compose" if crossfade > 0 else "chain"
    final = concatenate_videoclips(clips, method=method)

    print(f"[builder] Writing → {output_path}")
    final.write_videofile(
        output_path,
        codec="libx264",
        audio_codec="aac",
        logger="bar",
    )

    source.close()
    final.close()
    for c in clips:
        c.close()

    print(f"\n✅  Highlight saved: {output_path}")
    return output_path
