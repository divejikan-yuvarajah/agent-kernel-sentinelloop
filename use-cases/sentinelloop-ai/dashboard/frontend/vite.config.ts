import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const apiProxy = {
  "/api": {
    target: "http://127.0.0.1:8000",
    changeOrigin: true,
    configure: (proxy) => {
      proxy.on("error", (_err, _req, res) => {
        if (res && !res.headersSent && "writeHead" in res) {
          res.writeHead(502, { "Content-Type": "application/json" });
          res.end(
            JSON.stringify({
              detail: "Dashboard API is not reachable. Start the SentinelLoop API on port 8000, then reload.",
            }),
          );
        }
      });
    },
  },
};

const SPA_HTML_ROUTES = new Set(["/sandbox", "/sandbox/", "/report", "/report/", "/try", "/try/"]);

function spaHtmlRoutes() {
  return {
    name: "spa-html-routes",
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        const raw = req.url || "";
        const path = raw.split("?")[0];
        if (SPA_HTML_ROUTES.has(path)) {
          req.url = "/index.html";
        }
        next();
      });
    },
    configurePreviewServer(server) {
      server.middlewares.use((req, _res, next) => {
        const raw = req.url || "";
        const path = raw.split("?")[0];
        if (SPA_HTML_ROUTES.has(path)) {
          req.url = "/index.html";
        }
        next();
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), spaHtmlRoutes()],
  resolve: {
    alias: {
      "@ds": fileURLToPath(new URL("./design-system", import.meta.url)),
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
    server: {
        host: "127.0.0.1",
        port: 5173,
        strictPort: true,
        proxy: apiProxy,
    },
    preview: {
        host: "127.0.0.1",
        port: 4173,
        strictPort: true,
        proxy: apiProxy,
    },
});
