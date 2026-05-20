// Single message bubble. User messages on the right (accent fill);
// assistant on the left (borderless with a 2px ink left rule).
// Onboarding messages are full-width cards (not bubbles) — they carry
// either an interactive widget (PhotosCard / GenderDobCard /
// HeightWaistCard) or a static "saved" / "skipped" summary line once
// the step has advanced.
//
// Pattern carried over from legacy ui.py chat layout.
//
// Assistant messages can carry outfit cards (D.C.2e — rich 3-column
// layout with thumbnails / hero / detail panel and mode switching).

import { OutfitCarousel } from "./outfit-carousel";
import { GenderDobCard } from "../onboarding/gender-dob-card";
import { HeightWaistCard } from "../onboarding/height-waist-card";
import { PhotosCard } from "../onboarding/photos-card";
import type { Outfit, OnboardingImageCategory } from "../../lib/engine.server";

export type OnboardingMessageKind = "photos" | "gender-dob" | "height-waist";

export type ChatMessage =
  | {
      role: "user";
      text: string;
      /** Data URL of an image the customer attached to this turn. When
       *  present we render it inline above the text so the conversation
       *  history reads accurately (legacy ui.py did this in its
       *  query-preview block). */
      imagePreview?: string;
    }
  | { role: "assistant"; text: string; outfits?: Outfit[] }
  | {
      role: "onboarding";
      kind: OnboardingMessageKind;
      status: "active" | "completed" | "skipped";
      // Short summary shown when status !== "active" (e.g. "Photos saved").
      summary?: string;
    };

export function MessageView({
  message,
  sessionId,
  onAdvanceOnboarding,
  onOnboardingPhotoUploaded,
  onHideOutfit,
  hasBodyPhoto = false,
  onRequestPhotosCard,
}: {
  message: ChatMessage;
  sessionId: string;
  /**
   * Notifies the parent that an onboarding card has resolved. `kind`
   * is passed explicitly because multiple cards can be active at the
   * same time (initial parallel photos + gender-DOB) and the parent
   * needs to know which to mark resolved.
   */
  onAdvanceOnboarding?: (
    kind: OnboardingMessageKind,
    mode: "completed" | "skipped",
  ) => void;
  onOnboardingPhotoUploaded?: (category: OnboardingImageCategory) => void;
  onHideOutfit?: (outfitId: string) => void;
  /** Phase W.5 — passed through to OutfitCarousel → OutfitCard so
   *  the auto-fire effect knows whether to render. */
  hasBodyPhoto?: boolean;
  /** Phase W.6 — passed through so the missing-person path can ask
   *  the parent to inject a photos onboarding card inline. */
  onRequestPhotosCard?: () => void;
}) {
  if (message.role === "user") {
    // Stacked layout — query text on top, attached image below.
    // Reads like a stylist's brief instead of a chat bubble.
    return (
      <div className="conv-message conv-message--user">
        <span className="conv-message-text">{message.text}</span>
        {message.imagePreview && (
          <img
            className="conv-message-attachment"
            src={message.imagePreview}
            alt="Attached"
          />
        )}
      </div>
    );
  }

  if (message.role === "onboarding") {
    if (message.status !== "active") {
      // Static summary line — keeps the feed coherent without
      // re-rendering the interactive widget after it's been consumed.
      return (
        <div
          className={`conv-message conv-message--onboarding-summary conv-message--onboarding-${message.status}`}
        >
          {message.summary ?? (message.status === "skipped" ? "Skipped" : "Saved")}
        </div>
      );
    }
    if (message.kind === "photos") {
      return (
        <div className="conv-message conv-message--onboarding">
          <PhotosCard
            sessionId={sessionId}
            onAdvance={(mode) => onAdvanceOnboarding?.("photos", mode)}
            onUploaded={onOnboardingPhotoUploaded}
          />
        </div>
      );
    }
    if (message.kind === "gender-dob") {
      return (
        <div className="conv-message conv-message--onboarding">
          <GenderDobCard
            sessionId={sessionId}
            onAdvance={(mode) => onAdvanceOnboarding?.("gender-dob", mode)}
          />
        </div>
      );
    }
    // height-waist (only remaining kind)
    return (
      <div className="conv-message conv-message--onboarding">
        <HeightWaistCard
          sessionId={sessionId}
          onAdvance={(mode) => onAdvanceOnboarding?.("height-waist", mode)}
        />
      </div>
    );
  }

  return (
    <div className="conv-message conv-message--assistant">
      <p>{message.text}</p>
      {message.outfits && message.outfits.length > 0 && (
        <OutfitCarousel
          outfits={message.outfits}
          onHide={onHideOutfit}
          hasBodyPhoto={hasBodyPhoto}
          onRequestPhotosCard={onRequestPhotosCard}
        />
      )}
    </div>
  );
}
