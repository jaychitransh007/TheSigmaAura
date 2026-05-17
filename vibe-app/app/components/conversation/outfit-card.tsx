// Rich outfit card — 3-column layout: thumbnails | hero | detail panel.
//
// Reference: legacy platform_core/ui.py PDP card.
//   - Per-item size chips (Record<garment_id, Size>): customers can be
//     S in tops and M in bottoms; one global size would silently force
//     them into the wrong variant on at least one item.
//   - Buy Outfit (outfit mode): adds every shoppable item at its picked
//     size to the Shopify cart, then navigates to /cart. Requires every
//     shoppable item to have a size selected AND a real variant gid.
//   - Buy Now (garment mode): adds just the current item at its picked
//     size. Wardrobe items render a static "From your wardrobe" pill
//     instead of a Buy button.
//   - Mock engine responses surface a friendly error toast instead of
//     hitting /cart/add.js with bogus ids.

import { useState } from "react";

import type { Outfit, OutfitItem } from "../../lib/engine.server";
import { addToCart } from "../../lib/cart.client";

const SIZES = ["XS", "S", "M", "L", "XL"] as const;
type Size = (typeof SIZES)[number];

type Mode =
  | { kind: "outfit" }
  | { kind: "garment"; item: OutfitItem };

export function OutfitCard({
  outfit,
  onHide,
}: {
  outfit: Outfit;
  onHide?: () => void;
}) {
  const [mode, setMode] = useState<Mode>({ kind: "outfit" });
  const [liked, setLiked] = useState(false);
  // Per-item size selection. Keyed by garment_id because customers
  // need to pick a size for each Shopify SKU independently — a
  // shopper who's S in tops can be M in bottoms, and a single global
  // size would silently force them into the wrong variant on at
  // least one item.
  const [selectedSizes, setSelectedSizes] = useState<Record<string, Size>>({});
  const [cartError, setCartError] = useState<string | null>(null);
  const [cartBusy, setCartBusy] = useState(false);

  const tryonImage = outfit.tryon_image_url ?? null;
  const isOutfitMode = mode.kind === "outfit";

  const heroImage = isOutfitMode
    ? tryonImage ?? outfit.items[0]?.image_url ?? null
    : mode.item.image_url ?? null;

  const pickSize = (garmentId: string, size: Size) =>
    setSelectedSizes((prev) => ({ ...prev, [garmentId]: size }));

  // Buy availability:
  //   Outfit mode: every shoppable item needs a size picked AND a
  //                variant gid for that size. Wardrobe items (price
  //                null) are excluded — the customer already owns
  //                them, so no cart add for those.
  //   Garment mode: just this item's variant gid for its picked size.
  const shoppableItems = outfit.items.filter((it) => !isWardrobe(it));
  const canBuyOutfit =
    isOutfitMode &&
    shoppableItems.length > 0 &&
    shoppableItems.every((item) => {
      const size = selectedSizes[item.garment_id];
      return size != null && item.shopify_variant_ids?.[size] != null;
    });
  const garmentSelected =
    mode.kind === "garment" ? selectedSizes[mode.item.garment_id] : undefined;
  const canBuyGarment =
    mode.kind === "garment" &&
    garmentSelected !== undefined &&
    mode.item.price != null &&
    mode.item.shopify_variant_ids?.[garmentSelected] != null;

  const handleBuy = async () => {
    setCartError(null);
    setCartBusy(true);
    try {
      if (mode.kind === "outfit") {
        const items = shoppableItems
          .map((it) => {
            const size = selectedSizes[it.garment_id];
            const variantId = size
              ? it.shopify_variant_ids?.[size]
              : undefined;
            return variantId ? { variantId } : null;
          })
          .filter((x): x is { variantId: string } => x !== null);
        if (items.length === 0) {
          setCartBusy(false);
          return;
        }
        await addToCart(items);
      } else {
        const size = selectedSizes[mode.item.garment_id];
        const variantId = size ? mode.item.shopify_variant_ids?.[size] : undefined;
        if (!variantId) return;
        await addToCart([{ variantId }]);
      }
    } catch (e) {
      setCartError(e instanceof Error ? e.message : String(e));
      setCartBusy(false);
    }
  };

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
                  availableSizes={sizesAvailableForItem(mode.item)}
                />
              )}
            </>
          )}

          {cartError && <div className="conv-cart-error">{cartError}</div>}

          <div className="conv-cta-row">
            {isOutfitMode ? (
              <button
                type="button"
                className="conv-cta"
                onClick={handleBuy}
                disabled={!canBuyOutfit || cartBusy}
                title={
                  !canBuyOutfit
                    ? "Pick a size for each item"
                    : ""
                }
              >
                {cartBusy ? "Adding…" : "Buy outfit"}
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
              <button
                type="button"
                className="conv-cta"
                onClick={handleBuy}
                disabled={!canBuyGarment || cartBusy}
                title={!garmentSelected ? "Pick a size first" : ""}
              >
                {cartBusy ? "Adding…" : "Buy now"}
              </button>
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

function sizesAvailableForOutfit(outfit: Outfit): Set<Size> {
  // A size is available for the outfit only if every shoppable item
  // has a variant for that size. Wardrobe items are excluded from the
  // requirement (they're owned, not bought).
  const shoppable = outfit.items.filter((it) => !isWardrobe(it));
  if (shoppable.length === 0) return new Set();
  const out = new Set<Size>();
  for (const size of SIZES) {
    if (shoppable.every((it) => it.shopify_variant_ids?.[size])) {
      out.add(size);
    }
  }
  return out;
}

function sizesAvailableForItem(item: OutfitItem): Set<Size> {
  if (isWardrobe(item)) return new Set();
  const out = new Set<Size>();
  for (const size of SIZES) {
    if (item.shopify_variant_ids?.[size]) out.add(size);
  }
  return out;
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
                  availableSizes={sizesAvailableForItem(item)}
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
  availableSizes,
  className,
}: {
  selected: Size | null;
  onSelect: (size: Size) => void;
  availableSizes: Set<Size>;
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
        const available = availableSizes.has(s);
        const isSelected = selected === s;
        return (
          <button
            key={s}
            type="button"
            className={`conv-size-chip ${isSelected ? "is-selected" : ""} ${
              !available ? "is-unavailable" : ""
            }`}
            onClick={() => available && onSelect(s)}
            disabled={!available}
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
