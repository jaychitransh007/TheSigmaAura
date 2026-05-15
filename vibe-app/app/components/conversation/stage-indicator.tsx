// Shows the latest engine stage during a turn-in-progress. Renders
// the stage's `message` (stylist-voice — "Reading your style…",
// "Composing the look…") not the technical stage name.
//
// Pulse animation comes from CSS (.conv-stage::before).

import type { TurnStage } from "../../lib/engine.server";

const FALLBACK_LABELS: Record<string, string> = {
  planner_complete: "Reading your style…",
  architect_complete: "Building the outfit shape…",
  composer_complete: "Composing the look…",
  rater_complete: "Checking the fit…",
  tryon_complete: "Rendering try-on…",
};

export function StageIndicator({ stages }: { stages: TurnStage[] }) {
  if (stages.length === 0) {
    return <div className="conv-stage">Getting started…</div>;
  }
  const latest = stages[stages.length - 1];
  const label =
    latest.message?.trim() || FALLBACK_LABELS[latest.stage] || latest.stage;
  return <div className="conv-stage">{label}</div>;
}
