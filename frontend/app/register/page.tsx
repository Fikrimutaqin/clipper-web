"use client";

import Link from "next/link";
import { Scissors, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useState } from "react";
import api from "@/lib/axios";
import { useAuth } from "@/context/AuthContext";

export default function RegisterPage() {
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("OWNER");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const { login } = useAuth();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      const res = await api.post("/api/auth/register", {
        full_name: fullName,
        email,
        password,
        role,
      });

      await login(res.data.data.access_token);
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      if (Array.isArray(detail)) {
        setError(detail[0]?.msg || "Pendaftaran gagal. Periksa kembali data kamu.");
      } else {
        setError(detail || "Pendaftaran gagal. Silakan coba lagi.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-gray-50 px-4">
      <div className="w-full max-w-md space-y-8 rounded-2xl bg-white p-8 shadow-xl">
        <div className="flex flex-col items-center text-center">
          <Link href="/" className="flex items-center gap-2 text-3xl font-bold text-primary">
            <Scissors className="h-8 w-8" />
            <span>ClipFIX</span>
          </Link>
          <h2 className="mt-6 text-2xl font-bold tracking-tight text-gray-900">
            Daftar Akun Baru
          </h2>
          <p className="mt-2 text-sm text-gray-600">
            Sudah punya akun?{" "}
            <Link href="/login" className="font-medium text-primary hover:text-primary-hover">
              Masuk di sini
            </Link>
          </p>
        </div>

        {error && (
          <div className="bg-red-50 text-red-600 p-3 rounded-lg text-sm text-center">
            {error}
          </div>
        )}

        <form className="mt-8 space-y-6" onSubmit={handleSubmit}>
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="fullName">Nama Lengkap</Label>
              <Input 
                id="fullName" 
                placeholder="John Doe" 
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                required 
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="email">Email</Label>
              <Input 
                id="email" 
                type="email" 
                placeholder="name@example.com" 
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required 
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="role">Daftar Sebagai</Label>
              <select 
                id="role" 
                value={role}
                onChange={(e) => setRole(e.target.value)}
                className="flex h-10 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
              >
                <option value="OWNER">Business Owner (Butuh Jasa Clip)</option>
                <option value="CLIPPER">Professional Clipper (Penyedia Jasa)</option>
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">Password (Minimal 8 Karakter)</Label>
              <Input 
                id="password" 
                type="password" 
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required 
                minLength={8}
                maxLength={64}
              />
            </div>
          </div>

          <Button 
            className="w-full rounded-lg py-6 text-lg" 
            type="submit"
            disabled={loading}
          >
            {loading ? <Loader2 className="h-5 w-5 animate-spin" /> : "Buat Akun"}
          </Button>
        </form>

        <p className="text-center text-xs text-gray-500">
          Dengan mendaftar, kamu menyetujui <Link href="#" className="underline">Terms of Service</Link> dan <Link href="#" className="underline">Privacy Policy</Link> kami.
        </p>
      </div>
    </div>
  );
}
