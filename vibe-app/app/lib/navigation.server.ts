// Inject + clean up Vibe's menu items in the merchant's main-menu.
//
// Adds two link items to the merchant's "Main menu" linklist:
//   - "Find your Vibe" → /apps/vibe/style
//   - "Your Vibes"     → /apps/vibe/looks
//
// Idempotent — checks for existing items by URL before inserting.
// On uninstall, removes items whose URL matches our Vibe paths.
//
// Required scope: `write_online_store_navigation` (implies read).
// Without it the menuUpdate mutation returns userErrors; we log +
// skip rather than fail loudly.

import { logWarn } from "./logger.server";

type AdminGraphqlClient = {
  graphql(query: string, options?: unknown): Promise<Response>;
};

type MenuItem = {
  id?: string;
  title: string;
  url: string;
  type: string;
  // Typed menu items (COLLECTION_LINK, PRODUCT_LINK, PAGE_LINK,
  // BLOG_LINK, ARTICLE_LINK, METAOBJECT, etc.) carry a resource
  // binding via resourceId. Without round-tripping it, the menuUpdate
  // mutation either rejects with "resourceId is required" userErrors
  // OR silently rewrites the items as broken links. Default Shopify
  // main menus have at least one typed item (Catalog → COLLECTION_LINK,
  // Contact → PAGE_LINK).
  resourceId?: string | null;
  tags?: string[] | null;
  items?: MenuItem[];
};

const VIBE_MENU_ITEMS: ReadonlyArray<{ title: string; url: string }> = [
  { title: "Find your Vibe", url: "/apps/vibe/style" },
  { title: "Your Vibes", url: "/apps/vibe/looks" },
];

// Derive from VIBE_MENU_ITEMS so a future addition stays in sync —
// and so the values are guaranteed lowercase to match
// urlAlreadyPresent's compare-on-lowercase contract.
const VIBE_PATH_MARKERS = VIBE_MENU_ITEMS.map((it) => it.url.toLowerCase());

type MenuListNode = {
  id?: string;
  handle?: string;
  title?: string;
  items?: MenuItem[];
};

type MenusIndexResult = {
  data?: {
    menus?: {
      edges?: Array<{ node?: { id?: string; handle?: string } }>;
    };
  };
};

type MenuByIdResult = {
  data?: {
    menu?: MenuListNode;
  };
};

type MenuUpdateResult = {
  data?: {
    menuUpdate?: {
      menu?: { id?: string };
      userErrors?: Array<{ field?: string[]; message?: string }>;
    };
  };
};

/**
 * Add the two Vibe menu items to the merchant's main-menu if they
 * aren't already there. Safe to call repeatedly — checks each item by
 * URL match before inserting.
 *
 * Returns `{added: number, alreadyPresent: number, skipped: string?}`
 * so the caller can log a meaningful summary. Failure (missing scope,
 * GraphQL error, no main-menu) returns skipped + a reason; doesn't
 * throw. The merchant home loader fires this best-effort.
 */
export async function ensureVibeMenuItems(admin: AdminGraphqlClient): Promise<{
  added: number;
  alreadyPresent: number;
  skipped?: string;
}> {
  const menu = await fetchMainMenu(admin);
  if (!menu || !menu.id) {
    return { added: 0, alreadyPresent: 0, skipped: "main-menu not found or missing id" };
  }
  const existingUrls = new Set(
    (menu.items ?? []).map((it) => (it.url || "").toLowerCase()),
  );
  const itemsToAdd = VIBE_MENU_ITEMS.filter(
    (it) => !urlAlreadyPresent(existingUrls, it.url),
  );
  if (itemsToAdd.length === 0) {
    return { added: 0, alreadyPresent: VIBE_MENU_ITEMS.length };
  }
  // menuUpdate replaces the items list wholesale. With the 2026-04
  // `MenuItemUpdateInput`, items keep their `id` to be updated in
  // place; items without `id` are treated as new creates. So we
  // round-trip existing items unchanged (with their ids) and append
  // new ones without an id.
  const merged: MenuItem[] = [
    ...(menu.items ?? []),
    ...itemsToAdd.map((it) => ({
      title: it.title,
      url: it.url,
      // `HTTP` is Shopify's MenuItemType for arbitrary external URLs
      // (App Proxy paths fall under this — they're served by Shopify
      // but proxied to our app). The old `FRONTEND_LINK` value was
      // removed in 2026-04.
      type: "HTTP",
    })),
  ];
  const ok = await writeMenuItems(admin, menu.id, menu.title || "Main menu", menu.handle || "main-menu", merged);
  if (!ok) {
    return {
      added: 0,
      alreadyPresent: existingUrls.size,
      skipped: "menuUpdate failed (check write_online_store_navigation scope)",
    };
  }
  return {
    added: itemsToAdd.length,
    alreadyPresent: VIBE_MENU_ITEMS.length - itemsToAdd.length,
  };
}

/**
 * Remove Vibe-owned items from the merchant's main-menu. Called from
 * the app/uninstalled webhook to leave the merchant's nav clean on
 * exit. Idempotent — no-op if neither item is present.
 */
export async function removeVibeMenuItems(admin: AdminGraphqlClient): Promise<{
  removed: number;
  skipped?: string;
}> {
  const menu = await fetchMainMenu(admin);
  if (!menu || !menu.id) {
    return { removed: 0, skipped: "main-menu not found or missing id" };
  }
  const items = menu.items ?? [];
  const filtered = items.filter(
    (it) => !urlAlreadyPresent(
      new Set(VIBE_PATH_MARKERS),
      (it.url || "").toLowerCase(),
    ),
  );
  if (filtered.length === items.length) {
    return { removed: 0 };
  }
  const ok = await writeMenuItems(
    admin,
    menu.id,
    menu.title || "Main menu",
    menu.handle || "main-menu",
    filtered,
  );
  if (!ok) {
    return { removed: 0, skipped: "menuUpdate failed during cleanup" };
  }
  return { removed: items.length - filtered.length };
}

async function fetchMainMenu(
  admin: AdminGraphqlClient,
): Promise<MenuListNode | null> {
  // The 2026-04 Admin API removed `menu(handle:)` — it only accepts
  // `menu(id: ID!)` now. Two-step: list menus (id + handle only) to
  // find main-menu's id, then fetch its full tree by id. This keeps
  // the heavy items{...} payload to one menu instead of pulling it
  // for every menu on the store.
  //
  // Three levels of `items` nesting is load-bearing: Shopify menus
  // can be three deep, and `writeMenuItems` round-trips the full
  // tree through `menuUpdate`, which replaces the items wholesale.
  // Fetching fewer levels here would silently delete deeper items
  // when the merchant's menu is updated.
  try {
    const listResp = await admin.graphql(
      `#graphql
      query VibeMenusIndex {
        menus(first: 50) {
          edges { node { id handle } }
        }
      }`,
    );
    if (!listResp.ok) {
      logWarn("vibe_navigation_menu_lookup_failed", {
        stage: "index",
        status: listResp.status,
      });
      return null;
    }
    const idx = (await listResp.json()) as MenusIndexResult;
    const id = idx.data?.menus?.edges?.find(
      (e) => e.node?.handle === "main-menu",
    )?.node?.id;
    if (!id) return null;

    const resp = await admin.graphql(
      `#graphql
      query VibeMainMenuDetail($id: ID!) {
        menu(id: $id) {
          id
          handle
          title
          items {
            id
            title
            url
            type
            resourceId
            tags
            items {
              id
              title
              url
              type
              resourceId
              tags
              items {
                id
                title
                url
                type
                resourceId
                tags
              }
            }
          }
        }
      }`,
      { variables: { id } },
    );
    if (!resp.ok) {
      logWarn("vibe_navigation_menu_lookup_failed", {
        stage: "detail",
        status: resp.status,
      });
      return null;
    }
    const gql = (await resp.json()) as MenuByIdResult;
    return gql.data?.menu ?? null;
  } catch (err) {
    logWarn("vibe_navigation_menu_lookup_failed", {
      stage: "exception",
      error: err instanceof Error ? err.message : String(err),
    });
    return null;
  }
}

async function writeMenuItems(
  admin: AdminGraphqlClient,
  menuId: string,
  title: string,
  handle: string,
  items: MenuItem[],
): Promise<boolean> {
  try {
    const resp = await admin.graphql(
      `#graphql
      mutation VibeMenuUpdate($id: ID!, $title: String!, $handle: String!, $items: [MenuItemUpdateInput!]!) {
        menuUpdate(id: $id, title: $title, handle: $handle, items: $items) {
          menu { id }
          userErrors { field message }
        }
      }`,
      {
        variables: {
          id: menuId,
          title,
          handle,
          items: items.map(toMenuItemInput),
        },
      },
    );
    if (!resp.ok) {
      logWarn("vibe_navigation_menu_update_failed", {
        stage: "http",
        status: resp.status,
      });
      return false;
    }
    const gql = (await resp.json()) as MenuUpdateResult;
    const errs = gql.data?.menuUpdate?.userErrors ?? [];
    if (errs.length > 0) {
      // Surface user-errors verbatim — usually "resourceId is
      // required for X" or scope/permission failures. Without this
      // the caller just sees skipped=true with no detail.
      logWarn("vibe_navigation_menu_update_failed", {
        stage: "user_errors",
        user_errors: errs,
      });
      return false;
    }
    return true;
  } catch (err) {
    logWarn("vibe_navigation_menu_update_failed", {
      stage: "exception",
      error: err instanceof Error ? err.message : String(err),
    });
    return false;
  }
}

function urlAlreadyPresent(urls: Set<string>, candidate: string): boolean {
  const lower = candidate.toLowerCase();
  // Tolerant match — Shopify normalises some menu URLs (adds host,
  // trims trailing slash); compare on the path suffix so a stored
  // `https://thesigmavibe.shop/apps/vibe/style` matches a freshly-
  // inserted `/apps/vibe/style`.
  for (const u of urls) {
    if (u === lower) return true;
    if (u.endsWith(lower) || lower.endsWith(u)) return true;
  }
  return false;
}

function toMenuItemInput(item: MenuItem): Record<string, unknown> {
  // Build a MenuItemUpdateInput. `id` is required to update an
  // existing item in place; new items omit it and get created. Items
  // present on the menu but absent from this payload are deleted by
  // Shopify, so we round-trip every existing item with its id.
  //
  // resourceId is mandatory for typed links (COLLECTION_LINK /
  // PRODUCT_LINK / PAGE_LINK / etc.) and forbidden for HTTP. We pass
  // it whenever non-null so the API validates per-type rather than
  // us hard-coding the allow-list.
  //
  // Explicit FRONTEND_LINK → HTTP rewrite: stores fetched before the
  // 2026-04 cutover (or with cached values) may still surface the
  // removed enum value on existing items. menuUpdate would reject
  // the whole mutation if we passed it through.
  const rawType = item.type;
  const type = !rawType || rawType === "FRONTEND_LINK" ? "HTTP" : rawType;
  const input: Record<string, unknown> = {
    title: item.title,
    type,
    items: (item.items ?? []).map(toMenuItemInput),
  };
  if (item.id) input.id = item.id;
  if (item.url) input.url = item.url;
  if (item.resourceId) input.resourceId = item.resourceId;
  if (item.tags && item.tags.length > 0) input.tags = item.tags;
  return input;
}
