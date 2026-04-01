"use client";

import { useAuth } from "@/context/AuthContext";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { 
  LayoutDashboard, 
  Scissors, 
  ShoppingBag, 
  LogOut, 
  PlusCircle, 
  Wallet,
  Briefcase,
  TrendingUp
} from "lucide-react";
import Link from "next/link";
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
          <SidebarGroup>
            <SidebarGroupLabel>Navigation</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {navItems.map((item) => (
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
            <button
              onClick={() => router.push("/dashboard/profile")}
              className="h-9 w-9 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold"
            >
              {user.full_name.charAt(0)}
            </button>
          </div>
        </header>
        <main className="p-6 md:p-8">{children}</main>
      </SidebarInset>
    </SidebarProvider>
  );
}
