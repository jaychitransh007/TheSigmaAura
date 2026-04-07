#!/usr/bin/env bash
#
# End-to-end smoke test: onboarding -> analysis -> first chat -> wardrobe ->
# (best-effort WhatsApp) -> dependency report. Designed to run against a
# *real* backend (local with seeded data, or staging) so it surfaces issues
# that unit/integration tests miss.
#
# Required env vars:
#   USER_ID         — onboarded user with completed analysis & style preference
#   BASE_URL        — defaults to http://127.0.0.1:8010
# Optional:
#   CONVERSATION_ID — reuse an existing conversation
#   WARDROBE_IMAGE  — local path to a test image for the wardrobe save step
#   SKIP_WHATSAPP   — set to 1 to skip the WhatsApp smoke step (default: skip
#                     unless WHATSAPP_INBOUND_URL is set, since the runtime
#                     was deliberately removed and is being rebuilt)

set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8010}"
USER_ID="${USER_ID:-}"
CONVERSATION_ID="${CONVERSATION_ID:-}"
WARDROBE_IMAGE="${WARDROBE_IMAGE:-}"
SKIP_WHATSAPP="${SKIP_WHATSAPP:-1}"
PASS=0
FAIL=0

color_ok()   { printf "\033[0;32m%s\033[0m\n" "$*"; }
color_warn() { printf "\033[0;33m%s\033[0m\n" "$*"; }
color_err()  { printf "\033[0;31m%s\033[0m\n" "$*"; }
section()    { printf "\n=== %s ===\n" "$*"; }

step_pass() { color_ok   "  PASS: $*"; PASS=$((PASS + 1)); }
step_fail() { color_err  "  FAIL: $*"; FAIL=$((FAIL + 1)); }
step_skip() { color_warn "  SKIP: $*"; }

if [[ -z "$USER_ID" ]]; then
  echo "Set USER_ID to an onboarded user with completed analysis and style preference." >&2
  exit 1
fi
if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required for this smoke test." >&2
  exit 1
fi

# ----- 1. Health -----
section "1. /healthz"
if curl --fail --silent "$BASE_URL/healthz" | jq -e '.status == "ok"' >/dev/null 2>&1; then
  step_pass "service is healthy"
else
  step_fail "/healthz did not return status=ok"
fi

# ----- 2. Onboarding state -----
section "2. Onboarding & analysis state for $USER_ID"
ONBOARDING_JSON="$(curl --fail --silent "$BASE_URL/v1/users/$USER_ID/conversations" || true)"
if [[ -n "$ONBOARDING_JSON" ]]; then
  step_pass "onboarding/conversations endpoint reachable"
else
  step_fail "could not query conversations for $USER_ID"
fi

# ----- 3. First chat turn -----
section "3. First chat turn"
if [[ -z "$CONVERSATION_ID" ]]; then
  CONVERSATION_ID="$(
    curl --fail --silent \
      -X POST "$BASE_URL/v1/conversations" \
      -H "Content-Type: application/json" \
      -d "{\"user_id\":\"$USER_ID\"}" \
      | jq -r '.conversation_id'
  )"
  echo "  created conversation: $CONVERSATION_ID"
fi

TURN1="$(
  curl --fail --silent \
    -X POST "$BASE_URL/v1/conversations/$CONVERSATION_ID/turns" \
    -H "Content-Type: application/json" \
    -d "{\"user_id\":\"$USER_ID\",\"message\":\"What should I wear to the office tomorrow?\"}" \
    || true
)"
if [[ -n "$TURN1" ]] && echo "$TURN1" | jq -e '.assistant_message != ""' >/dev/null 2>&1; then
  step_pass "first turn returned a non-empty assistant_message"
  echo "$TURN1" | jq '{turn_id, assistant_message, primary_intent: .metadata.primary_intent, answer_source: .metadata.answer_source}'
else
  step_fail "first turn returned empty / failed"
fi

# ----- 4. Wardrobe save (optional, requires image) -----
section "4. Wardrobe save"
if [[ -n "$WARDROBE_IMAGE" && -f "$WARDROBE_IMAGE" ]]; then
  IMAGE_B64="$(base64 < "$WARDROBE_IMAGE" | tr -d '\n')"
  if curl --fail --silent \
       -X POST "$BASE_URL/v1/conversations/$CONVERSATION_ID/turns" \
       -H "Content-Type: application/json" \
       -d "{\"user_id\":\"$USER_ID\",\"message\":\"Save this to my wardrobe\",\"image_data\":\"data:image/jpeg;base64,$IMAGE_B64\"}" \
       | jq -e '.assistant_message != ""' >/dev/null 2>&1; then
    step_pass "wardrobe save turn succeeded"
  else
    step_fail "wardrobe save turn failed"
  fi
else
  step_skip "WARDROBE_IMAGE not set or file missing — set WARDROBE_IMAGE=/path/to/test.jpg"
fi

# ----- 5. WhatsApp smoke (deliberately skipped — runtime removed) -----
section "5. WhatsApp inbound"
if [[ "$SKIP_WHATSAPP" == "1" ]]; then
  step_skip "WhatsApp inbound runtime is removed and being rebuilt — skipping"
else
  step_skip "WhatsApp smoke not yet implemented in this script"
fi

# ----- 6. Dependency report -----
section "6. Dependency report"
DEP_REPORT="$(curl --fail --silent "$BASE_URL/v1/analytics/dependency-report" || true)"
if [[ -n "$DEP_REPORT" ]]; then
  step_pass "dependency-report endpoint reachable"
  echo "$DEP_REPORT" | jq '{generated_at, intent_count: (.intents // [] | length), dependency_count: (.dependencies // [] | length)}'
else
  step_fail "dependency-report endpoint failed"
fi

# ----- Summary -----
section "Summary"
echo "  pass: $PASS"
echo "  fail: $FAIL"
if [[ $FAIL -gt 0 ]]; then
  exit 1
fi
exit 0
