"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Video, Search, Download, Loader2, Zap, Scissors, Play, Send,
  ExternalLink, CheckCircle2, AlertCircle, Sparkles, Image as ImageIcon,
  Copy, Clock, FileText, ChevronRight, BarChart2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import api from "@/lib/axios";

interface VideoItem {
  id: string;
  snippet: { title: string; thumbnails: { medium: { url: string } }; channelTitle: string };
  statistics: { viewCount: string };
}

const STEPS = [
  { id: 1, icon: "🔥", label: "AI Detect" },
  { id: 2, icon: "✂️", label: "Auto Cut" },
  { id: 3, icon: "🧠", label: "Content" },
  { id: 4, icon: "🎬", label: "Subtitles" },
  { id: 5, icon: "📤", label: "Export" },
];

const PLATFORM_CARDS = [
  { key: "YT", label: "YouTube", icon: "🎬", bg: "bg-red-50", desc: "Upload ke YouTube Shorts & video biasa", available: true },
  { key: "IG", label: "Instagram", icon: "📸", bg: "bg-pink-50", desc: "Posting ke Reels & feed Instagram", available: false },
  { key: "TT", label: "TikTok", icon: "🎵", bg: "bg-gray-100", desc: "Upload langsung ke akun TikTok kamu", available: false },
  { key: "FB", label: "Facebook", icon: "👥", bg: "bg-blue-50", desc: "Share ke Facebook Page & Reels", available: false },
];

const fmtSec = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
const toNum = (v: string, fb: number) => { const n = Number(v); return isFinite(n) ? n : fb; };

/** Normalize any Axios/FastAPI error into a plain string for React rendering */
const extractError = (e: any, fallback = "Terjadi kesalahan."): string => {
  const detail = e?.response?.data?.detail;
  if (Array.isArray(detail))
    return detail.map((d: any) => (typeof d === "object" ? d.msg ?? JSON.stringify(d) : String(d))).join("; ");
  if (typeof detail === "string") return detail;
  if (typeof detail === "object" && detail !== null) return detail.msg ?? JSON.stringify(detail);
  if (typeof e?.message === "string") return e.message;
  return fallback;
};

const viralBadge = (score: number) =>
  score >= 75 ? "bg-green-100 text-green-700 border-green-300"
    : score >= 50 ? "bg-orange-100 text-orange-700 border-orange-300"
      : "bg-gray-100 text-gray-600 border-gray-300";

const typeColor: Record<string, string> = {
  emotion: "border-l-pink-400",
  punchline: "border-l-orange-400",
  insight: "border-l-blue-400",
  hook: "border-l-purple-400",
  intro: "border-l-yellow-400",
  value: "border-l-emerald-400",
  cta: "border-l-red-400",
};

export default function ClipperPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const apiBase = (api.defaults.baseURL || "").toString().replace(/\/$/, "");
  const pollRef = useRef<number | null>(null);

  // Platform
  const [sourcePlatform, setSourcePlatform] = useState<"YT" | "TT" | "IG" | "FB">("YT");
  const [publishPlatform, setPublishPlatform] = useState<"YT" | "TT" | "IG" | "FB">("YT");
  const [ytConnected, setYtConnected] = useState(false);
  const [platformStatus, setPlatformStatus] = useState<Record<string, boolean>>({ YT: false, TT: false, IG: false, FB: false });

  // Search / Download
  const [searchUrl, setSearchUrl] = useState("");
  const [searchQuery, setSearchQuery] = useState("");
  const [videos, setVideos] = useState<VideoItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState<{ id: string; progress: number; status?: string; task_id?: string } | null>(null);
  const [error, setError] = useState("");
  const [viewMode, setViewMode] = useState<"trending" | "search">("trending");

  // Wizard core
  const [wizardStep, setWizardStep] = useState(1);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [videoDuration, setVideoDuration] = useState<number | null>(null);

  // Step 1 – AI Detect
  const [format, setFormat] = useState<"short" | "regular">("short");
  const [suggestions, setSuggestions] = useState<any[]>([]);
  const [detecting, setDetecting] = useState(false);
  const [pickedSuggestion, setPickedSuggestion] = useState<any>(null);

  // Step 2 – Auto Cut
  const [trimStart, setTrimStart] = useState(0);
  const [trimEnd, setTrimEnd] = useState(60);
  const [trimming, setTrimming] = useState(false);
  const [clipResult, setClipResult] = useState<{ clip_id: string; url: string; full_url?: string } | null>(null);

  // Step 3 – Content
  const [viralTitles, setViralTitles] = useState<any[]>([]);
  const [viralDescs, setViralDescs] = useState<any[]>([]);
  const [generatingContent, setGeneratingContent] = useState(false);
  const [thumbnailUrl, setThumbnailUrl] = useState<string | null>(null);
  const [thumbError, setThumbError] = useState("");
  const [generatingThumb, setGeneratingThumb] = useState(false);
  const [copiedTitle, setCopiedTitle] = useState<string | null>(null);
  const [copiedDesc, setCopiedDesc] = useState<string | null>(null);
  const [uploadTitle, setUploadTitle] = useState("ClipFIX Clip");
  const [uploadDesc, setUploadDesc] = useState("Generated by ClipFIX.");

  // Step 4 – Subtitles
  const [subtitleData, setSubtitleData] = useState<{ available: boolean; entries: any[]; } | null>(null);
  const [loadingSubs, setLoadingSubs] = useState(false);

  // Step 5 – Export
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<{ url: string; youtube_video_id: string } | null>(null);
  const [activeJobs, setActiveJobs] = useState<any[]>([]);
  const [selectedJobId, setSelectedJobId] = useState("");
  const [submittingJob, setSubmittingJob] = useState(false);

  // ── Computed ───────────────────────────────────────────────────────────────
  const minDur = format === "regular" ? 600 : 20;
  const clipDur = trimEnd - trimStart;
  const durWarn = clipDur < minDur
    ? `Min durasi ${format === "regular" ? "10 menit" : "20 detik"} untuk ${format}. Sekarang: ${clipDur}s.`
    : null;
  const clipUrl = clipResult ? (clipResult.full_url || `${apiBase}${clipResult.url}`) : "";

  // ── Effects ────────────────────────────────────────────────────────────────
  useEffect(() => {
    // Check YouTube connection — endpoint is /status, not /me
    api.get("/api/youtube/status")
      .then(r => {
        const connected = r.data?.data?.connected === true;
        setYtConnected(connected);
        setPlatformStatus(p => ({ ...p, YT: connected }));
      })
      .catch(() => {
        setYtConnected(false);
        setPlatformStatus(p => ({ ...p, YT: false }));
      });
    // Trending videos — endpoint is /discover, not /trending
    api.get("/api/youtube/discover").then(r => setVideos(r.data?.data?.items || [])).catch(() => { });
  }, []);


  useEffect(() => {
    const clipExportId = searchParams.get("clip_export");
    const exportFilename = searchParams.get("filename") || "Video Clip";
    const exportUrl = searchParams.get("url") || "";

    if (clipExportId && exportUrl) {
      setSelectedTaskId("clip-" + clipExportId); // dummy task_id to pass validation
      setClipResult({ clip_id: clipExportId, url: exportUrl, full_url: exportUrl });
      setUploadTitle(exportFilename.replace(/\.mp4$/i, ""));
      setUploadDesc("Diposting secara otomatis melalui ClipFIX AI! 🔥 #shorts #viral");
      setWizardStep(5);
      return;
    }

    const tid = searchParams.get("task_id");
    if (!tid) return;

    const activate = () => {
      setSelectedTaskId(tid);
      setWizardStep(1);
    };

    // Try status endpoint first (now with auto-recovery on BE side)
    api.get(`/api/youtube/download/${tid}`)
      .then(r => {
        const status = r.data?.data?.status;
        // Accept 'done' — or a recovered task that has file_path
        if (status === "done" || r.data?.data?.file_path) {
          activate();
        } else {
          // Fallback: trust the task_id from Media Library and let wizard
          // endpoints handle auto-recovery when user clicks "Detect Highlights"
          activate();
        }
      })
      .catch(() => {
        // Even if status check fails, activate — the suggest/trim endpoints
        // will auto-recover from disk and show proper errors if needed
        activate();
      });
  }, [searchParams]);

  // Reset wizard when new video is selected
  useEffect(() => {
    if (!selectedTaskId) return;
    if (selectedTaskId.startsWith("clip-")) return; // Skip reset for direct clip export
    setSuggestions([]);
    setPickedSuggestion(null);
    setClipResult(null);
    setViralTitles([]);
    setViralDescs([]);
    setThumbnailUrl(null);
    setSubtitleData(null);
    setWizardStep(1);
  }, [selectedTaskId]);

  // Auto-advance to step 3 when clip is created
  useEffect(() => {
    if (clipResult && wizardStep === 2) setWizardStep(3);
  }, [clipResult, wizardStep]);

  // Protect against navigation
  useEffect(() => {
    // Only warn if they actually started working (wizardStep > 1)
    const isEditing = wizardStep > 1;
    if (!isEditing) return;

    // 1. Warn on browser refresh, tab close, or manual URL change
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handleBeforeUnload);

    // 2. Warn on client-side navigation (Links & Buttons)
    const handleNavigationClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      
      // Is it a sidebar link or a button outside the editor?
      const anchor = target.closest("a");
      const isExternalLink = anchor && anchor.getAttribute("target") === "_blank";
      const href = anchor ? anchor.getAttribute("href") : null;
      const isSamePage = href && (href.startsWith("#") || href.startsWith("/dashboard/clipper"));

      // Intercept profile button or any external anchor
      const isOutsideButton = target.closest('[role="button"]') && !target.closest('#clip-editor');
      
      if (isExternalLink || isSamePage) return;

      if ((anchor && href) || isOutsideButton) {
        if (!confirm("Kamu sedang mengedit klip. Jika keluar sekarang, progress edit akan hilang.\n\nYakin ingin keluar dari Editor?")) {
          e.preventDefault();
          e.stopPropagation();
        }
      }
    };

    document.addEventListener("click", handleNavigationClick, { capture: true });

    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload);
      document.removeEventListener("click", handleNavigationClick, { capture: true });
    };
  }, [wizardStep]);


  // Download polling
  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  // ── Handlers ───────────────────────────────────────────────────────────────
  const handleSearch = async () => {

    if (!searchQuery.trim()) return;
    setLoading(true); setError(""); setViewMode("search");
    try {
      const res = await api.get("/api/youtube/search", { params: { q: searchQuery, maxResults: 8 } });
      setVideos(res.data?.data?.items || []);
    } catch (e: any) {
      setError(extractError(e, "Gagal mencari video."));
    } finally { setLoading(false); }
  };

  const handleDownload = async (videoId: string) => {
    const url = searchUrl.trim() || `https://www.youtube.com/watch?v=${videoId}`;
    setDownloading({ id: videoId, progress: 0 });
    setError("");
    try {
      const res = await api.post("/api/youtube/download", { url });
      const task_id = res.data?.data?.task_id;
      if (!task_id) throw new Error("No task_id");
      setDownloading(p => ({ ...p!, task_id, status: "downloading" }));
      pollRef.current = window.setInterval(async () => {
        try {
          const pr = await api.get(`/api/youtube/download/${task_id}`);
          const d = pr.data?.data;
          setDownloading(p => ({ ...p!, progress: d?.progress ?? 0, status: d?.status }));
          if (d?.status === "done") {
            clearInterval(pollRef.current!);
            setDownloading(null);
            setSelectedTaskId(task_id);
          } else if (d?.status === "error") {
            clearInterval(pollRef.current!);
            setError(`Download error: ${d?.error || "Unknown"}`);
            setDownloading(null);
          }
        } catch { clearInterval(pollRef.current!); setDownloading(null); setError("Gagal polling status."); }
      }, 1500);
    } catch (e: any) {
      setError(extractError(e, "Gagal download."));
      setDownloading(null);
    }
  };

  const detectHighlights = async () => {
    if (!selectedTaskId) return;
    setDetecting(true); setSuggestions([]);
    try {
      const res = await api.get(`/api/youtube/suggest/${selectedTaskId}`, { params: { format_type: format } });
      setSuggestions(res.data.data.suggestions || []);
      setVideoDuration(res.data.data.duration ?? null);
    } catch (e: any) {
      setError(extractError(e, "Gagal mendeteksi highlight."));
    } finally { setDetecting(false); }
  };

  const pickSuggestion = (s: any) => {
    setPickedSuggestion(s);
    setTrimStart(Math.floor(s.start_seconds));
    setTrimEnd(Math.ceil(s.end_seconds));
    setWizardStep(2);
  };

  const handleTrim = async () => {
    if (!selectedTaskId) return;
    const maxDur = typeof videoDuration === "number" && videoDuration > 0 ? videoDuration : Infinity;
    const st = clamp(trimStart, 0, maxDur);
    const en = clamp(trimEnd, 0, maxDur);
    if (en <= st) { setError("End harus lebih besar dari start."); return; }
    setTrimming(true); setError("");
    try {
      const res = await api.post("/api/youtube/trim", {
        task_id: selectedTaskId, start_seconds: st, end_seconds: en, format_type: format,
      });
      setClipResult(res.data.data);
    } catch (e: any) {
      setError(extractError(e, "Gagal memproses clip."));
    } finally { setTrimming(false); }
  };

  const generateContent = async () => {
    if (!selectedTaskId) return;
    setGeneratingContent(true);
    try {
      const res = await api.get(`/api/youtube/title/${selectedTaskId}`, { params: { format_type: format } });
      const titles: any[] = res.data.data.titles || [];
      const vTitle: string = res.data.data.video_title || "";
      setViralTitles(titles);
      if (titles.length > 0) setUploadTitle(titles[0].title);
      const mm = (s: number) => fmtSec(s);
      const descs = titles.slice(0, 3).map((t: any) => ({
        type: t.type,
        description: t.type === "emotion"
          ? `Momen emosional dari "${vTitle}" — bikin speechless! ❤️\n\n⏱ ${mm(trimStart)} – ${mm(trimEnd)}\n\n#viral #emosional #shorts`
          : t.type === "punchline"
            ? `Plot twist dari "${vTitle}" yang gak ada yang nyangka 🤯\n\n⏱ ${mm(trimStart)} – ${mm(trimEnd)}\n\n#plottwist #viral #shorts`
            : `Insight terbaik dari "${vTitle}" 💡\n\n⏱ ${mm(trimStart)} – ${mm(trimEnd)}\n\n#insight #edukasi #viral`,
      }));
      setViralDescs(descs);
      if (descs.length > 0) setUploadDesc(descs[0].description);
    } catch { /* silent */ }
    finally { setGeneratingContent(false); }
  };

  const generateThumbnail = async () => {
    if (!selectedTaskId) return;
    setGeneratingThumb(true); setThumbnailUrl(null); setThumbError("");
    if (thumbnailUrl?.startsWith("blob:")) URL.revokeObjectURL(thumbnailUrl);
    try {
      const res = await api.get(`/api/youtube/thumbnail/${selectedTaskId}`, {
        params: { at: Math.max(0, trimStart) }, responseType: "blob",
      });
      setThumbnailUrl(URL.createObjectURL(res.data));
    } catch (e: any) {
      const txt = e.response?.data ? await e.response.data.text?.() : "";
      setThumbError(extractError(e, txt || "Gagal generate thumbnail."));
    } finally { setGeneratingThumb(false); }
  };

  const fetchSubtitles = async () => {
    if (!selectedTaskId || subtitleData !== null) return;
    setLoadingSubs(true);
    try {
      const res = await api.get(`/api/youtube/subtitles/${selectedTaskId}`, {
        params: { start: trimStart, end: trimEnd },
      });
      setSubtitleData(res.data.data);
    } catch { setSubtitleData({ available: false, entries: [] }); }
    finally { setLoadingSubs(false); }
  };

  const handleUpload = async () => {
    if (!clipResult) return;
    setUploading(true);
    try {
      const res = await api.post("/api/youtube/upload-clip", {
        clip_id: clipResult.clip_id, title: uploadTitle, description: uploadDesc,
      });
      setUploadResult(res.data.data);
    } catch (e: any) {
      setError(extractError(e, "Gagal upload."));
    } finally { setUploading(false); }
  };

  const copyText = (text: string, setter: (v: string | null) => void) => {
    navigator.clipboard.writeText(text).catch(() => { });
    setter(text);
    setTimeout(() => setter(null), 1500);
  };

  const handleConnect = (platform: string) => {
    if (platform !== "YT") {
      alert("Integrasi platform ini belum tersedia. (Coming soon)");
      return;
    }
    const redirectUrl = selectedTaskId
      ? `${window.location.origin}/dashboard/clipper?task_id=${selectedTaskId}`
      : `${window.location.origin}/dashboard/clipper`;
    window.location.href = `${apiBase}/api/youtube/connect?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  // ── Left panel helpers ─────────────────────────────────────────────────────
  const PLATFORMS = ["YT", "TT", "IG", "FB"] as const;

  // ── JSX ────────────────────────────────────────────────────────────────────
  return (
    <div className="h-screen flex flex-col bg-gray-50 rounded-lg">
      {/* Topbar */}
      <div className="shrink-0 border-b bg-white px-8 py-4 flex items-center gap-3 rounded-lg">
        <Video className="h-5 w-5 text-violet-600" />
        <h1 className="text-lg font-bold text-gray-900">Clip Editor</h1>
        <span className="text-xs text-gray-400 ml-2 hidden sm:block">Pipeline AI → Auto Cut → Subtitle → Export</span>

        {/* Platform badges — right side */}
        <div className="ml-auto flex items-center gap-2">
          {PLATFORM_CARDS.map(pl => {
            const connected = platformStatus[pl.key];
            return (
              <button
                key={pl.key}
                title={connected ? `${pl.label} terhubung` : `Connect ${pl.label}`}
                onClick={() => !connected && handleConnect(pl.key)}
                className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[11px] font-semibold transition-all ${connected
                  ? "bg-green-50 border-green-300 text-green-700 cursor-default"
                  : "bg-gray-50 border-gray-200 text-gray-400 hover:border-gray-400 hover:text-gray-600 cursor-pointer"
                  }`}>
                <span>{pl.icon}</span>
                <span className="hidden md:inline">{pl.key}</span>
                {connected && <CheckCircle2 className="h-3 w-3" />}
              </button>
            );
          })}
        </div>
      </div>

      <div className="flex-1 flex gap-0 min-h-0 rounded-lg">
        {/* ═══ LEFT PANEL ═══ */}
        <div className="w-80 shrink-0 border-r bg-white flex flex-col min-h-0">
          <div className="p-4 border-b space-y-3">
            {/* Source platform */}
            <div className="flex gap-1">
              {PLATFORMS.map(p => (
                <button key={p} onClick={() => setSourcePlatform(p)}
                  className={`flex-1 text-[10px] py-1 rounded-lg font-semibold transition-colors ${sourcePlatform === p ? "bg-violet-600 text-white" : "bg-gray-100 text-gray-500 hover:bg-gray-200"}`}>
                  {p}
                </button>
              ))}
            </div>
            {/* URL input */}
            <div className="flex gap-2">
              <Input value={searchUrl} onChange={e => setSearchUrl(e.target.value)}
                placeholder="Paste URL video..." className="text-sm h-9 rounded-xl" />
              <Button size="sm" className="rounded-xl h-9 px-3" onClick={() => {
                if (searchUrl.trim()) handleDownload("");
              }}>
                <Download className="h-4 w-4" />
              </Button>
            </div>
            {/* Search */}
            <div className="flex gap-2">
              <Input value={searchQuery} onChange={e => setSearchQuery(e.target.value)}
                onKeyDown={e => e.key === "Enter" && handleSearch()}
                placeholder="Cari video YouTube..." className="text-sm h-9 rounded-xl" />
              <Button size="sm" variant="outline" className="rounded-xl h-9 px-3" onClick={handleSearch}>
                <Search className="h-4 w-4" />
              </Button>
            </div>
          </div>

          {/* Download progress */}
          {downloading && (
            <div className="mx-4 mt-3 p-3 rounded-xl border bg-violet-50">
              <div className="text-xs font-semibold text-violet-700 mb-1">
                {downloading.status === "merging" ? "Merging…" : `Downloading… ${downloading.progress}%`}
              </div>
              <div className="w-full h-2 bg-violet-200 rounded-full overflow-hidden">
                <div className="h-full bg-violet-500 transition-all" style={{ width: `${downloading.progress}%` }} />
              </div>
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="mx-4 mt-3 flex gap-2 items-start text-xs text-red-600 bg-red-50 border border-red-200 rounded-xl p-3">
              <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" /> {error}
            </div>
          )}

          {/* Video list */}
          <div className="flex-1 overflow-y-auto p-4 space-y-2">
            {loading ? (
              <div className="flex justify-center pt-10"><Loader2 className="h-5 w-5 animate-spin text-gray-400" /></div>
            ) : videos.map(v => (
              <div key={v.id} className="rounded-xl border bg-white overflow-hidden hover:shadow-md transition-shadow cursor-pointer group">
                <img src={v.snippet.thumbnails.medium.url} alt={v.snippet.title}
                  className="w-full aspect-video object-cover" />
                <div className="p-2 space-y-1">
                  <p className="text-xs font-semibold leading-snug line-clamp-2">{v.snippet.title}</p>
                  <p className="text-[10px] text-gray-400">{v.snippet.channelTitle}</p>
                  <Button size="sm" className="w-full rounded-lg h-7 text-xs"
                    onClick={() => handleDownload(v.id)}
                    disabled={!!downloading}>
                    <Download className="h-3 w-3 mr-1" />Download
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* ═══ RIGHT PANEL – Wizard ═══ */}
        <div id="clip-editor" className="flex-1 flex flex-col min-h-0 rounded-lg">
          {!selectedTaskId ? (
            (() => {
              const anyConnected = Object.values(platformStatus).some(v => v);
              return anyConnected ? (
                /* ── Already connected: simple pick-video empty state ── */
                <div className="flex-1 flex flex-col items-center justify-center text-center gap-4 p-12">
                  <div className="w-20 h-20 rounded-3xl bg-violet-50 flex items-center justify-center text-4xl">🎬</div>
                  {/* Connected badges */}
                  <div className="flex gap-2 justify-center">
                    {PLATFORM_CARDS.filter(p => platformStatus[p.key]).map(p => (
                      <span key={p.key} className="flex items-center gap-1 text-xs font-semibold bg-green-50 border border-green-200 text-green-700 rounded-full px-3 py-1">
                        {p.icon} {p.label} <CheckCircle2 className="h-3 w-3" />
                      </span>
                    ))}
                  </div>
                  <div>
                    <h2 className="text-xl font-bold text-gray-800">Siap untuk Clipping!</h2>
                    <p className="text-sm text-gray-500 mt-1">Platform sudah terhubung. Paste URL atau pilih video dari panel kiri.</p>
                  </div>
                  <div className="flex flex-wrap gap-2 justify-center text-xs text-gray-400">
                    {STEPS.map((s, i) => (
                      <span key={i} className="flex items-center gap-1">
                        {s.icon} <span>{s.label}</span>
                        {i < STEPS.length - 1 && <ChevronRight className="h-3 w-3" />}
                      </span>
                    ))}
                  </div>
                </div>
              ) : (
                /* ── Not connected: show connect platform screen ── */
                <div className="flex-1 overflow-y-auto p-8">
                  <div className="max-w-lg mx-auto space-y-6">
                    {/* Header */}
                    <div className="text-center space-y-1">
                      <div className="text-4xl mb-3">🔗</div>
                      <h2 className="text-2xl font-bold text-gray-900">Hubungkan Platform</h2>
                      <p className="text-sm text-gray-500">Koneksikan akun agar clip kamu bisa langsung diupload setelah selesai diedit.</p>
                    </div>

                    {/* Platform cards */}
                    <div className="space-y-3">
                      {PLATFORM_CARDS.map(pl => {
                        const connected = platformStatus[pl.key];
                        return (
                          <div key={pl.key}
                            className={`rounded-2xl border-2 p-4 flex items-center gap-4 transition-all ${connected ? "border-green-200 bg-green-50" : "border-gray-200 bg-white hover:border-gray-300"}`}>
                            <div className={`w-12 h-12 rounded-2xl flex items-center justify-center text-2xl shrink-0 ${pl.bg}`}>
                              {pl.icon}
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2">
                                <span className="font-bold text-gray-900">{pl.label}</span>
                                {connected && (
                                  <span className="text-[10px] font-bold bg-green-100 text-green-700 border border-green-200 rounded-full px-2 py-0.5 flex items-center gap-1">
                                    <CheckCircle2 className="h-3 w-3" /> Terhubung
                                  </span>
                                )}
                                {!pl.available && (
                                  <span className="text-[10px] font-semibold bg-gray-100 text-gray-500 border border-gray-200 rounded-full px-2 py-0.5">Coming Soon</span>
                                )}
                              </div>
                              <p className="text-xs text-gray-400 mt-0.5">{pl.desc}</p>
                            </div>
                            {pl.available && (
                              connected ? (
                                <span className="text-xs text-green-600 font-semibold shrink-0">✓ Siap dipakai</span>
                              ) : (
                                <Button size="sm" className="rounded-xl shrink-0 gap-1.5"
                                  onClick={() => handleConnect(pl.key)}>
                                  Connect
                                </Button>
                              )
                            )}
                          </div>
                        );
                      })}
                    </div>

                    {/* Skip CTA */}
                    <div className="pt-2 border-t">
                      <p className="text-xs text-center text-gray-400 mb-4">Koneksi bersifat opsional — kamu bisa skip dan tetap download clip secara manual.</p>
                      <div className="text-center space-y-2">
                        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Atau langsung mulai:</p>
                        <div className="flex flex-wrap gap-2 justify-center text-xs text-gray-400">
                          {STEPS.map((s, i) => (
                            <span key={i} className="flex items-center gap-1">
                              {s.icon} <span>{s.label}</span>
                              {i < STEPS.length - 1 && <ChevronRight className="h-3 w-3" />}
                            </span>
                          ))}
                        </div>
                        <p className="text-sm text-gray-500 mt-2">Paste URL atau pilih video dari panel kiri untuk mulai.</p>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })()
          ) : (
            <div className="flex-1 flex flex-col min-h-0">
              {/* Step Progress */}
              <div className="shrink-0 border-b bg-white px-6 py-3">
                <div className="flex items-center gap-1">
                  {STEPS.map((s, i) => {
                    const done = wizardStep > s.id;
                    const active = wizardStep === s.id;
                    return (
                      <div key={s.id} className="flex items-center gap-1">
                        <button
                          onClick={() => done && setWizardStep(s.id)}
                          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold transition-all ${active ? "bg-violet-600 text-white shadow-sm"
                            : done ? "bg-violet-100 text-violet-700 cursor-pointer hover:bg-violet-200"
                              : "bg-gray-100 text-gray-400 cursor-not-allowed"}`}>
                          {done ? <CheckCircle2 className="h-3 w-3" /> : <span>{s.icon}</span>}
                          <span className="hidden sm:inline">{s.label}</span>
                        </button>
                        {i < STEPS.length - 1 && <ChevronRight className="h-3.5 w-3.5 text-gray-300" />}
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Step Content */}
              <div className="flex-1 overflow-y-auto p-6">

                {/* ── STEP 1: AI Detect ── */}
                {wizardStep === 1 && (
                  <div className="max-w-2xl space-y-5">
                    <div>
                      <h2 className="text-xl font-bold flex items-center gap-2">🔥 AI Detect Highlight</h2>
                      <p className="text-sm text-gray-500 mt-0.5">AI menganalisis audio energy untuk temukan momen paling viral.</p>
                    </div>
                    {/* Format */}
                    <div className="flex gap-3">
                      {[{ k: "short", l: "9:16 Short", d: "(min 20s)" }, { k: "regular", l: "16:9 Regular", d: "(min 10 min)" }].map(f => (
                        <button key={f.k} onClick={() => setFormat(f.k as any)}
                          className={`flex-1 rounded-xl border-2 py-3 px-4 text-sm font-semibold transition-all ${format === f.k ? "border-violet-500 bg-violet-50 text-violet-700" : "border-gray-200 text-gray-600 hover:border-gray-300"}`}>
                          {f.l} <span className="text-xs opacity-60">{f.d}</span>
                        </button>
                      ))}
                    </div>
                    {/* Detect button */}
                    <Button className="w-full py-5 rounded-xl text-base gap-2" onClick={detectHighlights} disabled={detecting}>
                      {detecting ? <Loader2 className="h-5 w-5 animate-spin" /> : <Zap className="h-5 w-5" />}
                      {detecting ? "Menganalisis video..." : "⚡ Detect Highlights"}
                    </Button>
                    {/* Suggestion cards */}
                    {suggestions.length > 0 && (
                      <div className="space-y-3">
                        <p className="text-xs font-bold text-gray-400 uppercase tracking-wider">
                          {suggestions.length} Highlight Ditemukan — Pilih satu untuk lanjut
                        </p>
                        {suggestions.map((s, i) => (
                          <div key={i} onClick={() => pickSuggestion(s)}
                            className={`rounded-2xl border-2 border-l-4 bg-white p-4 cursor-pointer hover:border-violet-300 hover:shadow-md transition-all ${typeColor[s.type] || "border-l-gray-300"}`}>
                            <div className="flex items-center justify-between mb-2">
                              <span className="font-semibold text-sm">{s.label || `Segment ${i + 1}`}</span>
                              <span className={`text-xs font-bold px-2 py-0.5 rounded-full border ${viralBadge(s.viral_score ?? 0)}`}>
                                ⚡ {s.viral_score ?? "—"}% Viral
                              </span>
                            </div>
                            <div className="flex items-center gap-4 text-xs text-gray-500">
                              <span className="flex items-center gap-1"><Clock className="h-3 w-3" />{fmtSec(s.start_seconds)} – {fmtSec(s.end_seconds)}</span>
                              <span className="flex items-center gap-1"><BarChart2 className="h-3 w-3" />{Math.round(s.end_seconds - s.start_seconds)}s</span>
                            </div>
                            {/* Viral score bar */}
                            <div className="mt-3 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                              <div className={`h-full rounded-full transition-all ${(s.viral_score ?? 0) >= 75 ? "bg-green-500" : (s.viral_score ?? 0) >= 50 ? "bg-orange-400" : "bg-gray-400"}`}
                                style={{ width: `${s.viral_score ?? 0}%` }} />
                            </div>
                            <div className="mt-2 flex justify-end">
                              <Button size="sm" className="rounded-full text-xs h-7 gap-1">
                                Pilih Clip Ini <ChevronRight className="h-3 w-3" />
                              </Button>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* ── STEP 2: Auto Cut ── */}
                {wizardStep === 2 && (
                  <div className="max-w-lg space-y-5">
                    <div>
                      <h2 className="text-xl font-bold flex items-center gap-2">✂️ Auto Cut Clip</h2>
                      <p className="text-sm text-gray-500 mt-0.5">Review dan sesuaikan waktu potongan, lalu proses.</p>
                    </div>
                    {/* Selected segment info */}
                    {pickedSuggestion && (
                      <div className={`rounded-2xl border-l-4 bg-white border p-4 ${typeColor[pickedSuggestion.type] || "border-l-gray-300"}`}>
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-sm">{pickedSuggestion.label}</span>
                          <span className={`text-xs font-bold px-2 py-0.5 rounded-full border ${viralBadge(pickedSuggestion.viral_score ?? 0)}`}>
                            ⚡ {pickedSuggestion.viral_score ?? 0}% Viral
                          </span>
                        </div>
                        <div className="text-xs text-gray-500 mt-1">
                          Saran: {fmtSec(pickedSuggestion.start_seconds)} – {fmtSec(pickedSuggestion.end_seconds)} ({Math.round(pickedSuggestion.end_seconds - pickedSuggestion.start_seconds)}s)
                        </div>
                      </div>
                    )}
                    {/* Time inputs */}
                    <div className="grid grid-cols-2 gap-3">
                      <div className="space-y-1">
                        <label className="text-xs font-semibold text-gray-600">Start (detik)</label>
                        <Input type="number" value={trimStart}
                          onChange={e => setTrimStart(clamp(toNum(e.target.value, trimStart), 0, videoDuration || Infinity))}
                          className="rounded-xl" />
                      </div>
                      <div className="space-y-1">
                        <label className="text-xs font-semibold text-gray-600">End (detik)</label>
                        <Input type="number" value={trimEnd}
                          onChange={e => setTrimEnd(clamp(toNum(e.target.value, trimEnd), 0, videoDuration || Infinity))}
                          className="rounded-xl" />
                      </div>
                    </div>
                    <div className="text-sm text-gray-500">
                      Durasi: <strong>{clipDur}s</strong> ({fmtSec(trimStart)} – {fmtSec(trimEnd)})
                    </div>
                    {durWarn && (
                      <div className="flex items-center gap-2 text-amber-700 bg-amber-50 border border-amber-200 rounded-xl px-3 py-2 text-xs">
                        <Clock className="h-3.5 w-3.5 shrink-0" />{durWarn}
                      </div>
                    )}
                    <Button className="w-full py-5 rounded-xl text-base gap-2"
                      onClick={handleTrim} disabled={trimming || !!durWarn}>
                      {trimming ? <Loader2 className="h-5 w-5 animate-spin" /> : <Scissors className="h-5 w-5" />}
                      {trimming ? "Memproses clip..." : "✂️ Cut Clip Sekarang"}
                    </Button>
                    <button onClick={() => setWizardStep(1)}
                      className="text-xs text-gray-400 hover:text-gray-600 transition-colors">
                      ← Kembali pilih highlight lain
                    </button>
                  </div>
                )}

                {/* ── STEP 3: Content ── */}
                {wizardStep === 3 && (
                  <div className="max-w-xl space-y-5">
                    <div>
                      <h2 className="text-xl font-bold flex items-center gap-2">🧠 Auto Hook Generator</h2>
                      <p className="text-sm text-gray-500 mt-0.5">Generate judul viral, thumbnail, dan deskripsi untuk clip kamu.</p>
                    </div>
                    {/* Generate button */}
                    <Button className="w-full py-4 rounded-xl gap-2" onClick={generateContent} disabled={generatingContent}>
                      {generatingContent ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                      {generatingContent ? "Generating..." : "✨ Generate Semua Content"}
                    </Button>
                    {/* Titles */}
                    {viralTitles.length > 0 && (
                      <div className="space-y-2">
                        <p className="text-xs font-bold text-gray-400 uppercase tracking-wider">Judul Viral — Klik untuk pakai</p>
                        {viralTitles.slice(0, 6).map((t, i) => {
                          const c = t.type === "emotion" ? "bg-pink-50 border-pink-200 text-pink-700" : t.type === "punchline" ? "bg-orange-50 border-orange-200 text-orange-700" : "bg-blue-50 border-blue-200 text-blue-700";
                          return (
                            <div key={i} onClick={() => copyText(t.title, setCopiedTitle)}
                              className={`rounded-xl border px-3 py-2 text-xs cursor-pointer hover:opacity-80 transition-opacity flex items-start gap-2 ${c}`}>
                              <div className="flex-1 font-medium leading-snug">{t.title}</div>
                              {copiedTitle === t.title ? <CheckCircle2 className="h-3.5 w-3.5 shrink-0 mt-0.5" /> : <Copy className="h-3.5 w-3.5 shrink-0 mt-0.5" />}
                            </div>
                          );
                        })}
                      </div>
                    )}
                    {/* Descriptions */}
                    {viralDescs.length > 0 && (
                      <div className="space-y-2">
                        <p className="text-xs font-bold text-gray-400 uppercase tracking-wider">Deskripsi — Klik untuk pakai</p>
                        {viralDescs.map((d, i) => {
                          const c = d.type === "emotion" ? "bg-pink-50 border-pink-200 text-pink-700" : d.type === "punchline" ? "bg-orange-50 border-orange-200 text-orange-700" : "bg-blue-50 border-blue-200 text-blue-700";
                          return (
                            <div key={i} onClick={() => copyText(d.description, setCopiedDesc)}
                              className={`rounded-xl border px-3 py-2 text-[11px] cursor-pointer hover:opacity-80 transition-opacity ${c}`}>
                              <div className="flex items-start gap-2">
                                <div className="flex-1 whitespace-pre-line leading-relaxed">{d.description}</div>
                                <div className="shrink-0">{copiedDesc === d.description ? <CheckCircle2 className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}</div>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                    {/* Thumbnail */}
                    <div className="space-y-2">
                      <p className="text-xs font-bold text-gray-400 uppercase tracking-wider">Thumbnail</p>
                      <Button size="sm" variant="outline" className="rounded-xl gap-1.5" onClick={generateThumbnail} disabled={generatingThumb}>
                        {generatingThumb ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ImageIcon className="h-3.5 w-3.5" />}
                        Capture Frame di {fmtSec(trimStart)}
                      </Button>
                      {thumbError && <div className="text-xs text-red-500 bg-red-50 border border-red-200 rounded-xl px-3 py-2">{thumbError}</div>}
                      {thumbnailUrl && !thumbError && (
                        <div className="rounded-xl overflow-hidden border shadow-sm">
                          <img src={thumbnailUrl} alt="Thumbnail" className="w-full h-auto" />
                          <div className="p-2 text-[10px] text-gray-400 text-center">Klik kanan → Simpan gambar</div>
                        </div>
                      )}
                    </div>
                    {/* Next */}
                    <Button className="w-full rounded-xl gap-2" onClick={() => { setWizardStep(4); fetchSubtitles(); }}>
                      Lanjut: Subtitles 🎬 <ChevronRight className="h-4 w-4" />
                    </Button>
                  </div>
                )}

                {/* ── STEP 4: Subtitles ── */}
                {wizardStep === 4 && (
                  <div className="max-w-xl space-y-5">
                    <div>
                      <h2 className="text-xl font-bold flex items-center gap-2">🎬 Auto Subtitle</h2>
                      <p className="text-sm text-gray-500 mt-0.5">Subtitle otomatis dari caption YouTube (jika tersedia).</p>
                    </div>
                    {loadingSubs && (
                      <div className="flex items-center gap-2 text-sm text-gray-500">
                        <Loader2 className="h-4 w-4 animate-spin" /> Mencari subtitle...
                      </div>
                    )}
                    {!loadingSubs && subtitleData && (
                      subtitleData.available ? (
                        <div className="space-y-3">
                          <div className="flex items-center gap-2 text-sm text-green-700 font-semibold">
                            <CheckCircle2 className="h-4 w-4" /> Subtitle tersedia!
                          </div>
                          <div className="rounded-xl border bg-gray-50 p-3 max-h-64 overflow-y-auto space-y-2">
                            {subtitleData.entries.slice(0, 30).map((e, i) => (
                              <div key={i} className="text-xs flex gap-3">
                                <span className="text-gray-400 shrink-0 font-mono">{fmtSec(e.start)}</span>
                                <span className="text-gray-700">{e.text}</span>
                              </div>
                            ))}
                          </div>
                          <Button size="sm" variant="outline" className="rounded-xl gap-1.5"
                            onClick={() => copyText(subtitleData.entries.map(e => `${fmtSec(e.start)} ${e.text}`).join("\n"), () => { })}>
                            <Copy className="h-3.5 w-3.5" /> Copy Semua Subtitle
                          </Button>
                        </div>
                      ) : (
                        <div className="rounded-2xl border-2 border-dashed p-6 text-center space-y-2">
                          <FileText className="h-8 w-8 text-gray-300 mx-auto" />
                          <p className="text-sm font-semibold text-gray-600">Subtitle tidak tersedia</p>
                          <p className="text-xs text-gray-400">Video baru yang didownload akan otomatis mencoba mendapatkan subtitle YouTube.</p>
                        </div>
                      )
                    )}
                    <Button className="w-full rounded-xl gap-2" onClick={() => setWizardStep(5)}>
                      Lanjut: Preview & Export 📤 <ChevronRight className="h-4 w-4" />
                    </Button>
                    <button onClick={() => setWizardStep(3)} className="text-xs text-gray-400 hover:text-gray-600 transition-colors">
                      ← Kembali ke Content
                    </button>
                  </div>
                )}

                {/* ── STEP 5: Export ── */}
                {wizardStep === 5 && (
                  <div className="max-w-2xl space-y-5">
                    <div>
                      <h2 className="text-xl font-bold flex items-center gap-2">📤 Preview & Export</h2>
                      <p className="text-sm text-gray-500 mt-0.5">Review clip dan upload ke platform pilihanmu.</p>
                    </div>
                    {/* Video player */}
                    {clipUrl && (
                      <div className="rounded-2xl overflow-hidden border shadow-lg bg-black">
                        <video src={clipUrl} controls className="w-full aspect-video" />
                      </div>
                    )}
                    {/* Editable metadata */}
                    <div className="space-y-3">
                      <div className="space-y-1">
                        <label className="text-xs font-semibold text-gray-600">Judul Upload</label>
                        <Input value={uploadTitle} onChange={e => setUploadTitle(e.target.value)} className="rounded-xl" />
                      </div>
                      <div className="space-y-1">
                        <label className="text-xs font-semibold text-gray-600">Deskripsi</label>
                        <textarea value={uploadDesc} onChange={e => setUploadDesc(e.target.value)} rows={4}
                          className="w-full rounded-xl border px-3 py-2 text-sm resize-none focus:outline-violet-400" />
                      </div>
                    </div>
                    {/* Platform */}
                    <div className="space-y-2">
                      <label className="text-xs font-semibold text-gray-600 uppercase tracking-wider">Platform</label>
                      <div className="flex flex-wrap gap-2">
                        {PLATFORMS.map(p => (
                          <Button key={p} size="sm" variant={publishPlatform === p ? "default" : "outline"}
                            className="rounded-full text-xs" onClick={() => setPublishPlatform(p)}>
                            {p.toUpperCase()}
                          </Button>
                        ))}
                      </div>
                    </div>
                    {/* Connect warning — only shown if not connected */}
                    {!platformStatus[publishPlatform] && (
                      <div className="flex items-center gap-2 text-amber-700 bg-amber-50 border border-amber-200 rounded-xl px-3 py-2 text-xs">
                        <AlertCircle className="h-3.5 w-3.5 shrink-0" />
                        {publishPlatform === "YT" ? "YouTube" : publishPlatform === "IG" ? "Instagram" : publishPlatform === "TT" ? "TikTok" : "Facebook"} belum terhubung.{" "}
                        <button onClick={() => handleConnect(publishPlatform as any)} className="underline font-semibold">
                          Connect sekarang
                        </button>
                      </div>
                    )}
                    {/* Upload result */}
                    {uploadResult && (
                      <div className="flex items-center gap-2 text-green-700 bg-green-50 border border-green-200 rounded-xl px-3 py-2 text-sm font-semibold">
                        <CheckCircle2 className="h-4 w-4" />Upload berhasil!{" "}
                        <a href={uploadResult.url} target="_blank" className="underline flex items-center gap-1">
                          Lihat video <ExternalLink className="h-3.5 w-3.5" />
                        </a>
                      </div>
                    )}
                    {/* Upload button */}
                    {!uploadResult && (
                      <Button className="w-full py-5 rounded-xl text-base gap-2"
                        onClick={handleUpload} disabled={uploading || !clipResult || !platformStatus[publishPlatform]}>
                        {uploading ? <Loader2 className="h-5 w-5 animate-spin" /> : <Send className="h-5 w-5" />}
                        {uploading ? "Mengupload..." : `📤 Upload ke ${publishPlatform.charAt(0).toUpperCase() + publishPlatform.slice(1)}`}
                      </Button>
                    )}
                    {/* Download clip */}
                    {clipUrl && (
                      <a href={clipUrl} download className="block">
                        <Button variant="outline" className="w-full rounded-xl gap-2">
                          <Download className="h-4 w-4" /> Download Clip (MP4)
                        </Button>
                      </a>
                    )}
                    <button onClick={() => setWizardStep(4)} className="text-xs text-gray-400 hover:text-gray-600 transition-colors">
                      ← Kembali ke Subtitles
                    </button>
                  </div>
                )}

              </div>{/* end step content */}
            </div>
          )}
        </div>{/* end right panel */}
      </div>
    </div>
  );
}
