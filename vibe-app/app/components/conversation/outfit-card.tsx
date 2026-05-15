// Rich outfit card — 3-column layout: thumbnails | hero | detail panel.
//
// Reference: legacy platform_core/ui.py PDP card (PRs #306, #317,
// #318, #323). Patterns carried over:
//   - Compact header: title + Hide icon. No border-bottom; card reads
//     as one unified surface.
//   - Outfit mode (try-on thumbnail active, default): outfit title,
//     reasoning paragraph, per-garment row list with price + size
//     chips, CTA row of "Buy Outfit" (disabled — multi-item checkout
//     comes in D.C.7) + Like (heart).
//   - Garment mode (garment thumbnail active): garment title, brand,
//     price, description, size chips, CTA row of "Buy Now" (opens
//     product_url) + Save (heart).
//   - Detail panel uses min-height + line-clamp so the CTA row stays
//     in a stable vertical position across cards.
//   - Prices in neutral ink, not accent.
//   - Wardrobe items show "From your wardrobe" instead of price and
//     hide Buy/Save CTAs.
//
// Anchor handling (PR #323) deferred to a follow-up — engine response
// shape doesn't currently mark anchor items in mocks. Add when real
// engine response includes the `is_anchor` flag.

import { useState } from "react";

import type { Outfit, OutfitItem } from "../../lib/engine.server";

const SIZES = ["XS", "S", "M", "L", "XL"] as const;

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

  // Try-on is the default hero. Falls back to first garment image.
  const tryonImage = outfit.tryon_image_url ?? null;
  const isOutfitMode = mode.kind === "outfit";

  const heroImage = isOutfitMode
    ? tryonImage ?? outfit.items[0]?.image_url ?? null
    : mode.item.image_url ?? null;

  return (
    <div className="conv-card" data-outfit-id={outfit.outfit_id}>
      <div className="conv-card-header">
        <h3 className="conv-card-title">
          {isOutfitMode
            ? outfit.name ?? "Your look"
            : mode.item.title}
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
              liked={liked}
              onToggleLike={() => setLiked((v) => !v)}
            />
          ) : (
            <GarmentDetail
              item={mode.item}
              liked={liked}
              onToggleLike={() => setLiked((v) => !v)}
            />
          )}
        </div>
      </div>
    </div>
  );
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
        const isActive = mode.kind === "garment" && mode.item.garment_id === item.garment_id;
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
  liked,
  onToggleLike,
}: {
  outfit: Outfit;
  liked: boolean;
  onToggleLike: () => void;
}) {
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
              <div className="conv-outfit-item-wardrobe">From your wardrobe</div>
            )}
          </li>
        ))}
      </ul>
      <SizeChips />
      <div className="conv-cta-row">
        <button
          type="button"
          className="conv-cta"
          disabled
          title="Multi-item checkout coming in D.C.7"
        >
          Buy outfit
        </button>
        <HeartButton liked={liked} onClick={onToggleLike} label="Like outfit" />
      </div>
    </>
  );
}

function GarmentDetail({
  item,
  liked,
  onToggleLike,
}: {
  item: OutfitItem;
  liked: boolean;
  onToggleLike: () => void;
}) {
  const isWardrobe = item.price == null;
  return (
    <>
      {item.brand && <div className="conv-detail-brand">{item.brand}</div>}
      <h4 className="conv-detail-title">{item.title}</h4>
      {isWardrobe ? (
        <p className="conv-detail-desc">From your wardrobe.</p>
      ) : (
        <p className="conv-detail-price">{formatRupees(item.price as number)}</p>
      )}
      <SizeChips />
      <div className="conv-cta-row">
        {isWardrobe ? (
          <div className="conv-cta" style={{ background: "var(--ink-muted)", cursor: "default", pointerEvents: "none" }}>
            From your wardrobe
          </div>
        ) : item.product_url ? (
          <a
            className="conv-cta"
            href={item.product_url}
            target="_blank"
            rel="noopener noreferrer"
          >
            Buy now
          </a>
        ) : (
          <button type="button" className="conv-cta" disabled>
            Buy now
          </button>
        )}
        {!isWardrobe && (
          <HeartButton liked={liked} onClick={onToggleLike} label="Save garment" />
        )}
      </div>
    </>
  );
}

function SizeChips() {
  return (
    <div className="conv-sizes" role="group" aria-label="Available sizes">
      {SIZES.map((s) => (
        <button key={s} type="button" className="conv-size-chip" aria-label={`Size ${s}`}>
          {s}
        </button>
      ))}
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
      <svg width="20" height="20" viewBox="0 0 24 24" fill={liked ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2">
        <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
      </svg>
    </button>
  );
}

function formatRupees(amount: number): string {
  return `₹${Math.round(amount).toLocaleString("en-IN")}`;
}
