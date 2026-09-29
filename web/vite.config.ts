import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev, proxy API and OAuth routes to the FastAPI backend so cookies stay same-origin.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
      "/auth": "http://localhost:8000",
    },
  },
});
