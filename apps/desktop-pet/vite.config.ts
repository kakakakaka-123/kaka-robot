import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { fileURLToPath, URL } from "node:url";

export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    host: "127.0.0.1",
    port: 5174,
    strictPort: true
  },
  build: {
    rollupOptions: {
      input: {
        main: fileURLToPath(new URL("./index.html", import.meta.url)),
        settings: fileURLToPath(new URL("./settings.html", import.meta.url))
      }
    }
  },
  envPrefix: ["VITE_", "TAURI_"]
});
