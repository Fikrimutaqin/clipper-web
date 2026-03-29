import Link from "next/link";
import { Scissors } from "lucide-react";

export default function Navbar() {
  return (
    <nav className="sticky top-0 z-50 w-full border-b bg-white/95 backdrop-blur supports-[backdrop-filter]:bg-white/60">
      <div className="container mx-auto flex h-16 items-center justify-between px-4">
        <div className="flex items-center gap-2">
          <Link href="/" className="flex items-center gap-2 text-xl font-bold text-primary">
            <Scissors className="h-6 w-6" />
            <span>ClipFIX</span>
          </Link>
        </div>
        
        <div className="hidden md:flex items-center gap-8 text-sm font-medium">
          <Link href="#features" className="transition-colors hover:text-primary">Features</Link>
          <Link href="#pricing" className="transition-colors hover:text-primary">Pricing</Link>
          <Link href="#testimonials" className="transition-colors hover:text-primary">Testimonials</Link>
        </div>

        <div className="flex items-center gap-4">
          <Link href="/login" className="text-sm font-medium hover:text-primary">Login</Link>
          <Link 
            href="/register" 
            className="rounded-full bg-primary px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-primary-hover"
          >
            Get Started
          </Link>
        </div>
      </div>
    </nav>
  );
}
