---
title: Video Highlight Generator
emoji: 🎸
colorFrom: purple
colorTo: green
sdk: streamlit
sdk_version: "1.35.0"
app_file: app.py
pinned: false
---

# Video Highlight Generator 🎸

Automatically summarises a band/concert video into a **≤ 90-second highlight reel** by detecting the most energetic, onset-rich, and spectrally bright moments (solos, big choruses, drum fills, etc.).

---

## Requirements

- Python 3.10+
- `ffmpeg` installed on your system (`sudo apt install ffmpeg` / `brew install ffmpeg`)

## Install Python dependencies

```bash
pip install -r requirements.txt
```

---

## Usage

```bash
# Simplest form – output saved as <input>_highlight.mp4
python highlight.py my_concert.mp4

# Custom output path
python highlight.py my_concert.mp4 -o highlight.mp4

# 2-minute reel
python highlight.py my_concert.mp4 --max-duration 120

# Boost solo detection (raise spectral-centroid weight)
python highlight.py my_concert.mp4 --w-centroid 0.5 --w-energy 0.3 --w-onset 0.2

# Hard cuts (no crossfade)
python highlight.py my_concert.mp4 --crossfade 0

# Downscale to 720p
python highlight.py my_concert.mp4 --resolution 1280x720
```

### All options

| Flag | Default | Description |
|---|---|---|
| `input` | — | Source video (≤ 1 GB, ≤ 10 min) |
| `-o / --output` | `<input>_highlight.mp4` | Output file path |
| `--max-duration` | `90` | Max highlight length in seconds |
| `--segment-duration` | `5` | Candidate segment granularity (seconds) |
| `--crossfade` | `0.5` | Crossfade between clips (0 = hard cuts) |
| `--w-energy` | `0.40` | Weight for RMS loudness |
| `--w-onset` | `0.35` | Weight for transient density |
| `--w-centroid` | `0.25` | Weight for spectral brightness (solos) |
| `--min-gap` | `2.0` | Min gap between selected segments (avoids duplicates) |
| `--resolution` | — | Resize output, e.g. `1280x720` |

---

## How it works

```
Video
  │
  ├─► Extract audio (WAV) ──► librosa analysis
  │                               │
  │                         ┌─────▼──────┐
  │                         │  Per-frame │
  │                         │  scoring   │
  │                         │  • RMS     │
  │                         │  • Onsets  │
  │                         │  • Centroid│
  │                         └─────┬──────┘
  │                               │
  │                    Segment scoring (5s windows)
  │                               │
  │                    Greedy selection (≤ 90s total)
  │                               │
  └─► moviepy: cut + crossfade + encode ──► highlight.mp4
```

### Tuning tips

- **More solos / lead guitar?** → increase `--w-centroid`
- **More drum-heavy sections?** → increase `--w-onset`
- **Prefer consistently loud parts?** → increase `--w-energy`
- **Shorter/longer clips?** → adjust `--segment-duration`
