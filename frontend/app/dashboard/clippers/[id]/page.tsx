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

  useEffect(() => {
    const fetchData = async () => {
      try {
        const res = await api.get("/api/marketplace/clippers");
        const found = res.data.data.find((c: any) => c.id === id);
        setClipper(found);

        if (user?.role === "OWNER") {
          const jobsRes = await api.get("/api/jobs/my-jobs");
          setActiveJobs(jobsRes.data.data.filter((j: any) => j.status === "OPEN"));
        }
      } catch (err) {
        console.error("Failed to fetch clipper detail", err);
      } finally {
        setLoading(false);
      }
    };
    if (id) fetchData();
  }, [id, user]);

  const getYoutubeEmbedUrl = (url: string) => {
    let videoId = "";
    if (url.includes("v=")) videoId = url.split("v=")[1].split("&")[0];
    else if (url.includes("youtu.be/")) videoId = url.split("youtu.be/")[1].split("?")[0];
    return videoId ? `https://www.youtube.com/embed/${videoId}` : null;
  };

  if (loading) return <div className="flex h-screen items-center justify-center"><Loader2 className="animate-spin h-8 w-8 text-primary" /></div>;
  if (!clipper) return <div className="text-center py-20"><p>Clipper tidak ditemukan.</p><Link href="/dashboard/marketplace"><Button variant="ghost">Kembali ke Marketplace</Button></Link></div>;

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
              {[...Array(5)].map((_, i) => <Star key={i} className="h-4 w-4 fill-current" />)}
              <span className="text-sm text-gray-500 ml-1">(5.0)</span>
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
                <p className="text-[10px] text-gray-400 uppercase tracking-widest font-bold">Atau Pilih Lowongan Aktif</p>
                {activeJobs.length > 0 ? (
                  <div className="space-y-2">
                    {activeJobs.map(job => (
                      <Button key={job.id} variant="outline" className="w-full rounded-xl text-xs justify-between group hover:border-primary transition-all">
                        {job.title} <Briefcase className="h-3 w-3 text-gray-300 group-hover:text-primary" />
                      </Button>
                    ))}
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
