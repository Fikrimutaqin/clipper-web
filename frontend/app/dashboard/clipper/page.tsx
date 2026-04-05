"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Video, Search, Download, Loader2, Zap, Scissors, Play, Send,
  ExternalLink, CheckCircle2, AlertCircle, Sparkles, Image as ImageIcon,
  Copy, Clock, ChevronRight, BarChart2, Flame, TrendingUp, Tag,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import api from "@/lib/axios";

interface ViralMomentResult {
  start_time: number;
  end_time: number;
  subtitle_text: string;
  viral_score: number;
  type: "punchline" | "emotion" | "insight" | "hook" | "cta";
  keywords_detected: string[];
  reason: string;
}

interface VideoItem {
  id: string;
  snippet: { title: string; thumbnails: { medium: { url: string } }; channelTitle: string };
  statistics: { viewCount: string };
}

const STEPS = [
  { id: 1, icon: "🔥", label: "AI Detect" },
  { id: 2, icon: "✂️", label: "Auto Cut" },
  { id: 3, icon: "🎬", label: "AI Video Studio" },
  { id: 4, icon: "🎬", label: "Subtitles" },
  { id: 5, icon: "📤", label: "Export" },
];

const PLATFORM_CARDS = [
  { key: "YT", label: "YouTube", icon: "🎬", bg: "bg-red-50", desc: "Upload ke YouTube Shorts & video biasa", available: true },
  { key: "IG", label: "Instagram", icon: "📸", bg: "bg-pink-50", desc: "Posting ke Reels & feed Instagram", available: false },
  { key: "TT", label: "TikTok", icon: "🎵", bg: "bg-gray-100", desc: "Upload langsung ke akun TikTok kamu", available: false },
  { key: "FB", label: "Facebook", icon: "👥", bg: "bg-blue-50", desc: "Share ke Facebook Page & Reels", available: false },
];

const VIRAL_TEMPLATES = [
  {
    id: "mrbeast",
    name: "🔥 MrBeast Style",
    desc: "Kuning tebal, outline besar (Bangers)",
    config: { fontname: "Bangers", primary_colour: "00FFFF", outline_colour: "000000", fontsize: "90", outline: 8, margin_v: 250, uppercase: true, shadow: 0 }
  },
  {
    id: "podcast",
    name: "🎙 Podcast Clean",
    desc: "Elegan, putih, font modern (Montserrat)",
    config: { fontname: "Montserrat", primary_colour: "FFFFFF", outline_colour: "000000", fontsize: "70", outline: 3, margin_v: 150, uppercase: false, shadow: 0 }
  },
  {
    id: "motivational",
    name: "🎯 Motivational Quotes",
    desc: "Teks besar di tengah untuk emosi",
    config: { fontname: "Montserrat", primary_colour: "FFFFFF", outline_colour: "000000", fontsize: "80", outline: 4, margin_v: 960, uppercase: true, shadow: 0 }
  },
  {
    id: "chat_story",
    name: "💬 Chat Story",
    desc: "Hijau ala iMessage",
    config: { fontname: "Montserrat", primary_colour: "00FF00", outline_colour: "000000", fontsize: "65", outline: 3, margin_v: 200, uppercase: false, shadow: 0 }
  }
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
  const [generatingAiSubs, setGeneratingAiSubs] = useState(false);

  // Viral Score Analysis
  const [viralScoreResults, setViralScoreResults] = useState<ViralMomentResult[]>([]);
  const [analyzingViral, setAnalyzingViral] = useState(false);
  const [viralError, setViralError] = useState("");
  const [showAllViral, setShowAllViral] = useState(false);

  // Step 5 – Template Editor
  const [templateConfig, setTemplateConfig] = useState({
    fontname: "Montserrat",
    primary_colour: "FFFFFF",
    outline_colour: "000000",
    fontsize: "80",
    outline: 5,
    margin_v: 200,
    uppercase: true,
    shadow: 0.2
  });
  const [renderingTemplate, setRenderingTemplate] = useState(false);
  const [activeOverlayText, setActiveOverlayText] = useState("");

  // Step 6 – Export
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
    api.get("/api/youtube/discover").then(r => setVideos(r.data?.data?.items || [])).catch(() => { });
  }, []);


  useEffect(() => {
    const clipExportId = searchParams.get("clip_export");
    const exportFilename = searchParams.get("filename") || "Video Clip";
    const exportUrl = searchParams.get("url") || "";

    if (clipExportId && exportUrl) {
      setSelectedTaskId("clip-" + clipExportId);
      setClipResult({ clip_id: clipExportId, url: exportUrl, full_url: exportUrl });
      setUploadTitle(exportFilename.replace(/\.mp4$/i, ""));
      setUploadDesc("Diposting secara otomatis melalui ClipFIX AI! 🔥 #shorts #viral");
      setWizardStep(6);
      return;
    }

    const editStyleId = searchParams.get("edit_style");
    if (editStyleId && exportUrl) {
      setSelectedTaskId("clip-" + editStyleId);
      setClipResult({ clip_id: editStyleId, url: exportUrl, full_url: exportUrl });
      setWizardStep(3); // Visual Studio
      
      // Auto-transcribe if needed
      if (!subtitleData) {
        setLoadingSubs(true);
        api.post(`/api/youtube/transcribe-clip/${editStyleId}`)
           .then(r => setSubtitleData(r.data?.data))
           .finally(() => setLoadingSubs(false));
      }
      return;
    }

    const tid = searchParams.get("task_id");
    if (!tid) return;

    const activate = () => {
      setSelectedTaskId(tid);
      setWizardStep(1);
    };

    api.get(`/api/youtube/download/${tid}`)
      .then(r => {
        const status = r.data?.data?.status;
        if (status === "done" || r.data?.data?.file_path) {
          activate();
        } else {
          activate();
        }
      })
      .catch(() => {
        activate();
      });
  }, [searchParams]);

  useEffect(() => {
    if (!selectedTaskId) return;
    if (selectedTaskId.startsWith("clip-")) return;
    setSuggestions([]);
    setPickedSuggestion(null);
    setClipResult(null);
    setViralTitles([]);
    setViralDescs([]);
    setThumbnailUrl(null);
    setSubtitleData(null);
    setWizardStep(1);
  }, [selectedTaskId]);

  useEffect(() => {
    if (clipResult && wizardStep === 2) setWizardStep(3);
  }, [clipResult, wizardStep]);

  useEffect(() => {
    const isEditing = wizardStep > 1;
    if (!isEditing) return;

    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", handleBeforeUnload);

    const handleNavigationClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      const anchor = target.closest("a");
      const isExternalLink = anchor && anchor.getAttribute("target") === "_blank";
      const href = anchor ? anchor.getAttribute("href") : null;
      const isSamePage = href && (href.startsWith("#") || href.startsWith("/dashboard/clipper"));
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

  const [batchClips, setBatchClips] = useState<any[]>([]);

  const detectHighlights = async () => {
    if (!selectedTaskId) return;
    setDetecting(true); setSuggestions([]); setBatchClips([]);
    try {
      // Trigger the batch process (Detect + Trim + Extract Subs)
      const res = await api.post(`/api/youtube/batch-process/${selectedTaskId}`, { format_type: format, samples: 10 });
      const clips = res.data.data.clips || [];
      setBatchClips(clips);

      // Keep legacy suggestions for compatibility if needed, but we focus on clips
      setSuggestions(clips.map((c: any) => ({
        ...c,
        start_seconds: c.start,
        end_seconds: c.end,
        viral_score: c.score,
        label: c.label,
        clip_id: c.id
      })));

    } catch (e: any) {
      setError(extractError(e, "Gagal mendeteksi highlight batch."));
    } finally { setDetecting(false); }
  };

  const pickSuggestion = (s: any) => {
    // With Batch Mode, the clip is ALREADY trimmed. 
    // We skip Step 2 (Trim) and go directly to Step 3 (Studio) or Step 4 (Subtitles)
    setPickedSuggestion(s);
    setTrimStart(Math.floor(s.start_seconds));
    setTrimEnd(Math.ceil(s.end_seconds));

    // Assign the already-created clip from batch to clipResult
    setClipResult({
      clip_id: s.id || s.clip_id,
      url: s.url,
      full_url: s.url.startsWith("http") ? s.url : `${apiBase}${s.url}`
    });

    // Populate subtitle immediately from batch
    if (s.subtitles) {
      setSubtitleData({ available: true, entries: s.subtitles });
    }

    // Jump to AI Video Studio / Template Step
    setWizardStep(3);
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
    } catch { /* silent */ }
    finally { setGeneratingContent(false); }
  };

  const [batchProcessing, setBatchProcessing] = useState(false);
  const [batchProgress, setBatchProgress] = useState("");

  const handleBatchRender = async (template: any) => {
    if (suggestions.length === 0) return;
    setBatchProcessing(true);
    setError("");
    setBatchProgress(`Styling ${suggestions.length} clips with ${template.name}...`);
    try {
      const clipIds = suggestions.map(s => s.clip_id);
      const res = await api.post("/api/youtube/render-batch", {
        clip_ids: clipIds,
        template: template.config
      });
      const results = res.data.data.results || [];
      // Update suggestions with new final URLs
      setSuggestions(prev => prev.map(s => {
        const matching = results.find((r: any) => r.id === s.clip_id);
        if (matching && matching.status === "done") {
          return { ...s, url: matching.url, clip_id: matching.final_id, is_styled: true };
        }
        return s;
      }));
      setBatchProgress("Semua clip berhasil di-style!");
      setTimeout(() => setBatchProgress(""), 3000);
    } catch (e: any) {
      setError(extractError(e, "Gagal batch rendering."));
    } finally { setBatchProcessing(false); }
  };

  const handleBatchUpload = async () => {
    if (suggestions.length === 0) return;
    if (!ytConnected) { alert("Hubungkan YouTube dulu di panel atas!"); return; }

    setBatchProcessing(true);
    setBatchProgress(`Mengupload ${suggestions.length} clips ke YouTube...`);
    try {
      const uploadReqs = suggestions.map((s, i) => ({
        clip_id: s.clip_id,
        title: `${s.label || "Clip"} - ${uploadTitle} #${i + 1}`,
        description: uploadDesc,
        format_type: format
      }));

      const res = await api.post("/api/youtube/upload-batch", uploadReqs);
      const results = res.data.data.results || [];
      const count = results.filter((r: any) => r.status === "done").length;
      setBatchProgress(`${count} video berhasil diposting ke YouTube!`);
      setTimeout(() => setWizardStep(6), 2000); // Go to export/success step
    } catch (e: any) {
      setError(extractError(e, "Gagal batch upload."));
    } finally { setBatchProcessing(false); }
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
      const data = res.data.data;
      setSubtitleData(data);
      if (data?.available && data.entries?.length > 0) {
        analyzeViralMoments(data.entries);
      }
    } catch { setSubtitleData({ available: false, entries: [] }); }
    finally { setLoadingSubs(false); }
  };

  const analyzeViralMoments = async (entries: any[]) => {
    if (!entries || entries.length === 0) return;
    setAnalyzingViral(true);
    setViralError("");
    setViralScoreResults([]);
    try {
      const segments = entries.map((e: any) => ({
        subtitle_text: e.text,
        start_time: e.start,
        end_time: e.end,
      }));
      const res = await api.post("/api/youtube/viral-score/batch", { segments });
      setViralScoreResults(res.data.data.results || []);
    } catch (e: any) {
      setViralError(extractError(e, "Gagal menganalisis momen viral."));
    } finally {
      setAnalyzingViral(false);
    }
  };

  const handleGenerateAiSubtitles = async () => {
    if (!clipResult) return;
    setGeneratingAiSubs(true);
    try {
      const res = await api.post(`/api/youtube/transcribe-clip/${clipResult.clip_id}`);
      const data = res.data.data;
      setSubtitleData({ available: true, entries: data.entries });
      if (data.entries && data.entries.length > 0) {
        analyzeViralMoments(data.entries);
      }
    } catch (e: any) {
      alert(e.response?.data?.detail || "Gagal menghasilkan subtitle dari AI.");
    } finally {
      setGeneratingAiSubs(false);
    }
  };

  const handleTimeUpdate = (e: React.SyntheticEvent<HTMLVideoElement>) => {
    if (!subtitleData || !subtitleData.entries) return;
    const time = (e.target as HTMLVideoElement).currentTime;
    const currentSub = subtitleData.entries.find((s: any) => time >= s.start && time <= s.end);
    if (currentSub) {
      setActiveOverlayText(templateConfig.uppercase ? currentSub.text.toUpperCase() : currentSub.text);
    } else {
      setActiveOverlayText("");
    }
  };

  const handleRenderTemplate = async () => {
    if (!clipResult) return;
    setRenderingTemplate(true);
    try {
      const resp = await api.post("/api/youtube/render-template", {
        clip_id: clipResult.clip_id,
        template: {
          ...templateConfig,
          entries: subtitleData?.entries || []
        }
      });
      setClipResult({
        clip_id: resp.data.data.clip_id,
        url: resp.data.data.url,
        full_url: resp.data.data.full_url
      });
      setWizardStep(6);
    } catch (e: any) {
      alert(e.response?.data?.detail || "Gagal merender template video");
    } finally {
      setRenderingTemplate(false);
    }
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

  const PLATFORMS = ["YT", "TT", "IG", "FB"] as const;

  return (
    <div className="h-screen flex flex-col bg-gray-50 rounded-lg">
      <div className="shrink-0 border-b bg-white px-8 py-4 flex items-center gap-3 rounded-lg">
        <Video className="h-5 w-5 text-violet-600" />
        <h1 className="text-lg font-bold text-gray-900">Clip Editor</h1>
        <span className="text-xs text-gray-400 ml-2 hidden sm:block">Pipeline AI → Auto Cut → Subtitle → Export</span>

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
        <div className="w-80 shrink-0 border-r bg-white flex flex-col min-h-0">
          <div className="p-4 border-b space-y-3">
            <div className="flex gap-1">
              {PLATFORMS.map(p => (
                <button key={p} onClick={() => setSourcePlatform(p)}
                  className={`flex-1 text-[10px] py-1 rounded-lg font-semibold transition-colors ${sourcePlatform === p ? "bg-violet-600 text-white" : "bg-gray-100 text-gray-500 hover:bg-gray-200"}`}>
                  {p}
                </button>
              ))}
            </div>
            <div className="flex gap-2">
              <Input value={searchUrl} onChange={e => setSearchUrl(e.target.value)}
                placeholder="Paste URL video..." className="text-sm h-9 rounded-xl" />
              <Button size="sm" className="rounded-xl h-9 px-3" onClick={() => {
                if (searchUrl.trim()) handleDownload("");
              }}>
                <Download className="h-4 w-4" />
              </Button>
            </div>
            <div className="flex gap-2">
              <Input value={searchQuery} onChange={e => setSearchQuery(e.target.value)}
                onKeyDown={e => e.key === "Enter" && handleSearch()}
                placeholder="Cari video YouTube..." className="text-sm h-9 rounded-xl" />
              <Button size="sm" variant="outline" className="rounded-xl h-9 px-3" onClick={handleSearch}>
                <Search className="h-4 w-4" />
              </Button>
            </div>
          </div>

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

          {error && (
            <div className="mx-4 mt-3 flex gap-2 items-start text-xs text-red-600 bg-red-50 border border-red-200 rounded-xl p-3">
              <AlertCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" /> {error}
            </div>
          )}

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

        <div id="clip-editor" className="flex-1 flex flex-col min-h-0 rounded-lg">
          {!selectedTaskId ? (
            (() => {
              const anyConnected = Object.values(platformStatus).some(v => v);
              return anyConnected ? (
                <div className="flex-1 flex flex-col items-center justify-center text-center gap-4 p-12">
                  <div className="w-20 h-20 rounded-3xl bg-violet-50 flex items-center justify-center text-4xl">🎬</div>
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
                <div className="flex-1 overflow-y-auto p-8">
                  <div className="max-w-lg mx-auto space-y-6">
                    <div className="text-center space-y-1">
                      <div className="text-4xl mb-3">🔗</div>
                      <h2 className="text-2xl font-bold text-gray-900">Hubungkan Platform</h2>
                      <p className="text-sm text-gray-500">Koneksikan akun agar clip kamu bisa langsung diupload setelah selesai diedit.</p>
                    </div>

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

              <div className="flex-1 overflow-y-auto p-6">

                {wizardStep === 1 && (
                  <div className="max-w-2xl space-y-5">
                    <div>
                      <h2 className="text-xl font-bold flex items-center gap-2">🔥 AI Detect Highlight</h2>
                      <p className="text-sm text-gray-500 mt-0.5">AI menganalisis audio energy untuk temukan momen paling viral.</p>
                    </div>
                    <div className="flex gap-3">
                      {[{ k: "short", l: "9:16 Short", d: "(min 20s)" }, { k: "regular", l: "16:9 Regular", d: "(min 10 min)" }].map(f => (
                        <button key={f.k} onClick={() => setFormat(f.k as any)}
                          className={`flex-1 rounded-xl border-2 py-3 px-4 text-sm font-semibold transition-all ${format === f.k ? "border-violet-500 bg-violet-50 text-violet-700" : "border-gray-200 text-gray-600 hover:border-gray-300"}`}>
                          {f.l} <span className="text-xs opacity-60">{f.d}</span>
                        </button>
                      ))}
                    </div>
                    <Button className="w-full py-5 rounded-xl text-base gap-2" onClick={detectHighlights} disabled={detecting}>
                      {detecting ? <Loader2 className="h-5 w-5 animate-spin" /> : <Zap className="h-5 w-5" />}
                      {detecting ? "Batch Processing (Top 10 Clips)..." : "⚡ AI Auto-Clip Top 10"}
                    </Button>

                    {suggestions.length > 0 && (
                      <div className="p-4 rounded-2xl border-2 border-violet-200 bg-violet-50/50 space-y-4">
                        <div className="flex items-center justify-between">
                          <label className="text-[11px] font-bold text-violet-700 uppercase tracking-widest flex items-center gap-2">
                            <Sparkles className="h-3.5 w-3.5" /> Bulk Action Center
                          </label>
                          {batchProcessing && <Loader2 className="h-4 w-4 animate-spin text-violet-600" />}
                        </div>

                        {batchProgress && (
                          <div className="text-[10px] bg-white border border-violet-100 rounded-lg p-2 text-violet-600 font-medium animate-pulse">
                            ⏳ {batchProgress}
                          </div>
                        )}

                        <div className="grid grid-cols-1 gap-2">
                          {/* <div className="space-y-1.5">
                             <p className="text-[9px] font-semibold text-gray-400 ml-1">1. APPLY STYLE TO ALL</p>
                             <div className="flex flex-wrap gap-1">
                               {VIRAL_TEMPLATES.map(t => (
                                 <button key={t.id} onClick={() => handleBatchRender(t)} disabled={batchProcessing}
                                   className="text-[10px] bg-white border border-gray-200 px-2 py-1 rounded-md hover:border-violet-400 hover:text-violet-600 shadow-sm transition-all whitespace-nowrap">
                                   {t.name}
                                 </button>
                               ))}
                             </div>
                          </div> */}
                          <div className="space-y-1.5 flex flex-col w-full">
                            <p className="text-[9px] font-semibold text-gray-400 ml-1">PUBLISH ALL</p>
                            <Button size="sm" variant="default" disabled={batchProcessing || !ytConnected} onClick={handleBatchUpload}
                              className="w-full! mt-auto h-8 text-[10px] rounded-lg bg-red-600 hover:bg-red-700 gap-1.5">
                              <Send className="h-3 w-3" /> Post All to Shorts
                            </Button>
                          </div>
                        </div>
                      </div>
                    )}

                    {suggestions.length > 0 && (
                      <div className="space-y-3">
                        <div className="flex items-center justify-between">
                          <p className="text-xs font-bold text-gray-400 uppercase tracking-wider">
                            🚀 {suggestions.length} Clips Berhasil di-Trim & Siap Diposting
                          </p>
                        </div>
                        {suggestions.map((s, i) => (
                          <div key={i} onClick={() => pickSuggestion(s)}
                            className={`rounded-2xl border-2 border-l-4 bg-white p-5 cursor-pointer hover:border-violet-300 hover:shadow-lg transition-all group ${typeColor[s.type] || "border-l-gray-300"}`}>
                            <div className="flex items-start justify-between mb-3">
                              <div className="space-y-1">
                                <div className="flex items-center gap-2">
                                  <span className="font-bold text-sm text-gray-900 group-hover:text-violet-700 transition-colors">
                                    {s.label}
                                  </span>
                                  <span className="text-[9px] bg-green-50 text-green-600 px-1.5 py-0.5 rounded-md border border-green-100 flex items-center gap-1 font-bold">
                                    <Scissors className="h-2 w-2" /> Ready
                                  </span>
                                </div>
                                {s.hook && (
                                  <p className="text-[11px] italic text-gray-500 line-clamp-1">
                                    "{s.hook}"
                                  </p>
                                )}
                              </div>
                              <div className="flex flex-col items-end gap-1">
                                <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border shadow-sm ${viralBadge(s.viral_score ?? 0)}`}>
                                  ⚡ {s.viral_score ?? "—"}% Viral
                                </span>
                              </div>
                            </div>

                            {s.reason && (
                              <div className="mb-3 p-2 bg-gray-50 rounded-lg border border-gray-100 italic text-[11px] text-gray-600 line-clamp-2">
                                ✨ {s.reason}
                              </div>
                            )}

                            <div className="flex items-center justify-between mb-3 text-[10px] text-gray-500 font-medium">
                              <div className="flex items-center gap-3">
                                <span className="flex items-center gap-1 bg-gray-100 px-2 py-0.5 rounded-full"><Clock className="h-2.5 w-2.5" />{fmtSec(s.start_seconds)} – {fmtSec(s.end_seconds)}</span>
                                <span className="flex items-center gap-1 bg-gray-100 px-2 py-0.5 rounded-full"><BarChart2 className="h-2.5 w-2.5" />{Math.round(s.end_seconds - s.start_seconds)}s</span>
                                {s.subtitles && <span className="flex items-center gap-1 bg-violet-50 text-violet-600 px-2 py-0.5 rounded-full font-bold">CC Active</span>}
                              </div>
                              {s.vectors && (
                                <div className="flex gap-1.5 opacity-60 group-hover:opacity-100 transition-opacity">
                                  {Object.entries(s.vectors).map(([k, v]: [string, any]) => (
                                    <div key={k} className="flex flex-col items-center">
                                      <div className="w-1 h-3 bg-gray-200 rounded-full relative overflow-hidden">
                                        <div className="absolute bottom-0 w-full bg-violet-500" style={{ height: `${(v as number) * 10}%` }} />
                                      </div>
                                      <span className="text-[7px] uppercase mt-0.5">{k[0]}</span>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>

                            <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden mb-3">
                              <div className={`h-full rounded-full transition-all ${(s.viral_score ?? 0) >= 75 ? "bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.5)]" : (s.viral_score ?? 0) >= 50 ? "bg-orange-400" : "bg-gray-400"}`}
                                style={{ width: `${s.viral_score ?? 0}%` }} />
                            </div>

                            <div className="flex justify-end">
                              <Button size="sm" className="rounded-full text-[10px] h-7 px-4 gap-1.5 shadow-sm hover:translate-x-1 transition-transform bg-violet-600">
                                🎨 Style & Publish <ChevronRight className="h-3 w-3" />
                              </Button>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {wizardStep === 2 && (
                  <div className="max-w-lg space-y-5">
                    <div>
                      <h2 className="text-xl font-bold flex items-center gap-2">✂️ Auto Cut Clip</h2>
                      <p className="text-sm text-gray-500 mt-0.5">Review dan sesuaikan waktu potongan, lalu proses.</p>
                    </div>
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

                {wizardStep === 3 && (
                  <div className="max-w-xl space-y-6">
                    <div className="bg-indigo-600 rounded-3xl p-8 text-white relative overflow-hidden shadow-2xl shadow-indigo-200">
                      <div className="absolute top-0 right-0 -mr-8 -mt-8 w-40 h-40 bg-white/10 rounded-full blur-3xl"></div>
                      <div className="relative z-10 space-y-4">
                        <div className="w-14 h-14 bg-white/20 rounded-2xl flex items-center justify-center backdrop-blur-md">
                          <Sparkles className="w-8 h-8 text-white" />
                        </div>
                        <div>
                          <h2 className="text-2xl font-bold leading-tight">AI Video Studio Editor</h2>
                          <p className="text-indigo-100 text-sm mt-1 opacity-80">Gunakan fitur Local Subtitle & Viral Hook Generator untuk hasil maksimal.</p>
                        </div>
                        <Button
                          onClick={() => router.push(`/dashboard/video-editor?from_clip=${clipResult?.clip_id}`)}
                          className="w-full bg-white text-indigo-600 hover:bg-indigo-50 py-7 rounded-2xl text-lg font-bold shadow-xl shadow-black/10 gap-3"
                        >
                          <Play className="w-6 h-6 fill-current" />
                          Buka di AI Video Studio
                        </Button>
                        <p className="text-[10px] text-center text-indigo-200/60 font-medium uppercase tracking-widest">
                          Re-style, Transcribe & Viral Logic
                        </p>
                      </div>
                    </div>

                    <div className="bg-white border border-slate-100 rounded-3xl p-6 shadow-sm space-y-4">
                      <div className="flex items-center gap-3">
                        <div className="p-2 bg-amber-50 rounded-xl text-amber-600">
                          <ImageIcon className="w-5 h-5" />
                        </div>
                        <h3 className="font-bold text-slate-800">Thumbnail Preview</h3>
                      </div>
                      <Button variant="outline" className="w-full rounded-2xl gap-2 py-6 border-slate-100 bg-slate-50 text-slate-600 font-bold" onClick={generateThumbnail} disabled={generatingThumb}>
                        {generatingThumb ? <Loader2 className="h-4 w-4 animate-spin" /> : <ImageIcon className="h-4 w-4" />}
                        Capture Frame di {fmtSec(trimStart)}
                      </Button>
                      {thumbnailUrl && (
                        <div className="rounded-2xl overflow-hidden border-4 border-white shadow-lg">
                          <img src={thumbnailUrl} alt="Thumbnail" className="w-full h-auto" />
                        </div>
                      )}
                    </div>

                    <div className="flex flex-col gap-3">
                      <Button className="w-full rounded-2xl py-6 gap-2 font-bold shadow-lg opacity-50 cursor-not-allowed" disabled={true}>
                        Lanjut ke Subtitles 🎬 <ChevronRight className="h-4 w-4" />
                      </Button>
                      <p className="text-[10px] text-center text-slate-400 italic">Harap gunakan <b>AI Video Studio</b> di atas untuk melanjutkan pengeditan.</p>
                      <button onClick={() => setWizardStep(2)} className="text-xs text-slate-400 hover:text-slate-600 transition-colors font-medium">
                        ← Kembali ke Auto Cut
                      </button>
                    </div>
                  </div>
                )}

                {wizardStep === 4 && (
                  <div className="max-w-2xl space-y-5">
                    <div>
                      <h2 className="text-xl font-bold flex items-center gap-2">🎬 Auto Subtitle & Viral Analysis</h2>
                      <p className="text-sm text-gray-500 mt-0.5">Subtitle otomatis + deteksi momen paling viral dari setiap baris.</p>
                    </div>

                    {loadingSubs && (
                      <div className="flex items-center gap-2 text-sm text-gray-500">
                        <Loader2 className="h-4 w-4 animate-spin" /> Mencari subtitle...
                      </div>
                    )}
                    {!loadingSubs && subtitleData && (
                      subtitleData.available ? (
                        <div className="space-y-3">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2 text-sm text-green-700 font-semibold">
                              <CheckCircle2 className="h-4 w-4" /> {subtitleData.entries.length} subtitle tersedia
                            </div>
                            <Button size="sm" variant="outline" className="rounded-xl gap-1.5 text-xs"
                              onClick={() => copyText(subtitleData.entries.map((e: any) => `${fmtSec(e.start)} ${e.text}`).join("\n"), () => { })}>
                              <Copy className="h-3 w-3" /> Copy Semua
                            </Button>
                          </div>
                          <div className="rounded-xl border bg-gray-50 p-3 max-h-48 overflow-y-auto space-y-2">
                            {subtitleData.entries.slice(0, 30).map((e: any, i: number) => (
                              <div key={i} className="text-xs flex gap-3">
                                <span className="text-gray-400 shrink-0 font-mono w-10">{fmtSec(e.start)}</span>
                                <span className="text-gray-700">{e.text}</span>
                              </div>
                            ))}
                          </div>
                          <Button className="w-full rounded-xl gap-2" onClick={() => setWizardStep(5)}>
                            Lanjut ke Template Customizer 🎨 →
                          </Button>
                        </div>
                      ) : (
                        <div className="flex flex-col items-center justify-center p-6 bg-red-50 border border-red-100 rounded-xl space-y-3">
                          <AlertCircle className="h-6 w-6 text-red-500" />
                          <div className="text-sm text-gray-700 text-center font-medium">
                            Subtitle gagal ditarik dari YouTube. Hal ini sering terjadi karena limitasi atau video tidak memilikinya.
                          </div>
                          <Button
                            onClick={handleGenerateAiSubtitles}
                            disabled={generatingAiSubs}
                            className="bg-indigo-600 hover:bg-indigo-700 rounded-lg shadow-md"
                          >
                            {generatingAiSubs ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Sparkles className="h-4 w-4 mr-2" />}
                            Transkrip Pakai AI (Gemini)
                          </Button>
                          <div className="text-xs text-gray-500 pt-3">atau lanjut tanpa subtitle</div>
                          <Button variant="outline" className="w-full rounded-xl gap-2" onClick={() => setWizardStep(5)}>
                            Lanjut ke Template Customizer →
                          </Button>
                        </div>
                      )
                    )}

                    <div className="border-t pt-5 space-y-4">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <Flame className="h-5 w-5 text-orange-500" />
                          <h3 className="font-bold text-gray-800">Viral Moment Detector</h3>
                          {viralScoreResults.length > 0 && (
                            <span className="text-[10px] font-bold bg-orange-100 text-orange-700 border border-orange-200 rounded-full px-2 py-0.5">
                              {viralScoreResults.length} segment dianalisis
                            </span>
                          )}
                        </div>
                        {subtitleData?.available && subtitleData.entries.length > 0 && (
                          <Button
                            size="sm"
                            variant="outline"
                            className="rounded-xl gap-1.5 text-xs"
                            onClick={() => analyzeViralMoments(subtitleData.entries)}
                            disabled={analyzingViral}
                          >
                            {analyzingViral ? <Loader2 className="h-3 w-3 animate-spin" /> : <TrendingUp className="h-3 w-3" />}
                            {analyzingViral ? "Analyzing..." : "Re-analyze"}
                          </Button>
                        )}
                      </div>

                      {analyzingViral && (
                        <div className="rounded-xl bg-gradient-to-r from-orange-50 to-yellow-50 border border-orange-200 p-4 flex items-center gap-3">
                          <Loader2 className="h-5 w-5 animate-spin text-orange-500 shrink-0" />
                          <div>
                            <p className="text-sm font-semibold text-orange-700">Menganalisis momen viral...</p>
                            <p className="text-xs text-orange-500 mt-0.5">Mendeteksi kata kunci, emosi, dan pola high-impact</p>
                          </div>
                        </div>
                      )}

                      {viralError && (
                        <div className="flex items-center gap-2 text-xs text-red-600 bg-red-50 border border-red-200 rounded-xl p-3">
                          <AlertCircle className="h-3.5 w-3.5 shrink-0" /> {viralError}
                        </div>
                      )}

                      {!analyzingViral && viralScoreResults.length > 0 && (() => {
                        const topResults = viralScoreResults.filter(r => r.viral_score >= 20);
                        const displayResults = showAllViral ? topResults : topResults.slice(0, 5);
                        const typePill: Record<string, string> = {
                          emotion: "bg-pink-100 text-pink-700 border-pink-200",
                          hook: "bg-purple-100 text-purple-700 border-purple-200",
                          insight: "bg-blue-100 text-blue-700 border-blue-200",
                          punchline: "bg-orange-100 text-orange-700 border-orange-200",
                          cta: "bg-red-100 text-red-700 border-red-200",
                        };
                        return (
                          <div className="space-y-3">
                            <div className="grid grid-cols-3 gap-2">
                              {([
                                { label: "🔥 Sangat Viral", min: 75, color: "bg-green-500", light: "bg-green-50 border-green-200 text-green-700" },
                                { label: "⚡ Potensial", min: 45, color: "bg-orange-400", light: "bg-orange-50 border-orange-200 text-orange-700" },
                                { label: "💤 Biasa", min: 0, color: "bg-gray-400", light: "bg-gray-50 border-gray-200 text-gray-500" },
                              ] as const).map(tier => {
                                const count = viralScoreResults.filter(r => {
                                  if (tier.min === 75) return r.viral_score >= 75;
                                  if (tier.min === 45) return r.viral_score >= 45 && r.viral_score < 75;
                                  return r.viral_score < 45;
                                }).length;
                                return (
                                  <div key={tier.label} className={`rounded-xl border p-2 text-center ${tier.light}`}>
                                    <div className="font-bold text-lg">{count}</div>
                                    <div className="text-[10px] font-semibold mt-0.5">{tier.label}</div>
                                  </div>
                                );
                              })}
                            </div>

                            <p className="text-xs font-bold text-gray-400 uppercase tracking-wider">Top Momen Viral — Klik untuk Set Range</p>
                            {displayResults.map((r, i) => (
                              <div
                                key={i}
                                className={`rounded-2xl border-2 border-l-4 bg-white p-4 hover:shadow-md transition-all cursor-pointer group ${typeColor[r.type] || "border-l-gray-300"
                                  } ${r.viral_score >= 75 ? "border-green-200" : r.viral_score >= 45 ? "border-orange-200" : "border-gray-200"}`}
                                onClick={() => {
                                  setTrimStart(Math.max(0, Math.floor(r.start_time + trimStart)));
                                  setTrimEnd(Math.ceil(r.end_time + trimStart));
                                }}
                              >
                                <div className="flex items-start justify-between gap-2 mb-2">
                                  <p className="text-xs font-semibold text-gray-800 leading-snug flex-1">
                                    &ldquo;{r.subtitle_text.length > 100 ? r.subtitle_text.slice(0, 100) + "…" : r.subtitle_text}&rdquo;
                                  </p>
                                  <span className={`shrink-0 text-xs font-bold px-2 py-0.5 rounded-full border ${r.viral_score >= 75
                                    ? "bg-green-100 text-green-700 border-green-300"
                                    : r.viral_score >= 45
                                      ? "bg-orange-100 text-orange-700 border-orange-300"
                                      : "bg-gray-100 text-gray-500 border-gray-300"
                                    }`}>
                                    ⚡ {r.viral_score}
                                  </span>
                                </div>

                                <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden mb-2">
                                  <div
                                    className={`h-full rounded-full transition-all ${r.viral_score >= 75 ? "bg-green-500" : r.viral_score >= 45 ? "bg-orange-400" : "bg-gray-400"
                                      }`}
                                    style={{ width: `${r.viral_score}%` }}
                                  />
                                </div>

                                <div className="flex flex-wrap items-center gap-2">
                                  <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${typePill[r.type] || "bg-gray-100 text-gray-600 border-gray-200"
                                    }`}>
                                    {r.type.toUpperCase()}
                                  </span>
                                  <span className="flex items-center gap-1 text-[10px] text-gray-400">
                                    <Clock className="h-3 w-3" />{fmtSec(r.start_time)} – {fmtSec(r.end_time)}
                                  </span>
                                  {r.keywords_detected.slice(0, 3).map((kw, ki) => (
                                    <span key={ki} className="flex items-center gap-0.5 text-[10px] bg-yellow-50 border border-yellow-200 text-yellow-700 rounded-full px-1.5 py-0.5">
                                      <Tag className="h-2.5 w-2.5" />{kw}
                                    </span>
                                  ))}
                                </div>

                                <p className="text-[10px] text-gray-400 mt-2 leading-relaxed italic">{r.reason}</p>

                                <div className="mt-2 text-right">
                                  <span className="text-[10px] text-violet-500 font-semibold opacity-0 group-hover:opacity-100 transition-opacity">
                                    ✂️ Klik untuk set clip ke segmen ini →
                                  </span>
                                </div>
                              </div>
                            ))}

                            {topResults.length > 5 && (
                              <button
                                onClick={() => setShowAllViral(v => !v)}
                                className="text-xs text-violet-600 font-semibold hover:underline w-full text-center py-1"
                              >
                                {showAllViral ? `↑ Tampilkan lebih sedikit` : `↓ Tampilkan ${topResults.length - 5} momen lainnya`}
                              </button>
                            )}

                            {topResults.length === 0 && (
                              <div className="text-center text-xs text-gray-400 py-4">
                                Tidak ada momen dengan skor viral cukup tinggi (≥ 20).
                              </div>
                            )}
                          </div>
                        );
                      })()}

                      {/* Empty state — no subtitle */}
                      {!analyzingViral && viralScoreResults.length === 0 && !subtitleData?.available && (
                        <div className="rounded-xl border-2 border-dashed p-5 text-center space-y-1">
                          <Flame className="h-7 w-7 text-gray-300 mx-auto" />
                          <p className="text-xs text-gray-500">Viral analysis membutuhkan subtitle.</p>
                          <p className="text-[10px] text-gray-400">Download video baru untuk mendapatkan subtitle otomatis.</p>
                        </div>
                      )}
                    </div>

                    <Button className="w-full rounded-xl gap-2 mt-4 opacity-50 cursor-not-allowed" disabled={true}>
                      Lanjut: Template & Styling 🎨 <ChevronRight className="h-4 w-4" />
                    </Button>
                    <p className="text-[10px] text-center text-gray-400 italic mt-2">Gunakan <b>AI Video Studio</b> (di step sebelumnya) untuk memproses styling & subtitle.</p>
                    <button onClick={() => setWizardStep(3)} className="text-xs text-gray-400 hover:text-gray-600 transition-colors">
                      ← Kembali ke Content
                    </button>
                  </div>
                )}

                {/* ── STEP 5: Template Customizer ── */}
                {wizardStep === 5 && (
                  <div className="max-w-2xl space-y-5">
                    <div>
                      <h2 className="text-xl font-bold flex items-center gap-2">🎨 Template Customizer</h2>
                      <p className="text-sm text-gray-500 mt-0.5">Atur tampilan subtitle viral dan efek rendering.</p>
                    </div>

                    {/* Template Library Selection */}
                    <div className="space-y-3">
                      <label className="text-xs font-semibold text-gray-600 uppercase tracking-wider">Pilih Template Viral (Preset)</label>
                      <div className="grid grid-cols-2 gap-3">
                        {VIRAL_TEMPLATES.map((tmpl) => {
                          // check if active by comparing config partially
                          const isActive = templateConfig.fontname === tmpl.config.fontname && templateConfig.primary_colour === tmpl.config.primary_colour && templateConfig.fontsize === tmpl.config.fontsize;
                          return (
                            <div
                              key={tmpl.id}
                              onClick={() => setTemplateConfig({ ...templateConfig, ...tmpl.config })}
                              className={`border-2 rounded-xl p-3 cursor-pointer hover:shadow-sm transition-all ${isActive ? 'border-violet-500 bg-violet-50' : 'border-gray-200 bg-white hover:border-violet-300'}`}
                            >
                              <div className={`font-bold text-sm ${isActive ? 'text-violet-700' : 'text-gray-800'}`}>{tmpl.name}</div>
                              <div className="text-[10px] text-gray-500 mt-0.5 leading-snug">{tmpl.desc}</div>
                            </div>
                          );
                        })}
                      </div>
                    </div>

                    {/* Live Preview Video player */}
                    {clipUrl && (
                      <div className="relative rounded-2xl overflow-hidden border shadow-lg bg-black group max-w-[300px] mx-auto">
                        <video src={clipUrl} controls onTimeUpdate={handleTimeUpdate} className="w-full h-auto aspect-[9/16] object-cover" />

                        {/* CSS Live Subtitle Overlay */}
                        {activeOverlayText && (
                          <div
                            className="absolute z-10 w-full flex justify-center text-center px-4 pointer-events-none transition-all duration-100 ease-linear"
                            style={{
                              bottom: `${parseInt(templateConfig.margin_v.toString()) / 19.2}%`,
                              fontFamily: templateConfig.fontname === "Bangers" ? '"Bangers", cursive' : '"Montserrat", sans-serif',
                              fontSize: `${parseInt(templateConfig.fontsize) / 3}px`,
                              fontWeight: 900,
                              color: `#${templateConfig.primary_colour}`,
                              WebkitTextStroke: `${templateConfig.outline / 2}px #${templateConfig.outline_colour}`,
                              textShadow: templateConfig.shadow ? `2px 2px 0px #${templateConfig.outline_colour}` : 'none',
                              lineHeight: 1.1
                            }}
                          >
                            {activeOverlayText}
                          </div>
                        )}
                      </div>
                    )}

                    {/* Controls */}
                    <div className="grid grid-cols-2 lg:grid-cols-3 gap-4 bg-gray-50 p-4 rounded-xl border">
                      <div className="space-y-1">
                        <label className="text-xs font-semibold text-gray-600">Pilih Font</label>
                        <select
                          className="w-full rounded-lg text-sm border-gray-300"
                          value={templateConfig.fontname}
                          onChange={(e) => setTemplateConfig({ ...templateConfig, fontname: e.target.value })}
                        >
                          <option value="Montserrat">Modern (Montserrat)</option>
                          <option value="Bangers">MrBeast Style (Bangers)</option>
                        </select>
                      </div>

                      <div className="space-y-1">
                        <label className="text-xs font-semibold text-gray-600">Warna Teks (Hex)</label>
                        <Input
                          className="rounded-lg text-sm"
                          placeholder="FFFFFF"
                          value={templateConfig.primary_colour}
                          onChange={(e) => setTemplateConfig({ ...templateConfig, primary_colour: e.target.value.replace('#', '') })}
                        />
                      </div>

                      <div className="space-y-1">
                        <label className="text-xs font-semibold text-gray-600">Warna Border (Hex)</label>
                        <Input
                          className="rounded-lg text-sm"
                          placeholder="000000"
                          value={templateConfig.outline_colour}
                          onChange={(e) => setTemplateConfig({ ...templateConfig, outline_colour: e.target.value.replace('#', '') })}
                        />
                      </div>

                      <div className="space-y-1">
                        <label className="text-xs font-semibold text-gray-600">Ukuran Teks (ASS)</label>
                        <Input
                          type="number"
                          className="rounded-lg text-sm"
                          value={templateConfig.fontsize}
                          onChange={(e) => setTemplateConfig({ ...templateConfig, fontsize: e.target.value })}
                        />
                      </div>

                      <div className="space-y-1">
                        <label className="text-xs font-semibold text-gray-600">Tebal Outline</label>
                        <Input
                          type="number"
                          className="rounded-lg text-sm"
                          value={templateConfig.outline}
                          onChange={(e) => setTemplateConfig({ ...templateConfig, outline: parseInt(e.target.value) || 0 })}
                        />
                      </div>

                      <div className="space-y-1">
                        <label className="text-xs font-semibold text-gray-600">Jarak dari Bawah (MarginV)</label>
                        <Input
                          type="number"
                          className="rounded-lg text-sm"
                          value={templateConfig.margin_v}
                          onChange={(e) => setTemplateConfig({ ...templateConfig, margin_v: parseInt(e.target.value) || 0 })}
                        />
                      </div>
                    </div>

                    <Button
                      className="w-full rounded-xl gap-2 bg-gradient-to-r from-violet-600 to-indigo-600"
                      onClick={handleRenderTemplate}
                      disabled={renderingTemplate}
                    >
                      {renderingTemplate ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                      {renderingTemplate ? "🔥 Rendering / Burning Subtitles..." : "🔥 Burn Subtitles & Render"}
                    </Button>
                    <button onClick={() => setWizardStep(4)} className="text-xs text-gray-400 hover:text-gray-600 transition-colors w-full mt-2 text-left">
                      ← Kembali ke Subtitles
                    </button>

                    <div className="text-xs text-center text-gray-400">Atau lewati styling subtitle: <button onClick={() => setWizardStep(6)} className="underline hover:text-gray-600">Buka halaman Export</button></div>
                  </div>
                )}

                {/* ── STEP 6: Export ── */}
                {wizardStep === 6 && (
                  <div className="max-w-2xl space-y-5">
                    <div>
                      <h2 className="text-xl font-bold flex items-center gap-2">📤 Preview & Export</h2>
                      <p className="text-sm text-gray-500 mt-0.5">Review clip dan upload ke platform pilihanmu.</p>
                    </div>
                    {/* Video player */}
                    {clipUrl && (
                      <div className="rounded-2xl overflow-hidden border shadow-lg bg-black">
                        <video key={clipUrl} src={clipUrl} controls className="w-full aspect-video" />
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
