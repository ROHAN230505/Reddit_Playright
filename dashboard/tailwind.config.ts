import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: "#f6f7f9",
        foreground: "#0f172a",
        muted: "#64748b",
        border: "#e5e7eb",
        panel: "#ffffff",
        accent: "#0f766e",
        warning: "#b45309",
        danger: "#b91c1c"
      },
      boxShadow: {
        soft: "0 1px 2px 0 rgba(16, 24, 40, 0.04), 0 1px 3px 0 rgba(16, 24, 40, 0.06)",
        lift: "0 4px 12px -2px rgba(16, 24, 40, 0.08), 0 2px 6px -2px rgba(16, 24, 40, 0.05)"
      }
    }
  },
  plugins: [],
};

export default config;
