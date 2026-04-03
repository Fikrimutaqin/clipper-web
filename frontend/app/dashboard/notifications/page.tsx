"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import api from "@/lib/axios";
import { Button } from "@/components/ui/button";
import { Loader2, Bell, CheckCircle2, Briefcase, AlertCircle } from "lucide-react";

type NotificationItem = {
  id: number;
  type: string;
  message: string;
  meta: Record<string, any>;
  created_at: number;
  read_at: number | null;
};

export default function NotificationsPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [markingAll, setMarkingAll] = useState(false);
  const [markingId, setMarkingId] = useState<number | null>(null);
  const [items, setItems] = useState<NotificationItem[]>([]);

  const unreadCount = useMemo(() => items.filter((n) => !n.read_at).length, [items]);

  const fetchNotifications = async () => {
    const res = await api.get("/api/marketplace/notifications");
    setItems(res.data.data || []);
    window.dispatchEvent(new Event("clipfix:notifications-updated"));
  };

  useEffect(() => {
    const init = async () => {
      try {
        setLoading(true);
        await fetchNotifications();
      } finally {
        setLoading(false);
      }
    };
    init();
  }, []);

  const markRead = async (id: number) => {
    setMarkingId(id);
    try {
      await api.post(`/api/marketplace/notifications/${id}/read`);
      const now = Math.floor(Date.now() / 1000);
      setItems((prev) => prev.map((n) => (n.id === id ? { ...n, read_at: now } : n)));
      window.dispatchEvent(new Event("clipfix:notifications-updated"));
    } finally {
      setMarkingId(null);
    }
  };

  const markAllRead = async () => {
    setMarkingAll(true);
    try {
      await api.post("/api/marketplace/notifications/read-all");
      const now = Math.floor(Date.now() / 1000);
      setItems((prev) => prev.map((n) => (n.read_at ? n : { ...n, read_at: now })));
      window.dispatchEvent(new Event("clipfix:notifications-updated"));
    } finally {
      setMarkingAll(false);
    }
  };

  const openNotification = async (n: NotificationItem) => {
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
    }
    router.push("/dashboard/notifications");
  };

  const getIcon = (type: string) => {
    if (type?.includes("APPROVED")) return CheckCircle2;
    if (type?.includes("ESCROW")) return Briefcase;
    if (type?.includes("INVITE")) return Bell;
    if (type?.includes("SUBMITTED") || type?.includes("REVISION")) return AlertCircle;
    return Bell;
  };

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="space-y-8">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Notifications</h1>
          <p className="text-sm text-gray-500">
            {unreadCount > 0 ? `${unreadCount} belum dibaca` : "Semua notifikasi sudah dibaca"}
          </p>
        </div>
        <Button
          variant="outline"
          className="rounded-full"
          disabled={markingAll || items.length === 0 || unreadCount === 0}
          onClick={markAllRead}
        >
          {markingAll ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
          Mark all as read
        </Button>
      </div>

      {items.length === 0 ? (
        <div className="bg-white rounded-2xl border p-12 text-center shadow-sm">
          <div className="mx-auto w-16 h-16 bg-gray-50 rounded-full flex items-center justify-center mb-4">
            <Bell className="h-8 w-8 text-gray-400" />
          </div>
          <h3 className="text-lg font-semibold text-gray-900">Belum ada notifikasi</h3>
          <p className="text-gray-500 mt-2">Aktivitas marketplace akan muncul di sini.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((n) => {
            const Icon = getIcon(n.type);
            const isUnread = !n.read_at;
            return (
              <button
                key={n.id}
                onClick={() => openNotification(n)}
                className={`w-full text-left rounded-2xl border p-5 transition-colors ${
                  isUnread ? "bg-blue-50 border-blue-100" : "bg-white hover:bg-gray-50"
                }`}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-start gap-3">
                    <div className={`mt-0.5 p-2 rounded-lg ${
                      isUnread ? "bg-primary text-white" : "bg-gray-50 text-gray-600"
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
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="rounded-full"
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        markRead(n.id);
                      }}
                      disabled={!isUnread || markingId === n.id}
                    >
                      {markingId === n.id ? <Loader2 className="h-4 w-4 animate-spin" /> : "Read"}
                    </Button>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
