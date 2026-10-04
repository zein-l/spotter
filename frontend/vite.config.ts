import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development the Django API runs on :8000; on Vercel both share one origin.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  worker: { format: "es" },
  server: {
    port: 5173,
    proxy: { "/api": { target: process.env.VITE_DEV_API ?? "http://127.0.0.1:8000", changeOrigin: true } },
  },
  build: {
    target: "es2022",
    chunkSizeWarningLimit: 1500,
    rollupOptions: {
      output: { manualChunks: (id) => (id.includes("maplibre-gl") ? "maplibre" : undefined) },
    },
  },
});
