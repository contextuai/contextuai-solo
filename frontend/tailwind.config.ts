import type { Config } from "tailwindcss";

const m3Primary = {
  50: "rgb(var(--m3-primary-50) / <alpha-value>)",
  100: "rgb(var(--m3-primary-100) / <alpha-value>)",
  200: "rgb(var(--m3-primary-200) / <alpha-value>)",
  300: "rgb(var(--m3-primary-300) / <alpha-value>)",
  400: "rgb(var(--m3-primary-400) / <alpha-value>)",
  500: "rgb(var(--m3-primary-500) / <alpha-value>)",
  600: "rgb(var(--m3-primary-600) / <alpha-value>)",
  700: "rgb(var(--m3-primary-700) / <alpha-value>)",
  800: "rgb(var(--m3-primary-800) / <alpha-value>)",
  900: "rgb(var(--m3-primary-900) / <alpha-value>)",
  950: "rgb(var(--m3-primary-950) / <alpha-value>)",
};

const m3Neutral = {
  50: "rgb(var(--m3-neutral-50) / <alpha-value>)",
  100: "rgb(var(--m3-neutral-100) / <alpha-value>)",
  200: "rgb(var(--m3-neutral-200) / <alpha-value>)",
  300: "rgb(var(--m3-neutral-300) / <alpha-value>)",
  400: "rgb(var(--m3-neutral-400) / <alpha-value>)",
  500: "rgb(var(--m3-neutral-500) / <alpha-value>)",
  600: "rgb(var(--m3-neutral-600) / <alpha-value>)",
  700: "rgb(var(--m3-neutral-700) / <alpha-value>)",
  800: "rgb(var(--m3-neutral-800) / <alpha-value>)",
  900: "rgb(var(--m3-neutral-900) / <alpha-value>)",
  950: "rgb(var(--m3-neutral-950) / <alpha-value>)",
};

const secondaryColors = {
  50: "#F0F9FF",
  100: "#E0F2FE",
  200: "#BAE6FD",
  300: "#7DD3FC",
  400: "#38BDF8",
  500: "#0EA5E9",
  600: "#0284C7",
  700: "#0369A1",
  800: "#075985",
  900: "#0C4A6E",
};

export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        primary: m3Primary,
        secondary: secondaryColors,
        neutral: m3Neutral,
        dark: m3Neutral,
        success: "#10B981",
        warning: "#F59E0B",
        error: "#EF4444",
        info: "#3B82F6",
      },
      fontFamily: {
        sans: ["Inter", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Fira Code", "Consolas", "monospace"],
      },
    },
  },
  plugins: [require("@tailwindcss/typography")],
} satisfies Config;
