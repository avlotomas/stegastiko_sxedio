#!/bin/sh
# Server side of the automatic deploy (.github/workflows/deploy.yml). Runs after the checkout
# has been moved to the release tag: backs up the database, rebuilds the containers, waits for
# the migrations (run by deploy/entrypoint.sh) to finish.
set -e
cd "$(dirname "$0")/.."

mkdir -p "$HOME/backups"
backup="$HOME/backups/pre-deploy-$(date +%Y%m%d-%H%M%S).sql.gz"
docker compose exec -T db pg_dump -U stegastiko stegastiko | gzip > "$backup"
if [ "$(gzip -dc "$backup" | head -c 1 | wc -c)" -eq 0 ]; then
    echo "Database backup is empty; aborting the deploy." >&2
    exit 1
fi
echo "Backup: $backup"
# Keep the 10 most recent pre-deploy backups.
ls -1t "$HOME"/backups/pre-deploy-*.sql.gz | tail -n +11 | xargs -r rm --

docker compose up -d --build

tries=0
until docker compose exec -T web python manage.py migrate --check >/dev/null 2>&1; do
    tries=$((tries + 1))
    if [ "$tries" -gt 60 ]; then
        echo "web did not become ready (migrations failed?). Restore with:" >&2
        echo "  gunzip -c $backup | docker compose exec -T db psql -U stegastiko stegastiko" >&2
        docker compose logs --tail 50 web >&2
        exit 1
    fi
    sleep 3
done

docker image prune -f >/dev/null
echo "Deployed $(git describe --tags --always)"
