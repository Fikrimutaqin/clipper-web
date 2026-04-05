"use client";

import { useState, useRef, useEffect } from "react";
import {
  Upload, Sparkles, Languages,
  Settings2, Play, CheckCircle2, Loader2, Download,
  History, Trash2, Edit3, ShieldCheck, Video, FolderOpen, Search, Scissors, Copy, Send, ExternalLink, AlertCircle
} from "lucide-react";
import { useSearchParams, useRouter } from "next/navigation";
import api from "@/lib/axios";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";

interface SubtitleEntry {
  start: number;
  end: number;
  text: string;
}

const PLATFORMS = ["YT", "TT", "IG", "FB"] as const;

const LANGUAGES = [
  { code: "id", name: "Bahasa Indonesia", icon: "🇮🇩" },
  { code: "en", name: "English", icon: "🇺🇸" },
  { code: "jw", name: "Basa Jawa", icon: "🇮🇩" },
  { code: "su", name: "Basa Sunda", icon: "🇮🇩" },
  { code: "ms", name: "Bahasa Melayu", icon: "🇲🇾" },
];

export default function VideoEditorPage() {
  const router = useRouter();
  const [file, setFile] = useState<File | null>(null);
  const [videoId, setVideoId] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isRendering, setIsRendering] = useState(false);
  const [targetLang, setTargetLang] = useState("id");
  const [subtitles, setSubtitles] = useState<SubtitleEntry[]>([]);
  const [activeStep, setActiveStep] = useState(1);
  const [finalVideoUrl, setFinalVideoUrl] = useState<string | null>(null);
  const [aiContent, setAiContent] = useState<{ title: string, description: string } | null>(null);
  const [isGeneratingContent, setIsGeneratingContent] = useState(false);

  const [uploadingSocial, setUploadingSocial] = useState(false);
  const [publishPlatform, setPublishPlatform] = useState<"YT" | "TT" | "IG" | "FB">("YT");
  const [platformStatus, setPlatformStatus] = useState<Record<string, boolean>>({ YT: false, TT: false, IG: false, FB: false });
  const [uploadResult, setUploadResult] = useState<{ url: string; youtube_video_id: string } | null>(null);

  const [styling, setStyling] = useState({
    fontname: "Montserrat",
    fontsize: 80,
    primary_colour: "FFFFFF",
    outline_colour: "000000",
    outline: 5,
    alignment: 2,
    margin_v: 200,
  });

  const [mediaItems, setMediaItems] = useState<any[]>([]);
  const [isLoadingMedia, setIsLoadingMedia] = useState(false);
  const [mediaTab, setMediaTab] = useState<"upload" | "library">("upload");

  const searchParams = useSearchParams();
  const fromClip = searchParams.get("from_clip");

  const fileInputRef = useRef<HTMLInputElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    fetchMedia();
    fetchPlatformStatus();
  }, []);

  const fetchPlatformStatus = async () => {
    try {
      const r = await api.get("/api/youtube/status");
      setPlatformStatus(p => ({ ...p, YT: r.data?.data?.connected === true }));
    } catch { }
  };

  const handleConnect = (platform: string) => {
    if (platform !== "YT") {
      alert("Integrasi platform ini belum tersedia. (Coming soon)");
      return;
    }
    const apiBase = (api.defaults.baseURL || "").toString().replace(/\/$/, "");
    const redirectUrl = videoId
      ? `${window.location.origin}/dashboard/video-editor?from_clip=${videoId}`
      : `${window.location.origin}/dashboard/video-editor`;
    window.location.href = `${apiBase}/api/youtube/connect?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  const handleSocialUpload = async () => {
    if (!videoId || !aiContent) return;
    setUploadingSocial(true);
    try {
      const res = await api.post("/api/youtube/upload-clip", {
        clip_id: `final_${videoId}`,
        title: aiContent.title,
        description: aiContent.description,
      });
      setUploadResult(res.data.data);
    } catch (err: any) {
      alert(err.response?.data?.detail || "Gagal upload ke sosial media");
    } finally {
      setUploadingSocial(false);
    }
  };

  useEffect(() => {
    if (fromClip && mediaItems.length > 0) {
      handleSelectMedia("clip", fromClip);
    }
  }, [fromClip, mediaItems]);

  const fetchMedia = async () => {
    setIsLoadingMedia(true);
    try {
      const resp = await api.get("/api/youtube/media");
      const clipsResp = await api.get("/api/youtube/media/clips");

      const downloads = (resp.data.data || []).map((d: any) => ({ ...d, type: "download" }));
      const clips = (clipsResp.data.data || []).map((c: any) => ({ ...c, type: "clip", id: c.clip_id }));

      setMediaItems([...downloads, ...clips]);
    } catch (err) {
      console.error("Failed to fetch media", err);
    } finally {
      setIsLoadingMedia(false);
    }
  };

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const selectedFile = e.target.files[0];
      setFile(selectedFile);
      e.target.value = "";
    }
  };

  const handleUpload = async () => {
    if (!file) {
      alert("Harap pilih file video terlebih dahulu!");
      return;
    }
    setIsUploading(true);
    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await api.post("/api/video-editor/upload", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setVideoId(res.data.data.video_id);
      setActiveStep(2);
    } catch (err: any) {
      alert(err.response?.data?.detail || "Gagal upload video");
    } finally {
      setIsProcessing(false);
    }
  };

  const [selectedMediaUrl, setSelectedMediaUrl] = useState<string | null>(null);

  const handleSelectMedia = async (mediaType: string, id: string) => {
    setIsProcessing(true);
    try {
      const res = await api.post(`/api/video-editor/select-media/${mediaType}/${id}`);
      setVideoId(res.data.data.video_id);

      const filename = res.data.data.filename;
      console.log("filename", filename);
      if (filename) {
        setSelectedMediaUrl(`/api/jobs/clips/${filename}`);
      }

      setActiveStep(2);
    } catch (err: any) {
      alert(err.response?.data?.detail || "Gagal memilih media");
    } finally {
      setIsProcessing(false);
    }
  };

  const handleGenerateSubtitles = async () => {
    if (!videoId) return;
    setIsProcessing(true);
    try {
      const res = await api.post(`/api/video-editor/process/${videoId}/subtitle?target_lang=${targetLang}`);
      setSubtitles(res.data.data.subtitles);
      setActiveStep(3);
    } catch (err: any) {
      alert(err.response?.data?.detail || "Gagal memproses AI Subtitle");
    } finally {
      setIsProcessing(false);
    }
  };

  const handleRender = async () => {
    if (!videoId) return;
    setIsRendering(true);
    try {
      const res = await api.post(`/api/video-editor/process/${videoId}/render`, {
        entries: subtitles,
        template: styling
      });
      const videoUrl = res.data.data.video_url;
      const filename = res.data.data.filename;
      setFinalVideoUrl(videoUrl);

      const exportId = videoId;
      router.push(`/dashboard/clipper?clip_export=${exportId}&filename=${encodeURIComponent(filename)}&url=${encodeURIComponent(videoUrl)}`);

    } catch (err: any) {
      alert(err.response?.data?.detail || "Gagal me-render video");
    } finally {
      setIsRendering(false);
    }
  };

  const updateSubtitle = (index: number, newText: string) => {
    const updated = [...subtitles];
    updated[index].text = newText;
    setSubtitles(updated);
  };

  const removeSubtitle = (index: number) => {
    setSubtitles(subtitles.filter((_, i) => i !== index));
  };

  return (
    <div className="min-h-screen bg-[#F8FAFC] p-8">
      <div className="max-w-6xl mx-auto space-y-8">
        <div className="flex items-center justify-between bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
          <div className="flex items-center gap-4">
            <div className="w-12 h-12 bg-indigo-600 rounded-2xl flex items-center justify-center text-white shadow-lg shadow-indigo-100">
              <Play className="fill-current w-6 h-6" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Local Studio Editor</h1>
              <p className="text-slate-500 text-sm">Transcribe, Clean & Style Locally — No API Credits Required</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {[1, 2, 3, 4].map((step) => (
              <div
                key={step}
                className={`w-10 h-10 rounded-xl flex items-center justify-center font-bold transition-all duration-300 ${activeStep === step
                  ? "bg-indigo-600 text-white scale-110 shadow-lg shadow-indigo-100"
                  : activeStep > step
                    ? "bg-emerald-50 text-emerald-600"
                    : "bg-slate-100 text-slate-400"
                  }`}
              >
                {activeStep > step ? <CheckCircle2 className="w-5 h-5" /> : step}
              </div>
            ))}
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          <div className="lg:col-span-2 space-y-6">
            <div className="aspect-[9/16] max-h-[700px] w-full bg-slate-900 rounded-[2.5rem] shadow-2xl relative overflow-hidden group border-8 border-white">
              {activeStep === 1 && (
                <div className="absolute inset-0 flex flex-col items-center justify-center p-0">
                  <div className="w-full flex border-b border-white/10">
                    <button
                      onClick={() => setMediaTab("upload")}
                      className={`flex-1 py-4 text-xs font-bold uppercase tracking-widest transition-all ${mediaTab === "upload" ? "bg-white/10 text-white" : "text-white/40 hover:text-white/60"}`}
                    >
                      New Upload
                    </button>
                    <button
                      onClick={() => setMediaTab("library")}
                      className={`flex-1 py-4 text-xs font-bold uppercase tracking-widest transition-all ${mediaTab === "library" ? "bg-white/10 text-white" : "text-white/40 hover:text-white/60"}`}
                    >
                      Media Library ({mediaItems.length})
                    </button>
                  </div>

                  {mediaTab === "upload" ? (
                    <div className="flex-1 flex flex-col items-center justify-center p-12 text-center text-white/80 w-full">
                      <div className="w-24 h-24 bg-white/10 rounded-full flex items-center justify-center mb-6 backdrop-blur-sm group-hover:scale-110 transition-transform duration-500">
                        <Upload className="w-10 h-10 text-white" />
                      </div>
                      <h2 className="text-xl font-bold text-white mb-2">Upload File Lokal</h2>
                      <p className="max-w-xs mb-8 text-sm opacity-60">Pilih video (MP4) dari komputer kamu.</p>
                      <input
                        type="file"
                        ref={fileInputRef}
                        className="hidden"
                        accept="video/*"
                        onChange={onFileChange}
                      />
                      <Button
                        onClick={() => fileInputRef.current?.click()}
                        className="bg-white text-indigo-600 hover:bg-slate-100 rounded-2xl px-8 py-6 font-bold shadow-xl"
                      >
                        {file ? file.name : "Pilih File Video"}
                      </Button>
                      {file && !isUploading && (
                        <Button
                          onClick={handleUpload}
                          className="mt-4 bg-indigo-500/20 hover:bg-indigo-500/40 text-white border border-white/20 rounded-2xl px-6"
                        >
                          Mulai Upload →
                        </Button>
                      )}
                      {isUploading && (
                        <div className="mt-6 flex items-center gap-3 bg-white/10 px-6 py-3 rounded-2xl backdrop-blur-md">
                          <Loader2 className="w-5 h-5 animate-spin text-white" />
                          <span className="font-medium text-sm">Uploading...</span>
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="flex-1 w-full overflow-y-auto p-6 space-y-4">
                      <div className="flex items-center justify-between mb-4">
                        <h4 className="text-sm font-bold text-white/60 uppercase tracking-widest">Pilih dari Media Sebelumnya</h4>
                        <Button variant="ghost" size="sm" onClick={fetchMedia} className="text-white/40 hover:text-white">
                          <History className="w-4 h-4" />
                        </Button>
                      </div>

                      <div className="grid grid-cols-2 gap-4">
                        {mediaItems.map((item, idx) => (
                          <div
                            key={item.task_id || item.id}
                            onClick={() => handleSelectMedia(item.type, item.task_id || item.id)}
                            className="group/item relative bg-white/5 border border-white/10 rounded-2xl overflow-hidden cursor-pointer hover:bg-white/10 hover:border-white/20 transition-all p-3"
                          >
                            <div className="aspect-video bg-black/40 rounded-xl mb-3 flex items-center justify-center relative overflow-hidden">
                              {item.type === "clip" ? <Scissors className="w-6 h-6 text-indigo-400 opacity-50" /> : <Video className="w-6 h-6 text-white/20" />}
                              <div className="absolute inset-0 bg-indigo-600/0 group-hover/item:bg-indigo-600/40 flex items-center justify-center transition-all">
                                <Play className="w-8 h-8 text-white opacity-0 group-hover/item:opacity-100 scale-50 group-hover/item:scale-100 transition-all" />
                              </div>
                            </div>
                            <p className="text-[10px] font-bold text-white/80 truncate mb-1">
                              {item.filename || `Clip ${item.id}`}
                            </p>
                            <div className="flex items-center justify-between">
                              <span className={`text-[8px] px-1.5 py-0.5 rounded-md font-bold uppercase ${item.type === 'clip' ? 'bg-amber-500/20 text-amber-500' : 'bg-blue-500/20 text-blue-500'}`}>
                                {item.type}
                              </span>
                              <span className="text-[8px] text-white/40 font-mono">
                                {item.duration_seconds ? `${Math.round(item.duration_seconds)}s` : '--'}
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>

                      {mediaItems.length === 0 && (
                        <div className="flex flex-col items-center justify-center h-full text-white/20 py-20">
                          <FolderOpen className="w-12 h-12 mb-4" />
                          <p className="font-bold">Library Kosong</p>
                          <p className="text-xs">Download video di menu AI Clipper dulu.</p>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}

              {(activeStep > 1 && (file || selectedMediaUrl)) && (
                <div className="absolute inset-0 bg-black">
                  <video
                    ref={videoRef}
                    src={finalVideoUrl || (selectedMediaUrl ? (selectedMediaUrl.startsWith('http') ? selectedMediaUrl : `${window.location.origin}${selectedMediaUrl}`) : URL.createObjectURL(file!))}
                    className="w-full h-full object-contain"
                    controls
                  />
                </div>
              )}
            </div>

            {activeStep === 4 && finalVideoUrl && (
              <div className="bg-emerald-50 border border-emerald-100 p-6 rounded-3xl flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <div className="w-12 h-12 bg-emerald-500 rounded-2xl flex items-center justify-center text-white">
                    <ShieldCheck className="w-6 h-6" />
                  </div>
                  <div>
                    <h3 className="font-bold text-emerald-900">Render Selesai!</h3>
                    <p className="text-emerald-700 text-sm">Video kamu sudah siap diunduh dengan subtitle permanen.</p>
                  </div>
                </div>
                <a href={finalVideoUrl} download={`clipfix_${videoId}.mp4`}>
                  <Button className="bg-emerald-600 hover:bg-emerald-700 rounded-2xl px-6 gap-2 font-bold shadow-lg shadow-emerald-100">
                    <Download className="w-4 h-4" /> Download Video
                  </Button>
                </a>
              </div>
            )}
          </div>

          {/* Controls Panel */}
          <div className="space-y-6">
            {/* Step 2: Language & Local Config */}
            {activeStep === 2 && (
              <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100 space-y-6">
                <div className="flex items-center gap-3 mb-2">
                  <div className="p-2 bg-indigo-50 rounded-xl text-indigo-600">
                    <ShieldCheck className="w-5 h-5" />
                  </div>
                  <h3 className="font-bold text-slate-800">Local Subtitle Config</h3>
                </div>

                <div className="space-y-4">
                  <p className="text-sm text-slate-500 font-medium">Auto-Subtitle (Faster Whisper):</p>
                  <div className="p-4 bg-slate-50 border border-slate-100 rounded-2xl flex items-start gap-3">
                    <Languages className="w-5 h-5 text-indigo-500 mt-0.5" />
                    <div className="text-xs text-slate-600 leading-relaxed">
                      Sistem akan memproses audio secara lokal di server. Proses ini gratis (Tanpa biaya token API).
                    </div>
                  </div>

                  <Separator className="my-6" />

                  <Button
                    onClick={handleGenerateSubtitles}
                    disabled={isProcessing}
                    className="w-full bg-indigo-600 hover:bg-indigo-700 py-8 rounded-3xl text-lg font-bold shadow-xl shadow-indigo-100 gap-3"
                  >
                    {isProcessing ? (
                      <>
                        <Loader2 className="w-6 h-6 animate-spin" />
                        Transcribing...
                      </>
                    ) : (
                      <>
                        <Play className="w-6 h-6 fill-current" />
                        Generate Local Subtitle
                      </>
                    )}
                  </Button>
                  <p className="text-[10px] text-slate-400 text-center uppercase tracking-widest font-bold">
                    Local Processing — 100% Free
                  </p>
                </div>
              </div>
            )}

            {/* Step 3: Editor & Styling */}
            {activeStep === 3 && (
              <div className="space-y-4">
                <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100">
                  <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-3">
                      <div className="p-2 bg-amber-50 rounded-xl text-amber-600">
                        <Edit3 className="w-5 h-5" />
                      </div>
                      <h3 className="font-bold text-slate-800">Subtitle Editor</h3>
                    </div>
                    <span className="bg-slate-100 text-slate-600 text-[10px] font-bold px-2 py-1 rounded-lg uppercase">
                      {subtitles.length} Baris
                    </span>
                  </div>

                  <div className="max-h-[350px] overflow-y-auto space-y-3 pr-2 scrollbar-thin">
                    {subtitles.map((sub, idx) => (
                      <div key={idx} className="group relative bg-slate-50 border border-slate-100 p-3 rounded-2xl hover:bg-white hover:border-indigo-100 transition-all">
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-[10px] font-bold text-slate-400 font-mono">
                            {sub.start.toFixed(1)}s → {sub.end.toFixed(1)}s
                          </span>
                          <button
                            onClick={() => removeSubtitle(idx)}
                            className="p-1.5 text-slate-300 hover:text-red-500 hover:bg-red-50 rounded-lg opacity-0 group-hover:opacity-100 transition-opacity"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                        <textarea
                          value={sub.text}
                          onChange={(e) => updateSubtitle(idx, e.target.value)}
                          className="w-full bg-transparent border-none text-sm font-medium text-slate-700 resize-none focus:ring-0 p-0 leading-relaxed"
                          rows={2}
                        />
                      </div>
                    ))}
                  </div>
                </div>

                <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100 space-y-4">
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-indigo-50 rounded-xl text-indigo-600">
                      <Settings2 className="w-5 h-5" />
                    </div>
                    <h3 className="font-bold text-slate-800">Visual Styling</h3>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1">
                      <p className="text-[10px] font-bold text-slate-400 uppercase">Text Color</p>
                      <div className="flex gap-2">
                        <input
                          type="color"
                          className="w-10 h-10 rounded-xl overflow-hidden cursor-pointer border-none"
                          value={"#" + styling.primary_colour}
                          onChange={(e) => setStyling({ ...styling, primary_colour: e.target.value.replace("#", "") })}
                        />
                        <Input
                          value={styling.primary_colour}
                          onChange={(e) => setStyling({ ...styling, primary_colour: e.target.value })}
                          className="bg-slate-50 border-slate-100 rounded-xl font-mono text-xs"
                        />
                      </div>
                    </div>
                    <div className="space-y-1">
                      <p className="text-[10px] font-bold text-slate-400 uppercase">Size</p>
                      <Input
                        type="number"
                        value={styling.fontsize}
                        onChange={(e) => setStyling({ ...styling, fontsize: parseInt(e.target.value) })}
                        className="bg-slate-50 border-slate-100 rounded-xl"
                      />
                    </div>
                  </div>

                  <Button
                    onClick={handleRender}
                    disabled={isRendering}
                    className="w-full bg-indigo-600 hover:bg-indigo-700 py-8 rounded-3xl text-lg font-bold shadow-xl shadow-indigo-100 mt-4"
                  >
                    {isRendering ? (
                      <>
                        <Loader2 className="w-6 h-6 animate-spin" />
                        Burning Text...
                      </>
                    ) : (
                      <>
                        <Video className="w-6 h-6" />&nbsp;
                        Render Video
                      </>
                    )}
                  </Button>
                </div>
              </div>
            )}

            {/* Step 4: Final Actions */}
            {activeStep === 4 && (
              <div className="space-y-6">
                <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100 space-y-6">
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-indigo-50 rounded-xl text-indigo-600">
                      <Sparkles className="w-5 h-5" />
                    </div>
                    <h3 className="font-bold text-slate-800">AI Social Content</h3>
                  </div>

                  {isGeneratingContent ? (
                    <div className="py-12 flex flex-col items-center justify-center space-y-3 opacity-40">
                      <Loader2 className="w-8 h-8 animate-spin" />
                      <p className="text-xs font-bold uppercase tracking-widest">Generating Viral Content...</p>
                    </div>
                  ) : aiContent ? (
                    <div className="space-y-4">
                      <div className="group relative bg-slate-50 border border-slate-100 p-4 rounded-2xl">
                        <p className="text-[10px] font-bold text-slate-400 uppercase mb-2">Viral Title</p>
                        <p className="text-sm font-bold text-slate-800 leading-relaxed">{aiContent.title}</p>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity"
                          onClick={() => { navigator.clipboard.writeText(aiContent.title); alert("Judul disalin!") }}
                        >
                          <Copy className="w-3.5 h-3.5" />
                        </Button>
                      </div>
                      <div className="group relative bg-slate-50 border border-slate-100 p-4 rounded-2xl">
                        <p className="text-[10px] font-bold text-slate-400 uppercase mb-2">Social Description</p>
                        <p className="text-xs text-slate-600 leading-relaxed">{aiContent.description}</p>
                        <Button
                          size="sm"
                          variant="ghost"
                          className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity"
                          onClick={() => { navigator.clipboard.writeText(aiContent.description); alert("Deskripsi disalin!") }}
                        >
                          <Copy className="w-3.5 h-3.5" />
                        </Button>
                      </div>
                    </div>
                  ) : null}
                </div>

                <div className="bg-white p-6 rounded-3xl shadow-sm border border-slate-100 space-y-6 text-center">
                  <div className="w-20 h-20 bg-emerald-50 text-emerald-500 rounded-full flex items-center justify-center mx-auto">
                    <ShieldCheck className="w-10 h-10" />
                  </div>
                  <h3 className="text-xl font-bold text-slate-800">Video Selesai Di-render!</h3>

                  <div className="space-y-4 pt-2">
                    <p className="text-xs font-bold text-slate-400 uppercase tracking-widest">Siap Posting ke Sosmed?</p>
                    <div className="flex justify-center gap-2">
                      {PLATFORMS.map(p => (
                        <button
                          key={p}
                          onClick={() => setPublishPlatform(p)}
                          className={`px-4 py-2 rounded-xl text-xs font-bold transition-all ${publishPlatform === p
                            ? "bg-indigo-600 text-white shadow-lg shadow-indigo-100"
                            : "bg-slate-50 text-slate-400 hover:bg-slate-100"
                            }`}
                        >
                          {p}
                        </button>
                      ))}
                    </div>

                    {!platformStatus[publishPlatform] ? (
                      <div className="bg-amber-50 border border-amber-100 p-4 rounded-2xl space-y-3">
                        <p className="text-[10px] text-amber-700 font-medium">Akun {publishPlatform} belum terhubung.</p>
                        <Button
                          size="sm"
                          onClick={() => handleConnect(publishPlatform)}
                          className="bg-amber-600 hover:bg-amber-700 rounded-xl px-6 h-9"
                        >
                          Sambungkan Sekarang
                        </Button>
                      </div>
                    ) : uploadResult ? (
                      <div className="bg-emerald-50 border border-emerald-100 p-4 rounded-2xl flex items-center justify-between">
                        <div className="text-left">
                          <p className="text-[10px] text-emerald-700 font-bold uppercase">Berhasil Diupload!</p>
                          <a href={uploadResult.url} target="_blank" className="text-xs font-bold text-emerald-600 underline flex items-center gap-1">
                            Lihat Video <ExternalLink className="w-3 h-3" />
                          </a>
                        </div>
                        <CheckCircle2 className="w-6 h-6 text-emerald-500" />
                      </div>
                    ) : (
                      <Button
                        onClick={handleSocialUpload}
                        disabled={uploadingSocial || !aiContent}
                        className="w-full bg-indigo-600 hover:bg-indigo-700 py-7 rounded-2xl shadow-xl shadow-indigo-100 gap-2 font-bold"
                      >
                        {uploadingSocial ? (
                          <>
                            <Loader2 className="w-5 h-5 animate-spin" />
                            Posting ke {publishPlatform}...
                          </>
                        ) : (
                          <>
                            <Send className="w-5 h-5" />
                            Upload ke {publishPlatform} Sekarang
                          </>
                        )}
                      </Button>
                    )}
                  </div>

                  <Separator className="my-6" />

                  <div className="space-y-4">
                    <p className="text-slate-500 text-sm">Ingin membuat video lain dengan studio AI kami?</p>
                    <Button
                      onClick={() => window.location.reload()}
                      variant="outline"
                      className="w-full border-slate-200 text-slate-600 hover:bg-slate-50 rounded-2xl py-6 font-bold"
                    >
                      🚀 Buat Video Baru
                    </Button>
                  </div>
                </div>
              </div>
            )}

            {/* Empty State/Instructions */}
            {activeStep === 1 && !file && (
              <div className="bg-indigo-600 p-8 rounded-[2rem] text-white space-y-6 relative overflow-hidden shadow-2xl shadow-indigo-200">
                <div className="absolute top-0 right-0 -mr-8 -mt-8 w-40 h-40 bg-white/10 rounded-full blur-3xl"></div>
                <h3 className="text-xl font-bold leading-tight">Local Processing. Zero Token Cost.</h3>
                <ul className="space-y-4 text-indigo-100 text-sm">
                  <li className="flex gap-3">
                    <div className="shrink-0 w-6 h-6 rounded-full bg-white/20 flex items-center justify-center text-[10px] font-bold">1</div>
                    <p><b>Resource:</b> Gunakan file lokal atau ambil dari Media Library.</p>
                  </li>
                  <li className="flex gap-3">
                    <div className="shrink-0 w-6 h-6 rounded-full bg-white/20 flex items-center justify-center text-[10px] font-bold">2</div>
                    <p><b>Faster Whisper:</b> Transkripsi dijalankan di CPU server kamu secara gratis.</p>
                  </li>
                  <li className="flex gap-3">
                    <div className="shrink-0 w-6 h-6 rounded-full bg-white/20 flex items-center justify-center text-[10px] font-bold">3</div>
                    <p><b>Permanen:</b> Subtitle langsung dibakar ke video (MP4) dengan styling pilihanmu.</p>
                  </li>
                </ul>
                <div className="pt-4">
                  <div className="bg-black/20 p-4 rounded-2xl flex items-center gap-4">
                    <ShieldCheck className="w-8 h-8 opacity-50" />
                    <div className="text-[10px] font-medium opacity-70 tracking-widest uppercase">100% Pemrosesan Lokal - Aman & Hemat</div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
