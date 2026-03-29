import { Button } from "@/components/ui/button";
import { ArrowRight, Video, Users, Zap } from "lucide-react";
import Link from "next/link";

export default function Hero() {
  return (
    <section className="relative overflow-hidden bg-white py-24 sm:py-32">
      <div className="container mx-auto px-4">
        <div className="flex flex-col items-center text-center">
          <div className="mb-8 flex items-center justify-center gap-2 rounded-full bg-primary/10 px-4 py-1 text-sm font-semibold text-primary">
            <Zap className="h-4 w-4" />
            <span>AI-Powered Video Clipping</span>
          </div>
          
          <h1 className="max-w-4xl text-4xl font-extrabold tracking-tight text-gray-900 sm:text-6xl">
            Transform Long Content into <span className="text-primary">Viral Masterpieces</span>
          </h1>
          
          <p className="mt-6 max-w-2xl text-lg leading-8 text-gray-600">
            ClipFIX menghubungkan pemilik bisnis dengan Clipper profesional. Gunakan AI kami untuk menemukan momen terbaik dan biarkan para ahli yang memolesnya.
          </p>
          
          <div className="mt-10 flex items-center gap-x-6">
            <Link href="/register">
              <Button size="lg" className="rounded-full px-8 shadow-lg hover:shadow-primary/30 transition-all">
                Mulai Sekarang <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </Link>
            <Button variant="ghost" size="lg" className="rounded-full">
              Lihat Demo
            </Button>
          </div>

          <div className="mt-16 grid grid-cols-1 gap-8 sm:grid-cols-3">
            <div className="flex flex-col items-center gap-2">
              <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-gray-50 text-primary">
                <Video className="h-6 w-6" />
              </div>
              <h3 className="font-bold">10k+ Video Terproses</h3>
            </div>
            <div className="flex flex-col items-center gap-2">
              <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-gray-50 text-primary">
                <Users className="h-6 w-6" />
              </div>
              <h3 className="font-bold">500+ Clipper Aktif</h3>
            </div>
            <div className="flex flex-col items-center gap-2">
              <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-gray-50 text-primary">
                <Zap className="h-6 w-6" />
              </div>
              <h3 className="font-bold">90% Lebih Cepat</h3>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
