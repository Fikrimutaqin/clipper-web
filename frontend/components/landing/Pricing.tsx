import { Button } from "@/components/ui/button";
import { Check } from "lucide-react";
import Link from "next/link";

const tiers = [
  {
    name: "Starter",
    price: "0",
    description: "Cocok untuk kreator pemula yang ingin mencoba fitur AI.",
    features: ["5 AI Video Discovery / bulan", "Akses Marketplace Clipper", "Standard Video Quality", "Community Support"],
  },
  {
    name: "Pro",
    price: "299k",
    description: "Untuk kreator serius yang ingin konsisten viral.",
    features: [
      "Unlimited AI Video Discovery",
      "Priority di Marketplace",
      "HD Video Quality",
      "Dedicated Account Manager",
      "Analitik Mendalam",
    ],
    popular: true,
  },
  {
    name: "Enterprise",
    price: "Custom",
    description: "Solusi lengkap untuk agensi dan media besar.",
    features: ["White-label Dashboard", "API Access", "Custom AI Training", "SLA Guarantee", "Multi-user Access"],
  },
];

export default function Pricing() {
  return (
    <section id="pricing" className="bg-white py-24 sm:py-32">
      <div className="container mx-auto px-4">
        <div className="mx-auto max-w-2xl text-center">
          <h2 className="text-base font-semibold leading-7 text-primary">Pricing</h2>
          <p className="mt-2 text-3xl font-bold tracking-tight text-gray-900 sm:text-4xl">
            Pilih Paket yang Sesuai dengan Kebutuhanmu
          </p>
        </div>
        <div className="mx-auto mt-16 grid max-w-lg grid-cols-1 gap-y-6 sm:mt-20 lg:max-w-none lg:grid-cols-3 lg:gap-x-8">
          {tiers.map((tier) => (
            <div
              key={tier.name}
              className={`flex flex-col justify-between rounded-3xl bg-white p-8 ring-1 ring-gray-200 xl:p-10 ${
                tier.popular ? "relative shadow-2xl ring-primary" : ""
              }`}
            >
              {tier.popular && (
                <div className="absolute -top-4 left-1/2 -translate-x-1/2 rounded-full bg-primary px-4 py-1 text-sm font-semibold text-white">
                  Paling Populer
                </div>
              )}
              <div>
                <h3 className="text-lg font-semibold leading-8 text-gray-900">{tier.name}</h3>
                <p className="mt-4 text-sm leading-6 text-gray-600">{tier.description}</p>
                <p className="mt-6 flex items-baseline gap-x-1">
                  <span className="text-4xl font-bold tracking-tight text-gray-900">Rp {tier.price}</span>
                  {tier.price !== "Custom" && <span className="text-sm font-semibold leading-6 text-gray-600">/bulan</span>}
                </p>
                <ul role="list" className="mt-8 space-y-3 text-sm leading-6 text-gray-600">
                  {tier.features.map((feature) => (
                    <li key={feature} className="flex gap-x-3">
                      <Check className="h-6 w-5 flex-none text-primary" aria-hidden="true" />
                      {feature}
                    </li>
                  ))}
                </ul>
              </div>
              <Link href="/register" className="mt-8">
                <Button
                  variant={tier.popular ? "default" : "outline"}
                  className="w-full rounded-full"
                >
                  Pilih Paket
                </Button>
              </Link>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
