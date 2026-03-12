#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BUCKET="style-archetypes"
SRC_DIR="$ROOT_DIR/archetypes/choices"

if [[ ! -d "$SRC_DIR" ]]; then
  echo "missing source directory: $SRC_DIR" >&2
  exit 1
fi

TARGET="${1:-}"
if [[ "$TARGET" != "local" && "$TARGET" != "staging" ]]; then
  echo "usage: $0 local|staging" >&2
  exit 2
fi

SUPABASE_URL=""
SUPABASE_SERVICE_ROLE_KEY=""

if [[ "$TARGET" == "local" ]]; then
  ENV_FILE="$ROOT_DIR/.env.local"
  if [[ -f "$ENV_FILE" ]]; then
    while IFS='=' read -r key value; do
      [[ -z "${key// }" || "$key" =~ ^# ]] && continue
      value="${value%\"}"
      value="${value#\"}"
      case "$key" in
        SUPABASE_URL) SUPABASE_URL="$value" ;;
        SUPABASE_SERVICE_ROLE_KEY) SUPABASE_SERVICE_ROLE_KEY="$value" ;;
      esac
    done < "$ENV_FILE"
  fi
  if [[ -z "$SUPABASE_URL" || -z "$SUPABASE_SERVICE_ROLE_KEY" ]]; then
    while IFS= read -r line; do
      line="${line#export }"
      key="${line%%=*}"
      value="${line#*=}"
      value="${value%\"}"
      value="${value#\"}"
      case "$key" in
        API_URL) SUPABASE_URL="$value" ;;
        SERVICE_ROLE_KEY) SUPABASE_SERVICE_ROLE_KEY="$value" ;;
      esac
    done < <(supabase status -o env)
  fi
else
  ENV_FILE="$ROOT_DIR/.env.staging"
  if [[ ! -f "$ENV_FILE" ]]; then
    echo "missing staging env file: $ENV_FILE" >&2
    exit 3
  fi
  while IFS='=' read -r key value; do
    [[ -z "${key// }" || "$key" =~ ^# ]] && continue
    value="${value%\"}"
    value="${value#\"}"
    case "$key" in
      SUPABASE_URL) SUPABASE_URL="$value" ;;
      SUPABASE_SERVICE_ROLE_KEY) SUPABASE_SERVICE_ROLE_KEY="$value" ;;
    esac
  done < "$ENV_FILE"
fi

if [[ -z "$SUPABASE_URL" || -z "$SUPABASE_SERVICE_ROLE_KEY" ]]; then
  echo "missing Supabase URL or service role key for $TARGET" >&2
  exit 4
fi

uploaded=0
for path in "$SRC_DIR"/*.png; do
  name="$(basename "$path")"
  curl -sS \
    -X POST \
    -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY" \
    -H "apikey: $SUPABASE_SERVICE_ROLE_KEY" \
    -H "x-upsert: true" \
    -H "Content-Type: image/png" \
    --data-binary "@$path" \
    "$SUPABASE_URL/storage/v1/object/$BUCKET/choices/$name" \
    >/dev/null
  uploaded=$((uploaded + 1))
done

echo "uploaded $uploaded files to $TARGET bucket $BUCKET"
