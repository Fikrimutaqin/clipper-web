"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { useRouter } from "next/navigation";
import api from "@/lib/axios";
import { 
  Loader2, 
  Briefcase, 
  Clock, 
  CheckCircle2, 
  AlertCircle,
  Video,
  Wallet
} from "lucide-react";

interface Job {
  id: string;
  title: string;
  budget: number;
  status: string;
  created_at: number;
  format_type: string;
}

export default function MyJobsPage() {
  const { user } = useAuth();
  const router = useRouter();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchMyJobs = async () => {
      try {
        const res = await api.get("/api/jobs/my-jobs");
        setJobs(res.data.data);
      } catch (err) {
        console.error("Failed to fetch my jobs", err);
      } finally {
        setLoading(false);
      }
    };
    fetchMyJobs();
  }, []);

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "OPEN": return <Briefcase className="h-4 w-4 text-blue-500" />;
      case "IN_PROGRESS": return <Clock className="h-4 w-4 text-orange-500" />;
      case "COMPLETED": return <CheckCircle2 className="h-4 w-4 text-green-500" />;
      default: return <AlertCircle className="h-4 w-4 text-gray-500" />;
    }
  };

  if (loading) return <div className="flex h-64 items-center justify-center"><Loader2 className="animate-spin" /></div>;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Pekerjaan Saya</h1>
        <p className="text-sm text-gray-500">
          {user?.role === "OWNER" 
            ? "Kelola lowongan yang sudah kamu posting." 
            : "Pantau pekerjaan yang sedang kamu kerjakan."}
        </p>
      </div>

      {jobs.length === 0 ? (
        <div className="bg-white rounded-2xl border p-12 text-center shadow-sm">
          <p className="text-gray-500">Belum ada daftar pekerjaan.</p>
        </div>
      ) : (
        <div className="bg-white rounded-2xl border overflow-hidden shadow-sm">
          <table className="w-full text-left text-sm">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="px-6 py-4 font-semibold text-gray-900">Judul Job</th>
                <th className="px-6 py-4 font-semibold text-gray-900">Budget</th>
                <th className="px-6 py-4 font-semibold text-gray-900">Status</th>
                <th className="px-6 py-4 font-semibold text-gray-900">Format</th>
                <th className="px-6 py-4 font-semibold text-gray-900">Tanggal</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {jobs.map((job) => (
                <tr 
                  key={job.id} 
                  className="hover:bg-gray-50 transition-colors cursor-pointer"
                  onClick={() => router.push(`/dashboard/jobs/${job.id}`)}
                >
                  <td className="px-6 py-4 font-medium text-gray-900">{job.title}</td>
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-1">
                      <Wallet className="h-3 w-3 text-gray-400" />
                      Rp {job.budget.toLocaleString("id-ID")}
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-2">
                      {getStatusIcon(job.status)}
                      <span className="capitalize">{job.status.toLowerCase().replace("_", " ")}</span>
                    </div>
                  </td>
                  <td className="px-6 py-4 capitalize">
                    <div className="flex items-center gap-2">
                      <Video className="h-3 w-3 text-gray-400" />
                      {job.format_type}
                    </div>
                  </td>
                  <td className="px-6 py-4 text-gray-500">
                    {new Date(job.created_at * 1000).toLocaleDateString("id-ID")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
