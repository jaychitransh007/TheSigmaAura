// Read the merchant's active Shopify theme settings + probe out the
// handful of values Vibe uses to bias its visual presentation toward
// the host store (font, primary color, logo URL).
//
// Approach: Admin GraphQL to fetch the MAIN theme's
// `config/settings_data.json`. That file is JSON written by the
// merchant via the theme editor; the schema varies wildly per theme
// (Dawn vs Studio vs Refresh vs a custom theme), so we probe a
// fallback chain for each value and gracefully give up — Vibe falls
// back to Confident Luxe defaults whenever a key isn't found.
//
// Required scope: `read_themes` (granted at F.1 — already in the
// app's scope set).

import { logWarn } from "./logger.server";

// Minimal structural type for the Admin GraphQL client. We only need
// the `graphql` method on it; pulling in `AdminApiContext` from the
// SDK trips the package's typing surface (the export's shape differs
// between Shopify SDK versions).
type AdminGraphqlClient = {
  graphql(query: string, options?: unknown): Promise<Response>;
};

export type ShopifyThemeOverrides = {
  font_body: string;
  color_primary: string;
  color_background: string;
  color_text: string;
  logo_url: string;
  // Used by MerchantHeader to replicate the merchant's storefront
  // brand + nav at the top of customer-facing Vibe pages.
  shop_name: string;
  main_menu: Array<{ title: string; url: string }>;
};

const EMPTY: ShopifyThemeOverrides = {
  font_body: "",
  color_primary: "",
  color_background: "",
  color_text: "",
  logo_url: "",
  shop_name: "",
  main_menu: [],
};

// Theme settings file body GraphQL response shape (Admin API).
type ThemeFileQueryResult = {
  data?: {
    themes?: {
      edges?: Array<{
        node?: {
          id?: string;
          files?: {
            edges?: Array<{
              node?: {
                body?: {
                  content?: string;
                };
              };
            }>;
          };
        };
      }>;
    };
  };
};

type ShopAndMenusIndexResult = {
  data?: {
    shop?: {
      name?: string;
    };
    menus?: {
      edges?: Array<{ node?: { id?: string; handle?: string } }>;
    };
  };
};

type MenuTopLevelByIdResult = {
  data?: {
    menu?: {
      items?: Array<{ title?: string; url?: string }>;
    };
  };
};

/**
 * Fetch theme settings + shop name + main menu via two parallel
 * Admin GraphQL queries (themes vs. menu use different filter shapes
 * so they don't compose into one document cleanly). Each query's
 * failure is contained — a missing menu doesn't prevent capturing
 * the font/color, and vice versa. Logo URL is left empty in this
 * MVP; the MerchantHeader falls back to the shop's name as a text
 * logo.
 *
 * Returns an all-empty object on total failure so the caller can
 * safely PATCH it to the engine (engine treats empty strings as
 * "not provided" and stores NULL).
 */
export async function readMerchantThemeOverrides(
  admin: AdminGraphqlClient,
): Promise<ShopifyThemeOverrides> {
  const [themeContent, shopAndMenu] = await Promise.all([
    fetchThemeSettings(admin),
    fetchShopAndMenu(admin),
  ]);
  const themeProbed = themeContent ? probeThemeSettings(themeContent) : EMPTY;
  return {
    ...themeProbed,
    // shop.brand.logo via Admin GraphQL wins over the theme JSON
    // probe (which is unreliable per theme). themeProbed.logo_url is
    // always empty today, so the precedence is effectively one-way.
    logo_url: shopAndMenu.logoUrl || themeProbed.logo_url,
    shop_name: shopAndMenu.shopName,
    main_menu: shopAndMenu.menuItems,
  };
}

async function fetchThemeSettings(admin: AdminGraphqlClient): Promise<string> {
  try {
    const resp = await admin.graphql(
      `#graphql
      query VibeThemeSettings {
        themes(first: 1, roles: [MAIN]) {
          edges {
            node {
              id
              files(filenames: ["config/settings_data.json"]) {
                edges {
                  node {
                    body {
                      ... on OnlineStoreThemeFileBodyText {
                        content
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }`,
    );
    if (!resp.ok) {
      logWarn("vibe_theme_probe_failed", {
        stage: "theme_settings_http",
        http_status: resp.status,
      });
      return "";
    }
    const gql = (await resp.json()) as ThemeFileQueryResult & {
      errors?: Array<{ message?: string; extensions?: Record<string, unknown> }>;
    };
    if (Array.isArray(gql.errors) && gql.errors.length > 0) {
      logWarn("vibe_theme_probe_failed", {
        stage: "theme_settings_gql",
        errors: gql.errors.map((e) => ({
          message: e.message ?? "",
          code: (e.extensions as { code?: string } | undefined)?.code ?? "",
        })),
      });
      return "";
    }
    const content =
      gql.data?.themes?.edges?.[0]?.node?.files?.edges?.[0]?.node?.body
        ?.content ?? "";
    if (!content) {
      logWarn("vibe_theme_probe_failed", {
        stage: "theme_settings_empty",
        themes_count: gql.data?.themes?.edges?.length ?? 0,
        files_count:
          gql.data?.themes?.edges?.[0]?.node?.files?.edges?.length ?? 0,
      });
    }
    return content;
  } catch (err) {
    logWarn("vibe_theme_probe_failed", {
      stage: "theme_settings_exception",
      error: err instanceof Error ? err.message : String(err),
    });
    return "";
  }
}

async function fetchShopAndMenu(
  admin: AdminGraphqlClient,
): Promise<{
  shopName: string;
  logoUrl: string;
  menuItems: Array<{ title: string; url: string }>;
}> {
  try {
    // Two-step menu lookup (2026-04 Admin API removed `menu(handle:)`):
    // pull shop.name + the menus index (id+handle only) in one call,
    // then fetch the chosen menu's top-level items by id in a second
    // call. MerchantHeader only renders the top level.
    //
    // `shop.brand` was dropped from this query 2026-05-20 — TheSigmaVibe's
    // Admin API rejects it with "Field 'brand' doesn't exist on type
    // 'Shop'" (the field is scope-gated and the Vibe scope set doesn't
    // include the one that exposes it; previously a silent catch hid
    // this and emptied the whole probe). MerchantHeader's text fallback
    // (shop.name in the brand slot) is the same behaviour we've had on
    // Vibe-Test all along since its logo_url was also null.
    const indexResp = await admin.graphql(
      `#graphql
      query VibeShopAndMenusIndex {
        shop {
          name
        }
        menus(first: 50) {
          edges { node { id handle } }
        }
      }`,
    );
    if (!indexResp.ok) {
      logWarn("vibe_theme_probe_failed", {
        stage: "shop_menu_index_http",
        http_status: indexResp.status,
      });
      return { shopName: "", logoUrl: "", menuItems: [] };
    }
    const idx = (await indexResp.json()) as ShopAndMenusIndexResult & {
      errors?: Array<{ message?: string; extensions?: Record<string, unknown> }>;
    };
    if (Array.isArray(idx.errors) && idx.errors.length > 0) {
      logWarn("vibe_theme_probe_failed", {
        stage: "shop_menu_index_gql",
        errors: idx.errors.map((e) => ({
          message: e.message ?? "",
          code: (e.extensions as { code?: string } | undefined)?.code ?? "",
        })),
      });
      return { shopName: "", logoUrl: "", menuItems: [] };
    }
    const shopName = String(idx.data?.shop?.name ?? "").trim();
    // shop.brand.logo intentionally dropped — see comment on the query
    // above. MerchantHeader falls back to shopName as a text logo.
    const logoUrl = "";
    const mainId = idx.data?.menus?.edges?.find(
      (e) => e.node?.handle === "main-menu",
    )?.node?.id;
    if (!mainId) {
      logWarn("vibe_theme_probe_failed", {
        stage: "main_menu_not_found",
        shop_name: shopName,
        menus_count: idx.data?.menus?.edges?.length ?? 0,
        menu_handles: (idx.data?.menus?.edges ?? [])
          .map((e) => e.node?.handle ?? "")
          .filter((h) => h),
      });
      return { shopName, logoUrl, menuItems: [] };
    }

    const menuResp = await admin.graphql(
      `#graphql
      query VibeMainMenuTopLevel($id: ID!) {
        menu(id: $id) {
          items { title url }
        }
      }`,
      { variables: { id: mainId } },
    );
    if (!menuResp.ok) {
      logWarn("vibe_theme_probe_failed", {
        stage: "menu_detail_http",
        http_status: menuResp.status,
      });
      return { shopName, logoUrl, menuItems: [] };
    }
    const detail = (await menuResp.json()) as MenuTopLevelByIdResult & {
      errors?: Array<{ message?: string; extensions?: Record<string, unknown> }>;
    };
    if (Array.isArray(detail.errors) && detail.errors.length > 0) {
      logWarn("vibe_theme_probe_failed", {
        stage: "menu_detail_gql",
        errors: detail.errors.map((e) => ({
          message: e.message ?? "",
          code: (e.extensions as { code?: string } | undefined)?.code ?? "",
        })),
      });
      return { shopName, logoUrl, menuItems: [] };
    }
    const items = detail.data?.menu?.items ?? [];
    const menuItems: Array<{ title: string; url: string }> = [];
    for (const it of items) {
      const title = String(it.title ?? "").trim();
      const url = String(it.url ?? "").trim();
      if (title && url) menuItems.push({ title, url });
    }
    return { shopName, logoUrl, menuItems };
  } catch (err) {
    logWarn("vibe_theme_probe_failed", {
      stage: "shop_menu_exception",
      error: err instanceof Error ? err.message : String(err),
    });
    return { shopName: "", logoUrl: "", menuItems: [] };
  }
}

/**
 * Parse `config/settings_data.json` and pick the merchant's chosen
 * font + colors. Exposed for tests; called by `readMerchantThemeOverrides`.
 *
 * Theme settings JSON has a `current` key with the live theme
 * configuration (or `"presets"` referencing one). Different themes
 * use different setting names — Dawn uses `type_body_font` and
 * `colors_accent_1`; Studio uses `font_body` and `color_primary`;
 * Refresh uses yet another set. We probe a fallback chain ordered
 * most-common-first and give up gracefully when nothing matches.
 */
export function probeThemeSettings(rawJson: string): ShopifyThemeOverrides {
  let parsed: unknown;
  try {
    parsed = JSON.parse(rawJson);
  } catch {
    return EMPTY;
  }
  if (!parsed || typeof parsed !== "object") return EMPTY;
  const root = parsed as Record<string, unknown>;
  // `current` is the live theme settings; falls back to the first
  // preset if `current` is just a preset name (string).
  let settings: Record<string, unknown> = {};
  const cur = root.current;
  if (cur && typeof cur === "object") {
    settings = cur as Record<string, unknown>;
  } else if (typeof cur === "string") {
    const presets = root.presets as Record<string, unknown> | undefined;
    if (presets && presets[cur] && typeof presets[cur] === "object") {
      settings = presets[cur] as Record<string, unknown>;
    }
  }
  // Newer Shopify themes nest under `current.settings` instead of
  // putting fields at the top level. Probe both.
  const nestedSettings = (settings.settings || settings) as Record<
    string,
    unknown
  >;

  return {
    font_body: pickFont(nestedSettings, [
      "type_body_font",       // Dawn, Sense, others derived from Dawn
      "font_body",            // Studio, Refresh
      "body_font",
      "main_body_font",
    ]),
    color_primary: pickColor(nestedSettings, [
      "colors_accent_1",      // Dawn
      "color_primary",        // Studio
      "accent_color",
      "primary_color",
      "button_color",
      "color_button_background",
    ]),
    color_background: pickColor(nestedSettings, [
      "colors_background_1",  // Dawn
      "color_background",
      "background_color",
    ]),
    color_text: pickColor(nestedSettings, [
      "colors_text",          // Dawn
      "color_text",
      "text_color",
    ]),
    // Header logo isn't typically in settings_data.json — it lives in
    // a section's settings or as a file under `assets/`. Skipping for
    // MVP; vibe-app can fall back to the shop's name as a text logo.
    logo_url: "",
    // shop_name + main_menu live outside settings_data.json — they're
    // populated separately by `readMerchantThemeOverrides` via a
    // second GraphQL query. probeThemeSettings returns empty for
    // these so the merged result still type-checks.
    shop_name: "",
    main_menu: [],
  };
}

function pickFont(
  settings: Record<string, unknown>,
  candidates: string[],
): string {
  for (const key of candidates) {
    const raw = settings[key];
    if (typeof raw !== "string") continue;
    const value = raw.trim();
    if (!value) continue;
    // Shopify font_picker values look like `assistant_n4` or
    // `inter_n5` — family name + weight + variant. Strip the weight
    // suffix to get a usable Google Fonts family name. Best-effort:
    // some custom themes store the full CSS font-family string here
    // and we pass that through unchanged.
    const cleaned = value.replace(/_n\d.*$/i, "").replace(/_/g, " ");
    return titleCase(cleaned);
  }
  return "";
}

function pickColor(
  settings: Record<string, unknown>,
  candidates: string[],
): string {
  for (const key of candidates) {
    const raw = settings[key];
    if (typeof raw !== "string") continue;
    const value = raw.trim();
    if (!value) continue;
    // Accept hex (#RRGGBB or #RGB), rgb(...), or rgba(...). The
    // anchored regex on rgb/rgba is load-bearing: this value gets
    // injected into a <style> tag via dangerouslySetInnerHTML, so an
    // open-ended `^rgba?\(` would let a malformed theme value like
    // `rgb(0,0,0); } body { display: none; }` escape the CSS
    // declaration. Requiring `\)$` at the end keeps the value
    // contained inside the parens.
    if (/^#[0-9a-f]{3,8}$/i.test(value)) return value;
    if (/^rgba?\([^)]+\)$/i.test(value)) return value;
  }
  return "";
}

function titleCase(s: string): string {
  return s
    .split(/\s+/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(" ");
}
