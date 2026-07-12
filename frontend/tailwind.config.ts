import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // green-tinted terminal — Alpha Engine identity, not zinc
        void: "#0A0D0C",
        panel: "#101513",
        panel2: "#161C19",
        rule: "#242C28",
        muted: "#7A8580",
        body: "#C9D1CC",
        bright: "#F2F5F3",
        gain: "#2FBF71",
        loss: "#E5533C",
        cobalt: "#5B7CFF",
        warn: "#D9A03F",
      },
      fontFamily: {
        display: ["var(--font-archivo)"],
        body: ["var(--font-inter)"],
        mono: ["var(--font-plex-mono)"],
      },
      fontSize: {
        "2xs": ["0.625rem", "0.875rem"],
      },
      animation: {
        "fade-in": "fadeIn 0.3s ease-out",
      },
      keyframes: {
        fadeIn: {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
      },
    },
  },
  plugins: [],
};
export default config;
