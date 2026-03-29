"use client";

import { useAuth } from "@/context/AuthContext";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { 
  LayoutDashboard, 
  Scissors, 
  ShoppingBag, 
  User, 
  LogOut, 
  PlusCircle, 
  Video,
  Wallet,
  Briefcase,
  TrendingUp
} from "lucide-react";
import Link from "next/link";
import { SidebarTrigger } from "@/components/ui/sidebar";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user, loading, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!loading && !user) {
      router.push("/login");
    }
  }, [user, loading, router]);

  if (loading || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      </div>
    );
  }

  const navItems = [
    { label: "Overview", icon: LayoutDashboard, href: "/dashboard" },
    ...(user.role === "OWNER" 
      ? [
          { label: "Post New Job", icon: PlusCircle, href: "/dashboard/post-job" },
          { label: "Manage Jobs", icon: Briefcase, href: "/dashboard/my-jobs" }
        ]
      : [
          { label: "Marketplace", icon: ShoppingBag, href: "/dashboard/marketplace" },
          { label: "My Jobs", icon: Briefcase, href: "/dashboard/my-jobs" },
          { label: "Earnings", icon: Wallet, href: "/dashboard/earnings" }
        ]
    ),
    { label: "AI Clipper Tool", icon: TrendingUp, href: "/dashboard/clipper" },
    { label: "Marketplace", icon: ShoppingBag, href: "/dashboard/marketplace" },
    // { label: "My Profile", icon: User, href: "/dashboard/profile" },
  ];

  return (
    <div className="flex min-h-screen bg-gray-50">
      {/* Sidebar */}
      <aside className="fixed left-0 top-0 h-full w-64 border-r bg-white">
        <div className="flex h-16 items-center px-6">
          <Link href="/" className="flex items-center gap-2 text-xl font-bold text-primary">
            <Scissors className="h-6 w-6" />
            <span>ClipFIX</span>
          </Link>
        </div>

        <SidebarTrigger className="-ml-1" />
        
        <nav className="mt-6 space-y-1 px-4">
          {navItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-gray-600 ${pathname === item.href ? "bg-primary text-white" : ""}`}
            >
              <item.icon className="h-5 w-5" />
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="absolute bottom-4 w-full px-4">
          <button
            onClick={logout}
            className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-red-600 hover:bg-red-50"
          >
            <LogOut className="h-5 w-5" />
            Logout
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="ml-64 w-full p-8">
        <header className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              Welcome back, {user.full_name}!
            </h1>
            <p className="text-sm text-gray-500">
              Role: <span className="font-semibold text-primary">{user.role}</span>
            </p>
          </div>
          <div className="flex items-center gap-4">
            <div onClick={() => router.push("/dashboard/profile")}  className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold cursor-pointer">
              {user.full_name.charAt(0)}
            </div>
          </div>
        </header>
        
        {children}
      </main>
    </div>
  );
}
