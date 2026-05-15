// Chat composer — textarea + send button.
//
// Behaviors carried over from legacy platform_core/ui.py:
//   - Cmd/Ctrl+Enter submits (Enter alone inserts newline)
//   - Send button disabled when input empty or a turn is in flight
//   - Textarea auto-grows up to max-height (CSS-driven)
//
// Deferred: the legacy "+" popover (upload image / from wardrobe /
// from wishlist) lands in D.C.5 alongside Outfit Check.

import { useEffect, useRef } from "react";

export function Composer({
  value,
  onChange,
  onSubmit,
  disabled,
}: {
  value: string;
  onChange: (next: string) => void;
  onSubmit: () => void;
  disabled: boolean;
}) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea to fit content (within CSS max-height cap).
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }, [value]);

  const canSend = !disabled && value.trim().length > 0;

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      if (canSend) onSubmit();
    }
  };

  return (
    <div className="conv-composer-outer">
      <div className="conv-composer">
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="What's the occasion?"
          rows={1}
          disabled={disabled}
        />
        <button
          type="button"
          className="conv-composer-send"
          onClick={onSubmit}
          disabled={!canSend}
          aria-label="Send"
        >
          {/* Up arrow — minimalist send icon */}
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
  );
}
