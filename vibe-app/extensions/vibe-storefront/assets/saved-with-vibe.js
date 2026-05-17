/* D.C.8 — Saved-with-Vibe customer-account block.
 *
 * Fetches /apps/vibe/api/wishlist for the signed-in customer and
 * renders the response inline. The fetch is a relative path on the
 * storefront origin, so Shopify's App Proxy edge:
 *   1. Appends ?logged_in_customer_id=<n>&shop=<...>&timestamp=<...>
 *   2. HMAC-signs the full URL
 *   3. Forwards to the Vibe Remix backend
 * which then matches sessionId ("shopify:<n>") against the signed
 * logged_in_customer_id (IDOR guard in apps.vibe.api.wishlist.tsx).
 *
 * Block hydration is idempotent — the grid element carries a
 * data-vibe-hydrated attribute the moment we start fetching, so a
 * second pass (e.g. theme editor refresh) won't double-render.
 */

(function () {
  "use strict";

  function init() {
    var grids = document.querySelectorAll(
      "[data-vibe-saved-grid]:not([data-vibe-hydrated])",
    );
    for (var i = 0; i < grids.length; i++) {
      hydrateGrid(grids[i]);
    }
  }

  function hydrateGrid(grid) {
    grid.setAttribute("data-vibe-hydrated", "true");

    var customerId = (grid.getAttribute("data-customer-id") || "").trim();
    if (!customerId) {
      // Shouldn't happen — the Liquid template only renders the grid
      // when `customer` is truthy. Guard anyway so a misconfigured
      // theme doesn't fire an unauthenticated request.
      renderState(grid, "signed-out");
      return;
    }

    var maxItems = parseInt(grid.getAttribute("data-max-items") || "12", 10);
    if (!isFinite(maxItems) || maxItems < 1) maxItems = 12;

    var emptyCopy = grid.getAttribute("data-empty-copy") || "Nothing saved yet.";
    var emptyCtaLabel =
      grid.getAttribute("data-empty-cta-label") || "Chat with Vibe";
    var loadingCopy =
      grid.getAttribute("data-loading-copy") || "Loading your saved items…";
    var errorCopy =
      grid.getAttribute("data-error-copy") ||
      "Couldn't load your saved items right now — try again in a moment.";
    var currencySymbol = (
      grid.getAttribute("data-currency-symbol") || "₹"
    ).trim() || "₹";
    // Locale comes from Liquid (request.locale.iso_code → shop.locale →
    // en-IN fallback). Passing it explicitly to toLocaleString keeps
    // grouping separators consistent with what the storefront uses on
    // its own price renders — without it the browser default kicks in
    // and an Indian shopper viewing the page in a US-English browser
    // would see 100,000 instead of 1,00,000.
    var locale = (grid.getAttribute("data-locale") || "en-IN").trim() || "en-IN";

    renderState(grid, "loading", { loadingCopy: loadingCopy });

    // sessionId encodes the merged identity Vibe stores on the engine
    // side (D.S.3b). The proxy auto-appends logged_in_customer_id when
    // the customer is signed in via Shopify Customer Account, so we
    // don't append it manually — the loader's IDOR check reads from
    // the signed param, not the body of our request.
    var sessionId = "shopify:" + customerId;
    var url =
      "/apps/vibe/api/wishlist?sessionId=" + encodeURIComponent(sessionId);

    fetch(url, { credentials: "same-origin" })
      .then(function (resp) {
        return resp.json().then(function (body) {
          return { resp: resp, body: body };
        });
      })
      .then(function (out) {
        if (!out.resp.ok || !out.body || out.body.ok !== true) {
          renderState(grid, "error", { errorCopy: errorCopy });
          return;
        }
        var items = Array.isArray(out.body.items) ? out.body.items : [];
        if (items.length === 0) {
          renderState(grid, "empty", {
            emptyCopy: emptyCopy,
            emptyCtaLabel: emptyCtaLabel,
          });
          return;
        }
        renderItems(grid, items.slice(0, maxItems), currencySymbol, locale);
      })
      .catch(function () {
        renderState(grid, "error", { errorCopy: errorCopy });
      });
  }

  function renderItems(grid, items, currencySymbol, locale) {
    var html = "";
    for (var i = 0; i < items.length; i++) {
      var it = items[i] || {};
      var title = escapeHtml(it.title || "Saved item");
      var brand = it.brand ? escapeHtml(it.brand) : "";
      var image = it.image_url ? escapeHtml(it.image_url) : "";
      var price = formatPrice(it.price, currencySymbol, locale);
      var metaParts = [];
      if (brand) metaParts.push(brand);
      if (price) metaParts.push(price);
      var meta = metaParts.join(" · ");

      var imageBlock = image
        ? '<img src="' +
          image +
          '" alt="' +
          title +
          '" loading="lazy" decoding="async">'
        : '<div class="vibe-saved-placeholder">No preview</div>';

      html +=
        '<a class="vibe-saved-tile" href="/apps/vibe/style">' +
        '<div class="vibe-saved-image">' +
        imageBlock +
        "</div>" +
        '<div class="vibe-saved-body">' +
        '<p class="vibe-saved-title">' +
        title +
        "</p>" +
        (meta ? '<p class="vibe-saved-meta">' + meta + "</p>" : "") +
        "</div>" +
        "</a>";
    }
    grid.innerHTML = html;
  }

  function renderState(grid, state, opts) {
    opts = opts || {};
    var html = "";
    if (state === "loading") {
      html =
        '<div class="vibe-saved-state">' +
        escapeHtml(opts.loadingCopy || "") +
        "</div>";
    } else if (state === "empty") {
      html =
        '<div class="vibe-saved-state">' +
        '<p style="margin:0;">' +
        escapeHtml(opts.emptyCopy || "") +
        "</p>" +
        '<a class="vibe-saved-cta" href="/apps/vibe/style">' +
        escapeHtml(opts.emptyCtaLabel || "Chat with Vibe") +
        "</a>" +
        "</div>";
    } else if (state === "error") {
      html =
        '<div class="vibe-saved-state vibe-saved-error">' +
        escapeHtml(opts.errorCopy || "") +
        "</div>";
    } else if (state === "signed-out") {
      // Same calm card as the empty state; copy comes from the Liquid
      // template's signed-out branch, which is rendered server-side
      // before this script runs. We don't override it here.
      return;
    }
    grid.innerHTML = html;
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      }[c];
    });
  }

  // Price is a number on the engine side. Both the currency symbol
  // AND the locale come from the storefront's Liquid context so the
  // formatting matches the rest of the storefront on the same page:
  //   - data-currency-symbol → cart.currency.symbol / shop.currency
  //   - data-locale          → request.locale.iso_code / shop.locale
  // The explicit locale matters because Indian thousands grouping
  // (1,00,000) differs from Western (100,000) — letting the browser
  // pick the default would produce inconsistent renders for shoppers
  // viewing an Indian storefront from a non-en-IN browser locale.
  // Checkout owns the precise formatting + tax, so this is a glance-
  // value, not a transactional figure.
  function formatPrice(value, currencySymbol, locale) {
    if (value === null || value === undefined || value === "") return "";
    var n =
      typeof value === "number"
        ? value
        : parseFloat(String(value).replace(/[^0-9.]/g, ""));
    if (!isFinite(n) || n <= 0) return "";
    var rounded = Math.round(n);
    var formatted;
    try {
      formatted = rounded.toLocaleString(locale || "en-IN");
    } catch (_e) {
      // Bad locale tag (rare) → safe fallback to en-IN, which is the
      // currently-locked storefront default. Never throw out of price
      // formatting — the worst case is "₹1234" instead of "₹1,234".
      formatted = rounded.toLocaleString("en-IN");
    }
    return (currencySymbol || "₹") + formatted;
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  // Theme editor re-renders blocks via the `shopify:section:load`
  // event without a full page reload — re-run hydration so the new
  // DOM node picks up its data.
  document.addEventListener("shopify:section:load", init);
})();
