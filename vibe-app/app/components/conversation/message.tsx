// Single message bubble. User messages on the right (accent fill);
// assistant on the left (borderless with a 2px ink left rule).
// Onboarding messages are full-width cards (not bubbles) — they carry
// either an interactive widget (PhotosCard / FieldCard) or a static
// "Photos saved" / "Skipped" summary line once the step has advanced.
//
// Pattern carried over from legacy ui.py chat layout.
//
// Assistant messages can carry outfit cards (D.C.2e — rich 3-column
// layout with thumbnails / hero / detail panel and mode switching).

import { OutfitCard } from "./outfit-card";
import { FieldCard, type FieldKind } from "../onboarding/field-card";
import { GenderDobCard } from "../onboarding/gender-dob-card";
import { PhotosCard } from "../onboarding/photos-card";
import type { Outfit, OnboardingImageCategory } from "../../lib/engine.server";

export type OnboardingMessageKind = "photos" | "gender-dob" | FieldKind;

export type ChatMessage =
  | { role: "user"; text: string }
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
}) {
  if (message.role === "user") {
    return <div className="conv-message conv-message--user">{message.text}</div>;
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
    const fieldKind = message.kind;
    return (
      <div className="conv-message conv-message--onboarding">
        <FieldCard
          kind={fieldKind}
          sessionId={sessionId}
          onAdvance={(mode) => onAdvanceOnboarding?.(fieldKind, mode)}
        />
      </div>
    );
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
