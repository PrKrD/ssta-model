import { defineConfig } from "vite";
import { viteStaticCopy } from "vite-plugin-static-copy";

export default defineConfig({
  define: {
    CESIUM_BASE_URL: JSON.stringify("/cesium"),
  },
  plugins: [
    viteStaticCopy({
      targets: ["Assets", "ThirdParty", "Widgets", "Workers"].map((directory) => ({
        src: `node_modules/cesium/Build/Cesium/${directory}`,
        dest: "cesium",
      })),
    }),
  ],
  server: {
    port: 5173,
  },
});
