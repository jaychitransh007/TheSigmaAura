// Rich outfit card — 3-column layout: thumbnails | hero | detail panel.
//
// Reference: legacy platform_core/ui.py PDP card.
//   - Per-item size chips (Record<garment_id, Size>): customers can be
//     S in tops and M in bottoms; one global size would silently force
//     them into the wrong variant on at least one item. Chips are
//     ALWAYS clickable — variant-id availability is a checkout-time
//     concern (the friendly error fires there), not a chip-state one.
//   - Buy Outfit (outfit mode): adds every shoppable item at its picked
//     size to the Shopify cart, navigates to /cart so the customer
//     reviews the bundle before paying.
//   - Garment mode now has THREE CTAs:
//       Add to Cart — adds the item, stays on chat (flashes "Added ✓")
//       Buy Now     — adds the item, navigates straight to /checkout
//       Heart       — like / save
//     Wardrobe items render a static "From your wardrobe" pill instead.
//   - Variant-id gaps (catalog mapping B.8 hasn't run) surface as a
//     friendly inline error from CartUnavailableError, never silent
//     failures.

import { useCallback, useEffect, useRef, useState } from "react";

import type { Outfit, OutfitItem } from "../../lib/engine.server";
import {
  CartUnavailableError,
  addToCart,
  type CartNavigation,
} from "../../lib/cart.client";
import { getOrCreateClientSessionId } from "../../lib/session.client";

// Per-garment virtual try-on state slice (Phase V.2). Keyed by
// garment_id so switching garments inside the same outfit card
// doesn't bleed a previous render into a different SKU. `loading`
// gates the button + shows a spinner overlay on the hero; `dataUrl`
// replaces the catalog image once Gemini returns; `missingPerson`
// surfaces a friendly nudge when the engine 400s with
// `missing_person_image` (customer hasn't onboarded photos yet).
type TryonState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ready"; dataUrl: string }
  | { kind: "missing_person"; message: string }
  | { kind: "error"; message: string };

const SIZES = ["XS", "S", "M", "L", "XL"] as const;
type Size = (typeof SIZES)[number];

type Mode =
  | { kind: "outfit" }
  | { kind: "garment"; item: OutfitItem };

export function OutfitCard({
  outfit,
  onHide,
  hasBodyPhoto = false,
  onRequestPhotosCard,
}: {
  outfit: Outfit;
  onHide?: () => void;
  /** Phase W — whether the customer has a full_body photo on file
   *  with the engine. Drives W.5 auto-fire (card auto-renders the
   *  try-on on mount when true) and gates the missing-person path
   *  away from the W.6 photo-card fallback (no point asking for an
   *  upload if the engine already has one). */
  hasBodyPhoto?: boolean;
  /** Phase W — invoked when a try-on attempt 400s with
   *  missing_person_image (or the customer clicks Try-On without a
   *  body photo on file). Parent emits an inline photos onboarding
   *  card to the conversation so the customer can upload without
   *  leaving the chat — supersedes the V.2 inline error nudge. */
  onRequestPhotosCard?: () => void;
}) {
  // Default to outfit-level mode for multi-item outfits, garment mode
  // for single-item outfits. Phase W's seed-product entry path
  // emits a synthetic 1-item Outfit (the storefront product the
  // customer landed on); the "Buy Outfit" framing doesn't make
  // sense for a single item, so we open directly in garment mode
  // and the customer sees Add to Cart / Buy Now / Try On.
  // Multi-item turns still default to outfit mode so the
  // outfit-level reasoning + cohesive Buy Outfit CTA show first.
  const [mode, setMode] = useState<Mode>(() =>
    outfit.items.length === 1
      ? { kind: "garment", item: outfit.items[0] }
      : { kind: "outfit" },
  );
  const [liked, setLiked] = useState(false);
  // Per-item size selection. Keyed by garment_id because customers
  // need to pick a size for each Shopify SKU independently.
  const [selectedSizes, setSelectedSizes] = useState<Record<string, Size>>({});
  const [cartError, setCartError] = useState<string | null>(null);
  const [cartBusy, setCartBusy] = useState<
    null | "outfit" | "add-to-cart" | "buy-now"
  >(null);
  // Flash for the stay-on-page Add to Cart CTA so the customer has
  // visual confirmation without us drawing a toast component.
  const [addedFlash, setAddedFlash] = useState(false);
  // Per-garment virtual try-on state (Phase V.2). Each garment_id
  // maps to its own TryonState — the customer can swipe between
  // garments without losing previously-rendered results, and a
  // re-click within the same session reuses the cached dataUrl
  // instead of paying for another Gemini render.
  const [garmentTryon, setGarmentTryon] = useState<Record<string, TryonState>>(
    {},
  );
  // Outfit-level virtual try-on state. The engine auto-renders this
  // at outfit-generation time, but the auto-render falls through if
  // the flag was off, the person photo arrived late, or Gemini timed
  // out. This state powers the "Virtual Try On" button when the
  // customer is in outfit mode — click → /apps/vibe/api/tryon-outfit
  // → swap the hero to the rendered composite.
  const [outfitTryonState, setOutfitTryonState] = useState<TryonState>({
    kind: "idle",
  });

  const tryonImage = outfit.tryon_image_url ?? null;
  const isOutfitMode = mode.kind === "outfit";

  // In garment mode, prefer a rendered single-garment try-on (if the
  // customer hit "Virtual Try On" earlier on this card) over the
  // catalog product image. The fallback chain keeps the card visually
  // populated even when nothing has been rendered yet.
  const garmentTryonState =
    mode.kind === "garment"
      ? garmentTryon[mode.item.garment_id] ?? { kind: "idle" }
      : { kind: "idle" as const };
  const garmentHeroOverride =
    garmentTryonState.kind === "ready" ? garmentTryonState.dataUrl : null;
  // Outfit hero precedence: a freshly-rendered outfit-level try-on
  // (from clicking the button on this session) > the engine's
  // pre-rendered try-on (from outfit-generation time) > the first
  // item's catalog image as a last-resort placeholder.
  const outfitHeroOverride =
    outfitTryonState.kind === "ready" ? outfitTryonState.dataUrl : null;

  const heroImage = isOutfitMode
    ? outfitHeroOverride ?? tryonImage ?? outfit.items[0]?.image_url ?? null
    : garmentHeroOverride ?? mode.item.image_url ?? null;
  // Loading overlay should follow whichever mode the customer is in.
  const isTryonLoading = isOutfitMode
    ? outfitTryonState.kind === "loading"
    : garmentTryonState.kind === "loading";
  const activeTryonState: TryonState = isOutfitMode
    ? outfitTryonState
    : garmentTryonState;

  const pickSize = (garmentId: string, size: Size) => {
    // Picking a size clears any prior cart error so the customer
    // sees a clean slate when they retry.
    setCartError(null);
    setSelectedSizes((prev) => ({ ...prev, [garmentId]: size }));
  };

  // Auto-clear the "Added ✓" flash after a moment.
  useEffect(() => {
    if (!addedFlash) return;
    const id = window.setTimeout(() => setAddedFlash(false), 2000);
    return () => window.clearTimeout(id);
  }, [addedFlash]);

  // Buy availability. Gated on SIZE PICKED only — variant-id
  // availability is checkout-time, not button-state. If a variant id
  // is missing at click time, the cart helper throws
  // CartUnavailableError and we surface the message inline.
  //
  // Wardrobe items (price == null) are excluded — the customer
  // already owns them, no cart write needed.
  const shoppableItems = outfit.items.filter((it) => !isWardrobe(it));
  const canBuyOutfit =
    isOutfitMode &&
    shoppableItems.length > 0 &&
    shoppableItems.every((item) => selectedSizes[item.garment_id] != null);
  const garmentSelected =
    mode.kind === "garment" ? selectedSizes[mode.item.garment_id] : undefined;
  const canBuyGarment =
    mode.kind === "garment" && garmentSelected !== undefined;

  // Pull the variant ids for the picked sizes at click time. Missing
  // ids → the helper raises CartUnavailableError with a friendly
  // message; UI doesn't have to know about catalog-mapping state.
  function variantIdsForOutfit(): { variantId: string }[] {
    if (mode.kind !== "outfit") return [];
    return shoppableItems
      .map((it) => {
        const size = selectedSizes[it.garment_id];
        const variantId = size ? it.shopify_variant_ids?.[size] : undefined;
        return variantId ? { variantId } : null;
      })
      .filter((x): x is { variantId: string } => x !== null);
  }

  function variantIdForCurrentGarment(): string | undefined {
    if (mode.kind !== "garment") return undefined;
    const size = selectedSizes[mode.item.garment_id];
    return size ? mode.item.shopify_variant_ids?.[size] : undefined;
  }

  async function runCart(args: {
    label: typeof cartBusy;
    items: { variantId: string }[];
    navigate: CartNavigation;
    /** Show "Added ✓" flash on success when we stay on the page. */
    flashOnSuccess?: boolean;
  }) {
    setCartError(null);
    setCartBusy(args.label);
    try {
      await addToCart(args.items, { navigate: args.navigate });
      if (args.flashOnSuccess) setAddedFlash(true);
    } catch (e) {
      if (e instanceof CartUnavailableError) {
        setCartError(e.message);
      } else {
        setCartError(
          e instanceof Error
            ? e.message
            : "Couldn't add to cart — try again in a moment.",
        );
      }
    } finally {
      setCartBusy(null);
    }
  }

  const handleBuyOutfit = () =>
    runCart({
      label: "outfit",
      items: variantIdsForOutfit(),
      navigate: "cart",
    });

  const handleAddToCart = () => {
    const variantId = variantIdForCurrentGarment();
    runCart({
      label: "add-to-cart",
      items: variantId ? [{ variantId }] : [],
      navigate: "none",
      flashOnSuccess: true,
    });
  };

  const handleBuyNow = () => {
    const variantId = variantIdForCurrentGarment();
    runCart({
      label: "buy-now",
      items: variantId ? [{ variantId }] : [],
      navigate: "checkout",
    });
  };

  // Phase V.2 — single-garment "Virtual Try On" click handler.
  // Fires `/apps/vibe/api/tryon` with the current garment's image
  // URL; the engine pulls the customer's stored full-body photo
  // (uploaded via the in-chat onboarding photos card) and runs
  // Gemini Flash Image. On success the rendered data URL takes
  // over the garment hero image. Missing-person-image returns a
  // friendly inline nudge instead of a generic error.
  const handleTryOn = useCallback(async () => {
    if (mode.kind !== "garment") return;
    const item = mode.item;
    if (isWardrobe(item)) return;
    if (!item.image_url) return;
    const sessionId = getOrCreateClientSessionId();
    // Optimistic loading state — hero overlay swaps to a spinner
    // while we wait on Gemini (~5–15s).
    setGarmentTryon((prev) => ({
      ...prev,
      [item.garment_id]: { kind: "loading" },
    }));
    const form = new FormData();
    form.set("sessionId", sessionId);
    form.set("productImageUrl", item.image_url);
    let resp: Response;
    try {
      resp = await fetch("/apps/vibe/api/tryon", {
        method: "POST",
        body: form,
      });
    } catch (err) {
      setGarmentTryon((prev) => ({
        ...prev,
        [item.garment_id]: {
          kind: "error",
          message:
            err instanceof Error
              ? err.message
              : "Couldn't reach the try-on service.",
        },
      }));
      return;
    }
    let body: {
      ok?: boolean;
      dataUrl?: string;
      error?: string;
      reasonCode?: string;
    };
    try {
      body = (await resp.json()) as typeof body;
    } catch {
      setGarmentTryon((prev) => ({
        ...prev,
        [item.garment_id]: {
          kind: "error",
          message: `Try-on failed (HTTP ${resp.status}).`,
        },
      }));
      return;
    }
    if (!resp.ok || !body.ok) {
      const message = body.error || `Try-on failed (HTTP ${resp.status}).`;
      // Engine surfaces `missing_person_image` when the customer
      // hasn't onboarded with a full-body photo yet — flag it
      // separately so the UI can point them at the photos card
      // instead of showing a generic error.
      const isMissingPerson =
        body.reasonCode === "missing_person_image" ||
        message.toLowerCase().includes("full-body");
      setGarmentTryon((prev) => ({
        ...prev,
        [item.garment_id]: isMissingPerson
          ? {
              kind: "missing_person",
              message:
                "Upload your full-body photo first — use the Photos card to share two photos, then come back and try this on.",
            }
          : { kind: "error", message },
      }));
      // Phase W.6 — surface the photos onboarding card inline so the
      // customer can upload without leaving the chat. Parent emits
      // the card into the message stream; the inline note above
      // stays as a fallback for the brief window before the card
      // mounts.
      if (isMissingPerson) {
        onRequestPhotosCard?.();
      }
      return;
    }
    setGarmentTryon((prev) => ({
      ...prev,
      [item.garment_id]: { kind: "ready", dataUrl: body.dataUrl! },
    }));
  }, [mode, onRequestPhotosCard]);

  // Phase V.2 — outfit-mode "Virtual Try On" click handler. Same
  // shape as `handleTryOn` but fires the multi-garment endpoint
  // (`/apps/vibe/api/tryon-outfit`) and stashes the result in the
  // shared `outfitTryonState` so the outfit hero swaps to the
  // rendered composite.
  const handleTryOnOutfit = useCallback(async () => {
    if (mode.kind !== "outfit") return;
    // Build the garment list. Skip wardrobe items — they're already
    // the customer's pieces (the engine renders them differently
    // during turn output) and the tryon endpoint can't reliably
    // fetch a wardrobe-local file from outside the engine VM. Skip
    // items without a usable URL too.
    const garments = outfit.items
      .filter((item) => !isWardrobe(item) && Boolean(item.image_url))
      .map((item) => ({
        role: (item as { role?: string }).role || "garment",
        image_url: item.image_url as string,
      }));
    if (garments.length === 0) {
      setOutfitTryonState({
        kind: "error",
        message: "No shoppable items to render in this outfit.",
      });
      return;
    }
    const sessionId = getOrCreateClientSessionId();
    setOutfitTryonState({ kind: "loading" });
    const form = new FormData();
    form.set("sessionId", sessionId);
    form.set("garments", JSON.stringify(garments));
    let resp: Response;
    try {
      resp = await fetch("/apps/vibe/api/tryon-outfit", {
        method: "POST",
        body: form,
      });
    } catch (err) {
      setOutfitTryonState({
        kind: "error",
        message:
          err instanceof Error
            ? err.message
            : "Couldn't reach the try-on service.",
      });
      return;
    }
    let body: {
      ok?: boolean;
      dataUrl?: string;
      error?: string;
      reasonCode?: string;
    };
    try {
      body = (await resp.json()) as typeof body;
    } catch {
      setOutfitTryonState({
        kind: "error",
        message: `Try-on failed (HTTP ${resp.status}).`,
      });
      return;
    }
    if (!resp.ok || !body.ok) {
      const message = body.error || `Try-on failed (HTTP ${resp.status}).`;
      const isMissingPerson =
        body.reasonCode === "missing_person_image" ||
        message.toLowerCase().includes("full-body");
      setOutfitTryonState(
        isMissingPerson
          ? {
              kind: "missing_person",
              message:
                "Upload your full-body photo first — use the Photos card to share two photos, then come back and try this on.",
            }
          : { kind: "error", message },
      );
      // Phase W.6 — same photo-card fallback as the garment path.
      if (isMissingPerson) {
        onRequestPhotosCard?.();
      }
      return;
    }
    setOutfitTryonState({ kind: "ready", dataUrl: body.dataUrl! });
  }, [mode.kind, outfit.items, onRequestPhotosCard]);

  // Phase W.5 — auto-fire the try-on render when the customer has a
  // body photo on file but the current card view doesn't already
  // show a rendered try-on. The customer's expectation, per the
  // Phase W flow ("if user image exists, the image should be served
  // with virtual try-on only"), is that every PDP card defaults to
  // the rendered hero — not the catalog stock photo.
  //
  // Gates:
  //   - `hasBodyPhoto`. Without a body photo there's nothing to
  //     render against; the customer needs to upload first (W.6).
  //   - Mode-aware:
  //       outfit mode → fire when neither the engine's pre-render
  //                    (outfit.tryon_image_url) nor a client-rendered
  //                    state is in place. The engine auto-renders at
  //                    turn-generation time; this auto-fire covers
  //                    the cases where it didn't (synthetic
  //                    seed-product outfit, engine flag off, etc.).
  //       garment mode → fire when no per-garment try-on is on file
  //                    yet. The engine never pre-renders single-
  //                    garment views, so this auto-fire is the only
  //                    path that paints a try-on hero in garment
  //                    mode.
  //   - State ≠ loading/ready. The handler is reused from the
  //     manual-click path; re-entering loading would step on it.
  //   - Per-card auto-fire ref so React StrictMode's double-effect
  //     pass doesn't fire two Gemini calls back-to-back.
  const autoFiredOutfitRef = useRef<boolean>(false);
  const autoFiredGarmentRef = useRef<Set<string>>(new Set());
  useEffect(() => {
    if (!hasBodyPhoto) return;
    if (mode.kind === "outfit") {
      if (autoFiredOutfitRef.current) return;
      if (outfit.tryon_image_url) return;
      if (outfitTryonState.kind !== "idle") return;
      // No try-on on file and we haven't already auto-fired.
      autoFiredOutfitRef.current = true;
      void handleTryOnOutfit();
      return;
    }
    // garment mode
    const item = mode.item;
    if (isWardrobe(item)) return;
    if (!item.image_url) return;
    if (autoFiredGarmentRef.current.has(item.garment_id)) return;
    if (garmentTryonState.kind !== "idle") return;
    autoFiredGarmentRef.current.add(item.garment_id);
    void handleTryOn();
  }, [
    hasBodyPhoto,
    mode,
    outfit.tryon_image_url,
    outfitTryonState.kind,
    garmentTryonState.kind,
    handleTryOn,
    handleTryOnOutfit,
  ]);

  return (
    <div className="conv-card" data-outfit-id={outfit.outfit_id}>
      <div className="conv-card-header">
        <h3 className="conv-card-title">
          {isOutfitMode ? outfit.name ?? "Your look" : mode.item.title}
        </h3>
        {onHide && (
          <button
            type="button"
            className="conv-card-hide"
            onClick={onHide}
            aria-label="Hide this outfit"
            title="Hide"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path
                d="M4 4l8 8M12 4l-8 8"
                stroke="currentColor"
                strokeWidth="1.75"
                strokeLinecap="round"
              />
            </svg>
          </button>
        )}
      </div>

      <div className="conv-card-body">
        <ThumbnailRail
          outfit={outfit}
          tryonImage={tryonImage}
          mode={mode}
          onSelect={setMode}
        />

        <div className="conv-hero">
          {heroImage ? (
            <img src={heroImage} alt="" />
          ) : (
            <div className="conv-hero-empty">
              {isOutfitMode ? "Try-on rendering…" : "No image"}
            </div>
          )}
          {/* V.2 — spinner overlay while a try-on renders. Sits on
              top of the catalog image until Gemini returns the
              rendered data URL (which then replaces the catalog
              image via the heroImage fallback chain above). One
              overlay for both modes: outfit-level multi-garment
              render and single-garment render. */}
          {isTryonLoading && (
            <div className="conv-hero-tryon-overlay">
              <span className="conv-hero-tryon-spinner" aria-hidden="true" />
              <span>Rendering try-on…</span>
            </div>
          )}
        </div>

        <div className="conv-detail">
          {isOutfitMode ? (
            <OutfitDetail
              outfit={outfit}
              selectedSizes={selectedSizes}
              onPickSize={pickSize}
            />
          ) : (
            <>
              <GarmentDetail item={mode.item} />
              {!isWardrobe(mode.item) && (
                <SizeChips
                  selected={selectedSizes[mode.item.garment_id] ?? null}
                  onSelect={(size) => pickSize(mode.item.garment_id, size)}
                />
              )}
            </>
          )}

          {cartError && <div className="conv-cart-error">{cartError}</div>}

          {/* V.2 — Virtual Try On button + status row. Sits above
              the Buy / Add to Cart CTAs. Outfit mode triggers the
              multi-garment render; garment mode triggers the
              single-garment render. Hidden for wardrobe garments —
              they don't have a Shopify product image URL the engine
              can render against. Hidden in outfit mode if every item
              is from the wardrobe (nothing the engine can render). */}
          {(() => {
            if (mode.kind === "garment") return !isWardrobe(mode.item);
            return outfit.items.some(
              (item) => !isWardrobe(item) && Boolean(item.image_url),
            );
          })() && (
            <div className="conv-tryon-row">
              <button
                type="button"
                className="conv-cta conv-cta--secondary"
                onClick={isOutfitMode ? handleTryOnOutfit : handleTryOn}
                disabled={
                  activeTryonState.kind === "loading" ||
                  (mode.kind === "garment" && !mode.item.image_url)
                }
              >
                {activeTryonState.kind === "loading"
                  ? "Rendering try-on…"
                  : activeTryonState.kind === "ready"
                    ? "Try on again"
                    : "Virtual Try On"}
              </button>
              {activeTryonState.kind === "missing_person" && (
                <p className="conv-tryon-note">{activeTryonState.message}</p>
              )}
              {activeTryonState.kind === "error" && (
                <p className="conv-tryon-error">{activeTryonState.message}</p>
              )}
            </div>
          )}

          <div className="conv-cta-row">
            {isOutfitMode ? (
              <button
                type="button"
                className="conv-cta"
                onClick={handleBuyOutfit}
                disabled={!canBuyOutfit || cartBusy !== null}
                title={!canBuyOutfit ? "Pick a size for each item" : ""}
              >
                {cartBusy === "outfit" ? "Adding…" : "Buy outfit"}
              </button>
            ) : isWardrobe(mode.item) ? (
              <div
                className="conv-cta"
                style={{
                  background: "var(--ink-muted)",
                  cursor: "default",
                  pointerEvents: "none",
                }}
              >
                From your wardrobe
              </div>
            ) : (
              <>
                <button
                  type="button"
                  className="conv-cta conv-cta--secondary"
                  onClick={handleAddToCart}
                  disabled={!canBuyGarment || cartBusy !== null}
                  title={!canBuyGarment ? "Pick a size first" : ""}
                >
                  {cartBusy === "add-to-cart"
                    ? "Adding…"
                    : addedFlash
                      ? "Added ✓"
                      : "Add to Cart"}
                </button>
                <button
                  type="button"
                  className="conv-cta"
                  onClick={handleBuyNow}
                  disabled={!canBuyGarment || cartBusy !== null}
                  title={!canBuyGarment ? "Pick a size first" : ""}
                >
                  {cartBusy === "buy-now" ? "Loading…" : "Buy now"}
                </button>
              </>
            )}
            <HeartButton
              liked={liked}
              onClick={() => setLiked((v) => !v)}
              label={isOutfitMode ? "Like outfit" : "Save garment"}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

function isWardrobe(item: OutfitItem): boolean {
  return item.price == null;
}

function ThumbnailRail({
  outfit,
  tryonImage,
  mode,
  onSelect,
}: {
  outfit: Outfit;
  tryonImage: string | null;
  mode: Mode;
  onSelect: (next: Mode) => void;
}) {
  const isOutfitActive = mode.kind === "outfit";
  return (
    <div className="conv-thumbs">
      <button
        type="button"
        className={`conv-thumb ${isOutfitActive ? "is-active" : ""}`}
        onClick={() => onSelect({ kind: "outfit" })}
        aria-label="Try-on view"
        aria-pressed={isOutfitActive}
      >
        {tryonImage ? (
          <img src={tryonImage} alt="" />
        ) : (
          <span className="conv-thumb-empty">⤴</span>
        )}
        <span className="conv-thumb-label">Try-on</span>
      </button>
      {outfit.items.map((item) => {
        const isActive =
          mode.kind === "garment" && mode.item.garment_id === item.garment_id;
        return (
          <button
            key={item.garment_id}
            type="button"
            className={`conv-thumb ${isActive ? "is-active" : ""}`}
            onClick={() => onSelect({ kind: "garment", item })}
            aria-label={`View ${item.title}`}
            aria-pressed={isActive}
          >
            {item.image_url ? (
              <img src={item.image_url} alt="" />
            ) : (
              <span className="conv-thumb-empty">◇</span>
            )}
          </button>
        );
      })}
    </div>
  );
}

function OutfitDetail({
  outfit,
  selectedSizes,
  onPickSize,
}: {
  outfit: Outfit;
  selectedSizes: Record<string, Size>;
  onPickSize: (garmentId: string, size: Size) => void;
}) {
  return (
    <>
      <h4 className="conv-detail-title">{outfit.name ?? "Your look"}</h4>
      {outfit.reasoning && (
        <p className="conv-detail-desc">{outfit.reasoning}</p>
      )}
      <ul className="conv-outfit-items">
        {outfit.items.map((item) => {
          const wardrobe = isWardrobe(item);
          return (
            <li key={item.garment_id} className="conv-outfit-item">
              <div className="conv-outfit-item-row">
                <div className="conv-outfit-item-info">
                  {item.brand && (
                    <div className="conv-outfit-item-brand">{item.brand}</div>
                  )}
                  <div className="conv-outfit-item-title">{item.title}</div>
                </div>
                {wardrobe ? (
                  <div className="conv-outfit-item-wardrobe">From wardrobe</div>
                ) : item.price != null ? (
                  <div className="conv-outfit-item-price">
                    {formatRupees(item.price)}
                  </div>
                ) : null}
              </div>
              {!wardrobe && (
                <SizeChips
                  className="conv-outfit-item-sizes"
                  selected={selectedSizes[item.garment_id] ?? null}
                  onSelect={(size) => onPickSize(item.garment_id, size)}
                />
              )}
            </li>
          );
        })}
      </ul>
    </>
  );
}

function GarmentDetail({ item }: { item: OutfitItem }) {
  // PDP description: prefer the store catalog's own copy
  // (catalog_description, sourced from Shopify's product description)
  // so the customer reads the merchant's voice. Fall back to the
  // composer's stylist-voice text when the catalog row has no
  // description — common for wardrobe items, occasional for catalog
  // items missing body_html at ingestion time.
  const description =
    item.catalog_description?.trim() || item.description?.trim();
  return (
    <>
      {item.brand && <div className="conv-detail-brand">{item.brand}</div>}
      <h4 className="conv-detail-title">{item.title}</h4>
      {isWardrobe(item) ? (
        <p className="conv-detail-desc">From your wardrobe.</p>
      ) : (
        <p className="conv-detail-price">
          {formatRupees(item.price as number)}
        </p>
      )}
      {description && <p className="conv-detail-desc">{description}</p>}
    </>
  );
}

function SizeChips({
  selected,
  onSelect,
  className,
}: {
  selected: Size | null;
  onSelect: (size: Size) => void;
  /** Override the default wrapper class. Per-item rows pass a smaller
   *  variant; garment-mode panel uses the default `.conv-sizes`. */
  className?: string;
}) {
  return (
    <div
      className={className ?? "conv-sizes"}
      role="group"
      aria-label="Available sizes"
    >
      {SIZES.map((s) => {
        const isSelected = selected === s;
        return (
          <button
            key={s}
            type="button"
            className={`conv-size-chip ${isSelected ? "is-selected" : ""}`}
            onClick={() => onSelect(s)}
            aria-label={`Size ${s}`}
            aria-pressed={isSelected}
          >
            {s}
          </button>
        );
      })}
    </div>
  );
}

function HeartButton({
  liked,
  onClick,
  label,
}: {
  liked: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      className={`conv-cta-heart ${liked ? "is-liked" : ""}`}
      onClick={onClick}
      aria-label={label}
      aria-pressed={liked}
    >
      <svg
        width="20"
        height="20"
        viewBox="0 0 24 24"
        fill={liked ? "currentColor" : "none"}
        stroke="currentColor"
        strokeWidth="2"
      >
        <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
      </svg>
    </button>
  );
}

function formatRupees(amount: number): string {
  return `₹${Math.round(amount).toLocaleString("en-IN")}`;
}
