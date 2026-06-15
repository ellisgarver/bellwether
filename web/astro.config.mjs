import { defineConfig } from "astro/config";

// Static site for GitHub Pages (ADR-043). `site` + `base` come from env so CI can
// set them to the Pages URL/repo subpath; local dev defaults to root.
//   SITE=https://<user>.github.io BASE=/macro-narrative-dynamics npm run build
export default defineConfig({
  site: process.env.SITE || "http://localhost:4321",
  base: process.env.BASE || "/",
  output: "static",
  trailingSlash: "ignore",
});
