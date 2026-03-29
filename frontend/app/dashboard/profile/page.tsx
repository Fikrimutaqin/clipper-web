"use client";

import { useState, useEffect } from "react";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Loader2, Save, Instagram, Twitter, Video, Plus, X } from "lucide-react";
import api from "@/lib/axios";

export default function ProfilePage() {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [bio, setBio] = useState("");
  const [socialLinks, setSocialLinks] = useState({ instagram: "", twitter: "", tiktok: "" });
  const [videoSamples, setVideoSamples] = useState<string[]>([]);
  const [newVideoUrl, setNewVideoUrl] = useState("");

  useEffect(() => {
    const fetchPortfolio = async () => {
      try {
        const res = await api.get("/api/marketplace/clippers");
        const myData = res.data.data.find((c: any) => c.id === user?.id);
        if (myData && myData.portfolio) {
          setBio(myData.portfolio.bio || "");
          setSocialLinks(myData.portfolio.social_links || { instagram: "", twitter: "", tiktok: "" });
          setVideoSamples(myData.portfolio.video_samples || []);
        }
      } catch (err) {
        console.error("Failed to fetch portfolio", err);
      } finally {
        setLoading(false);
      }
    };
    if (user?.role === "CLIPPER") fetchPortfolio();
    else setLoading(false);
  }, [user]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.post("/api/marketplace/portfolio", {
        bio,
        social_links: socialLinks,
        video_samples: videoSamples,
      });
      alert("Profil & Portofolio berhasil diperbarui!");
    } catch (err) {
      alert("Gagal memperbarui profil.");
    } finally {
      setSaving(false);
    }
  };

  const addVideo = () => {
    if (newVideoUrl) {
      setVideoSamples([...videoSamples, newVideoUrl]);
      setNewVideoUrl("");
    }
  };

  const removeVideo = (index: number) => {
    setVideoSamples(videoSamples.filter((_, i) => i !== index));
  };

  if (loading) return <div className="flex h-64 items-center justify-center"><Loader2 className="animate-spin" /></div>;

  return (
    <div className="max-w-4xl mx-auto space-y-8">
      <div className="bg-white rounded-2xl border p-8 shadow-sm">
        <h2 className="text-xl font-bold text-gray-900 mb-6">Informasi Dasar</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-2">
            <Label>Nama Lengkap</Label>
            <Input value={user?.full_name} disabled className="bg-gray-50" />
          </div>
          <div className="space-y-2">
            <Label>Email</Label>
            <Input value={user?.email} disabled className="bg-gray-50" />
          </div>
        </div>
      </div>

      {user?.role === "CLIPPER" && (
        <>
          <div className="bg-white rounded-2xl border p-8 shadow-sm">
            <h2 className="text-xl font-bold text-gray-900 mb-6">Portofolio Clipper</h2>
            <div className="space-y-6">
              <div className="space-y-2">
                <Label htmlFor="bio">Bio Profesional</Label>
                <textarea
                  id="bio"
                  className="flex min-h-[100px] w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                  placeholder="Ceritakan pengalamanmu sebagai editor video..."
                  value={bio}
                  onChange={(e) => setBio(e.target.value)}
                />
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="space-y-2">
                  <Label className="flex items-center gap-2"><Instagram className="h-4 w-4" /> Instagram</Label>
                  <Input 
                    placeholder="@username" 
                    value={socialLinks.instagram}
                    onChange={(e) => setSocialLinks({...socialLinks, instagram: e.target.value})}
                  />
                </div>
                <div className="space-y-2">
                  <Label className="flex items-center gap-2"><Twitter className="h-4 w-4" /> Twitter</Label>
                  <Input 
                    placeholder="@username" 
                    value={socialLinks.twitter}
                    onChange={(e) => setSocialLinks({...socialLinks, twitter: e.target.value})}
                  />
                </div>
                <div className="space-y-2">
                  <Label className="flex items-center gap-2"><Video className="h-4 w-4" /> TikTok</Label>
                  <Input 
                    placeholder="@username" 
                    value={socialLinks.tiktok}
                    onChange={(e) => setSocialLinks({...socialLinks, tiktok: e.target.value})}
                  />
                </div>
              </div>
            </div>
          </div>

          <div className="bg-white rounded-2xl border p-8 shadow-sm">
            <h2 className="text-xl font-bold text-gray-900 mb-6">Video Samples (Portofolio)</h2>
            <div className="flex gap-2 mb-6">
              <Input 
                placeholder="Paste URL video YouTube hasil kerjamu..." 
                value={newVideoUrl}
                onChange={(e) => setNewVideoUrl(e.target.value)}
              />
              <Button onClick={addVideo} type="button" variant="outline">
                <Plus className="h-4 w-4 mr-2" /> Add
              </Button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {videoSamples.map((url, idx) => (
                <div key={idx} className="flex items-center justify-between p-3 border rounded-lg bg-gray-50">
                  <span className="text-xs truncate max-w-[200px]">{url}</span>
                  <button onClick={() => removeVideo(idx)} className="text-red-500 hover:bg-red-50 p-1 rounded">
                    <X className="h-4 w-4" />
                  </button>
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      <div className="flex justify-end">
        <Button onClick={handleSave} disabled={saving} size="lg" className="rounded-full px-8">
          {saving ? <Loader2 className="animate-spin mr-2" /> : <Save className="mr-2 h-4 w-4" />}
          Simpan Perubahan
        </Button>
      </div>
    </div>
  );
}
