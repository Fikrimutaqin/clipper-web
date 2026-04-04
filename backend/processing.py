import re
from pathlib import Path
from typing import Any

import av
import numpy as np


def parse_iso8601_duration(duration: str) -> str:
    """Convert YouTube ISO-8601 duration (e.g. PT1H2M3S) into H:MM:SS or M:SS."""
    if not duration:
        return "0:00"
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
    if not match:
        return "0:00"
    h, m, s = match.groups()
    h_i = int(h) if h else 0
    m_i = int(m) if m else 0
    s_i = int(s) if s else 0
    if h_i > 0:
        return f"{h_i}:{m_i:02d}:{s_i:02d}"
    return f"{m_i}:{s_i:02d}"


def _viral_score(seg_type: str, raw: float, max_raw: float, clip_dur: float, fmt: str) -> int:
    """Compute 0-100 viral potential score for a suggested segment."""
    energy = min(1.0, raw / (max_raw + 1e-9))
    type_w = {"hook": 0.90, "punchline": 1.00, "emotion": 0.85,
              "value": 0.80, "intro": 0.65, "cta": 0.55, "insight": 0.70}
    tw = type_w.get(seg_type, 0.70)
    if fmt == "short":
        opt = 30.0
        dur_fit = max(0.0, 1.0 - abs(clip_dur - opt) / max(opt, 1.0))
    else:
        opt = 600.0
        dur_fit = min(1.0, clip_dur / (opt + 1e-9))
    return max(1, min(100, round((energy * 0.5 + tw * 0.3 + dur_fit * 0.2) * 100)))


# ─── Audio helpers ────────────────────────────────────────────────────────────

def _read_audio_energy(
    container: "av.container.InputContainer",
    audio_stream: Any,
    max_scan_seconds: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (times, rms_energies) arrays sorted by time."""
    samples: list[tuple[float, float]] = []
    for frame in container.decode(audio_stream):
        t = frame.time
        if t is None:
            continue
        if t > max_scan_seconds:
            break
        try:
            arr = frame.to_ndarray()
        except AttributeError:
            arr = frame.to_ndarray(format="s16")
        if arr.ndim == 2:
            arr = arr.mean(axis=0)
        arr = arr.astype(np.float32, copy=False)
        if arr.size == 0:
            continue
        rms = float(np.sqrt(np.mean(arr * arr)))
        samples.append((float(t), rms))
    if not samples:
        return np.array([], dtype=np.float32), np.array([], dtype=np.float32)
    times = np.array([s[0] for s in samples], dtype=np.float32)
    energies = np.array([s[1] for s in samples], dtype=np.float32)
    order = np.argsort(times)
    return times[order], energies[order]


def _best_window(
    times: np.ndarray,
    energies: np.ndarray,
    range_start: float,
    range_end: float,
    window: float,
    step: float = 5.0,
) -> tuple[float, float, float]:
    """Return (start, end, score) of highest-average-energy window in range."""
    best_s, best_score = range_start, -1.0
    t = range_start
    while t + window <= range_end + 1e-6:
        mask = (times >= t) & (times < t + window)
        seg = energies[mask]
        if seg.size > 0:
            score = float(np.mean(seg))
            if score > best_score:
                best_score, best_s = score, t
        t += step
    return best_s, best_s + window, max(best_score, 0.0)


def _classify_type(
    energies: np.ndarray,
    times: np.ndarray,
    start: float,
    end: float,
    p75: float,
) -> str:
    mask = (times >= start) & (times <= end)
    seg = energies[mask]
    if seg.size == 0:
        return "insight"
    mean_e = float(np.mean(seg))
    std_e = float(np.std(seg))
    max_e = float(np.max(seg))
    if max_e > mean_e * 2.5:
        return "punchline"
    if std_e / (mean_e + 1e-9) > 0.5:
        return "emotion"
    return "insight"


def _suggest_short_clips(
    times: np.ndarray,
    energies: np.ndarray,
    total_duration: float,
    p75: float,
    target_seconds: float,
    max_candidates: int,
) -> list[dict[str, Any]]:
    window = max(20.0, min(target_seconds, 60.0))
    p90 = float(np.percentile(energies, 90)) if energies.size >= 4 else float(np.max(energies))
    peak_idx = np.where(energies >= p90)[0]
    if peak_idx.size == 0:
        peak_idx = np.array([int(np.argmax(energies))])

    candidates: list[dict[str, Any]] = []
    type_labels = {"emotion": "🎭 Emosi", "punchline": "🎯 Punchline", "insight": "💡 Insight"}
    max_e = float(np.max(energies)) if energies.size > 0 else 1.0
    for idx in peak_idx.tolist():
        t = float(times[idx])
        start = max(0.0, t - window * 0.25)
        end = min(total_duration, start + window)
        start = max(0.0, end - window)
        seg_type = _classify_type(energies, times, start, end, p75)
        raw = float(energies[idx])
        candidates.append({
            "start_seconds": round(start, 1),
            "end_seconds": round(end, 1),
            "score": round(raw, 4),
            "viral_score": _viral_score(seg_type, raw, max_e, end - start, "short"),
            "type": seg_type,
            "label": type_labels.get(seg_type, "📌 Segment"),
        })

    candidates.sort(key=lambda c: c["score"], reverse=True)
    picked: list[dict[str, Any]] = []
    for c in candidates:
        if len(picked) >= max_candidates:
            break
        if all(abs(p["start_seconds"] - c["start_seconds"]) >= window * 0.5 for p in picked):
            picked.append(c)
    return picked


def _suggest_regular_phases(
    times: np.ndarray,
    energies: np.ndarray,
    total_duration: float,
    p75: float,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []

    def phase(label: str, ptype: str, r_start: float, r_end: float, window: float, step: float = 5.0):
        r_end = min(r_end, total_duration)
        r_start = min(r_start, total_duration)
        if r_end <= r_start:
            return
        w = min(window, r_end - r_start)
        s, e, score = _best_window(times, energies, r_start, r_end, w, step)
        max_e = float(np.max(energies)) if energies.size > 0 else 1.0
        results.append({
            "start_seconds": round(s, 1),
            "end_seconds": round(min(e, total_duration), 1),
            "score": round(score, 4),
            "viral_score": _viral_score(ptype, score, max_e, min(e, total_duration) - s, "regular"),
            "type": ptype,
            "label": label,
        })

    phase("🪝 Hook (0:00 – 0:10)",           "hook",    0.0,   10.0,  10.0,  1.0)
    phase("⚡ Intro Cepat (0:10 – 1:00)",    "intro",   10.0,  60.0,  50.0,  2.0)
    phase("💡 Value Utama (1:00 – 8:00)",    "value",   60.0,  480.0, 420.0, 30.0)
    phase("📣 CTA (8:00+)",                  "cta",     480.0, max(total_duration, 481.0), min(120.0, max(1.0, total_duration - 480.0)), 10.0)

    return results


def suggest_segments_from_file(
    *,
    input_path: Path,
    target_seconds: float = 60.0,
    format_type: str = "short",
    max_candidates: int = 5,
    max_scan_seconds: float = 7200.0,
) -> list[dict[str, Any]]:
    """
    Suggest clip segments from audio energy analysis.

    format_type='short'  → 3-5 short clips (20-60 s) labeled Emosi / Punchline / Insight.
    format_type='regular' → structured phases: Hook / Intro / Value / CTA.
    """
    container = av.open(str(input_path))
    try:
        audio_stream = next((s for s in container.streams if s.type == "audio"), None)
        total_duration = 0.0
        if container.duration:
            total_duration = float(container.duration / av.time_base)

        if audio_stream is None:
            fallback_end = min(target_seconds, total_duration) if total_duration > 0 else target_seconds
            return [{"start_seconds": 0.0, "end_seconds": fallback_end, "score": 0.5,
                     "type": "insight", "label": "📌 Segment"}]

        times, energies = _read_audio_energy(container, audio_stream, max_scan_seconds)
        if times.size == 0:
            return []

        p75 = float(np.percentile(energies, 75)) if energies.size >= 4 else 0.0

        if format_type == "regular":
            return _suggest_regular_phases(times, energies, total_duration, p75)
        else:
            return _suggest_short_clips(
                times, energies, total_duration, p75,
                target_seconds=target_seconds,
                max_candidates=max_candidates,
            )
    finally:
        container.close()


# ─── Thumbnail extractor ───────────────────────────────────────────────────────

def extract_frame_jpeg(
    input_path: Path,
    timestamp_seconds: float,
    max_width: int = 1280,
    max_height: int = 720,
) -> bytes:
    """Extract a JPEG frame at the given timestamp using PyAV only (no Pillow needed)."""
    container = av.open(str(input_path))
    try:
        video_stream = next((s for s in container.streams if s.type == "video"), None)
        if not video_stream:
            raise RuntimeError("No video stream found")

        # Seek a bit before the target so decode has context
        seek_ts = max(0, int((timestamp_seconds - 2.0) * av.time_base))
        container.seek(seek_ts)

        for packet in container.demux(video_stream):
            for frame in packet.decode():
                t = frame.time
                if t is None or t < timestamp_seconds - 1.5:
                    continue

                # Scale to fit within max dimensions (keep even numbers for codec)
                w, h = frame.width, frame.height
                if w > max_width or h > max_height:
                    r = min(max_width / w, max_height / h)
                    w = int(w * r) & ~1
                    h = int(h * r) & ~1

                # Reformat to yuvj420p (required by mjpeg encoder)
                reformatted = frame.reformat(width=w, height=h, format="yuvj420p")

                # Encode directly via codec context — no container needed
                codec_ctx = av.CodecContext.create("mjpeg", "w")
                codec_ctx.width = w
                codec_ctx.height = h
                codec_ctx.pix_fmt = "yuvj420p"
                codec_ctx.bit_rate = 4_000_000

                packets = list(codec_ctx.encode(reformatted))
                packets += list(codec_ctx.encode(None))  # flush
                if packets:
                    return bytes(packets[0])
                raise RuntimeError("mjpeg encoder produced no output")
    finally:
        container.close()
    raise RuntimeError("Could not extract frame at given timestamp")



# ─── Fast stream-copy helper ─────────────────────────────────────────────────

def _stream_copy_trim(
    in_c: "av.container.InputContainer",
    out_c: "av.container.OutputContainer",
    v_in: Any,
    a_in: Any,
    v_out: Any,
    a_out: Any,
    start_sec: float,
    end_sec: float,
) -> None:
    """
    Remux packets without re-encoding (stream copy).
    Seeks to the keyframe at/before start_sec, copies packets until end_sec,
    and remaps PTS/DTS so the output starts from 0.
    ~50-100x faster than decode+encode for the same clip.
    """
    in_c.seek(int(start_sec * av.time_base))

    streams = [s for s in [v_in, a_in] if s is not None]
    v_base: int | None = None
    a_base: int | None = None

    for pkt in in_c.demux(*streams):
        if pkt.pts is None:
            continue

        if pkt.stream is v_in and v_out is not None:
            t = float(pkt.pts * v_in.time_base)
            if t < start_sec - 2.0:   # include up to 2 s of pre-roll for decoder
                continue
            if t > end_sec:
                continue
            if v_base is None:
                v_base = pkt.pts
            pkt.pts -= v_base
            pkt.dts = max(0, (pkt.dts - v_base)) if pkt.dts is not None else pkt.pts
            pkt.stream = v_out
            out_c.mux(pkt)

        elif pkt.stream is a_in and a_out is not None:
            t = float(pkt.pts * a_in.time_base)
            if t < start_sec - 2.0:
                continue
            if t > end_sec:
                continue
            if a_base is None:
                a_base = pkt.pts
            pkt.pts -= a_base
            pkt.dts = max(0, (pkt.dts - a_base)) if pkt.dts is not None else pkt.pts
            pkt.stream = a_out
            out_c.mux(pkt)


# ─── Encode helper for Short format ──────────────────────────────────────────

def _encode_short_trim(
    in_c: "av.container.InputContainer",
    out_c: "av.container.OutputContainer",
    v_in: Any,
    a_in: Any,
    start_sec: float,
    end_sec: float,
) -> None:
    """
    Decode + re-encode with crop/scale for 9:16 Shorts.
    Uses ultrafast preset and multi-threading for speed.
    """
    rate = 30
    if v_in.average_rate is not None:
        try:
            rate = int(float(v_in.average_rate))
        except Exception:
            pass

    orig_w = int(v_in.codec_context.width or 1920)
    orig_h = int(v_in.codec_context.height or 1080)

    out_v = out_c.add_stream("libx264", rate=rate)
    out_v.pix_fmt = "yuv420p"

    # Crop from landscape to portrait (9:16) only if needed
    needs_crop = orig_w > orig_h
    if needs_crop:
        out_v.width = 1080
        out_v.height = 1920
    else:
        out_v.width = orig_w
        out_v.height = orig_h

    # ultrafast = fastest encode, acceptable quality for social clips
    out_v.options = {
        "preset": "ultrafast",
        "crf": "20",
        "tune": "zerolatency",
        "threads": "0",  # auto thread count
    }

    out_a = None
    if a_in is not None:
        out_a = out_c.add_stream("aac", rate=int(a_in.rate or 44100))
        out_a.bit_rate = 128000
        try:
            if hasattr(a_in, "layout") and a_in.layout is not None:
                out_a.layout = getattr(a_in.layout, "name", "stereo")
        except Exception:
            out_a.layout = "stereo"

    # Build filtergraph only when crop is needed
    graph = av.filter.Graph()
    buf = graph.add_buffer(template=v_in)
    sink = graph.add("buffersink")
    if needs_crop:
        crop = graph.add("crop", "ih*9/16:ih")
        scale = graph.add("scale", "1080:1920:flags=bilinear")  # bilinear faster than lanczos
        buf.link_to(crop)
        crop.link_to(scale)
        scale.link_to(sink)
    else:
        buf.link_to(sink)
    graph.configure()

    in_c.seek(int(start_sec * av.time_base))

    streams = [v_in] + ([a_in] if a_in else [])
    v_pts_off: float | None = None
    a_pts_off: float | None = None
    done_v = False
    done_a = a_in is None

    for pkt in in_c.demux(*streams):
        for frame in pkt.decode():
            t = frame.time
            if t is None:
                continue
            if t < float(start_sec):
                continue
            if t > float(end_sec):
                if pkt.stream.type == "video":
                    done_v = True
                elif pkt.stream.type == "audio":
                    done_a = True
                continue

            if pkt.stream.type == "video":
                if v_pts_off is None:
                    v_pts_off = t
                frame.pts = int((t - v_pts_off) / float(v_in.time_base))
                graph.push(frame)
                while True:
                    try:
                        ff = graph.pull()
                    except (av.error.EOFError, Exception):
                        break
                    for op in out_v.encode(ff):
                        out_c.mux(op)

            elif pkt.stream.type == "audio" and out_a:
                if a_pts_off is None:
                    a_pts_off = t
                frame.pts = int((t - a_pts_off) / float(a_in.time_base))
                for op in out_a.encode(frame):
                    out_c.mux(op)

        if done_v and done_a:
            break

    # Flush filtergraph
    try:
        graph.push(None)
        while True:
            try:
                ff = graph.pull()
            except (av.error.EOFError, Exception):
                break
            for op in out_v.encode(ff):
                out_c.mux(op)
    except Exception:
        pass

    # Flush encoders
    for op in out_v.encode():
        out_c.mux(op)
    if out_a:
        for op in out_a.encode():
            out_c.mux(op)


# ─── Public API ───────────────────────────────────────────────────────────────

def pyav_trim(
    *,
    input_path: Path,
    output_path: Path,
    start_seconds: float,
    end_seconds: float,
    format_type: str = "regular",
) -> None:
    """
    Trim/clip a video file.

    Performance strategy:
      - regular (16:9): stream copy — NO re-encoding, ~50-100x faster.
      - short   (9:16): decode + ultrafast libx264 encode + crop/scale.
    """
    if float(end_seconds) <= float(start_seconds):
        raise ValueError("end_seconds harus lebih besar dari start_seconds")

    in_c = av.open(str(input_path))
    try:
        v_in = next((s for s in in_c.streams if s.type == "video"), None)
        if not v_in:
            raise RuntimeError("Video stream tidak ditemukan")
        a_in = next((s for s in in_c.streams if s.type == "audio"), None)

        out_c = av.open(str(output_path), mode="w")
        try:
            if format_type != "short":
                # ── FAST PATH: stream copy (no decode/encode) ──────────────
                v_out = out_c.add_stream(template=v_in)
                a_out = out_c.add_stream(template=a_in) if a_in else None
                _stream_copy_trim(in_c, out_c, v_in, a_in, v_out, a_out,
                                  float(start_seconds), float(end_seconds))
            else:
                # ── ENCODE PATH: needed for 9:16 crop/scale ───────────────
                _encode_short_trim(in_c, out_c, v_in, a_in,
                                   float(start_seconds), float(end_seconds))
        finally:
            out_c.close()
    finally:
        in_c.close()
