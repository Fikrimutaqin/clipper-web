import Navbar from "@/components/layout/Navbar";
import Hero from "@/components/landing/Hero";
import Features from "@/components/landing/Features";
import Pricing from "@/components/landing/Pricing";
import { Users, Star, Quote } from "lucide-react";
import Link from "next/link";

const testimonials = [
  {
    content: "ClipFIX benar-benar mengubah cara kami memproduksi konten. Proses clipping yang biasanya memakan waktu berjam-jam, sekarang selesai dalam hitungan menit berkat bantuan AI.",
    author: "Andi Wijaya",
    role: "Tech Content Creator",
    avatar: "AW"
  },
  {
    content: "Sebagai editor video, platform ini memberikan saya aliran klien yang stabil. Sistem Escrow-nya membuat saya merasa tenang saat bekerja karena pembayaran sudah terjamin.",
    author: "Siti Rahma",
    role: "Professional Clipper",
    avatar: "SR"
  },
  {
    content: "Kualitas hasil clipping sangat luar biasa. Fitur suggest AI-nya sangat akurat menemukan momen-momen lucu di podcast kami.",
    author: "Budi Santoso",
    role: "Podcast Owner",
    avatar: "BS"
  }
];

export default function Home() {
  return (
    <main className="min-h-screen bg-white">
      <Navbar />
      <Hero />
      <Features />
      
      {/* Testimonials Section */}
      <section id="testimonials" className="bg-gray-50 py-24 sm:py-32 overflow-hidden">
        <div className="container mx-auto px-4">
          <div className="text-center mb-16">
            <h2 className="text-base font-semibold leading-7 text-primary">Testimoni</h2>
            <p className="mt-2 text-3xl font-bold tracking-tight text-gray-900 sm:text-4xl">
              Dipercaya oleh 100+ Kreator & Bisnis
            </p>
          </div>
          
          <div className="grid grid-cols-1 gap-8 md:grid-cols-3">
            {testimonials.map((t, i) => (
              <div key={i} className="flex flex-col justify-between bg-white p-8 rounded-3xl shadow-sm border border-gray-100 hover:shadow-md transition-shadow">
                <div>
                  <div className="flex gap-1 mb-4 text-orange-400">
                    {[...Array(5)].map((_, i) => <Star key={i} className="h-4 w-4 fill-current" />)}
                  </div>
                  <Quote className="h-8 w-8 text-primary/20 mb-4" />
                  <p className="text-gray-600 italic leading-relaxed">"{t.content}"</p>
                </div>
                <div className="mt-8 flex items-center gap-4 border-t pt-6">
                  <div className="h-12 w-12 rounded-full bg-primary/10 flex items-center justify-center text-primary font-bold">
                    {t.avatar}
                  </div>
                  <div>
                    <div className="font-bold text-gray-900">{t.author}</div>
                    <div className="text-sm text-gray-500">{t.role}</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <Pricing />
      
      {/* Newsletter / CTA Final */}
      <section className="bg-primary py-20">
        <div className="container mx-auto px-4 text-center">
          <h2 className="text-3xl font-bold text-white sm:text-4xl mb-6">Siap untuk Viral Hari Ini?</h2>
          <p className="text-primary-foreground/80 text-lg max-w-2xl mx-auto mb-10 text-white">
            Bergabunglah dengan ratusan kreator lainnya yang telah meningkatkan produktivitas konten mereka dengan ClipFIX.
          </p>
          <div className="flex justify-center gap-4">
            <Link href="/register">
              <button className="bg-white text-primary font-bold px-8 py-4 rounded-full hover:bg-gray-100 transition-all shadow-xl hover:scale-105">
                Daftar Gratis Sekarang
              </button>
            </Link>
          </div>
        </div>
      </section>

      <footer className="bg-white border-t py-12">
        <div className="container mx-auto px-4 text-center text-gray-500 text-sm">
          <p>&copy; {new Date().getFullYear()} ClipFIX. All rights reserved.</p>
        </div>
      </footer>
    </main>
  );
}
