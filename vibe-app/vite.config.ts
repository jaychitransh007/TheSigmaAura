import { vitePlugin as remix } from "@remix-run/dev";
import { installGlobals } from "@remix-run/node";
import { defineConfig, type UserConfig } from "vite";
import tsconfigPaths from "vite-tsconfig-paths";

installGlobals({ nativeFetch: true });

// Related: https://github.com/remix-run/remix/issues/2835#issuecomment-1144102176
// Replace the HOST env var with SHOPIFY_APP_URL so that it doesn't break the remix server. The CLI will eventually
// stop passing in HOST, so we can remove this workaround after the next major release.
if (
  process.env.HOST &&
  (!process.env.SHOPIFY_APP_URL ||
    process.env.SHOPIFY_APP_URL === process.env.HOST)
) {
  process.env.SHOPIFY_APP_URL = process.env.HOST;
  delete process.env.HOST;
}

const host = new URL(process.env.SHOPIFY_APP_URL || "http://localhost")
  .hostname;

// App Proxy customer pages render at thesigmavibe.shop/apps/vibe/* but the
// Remix bundles ship from vibe-app-five.vercel.app. If Vite emits relative
// asset URLs (the default), the browser resolves them against the
// storefront origin → 404 from Shopify. Setting base to the full
// SHOPIFY_APP_URL makes Vite emit absolute URLs that the browser fetches
// straight from Vercel, bypassing the proxy. Falls back to "/" for local
// dev when SHOPIFY_APP_URL is unset.
const assetBase = process.env.SHOPIFY_APP_URL
  ? (process.env.SHOPIFY_APP_URL.endsWith("/")
      ? process.env.SHOPIFY_APP_URL
      : `${process.env.SHOPIFY_APP_URL}/`)
  : "/";

let hmrConfig;
if (host === "localhost") {
  hmrConfig = {
    protocol: "ws",
    host: "localhost",
    port: 64999,
    clientPort: 64999,
  };
} else {
  hmrConfig = {
    protocol: "wss",
    host: host,
    port: parseInt(process.env.FRONTEND_PORT!) || 8002,
    clientPort: 443,
  };
}

export default defineConfig({
  base: assetBase,
  server: {
    allowedHosts: [host],
    cors: {
      preflightContinue: true,
    },
    port: Number(process.env.PORT || 3000),
    hmr: hmrConfig,
    fs: {
      // See https://vitejs.dev/config/server-options.html#server-fs-allow for more information
      allow: ["app", "node_modules"],
    },
  },
  plugins: [
    remix({
      ignoredRouteFiles: ["**/.*"],
      future: {
        v3_fetcherPersist: true,
        v3_relativeSplatPath: true,
        v3_throwAbortReason: true,
        // v3_lazyRouteDiscovery uses runtime fetches to `/__manifest?paths[]=`
        // against the PAGE's origin. Through App Proxy, that means
        // thesigmavibe.shop/__manifest → Shopify 404. Disabling it so all
        // routes are known at hydration time. Our route tree is small
        // (5 customer pages + 1 resource route), so eager discovery has
        // no measurable cost.
        v3_lazyRouteDiscovery: false,
        v3_singleFetch: false,
        v3_routeConfig: true,
      },
    }),
    tsconfigPaths(),
  ],
  build: {
    assetsInlineLimit: 0,
  },
  optimizeDeps: {
    include: ["@shopify/app-bridge-react", "@shopify/polaris"],
  },
}) satisfies UserConfig;
