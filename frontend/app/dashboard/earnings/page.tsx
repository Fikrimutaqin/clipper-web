"use client";

import { useState, useEffect } from "react";
import { useAuth } from "@/context/AuthContext";
import { 
  Wallet, 
  Clock, 
  CheckCircle2, 
  ArrowUpRight, 
  ArrowDownLeft,
  Loader2,
  TrendingUp,
  Download,
  AlertCircle
} from "lucide-react";
import { Button } from "@/components/ui/button";
import api from "@/lib/axios";

interface Transaction {
  id: string;
  title: string;
  amount: number;
  status: string;
  payment_status: string;
  date: number;
}

export default function EarningsPage() {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState({
    totalEarned: 0,
    pendingEscrow: 0,
    readyToWithdraw: 0,
    completedJobs: 0
  });
  const [transactions, setTransactions] = useState<Transaction[]>([]);

  useEffect(() => {
    const fetchEarnings = async () => {
      try {
        const res = await api.get("/api/jobs/my-jobs");
        const jobs = res.data.data;

        // Filter only jobs that affect earnings
        const earningsJobs = jobs.filter((j: any) => 
          j.status === "COMPLETED" || j.payment_status === "ESCROW_HOLD"
        );

        const totalEarned = jobs
          .filter((j: any) => j.payment_status === "RELEASED")
          .reduce((acc: number, curr: any) => acc + curr.budget, 0);

        const pending = jobs
          .filter((j: any) => j.payment_status === "ESCROW_HOLD")
          .reduce((acc: number, curr: any) => acc + curr.budget, 0);

        const ready = jobs
          .filter((j: any) => j.payment_status === "RELEASED") // Simplification: Released = Ready
          .reduce((acc: number, curr: any) => acc + curr.budget, 0);

        setStats({
          totalEarned,
          pendingEscrow: pending,
          readyToWithdraw: ready,
          completedJobs: jobs.filter((j: any) => j.status === "COMPLETED").length
        });

        setTransactions(jobs.map((j: any) => ({
          id: j.id,
          title: j.title,
          amount: j.budget,
          status: j.status,
          payment_status: j.payment_status,
          date: j.updated_at || j.created_at
        })).sort((a: any, b: any) => b.date - a.date));

      } catch (err) {
        console.error("Failed to fetch earnings data", err);
      } finally {
        setLoading(false);
      }
    };

    if (user?.role === "CLIPPER") fetchEarnings();
    else setLoading(false);
  }, [user]);

  if (user?.role !== "CLIPPER") {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <AlertCircle className="h-12 w-12 text-orange-400 mb-4" />
        <h2 className="text-xl font-bold text-gray-900">Akses Ditolak</h2>
        <p className="text-gray-500 max-w-sm mt-2">Halaman Dashboard Keuangan hanya tersedia untuk akun Professional Clipper.</p>
      </div>
    );
  }

  if (loading) return <div className="flex h-64 items-center justify-center"><Loader2 className="animate-spin h-8 w-8 text-primary" /></div>;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Dashboard Keuangan</h1>
        <p className="text-sm text-gray-500">Pantau pendapatan, saldo escrow, dan riwayat transaksimu.</p>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-primary rounded-3xl p-8 text-white shadow-xl shadow-primary/20 relative overflow-hidden group">
          <div className="relative z-10">
            <p className="text-primary-foreground/80 text-sm font-medium mb-1">Total Pendapatan Cair</p>
            <h3 className="text-3xl font-bold mb-6">Rp {stats.totalEarned.toLocaleString("id-ID")}</h3>
            <div className="flex items-center gap-2 text-xs bg-white/10 w-fit px-3 py-1 rounded-full">
              <TrendingUp className="h-3 w-3" /> +12% dari bulan lalu
            </div>
          </div>
          <Wallet className="absolute -right-4 -bottom-4 h-32 w-32 text-white/10 group-hover:scale-110 transition-transform duration-500" />
        </div>

        <div className="bg-white rounded-3xl border p-8 shadow-sm">
          <div className="flex items-center gap-4 mb-4">
            <div className="p-3 rounded-2xl bg-orange-50 text-orange-600">
              <Clock className="h-6 w-6" />
            </div>
            <div>
              <p className="text-sm font-medium text-gray-500">Dana di Escrow</p>
              <h3 className="text-xl font-bold text-gray-900">Rp {stats.pendingEscrow.toLocaleString("id-ID")}</h3>
            </div>
          </div>
          <p className="text-xs text-gray-400 italic">Dana ini sedang ditahan sistem sampai pekerjaanmu disetujui Owner.</p>
        </div>

        <div className="bg-white rounded-3xl border p-8 shadow-sm">
          <div className="flex items-center gap-4 mb-4">
            <div className="p-3 rounded-2xl bg-green-50 text-green-600">
              <CheckCircle2 className="h-6 w-6" />
            </div>
            <div>
              <p className="text-sm font-medium text-gray-500">Saldo Siap Tarik</p>
              <h3 className="text-xl font-bold text-gray-900">Rp {stats.readyToWithdraw.toLocaleString("id-ID")}</h3>
            </div>
          </div>
          <Button className="w-full rounded-xl" variant="outline" size="sm">
            Tarik Saldo <ArrowUpRight className="ml-2 h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Transaction History */}
      <div className="bg-white rounded-3xl border shadow-sm overflow-hidden">
        <div className="p-8 border-b flex items-center justify-between">
          <h3 className="text-lg font-bold text-gray-900">Riwayat Pendapatan</h3>
          <Button variant="ghost" size="sm" className="text-xs font-bold text-primary">
            <Download className="h-4 w-4 mr-2" /> Download Report (PDF)
          </Button>
        </div>
        
        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="bg-gray-50 text-gray-500 text-[10px] uppercase tracking-widest font-bold">
                <th className="px-8 py-4">Pekerjaan</th>
                <th className="px-8 py-4">Tanggal</th>
                <th className="px-8 py-4">Status</th>
                <th className="px-8 py-4">Pembayaran</th>
                <th className="px-8 py-4 text-right">Jumlah</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {transactions.length > 0 ? transactions.map((t) => (
                <tr key={t.id} className="hover:bg-gray-50 transition-colors group">
                  <td className="px-8 py-6">
                    <p className="font-bold text-gray-900 group-hover:text-primary transition-colors">{t.title}</p>
                    <p className="text-[10px] text-gray-400 font-mono">ID: {t.id.slice(0,8)}</p>
                  </td>
                  <td className="px-8 py-6 text-sm text-gray-500">
                    {new Date(t.date * 1000).toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' })}
                  </td>
                  <td className="px-8 py-6">
                    <span className={`px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider ${
                      t.status === 'COMPLETED' ? 'bg-green-50 text-green-600' :
                      t.status === 'IN_PROGRESS' ? 'bg-orange-50 text-orange-600' :
                      'bg-blue-50 text-blue-600'
                    }`}>
                      {t.status}
                    </span>
                  </td>
                  <td className="px-8 py-6">
                    <div className="flex items-center gap-2">
                      <div className={`h-2 w-2 rounded-full ${
                        t.payment_status === 'RELEASED' ? 'bg-green-500' :
                        t.payment_status === 'ESCROW_HOLD' ? 'bg-orange-500' :
                        'bg-gray-300'
                      }`} />
                      <span className="text-sm font-medium text-gray-700 capitalize">
                        {t.payment_status.replace('_', ' ').toLowerCase()}
                      </span>
                    </div>
                  </td>
                  <td className="px-8 py-6 text-right">
                    <p className="font-bold text-gray-900 flex items-center justify-end">
                      {t.payment_status === 'RELEASED' ? (
                        <ArrowDownLeft className="h-4 w-4 text-green-500 mr-1" />
                      ) : (
                        <Clock className="h-4 w-4 text-orange-500 mr-1" />
                      )}
                      Rp {t.amount.toLocaleString("id-ID")}
                    </p>
                  </td>
                </tr>
              )) : (
                <tr>
                  <td colSpan={5} className="px-8 py-20 text-center text-gray-400 italic">
                    Belum ada riwayat pendapatan yang tercatat.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
