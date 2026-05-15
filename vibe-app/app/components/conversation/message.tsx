// Single message bubble. User messages on the right (accent fill);
// assistant on the left (borderless with a 2px ink left rule).
// Pattern carried over from legacy ui.py chat layout.
//
// Assistant messages can carry outfit cards (D.C.2e — rich 3-column
// layout with thumbnails / hero / detail panel and mode switching).

import { OutfitCard } from "./outfit-card";
import type { Outfit } from "../../lib/engine.server";

export type ChatMessage =
  | { role: "user"; text: string }
  | { role: "assistant"; text: string; outfits?: Outfit[] };

export function MessageView({
  message,
  onHideOutfit,
}: {
  message: ChatMessage;
  onHideOutfit?: (outfitId: string) => void;
}) {
  if (message.role === "user") {
    return <div className="conv-message conv-message--user">{message.text}</div>;
  }

  return (
    <div className="conv-message conv-message--assistant">
      <p>{message.text}</p>
      {message.outfits?.map((outfit) => (
        <OutfitCard
          key={outfit.outfit_id}
          outfit={outfit}
          onHide={onHideOutfit ? () => onHideOutfit(outfit.outfit_id) : undefined}
        />
      ))}
    </div>
  );
}
