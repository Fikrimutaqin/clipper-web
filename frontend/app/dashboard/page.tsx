"use client";

import { useAuth } from "@/context/AuthContext";
import {
  Video,
  PlusCircle,
  ShoppingBag,
  ArrowRight,
  TrendingUp,
  Clock,
  Wallet,
  CheckCircle2,
  AlertCircle,
  Briefcase,
  Users
} from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/axios";

export default function DashboardPage() {
  const router = useRouter();
  const { user } = useAuth();
  const [stats, setStats] = useState({
    totalClips: 0,
    activeJobs: 0,
    totalEarnings: 0,
    pendingPayments: 0,
    openJobs: 0
  });
  const [recentJobs, setRecentJobs] = useState<any[]>([]);
  const [notifications, setNotifications] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [markingAll, setMarkingAll] = useState(false);
  const [markingId, setMarkingId] = useState<number | null>(null);

  useEffect(() => {
    const fetchDashboardData = async () => {
      try {
        const [jobsRes, notifsRes] = await Promise.all([
          api.get("/api/jobs/my-jobs"),
          api.get("/api/marketplace/notifications"),
        ]);
        const jobs = jobsRes.data.data;
        setRecentJobs(jobs.slice(0, 3));
        setNotifications(notifsRes.data.data || []);

        if (user?.role === "OWNER") {
          setStats({
            totalClips: jobs.filter((j: any) => j.status === "COMPLETED").length,
            activeJobs: jobs.filter((j: any) => ["IN_PROGRESS", "REVIEW"].includes(j.status)).length,
            totalEarnings: 0, // Owners don't earn, they pay
            pendingPayments: jobs.filter((j: any) => j.payment_status === "ESCROW_HOLD").length,
            openJobs: jobs.filter((j: any) => j.status === "OPEN").length
          });
        } else {
          // Clipper Stats
          const completedJobs = jobs.filter((j: any) => j.status === "COMPLETED");
          const totalEarned = completedJobs.reduce((acc: number, curr: any) => acc + curr.budget, 0);
          const pending = jobs.filter((j: any) => j.payment_status === "ESCROW_HOLD").reduce((acc: number, curr: any) => acc + curr.budget, 0);

          setStats({
            totalClips: completedJobs.length,
            activeJobs: jobs.filter((j: any) => ["IN_PROGRESS", "REVIEW"].includes(j.status)).length,
            totalEarnings: totalEarned,
            pendingPayments: pending,
            openJobs: 0
          });
        }
      } catch (err) {
        console.error("Failed to fetch dashboard data", err);
      } finally {
        setLoading(false);
      }
    };

    if (user) fetchDashboardData();
  }, [user]);

  const markRead = async (id: number) => {
    setMarkingId(id);
    try {
      await api.post(`/api/marketplace/notifications/${id}/read`);
      const res = await api.get("/api/marketplace/notifications");
      setNotifications(res.data.data || []);
      window.dispatchEvent(new Event("clipfix:notifications-updated"));
    } finally {
      setMarkingId(null);
    }
  };

  const markAllRead = async () => {
    setMarkingAll(true);
    try {
      await api.post("/api/marketplace/notifications/read-all");
      const res = await api.get("/api/marketplace/notifications");
      setNotifications(res.data.data || []);
      window.dispatchEvent(new Event("clipfix:notifications-updated"));
    } finally {
      setMarkingAll(false);
    }
  };

  const openNotification = async (n: any) => {
    if (!n.read_at) {
      await markRead(n.id);
    }
    const jobId = n.meta?.job_id;
    if (jobId) {
      router.push(`/dashboard/jobs/${jobId}`);
      return;
    }
    const clipperId = n.meta?.clipper_id;
    if (clipperId) {
      router.push(`/dashboard/clippers/${clipperId}`);
      return;
    } else {
      router.push("/dashboard/notifications");
    }
  };

  const OwnerDashboard = () => (
    <div className="space-y-8">
      {/* Owner Stats */}
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-2xl border bg-white p-6 shadow-sm">
          <div className="flex items-center gap-4">
            <div className="rounded-full bg-blue-50 p-3 text-blue-600">
              <Video className="h-6 w-6" />
            </div>
            <div>
              <p className="text-sm font-medium text-gray-500">Clips Selesai</p>
              <h3 className="text-2xl font-bold text-gray-900">{stats.totalClips}</h3>
            </div>
          </div>
        </div>
        <div className="rounded-2xl border bg-white p-6 shadow-sm">
          <div className="flex items-center gap-4">
            <div className="rounded-full bg-orange-50 p-3 text-orange-600">
              <Clock className="h-6 w-6" />
            </div>
            <div>
              <p className="text-sm font-medium text-gray-500">Pekerjaan Aktif</p>
              <h3 className="text-2xl font-bold text-gray-900">{stats.activeJobs}</h3>
            </div>
          </div>
        </div>
        <div className="rounded-2xl border bg-white p-6 shadow-sm">
          <div className="flex items-center gap-4">
            <div className="rounded-full bg-green-50 p-3 text-green-600">
              <Briefcase className="h-6 w-6" />
            </div>
            <div>
              <p className="text-sm font-medium text-gray-500">Lowongan Buka</p>
              <h3 className="text-2xl font-bold text-gray-900">{stats.openJobs}</h3>
            </div>
          </div>
        </div>
        <div className="rounded-2xl border bg-white p-6 shadow-sm">
          <div className="flex items-center gap-4">
            <div className="rounded-full bg-purple-50 p-3 text-purple-600">
              <Wallet className="h-6 w-6" />
            </div>
            <div>
              <p className="text-sm font-medium text-gray-500">Dana di Escrow</p>
              <h3 className="text-2xl font-bold text-gray-900">{stats.pendingPayments}</h3>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
        <div className="rounded-2xl border bg-white p-8 shadow-sm">
          <h3 className="text-xl font-bold text-gray-900 flex items-center gap-2">
            <PlusCircle className="h-5 w-5 text-primary" /> Butuh Jasa Clip?
          </h3>
          <p className="mt-2 text-gray-600">
            Posting kebutuhan video clipping kamu dan biarkan para ahli yang mengerjakan.
          </p>
          <div className="mt-6">
            <Link href="/dashboard/post-job">
              <Button className="rounded-full px-6">
                Buat Lowongan Baru
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </Link>
          </div>
        </div>

        <div className="rounded-2xl border bg-white p-8 shadow-sm">
          <h3 className="text-xl font-bold text-gray-900 flex items-center gap-2">
            <Users className="h-5 w-5 text-primary" /> Browse Clippers
          </h3>
          <p className="mt-2 text-gray-600">
            Lihat daftar Clipper profesional dan portofolio mereka sebelum mempekerjakan.
          </p>
          <div className="mt-6">
            <Link href="/dashboard/marketplace">
              <Button variant="outline" className="rounded-full px-6">
                Lihat Semua Clipper
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </Link>
          </div>
        </div>
      </div>
    </div>
  );

  const ClipperDashboard = () => (
    <div className="space-y-8">
      {/* Clipper Stats */}
      {/* <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-2xl border bg-white p-6 shadow-sm">
          <div className="flex items-center gap-2">
            <div className="rounded-full bg-green-50 p-3 text-green-600">
              <Wallet className="h-6 w-6" />
            </div>
            <div className="flex flex-col flex-wrap">
              <p className="text-sm font-medium text-gray-500 text-wrap">Total Pendapatan</p>
              <h3 className="text-2xl font-bold text-gray-900 text-wrap">Rp {stats.totalEarnings.toLocaleString("id-ID")}</h3>
            </div>
          </div>
        </div>
        <div className="rounded-2xl border bg-white p-6 shadow-sm">
          <div className="flex items-center gap-2">
            <div className="rounded-full bg-orange-50 p-3 text-orange-600">
              <Clock className="h-6 w-6" />
            </div>
            <div className="flex flex-col flex-wrap">
              <p className="text-sm font-medium text-gray-500 text-wrap">Dana Tertahan</p>
              <h3 className="text-2xl font-bold text-gray-900 text-wrap">Rp {stats.pendingPayments.toLocaleString("id-ID")}</h3>
            </div>
          </div>
        </div>
        <div className="rounded-2xl border bg-white p-6 shadow-sm">
          <div className="flex items-center gap-2">
            <div className="rounded-full bg-blue-50 p-3 text-blue-600">
              <CheckCircle2 className="h-6 w-6" />
            </div>
            <div className="flex flex-col flex-wrap">
              <p className="text-sm font-medium text-gray-500 text-wrap">Pekerjaan Selesai</p>
              <h3 className="text-2xl font-bold text-gray-900 text-wrap">{stats.totalClips}</h3>
            </div>
          </div>
        </div>
        <div className="rounded-2xl border bg-white p-6 shadow-sm">
          <div className="flex items-center gap-2">
            <div className="rounded-full bg-purple-50 p-3 text-purple-600">
              <TrendingUp className="h-6 w-6" />
            </div>
            <div className="flex flex-col flex-wrap">
              <p className="text-sm font-medium text-gray-500 text-wrap">Rating Performa</p>
              <h3 className="text-2xl font-bold text-gray-900 text-wrap">4.9/5</h3>
            </div>
          </div>
        </div>
      </div> */}

      <div className="grid grid-cols-1 gap-8 lg:grid-cols-2">
        {/* <div className="rounded-2xl border bg-white p-8 shadow-sm">
          <h3 className="text-xl font-bold text-gray-900 flex items-center gap-2">
            <ShoppingBag className="h-5 w-5 text-primary" /> Cari Pekerjaan?
          </h3>
          <p className="mt-2 text-gray-600">
            Lihat daftar lowongan clipping terbaru dari para pemilik bisnis di Marketplace.
          </p>
          <div className="mt-6">
            <Link href="/dashboard/marketplace">
              <Button className="rounded-full px-6">
                Buka Marketplace
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </Link>
          </div>
        </div> */}

        <div className="rounded-2xl border bg-white p-8 shadow-sm">
          <h3 className="text-xl font-bold text-gray-900 flex items-center gap-2">
            <TrendingUp className="h-5 w-5 text-primary" /> AI Clipper Tool
          </h3>
          <p className="mt-2 text-gray-600">
            Gunakan teknologi AI kami untuk memotong video secara otomatis dan tingkatkan produktivitasmu.
          </p>
          <div className="mt-6">
            <Link href="/dashboard/clipper">
              <Button variant="outline" className="rounded-full px-6">
                Buka AI Tools
                <PlusCircle className="ml-2 h-4 w-4" />
              </Button>
            </Link>
          </div>
        </div>
      </div>
    </div>
  );

  return (
    <div className="space-y-8">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold text-gray-900">Dashboard Overview</h2>
        <div className="text-sm text-gray-500">Role: <span className="font-bold text-primary">{user?.role}</span></div>
      </div>

      {loading ? (
        <div className="flex h-64 items-center justify-center">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
        </div>
        // ) : user?.role === "OWNER" ? (
        //   <OwnerDashboard />
        // ) : (
        //   <ClipperDashboard />
        // )

      ) : <ClipperDashboard />
      }

      {/* Shared Recent Activity Section */}
      {/* <div className="rounded-2xl border bg-white p-8 shadow-sm">
        <div className="flex items-center justify-between mb-6">
          <h3 className="text-xl font-bold text-gray-900">Aktivitas Terbaru</h3>
          <div className="flex items-center gap-4">
            <button
              onClick={markAllRead}
              disabled={markingAll || notifications.filter((n: any) => !n.read_at).length === 0}
              className="text-sm text-gray-500 hover:text-primary font-medium disabled:opacity-40"
            >
              {markingAll ? "..." : "Mark all read"}
            </button>
            <Link href="/dashboard/notifications" className="text-sm text-primary font-medium hover:underline">
              Lihat Notifikasi
            </Link>
          </div>
        </div>

        {notifications.length > 0 && (
          <div className="space-y-3 mb-8">
            {notifications.slice(0, 5).map((n: any) => {
              const isUnread = !n.read_at;
              const icon =
                n.type?.includes("ESCROW") ? Wallet :
                  n.type?.includes("INVITE") ? Users :
                    n.type?.includes("APPROVED") ? CheckCircle2 :
                      n.type?.includes("REVISION") ? AlertCircle :
                        n.type?.includes("SUBMITTED") ? AlertCircle :
                          Briefcase;
              const Icon = icon;
              return (
                <button
                  key={n.id}
                  onClick={() => openNotification(n)}
                  className={`flex items-start justify-between gap-4 p-4 rounded-xl border ${isUnread ? "bg-blue-50 border-blue-100" : "bg-gray-50 border-gray-100"
                    }`}
                >
                  <div className="flex items-start gap-3">
                    <div className={`mt-0.5 p-2 rounded-lg ${isUnread ? "bg-primary text-white" : "bg-white text-gray-600"
                      }`}>
                      <Icon className="h-4 w-4" />
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-gray-900">{n.message}</p>
                      <p className="text-xs text-gray-500 mt-1">
                        {new Date(n.created_at * 1000).toLocaleString("id-ID")}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {isUnread ? (
                      <span className="text-[10px] font-bold uppercase tracking-wider text-primary">New</span>
                    ) : null}
                    <button
                      type="button"
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        markRead(n.id);
                      }}
                      disabled={!isUnread || markingId === n.id}
                      className="text-xs font-bold text-gray-500 hover:text-primary disabled:opacity-40"
                    >
                      {markingId === n.id ? "..." : "Read"}
                    </button>
                  </div>
                </button>
              );
            })}
          </div>
        )}

        {recentJobs.length > 0 ? (
          <div className="space-y-4">
            {recentJobs.map((job) => (
              <div key={job.id} className="flex items-center justify-between p-4 rounded-xl bg-gray-50 border border-gray-100">
                <div className="flex items-center gap-4">
                  <div className={`p-2 rounded-lg ${job.status === 'COMPLETED' ? 'bg-green-100 text-green-600' :
                      job.status === 'IN_PROGRESS' ? 'bg-orange-100 text-orange-600' :
                        'bg-blue-100 text-blue-600'
                    }`}>
                    <Briefcase className="h-5 w-5" />
                  </div>
                  <div>
                    <p className="font-bold text-gray-900">{job.title}</p>
                    <p className="text-xs text-gray-500">{new Date(job.created_at * 1000).toLocaleDateString()}</p>
                  </div>
                </div>
                <div className="text-right">
                  <p className="font-bold text-primary">Rp {job.budget.toLocaleString("id-ID")}</p>
                  <p className="text-[10px] uppercase font-bold tracking-wider text-gray-400">{job.status}</p>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="mt-6 flex flex-col items-center justify-center py-12 text-center">
            <div className="rounded-full bg-gray-50 p-4">
              <ShoppingBag className="h-8 w-8 text-gray-400" />
            </div>
            <p className="mt-4 text-gray-500">Belum ada aktivitas terbaru saat ini.</p>
          </div>
        )}
      </div> */}
    </div>
  );
}
