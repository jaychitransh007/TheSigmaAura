// Chat composer — attach button + chip preview + textarea + send.
//
// Behaviors carried over from legacy platform_core/ui.py composer:
//   - Cmd/Ctrl+Enter submits (Enter alone inserts newline)
//   - Plus (+) button opens the OS file picker for an image attachment
//   - Attached image renders as a chip above the input with an X to remove
//   - Sending is allowed when there's text OR an attachment (the engine
//     auto-fills a pairing prompt when text is empty and image is set —
//     see action handler in apps.vibe.style.tsx)
//   - Send button + textarea share the disabled state during a turn
//
// The "From wardrobe" / "From saved" picker variants from the legacy
// + popover live in their own routes (wardrobe / wishlist endpoints)
// and aren't wired yet — image upload is the path that unblocks
// pairing requests, which is the gap in the current Vibe shell.

import { useRef } from "react";

const MAX_BYTES = 10 * 1024 * 1024;

export type Attachment = {
  // Data URL — what the engine's image_data field accepts. We forward
  // it verbatim from FileReader.readAsDataURL.
  dataUrl: string;
  filename: string;
};

export function Composer({
  value,
  onChange,
  onSubmit,
  disabled,
  attachment,
  onAttach,
  onDetach,
  onAttachError,
}: {
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

  // Allow send when there's text OR an attachment. Pairing requests
  // commonly come in as image-only ("here, find me something to pair");
  // requiring text would block that flow.
  const canSend = !disabled && (value.trim().length > 0 || attachment !== null);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    // Enter submits — matches legacy ui.py's <input> composer. We use a
    // single-line input (not textarea) so the row stays exactly one
    // line tall and the +/send icons can center-align cleanly against
    // it without any auto-resize JS or height-matching gymnastics.
    if (e.key === "Enter") {
      e.preventDefault();
      if (canSend) onSubmit();
    }
  };

  const openFilePicker = () => {
    if (disabled) return;
    fileInputRef.current?.click();
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
      onAttach({ dataUrl: result, filename: file.name || "attachment.jpg" });
    };
    reader.onerror = () => {
      onAttachError?.("Couldn't read that image, try another one.");
    };
    reader.readAsDataURL(file);
  };

  // Structure: one bordered pill (.conv-composer) that contains an
  // optional chip row above an input row. Putting the chip *inside*
  // the pill (instead of stacked above as its own card) makes the
  // composer read as one unit and stops the chip from "flowing out"
  // visually. Matches the legacy ui.py composer where .image-chip and
  // the input row live inside a single .composer-outer.
  return (
    <div className="conv-composer-outer">
      <div className="conv-composer">
        {attachment && (
          <div className="conv-attach-chip">
            <img src={attachment.dataUrl} alt="" />
            <span className="conv-attach-chip-name" title={attachment.filename}>
              {attachment.filename}
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
          <button
            type="button"
            className="conv-composer-attach"
            onClick={openFilePicker}
            disabled={disabled}
            aria-label="Attach image"
            title="Attach image"
          >
            {/* Plain "+" — matches the legacy plusBtn affordance */}
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
              <path
                d="M12 5v14M5 12h14"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
              />
            </svg>
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            style={{ display: "none" }}
            onChange={(e) => {
              const file = e.currentTarget.files?.[0];
              if (file) handleFile(file);
              // Reset so picking the same file twice in a row re-fires
              // onChange. Without this, removing then re-attaching the
              // same photo would silently do nothing.
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
  );
}
