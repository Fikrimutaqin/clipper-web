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


def suggest_segments_from_file(
    *,
    input_path: Path,
    target_seconds: float,
    max_candidates: int = 3,
    max_scan_seconds: float = 900.0,
) -> list[dict[str, Any]]:
    """Suggest clip segments based on audio energy (preferred) or scene changes fallback."""
    dur = float(target_seconds)
    if dur <= 0:
        raise ValueError("target_seconds harus > 0")
    dur = min(dur, 180.0)

    container = av.open(str(input_path))
    try:
        audio_stream = next((s for s in container.streams if s.type == "audio"), None)
        video_stream = next((s for s in container.streams if s.type == "video"), None)
        if audio_stream is None and video_stream is None:
            raise RuntimeError("Tidak ada stream audio/video yang bisa dianalisis")

        if audio_stream is not None:
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
                raise RuntimeError("Gagal membaca audio untuk analisis")

            times = np.array([t for t, _ in samples], dtype=np.float32)
            energies = np.array([e for _, e in samples], dtype=np.float32)

            order = np.argsort(times)
            times = times[order]
            energies = energies[order]

            if energies.size < 5:
                peak_indices = np.array([int(np.argmax(energies))], dtype=np.int32)
            else:
                p = float(np.percentile(energies, 90))
                peak_indices = np.where(energies >= p)[0]
                if peak_indices.size == 0:
                    peak_indices = np.array([int(np.argmax(energies))], dtype=np.int32)

            candidates: list[dict[str, Any]] = []
            for idx in peak_indices.tolist():
                t = float(times[idx])
                start = max(0.0, t - dur * 0.25)
                end = start + dur
                score = float(energies[idx])
                candidates.append({"start_seconds": start, "end_seconds": end, "score": score})

            candidates.sort(key=lambda c: c["score"], reverse=True)
            picked: list[dict[str, Any]] = []
            for c in candidates:
                if len(picked) >= int(max_candidates):
                    break
                ok = True
                for p2 in picked:
                    if abs(float(p2["start_seconds"]) - float(c["start_seconds"])) < dur * 0.5:
                        ok = False
                        break
                if ok:
                    picked.append(c)
            if picked:
                return picked

        if video_stream is not None:
            container.seek(0)
            diffs: list[tuple[float, float]] = []
            prev = None
            frame_step = max(1, int(float(video_stream.average_rate or 30) // 2))
            i = 0
            for frame in container.decode(video_stream):
                t = frame.time
                if t is None:
                    continue
                if t > max_scan_seconds:
                    break
                i += 1
                if i % frame_step != 0:
                    continue
                arr = frame.to_ndarray(format="gray")
                arr = arr[::8, ::8].astype(np.float32, copy=False)
                if prev is not None:
                    diff = float(np.mean(np.abs(arr - prev)))
                    diffs.append((float(t), diff))
                prev = arr

            if not diffs:
                raise RuntimeError("Gagal membaca video untuk analisis")

            times = np.array([t for t, _ in diffs], dtype=np.float32)
            scores = np.array([d for _, d in diffs], dtype=np.float32)
            best = int(np.argmax(scores))
            t = float(times[best])
            start = max(0.0, t - dur * 0.25)
            end = start + dur
            return [{"start_seconds": start, "end_seconds": end, "score": float(scores[best])}]

        raise RuntimeError("Tidak ada stream yang bisa dianalisis")
    finally:
        container.close()


def pyav_trim(
    *,
    input_path: Path,
    output_path: Path,
    start_seconds: float,
    end_seconds: float,
    format_type: str = "regular",
) -> None:
    """Trim a video into a new MP4, optionally cropping to 9:16 for Shorts without stretching."""
    if float(end_seconds) <= float(start_seconds):
        raise ValueError("end_seconds harus lebih besar dari start_seconds")

    in_container = av.open(str(input_path))
    try:
        video_stream = next((s for s in in_container.streams if s.type == "video"), None)
        if not video_stream:
            raise RuntimeError("Video stream tidak ditemukan")
        audio_stream = next((s for s in in_container.streams if s.type == "audio"), None)

        out_container = av.open(str(output_path), mode="w")
        try:
            rate = 30
            if video_stream.average_rate is not None:
                try:
                    rate = int(float(video_stream.average_rate))
                except Exception:
                    rate = 30

            out_video = out_container.add_stream("libx264", rate=rate)
            orig_w = int(video_stream.codec_context.width or 1920)
            orig_h = int(video_stream.codec_context.height or 1080)

            graph = av.filter.Graph()
            buffer = graph.add_buffer(template=video_stream)
            sink = graph.add("buffersink")

            if format_type == "short" and orig_w > orig_h:
                out_video.width = 1080
                out_video.height = 1920
                crop = graph.add("crop", "ih*9/16:ih")
                scale = graph.add("scale", "1080:1920:flags=lanczos")
                buffer.link_to(crop)
                crop.link_to(scale)
                scale.link_to(sink)
            else:
                out_video.width = orig_w
                out_video.height = orig_h
                buffer.link_to(sink)

            graph.configure()

            out_video.pix_fmt = "yuv420p"
            out_video.options = {"preset": "slow", "crf": "16", "profile": "high"}

            out_audio = None
            if audio_stream is not None:
                out_audio = out_container.add_stream("aac", rate=int(audio_stream.rate or 44100))
                out_audio.bit_rate = 192000
                try:
                    if hasattr(audio_stream, "layout") and audio_stream.layout is not None:
                        out_audio.layout = getattr(audio_stream.layout, "name", "stereo")
                except Exception:
                    out_audio.layout = "stereo"

            in_container.seek(int(float(start_seconds) * av.time_base))

            done_video = False
            done_audio = audio_stream is None
            streams = [video_stream] + ([audio_stream] if audio_stream is not None else [])

            for packet in in_container.demux(streams):
                for frame in packet.decode():
                    t = frame.time
                    if t is None:
                        continue
                    if t < float(start_seconds):
                        continue
                    if t > float(end_seconds):
                        if packet.stream.type == "video":
                            done_video = True
                        elif packet.stream.type == "audio":
                            done_audio = True
                        continue

                    if packet.stream.type == "video":
                        graph.push(frame)
                        while True:
                            try:
                                filtered_frame = graph.pull()
                            except av.error.EOFError:
                                break
                            except Exception:
                                break
                            for out_packet in out_video.encode(filtered_frame):
                                out_container.mux(out_packet)
                    elif packet.stream.type == "audio" and out_audio is not None:
                        for out_packet in out_audio.encode(frame):
                            out_container.mux(out_packet)

                if done_video and done_audio:
                    break

            try:
                graph.push(None)
                while True:
                    try:
                        filtered_frame = graph.pull()
                    except av.error.EOFError:
                        break
                    except Exception:
                        break
                    for out_packet in out_video.encode(filtered_frame):
                        out_container.mux(out_packet)
            except Exception:
                pass

            for out_packet in out_video.encode():
                out_container.mux(out_packet)
            if out_audio is not None:
                for out_packet in out_audio.encode():
                    out_container.mux(out_packet)
        finally:
            out_container.close()
    finally:
        in_container.close()
