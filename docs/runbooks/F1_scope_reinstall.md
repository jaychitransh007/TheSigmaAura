# F.1 — Scope expansion + reinstall

Runbook for what happens when [vibe-app/shopify.app.vibe.toml](../../vibe-app/shopify.app.vibe.toml) `[access_scopes].scopes` changes and existing installs need to re-grant.

## Current scope set (2026-05-17)

| Scope | Powers |
|---|---|
| `read_products` | F.2 catalog sync — Vibe recommends from the merchant's actual Shopify catalog |
| `read_inventory` | F.4 stock-aware retrieval — no recommendations for OOS pieces |
| `read_orders` | G.1 order webhooks — kicks off purchase attribution |
| `read_customers` | G.2 link orders to engine `external_user_id` |
| `read_themes` | D.M.3 verify the Style-with-Vibe theme app extension block is in the active theme |
| `write_metafields` | G.2 tag Vibe-attributed orders with the influencing outfit's id |

`write_products` (the Shopify CLI bootstrap template's default) was dropped — Vibe never writes to products.

## Operator procedure when scopes change

### 1. Update the toml

Edit `[access_scopes].scopes` in [vibe-app/shopify.app.vibe.toml](../../vibe-app/shopify.app.vibe.toml). Comma-separated, no spaces around commas. Keep the in-file comment block in sync with the new scope list — that comment is the source-of-truth doc for *why* each scope is requested.

If the change adds a scope, update [vibe-app/app/routes/app._index.tsx](../../vibe-app/app/routes/app._index.tsx) `SCOPE_DESCRIPTIONS` with a plain-English label + reason. Without an entry, the welcome-screen Permissions card silently drops the new row.

### 2. Deploy

```bash
cd vibe-app
shopify app deploy
```

Pushes the new scope spec to Partner Dashboard. **No data is touched.** Existing installs continue running on their previously-granted scope set until a re-grant fires.

### 3. Re-grant for existing installs

There are two paths Shopify supports:

**(a) Merchant-initiated.** Next time the merchant opens the embedded app in admin, Shopify detects the scope drift and shows a banner asking them to re-authorize. They click → consent screen with the new scope list → app reloads with the expanded grant.

**(b) Programmatic re-auth flow.** Force the re-grant from inside the app via `app/auth/login?shop=<domain>`. Useful when you want to surface a "Permissions update available" CTA in admin without waiting for the merchant's next visit. Not currently wired — add when D.M.2 ships.

For the dev store (`vibe-test-nmt8wy3q.myshopify.com`) the merchant-initiated path (a) is sufficient; you'll see the banner the first time you reopen Vibe in admin.

### 4. Verify

After re-grant:
1. Open the Vibe admin app for the affected shop.
2. Check the **Permissions** card on the welcome screen — every new scope should appear with its label + reason.
3. Quick smoke for the most load-bearing new capability the scope unblocks (e.g. after `read_products` lands, hit the Admin GraphQL `products` query via Shopify GraphiQL with your session token to confirm reads succeed).

## What goes wrong, and how to recover

| Symptom | Cause | Fix |
|---|---|---|
| Banner never appears | Toml was edited but `shopify app deploy` wasn't run | Run the deploy. Banner shows up within minutes of Partner Dashboard receiving the spec. |
| Banner appears but consent screen shows fewer scopes than expected | App-version mismatch in Partner Dashboard | Confirm the deploy succeeded; inspect the latest app version's scope list in Partner Dashboard. |
| Re-grant succeeds but Vibe still 403s on the new API | `session.scope` in the Prisma session row is stale | Uninstall + reinstall on the dev store (production: use `unauthenticated.admin(shop)` to invalidate the session token). |
| Permissions card shows raw scope strings instead of labels | `SCOPE_DESCRIPTIONS` in `app._index.tsx` is missing the entry | Add the label + reason. PR-and-deploy. |

## Notes

- Adding a scope is **always backward-compatible**. Existing functionality keeps working under the prior grant; the new feature gated on the new scope just no-ops until re-grant.
- **Removing** a scope (rare) is harder — Shopify doesn't auto-revoke. The merchant has to uninstall + reinstall. Document the impact loudly if it ever happens.
- Shopify's consent screen surfaces scope strings, not our plain-English descriptions. The descriptions in `SCOPE_DESCRIPTIONS` only appear on the post-install welcome screen. Until D.M.2 ships a dedicated permissions panel, that's the closest we have to in-app transparency.
