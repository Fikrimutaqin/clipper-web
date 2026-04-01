"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { 
  Loader2, 
  Star, 
  MessageSquare, 
  Globe, 
  ExternalLink,
  Briefcase,
  PlayCircle,
  ArrowLeft,
  Video
} from "lucide-react";
import { Button } from "@/components/ui/button";
import api from "@/lib/axios";
import Link from "next/link";

interface Clipper {
  id: string;
  full_name: string;
  avatar_url?: string;
  rating_avg?: number | null;
  rating_count?: number;
  portfolio: {
    bio: string;
    social_links: {
      youtube?: string;
      instagram?: string;
      twitter?: string;
      tiktok?: string;
    };
    video_samples: string[];
  };
}

export default function ClipperDetailPage() {
  const { id } = useParams();
  const router = useRouter();
  const { user } = useAuth();
  const [clipper, setClipper] = useState<Clipper | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeJobs, setActiveJobs] = useState<any[]>([]);
  const [showPendingJobs, setShowPendingJobs] = useState(false);
  const [selectedJobId, setSelectedJobId] = useState("");
  const [inviting, setInviting] = useState(false);
  const [inviteError, setInviteError] = useState("");
  const [depositing, setDepositing] = useState(false);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await api.get("/api/marketplace/clippers");
        const found = res.data.data.find((c: any) => c.id === id);
        setClipper(found);

        if (user?.role === "OWNER") {
          const jobsRes = await api.get("/api/jobs/my-jobs");
          const openJobs = jobsRes.data.data.filter((j: any) => j.status === "OPEN");
          setActiveJobs(openJobs);
          const firstEligible = openJobs.find((j: any) => (j.payment_status || "PENDING") === "ESCROW_HOLD");
          if (firstEligible) setSelectedJobId(firstEligible.id);
          else if (openJobs.length > 0) setSelectedJobId(openJobs[0].id);
        }
      } catch (err) {
        console.error("Failed to fetch clipper detail", err);
      } finally {
        setLoading(false);
      }
    };
    if (id) fetchData();
  }, [id, user]);

  const eligibleJobs = activeJobs.filter((j: any) => (j.payment_status || "PENDING") === "ESCROW_HOLD");
  const visibleJobs = showPendingJobs ? activeJobs : eligibleJobs;
  const selectedJob = activeJobs.find((j: any) => j.id === selectedJobId);
  const selectedPaymentStatus = selectedJob?.payment_status || "PENDING";
  const canInvite = Boolean(selectedJobId) && selectedPaymentStatus === "ESCROW_HOLD";

  const refreshOpenJobs = async () => {
    if (!user || user.role !== "OWNER") return;
    const jobsRes = await api.get("/api/jobs/my-jobs");
    const openJobs = jobsRes.data.data.filter((j: any) => j.status === "OPEN");
    setActiveJobs(openJobs);
    const stillSelected = openJobs.find((j: any) => j.id === selectedJobId);
    if (!stillSelected) {
      const firstEligible = openJobs.find((j: any) => (j.payment_status || "PENDING") === "ESCROW_HOLD");
      if (firstEligible) setSelectedJobId(firstEligible.id);
      else if (openJobs.length > 0) setSelectedJobId(openJobs[0].id);
      else setSelectedJobId("");
    }
  };

  const handleDepositEscrow = async () => {
    if (!user || user.role !== "OWNER") return;
    if (!selectedJobId) return;
    setDepositing(true);
    setInviteError("");
    try {
      await api.post(`/api/marketplace/jobs/${selectedJobId}/pay`);
      await refreshOpenJobs();
    } catch (err: any) {
      setInviteError(err.response?.data?.detail || "Gagal deposit escrow.");
    } finally {
      setDepositing(false);
    }
  };

  const handleInvite = async () => {
    if (!user || user.role !== "OWNER" || !clipper) return;
    if (!selectedJobId) return;
    setInviting(true);
    setInviteError("");
    try {
      if (!canInvite) {
        setInviteError("Dana belum dititipkan. Silakan deposit ke Escrow dulu (ESCROW_HOLD).");
        return;
      }
      await api.post(`/api/marketplace/jobs/${selectedJobId}/invite`, {
        clipper_id: clipper.id,
      });
      alert("Clipper berhasil diundang. Pekerjaan dimulai!");
      router.push(`/dashboard/jobs/${selectedJobId}`);
    } catch (err: any) {
      setInviteError(err.response?.data?.detail || "Gagal mengundang clipper.");
    } finally {
      setInviting(false);
    }
  };

  const getYoutubeEmbedUrl = (url: string) => {
    let videoId = "";
    if (url.includes("v=")) videoId = url.split("v=")[1].split("&")[0];
    else if (url.includes("youtu.be/")) videoId = url.split("youtu.be/")[1].split("?")[0];
    return videoId ? `https://www.youtube.com/embed/${videoId}` : null;
  };

  if (loading) return <div className="flex h-screen items-center justify-center"><Loader2 className="animate-spin h-8 w-8 text-primary" /></div>;
  if (!clipper) return <div className="text-center py-20"><p>Clipper tidak ditemukan.</p><Link href="/dashboard/marketplace"><Button variant="ghost">Kembali ke Marketplace</Button></Link></div>;

  const ratingLabel =
    typeof clipper.rating_avg === "number"
      ? `${clipper.rating_avg.toFixed(1)} • ${clipper.rating_count || 0}`
      : "New";

  return (
    <div className="max-w-6xl mx-auto space-y-8 pb-20">
      <button onClick={() => router.back()} className="flex items-center gap-2 text-gray-500 hover:text-primary transition-colors mb-4">
        <ArrowLeft className="h-4 w-4" /> Kembali
      </button>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Profile Sidebar */}
        <div className="lg:col-span-1 space-y-6">
          <div className="bg-white rounded-2xl border p-8 shadow-sm text-center">
            <div className="h-32 w-32 rounded-full bg-primary/10 flex items-center justify-center text-primary text-4xl font-bold border-4 border-white shadow-md mx-auto mb-6">
              {clipper.full_name.charAt(0)}
            </div>
            <h1 className="text-2xl font-bold text-gray-900">{clipper.full_name}</h1>
            <div className="flex items-center justify-center gap-1 text-orange-400 mt-2 mb-6">
              {[...Array(5)].map((_, i) => (
                <Star
                  key={i}
                  className={`h-4 w-4 ${typeof clipper.rating_avg === "number" && i < Math.round(clipper.rating_avg) ? "fill-current" : ""}`}
                />
              ))}
              <span className="text-sm text-gray-500 ml-1">({ratingLabel})</span>
            </div>

            <div className="flex justify-center gap-4 mb-8">
              {clipper.portfolio?.social_links?.youtube && (
                <a
                  href={clipper.portfolio.social_links.youtube}
                  target="_blank"
                  rel="noopener noreferrer"
                  title="YouTube"
                  className="p-3 rounded-full bg-gray-50 hover:bg-gray-100 text-gray-400 hover:text-primary transition-all"
                >
                  <ExternalLink className="h-5 w-5" />
                </a>
              )}
              {clipper.portfolio?.social_links?.instagram && (
                <a
                  href={clipper.portfolio.social_links.instagram}
                  target="_blank"
                  rel="noopener noreferrer"
                  title="Instagram"
                  className="p-3 rounded-full bg-gray-50 hover:bg-gray-100 text-gray-400 hover:text-primary transition-all"
                >
                  <ExternalLink className="h-5 w-5" />
                </a>
              )}
              {clipper.portfolio?.social_links?.twitter && (
                <a
                  href={clipper.portfolio.social_links.twitter}
                  target="_blank"
                  rel="noopener noreferrer"
                  title="Twitter"
                  className="p-3 rounded-full bg-gray-50 hover:bg-gray-100 text-gray-400 hover:text-primary transition-all"
                >
                  <ExternalLink className="h-5 w-5" />
                </a>
              )}
              {!clipper.portfolio?.social_links && (
                <div className="p-3 rounded-full bg-gray-50 text-gray-400">
                  <Globe className="h-5 w-5" />
                </div>
              )}
            </div>

            {user?.role === "OWNER" && (
              <div className="space-y-3">
                <Button className="w-full rounded-xl py-6 text-lg font-bold shadow-lg shadow-primary/20">
                  <MessageSquare className="h-5 w-5 mr-2" /> Hubungi Clipper
                </Button>
                <p className="text-[10px] text-gray-400 uppercase tracking-widest font-bold">Invite ke Lowongan (OPEN)</p>
                {activeJobs.length > 0 ? (
                  <div className="space-y-3">
                    <label className="flex items-center justify-between gap-3 rounded-xl border bg-gray-50 px-3 py-2 text-xs text-gray-700">
                      <span className="font-medium">Show PENDING jobs</span>
                      <input
                        type="checkbox"
                        checked={showPendingJobs}
                        onChange={(e) => {
                          setShowPendingJobs(e.target.checked);
                          setInviteError("");
                          if (!e.target.checked) {
                            const firstEligible = eligibleJobs[0];
                            if (firstEligible) setSelectedJobId(firstEligible.id);
                          } else if (!selectedJobId && activeJobs.length > 0) {
                            setSelectedJobId(activeJobs[0].id);
                          }
                        }}
                      />
                    </label>
                    <select
                      className="w-full rounded-xl border-gray-300 text-sm focus:ring-primary focus:border-primary"
                      value={selectedJobId}
                      onChange={(e) => {
                        setSelectedJobId(e.target.value);
                        setInviteError("");
                      }}
                    >
                      {visibleJobs.map((job) => (
                        <option key={job.id} value={job.id}>
                          {job.title} • {job.payment_status || "PENDING"}
                        </option>
                      ))}
                    </select>
                    {!showPendingJobs && eligibleJobs.length === 0 && (
                      <p className="text-xs text-gray-500">
                        Tidak ada job yang siap di-invite. Aktifkan toggle untuk menampilkan job PENDING lalu deposit escrow.
                      </p>
                    )}
                    {inviteError && <p className="text-xs text-red-600">{inviteError}</p>}
                    {selectedJobId && selectedPaymentStatus !== "ESCROW_HOLD" && (
                      <Button
                        onClick={handleDepositEscrow}
                        disabled={depositing}
                        variant="outline"
                        className="w-full rounded-xl justify-center"
                      >
                        {depositing ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Briefcase className="h-4 w-4 mr-2" />}
                        Deposit ke Escrow
                      </Button>
                    )}
                    <Button
                      onClick={handleInvite}
                      disabled={inviting || !selectedJobId || !canInvite}
                      className="w-full rounded-xl justify-center"
                    >
                      {inviting ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Briefcase className="h-4 w-4 mr-2" />}
                      Invite Clipper
                    </Button>
                    <p className="text-[10px] text-gray-400">
                      Syarat: job harus sudah Deposit ke Escrow (ESCROW_HOLD).
                    </p>
                  </div>
                ) : (
                  <p className="text-xs text-gray-400 italic">Kamu tidak memiliki lowongan aktif.</p>
                )}
              </div>
            )}
          </div>

          <div className="bg-white rounded-2xl border p-8 shadow-sm">
            <h3 className="text-lg font-bold text-gray-900 mb-4">Statistik</h3>
            <div className="space-y-4">
              <div className="flex justify-between items-center text-sm">
                <span className="text-gray-500">Pekerjaan Selesai</span>
                <span className="font-bold text-gray-900">24</span>
              </div>
              <div className="flex justify-between items-center text-sm">
                <span className="text-gray-500">Respons Rate</span>
                <span className="font-bold text-gray-900">98%</span>
              </div>
              <div className="flex justify-between items-center text-sm">
                <span className="text-gray-500">Member Sejak</span>
                <span className="font-bold text-gray-900">Maret 2024</span>
              </div>
            </div>
          </div>
        </div>

        {/* Portfolio Content */}
        <div className="lg:col-span-2 space-y-8">
          <div className="bg-white rounded-2xl border p-8 shadow-sm">
            <h2 className="text-xl font-bold text-gray-900 mb-4 flex items-center gap-2">
              <Globe className="h-5 w-5 text-primary" /> Tentang Clipper
            </h2>
            <p className="text-gray-600 leading-relaxed italic">
              "{clipper.portfolio?.bio || "Clipper ini belum mengisi biografi profesional mereka."}"
            </p>
          </div>

          <div className="bg-white rounded-2xl border p-8 shadow-sm">
            <h2 className="text-xl font-bold text-gray-900 mb-6 flex items-center gap-2">
              <PlayCircle className="h-5 w-5 text-primary" /> Portofolio Video
            </h2>
            
            {clipper.portfolio?.video_samples && clipper.portfolio.video_samples.length > 0 ? (
              <div className="grid grid-cols-1 gap-6">
                {clipper.portfolio.video_samples.map((url, idx) => {
                  const embedUrl = getYoutubeEmbedUrl(url);
                  return (
                    <div key={idx} className="space-y-3">
                      <div className="aspect-video bg-black rounded-2xl overflow-hidden shadow-lg border border-gray-100">
                        {embedUrl ? (
                          <iframe 
                            src={embedUrl}
                            className="w-full h-full"
                            allowFullScreen
                            title={`Portfolio Video ${idx + 1}`}
                          />
                        ) : (
                          <div className="w-full h-full flex flex-col items-center justify-center text-gray-500 gap-2">
                            <Video className="h-10 w-10 opacity-20" />
                            <p className="text-xs">Video format tidak didukung</p>
                          </div>
                        )}
                      </div>
                      <div className="flex items-center justify-between px-2">
                        <span className="text-sm font-medium text-gray-700">Sample Project #{idx + 1}</span>
                        <a href={url} target="_blank" className="text-primary text-xs font-bold hover:underline flex items-center gap-1">
                          Buka di YouTube <ExternalLink className="h-3 w-3" />
                        </a>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="text-center py-12 border-2 border-dashed rounded-2xl bg-gray-50">
                <Video className="h-12 w-12 text-gray-300 mx-auto mb-4" />
                <p className="text-gray-400 text-sm">Belum ada video portofolio yang ditampilkan.</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
