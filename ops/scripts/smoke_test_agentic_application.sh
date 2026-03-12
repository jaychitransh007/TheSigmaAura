#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8010}"
USER_ID="${USER_ID:-}"
CONVERSATION_ID="${CONVERSATION_ID:-}"
FIRST_MESSAGE="${FIRST_MESSAGE:-Need a smart casual outfit for a work meeting}"
FOLLOWUP_MESSAGE="${FOLLOWUP_MESSAGE:-Show me something bolder}"

if [[ -z "$USER_ID" ]]; then
  echo "Set USER_ID to an onboarded user with completed analysis and style preference." >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required for this smoke test." >&2
  exit 1
fi

echo "Checking health at $BASE_URL/healthz"
curl --fail --silent "$BASE_URL/healthz" | jq .

if [[ -z "$CONVERSATION_ID" ]]; then
  echo
  echo "Creating conversation for user $USER_ID"
  CONVERSATION_ID="$(
    curl --fail --silent \
      -X POST "$BASE_URL/v1/conversations" \
      -H "Content-Type: application/json" \
      -d "{\"user_id\":\"$USER_ID\"}" \
      | jq -r '.conversation_id'
  )"
fi

echo "Conversation ID: $CONVERSATION_ID"

echo
echo "Sending first turn"
curl --fail --silent \
  -X POST "$BASE_URL/v1/conversations/$CONVERSATION_ID/turns" \
  -H "Content-Type: application/json" \
  -d "{\"user_id\":\"$USER_ID\",\"message\":\"$FIRST_MESSAGE\"}" \
  | jq '{
      turn_id,
      assistant_message,
      resolved_context,
      metadata,
      outfit_titles: [.outfits[]?.title]
    }'

if [[ -n "$FOLLOWUP_MESSAGE" ]]; then
  echo
  echo "Sending follow-up turn"
  curl --fail --silent \
    -X POST "$BASE_URL/v1/conversations/$CONVERSATION_ID/turns" \
    -H "Content-Type: application/json" \
    -d "{\"user_id\":\"$USER_ID\",\"message\":\"$FOLLOWUP_MESSAGE\"}" \
    | jq '{
        turn_id,
        assistant_message,
        resolved_context,
        metadata,
        outfit_titles: [.outfits[]?.title],
        follow_up_suggestions
      }'
fi
