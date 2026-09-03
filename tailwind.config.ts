import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#17181A",
        muted: "#6E6E73",
        hairline: "#DCDCE0",
        paper: "#FFFFFF",
        mist: "#F5F5F7",
        signal: "#0B5FD0",
        signalDim: "#E7F0FC",
        ok: "#1B8A5A",
        warn: "#B8760B",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "sans-serif"],
        mono: ["'IBM Plex Mono'", "ui-monospace", "monospace"],
      },
      letterSpacing: { tightest: "-0.045em" },
      maxWidth: { shell: "1180px" },
      keyframes: {
        rise: {
          "0%": { opacity: "0", transform: "translateY(12px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        etch: {
          "0%": { opacity: "0", transform: "translateX(-6px)" },
          "100%": { opacity: "1", transform: "translateX(0)" },
        },
      },
      animation: {
        rise: "rise .7s cubic-bezier(.16,1,.3,1) both",
        etch: "etch .5s cubic-bezier(.16,1,.3,1) both",
      },
    },
  },
  plugins: [],
};
export default config;
