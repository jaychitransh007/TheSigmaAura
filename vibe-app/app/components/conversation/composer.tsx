// Chat composer — attach popover + chip preview + text input + send.
//
// Behaviors carried over from legacy platform_core/ui.py composer:
//   - Plus (+) button opens a 3-option popover: Upload image / From
//     wardrobe / From saved. Wardrobe + wishlist open modal grid
//     pickers; upload opens the OS file picker. Identity matches the
//     legacy .plus-popover.
//   - Selected attachment renders as a chip above the input with an X
//     to remove. One attachment per turn (popover swaps the previous
//     selection — engine accepts at most one anchor per call).
//   - Enter submits (legacy parity). Send is enabled when there is
//     text OR an attachment.
//
// Attachment is a discriminated union so the parent (and the action
// handler) can route to the right engine field — image_data /
// wardrobe_item_id / wishlist_product_id — without re-deriving the
// shape from optional fields.

import { useEffect, useRef, useState } from "react";

import { WardrobePicker, WishlistPicker } from "./pickers";

const MAX_BYTES = 10 * 1024 * 1024;

export type Attachment =
  | {
      kind: "image";
      // Data URL — what the engine's image_data field accepts. We
      // forward it verbatim from FileReader.readAsDataURL.
      dataUrl: string;
      filename: string;
    }
  | {
      kind: "wardrobe";
      itemId: string;
      title: string;
      // Image URL already routed through the App Proxy tryon-image
      // passthrough — safe to drop directly into <img src>.
      imageUrl: string;
    }
  | {
      kind: "wishlist";
      productId: string;
      title: string;
      imageUrl: string;
    };

export function Composer({
  sessionId,
  value,
  onChange,
  onSubmit,
  disabled,
  attachment,
  onAttach,
  onDetach,
  onAttachError,
}: {
  sessionId: string;
  value: string;
  onChange: (next: string) => void;
  onSubmit: () => void;
  disabled: boolean;
  attachment: Attachment | null;
  onAttach: (attachment: Attachment) => void;
  onDetach: () => void;
  /** Called with a customer-friendly message when the file is too large
   *  or unreadable. The parent surfaces it in the feed's error slot. */
  onAttachError?: (message: string) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const plusBtnRef = useRef<HTMLButtonElement>(null);

  const [popoverOpen, setPopoverOpen] = useState(false);
  const [pickerOpen, setPickerOpen] = useState<null | "wardrobe" | "wishlist">(
    null,
  );

  // Close the popover when the customer clicks anywhere else — both
  // the popover itself and the + button trigger get a click-outside
  // exemption so toggling stays predictable.
  useEffect(() => {
    if (!popoverOpen) return;
    const handler = (e: MouseEvent) => {
      const target = e.target as Node;
      if (popoverRef.current?.contains(target)) return;
      if (plusBtnRef.current?.contains(target)) return;
      setPopoverOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [popoverOpen]);

  // Allow send when there's text OR an attachment. Pairing requests
  // commonly come in attachment-only ("here, find me something to
  // pair") — requiring text would block that flow.
  const canSend = !disabled && (value.trim().length > 0 || attachment !== null);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      if (canSend) onSubmit();
    }
  };

  const openFilePicker = () => {
    if (disabled) return;
    setPopoverOpen(false);
    fileInputRef.current?.click();
  };

  const openWardrobePicker = () => {
    if (disabled) return;
    setPopoverOpen(false);
    setPickerOpen("wardrobe");
  };

  const openWishlistPicker = () => {
    if (disabled) return;
    setPopoverOpen(false);
    setPickerOpen("wishlist");
  };

  const handleFile = (file: File) => {
    if (!file.type.startsWith("image/")) {
      onAttachError?.("Pick an image file (JPG / PNG / WebP).");
      return;
    }
    if (file.size > MAX_BYTES) {
      onAttachError?.("Image must be under 10 MB.");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result;
      if (typeof result !== "string") {
        onAttachError?.("Couldn't read that image, try another one.");
        return;
      }
      onAttach({
        kind: "image",
        dataUrl: result,
        filename: file.name || "attachment.jpg",
      });
    };
    reader.onerror = () => {
      onAttachError?.("Couldn't read that image, try another one.");
    };
    reader.readAsDataURL(file);
  };

  // Chip thumbnail src + label resolve from the attachment kind. Image
  // uploads use the data URL directly; wardrobe / wishlist already
  // have engine-side image URLs (routed through the App Proxy proxy
  // for any local engine paths).
  const chipImageSrc =
    attachment?.kind === "image"
      ? attachment.dataUrl
      : attachment?.imageUrl ?? "";
  const chipLabel =
    attachment?.kind === "image" ? attachment.filename : attachment?.title ?? "";

  return (
    <>
      <div className="conv-composer-outer">
        <div className="conv-composer">
          {attachment && (
            <div className="conv-attach-chip">
              {chipImageSrc && <img src={chipImageSrc} alt="" />}
              <span className="conv-attach-chip-name" title={chipLabel}>
                {chipLabel}
              </span>
              <button
                type="button"
                className="conv-attach-chip-remove"
                onClick={onDetach}
                aria-label="Remove attachment"
                title="Remove"
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none">
                  <path
                    d="M18 6L6 18M6 6l12 12"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </button>
            </div>
          )}
          <div className="conv-composer-row">
            <div className="conv-attach-menu">
              <button
                ref={plusBtnRef}
                type="button"
                className="conv-composer-attach"
                onClick={() => setPopoverOpen((v) => !v)}
                disabled={disabled}
                aria-label="Attach"
                aria-haspopup="menu"
                aria-expanded={popoverOpen}
                title="Attach"
              >
                +
              </button>
              {popoverOpen && (
                <div
                  ref={popoverRef}
                  className="conv-attach-popover"
                  role="menu"
                >
                  <button
                    type="button"
                    role="menuitem"
                    onClick={openFilePicker}
                  >
                    <span className="conv-attach-popover-icon" aria-hidden="true">
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                        <rect
                          x="3"
                          y="3"
                          width="18"
                          height="18"
                          rx="2"
                          stroke="currentColor"
                          strokeWidth="1.8"
                        />
                        <circle
                          cx="8.5"
                          cy="8.5"
                          r="1.5"
                          stroke="currentColor"
                          strokeWidth="1.8"
                        />
                        <path
                          d="M21 15l-5-5L5 21"
                          stroke="currentColor"
                          strokeWidth="1.8"
                        />
                      </svg>
                    </span>
                    Upload image
                  </button>
                  <button
                    type="button"
                    role="menuitem"
                    onClick={openWardrobePicker}
                  >
                    <span className="conv-attach-popover-icon" aria-hidden="true">
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                        <path
                          d="M20.38 3.46L16 2 12 3.46 8 2 3.62 3.46a2 2 0 00-1.34 1.89v13.3a2 2 0 002.26 1.98L8 20l4-1.46L16 20l3.46.63a2 2 0 002.26-1.98V5.35a2 2 0 00-1.34-1.89z"
                          stroke="currentColor"
                          strokeWidth="1.8"
                        />
                      </svg>
                    </span>
                    From wardrobe
                  </button>
                  <button
                    type="button"
                    role="menuitem"
                    onClick={openWishlistPicker}
                  >
                    <span className="conv-attach-popover-icon" aria-hidden="true">
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                        <path
                          d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78L12 21.23l8.84-8.84a5.5 5.5 0 000-7.78z"
                          stroke="currentColor"
                          strokeWidth="1.8"
                        />
                      </svg>
                    </span>
                    From saved
                  </button>
                </div>
              )}
            </div>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              style={{ display: "none" }}
              onChange={(e) => {
                const file = e.currentTarget.files?.[0];
                if (file) handleFile(file);
                // Reset so picking the same file twice in a row
                // re-fires onChange.
                e.currentTarget.value = "";
              }}
            />
            <input
              ref={inputRef}
              type="text"
              value={value}
              onChange={(e) => onChange(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                attachment
                  ? "What goes with this? (optional)"
                  : "What's the occasion?"
              }
              disabled={disabled}
            />
            <button
              type="button"
              className="conv-composer-send"
              onClick={onSubmit}
              disabled={!canSend}
              aria-label="Send"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path
                  d="M8 13V3M8 3L4 7M8 3L12 7"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </button>
          </div>
        </div>
      </div>

      {pickerOpen === "wardrobe" && (
        <WardrobePicker
          sessionId={sessionId}
          onClose={() => setPickerOpen(null)}
          onPick={(item) => {
            onAttach({
              kind: "wardrobe",
              itemId: item.id,
              title: item.title,
              imageUrl: item.image_url,
            });
            setPickerOpen(null);
          }}
        />
      )}
      {pickerOpen === "wishlist" && (
        <WishlistPicker
          sessionId={sessionId}
          onClose={() => setPickerOpen(null)}
          onPick={(item) => {
            onAttach({
              kind: "wishlist",
              productId: item.product_id,
              title: item.title,
              imageUrl: item.image_url,
            });
            setPickerOpen(null);
          }}
        />
      )}
    </>
  );
}
