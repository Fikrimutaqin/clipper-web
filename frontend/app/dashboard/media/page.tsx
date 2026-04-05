"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  Library,
  Scissors,
  Trash2,
  RefreshCw,
  Clock,
  HardDrive,
  Film,
  ExternalLink,
  Loader2,
  FolderOpen,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import api from "@/lib/axios";

interface MediaItem {
  task_id: string;
  filename: string;
  youtube_id: string | null;
  size_bytes: number;
  duration_seconds: number | null;
  created_at: number; // unix timestamp
}

interface ClipItem {
  clip_id: string;
  filename: string;
  size_bytes: number;
  duration_seconds: number | null;
  created_at: number;
  url: string;
  full_url: string;
}

function formatDuration(seconds: number | null): string {
  if (seconds === null || seconds <= 0) return "—";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function formatDate(ts: number): string {
  const d = new Date(ts * 1000);
  return d.toLocaleDateString("id-ID", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function totalSize(items: MediaItem[]): number {
  return items.reduce((acc, i) => acc + i.size_bytes, 0);
}

export default function MediaPage() {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<"downloaded" | "clipped">("downloaded");
  const [ytConnected, setYtConnected] = useState(false);

  const [items, setItems] = useState<MediaItem[]>([]);
  const [clips, setClips] = useState<ClipItem[]>([]);

  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [uploadingId, setUploadingId] = useState<string | null>(null);
  const [error, setError] = useState("");


  const fetchMedia = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [mediaRes, clipsRes, statusRes] = await Promise.all([
        api.get("/api/youtube/media"),
        api.get("/api/youtube/media/clips").catch(() => ({ data: { data: [] } })),
        api.get("/api/youtube/status").catch(() => ({ data: { data: { connected: false } } }))
      ]);
      setItems(mediaRes.data.data || []);
      setClips(clipsRes.data.data || []);
      setYtConnected(statusRes.data?.data?.connected || false);
    } catch (e: any) {
      setError(e.response?.data?.detail || "Gagal memuat media library.");
    } finally {

      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchMedia();
  }, [fetchMedia]);

  const handleClip = (taskId: string) => {
    router.push(`/dashboard/clipper?task_id=${taskId}`);
  };

  const handleDelete = async (taskId: string) => {
    if (!confirm("Yakin ingin menghapus video ini dari server?")) return;
    setDeletingId(taskId);
    try {
      await api.delete(`/api/youtube/media/${taskId}`);
      setItems((prev) => prev.filter((i) => i.task_id !== taskId));
    } catch (e: any) {
      alert(e.response?.data?.detail || "Gagal menghapus video.");
    } finally {
      setDeletingId(null);
    }
  };

  const handleDownloadClip = (clipUrl: string, filename: string) => {
    const a = document.createElement('a');
    a.href = clipUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  const handleDeleteClip = async (filename: string) => {
    if (!confirm("Yakin ingin menghapus klip ini? File akan hilang secara permanen.")) return;
    setDeletingId(filename); // reuse state since task_id and filename don't overlap keys usually
    try {
      await api.delete(`/api/youtube/media/clips/${filename}`);
      setClips((prev) => prev.filter((i) => i.filename !== filename));
    } catch (e: any) {
      alert(e.response?.data?.detail || "Gagal menghapus klip.");
    } finally {
      setDeletingId(null);
    }
  };

  const handlePostToPlatform = (clipId: string, filename: string, url: string) => {
    router.push(`/dashboard/clipper?clip_export=${clipId}&filename=${encodeURIComponent(filename)}&url=${encodeURIComponent(url)}`);
  };

  const handleEditStyle = (clipId: string, filename: string, url: string) => {
    router.push(`/dashboard/clipper?edit_style=${clipId}&filename=${encodeURIComponent(filename)}&url=${encodeURIComponent(url)}`);
  };

  return (


    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <div className="rounded-full bg-primary/10 p-2 text-primary">
              <Library className="h-5 w-5" />
            </div>
            <h1 className="text-2xl font-bold text-gray-900">Media Library</h1>
          </div>
          <p className="text-sm text-gray-500 ml-11">
            Video yang sudah terdownload ke server dan siap untuk di-clip.
          </p>
        </div>
        <Button
          variant="outline"
          className="rounded-full flex items-center gap-2"
          onClick={fetchMedia}
          disabled={loading}
        >
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <RefreshCw className="h-4 w-4" />
          )}
          Refresh
        </Button>
      </div>

      {/* Stats Bar */}
      {(items.length > 0 || clips.length > 0) && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-white rounded-2xl border p-4 flex items-center gap-3">
            <div className="rounded-full bg-blue-50 p-2 text-blue-500">
              <Film className="h-5 w-5" />
            </div>
            <div>
              <p className="text-xs text-gray-400 font-medium uppercase tracking-wider">Video Downloaded</p>
              <p className="text-xl font-bold text-gray-900">{items.length}</p>
            </div>
          </div>
          <div className="bg-white rounded-2xl border p-4 flex items-center gap-3">
            <div className="rounded-full bg-violet-50 p-2 text-violet-500">
              <Scissors className="h-5 w-5" />
            </div>
            <div>
              <p className="text-xs text-gray-400 font-medium uppercase tracking-wider">Video Clipped</p>
              <p className="text-xl font-bold text-gray-900">{clips.length}</p>
            </div>
          </div>
          <div className="bg-white rounded-2xl border p-4 flex items-center gap-3">
            <div className="rounded-full bg-purple-50 p-2 text-purple-500">
              <HardDrive className="h-5 w-5" />
            </div>
            <div>
              <p className="text-xs text-gray-400 font-medium uppercase tracking-wider">Total Ukuran</p>
              <p className="text-xl font-bold text-gray-900">{formatBytes(totalSize(items) + totalSize(clips as any))}</p>
            </div>
          </div>
          <div className="bg-white rounded-2xl border p-4 flex items-center gap-3">
            <div className="rounded-full bg-green-50 p-2 text-green-500">
              <Clock className="h-5 w-5" />
            </div>
            <div>
              <p className="text-xs text-gray-400 font-medium uppercase tracking-wider">Durasi Total</p>
              <p className="text-xl font-bold text-gray-900">
                {formatDuration(items.reduce((a, i) => a + (i.duration_seconds ?? 0), 0) + clips.reduce((a, i) => a + (i.duration_seconds ?? 0), 0))}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex border-b">
        <button
          className={`pb-3 px-6 text-sm font-semibold transition-colors border-b-2 ${activeTab === "downloaded" ? "border-primary text-primary" : "border-transparent text-gray-500 hover:text-gray-700"}`}
          onClick={() => setActiveTab("downloaded")}
        >
          Download Area ({items.length})
        </button>
        <button
          className={`pb-3 px-6 text-sm font-semibold transition-colors border-b-2 ${activeTab === "clipped" ? "border-primary text-primary" : "border-transparent text-gray-500 hover:text-gray-700"}`}
          onClick={() => setActiveTab("clipped")}
        >
          Clip Area ({clips.length})
        </button>
      </div>


      {/* Error */}
      {error && (
        <div className="bg-red-50 text-red-600 p-4 rounded-xl border border-red-100 text-sm">
          {error}
        </div>
      )}

      {/* Loading */}
      {loading ? (
        <div className="flex h-64 items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
        </div>
      ) : activeTab === "downloaded" ? (
        items.length === 0 ? (
          /* Empty State Downloaded */
          <div className="flex flex-col items-center justify-center py-24 gap-4 bg-white rounded-2xl border">
            <div className="rounded-full bg-gray-100 p-6">
              <FolderOpen className="h-12 w-12 text-gray-300" />
            </div>
            <div className="text-center">
              <p className="font-bold text-gray-700 text-lg">Belum Ada Video Didownload</p>
              <p className="text-sm text-gray-400 mt-1">
                Pergi ke{" "}
                <button
                  onClick={() => router.push("/dashboard/clipper")}
                  className="text-primary underline underline-offset-2 font-medium"
                >
                  AI Clipper
                </button>{" "}
                untuk mulai streaming/download video.
              </p>
            </div>
          </div>
        ) : (
          /* Video Grid Downloaded */
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {items.map((item) => (
              <div
                key={item.task_id}
                className="group flex flex-col justify-center items-center bg-white rounded-2xl border overflow-hidden shadow-sm hover:shadow-md transition-all duration-200"
              >
                {/* Thumbnail area */}
                <div className="relative aspect-video bg-gradient-to-br from-gray-900 to-gray-700 flex items-center justify-center overflow-hidden mt-2 rounded-lg">
                  {item.youtube_id ? (
                    <img
                      src={`https://img.youtube.com/vi/${item.youtube_id}/mqdefault.jpg`}
                      alt={item.filename}
                      className="w-full h-full object-cover opacity-80 group-hover:opacity-100 transition-opacity"
                      onError={(e) => {
                        (e.target as HTMLImageElement).style.display = "none";
                      }}
                    />
                  ) : (
                    <Film className="h-12 w-12 text-gray-500" />
                  )}

                  {/* Duration badge */}
                  {item.duration_seconds !== null && (
                    <div className="absolute bottom-2 right-2 bg-black/80 text-white text-[11px] font-bold px-2 py-0.5 rounded-md">
                      {formatDuration(item.duration_seconds)}
                    </div>
                  )}

                  {/* Hover overlay with quick actions */}
                  <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-3">
                    <Button
                      size="sm"
                      className="rounded-full gap-1.5"
                      onClick={() => handleClip(item.task_id)}
                    >
                      <Scissors className="h-4 w-4" />
                      Clip Now
                    </Button>
                    {item.youtube_id && (
                      <a
                        href={`https://www.youtube.com/watch?v=${item.youtube_id}`}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        <Button size="sm" variant="secondary" className="rounded-full">
                          <ExternalLink className="h-4 w-4" />
                        </Button>
                      </a>
                    )}
                  </div>
                </div>

                {/* Card body */}
                <div className="p-4 space-y-3 w-full">
                  {/* Filename / YouTube ID */}
                  <div>
                    <p className="text-xs text-gray-400 font-medium uppercase tracking-wider mb-0.5">
                      {item.youtube_id ? "YouTube ID" : "Filename"}
                    </p>
                    <p className="text-sm font-bold text-gray-800 truncate" title={item.filename}>
                      {item.youtube_id || item.filename}
                    </p>
                  </div>

                  {/* Meta chips */}
                  <div className="flex flex-wrap gap-2">
                    <span className="inline-flex items-center gap-1 text-[11px] bg-gray-100 text-gray-600 rounded-full px-2.5 py-1 font-medium">
                      <HardDrive className="h-3 w-3" />
                      {formatBytes(item.size_bytes)}
                    </span>
                    <span className="inline-flex items-center gap-1 text-[11px] bg-gray-100 text-gray-600 rounded-full px-2.5 py-1 font-medium">
                      <Clock className="h-3 w-3" />
                      {formatDate(item.created_at)}
                    </span>
                  </div>

                  {/* Actions */}
                  <div className="flex gap-2 pt-1">
                    <Button
                      className="flex-1 rounded-xl gap-1.5 text-sm"
                      onClick={() => handleClip(item.task_id)}
                    >
                      <Scissors className="h-4 w-4" />
                      Clip Video
                    </Button>
                    <Button
                      variant="outline"
                      className="rounded-xl text-red-500 hover:text-red-600 hover:border-red-200 hover:bg-red-50"
                      onClick={() => handleDelete(item.task_id)}
                      disabled={deletingId === item.task_id}
                      title="Hapus dari server"
                    >
                      {deletingId === item.task_id ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Trash2 className="h-4 w-4" />
                      )}
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )
      ) : (
        clips.length === 0 ? (
          /* Empty State Clipped */
          <div className="flex flex-col items-center justify-center py-24 gap-4 bg-white rounded-2xl border">
            <div className="rounded-full bg-gray-100 p-6">
              <Scissors className="h-12 w-12 text-gray-300" />
            </div>
            <div className="text-center">
              <p className="font-bold text-gray-700 text-lg">Belum Ada Video Clipped</p>
              <p className="text-sm text-gray-400 mt-1">
                Gunakan menu Clip Video untuk membuat video clip baru.
              </p>
            </div>
          </div>
        ) : (
          /* Video Grid Clipped */
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
            {clips.map((item) => (
              <div
                key={item.clip_id}
                className="bg-white rounded-2xl border overflow-hidden shadow-sm hover:shadow-md transition-all duration-200"
              >
                {/* Visual Area */}
                <div className="w-full flex flex-col justify-center items-center">
                  <div className="relative aspect-[9/16] bg-gray-900 flex items-center justify-center overflow-hidden max-h-64 sm:max-h-56">
                    <div className="absolute inset-0 bg-gradient-to-t from-gray-900/60 to-transparent z-10 pointer-events-none" />
                    <video src={item.full_url} className="w-full h-full object-cover" muted preload="metadata" />

                    {/* Duration badge */}
                    {item.duration_seconds !== null && (
                      <div className="absolute bottom-2 right-2 bg-black/80 text-white text-[11px] font-bold px-2 py-0.5 rounded-md z-20">
                        {formatDuration(item.duration_seconds)}
                      </div>
                    )}

                    <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex flex-col items-center justify-center gap-3 z-20">
                      <Button size="sm" className="rounded-full px-6" onClick={() => window.open(item.full_url, '_blank')}>
                        Play Video
                      </Button>
                    </div>
                  </div>
                </div>

                {/* Card body */}
                <div className="p-4 space-y-3">
                  <div>
                    <p className="text-xs text-gray-400 font-medium uppercase tracking-wider mb-0.5">
                      Clip File
                    </p>
                    <p className="text-sm font-bold text-gray-800 truncate" title={item.filename}>
                      {item.filename}
                    </p>
                  </div>

                  {/* Meta chips */}
                  <div className="flex flex-wrap gap-2">
                    <span className="inline-flex items-center gap-1 text-[11px] bg-gray-100 text-gray-600 rounded-full px-2.5 py-1 font-medium">
                      <HardDrive className="h-3 w-3" />
                      {formatBytes(item.size_bytes)}
                    </span>
                    <span className="inline-flex items-center gap-1 text-[11px] bg-gray-100 text-gray-600 rounded-full px-2.5 py-1 font-medium">
                      <Clock className="h-3 w-3" />
                      {formatDate(item.created_at)}
                    </span>
                  </div>

                  {/* Actions */}
                  <div className="flex flex-col gap-2 pt-1">
                    <div className="flex flex-row gap-2 items-center">
                      <Button
                        className="w-full rounded-xl text-sm bg-violet-600 hover:bg-violet-700 text-white border-0"
                        onClick={() => handleEditStyle(item.clip_id, item.filename, item.full_url)}
                      >
                        🎨 Edit Subtitle
                      </Button>
                      {ytConnected && (
                        <Button
                          className="w-full rounded-xl text-sm bg-[#FF0000] hover:bg-[#CC0000] text-white border-0"
                          onClick={() => handlePostToPlatform(item.clip_id, item.filename, item.full_url)}
                        >
                          📤 Post to Platform
                        </Button>
                      )}
                    </div>

                    <div className="flex gap-2">
                      <Button
                        variant="outline"
                        className="flex-1 rounded-xl text-sm"
                        onClick={() => handleDownloadClip(item.full_url, item.filename)}
                      >
                        <HardDrive className="h-4 w-4 mr-1.5" />
                        Download
                      </Button>
                      <Button
                        variant="outline"
                        className="rounded-xl px-3 text-red-500 hover:text-red-600 hover:border-red-200 hover:bg-red-50"
                        onClick={() => handleDeleteClip(item.filename)}
                        disabled={deletingId === item.filename}
                        title="Hapus klip ini"
                      >
                        {deletingId === item.filename ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <Trash2 className="h-4 w-4" />
                        )}
                      </Button>
                    </div>
                  </div>
                </div>
              </div>


            ))}
          </div>
        )
      )}

    </div>
  );
}
