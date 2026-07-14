#!/bin/bash
# Send awada invite control message and update customer status to exp_invited.
# --peer: DB primary key (from [CustomerDB].peer), used for all DB operations.
# --user-id-external: raw awada user ID (from Sender.id), used for the invite routing message.
# --force: force invite even if business_status is not 'free' (for re-invite requests).
set -euo pipefail

DB_FILE="./db/customer.db"

PEER=""
USER_ID_EXTERNAL=""
GROUP_NAME="风暴眼（wiseflow情报小站）"
FORCE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --peer)
      PEER="${2:-}"
      shift 2
      ;;
    --user-id-external)
      USER_ID_EXTERNAL="${2:-}"
      shift 2
      ;;
    --group-name)
      GROUP_NAME="${2:-}"
      shift 2
      ;;
    --force)
      FORCE="1"
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [ -z "$PEER" ]; then
  echo "❌ --peer is required (use [CustomerDB].peer)" >&2
  exit 1
fi

if [ -z "$USER_ID_EXTERNAL" ]; then
  echo "❌ --user-id-external is required (use Sender.id)" >&2
  exit 1
fi

WORKDIR="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$WORKDIR"

if [ ! -f "$DB_FILE" ]; then
  echo "❌ Database not found: $DB_FILE" >&2
  exit 1
fi

sql_quote() {
  printf '%s' "$1" | sed "s/'/''/g"
}

existing_status="$(sqlite3 "$DB_FILE" "SELECT business_status FROM cs_record WHERE peer = '$(sql_quote "$PEER")'" || true)"

if [ -z "$existing_status" ]; then
  sqlite3 "$DB_FILE" "INSERT INTO cs_record (peer, business_status, purpose, prompt_source) VALUES ('$(sql_quote "$PEER")', 'free', '', '')"
  existing_status="free"
fi

# Block auto-invite for non-free users, unless --force is specified
if [ "$existing_status" != "free" ] && [ -z "$FORCE" ]; then
  echo "ALREADY_INVITED"
  exit 10
fi

# Only update business_status to exp_invited if current status is free or empty
# For exp_invited/subs/club users with --force, don't change business_status
if [ "$existing_status" = "free" ] || [ -z "$existing_status" ]; then
  sqlite3 "$DB_FILE" "UPDATE cs_record SET business_status = 'exp_invited' WHERE peer = '$(sql_quote "$PEER")'"
fi

printf '/invite//%s//%s\n' "$USER_ID_EXTERNAL" "$GROUP_NAME"
