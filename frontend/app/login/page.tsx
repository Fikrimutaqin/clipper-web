"use client";

import Link from "next/link";
import { Scissors, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useEffect, useState } from "react";
import api from "@/lib/axios";
import { useAuth } from "@/context/AuthContext";
import { useSearchParams } from "next/navigation";

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const { login } = useAuth();
  const searchParams = useSearchParams();
  const apiBase = (api.defaults.baseURL || "").toString().replace(/\/$/, "");

  useEffect(() => {
    const token = searchParams.get("token");
    if (!token) return;
    window.history.replaceState({}, "", "/login");
    login(token).catch(() => {
      setError("Login Google gagal. Silakan coba lagi.");
    });
  }, [searchParams, login]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError("");

    try {
      const formData = new FormData();
      formData.append("username", email);
      formData.append("password", password);

      const res = await api.post("/api/auth/login", formData, {
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
      });

      await login(res.data.data.access_token);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Login gagal. Periksa email/password.");
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleLogin = () => {
    const redirectUrl = `${window.location.origin}/login`;
    window.location.href = `${apiBase}/api/auth/google/connect?redirect=${encodeURIComponent(redirectUrl)}`;
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
            Masuk ke Akun Kamu
          </h2>
          <p className="mt-2 text-sm text-gray-600">
            Belum punya akun?{" "}
            <Link href="/register" className="font-medium text-primary hover:text-primary-hover">
              Daftar sekarang
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
              <div className="flex items-center justify-between">
                <Label htmlFor="password">Password</Label>
                <Link href="#" className="text-xs text-primary hover:underline">
                  Lupa password?
                </Link>
              </div>
              <Input 
                id="password" 
                type="password" 
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required 
              />
            </div>
          </div>

          <Button 
            className="w-full rounded-lg py-6 text-lg" 
            type="submit"
            disabled={loading}
          >
            {loading ? <Loader2 className="h-5 w-5 animate-spin" /> : "Sign In"}
          </Button>
        </form>

        <div className="relative">
          <div className="absolute inset-0 flex items-center">
            <span className="w-full border-t" />
          </div>
          <div className="relative flex justify-center text-xs uppercase">
            <span className="bg-white px-2 text-gray-500">Or continue with</span>
          </div>
        </div>

        <Button variant="outline" className="w-full rounded-lg py-6" type="button" onClick={handleGoogleLogin}>
          <svg className="mr-2 h-4 w-4" aria-hidden="true" focusable="false" data-prefix="fab" data-icon="google" role="img" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 488 512">
            <path fill="currentColor" d="M488 261.8C488 403.3 391.1 504 248 504 110.8 504 0 393.2 0 256S110.8 8 248 8c66.8 0 123 24.5 166.3 64.9l-67.5 64.9C258.5 52.6 94.3 116.6 94.3 256c0 86.5 69.1 156.6 153.7 156.6 98.2 0 135-70.4 140.8-106.9H248v-85.3h236.1c2.3 12.7 3.9 24.9 3.9 41.4z"></path>
          </svg>
          Google
        </Button>
      </div>
    </div>
  );
}
