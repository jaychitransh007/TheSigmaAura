// PDP carousel — wraps an array of OutfitCards and shows one at a time
// with a "N / total" counter and prev/next arrows. Mirrors the legacy
// platform_core/ui.py renderPdpCarousel (Phase 15) pattern: header row
// over a single visible card, keyboard arrows + horizontal swipe to
// navigate. Hidden outfits are dropped from the rotation so the counter
// stays accurate.

import { useEffect, useRef, useState } from "react";

import type { Outfit } from "../../lib/engine.server";
import { OutfitCard } from "./outfit-card";

const SWIPE_PX = 50;
const SWIPE_RATIO = 1.5;

export function OutfitCarousel({
  outfits,
  onHide,
}: {
  outfits: Outfit[];
  /** Same contract as OutfitCard.onHide — receives the outfit_id of
   *  the card the user dismissed; parent state owns the filtered list. */
  onHide?: (outfitId: string) => void;
}) {
  const [idx, setIdx] = useState(0);
  const slotRef = useRef<HTMLDivElement | null>(null);
  const touchStart = useRef<{ x: number; y: number } | null>(null);

  // Clamp when the visible card was just hidden (parent shortened the
  // outfit array). Without this we'd render undefined and crash.
  useEffect(() => {
    if (idx >= outfits.length && outfits.length > 0) {
      setIdx(outfits.length - 1);
    }
  }, [outfits.length, idx]);

  if (outfits.length === 0) return null;
  const current = outfits[Math.min(idx, outfits.length - 1)];
  const total = outfits.length;
  const hasMultiple = total > 1;

  const goPrev = () => setIdx((i) => Math.max(0, i - 1));
  const goNext = () => setIdx((i) => Math.min(total - 1, i + 1));

  return (
    <div className="conv-carousel">
      {hasMultiple && (
        <div className="conv-carousel-header">
          <span className="conv-carousel-counter">
            {Math.min(idx, total - 1) + 1} / {total}
          </span>
          <div className="conv-carousel-nav">
            <button
              type="button"
              onClick={goPrev}
              disabled={idx === 0}
              aria-label="Previous outfit"
              title="Previous"
            >
              ←
            </button>
            <button
              type="button"
              onClick={goNext}
              disabled={idx >= total - 1}
              aria-label="Next outfit"
              title="Next"
            >
              →
            </button>
          </div>
        </div>
      )}

      <div
        ref={slotRef}
        className="conv-carousel-slot"
        tabIndex={0}
        role="region"
        aria-label="Outfit carousel"
        onKeyDown={(e) => {
          if (!hasMultiple) return;
          if (e.key === "ArrowLeft") {
            e.preventDefault();
            goPrev();
          }
          if (e.key === "ArrowRight") {
            e.preventDefault();
            goNext();
          }
        }}
        onTouchStart={(e) => {
          const t = e.touches[0];
          touchStart.current = { x: t.clientX, y: t.clientY };
        }}
        onTouchEnd={(e) => {
          if (!hasMultiple || !touchStart.current) return;
          const t = e.changedTouches[0];
          const dx = t.clientX - touchStart.current.x;
          const dy = t.clientY - touchStart.current.y;
          touchStart.current = null;
          if (Math.abs(dx) > SWIPE_PX && Math.abs(dx) > Math.abs(dy) * SWIPE_RATIO) {
            if (dx < 0) goNext();
            else goPrev();
          }
        }}
      >
        <OutfitCard
          // Keying by outfit_id forces a fresh OutfitCard instance per
          // slide — internal state (selected size, garment-vs-outfit
          // mode, cart busy/error) is per-outfit and shouldn't bleed
          // between cards as the user swipes.
          key={current.outfit_id}
          outfit={current}
          onHide={onHide ? () => onHide(current.outfit_id) : undefined}
        />
      </div>
    </div>
  );
}
