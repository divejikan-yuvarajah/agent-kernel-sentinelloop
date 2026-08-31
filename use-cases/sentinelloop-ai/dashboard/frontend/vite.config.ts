import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@ds": fileURLToPath(new URL("./design-system", import.meta.url)),
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/incidents": "http://127.0.0.1:8000",
      "/analytics": "http://127.0.0.1:8000",
      "/router": "http://127.0.0.1:8000",
    },
  },
});
