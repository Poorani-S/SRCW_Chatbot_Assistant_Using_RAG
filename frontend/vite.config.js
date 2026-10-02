import path from "path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  // Proxy /api/* to FastAPI so the frontend never hardcodes the backend URL
  server: { proxy: { "/api": "http://localhost:8000" } },
  build: {
    // Smaller bundle for embedding as a widget
    rollupOptions: {
      output: { manualChunks: { react: ["react", "react-dom"] } },
    },
  },
});
