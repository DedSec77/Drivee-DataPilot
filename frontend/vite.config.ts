import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    strictPort: true,
    allowedHosts: true,
    proxy: {
      "/api": { target: "http://backend:8000", changeOrigin: true },
      "/files": { target: "http://backend:8000", changeOrigin: true },
      "/health": { target: "http://backend:8000", changeOrigin: true },
    },
  },
});
