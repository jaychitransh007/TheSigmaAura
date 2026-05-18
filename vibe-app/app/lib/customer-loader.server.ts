// Shared helper for the customer-facing Vibe page loaders.
//
// Every Vibe page that renders a header needs the tenant's
// theme_overrides (font + primary color + shop name + main menu).
// Repeating the shop-from-URL lookup + engine call inside each
// loader is noise — this helper centralises it.
//
// Best-effort: any failure returns `null` so callers can fall back
// to Confident Luxe defaults. Doesn't 500 the page.

import {
  lookupOrCreateTenant,
  type TenantThemeOverrides,
} from "./engine.server";

export async function loadTenantThemeOverrides(
  request: Request,
): Promise<TenantThemeOverrides | null> {
  const url = new URL(request.url);
  const shopDomain = url.searchParams.get("shop")?.trim() ?? "";
  if (!shopDomain) return null;
  try {
    const tenant = await lookupOrCreateTenant({ shopDomain });
    return tenant.theme_overrides ?? null;
  } catch {
    // Engine wobble — fall back to Confident Luxe defaults.
    return null;
  }
}
