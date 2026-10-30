/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        surface: "hsl(var(--surface))",
        muted: "hsl(var(--muted))",
        accent: "hsl(var(--accent))",
        positive: "hsl(var(--positive))",
        negative: "hsl(var(--negative))",
        warning: "hsl(var(--warning))",
      },
      borderRadius: {
        xl: "0.9rem",
      },
      fontFamily: {
        mono: ["IBM Plex Mono", "Consolas", "monospace"],
        sans: ["IBM Plex Sans", "Segoe UI", "sans-serif"],
      },
      boxShadow: {
        panel: "0 16px 40px rgba(0, 0, 0, 0.24)",
      },
    },
  },
  plugins: [],
};
