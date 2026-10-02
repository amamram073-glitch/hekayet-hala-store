#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
BACKUP_DIR="${BACKUP_DIR:-$ROOT/backups}"
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DB_TMP="$BACKUP_DIR/cybershield-db-$STAMP.dump.partial"
EVIDENCE_TMP="$BACKUP_DIR/cybershield-evidence-$STAMP.tar.gz.partial"
DB_FILE="${DB_TMP%.partial}"
EVIDENCE_FILE="${EVIDENCE_TMP%.partial}"
cleanup() { rm -f "$DB_TMP" "$EVIDENCE_TMP"; }
trap cleanup EXIT

docker compose exec -T postgres sh -c 'exec pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > "$DB_TMP"
docker compose exec -T postgres sh -c 'exec pg_restore --list' < "$DB_TMP" >/dev/null
mv "$DB_TMP" "$DB_FILE"

docker compose exec -T api python -c 'import pathlib,sys,tarfile; p=pathlib.Path("/var/lib/cybershield/evidence"); t=tarfile.open(fileobj=sys.stdout.buffer,mode="w|gz"); t.add(p,arcname="evidence"); t.close()' > "$EVIDENCE_TMP"
gzip -t "$EVIDENCE_TMP"
mv "$EVIDENCE_TMP" "$EVIDENCE_FILE"
chmod 600 "$DB_FILE" "$EVIDENCE_FILE"
(
  cd "$BACKUP_DIR"
  sha256sum "$(basename "$DB_FILE")" "$(basename "$EVIDENCE_FILE")" > "cybershield-$STAMP.sha256"
  chmod 600 "cybershield-$STAMP.sha256"
)
printf 'Backup verified:\n  %s\n  %s\n  %s\n' "$DB_FILE" "$EVIDENCE_FILE" "$BACKUP_DIR/cybershield-$STAMP.sha256"
