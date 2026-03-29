"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import api from "@/lib/axios";
import { 
  Loader2, 
  ArrowLeft, 
  Briefcase, 
  Wallet, 
  ExternalLink, 
  Send, 
  CheckCircle2, 
  XCircle,
  Clock,
  MessageSquare
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import Link from "next/link";

interface Job {
  id: string;
  title: string;
  description: string;
  budget: number;
  status: string;
  owner_id: string;
  clipper_id?: string;
  source_url?: string;
  result_url?: string;
  owner_notes?: string;
  payment_status: string;
}

export default function JobDetailPage() {
  const { id } = useParams();
  const router = useRouter();
  const { user } = useAuth();
  const [job, setJob] = useState<Job | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  
  // Form states
  const [resultUrl, setResultUrl] = useState("");
  const [reviewNotes, setReviewNotes] = useState("");

  const fetchJob = async () => {
    try {
      const res = await api.get(`/api/marketplace/jobs/${id}`);
      setJob(res.data.data);
    } catch (err) {
      console.error("Failed to fetch job", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchJob();
  }, [id]);

  const handleSubmitResult = async () => {
    if (!resultUrl) return alert("Masukkan link hasil pekerjaan!");
    setActionLoading(true);
    try {
      await api.post(`/api/marketplace/jobs/${id}/submit`, { result_url: resultUrl });
      alert("Hasil pekerjaan berhasil dikirim!");
      fetchJob();
    } catch (err) {
      alert("Gagal mengirim hasil.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleReview = async (approve: boolean) => {
    setActionLoading(true);
    try {
      await api.post(`/api/marketplace/jobs/${id}/review`, { approve, notes: reviewNotes });
      alert(approve ? "Pekerjaan disetujui!" : "Revisi diminta.");
      fetchJob();
    } catch (err) {
      alert("Gagal memproses review.");
    } finally {
      setActionLoading(false);
    }
  };

  const handlePayToEscrow = async () => {
    setActionLoading(true);
    try {
      await api.post(`/api/marketplace/jobs/${id}/pay`);
      alert("Dana berhasil dititipkan di Escrow (ClipFIX)!");
      fetchJob();
    } catch (err) {
      alert("Gagal melakukan pembayaran.");
    } finally {
      setActionLoading(false);
    }
  };

  if (loading) return <div className="flex h-screen items-center justify-center"><Loader2 className="animate-spin" /></div>;
  if (!job) return <div className="p-8 text-center">Pekerjaan tidak ditemukan.</div>;

  const isOwner = user?.id === job.owner_id;
  const isClipper = user?.id === job.clipper_id;

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      <div className="mb-6">
        <Link href="/dashboard/my-jobs" className="inline-flex items-center text-sm text-gray-500 hover:text-primary">
          <ArrowLeft className="mr-2 h-4 w-4" /> Kembali ke Pekerjaan Saya
        </Link>
      </div>

      <div className="bg-white rounded-2xl border p-8 shadow-sm">
        <div className="flex justify-between items-start mb-6">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <span className={`px-3 py-1 rounded-full text-xs font-bold ${
                job.status === 'OPEN' ? 'bg-blue-50 text-blue-600' :
                job.status === 'IN_PROGRESS' ? 'bg-orange-50 text-orange-600' :
                job.status === 'REVIEW' ? 'bg-purple-50 text-purple-600' :
                'bg-green-50 text-green-600'
              }`}>
                {job.status}
              </span>
              <h1 className="text-2xl font-bold text-gray-900">{job.title}</h1>
            </div>
            <p className="text-gray-600">{job.description}</p>
          </div>
          <div className="text-right">
            <div className="text-primary font-bold text-xl">
              Rp {job.budget.toLocaleString("id-ID")}
            </div>
            <div className={`text-[10px] font-bold uppercase tracking-wider mt-1 ${
              job.payment_status === 'PENDING' ? 'text-gray-400' :
              job.payment_status === 'ESCROW_HOLD' ? 'text-orange-500' :
              job.payment_status === 'RELEASED' ? 'text-green-500' :
              'text-red-500'
            }`}>
              Payment: {job.payment_status.replace('_', ' ')}
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-4">
          {job.source_url && (
            <div className="p-4 rounded-xl bg-gray-50 border flex items-center justify-between">
              <div className="flex items-center gap-3">
                <ExternalLink className="h-5 w-5 text-gray-400" />
                <span className="text-sm font-medium">Video Sumber</span>
              </div>
              <a href={job.source_url} target="_blank" className="text-primary text-sm font-bold hover:underline">
                Buka di YouTube
              </a>
            </div>
          )}

          {isOwner && job.payment_status === 'PENDING' && (
            <div className="p-4 rounded-xl bg-orange-50 border border-orange-100 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Wallet className="h-5 w-5 text-orange-500" />
                <div className="text-sm">
                  <span className="font-bold text-orange-800">Dana belum dititipkan.</span>
                  <p className="text-orange-600 text-xs">Clipper baru bisa mulai bekerja setelah dana masuk ke Escrow.</p>
                </div>
              </div>
              <Button size="sm" onClick={handlePayToEscrow} disabled={actionLoading} className="bg-orange-500 hover:bg-orange-600 rounded-full px-6">
                Deposit ke Escrow
              </Button>
            </div>
          )}
        </div>
      </div>

      {/* Clipper Workspace: Submit Result */}
      {isClipper && job.status === "IN_PROGRESS" && (
        <div className="bg-white rounded-2xl border p-8 shadow-sm space-y-6">
          <h2 className="text-xl font-bold text-gray-900">Submit Hasil Pekerjaan</h2>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="resultUrl">Link Video Hasil (Google Drive / YouTube)</Label>
              <Input 
                id="resultUrl" 
                placeholder="https://..." 
                value={resultUrl}
                onChange={(e) => setResultUrl(e.target.value)}
              />
            </div>
            <Button onClick={handleSubmitResult} disabled={actionLoading} className="w-full rounded-full">
              {actionLoading ? <Loader2 className="animate-spin mr-2" /> : <Send className="mr-2 h-4 w-4" />}
              Kirim untuk Review
            </Button>
          </div>
        </div>
      )}

      {/* Owner Workspace: Review Result */}
      {isOwner && job.status === "REVIEW" && (
        <div className="bg-white rounded-2xl border p-8 shadow-sm space-y-6">
          <h2 className="text-xl font-bold text-gray-900">Review Hasil Pekerjaan</h2>
          <div className="p-4 rounded-xl bg-purple-50 border border-purple-100 flex items-center justify-between mb-6">
            <span className="text-sm font-medium">Link Hasil: <a href={job.result_url} target="_blank" className="text-primary underline">{job.result_url}</a></span>
          </div>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="notes">Catatan / Revisi (Opsional)</Label>
              <textarea
                id="notes"
                className="w-full p-3 rounded-lg border focus:ring-2 focus:ring-primary outline-none"
                placeholder="Berikan masukan jika butuh revisi..."
                value={reviewNotes}
                onChange={(e) => setReviewNotes(e.target.value)}
              />
            </div>
            <div className="flex gap-4">
              <Button onClick={() => handleReview(true)} disabled={actionLoading} className="flex-1 rounded-full bg-green-600 hover:bg-green-700">
                <CheckCircle2 className="mr-2 h-4 w-4" /> Setujui & Selesaikan
              </Button>
              <Button onClick={() => handleReview(false)} disabled={actionLoading} variant="outline" className="flex-1 rounded-full border-red-200 text-red-600 hover:bg-red-50">
                <XCircle className="mr-2 h-4 w-4" /> Minta Revisi
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Result Display for other states */}
      {job.result_url && (job.status === "COMPLETED" || (isClipper && job.status === "REVIEW")) && (
        <div className="bg-white rounded-2xl border p-8 shadow-sm">
          <h2 className="text-xl font-bold text-gray-900 mb-4">Hasil Pekerjaan</h2>
          <div className="flex items-center gap-3 p-4 bg-green-50 text-green-700 rounded-lg">
            <ExternalLink className="h-5 w-5" />
            <a href={job.result_url} target="_blank" className="font-bold underline">{job.result_url}</a>
          </div>
        </div>
      )}

      {/* Owner Notes / Feedback Display */}
      {job.owner_notes && (
        <div className="bg-white rounded-2xl border p-8 shadow-sm">
          <h2 className="text-xl font-bold text-gray-900 mb-4 flex items-center gap-2">
            <MessageSquare className="h-5 w-5 text-orange-500" /> Catatan dari Owner
          </h2>
          <div className="p-4 bg-orange-50 border border-orange-100 text-orange-800 rounded-lg italic">
            "{job.owner_notes}"
          </div>
        </div>
      )}
    </div>
  );
}
