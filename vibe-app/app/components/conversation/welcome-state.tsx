// First-visit empty state.
//
// Reference: legacy platform_core/ui.py chat welcome screen.
//   - One dominant primary CTA ("Dress me for tonight")
//   - Three secondary suggestions tucked below (legacy hid these
//     behind a "More ways to style" toggle; for v1 we keep them
//     visible — toggle can come back if the screen feels crowded)

import type { Dispatch, SetStateAction } from "react";

const SUGGESTIONS = [
  "Dress me for tonight",
  "What goes with my new jeans?",
  "I need an outfit for a wedding",
  "Should I buy this?",
];

const PRIMARY = SUGGESTIONS[0];

export function WelcomeState({
  onPick,
}: {
  onPick: Dispatch<SetStateAction<string>>;
}) {
  return (
    <div className="conv-welcome">
      <h2 className="conv-welcome-headline">Style that gets you.</h2>
      <p className="conv-welcome-sub">
        Tell me about the moment — I'll build the look.
      </p>
      <button
        type="button"
        className="conv-welcome-cta"
        onClick={() => onPick(PRIMARY)}
      >
        {PRIMARY}
      </button>
      <div className="conv-welcome-secondary">
        {SUGGESTIONS.slice(1).map((s) => (
          <button
            key={s}
            type="button"
            className="conv-prompt-chip"
            onClick={() => onPick(s)}
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}
