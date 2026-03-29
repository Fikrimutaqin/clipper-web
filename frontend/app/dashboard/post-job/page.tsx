"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Loader2, ArrowLeft, Send } from "lucide-react";
import Link from "next/link";
import api from "@/lib/axios";

export default function PostJobPage() {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [budget, setBudget] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const router = useRouter();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      await api.post("/api/marketplace/jobs", {
        title,
        description,
        budget: parseFloat(budget),
        source_url: sourceUrl,
      });
      router.push("/dashboard");
    } catch (err: any) {
      setError(err.response?.data?.detail || "Gagal memposting pekerjaan.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="max-w-2xl mx-auto">
      <div className="mb-6">
        <Link 
          href="/dashboard" 
          className="inline-flex items-center text-sm text-gray-500 hover:text-primary transition-colors"
        >
          <ArrowLeft className="mr-2 h-4 w-4" /> Kembali ke Dashboard
        </Link>
      </div>

      <div className="bg-white rounded-2xl border p-8 shadow-sm">
        <div className="mb-8">
          <h1 className="text-2xl font-bold text-gray-900">Post New Job</h1>
          <p className="text-sm text-gray-500">
            Berikan detail pekerjaan video clipping kamu untuk ditemukan oleh para Clipper profesional.
          </p>
        </div>

        {error && (
          <div className="mb-6 bg-red-50 text-red-600 p-3 rounded-lg text-sm text-center">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="space-y-2">
            <Label htmlFor="title">Judul Pekerjaan</Label>
            <Input 
              id="title" 
              placeholder="Contoh: Butuh 10 Short Clips dari Podcast X" 
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required 
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="description">Deskripsi Detail</Label>
            <textarea
              id="description"
              className="flex min-h-[120px] w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
              placeholder="Jelaskan kriteria video yang kamu inginkan..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              required
            />
          </div>

          <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="budget">Budget (Rp)</Label>
              <Input 
                id="budget" 
                type="number" 
                placeholder="Contoh: 500000" 
                value={budget}
                onChange={(e) => setBudget(e.target.value)}
                required 
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="sourceUrl">Link Video Sumber (Opsional)</Label>
              <Input 
                id="sourceUrl" 
                placeholder="https://youtube.com/..." 
                value={sourceUrl}
                onChange={(e) => setSourceUrl(e.target.value)}
              />
            </div>
          </div>

          <Button 
            className="w-full rounded-lg py-6 text-lg" 
            type="submit"
            disabled={loading}
          >
            {loading ? (
              <Loader2 className="h-5 w-5 animate-spin" />
            ) : (
              <>
                Posting Lowongan <Send className="ml-2 h-4 w-4" />
              </>
            )}
          </Button>
        </form>
      </div>
    </div>
  );
}
