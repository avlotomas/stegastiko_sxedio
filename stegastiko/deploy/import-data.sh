#!/bin/sh
# Replace the server database with a dumpdata export (see DEPLOY.md, step 6).
#   sh deploy/import-data.sh data.json [media.tar.gz]
# The current database is first backed up to ~/backup-before-import-<timestamp>.sql.gz.
set -e

if [ ! -f "$1" ]; then
    echo "usage: sh deploy/import-data.sh data.json [media.tar.gz]" >&2
    exit 1
fi
data=$(realpath "$1")
media=""
if [ -n "$2" ]; then
    media=$(realpath "$2")
fi
cd "$(dirname "$0")/.."

backup="$HOME/backup-before-import-$(date +%Y%m%d-%H%M%S).sql.gz"
docker compose exec -T db pg_dump -U stegastiko stegastiko | gzip > "$backup"
if [ "$(gzip -dc "$backup" | head -c 1 | wc -c)" -eq 0 ]; then
    echo "Backup is empty; aborting before changing the database." >&2
    exit 1
fi
echo "Backup: $backup"

docker compose cp "$data" web:/tmp/import.json
docker compose exec -T web python manage.py flush --noinput
docker compose exec -T web python manage.py loaddata /tmp/import.json
docker compose exec -T -u root web rm -f /tmp/import.json

if [ -n "$media" ]; then
    tmp=$(mktemp -d)
    tar -xzf "$media" -C "$tmp"
    docker compose cp "$tmp/." web:/data/media/
    docker compose exec -T -u root web chown -R app /data/media
    rm -rf "$tmp"
    echo "Media copied."
fi

docker compose exec -T web python manage.py shell --no-imports -c "
from django.apps import apps
skip = {'contenttypes.contenttype', 'auth.permission', 'sessions.session', 'admin.logentry'}
print('Rows imported:', sum(m.objects.count() for m in apps.get_models() if m._meta.label_lower not in skip))
"
