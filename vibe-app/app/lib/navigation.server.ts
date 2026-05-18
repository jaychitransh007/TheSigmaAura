// Inject + clean up Vibe's menu items in the merchant's main-menu
// (PR #481).
//
// Adds two link items to the merchant's "Main menu" linklist:
//   - "Find your Vibe" → /apps/vibe/style
//   - "Your Vibes"     → /apps/vibe/looks
//
// Idempotent — checks for existing items by URL before inserting.
// On uninstall, removes items whose URL matches our Vibe paths.
//
// Required scope: `write_navigation` (added in PR #481, forces a
// re-grant on the dev store + production stores). Without it the
// menuUpdate mutation returns userErrors; we log + skip rather than
// fail loudly.

type AdminGraphqlClient = {
  graphql(query: string, options?: unknown): Promise<Response>;
};

type MenuItem = {
  id?: string;
  title: string;
  url: string;
  type: string;
  items?: MenuItem[];
};

const VIBE_MENU_ITEMS: ReadonlyArray<{ title: string; url: string }> = [
  { title: "Find your Vibe", url: "/apps/vibe/style" },
  { title: "Your Vibes", url: "/apps/vibe/looks" },
];

// URLs (lowercased) that identify Vibe-owned menu items. Used by
// removeVibeMenuItems to recognise and prune them on uninstall.
const VIBE_PATH_MARKERS = ["/apps/vibe/style", "/apps/vibe/looks"];

type MenuQueryResult = {
  data?: {
    menu?: {
      id?: string;
      handle?: string;
      title?: string;
      items?: MenuItem[];
    };
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
  if (!menu) {
    return { added: 0, alreadyPresent: 0, skipped: "main-menu not found" };
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
  // menuUpdate replaces the items list wholesale, so we merge existing
  // + new and write back. menuUpdate also expects MenuItemCreateInput
  // (no `id`), so we strip the id field from existing items —
  // Shopify will re-create them under new ids but the URLs + order
  // round-trip cleanly.
  const merged: MenuItem[] = [
    ...(menu.items ?? []).map(stripMenuItemId),
    ...itemsToAdd.map((it) => ({
      title: it.title,
      url: it.url,
      type: "FRONTEND_LINK",
    })),
  ];
  const ok = await writeMenuItems(admin, menu.id!, menu.title || "Main menu", menu.handle || "main-menu", merged);
  if (!ok) {
    return {
      added: 0,
      alreadyPresent: existingUrls.size,
      skipped: "menuUpdate failed (check write_navigation scope)",
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
  if (!menu) return { removed: 0, skipped: "main-menu not found" };
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
    menu.id!,
    menu.title || "Main menu",
    menu.handle || "main-menu",
    filtered.map(stripMenuItemId),
  );
  if (!ok) {
    return { removed: 0, skipped: "menuUpdate failed during cleanup" };
  }
  return { removed: items.length - filtered.length };
}

async function fetchMainMenu(
  admin: AdminGraphqlClient,
): Promise<{ id?: string; handle?: string; title?: string; items?: MenuItem[] } | null> {
  try {
    const resp = await admin.graphql(
      `#graphql
      query VibeMainMenu {
        menu(handle: "main-menu") {
          id
          handle
          title
          items {
            id
            title
            url
            type
            items { id title url type }
          }
        }
      }`,
    );
    if (!resp.ok) return null;
    const gql = (await resp.json()) as MenuQueryResult;
    return gql.data?.menu ?? null;
  } catch {
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
      mutation VibeMenuUpdate($id: ID!, $title: String!, $handle: String!, $items: [MenuItemCreateInput!]!) {
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
    if (!resp.ok) return false;
    const gql = (await resp.json()) as MenuUpdateResult;
    const errs = gql.data?.menuUpdate?.userErrors ?? [];
    return errs.length === 0;
  } catch {
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

function stripMenuItemId(item: MenuItem): MenuItem {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { id: _id, items, ...rest } = item;
  return {
    ...rest,
    items: items?.map(stripMenuItemId),
  };
}

function toMenuItemInput(item: MenuItem): Record<string, unknown> {
  return {
    title: item.title,
    url: item.url,
    type: item.type || "FRONTEND_LINK",
    items: (item.items ?? []).map(toMenuItemInput),
  };
}
