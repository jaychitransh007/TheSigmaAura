// Single message bubble. User messages on the right (accent fill);
// assistant on the left (borderless with a 2px ink left rule).
// Pattern carried over from legacy ui.py chat layout.

import type { Outfit } from "../../lib/engine.server";

export type ChatMessage =
  | { role: "user"; text: string }
  | { role: "assistant"; text: string; outfits?: Outfit[] };

export function MessageView({ message }: { message: ChatMessage }) {
  if (message.role === "user") {
    return <div className="conv-message conv-message--user">{message.text}</div>;
  }

  return (
    <div className="conv-message conv-message--assistant">
      <p>{message.text}</p>
      {message.outfits?.map((outfit) => (
        <OutfitCardSimple key={outfit.outfit_id} outfit={outfit} />
      ))}
    </div>
  );
}

// Minimal outfit card. D.C.2e replaces this with the full 3-column
// version (thumbnails | hero | detail panel with line-clamp). For
// D.C.2d we just need the engine response to render somewhere
// believable so the chat loop is testable end-to-end.
function OutfitCardSimple({ outfit }: { outfit: Outfit }) {
  return (
    <div className="conv-outfit-card">
      {outfit.name && <h3 className="conv-outfit-name">{outfit.name}</h3>}
      {outfit.reasoning && (
        <p className="conv-outfit-reasoning">{outfit.reasoning}</p>
      )}
      <ul className="conv-outfit-items">
        {outfit.items.map((item) => (
          <li key={item.garment_id} className="conv-outfit-item">
            <div>
              {item.brand && (
                <div className="conv-outfit-item-brand">{item.brand}</div>
              )}
              <div>{item.title}</div>
            </div>
            {item.price != null && (
              <div className="conv-outfit-item-price">
                ₹{Math.round(item.price).toLocaleString("en-IN")}
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
