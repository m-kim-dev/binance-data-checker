import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: process.env.VITE_PROXY_TARGET ?? "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path) =>
          process.env.VITE_PROXY_TARGET?.includes("4010")
            ? path.replace(/^\/api\/v1/, "")
            : path
      }
    }
  }
});
