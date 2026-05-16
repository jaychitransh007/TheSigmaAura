// Rich outfit card — 3-column layout: thumbnails | hero | detail panel.
//
// Reference: legacy platform_core/ui.py PDP card (PRs #306, #317,
// #318, #323). D.C.2e introduced the structure; D.C.7 wires the
// cart:
//   - Size chips toggle a selected size (one per card, shared across
//     outfit/garment mode — a customer's size is consistent).
//   - Buy Outfit (outfit mode): adds every item at selectedSize to
//     the Shopify cart, then navigates to /cart.
//   - Buy Now (garment mode): adds just the current item at
//     selectedSize, then navigates to /cart.
//   - Both require selectedSize AND a valid (non-mock) variant gid.
//     Mock engine responses surface a friendly error toast instead
//     of hitting /cart/add.js with bogus ids.

import { useState } from "react";

import type { Outfit, OutfitItem } from "../../lib/engine.server";
import { addToCart, isMockVariantId } from "../../lib/cart.client";

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
  const [selectedSize, setSelectedSize] = useState<Size | null>(null);
  const [cartError, setCartError] = useState<string | null>(null);
  const [cartBusy, setCartBusy] = useState(false);

  const tryonImage = outfit.tryon_image_url ?? null;
  const isOutfitMode = mode.kind === "outfit";

  const heroImage = isOutfitMode
    ? tryonImage ?? outfit.items[0]?.image_url ?? null
    : mode.item.image_url ?? null;

  // Buy availability:
  //   Outfit mode: every item must have a variant gid for the selected
  //                size. (We require all-or-nothing — partial cart adds
  //                would confuse the customer.)
  //   Garment mode: just this item's variant gid for the selected size.
  const canBuyOutfit =
    isOutfitMode &&
    selectedSize !== null &&
    outfit.items.every(
      (item) =>
        item.price != null &&
        item.shopify_variant_ids?.[selectedSize] != null,
    );
  const canBuyGarment =
    !isOutfitMode &&
    selectedSize !== null &&
    mode.item.price != null &&
    mode.item.shopify_variant_ids?.[selectedSize] != null;

  const handleBuy = async () => {
    if (!selectedSize) return;
    setCartError(null);
    setCartBusy(true);
    try {
      if (mode.kind === "outfit") {
        const items = outfit.items
          .filter((it) => it.shopify_variant_ids?.[selectedSize])
          .map((it) => ({
            variantId: it.shopify_variant_ids![selectedSize]!,
          }));
        await addToCart(items);
      } else {
        const variantId = mode.item.shopify_variant_ids?.[selectedSize];
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
            <OutfitDetail outfit={outfit} />
          ) : (
            <GarmentDetail item={mode.item} />
          )}

          <SizeChips
            selected={selectedSize}
            onSelect={setSelectedSize}
            availableSizes={
              isOutfitMode
                ? sizesAvailableForOutfit(outfit)
                : sizesAvailableForItem(mode.item)
            }
          />

          {cartError && <div className="conv-cart-error">{cartError}</div>}

          <div className="conv-cta-row">
            {isOutfitMode ? (
              <button
                type="button"
                className="conv-cta"
                onClick={handleBuy}
                disabled={!canBuyOutfit || cartBusy}
                title={
                  !selectedSize
                    ? "Pick a size first"
                    : !canBuyOutfit
                    ? "One or more items aren't shoppable yet"
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
                title={!selectedSize ? "Pick a size first" : ""}
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

function OutfitDetail({ outfit }: { outfit: Outfit }) {
  return (
    <>
      <h4 className="conv-detail-title">{outfit.name ?? "Your look"}</h4>
      {outfit.reasoning && (
        <p className="conv-detail-desc">{outfit.reasoning}</p>
      )}
      <ul className="conv-outfit-items">
        {outfit.items.map((item) => (
          <li key={item.garment_id} className="conv-outfit-item">
            <div className="conv-outfit-item-info">
              {item.brand && (
                <div className="conv-outfit-item-brand">{item.brand}</div>
              )}
              <div className="conv-outfit-item-title">{item.title}</div>
            </div>
            {item.price != null ? (
              <div className="conv-outfit-item-price">
                {formatRupees(item.price)}
              </div>
            ) : (
              <div className="conv-outfit-item-wardrobe">
                From your wardrobe
              </div>
            )}
          </li>
        ))}
      </ul>
    </>
  );
}

function GarmentDetail({ item }: { item: OutfitItem }) {
  const description = item.description?.trim();
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
}: {
  selected: Size | null;
  onSelect: (size: Size) => void;
  availableSizes: Set<Size>;
}) {
  return (
    <div className="conv-sizes" role="group" aria-label="Available sizes">
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
