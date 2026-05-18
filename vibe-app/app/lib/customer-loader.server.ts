// Shared helper for the customer-facing Vibe page loaders.
//
// Every Vibe page that renders a header needs:
//   - the tenant's theme_overrides (font + primary color + shop
//     name + main menu) so MerchantHeader can replicate the
//     merchant's storefront
//   - the App Proxy's signed logged_in_customer_id so the header
//     can decide whether to show "Sign in" or "Account"
//
// Best-effort on the engine lookup: any failure returns null so the
// page falls back to Confident Luxe defaults.

import {
  lookupOrCreateTenant,
  type TenantThemeOverrides,
} from "./engine.server";

export type CustomerHeaderData = {
  themeOverrides: TenantThemeOverrides | null;
  /** Truthy iff the App Proxy carried a `logged_in_customer_id` —
   *  HMAC-validated by Shopify before the request hits Vercel. */
  isAuthenticated: boolean;
};

export async function loadCustomerHeaderData(
  request: Request,
): Promise<CustomerHeaderData> {
  const url = new URL(request.url);
  const shopDomain = url.searchParams.get("shop")?.trim() ?? "";
  const loggedInCustomerId =
    url.searchParams.get("logged_in_customer_id")?.trim() ?? "";
  const isAuthenticated = loggedInCustomerId.length > 0;
  if (!shopDomain) {
    return { themeOverrides: null, isAuthenticated };
  }
  try {
    const tenant = await lookupOrCreateTenant({ shopDomain });
    return { themeOverrides: tenant.theme_overrides ?? null, isAuthenticated };
  } catch {
    return { themeOverrides: null, isAuthenticated };
  }
}

// Back-compat shim — earlier loaders only pulled themeOverrides.
// New code should prefer loadCustomerHeaderData.
export async function loadTenantThemeOverrides(
  request: Request,
): Promise<TenantThemeOverrides | null> {
  const { themeOverrides } = await loadCustomerHeaderData(request);
  return themeOverrides;
}
