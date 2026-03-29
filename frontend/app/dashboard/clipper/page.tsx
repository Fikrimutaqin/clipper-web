"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { 
  Search, 
  Video, 
  Download, 
  Loader2, 
  Zap, 
  Scissors, 
  Play, 
  PlusCircle,
  Send,
  ExternalLink,
  CheckCircle2,
  AlertCircle
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import api from "@/lib/axios";
import Link from "next/link";

interface VideoItem {
  id: string;
  snippet: {
    title: string;
    thumbnails: {
      medium: { url: string };
    };
    channelTitle: string;
  };
  statistics: {
    viewCount: string;
  };
}

export default function ClipperPage() {
  const router = useRouter();
  const [searchUrl, setSearchUrl] = useState("");
  const [videos, setVideos] = useState<VideoItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState<{ id: string; progress: number; task_id?: string } | null>(null);
  const [error, setError] = useState("");

  // Trimming states
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [suggestions, setSuggestions] = useState<any[]>([]);
  const [trimSettings, setTrimSettings] = useState({ start: 0, end: 60, format: "regular" });
  const [trimming, setTrimming] = useState(false);
  const [clipResult, setClipResult] = useState<{ clip_id: string; url: string } | null>(null);
  const [activeJobs, setActiveJobs] = useState<any[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string>("");
  const [submittingToJob, setSubmittingToJob] = useState(false);

  const fetchActiveJobs = async () => {
    try {
      const res = await api.get("/api/jobs/my-jobs");
      // Filter only IN_PROGRESS jobs for Clippers
      const inProgress = res.data.data.filter((j: any) => j.status === "IN_PROGRESS");
      setActiveJobs(inProgress);
      if (inProgress.length > 0) setSelectedJobId(inProgress[0].id);
    } catch (err) {
      console.error("Failed to fetch active jobs", err);
    }
  };

  const fetchTrending = async () => {
    setLoading(true);
    setError("");
    try {
      fetchActiveJobs(); // Fetch jobs in parallel
      const res = await api.get("/api/youtube/discover?region=ID&limit=12");
      setVideos(res.data.data?.items || []);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Gagal mengambil video trending.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTrending();
  }, []);

  const fetchSuggestions = async (taskId: string) => {
    try {
      const res = await api.get(`/api/youtube/suggest/${taskId}`);
      setSuggestions(res.data.data.suggestions);
      if (res.data.data.suggestions.length > 0) {
        setTrimSettings({
          ...trimSettings,
          start: Math.floor(res.data.data.suggestions[0].start_seconds),
          end: Math.ceil(res.data.data.suggestions[0].end_seconds),
        });
      }
    } catch (err) {
      console.error("Failed to fetch suggestions", err);
    }
  };

  const handleTrim = async () => {
    if (!selectedTaskId) return;
    setTrimming(true);
    setError("");
    setClipResult(null);
    try {
      const res = await api.post("/api/youtube/trim", {
        task_id: selectedTaskId,
        start_seconds: trimSettings.start,
        end_seconds: trimSettings.end,
        format_type: trimSettings.format,
      });
      setClipResult(res.data.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Gagal memproses clip video.");
    } finally {
      setTrimming(false);
    }
  };

  const handleSubmitToJob = async () => {
    if (!selectedJobId || !clipResult) return;
    setSubmittingToJob(true);
    try {
      await api.post(`/api/marketplace/jobs/${selectedJobId}/submit`, {
        result_url: `http://localhost:8000${clipResult.url}`
      });
      alert("Hasil clipping berhasil dikirim ke pekerjaan!");
      router.push(`/dashboard/jobs/${selectedJobId}`);
    } catch (err) {
      alert("Gagal mengirim hasil ke pekerjaan.");
    } finally {
      setSubmittingToJob(false);
    }
  };

  const handleDownload = async (url: string, videoId: string) => {
    setDownloading({ id: videoId, progress: 0 });
    setSelectedTaskId(null);
    setSuggestions([]);
    setClipResult(null);
    try {
      const res = await api.post("/api/youtube/download", null, { params: { url } });
      const taskId = res.data.data.task_id;
      setDownloading({ id: videoId, progress: 0, task_id: taskId });
      
      // Poll status
      const interval = setInterval(async () => {
        try {
          const statusRes = await api.get(`/api/youtube/download/${taskId}`);
          if (statusRes.data.data.status === "done") {
            setDownloading({ id: videoId, progress: 100, task_id: taskId });
            clearInterval(interval);
            setSelectedTaskId(taskId);
            fetchSuggestions(taskId);
            setTimeout(() => setDownloading(null), 1000);
          } else if (statusRes.data.data.status === "error") {
            setError("Gagal mendownload video.");
            setDownloading(null);
            clearInterval(interval);
          } else {
            setDownloading({ id: videoId, progress: statusRes.data.data.progress, task_id: taskId });
          }
        } catch (e) {
          clearInterval(interval);
        }
      }, 2000);
    } catch (err) {
      setDownloading(null);
      alert("Gagal memulai download.");
    }
  };

  return (
    <div className="space-y-8">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">AI Clipper Tools</h1>
          <p className="text-sm text-gray-500">Temukan momen viral dan potong video secara otomatis.</p>
        </div>
        <div className="flex w-full max-w-md gap-2">
          <Input 
            placeholder="Paste YouTube URL..." 
            value={searchUrl}
            onChange={(e) => setSearchUrl(e.target.value)}
            className="rounded-full"
          />
          <Button onClick={() => handleDownload(searchUrl, "manual")} disabled={!searchUrl} className="rounded-full">
            <Download className="h-4 w-4 mr-2" /> Download
          </Button>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 text-red-600 p-4 rounded-xl flex items-center gap-3 border border-red-100">
          <AlertCircle className="h-5 w-5" />
          <span className="text-sm">{error}</span>
        </div>
      )}

      {/* Trimming UI Section */}
      {selectedTaskId && (
        <div className="bg-white rounded-2xl border p-8 shadow-sm space-y-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="rounded-full bg-primary/10 p-2 text-primary">
                <Scissors className="h-5 w-5" />
              </div>
              <h2 className="text-xl font-bold text-gray-900">Clip Editor</h2>
            </div>
            <Button variant="ghost" size="sm" onClick={() => setSelectedTaskId(null)}>Tutup</Button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium text-gray-700">Start (detik)</label>
                  <Input 
                    type="number" 
                    value={trimSettings.start}
                    onChange={(e) => setTrimSettings({...trimSettings, start: parseFloat(e.target.value)})}
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium text-gray-700">End (detik)</label>
                  <Input 
                    type="number" 
                    value={trimSettings.end}
                    onChange={(e) => setTrimSettings({...trimSettings, end: parseFloat(e.target.value)})}
                  />
                </div>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium text-gray-700">Format</label>
                <div className="flex gap-4">
                  <Button 
                    variant={trimSettings.format === "regular" ? "default" : "outline"}
                    className="flex-1 rounded-xl"
                    onClick={() => setTrimSettings({...trimSettings, format: "regular"})}
                  >
                    16:9 Regular
                  </Button>
                  <Button 
                    variant={trimSettings.format === "short" ? "default" : "outline"}
                    className="flex-1 rounded-xl"
                    onClick={() => setTrimSettings({...trimSettings, format: "short"})}
                  >
                    9:16 Short/TikTok
                  </Button>
                </div>
              </div>

              {suggestions.length > 0 && (
                <div className="space-y-3">
                  <label className="text-xs font-bold text-gray-400 uppercase tracking-wider">AI Suggestions</label>
                  <div className="flex flex-wrap gap-2">
                    {suggestions.map((s, idx) => (
                      <Button 
                        key={idx}
                        variant="secondary"
                        size="sm"
                        className="text-xs rounded-full"
                        onClick={() => setTrimSettings({
                          ...trimSettings,
                          start: Math.floor(s.start_seconds),
                          end: Math.ceil(s.end_seconds)
                        })}
                      >
                        Segment {idx + 1} ({Math.round(s.score * 100)}% score)
                      </Button>
                    ))}
                  </div>
                </div>
              )}

              <Button 
                className="w-full py-6 text-lg rounded-xl" 
                onClick={handleTrim}
                disabled={trimming}
              >
                {trimming ? <Loader2 className="h-6 w-6 animate-spin mr-2" /> : <Play className="h-6 w-6 mr-2" />}
                {trimming ? "Sedang Memproses..." : "Mulai Clipping"}
              </Button>
            </div>

            <div className="flex flex-col items-center justify-center border-2 border-dashed rounded-2xl bg-gray-50 p-8 min-h-[300px]">
              {clipResult ? (
                <div className="w-full space-y-4">
                  <div className="aspect-video bg-black rounded-xl overflow-hidden shadow-lg">
                    <video 
                      src={`http://localhost:8000${clipResult.url}`} 
                      controls 
                      className="w-full h-full"
                    />
                  </div>
                  <div className="flex gap-2">
                    <a href={`http://localhost:8000${clipResult.url}`} download className="flex-1">
                      <Button variant="outline" className="w-full rounded-xl">
                        <Download className="h-4 w-4 mr-2" /> Download
                      </Button>
                    </a>
                    <Button 
                      className="flex-1 rounded-xl"
                      disabled={submittingToJob || activeJobs.length === 0}
                      onClick={handleSubmitToJob}
                    >
                      {submittingToJob ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4 mr-2" />}
                      Submit to Job
                    </Button>
                  </div>
                  
                  {activeJobs.length > 0 ? (
                    <div className="space-y-2">
                      <label className="text-xs font-bold text-gray-400 uppercase tracking-wider">Select Active Job</label>
                      <select 
                        className="w-full rounded-xl border-gray-300 text-sm focus:ring-primary focus:border-primary"
                        value={selectedJobId}
                        onChange={(e) => setSelectedJobId(e.target.value)}
                      >
                        {activeJobs.map(job => (
                          <option key={job.id} value={job.id}>{job.title}</option>
                        ))}
                      </select>
                    </div>
                  ) : (
                    <p className="text-xs text-center text-gray-400">Kamu tidak memiliki pekerjaan aktif untuk di-submit.</p>
                  )}
                </div>
              ) : trimming ? (
                <div className="text-center space-y-4">
                  <div className="flex justify-center">
                    <div className="h-12 w-12 animate-spin rounded-full border-4 border-primary border-t-transparent" />
                  </div>
                  <p className="text-gray-500 font-medium animate-pulse">AI sedang menganalisis & memotong video...</p>
                </div>
              ) : (
                <div className="text-center">
                  <Video className="h-12 w-12 text-gray-300 mx-auto mb-4" />
                  <p className="text-gray-400 text-sm">Pilih segment dan klik "Mulai Clipping" untuk melihat hasil.</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      <div>
        <div className="flex items-center gap-2 mb-6">
          <Zap className="h-5 w-5 text-primary fill-primary" />
          <h2 className="text-xl font-bold text-gray-900">Trending in Indonesia</h2>
        </div>

        {loading ? (
          <div className="flex h-64 items-center justify-center">
            <Loader2 className="h-8 w-8 animate-spin text-primary" />
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
            {videos.map((video) => (
              <div key={video.id} className="group bg-white rounded-2xl border overflow-hidden shadow-sm hover:shadow-md transition-all">
                <div className="relative aspect-video">
                  <img 
                    src={video.snippet.thumbnails.medium.url} 
                    alt={video.snippet.title}
                    className="w-full h-full object-cover"
                  />
                  <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-2">
                    <Button 
                      size="sm" 
                      variant="secondary" 
                      className="rounded-full"
                      onClick={() => handleDownload(`https://youtube.com/watch?v=${video.id}`, video.id)}
                      disabled={downloading?.id === video.id}
                    >
                      {downloading?.id === video.id ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Download className="h-4 w-4 mr-1" />
                      )}
                      Server
                    </Button>
                    <a href={`https://youtube.com/watch?v=${video.id}`} target="_blank">
                      <Button size="sm" variant="secondary" className="rounded-full">
                        <ExternalLink className="h-4 w-4" />
                      </Button>
                    </a>
                  </div>
                </div>
                <div className="p-4">
                  <h3 className="font-bold text-sm text-gray-900 line-clamp-2 mb-1">{video.snippet.title}</h3>
                  <p className="text-xs text-gray-500 mb-3">{video.snippet.channelTitle}</p>
                  
                  {downloading?.id === video.id ? (
                    <div className="w-full bg-gray-100 h-1.5 rounded-full overflow-hidden">
                      <div 
                        className="bg-primary h-full transition-all duration-500" 
                        style={{ width: `${downloading.progress}%` }}
                      />
                    </div>
                  ) : (
                    <div className="flex items-center justify-between text-[10px] text-gray-400 font-medium uppercase tracking-wider">
                      <span>{parseInt(video.statistics.viewCount).toLocaleString()} views</span>
                      <span className="flex items-center text-primary">
                        <CheckCircle2 className="h-3 w-3 mr-1" /> Ready
                      </span>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
