import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: "#4f46e5",
          hover: "#4338ca",
        },
        background: "#f3f4f6",
        card: "#ffffff",
        border: "#e5e7eb",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};
export default config;
