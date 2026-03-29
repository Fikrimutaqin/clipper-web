"use client";

import { createContext, useContext, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/axios";

interface User {
  id: string;
  email: string;
  full_name: string;
  role: "OWNER" | "CLIPPER" | "ADMIN";
}

interface AuthContextType {
  user: User | null;
  loading: boolean;
  login: (token: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    const fetchUser = async () => {
      const token = localStorage.getItem("token");
      if (token) {
        try {
          const res = await api.get("/api/auth/me");
          setUser(res.data.data);
        } catch (err) {
          localStorage.removeItem("token");
          setUser(null);
        }
      }
      setLoading(false);
    };
    fetchUser();
  }, []);

  const login = async (token: string) => {
    localStorage.setItem("token", token);
    try {
      const res = await api.get("/api/auth/me");
      setUser(res.data.data);
      router.push("/dashboard");
    } catch (err) {
      localStorage.removeItem("token");
      setUser(null);
      throw err;
    }
  };

  const logout = () => {
    localStorage.removeItem("token");
    setUser(null);
    router.push("/login");
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
