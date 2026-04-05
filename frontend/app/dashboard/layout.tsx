"use client";

import { useAuth } from "@/context/AuthContext";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  LayoutDashboard,
  Scissors,
  ShoppingBag,
  LogOut,
  PlusCircle,
  Wallet,
  Briefcase,
  TrendingUp,
  Bell,
  Library,
  Sparkles
} from "lucide-react";
import Link from "next/link";
import api from "@/lib/axios";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarSeparator,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { Separator } from "@/components/ui/separator";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user, loading, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [unreadCount, setUnreadCount] = useState(0);

  useEffect(() => {
    if (!loading && !user) {
      router.push("/login");
    }
  }, [user, loading, router]);

  // useEffect(() => {
  //   if (!user) return;

  //   const refresh = async () => {
  //     try {
  //       const res = await api.get("/api/marketplace/notifications");
  //       setUnreadCount(res.data?.meta?.unread_count || 0);
  //     } catch {
  //       setUnreadCount(0);
  //     }
  //   };

  //   const onUpdated = () => {
  //     refresh();
  //   };

  //   refresh();
  //   const interval = window.setInterval(refresh, 20000);
  //   window.addEventListener("clipfix:notifications-updated", onUpdated as any);
  //   return () => {
  //     window.clearInterval(interval);
  //     window.removeEventListener("clipfix:notifications-updated", onUpdated as any);
  //   };
  // }, [user, pathname]);

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
        { label: "Manage Jobs", icon: Briefcase, href: "/dashboard/my-jobs" },
        { label: "Browse Clippers", icon: ShoppingBag, href: "/dashboard/marketplace" },
      ]
      : [
        { label: "Marketplace", icon: ShoppingBag, href: "/dashboard/marketplace" },
        { label: "My Jobs", icon: Briefcase, href: "/dashboard/my-jobs" },
        { label: "Earnings", icon: Wallet, href: "/dashboard/earnings" },
      ]),
  ];

  const toolItems = [
    { label: "AI Clipper", icon: TrendingUp, href: "/dashboard/clipper" },
    { label: "AI Video Studio", icon: Sparkles, href: "/dashboard/video-editor" },
  ];

  const storageItems = [
    { label: "Media Library", icon: Library, href: "/dashboard/media" },
  ];

  return (
    <SidebarProvider>
      <Sidebar>
        <SidebarHeader className="p-4">
          <Link href="/" className="flex items-center gap-2 text-lg font-bold text-primary">
            <Scissors className="h-5 w-5" />
            <span>ClipFIX</span>
          </Link>
          <div
            className="mt-2 flex items-center gap-3 rounded-xl border bg-white px-3 py-2"
            onClick={() => router.push("/dashboard/profile")}
            role="button"
          >
            <div className="h-9 w-9 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold">
              {user.full_name.charAt(0)}
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-bold text-gray-900">{user.full_name}</p>
              <p className="text-[10px] font-bold uppercase tracking-wider text-gray-400">{user.role}</p>
            </div>
          </div>
        </SidebarHeader>

        <SidebarSeparator />

        <SidebarContent>
          {/* <SidebarGroup>
            <SidebarGroupLabel>Navigation</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {navItems.map((item) => (
                  <SidebarMenuItem key={item.href}>
                    {(() => {
                      const badgeCount = (item as any).badgeCount as number | undefined;
                      return (
                    <SidebarMenuButton
                      asChild
                      isActive={item.href === pathname}
                      className={
                        item.href === pathname
                          ? "!bg-primary !text-white hover:!bg-primary/90"
                          : undefined
                      }
                    >
                      <Link href={item.href} className="flex items-center gap-3">
                        <item.icon className="h-4 w-4" />
                        <span className="flex-1">{item.label}</span>
                        {typeof badgeCount === "number" && badgeCount > 0 ? (
                          <span className="ml-auto rounded-full bg-white/20 px-2 py-0.5 text-[10px] font-bold">
                            {badgeCount}
                          </span>
                        ) : null}
                      </Link>
                    </SidebarMenuButton>
                      );
                    })()}
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup> */}

          <SidebarGroup>
            <SidebarGroupLabel>Tools</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {toolItems.map((item) => (
                  <SidebarMenuItem key={item.href}>
                    <SidebarMenuButton
                      asChild
                      isActive={item.href === pathname}
                      className={
                        item.href === pathname
                          ? "!bg-primary !text-white hover:!bg-primary/90"
                          : undefined
                      }
                    >
                      <Link href={item.href} className="flex items-center gap-3">
                        <item.icon className="h-4 w-4" />
                        <span>{item.label}</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>

          <SidebarGroup>
            <SidebarGroupLabel>Storage</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {storageItems.map((item) => (
                  <SidebarMenuItem key={item.href}>
                    <SidebarMenuButton
                      asChild
                      isActive={item.href === pathname}
                      className={
                        item.href === pathname
                          ? "!bg-primary !text-white hover:!bg-primary/90"
                          : undefined
                      }
                    >
                      <Link href={item.href} className="flex items-center gap-3">
                        <item.icon className="h-4 w-4" />
                        <span>{item.label}</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        </SidebarContent>

        <SidebarFooter>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton onClick={logout} className="text-red-600 hover:text-red-700">
                <LogOut className="h-4 w-4" />
                <span>Logout</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarFooter>
      </Sidebar>

      <SidebarInset>
        <header className="flex h-16 shrink-0 items-center gap-2 border-b bg-white px-4">
          <SidebarTrigger className="-ml-1" />
          <Separator orientation="vertical" className="mr-2 data-[orientation=vertical]:h-4" />
          <div className="flex flex-1 items-center justify-between">
            <div className="min-w-0">
              <p className="truncate text-sm font-bold text-gray-900">Welcome back, {user.full_name}!</p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => router.push("/dashboard/notifications")}
                className="relative h-9 w-9 rounded-full border bg-white flex items-center justify-center text-gray-700 hover:bg-gray-50"
                aria-label="Notifications"
              >
                <Bell className="h-4 w-4" />
                {unreadCount > 0 ? (
                  <span className="absolute -top-1 -right-1 h-5 min-w-5 rounded-full bg-primary px-1 text-[10px] font-bold text-white flex items-center justify-center">
                    {unreadCount > 99 ? "99+" : unreadCount}
                  </span>
                ) : null}
              </button>
              <button
                onClick={() => router.push("/dashboard/profile")}
                className="h-9 w-9 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold"
              >
                {user.full_name.charAt(0)}
              </button>
            </div>
          </div>
        </header>
        <main className="p-3 md:p-4">{children}</main>
      </SidebarInset>
    </SidebarProvider>
  );
}
