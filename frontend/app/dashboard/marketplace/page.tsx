"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { 
  ShoppingBag, 
  Loader2, 
  Briefcase, 
  Wallet, 
  ExternalLink,
  CheckCircle2,
  Users,
  Star,
  MessageSquare,
  Globe,
  Instagram,
  Youtube,
  Twitter
} from "lucide-react";
import api from "@/lib/axios";
import { useAuth } from "@/context/AuthContext";
import Link from "next/link";

interface Job {
  id: string;
  title: string;
  description: string;
  budget: number;
  status: string;
  owner_id: string;
  created_at: number;
  source_url?: string;
}

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

export default function MarketplacePage() {
  const [activeTab, setActiveTab] = useState<"jobs" | "clippers">("jobs");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [clippers, setClippers] = useState<Clipper[]>([]);
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState<string | null>(null);
  const { user } = useAuth();

  const fetchJobs = async () => {
    try {
      const res = await api.get("/api/marketplace/jobs");
      setJobs(res.data.data);
    } catch (err) {
      console.error("Failed to fetch jobs", err);
    }
  };

  const fetchClippers = async () => {
    try {
      const res = await api.get("/api/marketplace/clippers");
      setClippers(res.data.data);
    } catch (err) {
      console.error("Failed to fetch clippers", err);
    }
  };

  useEffect(() => {
    const init = async () => {
      setLoading(true);
      await Promise.all([fetchJobs(), fetchClippers()]);
      setLoading(false);
    };
    init();
  }, []);

  const handleApply = async (jobId: string) => {
    if (!confirm("Apakah kamu yakin ingin mengambil pekerjaan ini?")) return;
    
    setApplying(jobId);
    try {
      await api.post(`/api/marketplace/jobs/${jobId}/apply`);
      alert("Berhasil mengambil pekerjaan! Cek menu My Jobs.");
      fetchJobs(); // Refresh list
    } catch (err: any) {
      alert(err.response?.data?.detail || "Gagal mengambil pekerjaan.");
    } finally {
      setApplying(null);
    }
  };

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  const JobMarketplace = () => (
    <div className="space-y-6">
      {jobs.length === 0 ? (
        <div className="bg-white rounded-2xl border p-12 text-center shadow-sm">
          <div className="mx-auto w-16 h-16 bg-gray-50 rounded-full flex items-center justify-center mb-4">
            <Briefcase className="h-8 w-8 text-gray-400" />
          </div>
          <h3 className="text-lg font-semibold text-gray-900">Belum Ada Lowongan</h3>
          <p className="text-gray-500 mt-2">Cek kembali nanti untuk melihat pekerjaan baru.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {jobs.map((job) => (
            <div key={job.id} className="bg-white rounded-2xl border p-6 shadow-sm hover:shadow-md transition-shadow">
              <div className="flex justify-between items-start mb-4">
                <h3 className="text-lg font-bold text-gray-900">{job.title}</h3>
                <div className="flex items-center text-primary font-bold">
                  <Wallet className="h-4 w-4 mr-1" />
                  Rp {job.budget.toLocaleString("id-ID")}
                </div>
              </div>
              
              <p className="text-gray-600 text-sm mb-6 line-clamp-3">
                {job.description}
              </p>

              <div className="flex items-center gap-4 mt-auto">
                {user?.role === "CLIPPER" ? (
                  <Button 
                    className="flex-1 rounded-full" 
                    onClick={() => handleApply(job.id)}
                    disabled={applying === job.id}
                  >
                    {applying === job.id ? (
                      <Loader2 className="h-4 w-4 animate-spin mr-2" />
                    ) : (
                      <CheckCircle2 className="h-4 w-4 mr-2" />
                    )}
                    Ambil Pekerjaan
                  </Button>
                ) : (
                  <div className="flex-1 text-sm text-gray-400 italic">
                    Hanya Clipper yang bisa mengambil job ini
                  </div>
                )}
                
                {job.source_url && (
                  <a 
                    href={job.source_url} 
                    target="_blank" 
                    rel="noopener noreferrer"
                    className="p-2 rounded-full border hover:bg-gray-50 transition-colors"
                    title="Lihat Sumber Video"
                  >
                    <ExternalLink className="h-5 w-5 text-gray-500" />
                  </a>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  const ClipperMarketplace = () => (
    <div className="space-y-6">
      {clippers.length === 0 ? (
        <div className="bg-white rounded-2xl border p-12 text-center shadow-sm">
          <div className="mx-auto w-16 h-16 bg-gray-50 rounded-full flex items-center justify-center mb-4">
            <Users className="h-8 w-8 text-gray-400" />
          </div>
          <h3 className="text-lg font-semibold text-gray-900">Belum Ada Clipper</h3>
          <p className="text-gray-500 mt-2">Belum ada clipper yang mendaftar di marketplace.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {clippers.map((clipper) => (
            <div key={clipper.id} className="bg-white rounded-2xl border p-6 shadow-sm hover:shadow-md transition-all group">
              <div className="flex flex-col items-center text-center space-y-4">
                <div className="relative">
                  <div className="h-20 w-20 rounded-full bg-primary/10 flex items-center justify-center text-primary text-2xl font-bold border-4 border-white shadow-sm">
                    {clipper.full_name.charAt(0)}
                  </div>
                  <div className="absolute bottom-0 right-0 bg-green-500 h-5 w-5 rounded-full border-2 border-white" title="Online" />
                </div>
                
                <div>
                  <h3 className="text-lg font-bold text-gray-900 group-hover:text-primary transition-colors">{clipper.full_name}</h3>
                  <div className="flex items-center justify-center gap-1 text-orange-400 mt-1">
                    {[...Array(5)].map((_, i) => <Star key={i} className="h-3 w-3 fill-current" />)}
                    <span className="text-xs text-gray-500 ml-1">(5.0)</span>
                  </div>
                </div>

                <p className="text-sm text-gray-600 line-clamp-2 italic">
                  "{clipper.portfolio?.bio || "Professional Video Clipper ready to make your content viral."}"
                </p>

                <div className="flex gap-3 text-gray-400">
                  {clipper.portfolio?.social_links?.youtube && <Youtube className="h-4 w-4 hover:text-red-600 cursor-pointer" />}
                  {clipper.portfolio?.social_links?.instagram && <Instagram className="h-4 w-4 hover:text-pink-600 cursor-pointer" />}
                  {clipper.portfolio?.social_links?.twitter && <Twitter className="h-4 w-4 hover:text-blue-400 cursor-pointer" />}
                  {!clipper.portfolio?.social_links && <Globe className="h-4 w-4" />}
                </div>

                <div className="w-full pt-4 flex gap-2">
                  <Button variant="outline" size="sm" className="flex-1 rounded-full text-xs">
                    <MessageSquare className="h-3 w-3 mr-1" /> Chat
                  </Button>
                  <Link href={`/dashboard/clippers/${clipper.id}`} className="flex-1">
                    <Button size="sm" className="w-full rounded-full text-xs">
                      Lihat Profil
                    </Button>
                  </Link>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  return (
    <div className="space-y-8">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">ClipFIX Marketplace</h1>
          <p className="text-sm text-gray-500">
            Pusat kolaborasi antara Business Owner dan Professional Clipper.
          </p>
        </div>

        <div className="flex p-1 bg-gray-100 rounded-full self-start md:self-center">
          <button 
            onClick={() => setActiveTab("jobs")}
            className={`px-6 py-2 rounded-full text-sm font-bold transition-all ${
              activeTab === "jobs" ? "bg-white text-primary shadow-sm" : "text-gray-500 hover:text-gray-700"
            }`}
          >
            <div className="flex items-center gap-2">
              <Briefcase className="h-4 w-4" /> Job List
            </div>
          </button>
          <button 
            onClick={() => setActiveTab("clippers")}
            className={`px-6 py-2 rounded-full text-sm font-bold transition-all ${
              activeTab === "clippers" ? "bg-white text-primary shadow-sm" : "text-gray-500 hover:text-gray-700"
            }`}
          >
            <div className="flex items-center gap-2">
              <Users className="h-4 w-4" /> Browse Clippers
            </div>
          </button>
        </div>
      </div>

      <div className="mt-8">
        {activeTab === "jobs" ? <JobMarketplace /> : <ClipperMarketplace />}
      </div>
    </div>
  );
}
