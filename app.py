"""
app.py  –  Video Highlight Generator — Streamlit UI
====================================================
Run with:
    streamlit run app.py
"""

import os
import sys
import tempfile
import time

import numpy as np
import streamlit as st

# ── page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="🎸 Video Highlight Generator",
    page_icon="🎸",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .param-card {
        background: #1e1e2e;
        border: 1px solid #313244;
        border-radius: 12px;
        padding: 1rem 1.2rem;
        margin-bottom: 0.8rem;
    }
    .param-title { font-size: 1rem; font-weight: 700; color: #cdd6f4; }
    .param-desc  { font-size: 0.82rem; color: #a6adc8; margin-top: 0.3rem; line-height: 1.5; }
    .tag {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 999px;
        font-size: 0.72rem;
        font-weight: 600;
        margin-right: 4px;
    }
    .tag-energy   { background:#f38ba8; color:#1e1e2e; }
    .tag-onset    { background:#fab387; color:#1e1e2e; }
    .tag-centroid { background:#a6e3a1; color:#1e1e2e; }
    .tag-cut      { background:#89b4fa; color:#1e1e2e; }
    .tag-time     { background:#cba6f7; color:#1e1e2e; }
    .seg-bar { height: 6px; border-radius: 3px; margin: 2px 0; }
    section[data-testid="stSidebar"] { background: #181825; }
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR  –  parameters
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## ⚙️ Parameters")
    st.markdown("---")

    # ── OUTPUT LENGTH ─────────────────────────────────────────────────────────
    st.markdown("""
<div class="param-card">
  <div class="param-title">🕒 Highlight duration &nbsp;<span class="tag tag-time">TIME</span></div>
  <div class="param-desc">
    Maximum length of the output video in seconds.<br>
    <b>90 s = 1 min 30 s</b> is the default.<br>
    Shorter → tighter reel; longer → more context kept.
  </div>
</div>""", unsafe_allow_html=True)
    max_duration = st.slider(
        "Max output duration (s)", min_value=20, max_value=180,
        value=90, step=5, label_visibility="collapsed"
    )

    st.markdown("---")

    # ── SEGMENT GRANULARITY ───────────────────────────────────────────────────
    st.markdown("""
<div class="param-card">
  <div class="param-title">✂️ Segment size &nbsp;<span class="tag tag-cut">CUT</span></div>
  <div class="param-desc">
    The analyser splits the video into windows of this size before scoring.<br>
    <b>Smaller (3–5 s)</b> → more precise cuts, may feel choppy.<br>
    <b>Larger (8–15 s)</b> → longer continuous stretches, smoother feel.
  </div>
</div>""", unsafe_allow_html=True)
    segment_duration = st.slider(
        "Segment size (s)", min_value=3, max_value=20,
        value=8, step=1, label_visibility="collapsed"
    )

    st.markdown("---")

    # ── CROSSFADE ─────────────────────────────────────────────────────────────
    st.markdown("""
<div class="param-card">
  <div class="param-title">🌊 Crossfade &nbsp;<span class="tag tag-cut">CUT</span></div>
  <div class="param-desc">
    Duration of the visual dissolve between two clips.<br>
    <b>0 s</b> = hard cut (instant, punchy).<br>
    <b>0.5–1 s</b> = smooth blend (feels more cinematic).
  </div>
</div>""", unsafe_allow_html=True)
    crossfade = st.slider(
        "Crossfade (s)", min_value=0.0, max_value=2.0,
        value=0.5, step=0.1, format="%.1f s", label_visibility="collapsed"
    )

    st.markdown("---")

    # ── SCORING WEIGHTS ───────────────────────────────────────────────────────
    st.markdown("### 🎚️ Scoring weights")
    st.markdown("""
<div class="param-desc" style="color:#a6adc8;font-size:0.82rem;margin-bottom:0.6rem">
  The three sliders below control how each audio feature influences
  segment selection. They are <b>automatically normalised</b> so they
  always sum to 100 %.
</div>""", unsafe_allow_html=True)

    st.markdown("""
<div class="param-card">
  <div class="param-title">⚡ Energy &nbsp;<span class="tag tag-energy">ENERGY</span></div>
  <div class="param-desc">
    Measures <b>loudness / power</b> (RMS amplitude).<br>
    High → keeps the <b>biggest, heaviest moments</b>: full-band
    climaxes, loud choruses, wall-of-sound sections.
  </div>
</div>""", unsafe_allow_html=True)
    w_energy = st.slider("Energy weight", 0, 10, 4, label_visibility="collapsed")

    st.markdown("""
<div class="param-card">
  <div class="param-title">🥁 Onset density &nbsp;<span class="tag tag-onset">ONSET</span></div>
  <div class="param-desc">
    Counts <b>transients per second</b> — note attacks, drum hits,
    pick strikes.<br>
    High → favours <b>busy, rhythmically dense parts</b>: fast fills,
    double-kick passages, tight riffs.
  </div>
</div>""", unsafe_allow_html=True)
    w_onset = st.slider("Onset weight", 0, 10, 3, label_visibility="collapsed")

    st.markdown("""
<div class="param-card">
  <div class="param-title">🎸 Brightness (solos) &nbsp;<span class="tag tag-centroid">CENTROID</span></div>
  <div class="param-desc">
    Measures the <b>spectral centroid</b> — how "bright" or "trebly"
    the audio is.<br>
    High → favours <b>lead guitar solos, screaming vocals, high
    synth leads</b> — anything that cuts through the mix in the
    upper frequencies.
  </div>
</div>""", unsafe_allow_html=True)
    w_centroid = st.slider("Brightness weight", 0, 10, 3, label_visibility="collapsed")

    # Normalise & display
    total_w = w_energy + w_onset + w_centroid
    if total_w == 0:
        total_w = 1
    we = w_energy  / total_w
    wo = w_onset   / total_w
    wc = w_centroid / total_w

    st.markdown(f"""
<div style="margin-top:0.5rem;font-size:0.8rem;color:#a6adc8;">
  Effective weights →
  <span class="tag tag-energy">Energy {we*100:.0f}%</span>
  <span class="tag tag-onset">Onset {wo*100:.0f}%</span>
  <span class="tag tag-centroid">Brightness {wc*100:.0f}%</span>
</div>""", unsafe_allow_html=True)

    st.markdown("---")

    # ── MIN GAP ───────────────────────────────────────────────────────────────
    st.markdown("""
<div class="param-card">
  <div class="param-title">↔️ Min gap between clips &nbsp;<span class="tag tag-cut">CUT</span></div>
  <div class="param-desc">
    Two selected segments must be at least this many seconds apart
    in the original video.<br>
    Prevents picking <b>near-identical consecutive windows</b>.
    Raise it to force more variety.
  </div>
</div>""", unsafe_allow_html=True)
    min_gap = st.slider(
        "Min gap (s)", min_value=0, max_value=30,
        value=2, step=1, label_visibility="collapsed"
    )


# ─────────────────────────────────────────────────────────────────────────────
# MAIN AREA
# ─────────────────────────────────────────────────────────────────────────────

st.title("🎸 Video Highlight Generator")
st.markdown(
    "Upload a concert or band video (≤ 1 GB, ≤ 10 min) and get back "
    "a highlight reel of the most energetic, rhythmically dense, and "
    "solo-packed moments — automatically."
)

# ── how it works ──────────────────────────────────────────────────────────────
with st.expander("ℹ️ How does it work?", expanded=False):
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("#### 1️⃣ Audio analysis")
        st.markdown(
            "The audio track is extracted and analysed frame-by-frame "
            "with **librosa**. Three signals are computed: loudness (RMS), "
            "transient density (onset strength), and spectral brightness "
            "(centroid). These are weighted and combined into a single "
            "score curve over time."
        )
    with col2:
        st.markdown("#### 2️⃣ Segment selection")
        st.markdown(
            "The timeline is split into equal windows. Each window gets "
            "an average score. The **highest-scoring windows** are greedily "
            "picked until the chosen total length fills your requested "
            "highlight duration. A minimum-gap rule avoids near-duplicate "
            "back-to-back clips."
        )
    with col3:
        st.markdown("#### 3️⃣ Video assembly")
        st.markdown(
            "The selected time ranges are cut from the original video "
            "with **moviepy** and stitched together. An optional crossfade "
            "dissolve smooths the transition between each pair of clips. "
            "The result is encoded as H.264 / AAC MP4."
        )

    st.markdown("---")
    st.markdown("#### 🎚️ Weight intuition — quick reference")
    ref_cols = st.columns(3)
    with ref_cols[0]:
        st.markdown("""
**⚡ Energy** (loudness)
| Value | Result |
|-------|--------|
| High  | Big choruses, walls of sound |
| Low   | Quieter, more dynamic moments |
""")
    with ref_cols[1]:
        st.markdown("""
**🥁 Onset** (transients)
| Value | Result |
|-------|--------|
| High  | Fast drum fills, dense riffs |
| Low   | Sustained, atmospheric parts |
""")
    with ref_cols[2]:
        st.markdown("""
**🎸 Brightness** (solos)
| Value | Result |
|-------|--------|
| High  | Lead guitar solos, screaming vocals |
| Low   | Bass-heavy, dark-toned sections |
""")

st.markdown("---")

# ── upload ────────────────────────────────────────────────────────────────────
uploaded = st.file_uploader(
    "📂 Drop your video here",
    type=["mp4", "mov", "avi", "mkv", "webm"],
    help="Max 1 GB · Max 10 minutes",
)



# ─────────────────────────────────────────────────────────────────────────────
# score visualisation helper  (defined after imports are guaranteed available)
# ─────────────────────────────────────────────────────────────────────────────

def _render_timeline(chosen: list, total_duration: float) -> str:
    """Render a simple HTML timeline bar showing chosen segments."""
    bars = []
    for start, end, score in chosen:
        left  = start / total_duration * 100
        width = (end - start) / total_duration * 100
        label = f"{start:.0f}s–{end:.0f}s"
        bars.append(
            f'<div style="position:absolute;left:{left:.2f}%;width:{width:.2f}%;">'
            f'  <div style="background:#a6e3a1;height:28px;border-radius:4px;'
            f'              opacity:0.9;border:1px solid #40a02b;">'
            f'    <span style="font-size:0.65rem;padding:2px 4px;color:#1e1e2e;'
            f'                 font-weight:600;">{label}</span>'
            f'  </div>'
            f'</div>'
        )
    return (
        '<div style="position:relative;height:36px;background:#313244;'
        '            border-radius:6px;margin:8px 0 16px 0;overflow:hidden;">'
        + "".join(bars)
        + "</div>"
    )



def _show_score_chart(
    scored: list,
    chosen: list,
    total_duration: float,
) -> None:
    """
    Display a simple bar chart showing the score of every candidate segment,
    with chosen segments highlighted.
    """
    import pandas as pd

    chosen_ranges = {(round(s, 1), round(e, 1)) for s, e, _ in chosen}

    rows = []
    for start, end, score in sorted(scored, key=lambda x: x[0]):
        mid = (start + end) / 2
        key = (round(start, 1), round(end, 1))
        rows.append({
            "time (s)": round(mid, 1),
            "score": round(score, 4),
            "selected": key in chosen_ranges,
        })

    df = pd.DataFrame(rows)

    st.markdown("### 📊 Segment scores")
    st.markdown(
        "Each bar is one candidate window. "
        "🟢 **Green bars** are the segments that made it into the highlight."
    )

    # Colour map: selected = green, not selected = muted blue
    colors = ["#a6e3a1" if r else "#45475a" for r in df["selected"]]

    st.bar_chart(
        df.set_index("time (s)")["score"],
        color="#a6e3a1",
        use_container_width=True,
        height=220,
    )

    # Timeline annotation
    st.markdown("**Selected windows on the timeline:**")
    timeline_html = _render_timeline(chosen, total_duration)
    st.markdown(timeline_html, unsafe_allow_html=True)

if uploaded is not None:
    # ── size guard ────────────────────────────────────────────────────────────
    MAX_BYTES = 1 * 1024 ** 3
    if uploaded.size > MAX_BYTES:
        st.error(f"❌ File is {uploaded.size/1024**3:.2f} GB — maximum is 1 GB.")
        st.stop()

    st.video(uploaded)

    # ── Reset session state when a new file is uploaded ───────────────────────
    if "last_upload" not in st.session_state or st.session_state.last_upload != uploaded.name:
        for key in ["in_path", "scored", "chosen", "duration", "highlight_bytes"]:
            st.session_state.pop(key, None)
        st.session_state.last_upload = uploaded.name

    # ═════════════════════════════════════════════════════════════════════════
    # PHASE 1 — ANALYSIS
    # ═════════════════════════════════════════════════════════════════════════
    if "scored" not in st.session_state:
        if st.button("🔬 Analyse Video", type="primary", use_container_width=True):
            suffix = os.path.splitext(uploaded.name)[1] or ".mp4"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_in:
                tmp_in.write(uploaded.read())
                in_path = tmp_in.name
            st.session_state.in_path = in_path

            progress = st.progress(0, text="Starting…")
            status   = st.empty()

            try:
                # validate
                progress.progress(5, text="Checking video…")
                from moviepy import VideoFileClip
                with VideoFileClip(in_path) as vc:
                    duration = vc.duration
                if duration > 10 * 60:
                    st.error(f"❌ Video is {duration/60:.1f} min — maximum is 10 min.")
                    st.stop()

                # extract audio
                progress.progress(15, text="Extracting audio…")
                status.info("🎵 Extracting audio track…")
                with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tf:
                    tmp_audio = tf.name
                with VideoFileClip(in_path) as vc:
                    vc.audio.write_audiofile(tmp_audio, logger=None)

                # analyse
                progress.progress(30, text="Analysing audio…")
                status.info("🔬 Analysing audio features…")
                from audio_analysis import analyse, select_segments
                weights = {"energy": we, "onset": wo, "centroid": wc}
                scored = analyse(
                    audio_path=tmp_audio,
                    segment_duration=float(segment_duration),
                    weights=weights,
                )
                os.remove(tmp_audio)

                # select
                progress.progress(55, text="Selecting best segments…")
                status.info("🏆 Selecting the best segments…")
                chosen = select_segments(
                    scored,
                    max_duration=float(max_duration),
                    min_gap=float(min_gap),
                )
                if not chosen:
                    st.error("❌ No segments selected — try reducing the min gap or segment size.")
                    st.stop()

                st.session_state.scored   = scored
                st.session_state.chosen   = chosen
                st.session_state.duration = duration
                progress.progress(100, text="Analysis complete!")
                status.success("✅ Analysis done! Review and adjust the segments below.")
                st.rerun()

            except Exception as exc:
                st.error(f"❌ Error during analysis: {exc}")
                import traceback; st.code(traceback.format_exc())

    # ═════════════════════════════════════════════════════════════════════════
    # PHASE 2 — SEGMENT EDITOR
    # ═════════════════════════════════════════════════════════════════════════
    if "scored" in st.session_state and "highlight_bytes" not in st.session_state:
        scored   = st.session_state.scored
        chosen   = st.session_state.chosen
        duration = st.session_state.duration

        _show_score_chart(scored, chosen, duration)

        st.markdown("---")
        st.markdown("### ✏️ Adjust segments")
        st.markdown(
            "The sliders below let you fine-tune each segment's **start** and **end** time. "
            "You can also **remove** a segment you don't want, or **add a new one**."
        )

        # ── editable segment list stored in session_state ─────────────────────
        if "edit_segments" not in st.session_state:
            st.session_state.edit_segments = [[s, e] for s, e, _ in chosen]

        segs = st.session_state.edit_segments
        to_delete = []

        for i, (seg_start, seg_end) in enumerate(segs):
            col_slider, col_del = st.columns([11, 1])
            with col_slider:
                new_start, new_end = st.slider(
                    f"Segment {i+1}",
                    min_value=0.0,
                    max_value=float(duration),
                    value=(float(seg_start), float(seg_end)),
                    step=0.5,
                    format="%.1f s",
                    key=f"seg_{i}",
                )
                segs[i] = [new_start, new_end]
                seg_len = new_end - new_start
                st.caption(
                    f"⏱ Duration: **{seg_len:.1f} s**  |  "
                    f"{new_start:.1f}s → {new_end:.1f}s"
                )
            with col_del:
                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("🗑️", key=f"del_{i}", help="Remove this segment"):
                    to_delete.append(i)

        # apply deletions
        if to_delete:
            st.session_state.edit_segments = [
                s for j, s in enumerate(segs) if j not in to_delete
            ]
            st.rerun()

        # ── add segment ───────────────────────────────────────────────────────
        with st.expander("➕ Add a segment manually"):
            c1, c2 = st.columns(2)
            add_start = c1.number_input("Start (s)", 0.0, duration, 0.0, 0.5, key="add_s")
            add_end   = c2.number_input("End (s)",   0.0, duration, min(10.0, duration), 0.5, key="add_e")
            if st.button("Add segment"):
                if add_end > add_start:
                    st.session_state.edit_segments.append([add_start, add_end])
                    st.rerun()
                else:
                    st.warning("End must be greater than start.")

        # ── total duration summary ────────────────────────────────────────────
        total_sel = sum(e - s for s, e in st.session_state.edit_segments)
        st.info(
            f"📏 **{len(st.session_state.edit_segments)} segment(s)** selected  |  "
            f"Total duration: **{total_sel:.1f} s** / {max_duration} s max"
        )

        st.markdown("---")
        build_col, reset_col = st.columns([3, 1])
        build_clicked = build_col.button(
            "🚀 Build Highlight with these segments",
            type="primary", use_container_width=True
        )
        if reset_col.button("🔄 Re-analyse", use_container_width=True):
            for key in ["scored", "chosen", "duration", "edit_segments", "highlight_bytes"]:
                st.session_state.pop(key, None)
            st.rerun()

        # ═════════════════════════════════════════════════════════════════════
        # PHASE 3 — BUILD
        # ═════════════════════════════════════════════════════════════════════
        if build_clicked:
            final_segments = [
                (s, e, 0.0) for s, e in st.session_state.edit_segments if e > s
            ]
            if not final_segments:
                st.error("No valid segments to build from.")
                st.stop()

            in_path  = st.session_state.in_path
            suffix   = os.path.splitext(in_path)[1] or ".mp4"
            out_path = in_path.replace(suffix, "_highlight.mp4")

            st.markdown("#### 🎬 Video reconstruction")
            encode_bar     = st.progress(0, text="🎬 Encoding… 0 %")
            encode_pct_txt = st.empty()
            encode_pct_txt.markdown("**0 %** — starting…")
            log_area  = st.expander("📋 Encoding log", expanded=False)
            log_lines: list[str] = []

            def log(msg: str):
                log_lines.append(msg)
                log_area.code("\n".join(log_lines), language="")

            import threading
            state = {"pct": 0, "msg": "starting…", "done": False, "error": None}

            def _encode_progress(pct: int, msg: str):
                state["pct"] = pct
                state["msg"] = msg

            def _run_build():
                try:
                    from highlight_builder import build_highlight
                    build_highlight(
                        video_path=in_path,
                        segments=final_segments,
                        output_path=out_path,
                        crossfade=crossfade,
                        progress_callback=_encode_progress,
                    )
                except Exception as exc:
                    state["error"] = exc
                finally:
                    state["done"] = True

            t = threading.Thread(target=_run_build, daemon=True)
            t.start()

            _last_pct = -1
            while not state["done"]:
                pct = state["pct"]
                encode_bar.progress(pct, text=f"🎬 Encoding… {pct} %")
                encode_pct_txt.markdown(f"**{pct} %** — {state['msg']}")
                if pct // 10 != _last_pct // 10:
                    log(f"  {pct}%")
                    _last_pct = pct
                time.sleep(0.15)
            t.join()

            if state["error"]:
                st.error(f"❌ {state['error']}")
                import traceback; st.code(traceback.format_exc())
                st.stop()

            encode_bar.progress(100, text="🎬 Encoding… 100 %")
            encode_pct_txt.markdown("**100 %** — ✅ Done!")

            with open(out_path, "rb") as f:
                st.session_state.highlight_bytes = f.read()
            st.session_state.highlight_name = (
                os.path.splitext(uploaded.name)[0] + "_highlight.mp4"
            )
            try:
                os.remove(out_path)
            except Exception:
                pass
            st.rerun()

    # ═════════════════════════════════════════════════════════════════════════
    # PHASE 4 — RESULT
    # ═════════════════════════════════════════════════════════════════════════
    if "highlight_bytes" in st.session_state:
        st.markdown("---")
        st.success("✅ Your highlight is ready!")
        st.video(st.session_state.highlight_bytes)
        st.download_button(
            label="⬇️ Download highlight",
            data=st.session_state.highlight_bytes,
            file_name=st.session_state.get("highlight_name", "highlight.mp4"),
            mime="video/mp4",
            use_container_width=True,
            type="primary",
        )
        if st.button("🔄 Start over", use_container_width=True):
            for key in ["in_path", "scored", "chosen", "duration",
                        "edit_segments", "highlight_bytes", "highlight_name"]:
                st.session_state.pop(key, None)
            st.rerun()





