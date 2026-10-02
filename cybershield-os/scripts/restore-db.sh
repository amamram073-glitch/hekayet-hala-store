#!/usr/bin/env bash
set -Eeuo pipefail
if [[ $# -ne 2 || "$2" != "--confirm-overwrite" ]]; then
  echo "Usage: $0 /absolute/path/to/cybershield-db-YYYYMMDDTHHMMSSZ.dump --confirm-overwrite" >&2
  echo "This overwrites database objects. First place the application in maintenance mode and take a fresh backup." >&2
  exit 2
fi
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
DUMP="$(realpath "$1")"
[[ -s "$DUMP" ]] || { echo "Backup file is empty or missing" >&2; exit 1; }
docker compose exec -T postgres sh -c 'exec pg_restore --list' < "$DUMP" >/dev/null
echo "Restoring $DUMP into the configured database; existing objects will be replaced."
docker compose exec -T postgres sh -c 'exec pg_restore --clean --if-exists --no-owner -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$DUMP"
echo "Database restore completed. Verify migrations, organization counts, login and evidence references before leaving maintenance mode."
